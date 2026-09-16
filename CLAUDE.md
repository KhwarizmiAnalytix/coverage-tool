# coverage-tool

Python package for C++ coverage report collection and HTML reporting.
First-party Python code lives in `src/coverage_tool/`, tests in `tests/`.
Support Python 3.9+ as declared in `pyproject.toml`. Preserve the
`coverage-tool` and `coverage-tool-html` command-line entry points and
compiler-specific behavior for GCC, Clang, and MSVC.

## Shared agent guidance

Adapted from the public [XSigma rules and skills](https://github.com/KhwarizmiAnalytix/XSigma/tree/89848c54492abef57fd0d0dc53b9da96b7cd1d5d)
at revision `89848c54492abef57fd0d0dc53b9da96b7cd1d5d`. Local API, dependency, language, and build
conventions below specialize that guidance for this standalone repository.

Read the applicable rules before editing. They apply to Claude as well as
Augment; C++ rules apply only when working on C++:

- [C++ coding](.augment/rules/coding.md) and [builders](.augment/rules/builder.md)
- [Python](.augment/rules/python.md)
- [Testing](.augment/rules/testing.md) and [builds](.augment/rules/build%20rule.md)
- [Dependencies](.augment/rules/ThirdParty.md)
- [Portability](.augment/rules/must-have.md) and [documentation](.augment/rules/markdown.md)

Use these task-specific skills as needed:

- [project-build](.claude/skills/project-build/SKILL.md): configure, build, and test
- [new-test](.claude/skills/new-test/SKILL.md): add tests using local conventions
- [clang-tidy](.claude/skills/clang-tidy/SKILL.md): analyze first-party C++ when applicable
- [session-checklist](.claude/skills/session-checklist/SKILL.md): verify completed work

## Build and test

Run from the repository root in the active development environment:

```sh
python -m pip install -e ".[test]"
python -m pytest tests/ -v
```

CI runs pytest on Python 3.9 through 3.12. The package currently has no
CMake/Bazel build or repository lintrunner configuration. Use
`pyproject.toml` and `.github/workflows/ci.yml` as the source of truth;
do not add C++ build scaffolding or an unsolicited formatter configuration.

## Test conventions

Follow existing pytest cases under `tests/` with `test_*.py` names.
Use temporary paths and mock external compiler/coverage tools at subprocess
boundaries when appropriate. Exercise parsing, missing-tool behavior, and
failure diagnostics without assuming those tools are installed.

## Verification and scope

For non-trivial source or build changes, run affected tests, review the diff,
and run configured lint/static-analysis checks relevant to touched files.
Check both build systems where provided. Follow the session checklist and
report checks run, failures, and unavailable tools explicitly. Guidance-only
changes need frontmatter/link/whitespace validation, not compilation.

Keep unrelated user edits and dependency sources intact. Share review
findings in the response or pull request; do not create unsolicited status
documents. Follow this repository's existing license and contribution policy.
