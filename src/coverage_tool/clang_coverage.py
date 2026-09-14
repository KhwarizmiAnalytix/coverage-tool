#!/usr/bin/env python3
"""Clang/LLVM-specific code coverage generation.

Handles coverage generation for Clang compiler using LLVM coverage tools
(llvm-profdata, llvm-cov). Generates both HTML and JSON coverage reports.
"""

import json
import os
import re
import subprocess
from pathlib import Path
from typing import Optional
import logging

from .common import (
    discover_tests_via_ctest,
    find_library,
    find_test_for_module,
    get_config,
    get_platform_config,
    resolve_multi_config_artifact,
)
from .coverage_formats import build_summary_json, parse_lcov, to_line_dicts

logger = logging.getLogger(__name__)

# Cache resolved tool names so detection runs only once per process.
_llvm_tool_cache: dict[str, str] = {}


def _clang_major_version() -> Optional[int]:
    """Return the major version of the clang compiler on PATH, or None."""
    for candidate in ["clang", "clang-cl"]:
        try:
            result = subprocess.run(
                [candidate, "--version"],
                capture_output=True, text=True, check=True
            )
            m = re.search(r"version\s+(\d+)", result.stdout)
            if m:
                return int(m.group(1))
        except (subprocess.CalledProcessError, FileNotFoundError):
            continue
    return None


def _resolve_llvm_tool(base_name: str) -> str:
    """Return the versioned LLVM tool that matches the clang compiler.

    Tries base_name-major first so that the tool version matches the profraw
    format produced by the compiler. Falls back to the unversioned base_name
    if no versioned variant is found.
    """
    if base_name in _llvm_tool_cache:
        return _llvm_tool_cache[base_name]

    major = _clang_major_version()
    if major is not None:
        versioned = f"{base_name}-{major}"
        try:
            subprocess.run(
                [versioned, "--version"],
                capture_output=True, text=True, check=True
            )
            logger.info("Using %s (matches clang %d)", versioned, major)
            _llvm_tool_cache[base_name] = versioned
            return versioned
        except (subprocess.CalledProcessError, FileNotFoundError):
            logger.warning(
                "%s not found; falling back to unversioned %s ",
                versioned, base_name
            )

    _llvm_tool_cache[base_name] = base_name
    return base_name


def _validate_llvm_tools() -> None:
    """Validate that required LLVM tools are available.

    Prefers versioned tools (e.g. llvm-profdata-18) that match the clang
    compiler to avoid raw-profile version mismatches.

    Raises:
        RuntimeError: If llvm-profdata or llvm-cov are not found.
    """
    for tool_base in ["llvm-profdata", "llvm-cov"]:
        tool = _resolve_llvm_tool(tool_base)
        try:
            subprocess.run(
                [tool, "--version"],
                capture_output=True,
                text=True,
                check=True
            )
        except (subprocess.CalledProcessError, FileNotFoundError) as e:
            raise RuntimeError(
                f"Required LLVM tool '{tool}' not found or not working. "
                f"Please ensure LLVM tools are installed and in PATH. Error: {e}"
            ) from e


