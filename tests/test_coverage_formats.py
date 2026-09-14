"""Tests for the shared coverage_formats parsers (lcov.py, cobertura.py, model.py).

These parsers are shared by all three compiler backends (GCC, Clang, MSVC),
so a fixture-level regression here would silently affect every backend at
once — see Tools/coverage/README.md's "Architecture" section.
"""

import unittest
from pathlib import Path

from coverage_tool.coverage_formats import (
    FileCoverage,
    build_summary_json,
    parse_cobertura,
    parse_lcov,
    to_line_dicts,
)

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"


class TestParseLcov(unittest.TestCase):
    """Tests for parse_lcov()."""

    def test_multi_da_records_recompute_from_da_not_lf_lh(self):
        """A line hit by multiple DA: records (e.g. template instantiations)
        counts as covered if any instantiation hit it, and totals are
        derived from DA: records rather than the file's own (here
        deliberately undercounting) LF:/LH: summary fields.
        """
        files = parse_lcov(FIXTURES_DIR / "multi_da.lcov")
        self.assertIn("/src/allocator.hpp", files)
        coverage = files["/src/allocator.hpp"]

        # LF:2/LH:1 in the fixture is deliberately wrong; the true DA:-derived
        # values are 3 unique lines (10, 11, 12), 2 covered (10 via max(1,0)=1, 11).
        self.assertEqual(coverage.line_total, 3)
        self.assertEqual(coverage.line_covered, 2)
        self.assertEqual(coverage.covered_lines, {10, 11})
        self.assertEqual(coverage.uncovered_lines, {12})
        self.assertEqual(coverage.function_total, 1)
        self.assertEqual(coverage.function_covered, 1)

    def test_full_coverage_file(self):
        files = parse_lcov(FIXTURES_DIR / "full_coverage.lcov")
        coverage = files["/src/full.cpp"]
        self.assertEqual(coverage.line_total, 3)
        self.assertEqual(coverage.line_covered, 3)
        self.assertEqual(coverage.uncovered_lines, set())

    def test_zero_coverage_file(self):
        files = parse_lcov(FIXTURES_DIR / "zero_coverage.lcov")
        coverage = files["/src/zero.cpp"]
        self.assertEqual(coverage.line_total, 2)
        self.assertEqual(coverage.line_covered, 0)
        self.assertEqual(coverage.covered_lines, set())

    def test_malformed_records_are_skipped_not_fatal(self):
        """Garbage DA:/FNF: records are skipped individually; a single
        corrupt line doesn't discard the rest of an otherwise valid file.
        """
        files = parse_lcov(FIXTURES_DIR / "malformed.lcov")
        coverage = files["/src/malformed.cpp"]

        # Only DA:10,2 was well-formed.
        self.assertEqual(coverage.execution_counts, {10: 2})
        # FNF:notanumber failed to parse and was skipped (stays at default 0).
        self.assertEqual(coverage.function_total, 0)
        # FNH:1 parsed fine.
        self.assertEqual(coverage.function_covered, 1)

    def test_missing_file_raises(self):
        """A missing LCOV file is a real error, not silently swallowed."""
        with self.assertRaises(OSError):
            parse_lcov(FIXTURES_DIR / "does_not_exist.lcov")


class TestParseCobertura(unittest.TestCase):
    """Tests for parse_cobertura()."""

    def test_parses_line_hits_per_file(self):
        files = parse_cobertura(FIXTURES_DIR / "sample_cobertura.xml")
        allocator = files["C:\\Project\\Library\\Memory\\allocator.cpp"]

        self.assertEqual(allocator.execution_counts, {1: 1, 2: 0, 3: 5, 4: 2})
        self.assertEqual(allocator.line_total, 4)
        self.assertEqual(allocator.line_covered, 3)
        self.assertEqual(allocator.uncovered_lines, {2})

    def test_malformed_line_entries_are_skipped(self):
        """A <line> with a non-numeric number or hits attribute is skipped;
        the well-formed <line> in the same class is still parsed.
        """
        files = parse_cobertura(FIXTURES_DIR / "sample_cobertura.xml")
        device = files["C:\\Project\\Library\\Memory\\device.cpp"]

        self.assertEqual(device.execution_counts, {1: 2})

    def test_missing_file_returns_empty_mapping(self):
        """Callers commonly probe several XML files and skip ones that
        don't exist yet — a missing file is not itself an error.
        """
        files = parse_cobertura(FIXTURES_DIR / "does_not_exist.xml")
        self.assertEqual(files, {})


class TestBuildSummaryJson(unittest.TestCase):
    """Tests for build_summary_json()."""

    def test_empty_input(self):
        summary = build_summary_json({})
        self.assertEqual(summary["summary"]["line_coverage"]["total"], 0)
        self.assertEqual(summary["summary"]["line_coverage"]["percent"], 0.0)
        self.assertEqual(summary["files"], [])

    def test_aggregates_across_files(self):
        files = {
            "a.cpp": FileCoverage(execution_counts={1: 1, 2: 0}, function_total=1, function_covered=1),
            "b.cpp": FileCoverage(execution_counts={1: 0, 2: 0}, function_total=1, function_covered=0),
        }
        summary = build_summary_json(files, generator="test_generator")

        self.assertEqual(summary["metadata"]["generator"], "test_generator")
        self.assertEqual(summary["summary"]["line_coverage"]["total"], 4)
        self.assertEqual(summary["summary"]["line_coverage"]["covered"], 1)
        self.assertEqual(summary["summary"]["line_coverage"]["percent"], 25.0)
        self.assertEqual(summary["summary"]["function_coverage"]["total"], 2)
        self.assertEqual(summary["summary"]["function_coverage"]["covered"], 1)
        self.assertEqual(len(summary["files"]), 2)

    def test_100_percent_coverage(self):
        files = {"a.cpp": FileCoverage(execution_counts={1: 1, 2: 2})}
        summary = build_summary_json(files)
        self.assertEqual(summary["summary"]["line_coverage"]["percent"], 100.0)

    def test_0_percent_coverage(self):
        files = {"a.cpp": FileCoverage(execution_counts={1: 0, 2: 0})}
        summary = build_summary_json(files)
        self.assertEqual(summary["summary"]["line_coverage"]["percent"], 0.0)


class TestToLineDicts(unittest.TestCase):
    """Tests for to_line_dicts(), the adapter feeding HtmlGenerator."""

    def test_adapts_canonical_model(self):
        files = {
            "a.cpp": FileCoverage(execution_counts={1: 1, 2: 0, 3: 4}),
        }
        covered, uncovered, counts = to_line_dicts(files)

        self.assertEqual(covered, {"a.cpp": {1, 3}})
        self.assertEqual(uncovered, {"a.cpp": {2}})
        self.assertEqual(counts, {"a.cpp": {1: 1, 2: 0, 3: 4}})


if __name__ == "__main__":
    unittest.main()
