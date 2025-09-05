"""ROI normalization and coordinate conversions."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple, Union
import numpy as np


@dataclass(frozen=True)
class ROI:
    """Region of Interest with absolute coordinates."""
    x: int
    y: int
    width: int
    height: int
    
    @property
    def center(self) -> Tuple[int, int]:
        """Get center point of ROI."""
        return (self.x + self.width // 2, self.y + self.height // 2)
    
    @property
    def bottom_right(self) -> Tuple[int, int]:
        """Get bottom-right corner."""
        return (self.x + self.width, self.y + self.height)
    
    def to_tuple(self) -> Tuple[int, int, int, int]:
        """Convert to (x, y, width, height) tuple."""
        return (self.x, self.y, self.width, self.height)
    
    def to_bbox(self) -> Tuple[int, int, int, int]:
        """Convert to bounding box (x1, y1, x2, y2)."""
        return (self.x, self.y, self.x + self.width, self.y + self.height)
    
    def scale(self, factor: float) -> ROI:
        """Scale ROI by factor."""
        return ROI(
            x=int(self.x * factor),
            y=int(self.y * factor),
            width=int(self.width * factor),
            height=int(self.height * factor)
        )
    
    def offset(self, dx: int, dy: int) -> ROI:
        """Offset ROI by dx, dy."""
        return ROI(
            x=self.x + dx,
            y=self.y + dy,
            width=self.width,
            height=self.height
        )


@dataclass(frozen=True)
class RelativeROI:
    """ROI with relative coordinates (0.0 to 1.0)."""
    x: float
    y: float
    width: float
    height: float
    
    def to_absolute(self, parent_width: int, parent_height: int) -> ROI:
        """Convert to absolute ROI within parent dimensions."""
        return ROI(
            x=int(self.x * parent_width),
            y=int(self.y * parent_height),
            width=int(self.width * parent_width),
            height=int(self.height * parent_height)
        )
    
    @classmethod
    def from_absolute(cls, roi: ROI, parent_width: int, parent_height: int) -> RelativeROI:
        """Create relative ROI from absolute ROI."""
        return cls(
            x=roi.x / parent_width,
            y=roi.y / parent_height,
            width=roi.width / parent_width,
            height=roi.height / parent_height
        )


class ROIManager:
    """Manages ROI conversions and normalization."""
    
    def __init__(self, table_roi: ROI):
        """Initialize with table ROI as reference."""
        self.table_roi = table_roi
    
    def normalize_roi(self, roi: Union[ROI, Dict], relative: bool = False) -> ROI:
        """Normalize ROI to absolute coordinates."""
        if isinstance(roi, dict):
            roi = ROI(**roi)
        
        if relative:
            # Convert relative to absolute within table
            return roi.to_absolute(self.table_roi.width, self.table_roi.height)
        
        # Already absolute, just return
        return roi
    
    def to_table_coordinates(self, roi: ROI) -> ROI:
        """Convert ROI to table-relative coordinates."""
        return ROI(
            x=roi.x - self.table_roi.x,
            y=roi.y - self.table_roi.y,
            width=roi.width,
            height=roi.height
        )
    
    def to_screen_coordinates(self, roi: ROI) -> ROI:
        """Convert table-relative ROI to screen coordinates."""
        return ROI(
            x=roi.x + self.table_roi.x,
            y=roi.y + self.table_roi.y,
            width=roi.width,
            height=roi.height
        )
    
    def validate_roi(self, roi: ROI) -> bool:
        """Validate ROI is within table bounds."""
        return (
            roi.x >= 0 and
            roi.y >= 0 and
            roi.x + roi.width <= self.table_roi.width and
            roi.y + roi.height <= self.table_roi.height
        )
    
    def clip_roi(self, roi: ROI) -> ROI:
        """Clip ROI to table bounds."""
        x = max(0, min(roi.x, self.table_roi.width - roi.width))
        y = max(0, min(roi.y, self.table_roi.height - roi.height))
        width = min(roi.width, self.table_roi.width - x)
        height = min(roi.height, self.table_roi.height - y)
        
        return ROI(x=x, y=y, width=width, height=height)


def parse_roi_config(roi_data: Union[Dict, List]) -> Dict[str, ROI]:
    """Parse ROI configuration from YAML/JSON."""
    rois = {}
    
    if isinstance(roi_data, dict):
        for name, roi_dict in roi_data.items():
            if isinstance(roi_dict, dict) and all(k in roi_dict for k in ['x', 'y', 'width', 'height']):
                rois[name] = ROI(**roi_dict)
    
    return rois


def roi_overlap(roi1: ROI, roi2: ROI) -> bool:
    """Check if two ROIs overlap."""
    return not (
        roi1.x + roi1.width <= roi2.x or
        roi2.x + roi2.width <= roi1.x or
        roi1.y + roi1.height <= roi2.y or
        roi2.y + roi2.height <= roi1.y
    )


def roi_intersection(roi1: ROI, roi2: ROI) -> Optional[ROI]:
    """Get intersection of two ROIs."""
    if not roi_overlap(roi1, roi2):
        return None
    
    x = max(roi1.x, roi2.x)
    y = max(roi1.y, roi2.y)
    width = min(roi1.x + roi1.width, roi2.x + roi2.width) - x
    height = min(roi1.y + roi1.height, roi2.y + roi2.height) - y
    
    return ROI(x=x, y=y, width=width, height=height)


def roi_union(roi1: ROI, roi2: ROI) -> ROI:
    """Get union of two ROIs."""
    x = min(roi1.x, roi2.x)
    y = min(roi1.y, roi2.y)
    width = max(roi1.x + roi1.width, roi2.x + roi2.width) - x
    height = max(roi1.y + roi1.height, roi2.y + roi2.height) - y
    
    return ROI(x=x, y=y, width=width, height=height)


def roi_area(roi: ROI) -> int:
    """Calculate ROI area."""
    return roi.width * roi.height


def roi_aspect_ratio(roi: ROI) -> float:
    """Calculate ROI aspect ratio (width/height)."""
    return roi.width / roi.height if roi.height > 0 else 0.0