def _generate_json_export(coverage_dir: Path, binaries: list[str],
                         output_format: str = "html-and-json",
                         source_root: str = "") -> Optional[dict]:
    """Generate JSON/HTML coverage export using llvm-cov export with lcov format.

    Note: LLVM 21.1.0 doesn't support JSON format directly, so we use lcov
    format and parse it into the canonical coverage model.

    Args:
        coverage_dir: Path to coverage report directory.
        binaries: List of binary objects to analyze.
        output_format: Output format - 'json', 'html', or 'html-and-json'
        source_root: Root directory for source files (for relative paths).

    Returns:
        The coverage summary dict if JSON output was generated, else None.

    Raises:
        RuntimeError: If LLVM tools are not available or export fails.
    """
    _validate_llvm_tools()

    lcov_file = coverage_dir / "coverage.lcov"
    export_cmd = [
        _resolve_llvm_tool("llvm-cov"), "export"
    ] + binaries + [
        f"-instr-profile={coverage_dir / 'all-merged.profdata'}",
        "-format=lcov"
    ]

    for pattern in get_config()["llvm_ignore_regex"]:
        export_cmd.insert(-2, f"-ignore-filename-regex={pattern}")

    try:
        result = subprocess.run(export_cmd, capture_output=True, text=True, check=True)
    except subprocess.CalledProcessError as e:
        error_msg = f"LLVM coverage export failed: {e}"
        if e.stderr:
            error_msg += f"\nError details: {e.stderr}"
        raise RuntimeError(error_msg) from e

    if not result.stdout:
        raise RuntimeError("llvm-cov export produced no output")

    with open(lcov_file, "w", encoding="utf-8") as f:
        f.write(result.stdout)
    print(f"LCOV file generated: {lcov_file}")

    return _generate_summary_json_from_lcov(lcov_file, coverage_dir, output_format, source_root)


def _generate_html_from_lcov(lcov_file: Path, coverage_dir: Path,
                             source_root: str = "") -> None:
    """Generate HTML coverage report directly from LCOV data.

    Args:
        lcov_file: Path to LCOV file.
        coverage_dir: Path to coverage report directory.
        source_root: Root directory for source files (for relative paths).

    Raises:
        RuntimeError: If the LCOV file cannot be parsed or the HTML report
            cannot be generated.
    """
    try:
        from .html_report import HtmlGenerator

        files = parse_lcov(lcov_file)
        covered_lines, uncovered_lines, execution_counts = to_line_dicts(files)

        html_dir = coverage_dir / "html"
        html_dir.mkdir(exist_ok=True)
        generator = HtmlGenerator(html_dir, source_root, preserve_hierarchy=True)
        generator.generate_report(covered_lines, uncovered_lines, execution_counts)
        print(f"[OK] HTML coverage report generated at: {html_dir}/index.html")
    except OSError as e:
        raise RuntimeError(f"Failed to generate HTML from LCOV data in {lcov_file}: {e}") from e


def _generate_summary_json_from_lcov(lcov_file: Path, coverage_dir: Path,
                                     output_format: str = "html-and-json",
                                     source_root: str = "") -> Optional[dict]:
    """Generate summary JSON and/or HTML from LCOV coverage data.

    Args:
        lcov_file: Path to LCOV file generated by llvm-cov export.
        coverage_dir: Path to coverage report directory.
        output_format: Output format - 'json', 'html', or 'html-and-json'
        source_root: Root directory for source files (for relative paths).

    Returns:
        The coverage summary dict if JSON output was generated, else None.

    Raises:
        RuntimeError: If the LCOV file cannot be parsed or written.
    """
    try:
        files = parse_lcov(lcov_file)
        summary = build_summary_json(files)
    except OSError as e:
        raise RuntimeError(f"Failed to parse LCOV data in {lcov_file}: {e}") from e

    if output_format not in ("json", "html", "html-and-json"):
        print(f"Warning: Unknown output format '{output_format}', defaulting to html-and-json")
        output_format = "html-and-json"

    result_summary: Optional[dict] = None

    if output_format in ("json", "html-and-json"):
        summary_file = coverage_dir / "coverage_summary.json"
        with open(summary_file, "w", encoding="utf-8") as f:
            json.dump(summary, f, indent=2)
        print(f"[OK] JSON coverage report saved to: {summary_file}")
        result_summary = summary

    if output_format in ("html", "html-and-json"):
        _generate_html_from_lcov(lcov_file, coverage_dir, source_root)

    return result_summary


