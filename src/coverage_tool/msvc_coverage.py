#!/usr/bin/env python3
"""MSVC-specific code coverage generation.

Handles coverage generation for MSVC compiler using OpenCppCoverage tool.
Generates both HTML and JSON coverage reports.
"""

import json
import re
import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Optional
import logging

from .common import (
    discover_test_executables,
    find_opencppcoverage,
    get_config,
    get_platform_config,
)
from .coverage_formats import FileCoverage, build_summary_json, parse_cobertura

logger = logging.getLogger(__name__)

# Windows drive letters, used to tell an already-absolute Cobertura path
# from a relative one that needs a drive prepended.
_DRIVE_LETTERS = tuple(f"{letter}:" for letter in "CDEFGHIJKLMNOPQRSTUVWXYZ")


def _generate_detailed_html_reports(html_dir: Path, raw_dir: Path, source_root: str) -> bool:
    """Generate detailed line-by-line HTML reports from Cobertura XML.

    Extracts source code and coverage data to create detailed per-file HTML reports
    with line-by-line coverage highlighting, matching the Clang coverage report format.

    Args:
        html_dir: Directory where HTML reports will be saved.
        raw_dir: Directory containing Cobertura XML files.
        source_root: Root directory for source files.

    Returns:
        True if reports were generated successfully, False otherwise.
    """
    try:
        from .html_report import HtmlGenerator

        if not raw_dir or not raw_dir.exists():
            print("No Cobertura XML directory found, skipping detailed HTML generation")
            return False

        xml_files = list(raw_dir.glob("*.xml"))
        if not xml_files:
            print("No Cobertura XML files found, skipping detailed HTML generation")
            return False

        covered_lines: dict[str, set] = {}
        uncovered_lines: dict[str, set] = {}
        execution_counts: dict[str, dict] = {}

        print(f"Parsing {len(xml_files)} Cobertura XML file(s) for detailed coverage...")

        for xml_file in xml_files:
            print(f"  Processing {xml_file.name}...")
            try:
                parsed = parse_cobertura(xml_file)
            except ET.ParseError as e:
                print(f"  Error parsing {xml_file.name}: {e}")
                continue

            for filename, file_cov in parsed.items():
                # Normalize path - convert to absolute Windows path
                norm_path = filename.replace('/', '\\')
                if not norm_path.startswith(_DRIVE_LETTERS):
                    # Relative path - prepend C: drive
                    norm_path = 'C:\\' + norm_path

                # Filter to only include source files from the source_root
                if source_root:
                    norm_src = source_root.replace('/', '\\').lower()
                    if norm_src not in norm_path.lower():
                        continue

                covered = file_cov.covered_lines
                uncovered = file_cov.uncovered_lines
                counts = file_cov.execution_counts

                if not covered and not uncovered:
                    continue

                # Verify the file exists before adding to coverage data
                if Path(norm_path).exists():
                    covered_lines[norm_path] = covered
                    uncovered_lines[norm_path] = uncovered
                    execution_counts[norm_path] = counts
                elif source_root:
                    # Try to find the file in the source_root
                    parts = norm_path.split('\\')
                    try:
                        lib_idx = next(i for i, p in enumerate(parts) if p.lower() == 'library')
                        rel_path = '\\'.join(parts[lib_idx:])
                        full_path = Path(source_root).parent / rel_path
                        if full_path.exists():
                            covered_lines[str(full_path)] = covered
                            uncovered_lines[str(full_path)] = uncovered
                            execution_counts[str(full_path)] = counts
                    except (StopIteration, IndexError):
                        pass

            print(f"    Found {len(covered_lines)} file(s) with coverage data")

        if not covered_lines and not uncovered_lines:
            print("Warning: No coverage data extracted from Cobertura XML")
            return False

        print(f"Generating detailed HTML reports for {len(covered_lines)} file(s)...")
        generator = HtmlGenerator(html_dir, source_root, preserve_hierarchy=True)
        generator.generate_report(covered_lines, uncovered_lines, execution_counts)
        print(f"Generated detailed HTML reports in: {html_dir}")
        return True

    except OSError as e:
        raise RuntimeError(f"Failed to generate detailed HTML reports: {e}") from e


