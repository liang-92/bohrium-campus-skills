"""paperkit - deterministic PDF -> evidence-linked structure for research papers.

The package is deliberately dependency-light: it runs on the Python standard
library alone and uses whatever PDF engine happens to be installed (PyMuPDF,
pdfplumber, pypdf, or the poppler CLI).  Every backend records its own
provenance so a downstream judge can tell how a string was obtained.
"""

__version__ = "1.0.0"

from .document import analyze, analyze_path  # noqa: F401
from .result import build_result, validate_result  # noqa: F401
