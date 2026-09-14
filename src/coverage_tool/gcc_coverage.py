#!/usr/bin/env python3
"""GCC/gcov-specific code coverage generation.

Handles coverage generation for GCC compiler using lcov/genhtml tools.
Generates both HTML and JSON coverage reports with consistent styling.
"""

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Optional

import logging

from .common import discover_modules, get_config
from .coverage_formats import build_summary_json, parse_lcov, to_line_dicts

logger = logging.getLogger(__name__)


def _check_required_tools() -> tuple[bool, list[str]]:
    """Check if required tools for GCC coverage are installed.

    Returns:
        Tuple of (all_found: bool, missing_tools: List[str])
    """
    required_tools = ["lcov", "genhtml", "gcov"]
    missing = [tool for tool in required_tools if shutil.which(tool) is None]
    return len(missing) == 0, missing


def _generate_json_from_lcov(lcov_file: Path, output_dir: Path) -> dict:
    """Generate JSON coverage report from LCOV data.

    Args:
        lcov_file: Path to the LCOV coverage file.
        output_dir: Directory where JSON report will be saved.

    Returns:
        The coverage summary dict that was written to disk.

    Raises:
        RuntimeError: If the LCOV file cannot be parsed or written.
    """
    try:
        files = parse_lcov(lcov_file)
        summary = build_summary_json(files)

        json_file = output_dir / "coverage_summary.json"
        with open(json_file, "w", encoding="utf-8") as f:
            json.dump(summary, f, indent=2)
        print(f"JSON coverage report saved to: {json_file}")
        return summary
    except OSError as e:
        raise RuntimeError(f"Failed to generate JSON from LCOV data in {lcov_file}: {e}") from e


def _generate_html_from_lcov(lcov_file: Path, output_dir: Path,
                             source_root: str = "") -> None:
    """Generate HTML coverage report directly from LCOV data using custom templates.

    Args:
        lcov_file: Path to the LCOV coverage file.
        output_dir: Directory where HTML report will be saved.
        source_root: Root directory for source files (for relative paths).

    Raises:
        RuntimeError: If the LCOV file cannot be parsed or the HTML report
            cannot be generated.
    """
    try:
        from .html_report import HtmlGenerator

        files = parse_lcov(lcov_file)
        covered_lines, uncovered_lines, execution_counts = to_line_dicts(files)

        html_dir = output_dir / "html"
        html_dir.mkdir(exist_ok=True)
        generator = HtmlGenerator(html_dir, source_root, preserve_hierarchy=True)
        generator.generate_report(covered_lines, uncovered_lines, execution_counts)
        print(f"HTML coverage report generated at: {html_dir}/index.html")
    except OSError as e:
        raise RuntimeError(f"Failed to generate HTML from LCOV data in {lcov_file}: {e}") from e


