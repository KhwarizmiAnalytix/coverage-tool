#!/usr/bin/env python3
"""Common utilities for code coverage generation.

Provides shared functions used across multiple coverage modules to eliminate
code duplication and improve maintainability.
"""

import json
import os
import shutil
import subprocess
import platform
from pathlib import Path
from typing import Optional, Union
import logging

try:
    import tomllib
except ImportError:
    try:
        import tomli as tomllib  # type: ignore[no-redef]
    except ImportError:
        tomllib = None  # type: ignore[assignment]

logger = logging.getLogger(__name__)

# CMake multi-config generators (Xcode, Visual Studio) place artifacts in
# lib/<Config>/ and bin/<Config>/ rather than lib/ and bin/.
_MULTI_CONFIG_DIR_NAMES = ("Debug", "Release", "RelWithDebInfo", "MinSizeRel")


def multi_config_search_dirs(base: Path) -> list[Path]:
    """Return ``base`` plus any existing CMake multi-config subdirectories."""
    dirs = [base]
    if not base.is_dir():
        return dirs
    for name in _MULTI_CONFIG_DIR_NAMES:
        candidate = base / name
        if candidate.is_dir():
            dirs.append(candidate)
    return dirs


def resolve_multi_config_artifact(path: Path) -> Optional[Path]:
    """Locate a build artifact, checking CMake multi-config subdirectories.

    If ``path`` exists, it is returned. Otherwise ``path.parent/<Config>/path.name``
    is tried for each standard CMake configuration name.
    """
    if path.exists():
        return path
    parent = path.parent
    for name in _MULTI_CONFIG_DIR_NAMES:
        candidate = parent / name / path.name
        if candidate.exists():
            return candidate
    return None


# ============================================================================
# CONFIGURATION - Centralized hardcoded values
# ============================================================================

CONFIG = {
    # Default filter folder (subfolder within source containing modules)
    "filter": "Library",

    # Default source folder
    "source_folder": "Library",

    # Default output format
    "output_format": "html-and-json",

    # Name of the coverage output directory (relative to build_dir)
    "coverage_report_dir": "coverage_report",

    # Minimum required line-coverage percent. None (or absent) disables the
    # gate entirely; a run below this threshold exits non-zero.
    "min_coverage": None,

    # File patterns to exclude from coverage reports
    "exclude_patterns": [
        "*ThirdParty*",
        "*Testing*",
        "/usr/*",
    ],

    # Regex patterns for LLVM to ignore
    "llvm_ignore_regex": [
        ".*Testing[/\\\\].*",
        ".*Serialization[/\\\\].*",
        ".*ThirdParty[/\\\\].*",
    ],

    # Markers to detect project root. Walk starts at cwd (the consumer),
    # never at this file — a pip install lives in site-packages.
    "project_markers": [".git", ".gitignore", "CMakeLists.txt", "coverage.toml"],

    # Optional explicit module list. Empty = scan filter/ and skip junk dirs.
    "modules": [],

    # Search directories for test executables (relative to build_dir)
    # Order matters: searched in this order to find tests
    "test_search_dirs": [
        "bin",
        "bin/Debug",
        "bin/Release",
        "lib",
        "tests",
    ],

    # Test executable name patterns
    "test_patterns": ["*Test*", "*test*", "*CxxTests*"],

    # Name template for a module's test executable ({module} replaced at runtime)
    "test_exe_pattern": "{module}CxxTests",

    # Name template for a module's .profraw file (Clang only)
    "profraw_pattern": "{module}CxxTests.profraw",

    # Relative-path template for the test working directory (Clang only)
    # {filter} and {module} are replaced at runtime
    "test_dir_template": "{filter}/{module}/Testing/Cxx",

    # lcov --ignore-errors values (GCC only)
    "lcov_ignore_errors": ["mismatch", "negative", "gcov"],

    # Seconds to wait for the test-executable verification run (MSVC only)
    "msvc_verify_timeout": 30,

    # Seconds to wait for each OpenCppCoverage run (MSVC only)
    "msvc_coverage_timeout": 120,

    # Explicit path to OpenCppCoverage.exe; empty = auto-detect (MSVC only)
    "opencppcoverage_path": "",

    # Force a specific compiler instead of auto-detecting.
    # Accepted values: "gcc" | "clang" | "msvc" | "" (empty = auto-detect)
    "compiler": "",
}

