---
name: project-build
description: Configure, build, and test coverage-tool with its own supported tooling. Use for build, test, coverage, or sanitizer requests; consult local capabilities before selecting optional flags.
---

# project-build

Adapted from XSigma's `xsigma-build` skill for coverage-tool.
Read [CLAUDE.md](../../../CLAUDE.md) for repository boundaries and test conventions.

Run from the repository root in the active development environment:

```sh
python -m pip install -e ".[test]"
python -m pytest tests/ -v
```

CI runs pytest on Python 3.9 through 3.12. The package currently has no
CMake/Bazel build or repository lintrunner configuration. Use
`pyproject.toml` and `.github/workflows/ci.yml` as the source of truth;
do not add C++ build scaffolding or an unsolicited formatter configuration.

Scope repeated test runs to affected behavior when the framework supports
it, then run the required broader checks before handoff. Use only options
documented in this repository; optional coverage, sanitizer, backend, and
compiler flags are not interchangeable across projects.

Distinguish missing prerequisites from build or test failures. Report the
command, selected configuration, and result; do not report unrun checks as
passing. Keep generated files in the normal build or temporary directories.
