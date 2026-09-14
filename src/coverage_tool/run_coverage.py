#!/usr/bin/env python3
"""Code coverage generation tool.

Supports multiple compilers (Clang, GCC, MSVC) with automatic detection.
Generates HTML reports and JSON summaries for code coverage analysis.
"""

import sys
import subprocess
import argparse
from pathlib import Path
from typing import Optional, Union

# Import compiler-specific modules
from .gcc_coverage import generate_lcov_coverage as gcc_generate_coverage
from .clang_coverage import generate_llvm_coverage as clang_generate_coverage
from .msvc_coverage import generate_msvc_coverage as msvc_generate_coverage

# Import common utilities
from .common import (
    load_config,
    get_project_root,
    discover_modules,
    resolve_build_dir,
    detect_compiler,
    merge_exclude_patterns,
    parse_exclude_patterns_string,
)



def _check_min_coverage(coverage_summary: Optional[dict], min_coverage: Optional[float]) -> None:
    """Enforce a minimum line-coverage threshold, if one was requested.

    Args:
        coverage_summary: The coverage_summary.json-shaped dict returned by
            a backend's generate_*_coverage(), or None if no JSON summary
            was produced.
        min_coverage: Minimum required line-coverage percent, or None to
            skip the check entirely.

    Raises:
        RuntimeError: If a threshold was requested but no summary is
            available, or coverage falls short of it.
    """
    if min_coverage is None:
        return

    if coverage_summary is None:
        raise RuntimeError(
            "--min-coverage was requested but no JSON coverage summary was "
            "generated (requires --output=json or html-and-json)"
        )

    percent = coverage_summary.get("summary", {}).get("line_coverage", {}).get("percent", 0.0)
    if percent < min_coverage:
        raise RuntimeError(
            f"Line coverage {percent:.2f}% is below the required minimum of "
            f"{min_coverage:.2f}%"
        )
    print(f"[OK] Line coverage {percent:.2f}% meets the minimum of {min_coverage:.2f}%")


def get_coverage(
    compiler: str = "auto",
    build_folder: Union[str, Path] = ".",
    source_folder: Union[str, Path] = "Library",
    output_folder: Optional[Union[str, Path]] = None,
    exclude: Optional[list[str]] = None,
    exclude_patterns: Optional[list[str]] = None,
    verbose: bool = False,
    summary: bool = True,
    project_root: Optional[Union[str, Path]] = None,
    output_format: str = "html-and-json",
    min_coverage: Optional[float] = None,
) -> int:
    """Generate code coverage report for the project.

    Provides a programmatic interface for coverage generation with automatic
    compiler detection. Supports Clang, GCC, and MSVC compilers.

    Args:
        compiler: Compiler to use ('clang', 'gcc', 'msvc', or 'auto' for
            automatic detection). Default: 'auto'.
        build_folder: Path to build directory (absolute or relative to
            project_root). Default: '.'.
        source_folder: Path to source directory (absolute or relative to
            project_root). Default: 'Library'.
        output_folder: Path to output directory. If None, uses
            build_folder/coverage_report. Default: None.
        exclude: List of folders to exclude from coverage analysis (deprecated,
            use exclude_patterns instead). Default: None.
        exclude_patterns: List of patterns to exclude from coverage analysis.
            Merged with default patterns. Default: None.
        verbose: Enable verbose output for debugging. Default: False.
        summary: Whether to generate and display summary report.
            Default: True.
        project_root: Project root directory for resolving relative paths.
            If None, uses current directory. Default: None.
        output_format: Output format for all compilers - 'json', 'html', or
            'html-and-json'. Default: 'html-and-json'.
        min_coverage: Minimum required line-coverage percent. If set,
            requires JSON output (output_format 'json' or 'html-and-json')
            and returns a non-zero exit code when coverage falls short.
            Default: None (no gate).

    Returns:
        Exit code (0 for success, non-zero for failure).

    Raises:
        ValueError: If paths are invalid or compiler cannot be detected.
        RuntimeError: If required tools are not found.
    """
    try:
        # Resolve paths
        if project_root is None:
            project_root = Path.cwd()
        else:
            project_root = Path(project_root)

        build_path = Path(build_folder)
        if not build_path.is_absolute():
            build_path = project_root / build_path
        build_path = build_path.resolve()

        source_path = Path(source_folder)
        if not source_path.is_absolute():
            source_path = project_root / source_path
        source_path = source_path.resolve()

        if output_folder is None:
            output_path = build_path / "coverage_report"
        else:
            output_path = Path(output_folder)
            if not output_path.is_absolute():
                output_path = project_root / output_path
            output_path = output_path.resolve()

        # Validate paths
        if not build_path.exists():
            raise ValueError(f"Build directory does not exist: {build_path}")
        if not source_path.exists():
            raise ValueError(f"Source directory does not exist: {source_path}")

        # Detect compiler if needed
        if compiler == "auto":
            compiler = detect_compiler(build_path)

        compiler = compiler.lower()
        if compiler not in ["clang", "gcc", "msvc"]:
            raise ValueError(f"Unsupported compiler: {compiler}")

        # Create output directory
        output_path.mkdir(parents=True, exist_ok=True)

        modules = discover_modules(source_path)

        if not modules:
            raise ValueError(f"No modules found in {source_path}")

        # Merge exclude patterns (user patterns override defaults)
        merged_patterns = merge_exclude_patterns(exclude_patterns, include_defaults=True)

        # Run coverage based on compiler
        coverage_summary: Optional[dict] = None
        if compiler == "msvc":
            print("Generating MSVC coverage...")
            coverage_summary = msvc_generate_coverage(
                build_path, modules, source_path,
                exclude_patterns=merged_patterns,
                verbose=verbose,
                output_format=output_format)
        elif compiler == "clang":
            print("Generating Clang coverage...")
            coverage_summary = clang_generate_coverage(
                build_path, modules, source_path,
                exclude_patterns=merged_patterns,
                verbose=verbose,
                output_format=output_format)
        elif compiler == "gcc":
            print("Generating GCC coverage...")
            coverage_summary = gcc_generate_coverage(
                build_path, modules, verbose=verbose,
                exclude_patterns=merged_patterns,
                output_format=output_format)

        _check_min_coverage(coverage_summary, min_coverage)

        return 0

    except (ValueError, RuntimeError, subprocess.CalledProcessError) as e:
        print(f"Coverage generation failed: {e}", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"Unexpected error during coverage generation: {e}",
              file=sys.stderr)
        return 1