# ============================================================================
# END CONFIGURATION


# ============================================================================
# CONFIG FILE LOADER
# ============================================================================

_config_cache: Optional[dict] = None


def _flatten_toml_config(toml_data: dict) -> dict:
    """Flatten a nested coverage.toml dict to the flat CONFIG key format."""
    cov = toml_data.get("coverage", {})
    result: dict = {}

    # [coverage]
    for key in ("filter", "source_folder", "output_format", "coverage_report_dir", "compiler",
                "min_coverage", "modules"):
        if key in cov:
            result[key] = cov[key]

    # [coverage.exclude]
    excl = cov.get("exclude", {})
    if "patterns" in excl:
        result["exclude_patterns"] = excl["patterns"]
    if "llvm_ignore_regex" in excl:
        result["llvm_ignore_regex"] = excl["llvm_ignore_regex"]

    # [coverage.project]
    proj = cov.get("project", {})
    if "markers" in proj:
        result["project_markers"] = proj["markers"]

    # [coverage.tests]
    tests = cov.get("tests", {})
    _tests_map = {
        "search_dirs": "test_search_dirs",
        "patterns": "test_patterns",
        "exe_pattern": "test_exe_pattern",
        "profraw_pattern": "profraw_pattern",
        "test_dir_template": "test_dir_template",
    }
    for toml_key, cfg_key in _tests_map.items():
        if toml_key in tests:
            result[cfg_key] = tests[toml_key]

    # [coverage.gcc]
    gcc = cov.get("gcc", {})
    if "lcov_ignore_errors" in gcc:
        result["lcov_ignore_errors"] = gcc["lcov_ignore_errors"]

    # [coverage.msvc]
    msvc = cov.get("msvc", {})
    _msvc_map = {
        "verify_timeout": "msvc_verify_timeout",
        "coverage_timeout": "msvc_coverage_timeout",
        "opencppcoverage_path": "opencppcoverage_path",
    }
    for toml_key, cfg_key in _msvc_map.items():
        if toml_key in msvc:
            result[cfg_key] = msvc[toml_key]

    return result


def load_config(config_path=None) -> dict:
    """Load configuration from coverage.toml merged with built-in defaults.

    Searches for coverage.toml in the script directory then the project root.
    Falls back to built-in CONFIG if the file is not found or cannot be parsed.

    Args:
        config_path: Explicit path to coverage.toml. If None, auto-detected.

    Returns:
        Configuration dictionary.
    """
    global _config_cache

    # Return cached result for repeated auto-detect calls
    if config_path is None and _config_cache is not None:
        return _config_cache

    if tomllib is None:
        logger.debug("No TOML parser available (needs Python 3.11+ or tomli); "
                     "using built-in defaults")
        return CONFIG

    # Locate the config file
    resolved_path: Optional[Path] = None
    if config_path is not None:
        resolved_path = Path(config_path)
    else:
        # Host project first (cwd / discovered root). Never prefer a file next
        # to this module — after `pip install` that is site-packages.
        candidates = [
            Path.cwd() / "coverage.toml",
        ]
        try:
            project_root = get_project_root()
            candidates.append(project_root / "coverage.toml")
            # Legacy in-tree vendor path used before this package was extracted.
            candidates.append(project_root / "Tools" / "coverage" / "coverage.toml")
        except Exception:
            pass
        resolved_path = next((p for p in candidates if p.exists()), None)

    if resolved_path is None or not resolved_path.exists():
        logger.debug("coverage.toml not found; using built-in defaults")
        return CONFIG

    try:
        with open(resolved_path, "rb") as f:
            toml_data = tomllib.load(f)
        overrides = _flatten_toml_config(toml_data)
        merged = {**CONFIG, **overrides}
        logger.debug("Loaded config from %s", resolved_path)
        if config_path is None:
            _config_cache = merged
        return merged
    except Exception as e:
        logger.warning("Failed to load %s: %s; using built-in defaults", resolved_path, e)
        return CONFIG


def get_config() -> dict:
    """Return the active configuration (auto-detected and cached).

    Equivalent to load_config() with no arguments. Use load_config(path) to
    load from an explicit path (e.g. from a --config CLI flag).
    """
    return load_config()


# ============================================================================
# PATTERN MERGING UTILITIES
# ============================================================================


