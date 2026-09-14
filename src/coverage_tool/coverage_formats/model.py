"""Canonical, compiler-agnostic coverage data model.

Every parser in this package (``lcov.py``, ``cobertura.py``) fills in
:class:`FileCoverage` instead of building its own JSON dict, so there is
exactly one place that turns "which lines ran how many times" into
covered/uncovered counts and percentages.
"""

from dataclasses import dataclass, field


@dataclass
class FileCoverage:
    """Per-file coverage data in a compiler-agnostic shape.

    ``execution_counts`` maps a 1-based line number to the number of times
    it executed (0 = instrumented but never hit). Function-level counts are
    tracked separately since not every format reports them per line.
    """

    execution_counts: dict[int, int] = field(default_factory=dict)
    function_total: int = 0
    function_covered: int = 0

    @property
    def covered_lines(self) -> set[int]:
        return {line for line, count in self.execution_counts.items() if count > 0}

    @property
    def uncovered_lines(self) -> set[int]:
        return {line for line, count in self.execution_counts.items() if count == 0}

    @property
    def line_total(self) -> int:
        return len(self.execution_counts)

    @property
    def line_covered(self) -> int:
        return len(self.covered_lines)


def _metric(total: int, covered: int) -> dict:
    """Build one of the total/covered/uncovered/percent metric blocks."""
    covered = min(covered, total)
    uncovered = total - covered
    percent = round((covered / total * 100), 2) if total > 0 else 0.0
    return {
        "total": total,
        "covered": covered,
        "uncovered": uncovered,
        "percent": percent,
    }


def build_summary_json(
    files: dict[str, FileCoverage], generator: str = "coverage_tool"
) -> dict:
    """Build the standard coverage_summary.json structure from parsed files.

    Args:
        files: Mapping of file path to its parsed FileCoverage.
        generator: Value written into metadata.generator.

    Returns:
        A dict matching the documented coverage_summary.json schema
        (metadata / summary / files), with region_coverage left at zero
        since no backend currently computes region-level data.
    """
    summary = {
        "metadata": {
            "format_version": "2.0",
            "generator": generator,
            "schema": "cobertura-compatible",
        },
        "summary": {
            "line_coverage": _metric(0, 0),
            "function_coverage": _metric(0, 0),
            "region_coverage": _metric(0, 0),
        },
        "files": [],
    }

    total_line_total = total_line_covered = 0
    total_func_total = total_func_covered = 0

    for filename, coverage in files.items():
        line_total = coverage.line_total
        line_covered = coverage.line_covered
        func_total = coverage.function_total
        func_covered = coverage.function_covered

        summary["files"].append(
            {
                "file": filename,
                "line_coverage": _metric(line_total, line_covered),
                "function_coverage": _metric(func_total, func_covered),
            }
        )

        total_line_total += line_total
        total_line_covered += line_covered
        total_func_total += func_total
        total_func_covered += func_covered

    summary["summary"]["line_coverage"] = _metric(total_line_total, total_line_covered)
    summary["summary"]["function_coverage"] = _metric(total_func_total, total_func_covered)

    return summary


def to_line_dicts(
    files: dict[str, FileCoverage],
) -> tuple[dict[str, set[int]], dict[str, set[int]], dict[str, dict[int, int]]]:
    """Adapt the canonical model to the (covered, uncovered, counts) dicts
    that ``html_report.HtmlGenerator.generate_report`` expects.
    """
    covered_lines: dict[str, set[int]] = {}
    uncovered_lines: dict[str, set[int]] = {}
    execution_counts: dict[str, dict[int, int]] = {}

    for filename, coverage in files.items():
        covered_lines[filename] = coverage.covered_lines
        uncovered_lines[filename] = coverage.uncovered_lines
        execution_counts[filename] = coverage.execution_counts

    return covered_lines, uncovered_lines, execution_counts