def print_help() -> None:
    """Print usage instructions."""
    print("""
    Code Coverage Generator

    Usage:
        python run_coverage.py --build=<build_directory> [--filter=<folder>] [--output=<format>] [--exclude-patterns=<patterns>] [--verbose]

    Arguments:
        --build=PATH        Build directory (required). Can be absolute or relative to:
                            1. Current working directory
                            2. Script directory
                            3. Project root (auto-detected from .git, etc.)

        --filter=FOLDER     Filter folder within source (default: Library).
                            All subfolders are treated as modules.

        --output=FORMAT     Output format (default: html-and-json):
                            - json: Generate JSON coverage data only
                            - html: Generate HTML report directly from coverage data
                            - html-and-json: Generate both HTML and JSON reports
                            (Applies to all compilers: GCC, Clang, MSVC)

        --exclude-patterns=PATTERNS
                            Comma-separated patterns to exclude from coverage analysis.
                            Examples: "Test,Benchmark,third_party" or "*Generated*,*Serialization*"
                            Default patterns (ThirdParty, Testing, /usr/*) are always applied.
                            User patterns are merged with defaults.

        --verbose           Print additional debug information

    Compiler Detection:
        The script automatically detects the compiler from CMakeCache.txt:
        - MSVC: Uses opencppcoverage coverage tool (Windows only)
        - Clang: Uses LLVM coverage tools (llvm-profdata, llvm-cov)
        - GCC: Uses lcov coverage tool

    Requirements for MSVC (opencppcoverage):
        - Windows platform
        - MSVC compiler
        - opencppcoverage installed (https://github.com/OpenCppCoverage/OpenCppCoverage)
        - Added to system PATH

    Requirements for Clang (LLVM coverage):
        - Clang compiler with instrumentation
        - LLVM tools: llvm-profdata, llvm-cov

    Requirements for GCC (lcov coverage):
        - Linux or macOS
        - lcov installed
        - GCC compiler with -fprofile-arcs -ftest-coverage flags

    Examples:
        # Auto-detect compiler, generate both HTML and JSON (default)
        python run_coverage.py --build=build

        # Generate JSON only
        python run_coverage.py --build=build --output=json

        # Generate HTML report directly
        python run_coverage.py --build=build --output=html

        # With custom filter folder and verbose output
        python run_coverage.py --build=build --filter=Src --output=html --verbose
    """)

