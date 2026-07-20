"""
XMatcher - industrial XRD phase matching toolkit.

The public API is intentionally small:
    - XRDRetriever: high-level search interface
    - XRDMatcher: peak-level scoring engine
    - PeakDetector: experimental peak detection
    - XRDReader: experimental data reader
    - DatabaseBuilder: offline database builder
"""

from .database import DatabaseBuilder, DatabaseProcessor, XRDCalculator
from .matcher import XRDMatcher
from .multiphase_matcher import MultiPhaseMatcher
from .peak_detector import PeakDetector
from .retriever import XRDRetriever
from .xrd_reader import XRDReader

__version__ = "1.1.0"
__author__ = "Bin Cao"
__email__ = "bcao686@connect.hkust-gz.edu.cn"
__github__ = "https://github.com/Bin-Cao/XMatcher"

__all__ = [
    "DatabaseBuilder",
    "DatabaseProcessor",
    "PeakDetector",
    "XRDRetriever",
    "XRDCalculator",
    "XRDMatcher",
    "MultiPhaseMatcher",
    "XRDReader",
]