def _generate_json_summary(html_dir: Path, output_dir: Path, raw_dir: Optional[Path] = None) -> dict:
    """Generate JSON coverage summary from OpenCppCoverage output.

    Prefers Cobertura XML (routed through the shared coverage_formats model,
    the same one the HTML report is built from, so the two stay in
    agreement); falls back to scraping OpenCppCoverage's own HTML output
    when no XML is available.

    Args:
        html_dir: Directory containing OpenCppCoverage HTML reports.
        output_dir: Directory where JSON report will be saved.
        raw_dir: Optional directory containing Cobertura XML files.

    Returns:
        Dictionary containing the coverage summary.
    """
    del output_dir  # kept for signature compatibility with callers

    all_files: dict[str, FileCoverage] = {}

    if raw_dir and raw_dir.exists():
        xml_files = list(raw_dir.glob("*.xml"))
        if xml_files:
            print(f"Found {len(xml_files)} Cobertura XML file(s), parsing for detailed coverage...")
            for xml_file in xml_files:
                try:
                    parsed = parse_cobertura(xml_file)
                except ET.ParseError as e:
                    logger.warning("Failed to parse Cobertura XML %s: %s", xml_file, e)
                    continue
                for filename, file_cov in parsed.items():
                    if filename not in all_files:
                        all_files[filename] = file_cov
                print(f"  Parsed {xml_file.name}: {len(parsed)} file(s) found")

    if all_files:
        return build_summary_json(all_files)

    # No Cobertura XML available — fall back to scraping the OpenCppCoverage
    # HTML output for an approximate summary.
    print("No Cobertura XML found, parsing HTML for coverage data...")
    summary = build_summary_json({})

    index_file = html_dir / "index.html"
    if not index_file.exists():
        print(f"Warning: OpenCppCoverage index.html not found at {index_file}")
        return summary

    with open(index_file, encoding='utf-8', errors='ignore') as f:
        content = f.read()
        coverage_pattern = r'(\d+(?:\.\d+)?)\s*%'
        matches = re.findall(coverage_pattern, content)
        if matches:
            try:
                overall_coverage = float(matches[0])
                summary["summary"]["line_coverage"]["percent"] = round(overall_coverage, 2)
            except (ValueError, IndexError):
                pass

    html_files = list(html_dir.glob("*.html"))
    print(f"Found {len(html_files)} HTML file(s) in coverage report")
    for html_file in html_files:
        if html_file.name == "index.html":
            continue
        try:
            with open(html_file, encoding='utf-8', errors='ignore') as f:
                file_content = f.read()
                file_data = {
                    "file": html_file.stem,
                    "line_coverage": {"total": 0, "covered": 0, "uncovered": 0, "percent": 0.0},
                }
                coverage_match = re.search(r'(\d+(?:\.\d+)?)\s*%', file_content)
                if coverage_match:
                    try:
                        file_data["line_coverage"]["percent"] = round(float(coverage_match.group(1)), 2)
                    except ValueError:
                        pass
                summary["files"].append(file_data)
        except OSError as e:
            logger.warning("Failed to parse %s: %s", html_file, e)

    return summary


def _save_json_report(summary: dict, output_dir: Path) -> None:
    """Save JSON coverage summary to file.

    Args:
        summary: Coverage summary dictionary.
        output_dir: Directory where JSON report will be saved.

    Raises:
        RuntimeError: If the report cannot be written.
    """
    try:
        json_file = output_dir / "coverage_summary.json"
        with open(json_file, 'w', encoding='utf-8') as f:
            json.dump(summary, f, indent=2)
        print(f"[OK] JSON coverage report saved to: {json_file}")
    except OSError as e:
        raise RuntimeError(f"Failed to save JSON report to {output_dir}: {e}") from e


def _verify_html_report(html_dir: Path) -> bool:
    """Verify that HTML coverage report exists.

    Args:
        html_dir: Directory containing HTML reports.

    Returns:
        True if HTML report exists, False otherwise.
    """
    if (html_dir / "index.html").exists():
        print(f"[OK] HTML coverage report available at: {html_dir}/index.html")
        return True
    else:
        print(f"Warning: HTML report not found at {html_dir}/index.html")
        return False


def _generate_json_from_html(html_dir: Path, output_dir: Path, raw_dir: Optional[Path] = None,
                             output_format: str = "html-and-json") -> Optional[dict]:
    """Generate JSON coverage report from OpenCppCoverage output.

    Args:
        html_dir: Directory containing OpenCppCoverage HTML reports.
        output_dir: Directory where JSON report will be saved.
        raw_dir: Optional directory containing Cobertura XML files.
        output_format: Output format - 'json', 'html', or 'html-and-json'

    Returns:
        The coverage summary dict if JSON output was generated, else None.
    """
    summary: Optional[dict] = _generate_json_summary(html_dir, output_dir, raw_dir)

    if output_format in ("json", "html-and-json"):
        _save_json_report(summary, output_dir)
    else:
        summary = None

    if output_format in ("html", "html-and-json"):
        _verify_html_report(html_dir)

    if output_format not in ("json", "html", "html-and-json"):
        print(f"Warning: Unknown output format '{output_format}', defaulting to html-and-json")
        _save_json_report(summary, output_dir)
        _verify_html_report(html_dir)

    return summary