def prepare_llvm_coverage(
    build_dir: Path,
    module_name: str,
    binaries_list: str,
    profraw_list: str,
    ctest_tests: Optional[dict[str, dict]] = None,
) -> bool:
    """Discover and run the test executable for a specific module.

    Prefers the CTest-registered command/working-directory for the module
    (see common.find_test_for_module) since that is accurate regardless of
    the project's directory layout; falls back to the
    {module}CxxTests naming template under build_dir/bin when CTest metadata
    isn't available (e.g. no CTest, or ctest not on PATH).

    Args:
        build_dir: Path to build directory.
        module_name: Name of the module to find tests for.
        binaries_list: Path to file for storing binary objects.
        profraw_list: Path to file for storing profraw files.
        ctest_tests: Pre-fetched output of discover_tests_via_ctest(), or
            None to skip CTest-based discovery entirely.

    Returns:
        True if coverage data was successfully generated, False otherwise.
    """
    platform_cfg = get_platform_config()
    exe_extension = platform_cfg["exe_extension"]
    bin_folder = platform_cfg["lib_folder"]
    dll_extension = platform_cfg["dll_extension"]

    cfg = get_config()
    coverage_report_dir = cfg["coverage_report_dir"]
    coverage_dir = build_dir / coverage_report_dir
    coverage_dir.mkdir(exist_ok=True)

    dll_path = find_library(build_dir, bin_folder, module_name, dll_extension)
    test_exe_name = cfg["test_exe_pattern"].format(module=module_name)
    profraw_name = cfg["profraw_pattern"].format(module=module_name)
    profraw_file = coverage_dir / profraw_name

    test_executable: Optional[Path] = None
    test_dir: Optional[Path] = None

    matched = find_test_for_module(ctest_tests or {}, module_name, cfg["test_exe_pattern"])
    if matched and matched["command"]:
        candidate = resolve_multi_config_artifact(Path(matched["command"][0]))
        if candidate is not None:
            test_executable = candidate
            if matched["cwd"]:
                test_dir = Path(matched["cwd"])

    if test_executable is None:
        # Fallback: template-based glob, for builds without CTest metadata.
        # Multi-config generators (Xcode, VS) use bin/<Config>/.
        test_dir_rel = cfg["test_dir_template"].format(
            filter=cfg["filter"], module=module_name
        )
        test_dir = build_dir / test_dir_rel
        test_executable = resolve_multi_config_artifact(
            build_dir / "bin" / f"{test_exe_name}{exe_extension}"
        )
        if test_executable is None:
            test_executable = build_dir / "bin" / f"{test_exe_name}{exe_extension}"

    if test_dir is None:
        test_dir = test_executable.parent

    # Validate that library was found
    if dll_path is None:
        print(f"Warning: Library not found for module {module_name}, skipping")
        return False

    if not test_executable.exists():
        print(f"Warning: Test executable not found for {module_name}, skipping")
        return False

    # Run test executable to generate profraw file
    env = os.environ.copy()
    env['LLVM_PROFILE_FILE'] = str(profraw_file)
    try:
        subprocess.run([str(test_executable)], env=env, check=False, cwd=str(test_dir), capture_output=True, text=True)
    except (subprocess.CalledProcessError, FileNotFoundError) as e:
        print(f"Warning: Could not execute {test_exe_name}: {e}")
        return False

    # Verify the profraw file was actually created — it won't be if the binary
    # was built without coverage instrumentation (-fprofile-instr-generate).
    if not profraw_file.exists():
        print(
            f"Warning: No profraw generated for {module_name} — "
            "binary may not have been built with coverage instrumentation "
            "(rebuild with ENABLE_COVERAGE=ON and reconfigure cmake)"
        )
        return False

    # Only write to files after all validations and successful test execution
    with open(binaries_list, 'a') as f:
        print(f"Adding {dll_path} to binaries list")
        f.write(f"-object={dll_path}\n")

    with open(binaries_list, 'a') as f:
        print(f"Adding {test_executable} to binaries list")
        f.write(f"-object={test_executable}\n")

    with open(profraw_list, 'a') as f:
        print(f"Adding {profraw_file} to profraw list")
        f.write(f"{profraw_file}\n")

    return True


