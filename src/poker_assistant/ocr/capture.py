"""Screen capture utilities using mss.

Captures exact client rectangles without DWM frames for reliable OCR.
"""

from dataclasses import dataclass

import mss
import numpy as np
import numpy.typing as npt


@dataclass
class GrabRect:
    left: int
    top: int
    width: int
    height: int


def grab_rect(rect: GrabRect) -> npt.NDArray[np.uint8]:
    """Grab a rectangular region of the screen as an RGB numpy array.

    Args:
        rect: Rectangle in absolute screen coordinates.

    Returns:
        RGB image (H, W, 3) uint8
    """
    with mss.mss() as sct:
        mon = {
            "left": int(rect.left),
            "top": int(rect.top),
            "width": int(rect.width),
            "height": int(rect.height),
        }
        raw = sct.grab(mon)
        # mss returns BGRA; convert to RGB by dropping alpha then reversing channels
        bgr: npt.NDArray[np.uint8] = np.array(raw)[:, :, :3]
        rgb: npt.NDArray[np.uint8] = bgr[:, :, ::-1]
        return rgb
