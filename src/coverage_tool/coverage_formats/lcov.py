"""Shared LCOV parser, used by both the GCC and Clang backends.

Both ``gcov``/``lcov`` (GCC) and ``llvm-cov export -format=lcov`` (Clang)
produce the same LCOV text format, so there is no reason for each backend to
carry its own copy of this parser.
"""

import logging
from pathlib import Path

from .model import FileCoverage

logger = logging.getLogger(__name__)


def parse_lcov(lcov_file: Path) -> dict[str, FileCoverage]:
    """Parse an LCOV ``.info``/``.lcov`` file into the canonical model.

    Line totals/hits are recomputed from ``DA:`` records rather than trusted
    from the file's own ``LF:``/``LH:`` summary fields. For headers
    instantiated as multiple distinct templates (e.g. allocator<T> over
    several T/alignment combinations), llvm-cov's ``-format=lcov`` export
    can emit an LF:/LH: pair that undercounts relative to the DA: lines it
    wrote in the very same section — self-inconsistent output from the same
    tool run. Recomputing from DA: avoids that class of bug for every
    backend that shares this parser, and keeps the JSON summary in
    agreement with the HTML report (also built from DA: records via
    ``to_line_dicts``).

    A source line can carry multiple DA: records across distinct template
    instantiations in the same translation unit; it counts as covered if
    any instantiation hit it.

    Malformed individual records are skipped rather than aborting the whole
    parse — a single corrupt line shouldn't discard an otherwise valid
    report. A missing file raises normally (not swallowed here); callers
    that want a soft failure should catch it explicitly.

    Args:
        lcov_file: Path to the LCOV file.

    Returns:
        Mapping of source file path to its parsed FileCoverage.
    """
    files: dict[str, FileCoverage] = {}
    current_file: str = None
    current: FileCoverage = None

    with open(lcov_file, encoding="utf-8", errors="ignore") as f:
        for raw_line in f:
            line = raw_line.strip()

            if line.startswith("SF:"):
                current_file = line[3:]
                current = FileCoverage()
                files[current_file] = current

            elif line.startswith("DA:") and current is not None:
                parts = line[3:].split(",")
                if len(parts) >= 2:
                    try:
                        line_num = int(parts[0])
                        hit_count = int(parts[1])
                    except ValueError:
                        logger.debug("Skipping malformed DA: record: %s", line)
                        continue
                    current.execution_counts[line_num] = max(
                        current.execution_counts.get(line_num, 0), hit_count
                    )

            elif line.startswith("FNF:") and current is not None:
                try:
                    current.function_total = int(line[4:])
                except ValueError:
                    logger.debug("Skipping malformed FNF: record: %s", line)

            elif line.startswith("FNH:") and current is not None:
                try:
                    current.function_covered = int(line[4:])
                except ValueError:
                    logger.debug("Skipping malformed FNH: record: %s", line)

            elif line == "end_of_record":
                current_file = None
                current = None

    return files