def merge_exclude_patterns(
    user_patterns: Optional[list[str]] = None,
    include_defaults: bool = True
) -> list[str]:
    """Merge user-provided exclusion patterns with default patterns.

    Combines user-provided patterns with default exclusion patterns from CONFIG.
    Removes duplicates while preserving order (defaults first, then user patterns).

    Args:
        user_patterns: List of user-provided patterns to exclude. Can be None.
        include_defaults: Whether to include default patterns from CONFIG.
                         Default: True.

    Returns:
        List of merged exclusion patterns with duplicates removed.

    Example:
        >>> patterns = merge_exclude_patterns(["*Generated*", "*Benchmark*"])
        >>> # Returns: ["*ThirdParty*", "*Testing*", "/usr/*", "*Generated*", "*Benchmark*"]
    """
    merged = []
    seen = set()

    # Add default patterns first
    if include_defaults:
        for pattern in get_config().get("exclude_patterns", []):
            if pattern not in seen:
                merged.append(pattern)
                seen.add(pattern)

    # Add user patterns
    if user_patterns:
        for pattern in user_patterns:
            if pattern not in seen:
                merged.append(pattern)
                seen.add(pattern)

    return merged


def parse_exclude_patterns_string(patterns_str: str) -> list[str]:
    """Parse comma-separated exclusion patterns from a string.

    Splits a comma-separated string into individual patterns, stripping whitespace.
    Empty strings are filtered out.

    Args:
        patterns_str: Comma-separated pattern string (e.g., "Test,Benchmark,third_party").

    Returns:
        List of individual patterns.

    Example:
        >>> patterns = parse_exclude_patterns_string("Test, Benchmark, third_party")
        >>> # Returns: ["Test", "Benchmark", "third_party"]
    """
    if not patterns_str or not patterns_str.strip():
        return []

    patterns = [p.strip() for p in patterns_str.split(",")]
    return [p for p in patterns if p]  # Filter out empty strings


# ============================================================================


def get_platform_config() -> dict:
    """Infer platform-specific extensions and paths.

    Returns:
        Dictionary with platform-specific configuration including
        dll_extension, exe_extension, lib_folder, and os_name.

    Raises:
        RuntimeError: If platform is not supported.
    """
    system = platform.system()

    if system == "Windows":
        return {
            "dll_extension": ".dll",
            "exe_extension": ".exe",
            "lib_folder": "bin",
            "os_name": "Windows"
        }
    elif system == "Darwin":
        return {
            "dll_extension": ".dylib",
            "exe_extension": "",
            "lib_folder": "lib",
            "os_name": "macOS"
        }
    elif system == "Linux":
        return {
            "dll_extension": ".so",
            "exe_extension": "",
            "lib_folder": "lib",
            "os_name": "Linux"
        }
    else:
        raise RuntimeError(f"Unsupported platform: {system}")


def find_opencppcoverage() -> Optional[str]:
    """Find OpenCppCoverage executable in system PATH or environment variable.

    Searches for OpenCppCoverage in the following order:
    1. OPENCPPCOVERAGE_PATH environment variable
    2. System PATH
    3. Common installation directories

    Returns:
        Path to OpenCppCoverage.exe or None if not found.
    """
    # Check environment variable first
    env_path = os.environ.get("OPENCPPCOVERAGE_PATH")
    if env_path:
        env_path_obj = Path(env_path)
        if env_path_obj.exists():
            logger.info(f"Found OpenCppCoverage via OPENCPPCOVERAGE_PATH: {env_path}")
            return str(env_path_obj)
        else:
            logger.warning(f"OPENCPPCOVERAGE_PATH set but not found: {env_path}")

    # Try system PATH
    try:
        subprocess.run(
            ["OpenCppCoverage.exe", "--help"],
            capture_output=True,
            check=True,
            text=True
        )
        logger.info("Found OpenCppCoverage in system PATH")
        return "OpenCppCoverage.exe"
    except (subprocess.CalledProcessError, FileNotFoundError):
        pass

    # Try common installation paths
    common_paths = [
        Path("C:\\Program Files\\OpenCppCoverage\\OpenCppCoverage.exe"),
        Path("C:\\Program Files (x86)\\OpenCppCoverage\\OpenCppCoverage.exe"),
    ]

    for path in common_paths:
        if path.exists():
            logger.info(f"Found OpenCppCoverage at: {path}")
            return str(path)

    logger.warning("OpenCppCoverage not found in PATH or common installation directories")
    return None


