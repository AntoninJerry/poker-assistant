"""OCR readers built on EasyOCR with OpenCV pre-processing.

Implements prioritized reading of ROIs: pot → to_call → hero cards → board.
This module provides a high-level `OCRReader.read_state` API returning a
`GameState` datamodel parsed from the frame and room configuration.
"""

from __future__ import annotations

from dataclasses import dataclass

import cv2
import easyocr  # type: ignore[import-untyped]
import numpy as np
import numpy.typing as npt

from ..config import AppSettings
from .parsers import GameState, ParsedAmounts


@dataclass
class ROI:
    name: str
    x: int
    y: int
    w: int
    h: int


class OCRReader:
    def __init__(self) -> None:
        # Lazy load reader to avoid heavy startup cost if not needed later
        self._reader: easyocr.Reader | None = None

    def _get_reader(self) -> easyocr.Reader:
        if self._reader is None:
            # English and numbers should cover amounts; extend per room if needed
            self._reader = easyocr.Reader(["en"])
        return self._reader

    def _preprocess_amount(self, roi_img: npt.NDArray[np.uint8]) -> npt.NDArray[np.uint8]:
        gray = cv2.cvtColor(roi_img, cv2.COLOR_RGB2GRAY)
        gray = cv2.bilateralFilter(gray, d=5, sigmaColor=50, sigmaSpace=50)
        _, bw = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        bw_u8: npt.NDArray[np.uint8] = np.asarray(bw, dtype=np.uint8)
        return bw_u8

    def _read_text(self, image: npt.NDArray[np.uint8]) -> str:
        reader = self._get_reader()
        result = reader.readtext(image)
        texts = [t[1] for t in result]
        return " ".join(texts)

    def read_state(self, frame_rgb: npt.NDArray[np.uint8], config: AppSettings) -> GameState:
        # Placeholder ROIs; will be driven by YAML in next iterations
        h, w, _ = frame_rgb.shape
        roi_pot = ROI(
            "pot",
            x=int(0.45 * w),
            y=int(0.10 * h),
            w=int(0.10 * w),
            h=int(0.06 * h),
        )
        roi_to_call = ROI(
            "to_call",
            x=int(0.45 * w),
            y=int(0.85 * h),
            w=int(0.10 * w),
            h=int(0.06 * h),
        )

        pot_img = frame_rgb[
            roi_pot.y : roi_pot.y + roi_pot.h,
            roi_pot.x : roi_pot.x + roi_pot.w,
        ]
        call_img = frame_rgb[
            roi_to_call.y : roi_to_call.y + roi_to_call.h,
            roi_to_call.x : roi_to_call.x + roi_to_call.w,
        ]

        pot_text = self._read_text(self._preprocess_amount(pot_img))
        call_text = self._read_text(self._preprocess_amount(call_img))

        amounts = ParsedAmounts.from_texts(pot_text, call_text)

        return GameState(
            pot_bb=amounts.pot_bb,
            to_call_bb=amounts.to_call_bb,
            street="preflop",
            hero_cards=None,
            board_cards=None,
        )
