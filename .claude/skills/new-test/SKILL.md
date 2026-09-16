---
name: new-test
description: Add or extend a unit test in coverage-tool, preserving its framework, test registration, and error-handling contracts. Use when writing tests for changed behavior.
---

# new-test

Read [CLAUDE.md](../../../CLAUDE.md) and the existing test closest to
the changed behavior before choosing a filename, fixture, or macro.

Follow existing pytest cases under `tests/` with `test_*.py` names.
Use temporary paths and mock external compiler/coverage tools at subprocess
boundaries when appropriate. Exercise parsing, missing-tool behavior, and
failure diagnostics without assuming those tools are installed.

1. Search for existing coverage with `rg`; extend the relevant test file
   instead of creating a duplicate suite.
2. Match the neighboring includes, namespace, fixtures, naming, and license
   conventions. Do not bring in test helpers from a different repository.
3. Cover the meaningful success, boundary, and failure cases for the change.
   Assert public behavior and the repository's documented error contract.
4. Check source registration, discovery patterns, and backend exclusions so
   the new cases actually execute. Keep parallel build definitions in sync
   where both exist.
5. Run the affected tests using [project-build](../project-build/SKILL.md).
   Report the test command and result, including any unavailable backend.
