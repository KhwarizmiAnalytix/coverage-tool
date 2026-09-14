# Coverage Tools

Code coverage generation for the project. Supports **GCC** (lcov),
**Clang** (LLVM), and **MSVC** (OpenCppCoverage) with automatic compiler
detection, and produces consistent HTML and JSON reports across all three.

Packaged as `coverage-tool` — installable standalone in *any*
CMake/CTest project, not just this repo. See
[Installing / using in another repo](#installing--using-in-another-repo).

---

## Table of Contents

1. [Quick Start](#quick-start)
2. [Requirements](#requirements)
3. [Installing / using in another repo](#installing--using-in-another-repo)
4. [Usage](#usage)
   - [CLI](#cli)
   - [Python API — `get_coverage()`](#python-api--get_coverage)
   - [Minimum coverage gate](#minimum-coverage-gate)
   - [HTML report standalone CLI](#html-report-standalone-cli)
5. [Visual Studio .sln without CMake](#visual-studio-sln-without-cmake)
6. [Output](#output)
7. [Configuration — `coverage.toml`](#configuration--coveragetoml)
   - [All options](#all-options)
   - [Customising exclude patterns](#customising-exclude-patterns)
   - [MSVC timeouts](#msvc-timeouts)
8. [Architecture](#architecture)
   - [File map](#file-map)
   - [Data flow](#data-flow)
   - [Compiler detection chain](#compiler-detection-chain)
   - [Test discovery](#test-discovery)
9. [Compiler-specific notes](#compiler-specific-notes)
   - [GCC / lcov](#gcc--lcov)
   - [Clang / LLVM](#clang--llvm)
   - [MSVC / OpenCppCoverage](#msvc--opencppcoverage)
10. [HTML report module](#html-report-module)
11. [Running the tests](#running-the-tests)
12. [Troubleshooting](#troubleshooting)

---

## Quick Start

```bash
# Auto-detect compiler, generate both HTML and JSON (default)
coverage-tool --build=<path/to/build>

# JSON only
coverage-tool --build=build --output=json

# HTML only
coverage-tool --build=build --output=html

# Use a custom config file
coverage-tool --build=build --config=my_coverage.toml

# Override the source folder and add extra exclusions
coverage-tool --build=build --filter=Src --exclude-patterns="*Generated*,*Benchmark*"

# Fail the run if line coverage drops below a threshold
coverage-tool --build=build --min-coverage=80
```

Not installed yet? Install the PyPI package (preferred) or run from a clone:

```bash
pip install coverage-tool
# until the first PyPI release:
pip install "git+https://github.com/KhwarizmiAnalytix/coverage-tool.git"
```

```bash
# from a clone, without installing:
PYTHONPATH=src python3 -m coverage_tool.run_coverage --build=build
```

---

## Requirements

| Compiler | Required tools |
|---|---|
| GCC | `lcov`, `genhtml`, `gcov` (install via `apt install lcov` / `brew install lcov`) |
| Clang | `llvm-profdata`, `llvm-cov` (part of your LLVM installation) |
| MSVC | [OpenCppCoverage](https://github.com/OpenCppCoverage/OpenCppCoverage) on Windows |

Optional but recommended for all three: `ctest` on `PATH` (ships with
CMake) — used for accurate test-executable discovery, see
[Test discovery](#test-discovery).

Python 3.11+ is required for built-in TOML support (`tomllib`). On Python
3.10 and older, `pip install`ing the package pulls in `tomli` automatically
(declared in `pyproject.toml`).

---

## Installing / using in another repo

Install from PyPI (or GitHub until the first release is published):

```bash
pip install coverage-tool
# pip install "git+https://github.com/KhwarizmiAnalytix/coverage-tool.git"
```

Copy [`examples/coverage.toml`](examples/coverage.toml) to the **consumer
repository root** and adjust `filter` / `modules` for that tree. The tool
reads `./coverage.toml` (cwd) or the file next to `.git` — it does **not**
read config from site-packages.

This registers two console scripts:
- `coverage-tool` — the main coverage generator (`run_coverage.py:main`)
- `coverage-tool-html` — the standalone JSON→HTML CLI (`html_report/cli.py:main`)

Then, from the consuming project:

```bash
coverage-tool --build=build
```

Compiler detection reads the standard CMake `CMAKE_CXX_COMPILER_ID` cache
variable (present in *any* CMake project) — no project-specific setup
required. Test discovery prefers `ctest --show-only=json-v1` when available,
so it doesn't depend on any particular `{module}CxxTests`-style naming
convention either (see [Test discovery](#test-discovery)). What *is* still
an opinionated default is the `filter = "Library"` module-scan root and the
`exe_pattern`/`test_dir_template` glob fallback used only when CTest
metadata isn't available — override these in your own `coverage.toml` if
your layout differs; nothing in the code itself assumes a particular
project name or directory structure.

A consuming project calls the Python API after `pip install coverage-tool`:

```python
from coverage_tool import get_coverage
```

---

## Usage

### CLI

```
coverage-tool --build=PATH [OPTIONS]
```

| Argument | Default | Description |
|---|---|---|
| `--build=PATH` | *(required)* | Build directory. Accepts absolute or relative paths (resolved against CWD, script dir, or project root). |
| `--compiler=NAME` | auto-detect | Force `gcc`, `clang`, or `msvc`. Use this for `.sln` builds or when auto-detection fails. |
| `--config=PATH` | auto-detected | Path to `coverage.toml`. Falls back to built-in defaults if not found. |
| `--filter=FOLDER` | `Library` (from config) | Source folder containing modules to analyse. All non-hidden subdirectories are treated as modules. |
| `--output=FORMAT` | `html-and-json` (from config) | `json`, `html`, or `html-and-json`. |
| `--exclude-patterns=LIST` | *(none)* | Comma-separated extra patterns to exclude (e.g. `"*Generated*,*Benchmark*"`). Merged with the defaults from config. |
| `--min-coverage=PERCENT` | *(none, from config)* | Minimum required line-coverage percent; exits non-zero if not met. Requires JSON output. |
| `--verbose` | off | Print extra diagnostic output. |
| `-h` / `--help` | — | Show detailed help. |

**Compiler resolution order**: `--compiler` flag → `compiler` in `coverage.toml` → auto-detection.

### Python API — `get_coverage()`

```python
from coverage_tool import get_coverage

exit_code = get_coverage(
    compiler="auto",            # "clang" | "gcc" | "msvc" | "auto"
    build_folder="build",
    source_folder="Library",
    output_folder=None,         # defaults to build_folder/coverage_report
    exclude_patterns=["*Benchmark*"],
    verbose=False,
    output_format="html-and-json",
    project_root="/path/to/project",
    min_coverage=None,          # e.g. 80.0 to gate on 80% line coverage
)
```

### Minimum coverage gate

Set `--min-coverage=PERCENT` (or `min_coverage` in `coverage.toml` /
`get_coverage()`) to fail the run — non-zero exit code, clear error message
— when line coverage falls short:

```bash
coverage-tool --build=build --min-coverage=80
# Error: Line coverage 74.30% is below the required minimum of 80.00%
```

The gate reads the `summary.line_coverage.percent` value from the JSON
summary each backend returns, so it requires `--output=json` or
`html-and-json` (the default) — `--output=html` alone has no JSON to check
against and raises an error if `--min-coverage` is also set.

### HTML report standalone CLI

Convert an existing JSON coverage report to HTML:

```bash
coverage-tool-html --json=coverage_report/coverage_summary.json --output=my_html
# or, unwrapped:
python -m coverage_tool.html_report.cli --json=coverage_report/coverage_summary.json --output=my_html
```

---

## Visual Studio .sln without CMake

When your project uses a Visual Studio Solution (`.sln`) instead of CMake,
there is no `CMakeCache.txt` for the tool to read. The compiler is still
detected automatically through a fallback chain, but you can also override it
explicitly.

### Automatic detection (no extra flags needed)

The tool tries the following in order until one succeeds:

| Step | What is checked | Detected as |
|---|---|---|
| 1 | `CMakeCache.txt` → `CMAKE_CXX_COMPILER_ID` | gcc / clang / msvc |
| 2 | `.sln` or `.vcxproj` in `--build` dir or up to 2 parent dirs | msvc |
| 3 | VS environment variables (`VCINSTALLDIR`, `VSCMD_ARG_TGT_ARCH`, …) | msvc |
| 4 | `cl.exe` present in `PATH` | msvc |

Steps 2–4 are specifically designed for `.sln` projects. If you run the tool
from a **VS Developer Command Prompt** (or after calling `vcvarsall.bat`),
detection via environment variables (step 3) will succeed automatically.

### Explicit override (most reliable)

```bash
# Fastest option — skip detection entirely
coverage-tool --build=x64\Release --compiler=msvc --filter=Library

# Or set it permanently in coverage.toml so you never need the flag
```

```toml
# coverage.toml
[coverage]
compiler = "msvc"
```

### Where to point `--build`

For a typical Visual Studio output layout, `--build` should point to the
directory that contains your compiled binaries and test executables:

```
MyProject/
├── MyProject.sln
├── x64/
│   ├── Release/          ← pass this as --build
│   │   ├── MyTests.exe
│   │   └── *.dll
│   └── Debug/
└── Library/              ← pass this as --filter (or set filter in coverage.toml)
```

```bash
coverage-tool --build=x64\Release --compiler=msvc --filter=Library
```

If your binaries are in a non-standard location, configure the search
directories in `coverage.toml`:

```toml
[coverage.tests]
search_dirs = [".", "x64/Release", "x64/Debug", "bin/Release", "bin/Debug"]
```

### Finding OpenCppCoverage

OpenCppCoverage must be installed on Windows. Download from
[github.com/OpenCppCoverage/OpenCppCoverage](https://github.com/OpenCppCoverage/OpenCppCoverage/releases).

The tool searches for it in this order:

1. `opencppcoverage_path` in `coverage.toml`
2. `OPENCPPCOVERAGE_PATH` environment variable
3. System `PATH`
4. `C:\Program Files\OpenCppCoverage\`
5. `C:\Program Files (x86)\OpenCppCoverage\`

---

## Output

All output is written to `<build_dir>/coverage_report/` by default
(configurable via `coverage_report_dir`).

```
coverage_report/
├── coverage_summary.json   # Cobertura-compatible JSON (format v2.0)
├── html/
│   ├── index.html          # Summary page with per-file and per-directory tables
│   └── <module>/<file>.html  # Line-by-line annotated source pages
│
│   # MSVC only:
├── raw/
│   ├── <TestName>.xml      # Cobertura XML from OpenCppCoverage
│   └── <TestName>.cov      # Binary coverage data
│
│   # GCC intermediates (in build_dir, not coverage_report):
├── coverage.info
└── coverage_filtered.info
```

### `coverage_summary.json` schema

```json
{
  "metadata": {
    "format_version": "2.0",
    "generator": "coverage_tool",
    "schema": "cobertura-compatible"
  },
  "summary": {
    "line_coverage":     { "total": 0, "covered": 0, "uncovered": 0, "percent": 0.0 },
    "function_coverage": { "total": 0, "covered": 0, "uncovered": 0, "percent": 0.0 },
    "region_coverage":   { "total": 0, "covered": 0, "uncovered": 0, "percent": 0.0 }
  },
  "files": [
    {
      "file": "/abs/path/to/source.cpp",
      "line_coverage":     { "total": 120, "covered": 95, "uncovered": 25, "percent": 79.17 },
      "function_coverage": { "total": 10,  "covered": 9,  "uncovered": 1,  "percent": 90.0  }
    }
  ]
}
```

This schema is now produced by a single shared function
(`coverage_formats.build_summary_json`) for all three compilers, so
`function_coverage`/`region_coverage` are always present and consistently
computed rather than varying by backend.

---

## Configuration — `coverage.toml`

Place `coverage.toml` at the **consumer repository root** (or pass
`--config=PATH`). The file is **optional** — all values have built-in
defaults so the tool works out of the box without it. A starter file is
[`examples/coverage.toml`](examples/coverage.toml).

The config is loaded once and cached. Pass `--config=PATH` on the CLI to
use a non-standard location.

### All options

```toml
[coverage]
# Subfolder within the project containing modules to analyse
filter = "Library"

# Default source folder passed to compiler modules
source_folder = "Library"

# Default output format: "json" | "html" | "html-and-json"
output_format = "html-and-json"

# Name of the output directory (relative to build_dir)
coverage_report_dir = "coverage_report"

# Minimum required line-coverage percent. Commented out (disabled) by
# default — see "Minimum coverage gate" above.
# min_coverage = 80.0


[coverage.exclude]
# lcov / OpenCppCoverage glob-style patterns to exclude from coverage
patterns = [
    "*ThirdParty*",
    "*Testing*",
    "/usr/*",
]

# LLVM -ignore-filename-regex patterns (Clang only)
llvm_ignore_regex = [
    ".*Testing[/\\\\].*",
    ".*Serialization[/\\\\].*",
    ".*ThirdParty[/\\\\].*",
]


[coverage.project]
# Filenames/directories whose presence marks the project root
markers = [".git", ".gitignore", "pyproject.toml"]


[coverage.tests]
# Directories (relative to build_dir) searched for test executables
# — fallback only; ctest --show-only=json-v1 is tried first when available.
search_dirs = ["bin", "bin/Debug", "bin/Release", "lib", "tests"]

# Glob patterns identifying test executables
patterns = ["*Test*", "*test*", "*CxxTests*"]

# Test executable name template — {module} is replaced at runtime (Clang/MSVC).
# Also used to match a CTest test name when no CTest LABELS match is found.
exe_pattern = "{module}CxxTests"

# .profraw filename template (Clang only)
profraw_pattern = "{module}CxxTests.profraw"

# Working directory for test execution, relative to build_dir (Clang only,
# fallback path — the CTest-reported WORKING_DIRECTORY is preferred).
# {filter} and {module} are replaced at runtime
test_dir_template = "{filter}/{module}/Testing/Cxx"


[coverage.gcc]
# Error types passed to lcov --ignore-errors (comma-joined at runtime)
lcov_ignore_errors = ["mismatch", "negative", "gcov"]


[coverage.msvc]
# Seconds before the test-verification run times out
verify_timeout = 30

# Seconds before the OpenCppCoverage instrumented run times out
coverage_timeout = 120

# Explicit path to OpenCppCoverage.exe — leave empty to auto-detect
# Auto-detection order: OPENCPPCOVERAGE_PATH env var → system PATH → common install dirs
opencppcoverage_path = ""


[coverage.html]
# Theme values — documented for future use; not yet wired into HtmlGenerator
primary_color    = "#007bff"
covered_color    = "#28a745"
uncovered_color  = "#dc3545"
neutral_color    = "#6c757d"
background_color = "#f5f5f5"
max_width        = "1200px"
font_family      = "Arial, sans-serif"
code_font_family = "'Courier New', monospace"
```

### Customising exclude patterns

Patterns passed via `--exclude-patterns` on the CLI are **merged** with the
defaults in `coverage.toml` (union, no duplicates). To replace the defaults
entirely, set `patterns = []` in `coverage.toml` and rely on the CLI flag.

```bash
# Add extra patterns on top of the configured defaults
coverage-tool --build=build --exclude-patterns="*Generated*,*Serialization*"
```

### MSVC timeouts

If OpenCppCoverage hangs on large test suites, increase the timeouts:

```toml
[coverage.msvc]
verify_timeout   = 60
coverage_timeout = 300
```

---

## Architecture

### File map

```
coverage-tool/
├── pyproject.toml          Package metadata, console-script entry points
├── examples/coverage.toml  Starter config to copy into a consumer repo
├── src/coverage_tool/
│   ├── __init__.py         Public API: get_coverage, HtmlGenerator, JsonHtmlGenerator
│   ├── run_coverage.py     Main CLI entry point & Python API (get_coverage)
│   ├── common.py           Shared utilities, config loader, CTest discovery
│   ├── clang_coverage.py   Clang/LLVM implementation (llvm-profdata, llvm-cov)
│   ├── gcc_coverage.py     GCC implementation (lcov, genhtml, gcov)
│   ├── msvc_coverage.py    MSVC implementation (OpenCppCoverage)
│   ├── coverage_formats/   Shared LCOV/Cobertura parsers (see below)
│   │   ├── model.py        Canonical FileCoverage model + build_summary_json
│   │   ├── lcov.py         LCOV parser — used by both GCC and Clang
│   │   └── cobertura.py    Cobertura XML parser — used by MSVC
│   └── html_report/
│       ├── __init__.py     Exports HtmlGenerator, JsonHtmlGenerator
│       ├── __main__.py     Entry point for `python -m coverage_tool.html_report`
│       ├── cli.py          Standalone CLI (--json → --output)
│       ├── html_generator.py   Direct coverage data → HTML
│       ├── json_html_generator.py  JSON report → HTML
│       ├── directory_aggregator.py  Directory-level metric rollup
│       ├── templates.py    Shared HTML/CSS templates
│       └── custom.css      External stylesheet
└── tests/
    ├── test_coverage_formats.py  Fixture-based parser tests
    ├── test_html_report.py       HTML report module tests
    └── fixtures/                 Sample .lcov / .xml files
```

Every backend parses its own raw format (LCOV for GCC/Clang, Cobertura XML
for MSVC) into the same `coverage_formats.FileCoverage` model before
building the JSON summary or handing data to `HtmlGenerator` — a parsing
correctness fix (see the DA:-recompute note in `lcov.py`) applies to every
backend at once instead of needing to be re-applied per compiler.

### Data flow

```
build_dir/
  └── CMakeCache.txt
        │
        ▼ detect_compiler()
  ┌─────────────┐
  │ run_coverage│ ◄── coverage.toml (load_config)
  └──────┬──────┘
         │
   ┌─────┼──────────┐
   ▼     ▼          ▼
 gcc   clang      msvc
 coverage coverage coverage
   │     │          │
   ▼     ▼          ▼
 lcov.parse_lcov  cobertura.parse_cobertura   ◄── coverage_formats/
   │     │          │        (shared parsing + FileCoverage model)
   └─────┼──────────┘
         │ build_summary_json() / to_line_dicts()
         ▼
  coverage_report/
    ├── coverage_summary.json
    └── html/
          ├── index.html
          └── <file>.html
                    ▲
             HtmlGenerator
             (html_report/)
```

**Config resolution order for each value:**

1. CLI flag (highest priority — overrides everything)
2. `coverage.toml` (auto-detected or `--config` path)
3. Built-in defaults in `common.CONFIG` (lowest priority)

### Test discovery

Clang and MSVC need to actually run each module's test executable. Rather
than only guessing its path from a naming template, `common.py` first asks
CTest for the ground truth:

```bash
ctest --show-only=json-v1
```

This returns each registered test's exact command line, working directory,
and `LABELS`. Module → test matching then goes, in order:

1. **CTest `LABELS`** — a test whose labels include the module name
   (case-insensitive exact match). This is the strongest signal since it
   doesn't depend on any executable-naming convention at all — any project
   whose CMake labels tests by module (e.g.
   `set_tests_properties(MyTest PROPERTIES LABELS "MyModule")`) gets
   accurate discovery for free.
2. **CTest test name == `exe_pattern.format(module=...)`** — matches this
   tool's own `{module}CxxTests` convention when present.
3. **CTest test name contains the module name** — last-resort substring
   match.
4. **Template/glob fallback** — `build_dir/bin/{module}CxxTests` — used only
   when `ctest` isn't on `PATH` or the build wasn't configured with CTest.

Because step 1 doesn't depend on any naming convention, this is the part of
the tool most likely to work unmodified against a different CMake/CTest
project — as long as its tests carry a `LABELS` property naming their
module (`set_tests_properties(MyTest PROPERTIES LABELS "MyModule")`).

---

## Compiler-specific notes

### GCC / lcov

**Prerequisites**: Build with `-fprofile-arcs -ftest-coverage` (or
`--coverage`). Compiler is auto-detected from `CMakeCache.txt`
(`CMAKE_CXX_COMPILER_ID`) — no manual setting needed.

**What happens**:
1. `lcov --capture` collects `.gcda` files from `build_dir`.
2. `lcov --remove` strips excluded patterns.
3. Filtered data is parsed (`coverage_formats.parse_lcov`) into JSON and/or
   rendered to HTML.

Intermediate files (`coverage.info`, `coverage_filtered.info`) are written
directly to `build_dir`. The final report goes to `coverage_report/`.

**Common issue — empty `coverage.info`**: no `.gcda` files were generated.
Verify tests actually ran and that the build used the coverage flags.

### Clang / LLVM

**Prerequisites**: Build with `-fprofile-instr-generate -fcoverage-mapping`.
Compiler is auto-detected from `CMakeCache.txt` (`CMAKE_CXX_COMPILER_ID`) —
no manual setting needed.

**What happens** (per module):
1. `prepare_llvm_coverage()` finds each module's test via CTest (or the
   naming template as fallback — see [Test discovery](#test-discovery)) and
   runs it with `LLVM_PROFILE_FILE=<module>CxxTests.profraw`.
2. `llvm-profdata merge` merges all `.profraw` files into
   `all-merged.profdata`.
3. `llvm-cov export -format=lcov` produces `coverage.lcov`.
4. `coverage_formats.parse_lcov` parses it into JSON and/or HTML.

The naming-template fallback (used only without CTest metadata) is driven
by config:

```toml
[coverage.tests]
exe_pattern      = "{module}CxxTests"
profraw_pattern  = "{module}CxxTests.profraw"
test_dir_template = "{filter}/{module}/Testing/Cxx"
```

### MSVC / OpenCppCoverage

**Prerequisites**: Windows only. MSVC build. OpenCppCoverage installed.

**What happens**:
1. Each test executable (found via `discover_test_executables` glob search)
   is run through `OpenCppCoverage.exe` with `--export_type=html`,
   `--export_type=cobertura`, and `--export_type=binary`.
2. Cobertura XML files (in `raw/`) are parsed once via
   `coverage_formats.parse_cobertura` and shared between JSON summary
   generation and the detailed HTML report (previously two independent
   parses of the same XML).
3. Line-by-line HTML is generated from the parsed data using `HtmlGenerator`.

**Finding OpenCppCoverage** (in order):
1. `opencppcoverage_path` in `coverage.toml`
2. `OPENCPPCOVERAGE_PATH` environment variable
3. System `PATH`
4. `C:\Program Files\OpenCppCoverage\`
5. `C:\Program Files (x86)\OpenCppCoverage\`

---

## HTML report module

The `html_report/` package can be used independently of the coverage runner.

### From Python

```python
from coverage_tool.html_report import HtmlGenerator, JsonHtmlGenerator

# Generate from raw line coverage data
gen = HtmlGenerator(output_dir="my_report", source_root="/project/Library")
gen.generate_report(
    covered_lines={"src/foo.cpp": {1, 2, 5}},
    uncovered_lines={"src/foo.cpp": {3, 4}},
    execution_counts={"src/foo.cpp": {1: 10, 2: 3, 5: 1}},
)

# Generate from a coverage_summary.json file
jgen = JsonHtmlGenerator(output_dir="my_report")
jgen.generate_from_json("coverage_report/coverage_summary.json")
```

### From the CLI

```bash
coverage-tool-html --json=coverage_summary.json --output=html_out --verbose
# or
python -m coverage_tool.html_report.cli --json=coverage_summary.json --output=html_out
```

### Classes

| Class | Module | Purpose |
|---|---|---|
| `HtmlGenerator` | `html_generator.py` | Builds HTML from raw `covered_lines` / `uncovered_lines` dicts |
| `JsonHtmlGenerator` | `json_html_generator.py` | Builds HTML from a `coverage_summary.json` file or dict |
| `DirectoryAggregator` | `directory_aggregator.py` | Rolls up line counts to directory level for the index page |

---

## Running the tests

```bash
pip install -e ".[test]"
python -m pytest tests/ -v
```

Expected: parser tests, HTML report tests, and discovery tests.

---

## Publishing to PyPI

Releases are published from GitHub Actions (`.github/workflows/publish.yml`)
using [Trusted Publishing](https://docs.pypi.org/trusted-publishers/).

1. Create the PyPI project `coverage-tool` (first upload can also be a
   manual `python -m build && twine upload dist/*`).
2. On PyPI → Publishing → add a trusted publisher:
   - Owner: `KhwarizmiAnalytix`
   - Repository: `coverage-tool`
   - Workflow: `publish.yml`
   - Environment: (leave empty, or match a GitHub Environment if you add one)
3. Tag a release (`v1.0.0`) or use **Publish to PyPI** workflow_dispatch.

Until that is configured, consumers install from GitHub:

```bash
pip install "git+https://github.com/KhwarizmiAnalytix/coverage-tool.git"
```

The test suite covers:
- `coverage_formats.parse_lcov` — multi-`DA:` records per line (the
  LF:/LH: undercount fix), full/zero coverage, malformed records, missing file
- `coverage_formats.parse_cobertura` — per-line hits, malformed `<line>`
  entries, missing file
- `coverage_formats.build_summary_json` — aggregation, 0%/100% coverage
- `HtmlGenerator` — report creation, execution counts, HTML content
- `JsonHtmlGenerator` — JSON file and dict inputs, file pages, metrics
- CLI interface — valid JSON, missing JSON, verbose flag
- Edge cases — empty data, 100% coverage, 0% coverage

---

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `CMakeCache.txt not found` | Build directory is wrong or the project was never configured | Check `--build` points to the CMake build directory |
| No compiler-id variable found | CMake cache exists but `CMAKE_CXX_COMPILER_ID` is missing or unrecognised | Reconfigure with the correct CMake toolchain, or pass `--compiler` explicitly |
| `coverage.info is empty` (GCC) | No `.gcda` files — tests didn't run or build is missing `--coverage` flag | Run the tests first; verify the build flags |
| `No profraw files generated` (Clang) | Test executable not found or failed to run | Check CTest registered the test (`ctest --show-only=json-v1`), or that `exe_pattern` in `coverage.toml` matches the actual binary name |
| `OpenCppCoverage not found` (MSVC) | Tool not installed or not on PATH | Install from the GitHub releases page; set `OPENCPPCOVERAGE_PATH` or `opencppcoverage_path` in config |
| `No modules found in <source_dir>` | `--filter` folder doesn't exist under the project root | Verify `filter` in `coverage.toml` or pass `--filter` explicitly |
| `--min-coverage was requested but no JSON coverage summary was generated` | `--output=html` was used together with `--min-coverage` | Use `--output=json` or `html-and-json` (the default) when gating on coverage |
| TOML config silently ignored | Python < 3.11 and `tomli` not installed | `pip install coverage-tool` (pulls in `tomli` automatically) |