def generate_lcov_coverage(build_dir: Path, modules: list[str],
                          exclude_patterns: Optional[list[str]] = None,
                          verbose: bool = False,
                          output_format: str = "json",
                          source_root: str = "") -> Optional[dict]:
    """
    Generate LCOV coverage report from build directory.

    Args:
        build_dir: Path to the build directory containing .gcda files
        modules: List of modules to include in coverage (currently informational
            only — lcov captures the whole build directory and filtering is done
            via exclude_patterns; kept for CLI/API symmetry with the other backends)
        exclude_patterns: List of patterns to exclude (e.g., ['/usr/*', '*/ThirdParty/*'])
        verbose: Enable verbose output for debugging
        output_format: Output format - 'json', 'html', or 'html-and-json'
        source_root: Root directory for source files (for relative paths).

    Returns:
        The coverage summary dict if JSON output was generated, else None.

    Raises:
        RuntimeError: If required tools are missing, lcov fails, or no
            coverage data was produced.
    """
    del modules  # not used directly by lcov's whole-build-dir capture

    tools_ok, missing_tools = _check_required_tools()
    if not tools_ok:
        raise RuntimeError(
            f"Required tools not found: {', '.join(missing_tools)}. "
            "Install lcov (Ubuntu/Debian: apt-get install lcov, "
            "Fedora/RHEL: dnf install lcov, macOS: brew install lcov)."
        )

    cfg = get_config()

    if exclude_patterns is None:
        exclude_patterns = []

    default_excludes = cfg["exclude_patterns"]
    exclude_patterns = list(set(default_excludes + exclude_patterns))

    coverage_info = build_dir / "coverage.info"
    coverage_filtered = build_dir / "coverage_filtered.info"
    coverage_report_dir = build_dir / cfg["coverage_report_dir"]
    coverage_report_dir.mkdir(parents=True, exist_ok=True)

    if verbose:
        print(f"[VERBOSE] Build directory: {build_dir}")
        print(f"[VERBOSE] Exclusion patterns: {exclude_patterns}")
        print(f"[VERBOSE] Output format: {output_format}")

    print(f"Capturing coverage data from {build_dir}...")

    capture_cmd = [
        "lcov",
        "--directory", str(build_dir),
        "--capture",
        "--ignore-errors", ",".join(cfg["lcov_ignore_errors"]),
        "--output-file", str(coverage_info)
    ]

    if verbose:
        print(f"[VERBOSE] Running: {' '.join(capture_cmd)}")

    result = subprocess.run(capture_cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"lcov --capture failed: {result.stderr}")

    coverage_info_size = coverage_info.stat().st_size if coverage_info.exists() else 0
    if coverage_info_size == 0:
        raise RuntimeError(
            "coverage.info is empty after capture. Possible causes: no tests were "
            "executed, no .gcda files were generated (check compilation flags), "
            "or tests didn't exercise any instrumented code. Debug with: "
            f"find {build_dir} -name '*.gcda'"
        )

    if verbose:
        print(f"[VERBOSE] coverage.info size: {coverage_info_size} bytes")

    print("Coverage data captured successfully.")
    print(f"Filtering exclusions: {exclude_patterns}")

    remove_cmd = ["lcov", "--remove", str(coverage_info)]
    remove_cmd.extend(exclude_patterns)
    remove_cmd.extend(["--ignore-errors", ",".join(cfg["lcov_ignore_errors"])])
    remove_cmd.extend(["--output-file", str(coverage_filtered)])

    if verbose:
        print(f"[VERBOSE] Running: {' '.join(remove_cmd)}")

    result = subprocess.run(remove_cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"lcov --remove failed: {result.stderr}")

    coverage_filtered_size = coverage_filtered.stat().st_size if coverage_filtered.exists() else 0
    if coverage_filtered_size == 0:
        raise RuntimeError(
            "coverage_filtered.info is empty after filtering — the exclusion "
            f"patterns removed all coverage data: {exclude_patterns}"
        )

    if verbose:
        print(f"[VERBOSE] coverage_filtered.info size: {coverage_filtered_size} bytes")

    print("Coverage data filtered.")

    summary: Optional[dict] = None
    if output_format in ("json", "html-and-json"):
        print("Generating JSON coverage report...")
        summary = _generate_json_from_lcov(coverage_filtered, coverage_report_dir)
        print(f"[OK] JSON coverage report generated at {coverage_report_dir}/coverage_summary.json")

    if output_format in ("html", "html-and-json"):
        print(f"Generating HTML report to {coverage_report_dir}...")
        _generate_html_from_lcov(coverage_filtered, coverage_report_dir, source_root)
        print(f"[OK] HTML coverage report generated at {coverage_report_dir}/html/index.html")

    if output_format not in ("json", "html", "html-and-json"):
        print(f"Warning: Unknown output format '{output_format}', defaulting to JSON")
        summary = _generate_json_from_lcov(coverage_filtered, coverage_report_dir)

    return summary


def main():
    """Main entry point for command-line usage."""
    parser = argparse.ArgumentParser(
        description="GCC Coverage Report Generator",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Output Formats:
  json              Generate JSON coverage data only (default)
  html              Generate HTML report directly from coverage data
  html-and-json    Generate both HTML and JSON coverage reports

Examples:
  # Generate JSON only (default)
  python -m coverage_tool.gcc_coverage --build=build_ninja_python --filter=Library

  # Generate HTML report directly
  python -m coverage_tool.gcc_coverage --build=build_ninja_python --filter=Library --output=html

  # Verbose output
  python -m coverage_tool.gcc_coverage --build=build_ninja_python --filter=Library --output=html --verbose
        """
    )

    parser.add_argument(
        "--build",
        required=True,
        help="Build directory path containing .gcda files"
    )
    parser.add_argument(
        "--filter",
        default="Library",
        help="Filter folder name (default: Library)"
    )
    parser.add_argument(
        "--output", "-o",
        choices=["json", "html", "html-and-json"],
        default="json",
        help="Output format: json (default), html, or html-and-json"
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable verbose output for debugging"
    )
    parser.add_argument(
        "--exclude",
        action="append",
        help="Additional exclusion patterns (can be specified multiple times)"
    )

    args = parser.parse_args()

    build_dir = Path(args.build)
    if not build_dir.is_absolute():
        build_dir = Path.cwd() / build_dir
    build_dir = build_dir.resolve()

    if not build_dir.exists():
        print(f"Error: Build directory does not exist: {build_dir}", file=sys.stderr)
        sys.exit(1)

    source_dir = Path.cwd() / args.filter
    if not source_dir.exists():
        print(f"Error: Source directory does not exist: {source_dir}", file=sys.stderr)
        sys.exit(1)

    modules = discover_modules(source_dir)

    if not modules:
        print(f"Error: No modules found in {source_dir}", file=sys.stderr)
        sys.exit(1)

    if args.verbose:
        print(f"Build directory: {build_dir}")
        print(f"Source directory: {source_dir}")
        print(f"Modules: {', '.join(modules)}")
        print(f"Output format: {args.output}")

    try:
        generate_lcov_coverage(
            build_dir=build_dir,
            modules=modules,
            exclude_patterns=args.exclude,
            verbose=args.verbose,
            output_format=args.output
        )
        print("\n[SUCCESS] Coverage generation completed.")
    except RuntimeError as e:
        print(f"Error: {e}", file=sys.stderr)
        if args.verbose:
            import traceback
            traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