def generate_llvm_coverage(
    build_dir: Path,
    modules: list[str],
    source_folder: Path,
    llvm_ignore_regex: Optional[list[str]] = None,
    exclude_patterns: Optional[list[str]] = None,
    verbose: bool = False,
    output_format: str = "html-and-json"
) -> Optional[dict]:
    """Generate code coverage using LLVM (for Clang).

    Args:
        build_dir: Path to build directory.
        modules: List of module names to analyze.
        source_folder: Path to source folder containing modules.
        llvm_ignore_regex: List of regex patterns to ignore. If None, read from config.
        exclude_patterns: List of file/folder patterns to exclude. If None, read from config
            (currently unused directly here — llvm_ignore_regex is what's applied to
            llvm-cov export; kept for CLI/API symmetry with the other backends).
        verbose: Enable verbose output for debugging. Default: False.
        output_format: Output format - 'json', 'html', or 'html-and-json'

    Returns:
        The coverage summary dict if JSON output was generated, else None.

    Raises:
        RuntimeError: If no modules could be processed, no profile data was
            generated, or the LLVM toolchain is unavailable/fails.
    """
    del exclude_patterns  # not directly consumed by the LLVM export step

    cfg = get_config()
    if llvm_ignore_regex is None:
        llvm_ignore_regex = cfg["llvm_ignore_regex"]

    if verbose:
        print(f"[VERBOSE] Build directory: {build_dir}")
        print(f"[VERBOSE] Modules: {modules}")
        print(f"[VERBOSE] LLVM ignore regex: {llvm_ignore_regex}")
        print(f"[VERBOSE] Output format: {output_format}")

    build_dir = Path(build_dir)
    coverage_dir = build_dir / "coverage_report"
    coverage_dir.mkdir(exist_ok=True)

    binaries_list = coverage_dir / "binaries.list"
    profraw_list = coverage_dir / "profraw.list"

    binaries_list.write_text("")
    profraw_list.write_text("")

    print("Discovering test executables...")
    ctest_tests = discover_tests_via_ctest(build_dir)
    if verbose:
        if ctest_tests:
            print(f"[VERBOSE] CTest reports {len(ctest_tests)} registered test(s)")
        else:
            print("[VERBOSE] No CTest metadata available; using template-based discovery")

    successful_modules = 0
    for module in modules:
        if verbose:
            print(f"[VERBOSE] Processing module: {module}")
        if prepare_llvm_coverage(build_dir, module, str(binaries_list), str(profraw_list), ctest_tests):
            successful_modules += 1
            if verbose:
                print(f"[VERBOSE] Successfully processed module: {module}")

    if successful_modules == 0:
        raise RuntimeError(
            f"No modules processed successfully out of {len(modules)}: {modules}"
        )

    print(f"Successfully processed {successful_modules}/{len(modules)} modules")

    print("Merging profile data...")
    profraw_files = [f for f in profraw_list.read_text().strip().split('\n') if f]

    if verbose:
        print(f"[VERBOSE] Found {len(profraw_files)} profraw files:")
        for pf in profraw_files:
            print(f"[VERBOSE]   - {pf}")

    if not profraw_files:
        raise RuntimeError("No profraw files generated")

    merge_cmd = [
        _resolve_llvm_tool("llvm-profdata"), "merge", "-o",
        str(coverage_dir / "all-merged.profdata"), "-sparse"
    ] + profraw_files

    if verbose:
        print(f"[VERBOSE] Running: {' '.join(merge_cmd)}")

    subprocess.run(merge_cmd, check=True)

    print("Generating coverage report...")
    binaries = [b for b in binaries_list.read_text().strip().split('\n') if b]

    if verbose:
        print(f"[VERBOSE] Found {len(binaries)} binaries:")
        for binary in binaries:
            print(f"[VERBOSE]   - {binary}")

    print(f"Generating {output_format} coverage report...")
    return _generate_json_export(coverage_dir, binaries, output_format, str(source_folder))