def discover_test_executables(build_dir: Path) -> list[Path]:
    """Discover all test executables in the build directory.

    Searches for executables matching common test patterns in configured search
    directories. Uses CONFIG["test_search_dirs"] and CONFIG["test_patterns"].

    Args:
        build_dir: Path to the build directory.

    Returns:
        List of Path objects pointing to test executables.
    """
    build_dir = Path(build_dir)
    test_executables = []
    config = get_platform_config()
    exe_ext = config["exe_extension"]

    # Use configured search directories and patterns
    cfg = get_config()
    search_dirs = [build_dir / d for d in cfg["test_search_dirs"]]
    test_patterns = cfg["test_patterns"]

    for search_dir in search_dirs:
        if not search_dir.exists():
            continue
        for pattern in test_patterns:
            for exe_file in search_dir.glob(f"{pattern}{exe_ext}"):
                if exe_file.is_file():
                    test_executables.append(exe_file)

    # Remove duplicates while preserving order
    seen = set()
    unique_executables = []
    for exe in test_executables:
        exe_str = str(exe.resolve())
        if exe_str not in seen:
            seen.add(exe_str)
            unique_executables.append(exe)

    return unique_executables


def discover_tests_via_ctest(build_dir: Path) -> dict[str, dict]:
    """Query CTest for the authoritative test-name -> command/cwd/labels map.

    This is preferred over guessing an executable's location from a naming
    template, because CTest already knows the exact command line and working
    directory each test was registered with — accurate regardless of how a
    given CMake project lays out its build tree. Returns an empty dict (never
    raises) if ``ctest`` isn't on PATH, the build wasn't configured with
    CTest, or the output can't be parsed — callers fall back to
    template/glob-based discovery in that case.

    Args:
        build_dir: Path to the CMake build directory.

    Returns:
        Mapping of CTest test name to
        ``{"command": [...], "cwd": Optional[str], "labels": [...]}``.
    """
    if shutil.which("ctest") is None:
        return {}

    try:
        result = subprocess.run(
            ["ctest", "--show-only=json-v1"],
            cwd=str(build_dir),
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        if result.returncode != 0 or not result.stdout:
            return {}
        data = json.loads(result.stdout)
    except (subprocess.TimeoutExpired, OSError, json.JSONDecodeError) as e:
        logger.debug("ctest --show-only=json-v1 unavailable: %s", e)
        return {}

    tests: dict[str, dict] = {}
    for test in data.get("tests", []):
        name = test.get("name")
        command = test.get("command")
        if not name or not command:
            continue
        properties = {
            prop.get("name"): prop.get("value")
            for prop in test.get("properties", [])
            if prop.get("name")
        }
        labels = properties.get("LABELS") or []
        if isinstance(labels, str):
            labels = [labels]
        tests[name] = {
            "command": command,
            "cwd": properties.get("WORKING_DIRECTORY"),
            "labels": labels,
        }
    return tests


def find_test_for_module(
    ctest_tests: dict[str, dict], module_name: str, exe_pattern: str
) -> Optional[dict]:
    """Match a module name to one of the tests returned by discover_tests_via_ctest.

    Match order:
    1. A test whose CTest LABELS include the module name exactly
       (case-insensitive) — the strongest signal, since it doesn't depend on
       any executable-naming convention.
    2. A test whose name equals ``exe_pattern`` formatted with the module
       (e.g. "{module}CxxTests") — matches this tool's own convention.
    3. A test whose name contains the module name (case-insensitive
       substring) — last-resort heuristic for projects using neither of the
       above.

    Args:
        ctest_tests: Output of discover_tests_via_ctest().
        module_name: Module directory name (e.g. "Memory").
        exe_pattern: Executable name template, e.g. "{module}CxxTests".

    Returns:
        The matched test's info dict, or None if no test matched.
    """
    module_lower = module_name.lower()

    for info in ctest_tests.values():
        if any(label.lower() == module_lower for label in info["labels"]):
            return info

    expected_name = exe_pattern.format(module=module_name)
    if expected_name in ctest_tests:
        return ctest_tests[expected_name]

    for name, info in ctest_tests.items():
        if module_lower in name.lower():
            return info

    return None


def find_library(build_dir: Path, lib_folder: str, module_name: str,
                 dll_extension: str) -> Optional[str]:
    """Find library file for a module.

    Searches for library files matching the module name pattern.

    Args:
        build_dir: Path to build directory.
        lib_folder: Folder name containing libraries (e.g., "lib", "bin").
        module_name: Name of the module to find.
        dll_extension: File extension for libraries (e.g., ".so", ".dll").

    Returns:
        Path to the library file or None if not found.
    """
    lib_path = build_dir / lib_folder
    if not lib_path.exists():
        return None

    patterns = [
        f"{module_name}{dll_extension}",
        f"lib{module_name}{dll_extension}",
        f"{module_name}*{dll_extension}",
    ]

    for directory in multi_config_search_dirs(lib_path):
        for pattern in patterns:
            matches = list(directory.glob(pattern))
            if matches:
                selected = matches[0]
                print(f"Found library for module '{module_name}': {selected.name} "
                      f"using {selected.name}")
                return str(selected)

    return None


def get_project_root(start: Optional[Union[str, Path]] = None) -> Path:
    """Find the consumer project root by walking up from ``start``.

    Walks from the current working directory (or ``start``), never from
    this file. When installed from PyPI the package lives under
    ``site-packages``; using ``__file__`` would miss the project under test
    and could pick up an unrelated ``.git`` above the venv.

    ``.git`` is checked across the whole upward walk before falling back
    to the other markers.

    Returns:
        Path to project root directory, or ``start`` if nothing matched.
    """
    start_path = Path(start).resolve() if start is not None else Path.cwd().resolve()
    markers = CONFIG["project_markers"]

    if ".git" in markers:
        current = start_path
        for _ in range(10):
            if (current / ".git").exists():
                return current
            if current.parent == current:
                break
            current = current.parent

    current = start_path
    for _ in range(10):
        for marker in markers:
            if marker == ".git":
                continue
            if (current / marker).exists():
                return current
        if current.parent == current:
            break
        current = current.parent

    return start_path


# Directory names that are never C++ library modules when scanning filter/.
_SKIP_MODULE_NAMES = frozenset({
    ".git",
    ".github",
    ".venv",
    "venv",
    "build",
    "cmake",
    "Cmake",
    "ThirdParty",
    "third_party",
    "Testing",
    "bazel",
    "docs",
    "Docs",
    "Scripts",
    "examples",
    "LICENSES",
})


def discover_modules(source_dir: Path, config: Optional[dict] = None) -> list[str]:
    """Return module directory names under ``source_dir``.

    If ``config['modules']`` is a non-empty list, that list is used as-is.
    Otherwise every immediate subdirectory is a module, except hidden dirs,
    ``build*`` / ``bazel-*``, and well-known tooling folders.
    """
    cfg = config if config is not None else get_config()
    explicit = cfg.get("modules") or []
    if explicit:
        return list(explicit)

    modules: list[str] = []
    if not source_dir.is_dir():
        return modules
    for entry in sorted(source_dir.iterdir()):
        if not entry.is_dir():
            continue
        name = entry.name
        if name.startswith(".") or name.startswith("_"):
            continue
        if name.startswith("build") or name.startswith("bazel-"):
            continue
        if name in _SKIP_MODULE_NAMES:
            continue
        modules.append(name)
    return modules


def resolve_build_dir(build_dir_arg: Union[str, Path],
                      project_root: Optional[Path] = None) -> Path:
    """Resolve build directory from argument (absolute or relative).

    Tries multiple resolution strategies:
    1. Absolute path
    2. Relative to current working directory
    3. Relative to script directory
    4. Relative to project root

    Args:
        build_dir_arg: Build directory argument (can be absolute or relative).
        project_root: Optional project root for relative resolution.

    Returns:
        Resolved Path to build directory.

    Raises:
        ValueError: If build directory cannot be resolved.
    """
    build_dir_arg = str(build_dir_arg)

    # Try as absolute path
    abs_path = Path(build_dir_arg).resolve()
    if abs_path.exists():
        return abs_path

    # Try relative to CWD
    cwd_relative = Path.cwd() / build_dir_arg
    if cwd_relative.exists():
        return cwd_relative

    # Try relative to script directory
    script_dir = Path(__file__).resolve().parent
    script_relative = script_dir / build_dir_arg
    if script_relative.exists():
        return script_relative

    # Try relative to project root
    if project_root is None:
        project_root = get_project_root()
    project_relative = project_root / build_dir_arg
    if project_relative.exists():
        return project_relative

    raise ValueError(
        f"Build directory '{build_dir_arg}' not found. Tried:\n"
        f"    - Absolute: {abs_path}\n"
        f"    - CWD relative: {cwd_relative}\n"
        f"    - Script relative: {script_relative}\n"
        f"    - Project relative: {project_relative}"
    )


def validate_build_structure(build_dir: Path, config: dict,
                             library_folder: str) -> dict:
    """Validate that the build directory has expected structure.

    Args:
        build_dir: Path to build directory.
        config: Configuration dictionary.
        library_folder: Name of library folder to check.

    Returns:
        Dictionary with 'valid' boolean and 'issues' list.
    """
    issues = []

    if not (build_dir / "CMakeCache.txt").exists():
        issues.append(f"CMakeCache.txt not found in {build_dir}")

    if not (build_dir / library_folder).exists():
        issues.append(f"Expected source folder not found: "
                      f"{build_dir / library_folder}")

    return {"valid": len(issues) == 0, "issues": issues}


# Maps the standard CMake CMAKE_CXX_COMPILER_ID value (as written into every
# CMakeCache.txt) to the lowercase compiler name this tool uses internally.
_CMAKE_COMPILER_ID_MAP = {
    "gnu": "gcc",
    "clang": "clang",
    "appleclang": "clang",
    "msvc": "msvc",
    "intel": "intel",
    "intelllvm": "intel",
}


def _detect_from_cmake_cache(cmake_cache: Path) -> Optional[str]:
    """Extract compiler from CMakeCache.txt.

    Reads the standard CMAKE_CXX_COMPILER_ID cache variable, which CMake
    writes for every project regardless of generator or platform. Falls back
    to inferring from the CMAKE_CXX_COMPILER path if the ID is missing or
    unrecognised.

    Args:
        cmake_cache: Path to CMakeCache.txt.

    Returns:
        Compiler name, or None if not found / unrecognised.
    """
    try:
        cmake_compiler_id: Optional[str] = None
        cxx_compiler: Optional[str] = None
        with open(cmake_cache, encoding='utf-8', errors='ignore') as f:
            for line in f:
                if '=' not in line:
                    continue
                # CMakeCache.txt entries look like NAME:TYPE=value. CMake also
                # emits a NAME-ADVANCED:INTERNAL=1 metadata line per variable,
                # so match on the exact key (before ':'), not a substring —
                # otherwise the -ADVANCED line is misread as the value.
                key = line.split(':', 1)[0].strip()
                value = line.split('=', 1)[-1].strip().lower()

                if key == 'CMAKE_CXX_COMPILER_ID' and cmake_compiler_id is None:
                    cmake_compiler_id = value
                elif key == 'CMAKE_CXX_COMPILER' and cxx_compiler is None:
                    cxx_compiler = value

        if cmake_compiler_id:
            mapped = _CMAKE_COMPILER_ID_MAP.get(cmake_compiler_id)
            if mapped:
                logger.info("CMAKE_CXX_COMPILER_ID found: %s -> %s", cmake_compiler_id, mapped)
                return mapped
            logger.warning("Unrecognised CMAKE_CXX_COMPILER_ID: %s", cmake_compiler_id)

        # Fall back to inferring from CMAKE_CXX_COMPILER path
        if cxx_compiler:
            logger.info("Inferring compiler from CMAKE_CXX_COMPILER: %s", cxx_compiler)
            if 'clang' in cxx_compiler:
                return 'clang'
            if 'g++' in cxx_compiler or 'gcc' in cxx_compiler:
                return 'gcc'
            if 'cl.exe' in cxx_compiler or 'cl' == os.path.basename(cxx_compiler):
                return 'msvc'
            if 'icpx' in cxx_compiler or 'icpc' in cxx_compiler:
                return 'intel'
    except Exception as e:
        logger.warning("Could not read CMakeCache.txt: %s", e)
    return None


def _detect_from_vs_project(search_dir: Path) -> Optional[str]:
    """Detect MSVC by looking for .sln or .vcxproj files.

    Searches the given directory and up to two levels of parent directories
    so that both in-source and out-of-source layouts are covered.

    Args:
        search_dir: Directory to start searching (usually the build dir).

    Returns:
        "msvc" if a Visual Studio project file is found, otherwise None.
    """
    dirs_to_search = [search_dir]
    # Also check immediate parent and grandparent — typical for out-of-source builds
    parent = search_dir.parent
    if parent != search_dir:
        dirs_to_search.append(parent)
        grandparent = parent.parent
        if grandparent != parent:
            dirs_to_search.append(grandparent)

    for d in dirs_to_search:
        if not d.is_dir():
            continue
        # Shallow glob — avoid walking entire trees
        if any(d.glob("*.sln")) or any(d.glob("*.vcxproj")):
            logger.info("Visual Studio project file found in %s → MSVC", d)
            return "msvc"
    return None


def _detect_from_vs_env() -> Optional[str]:
    """Detect MSVC from Visual Studio environment variables.

    These variables are set by the VS Developer Command Prompt and
    vcvarsall.bat / vsdevcmd.bat.

    Returns:
        "msvc" if a VS environment is active, otherwise None.
    """
    vs_env_vars = (
        "VCINSTALLDIR",       # set by vcvarsall.bat
        "VSCMD_ARG_TGT_ARCH", # set by vsdevcmd.bat
        "VSAPPIDNAME",        # Visual Studio app identity
        "VisualStudioVersion",# set by VS build environment
    )
    for var in vs_env_vars:
        if os.environ.get(var):
            logger.info("VS environment variable %s found → MSVC", var)
            return "msvc"
    return None


def _detect_cl_in_path() -> Optional[str]:
    """Detect MSVC by checking whether cl.exe is available in PATH.

    Returns:
        "msvc" if cl.exe is found, otherwise None.
    """
    import shutil
    if shutil.which("cl.exe") or shutil.which("cl"):
        logger.info("cl.exe found in PATH → MSVC")
        return "msvc"
    return None


def detect_compiler(build_dir: Union[Path, str]) -> str:
    """Detect the compiler used in the build directory.

    Detection order:
    1. ``CMakeCache.txt`` — reads the standard ``CMAKE_CXX_COMPILER_ID``
       (present in any CMake build).
    2. ``.sln`` / ``.vcxproj`` files — indicates a Visual Studio / MSVC build.
    3. Visual Studio environment variables (``VCINSTALLDIR`` etc.).
    4. ``cl.exe`` present in ``PATH``.

    For non-CMake Visual Studio solutions, steps 2–4 provide automatic
    detection. You can also bypass detection entirely with the ``--compiler``
    CLI flag or the ``compiler`` key in ``coverage.toml``.

    Args:
        build_dir: Path to the build (or solution output) directory.

    Returns:
        Compiler name: ``"gcc"``, ``"clang"``, ``"msvc"``, or ``"intel"``.

    Raises:
        RuntimeError: If the compiler cannot be determined.
    """
    build_dir = Path(build_dir)

    # 1. CMakeCache.txt (CMake builds)
    cmake_cache = build_dir / "CMakeCache.txt"
    if cmake_cache.exists():
        result = _detect_from_cmake_cache(cmake_cache)
        if result:
            return result
        # CMakeCache exists but neither compiler-id variable is usable — fall through
        logger.warning(
            "CMakeCache.txt found but no usable compiler-id variable; "
            "trying Visual Studio detection"
        )
    else:
        logger.info("No CMakeCache.txt in %s; trying Visual Studio detection", build_dir)

    # 2. .sln / .vcxproj files
    result = _detect_from_vs_project(build_dir)
    if result:
        return result

    # 3. Visual Studio environment variables
    result = _detect_from_vs_env()
    if result:
        return result

    # 4. cl.exe in PATH
    result = _detect_cl_in_path()
    if result:
        return result

    raise RuntimeError(
        f"Could not detect compiler for build directory: {build_dir}\n"
        "\n"
        "Tried:\n"
        "  1. CMakeCache.txt  (CMAKE_CXX_COMPILER_ID)\n"
        "  2. .sln / .vcxproj files in or near the build directory\n"
        "  3. Visual Studio environment variables (VCINSTALLDIR, etc.)\n"
        "  4. cl.exe in PATH\n"
        "\n"
        "To fix this, pass the compiler explicitly:\n"
        "  python run_coverage.py --build=<path> --compiler=msvc\n"
        "Or set it in coverage.toml:\n"
        "  [coverage]\n"
        '  compiler = "msvc"'
    )
