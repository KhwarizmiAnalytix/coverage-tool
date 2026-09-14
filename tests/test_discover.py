"""Tests for consumer-repo discovery (cwd-based, pip-install safe)."""

from __future__ import annotations

import unittest
from pathlib import Path

from coverage_tool.common import (
    CONFIG,
    discover_modules,
    get_project_root,
    load_config,
)


class TestGetProjectRoot(unittest.TestCase):
    def test_finds_git_from_cwd_not_package_file(self):
        # This test file lives in the coverage-tool repo, which has .git.
        root = get_project_root(Path(__file__).resolve().parent)
        self.assertTrue((root / ".git").exists(), root)

    def test_start_argument_is_honoured(self):
        start = Path(__file__).resolve().parent
        self.assertEqual(get_project_root(start), get_project_root(start / "fixtures"))


class TestDiscoverModules(unittest.TestCase):
    def test_skips_tooling_directories(self):
        # Simulate a flat C++ repo layout.
        class _FakeDir:
            def __init__(self, name, is_dir=True):
                self.name = name
                self._is_dir = is_dir

            def is_dir(self):
                return self._is_dir

        # Use a real temp tree instead of fakes — pathlib.iterdir needs a path.
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for name in ("logger", "util", "common", "Testing", "ThirdParty",
                         "Cmake", "build", "bazel-bin", ".github"):
                (root / name).mkdir()
            (root / "README.md").write_text("x")
            modules = discover_modules(root, config={**CONFIG, "modules": []})
            self.assertEqual(modules, ["common", "logger", "util"])
            self.assertNotIn("Testing", modules)
            self.assertNotIn("ThirdParty", modules)
            self.assertNotIn("build", modules)
            self.assertNotIn("bazel-bin", modules)

    def test_explicit_modules_list_wins(self):
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "logger").mkdir()
            (root / "util").mkdir()
            modules = discover_modules(
                root, config={**CONFIG, "modules": ["logger"]}
            )
            self.assertEqual(modules, ["logger"])


class TestLoadConfigDoesNotReadSitePackages(unittest.TestCase):
    def test_missing_host_toml_uses_defaults(self):
        import os
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            old = os.getcwd()
            try:
                os.chdir(tmp)
                # Reset cache
                import coverage_tool.common as common

                common._config_cache = None
                cfg = load_config()
                self.assertEqual(cfg["filter"], CONFIG["filter"])
            finally:
                os.chdir(old)
                import coverage_tool.common as common

                common._config_cache = None


if __name__ == "__main__":
    unittest.main()
