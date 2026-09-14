"""Cross-platform C++ code coverage generation tool.

Supports GCC (lcov), Clang (LLVM), and MSVC (OpenCppCoverage) with automatic
compiler detection, producing a consistent JSON summary and HTML report
across all three backends. See README.md for usage.
"""

from .html_report import HtmlGenerator, JsonHtmlGenerator
from .run_coverage import get_coverage, main

__all__ = ["get_coverage", "main", "HtmlGenerator", "JsonHtmlGenerator"]

__version__ = "1.0.0"