def main() -> None:
    """Main entry point for command-line usage."""
    parser = argparse.ArgumentParser(
        description="Code Coverage Generator",
        add_help=False
    )

    parser.add_argument("--build", required=True, help="Build directory path")
    parser.add_argument("--compiler",
                        choices=["gcc", "clang", "msvc", "auto"],
                        default=None,
                        help="Compiler to use. Overrides auto-detection. "
                             "Use 'msvc' for Visual Studio .sln builds without CMake.")
    parser.add_argument("--config", default=None,
                        help="Path to coverage.toml config file (auto-detected if omitted)")
    parser.add_argument("--filter", default=None,
                        help="Filter folder name (default: Library)")
    parser.add_argument("--output", "-o",
                        choices=["json", "html", "html-and-json"],
                        default=None,
                        help="Output format: json, html, or html-and-json (default from config)")
    parser.add_argument("--exclude-patterns", default="",
                        help="Comma-separated patterns to exclude from coverage analysis")
    parser.add_argument("--min-coverage", type=float, default=None,
                        help="Minimum required line coverage percent; exits non-zero if not "
                             "met. Requires --output=json or html-and-json (default from config).")
    parser.add_argument("--verbose", action="store_true",
                        help="Enable verbose output")
    parser.add_argument("-h", "--help", action="store_true",
                        help="Show help message")

    args = parser.parse_args()

    if args.help:
        print_help()
        return

    try:
        # Load config first so all subsequent calls pick it up from cache
        cfg = load_config(args.config)

        project_root = get_project_root()
        if args.verbose:
            print(f"Project root detected at: {project_root}")

        build_dir = resolve_build_dir(args.build, project_root)
        if args.verbose:
            print(f"Resolved build directory: {build_dir}")

        filter_folder = args.filter if args.filter is not None else cfg["filter"]
        source_dir = project_root / filter_folder
        if args.verbose:
            print(f"Filter folder: {filter_folder}")
            print(f"Source directory: {source_dir}")

        # Resolve compiler: CLI flag → coverage.toml → auto-detect
        if args.compiler and args.compiler != "auto":
            compiler = args.compiler
            print(f"Compiler (from --compiler flag): {compiler.upper()}")
        elif cfg.get("compiler"):
            compiler = cfg["compiler"]
            print(f"Compiler (from coverage.toml): {compiler.upper()}")
        else:
            compiler = detect_compiler(build_dir)
            print(f"Detected compiler: {compiler.upper()}")

        modules = discover_modules(source_dir, cfg)

        if not modules:
            raise ValueError(f"No modules found in {source_dir}")

        if args.verbose:
            print(f"Modules to analyze: {', '.join(modules)}")

        # Parse and merge exclude patterns
        user_patterns = parse_exclude_patterns_string(args.exclude_patterns)
        merged_patterns = merge_exclude_patterns(user_patterns, include_defaults=True)

        output_format = args.output if args.output is not None else cfg["output_format"]
        min_coverage = args.min_coverage if args.min_coverage is not None else cfg.get("min_coverage")

        if args.verbose and user_patterns:
            print(f"User exclude patterns: {user_patterns}")
            print(f"Merged exclude patterns: {merged_patterns}")

        # Choose coverage tool based on compiler
        coverage_summary: Optional[dict] = None
        if compiler == "msvc":
            print("Using opencppcoverage tool...")
            coverage_summary = msvc_generate_coverage(
                build_dir, modules, source_dir,
                exclude_patterns=merged_patterns,
                verbose=args.verbose,
                output_format=output_format)
        elif compiler == "clang":
            print("Using LLVM coverage tools...")
            coverage_summary = clang_generate_coverage(
                build_dir, modules, source_dir,
                exclude_patterns=merged_patterns,
                verbose=args.verbose,
                output_format=output_format)
        elif compiler == "gcc":
            print("Using lcov coverage tool...")
            coverage_summary = gcc_generate_coverage(
                build_dir, modules, verbose=args.verbose,
                exclude_patterns=merged_patterns,
                output_format=output_format)
        else:
            raise RuntimeError(f"Unsupported compiler: {compiler}")

        _check_min_coverage(coverage_summary, min_coverage)

    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
    except subprocess.CalledProcessError as e:
        print(f"Error: Command failed: {e}", file=sys.stderr)
        sys.exit(1)
    except FileNotFoundError as e:
        print(f"Error: Required tool not found: {e}", file=sys.stderr)
        sys.exit(1)
    except RuntimeError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()
