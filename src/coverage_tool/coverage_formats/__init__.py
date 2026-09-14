"""Compiler-agnostic coverage format parsing.

Every backend (GCC/lcov, Clang/LLVM, MSVC/OpenCppCoverage) parses its own
raw coverage format into the shared :class:`FileCoverage` model here, then
hands off to :func:`build_summary_json` and/or the HTML generator. Keeping
the parsing and summary-math in one place means a correctness fix (see the
DA:-recompute note in ``lcov.py``) applies to every backend at once instead
of needing to be re-applied per compiler.
"""

from .cobertura import parse_cobertura
from .lcov import parse_lcov
from .model import FileCoverage, build_summary_json, to_line_dicts

__all__ = [
    "FileCoverage",
    "build_summary_json",
    "to_line_dicts",
    "parse_lcov",
    "parse_cobertura",
]