def generate_msvc_coverage(
    build_dir: Path,
    modules: list[str],
    source_folder: Path,
    exclude_patterns: Optional[list[str]] = None,
    verbose: bool = False,
    output_format: str = "html-and-json"
) -> Optional[dict]:
    """Generate code coverage using opencppcoverage (for MSVC on Windows).

    Generates HTML reports in html/ folder and raw coverage data in raw/ folder.
    Uses coverage.toml / get_config() for all configurable parameters including exclude patterns.

    Args:
        build_dir: Path to build directory.
        modules: List of module names to analyze.
        source_folder: Path to source folder containing modules.
        exclude_patterns: List of patterns to exclude from coverage. If None, read from config.
        verbose: Enable verbose output for debugging. Default: False.
        output_format: Output format - 'json', 'html', or 'html-and-json'

    Returns:
        The coverage summary dict if JSON output was generated, else None.

    Raises:
        RuntimeError: If not on Windows, opencppcoverage not found, or no
            coverage output was produced at all.
    """
    build_dir = Path(build_dir)
    coverage_dir = build_dir / "coverage_report"
    html_dir = coverage_dir / "html"
    raw_dir = coverage_dir / "raw"

    html_dir.mkdir(parents=True, exist_ok=True)
    raw_dir.mkdir(parents=True, exist_ok=True)

    platform_cfg = get_platform_config()
    cfg = get_config()
    if exclude_patterns is None:
        excludes = cfg.get("exclude_patterns", [])
    else:
        excludes = exclude_patterns
    verify_timeout = cfg["msvc_verify_timeout"]
    coverage_timeout = cfg["msvc_coverage_timeout"]

    if verbose:
        print(f"[VERBOSE] Build directory: {build_dir}")
        print(f"[VERBOSE] Modules: {modules}")
        print(f"[VERBOSE] Exclusion patterns: {excludes}")
        print(f"[VERBOSE] Output format: {output_format}")

    if platform_cfg["os_name"] != "Windows":
        raise RuntimeError("MSVC coverage only supported on Windows")

    opencpp_path = find_opencppcoverage()
    if not opencpp_path:
        raise RuntimeError("OpenCppCoverage not found. Please install it.")

    print(f"OpenCppCoverage found at: {opencpp_path}")
    if verbose:
        print(f"[VERBOSE] OpenCppCoverage path: {opencpp_path}")

    print("\nDiscovering test executables...")
    test_executables = discover_test_executables(build_dir)

    if not test_executables:
        print("Warning: No test executables found")
        print(f"Searched in: {build_dir}")
        print("Expected locations:")
        print(f"  - {build_dir / 'bin'}")
        print(f"  - {build_dir / 'bin/Debug'}")
        print(f"  - {build_dir / 'bin/Release'}")
        print(f"  - {build_dir / 'lib'}")
        print(f"  - {build_dir / 'tests'}")
        return None

    print(f"Found {len(test_executables)} test executable(s):")
    for exe in test_executables:
        print(f"  - {exe.name} ({exe.stat().st_size} bytes)")
        if verbose:
            print(f"[VERBOSE]   Full path: {exe}")

    print("\nRunning coverage analysis...")
    print(f"Analyzing coverage for: {source_folder}")
    print(f"OpenCppCoverage path: {opencpp_path}")

    failed_tests = []
    successful_tests = 0

    for test_exe in test_executables:
        test_name = test_exe.stem
        separator = "=" * 60
        print(f"\n{separator}")
        print(f"Running coverage for: {test_name}")
        print(f"Executable: {test_exe}")
        print(separator)

        cov_cmd = [
            str(opencpp_path),
            "--optimized_build",  # suppress false-zero lines caused by inlining in Release builds
        ]
        cov_cmd.append(f"--export_type=html:{html_dir}")

        xml_file = raw_dir / f"{test_name}.xml"
        cov_cmd.append(f"--export_type=cobertura:{xml_file}")

        raw_file = raw_dir / f"{test_name}.cov"
        cov_cmd.append(f"--export_type=binary:{raw_file}")

        source_path = Path(source_folder)
        windows_source_path = str(source_path).replace("/", "\\")
        cov_cmd.append(f"--sources={windows_source_path}")

        if verbose:
            print(f"[VERBOSE] Applying {len(excludes)} exclusion patterns:")
            for exclude_pattern in excludes:
                print(f"[VERBOSE]   - {exclude_pattern}")

        for exclude_pattern in excludes:
            windows_pattern = exclude_pattern.replace("/", "\\")
            cov_cmd.append(f"--excluded_sources={windows_pattern}")

        cov_cmd.append("--")
        cov_cmd.append(str(test_exe))

        print(f"Command: {' '.join(cov_cmd)}\n")

        if verbose:
            print("[VERBOSE] OpenCppCoverage command:")
            print(f"[VERBOSE]   {' '.join(cov_cmd)}")
            print("[VERBOSE] Output files:")
            print(f"[VERBOSE]   HTML: {html_dir}")
            print(f"[VERBOSE]   XML: {xml_file}")
            print(f"[VERBOSE]   Binary: {raw_file}")

        # Each test's coverage run is independent — a failure here should not
        # abort the whole batch, so this stays resilient (unlike the parsing
        # helpers above, which now raise instead of swallowing errors).
        try:
            print("Verifying test executable runs...")
            if verbose:
                print(f"[VERBOSE] Running test executable: {test_exe}")
            verify_result = subprocess.run(
                [str(test_exe)],
                cwd=str(test_exe.parent),
                capture_output=True,
                text=True,
                timeout=verify_timeout,
                check=False
            )

            if verify_result.returncode != 0:
                print(f"Warning: Test executable returned non-zero exit code: {verify_result.returncode}")
                if verify_result.stderr:
                    print(f"  Test stderr: {verify_result.stderr[:200]}")
                if verbose:
                    print(f"[VERBOSE] Test stdout: {verify_result.stdout[:200]}")
            else:
                print("Test executable runs successfully")

            if verbose:
                print(f"[VERBOSE] Running OpenCppCoverage for {test_name}...")
            result = subprocess.run(
                cov_cmd,
                cwd=str(test_exe.parent),
                capture_output=True,
                text=True,
                check=False,
                timeout=coverage_timeout
            )

            if result.stdout:
                print(f"Coverage tool output:\n{result.stdout}")

            if result.returncode == 0:
                print(f"Coverage generated for: {test_name}")
                successful_tests += 1
                if verbose:
                    print(f"[VERBOSE] Successfully generated coverage for {test_name}")
            else:
                print(f"Coverage failed for: {test_name} (exit code: {result.returncode})")
                if result.stderr:
                    print(f"  Error: {result.stderr}")
                if verbose:
                    print(f"[VERBOSE] Coverage generation failed for {test_name}")
                    print(f"[VERBOSE] stderr: {result.stderr}")
                failed_tests.append(test_name)
        except subprocess.TimeoutExpired:
            print(f"Coverage timed out for: {test_name}")
            failed_tests.append(test_name)
        except OSError as e:
            print(f"Exception running coverage for {test_name}: {e}")
            failed_tests.append(test_name)

    html_files = list(html_dir.glob("**/*.html"))
    raw_files = list(raw_dir.glob("*.cov"))

    if verbose:
        print("[VERBOSE] Coverage output verification:")
        print(f"[VERBOSE] HTML files found: {len(html_files)}")
        for html_file in html_files[:5]:
            print(f"[VERBOSE]   - {html_file}")
        if len(html_files) > 5:
            print(f"[VERBOSE]   ... and {len(html_files) - 5} more")
        print(f"[VERBOSE] Raw coverage files found: {len(raw_files)}")
        for raw_file in raw_files:
            print(f"[VERBOSE]   - {raw_file}")

    separator = "=" * 60
    print(f"\n{separator}")
    print("Coverage Report Summary")
    print(separator)
    print(f"Tests processed: {successful_tests}/{len(test_executables)}")
    print(f"HTML files generated: {len(html_files)}")
    print(f"Raw coverage files: {len(raw_files)}")
    print(f"HTML report location: {html_dir}")
    print(f"Raw data location: {raw_dir}")

    if not html_files and not raw_files:
        raise RuntimeError("Coverage generation produced no output")

    if output_format in ["html", "html-and-json"]:
        print("\nGenerating detailed line-by-line HTML reports from Cobertura XML...")
        detailed_generated = _generate_detailed_html_reports(html_dir, raw_dir, str(source_folder))
        if not detailed_generated:
            print("Warning: Detailed HTML generation skipped or failed.")
    else:
        print("\nSkipping HTML generation (output format is json only)")

    summary: Optional[dict] = None
    if output_format in ["json", "html-and-json"]:
        print(f"\nGenerating {output_format} coverage report...")
        summary = _generate_json_from_html(html_dir, coverage_dir, raw_dir, output_format)
    else:
        print("\nSkipping JSON generation (output format is html only)")

    if failed_tests:
        print(f"\n{len(failed_tests)} test(s) had issues:")
        for test_name in failed_tests:
            print(f"  - {test_name}")
    else:
        print(f"\nAll {len(test_executables)} test(s) processed successfully!")

    return summary
