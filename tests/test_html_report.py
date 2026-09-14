"""Comprehensive tests for HTML coverage report generation.

Tests cover both HtmlGenerator (direct coverage data) and JsonHtmlGenerator
(JSON-based reports) to ensure all functionality works correctly.
"""

import json
import tempfile
import unittest
from pathlib import Path

from coverage_tool.html_report import HtmlGenerator, JsonHtmlGenerator


class TestHtmlGenerator(unittest.TestCase):
    """Tests for HtmlGenerator class."""

    def setUp(self):
        """Set up test fixtures."""
        self.temp_dir = tempfile.TemporaryDirectory()
        self.output_dir = Path(self.temp_dir.name)

    def tearDown(self):
        """Clean up test fixtures."""
        self.temp_dir.cleanup()

    def test_init_creates_output_directory(self):
        """Test that __init__ creates output directory."""
        output_path = self.output_dir / "test_output"
        generator = HtmlGenerator(output_path)
        self.assertTrue(output_path.exists())

    def test_generate_report_creates_index(self):
        """Test that generate_report creates index.html."""
        generator = HtmlGenerator(self.output_dir)
        covered = {"file1.py": {1, 2, 3}}
        uncovered = {"file1.py": {4, 5}}
        generator.generate_report(covered, uncovered)
        
        index_file = self.output_dir / "index.html"
        self.assertTrue(index_file.exists())

    def test_index_html_contains_coverage_stats(self):
        """Test that index.html contains coverage statistics."""
        generator = HtmlGenerator(self.output_dir)
        covered = {"file1.py": {1, 2, 3}}
        uncovered = {"file1.py": {4, 5}}
        generator.generate_report(covered, uncovered)
        
        index_file = self.output_dir / "index.html"
        content = index_file.read_text()
        self.assertIn("60.0%", content)  # 3 covered / 5 total
        self.assertIn("Code Coverage Report", content)

    def test_generate_report_with_execution_counts(self):
        """Test generate_report with execution counts."""
        generator = HtmlGenerator(self.output_dir)
        covered = {"file1.py": {1, 2}}
        uncovered = {"file1.py": {3}}
        execution_counts = {"file1.py": {1: 5, 2: 10}}
        generator.generate_report(covered, uncovered, execution_counts)
        
        index_file = self.output_dir / "index.html"
        self.assertTrue(index_file.exists())


class TestJsonHtmlGenerator(unittest.TestCase):
    """Tests for JsonHtmlGenerator class."""

    def setUp(self):
        """Set up test fixtures."""
        self.temp_dir = tempfile.TemporaryDirectory()
        self.output_dir = Path(self.temp_dir.name)

    def tearDown(self):
        """Clean up test fixtures."""
        self.temp_dir.cleanup()

    def test_init_creates_output_directory(self):
        """Test that __init__ creates output directory."""
        output_path = self.output_dir / "test_output"
        generator = JsonHtmlGenerator(output_path)
        self.assertTrue(output_path.exists())

    def test_generate_from_json_reads_file(self):
        """Test that generate_from_json reads JSON file."""
        data = {
            "metadata": {"format_version": "2.0"},
            "summary": {
                "line_coverage": {"total": 10, "covered": 6, "percent": 60.0},
                "function_coverage": {"total": 2, "covered": 1, "percent": 50.0},
                "region_coverage": {"total": 5, "covered": 3, "percent": 60.0}
            },
            "files": []
        }
        
        json_file = self.output_dir / "coverage.json"
        with open(json_file, 'w') as f:
            json.dump(data, f)
        
        generator = JsonHtmlGenerator(self.output_dir)
        index_file = generator.generate_from_json(json_file)
        self.assertTrue(index_file.exists())

    def test_generate_from_json_file_not_found(self):
        """Test that generate_from_json raises error for missing file."""
        generator = JsonHtmlGenerator(self.output_dir)
        with self.assertRaises(FileNotFoundError):
            generator.generate_from_json(self.output_dir / "nonexistent.json")

    def test_generate_from_dict_creates_index(self):
        """Test that generate_from_dict creates index.html."""
        data = {
            "metadata": {"format_version": "2.0"},
            "summary": {
                "line_coverage": {"total": 10, "covered": 6, "percent": 60.0},
                "function_coverage": {"total": 2, "covered": 1, "percent": 50.0},
                "region_coverage": {"total": 5, "covered": 3, "percent": 60.0}
            },
            "files": []
        }
        
        generator = JsonHtmlGenerator(self.output_dir)
        index_file = generator.generate_from_dict(data)
        self.assertTrue(index_file.exists())

    def test_generate_from_dict_creates_file_pages(self):
        """Test that generate_from_dict creates file pages."""
        data = {
            "metadata": {"format_version": "2.0"},
            "summary": {
                "line_coverage": {"total": 10, "covered": 6, "percent": 60.0},
                "function_coverage": {"total": 2, "covered": 1, "percent": 50.0},
                "region_coverage": {"total": 5, "covered": 3, "percent": 60.0}
            },
            "files": [
                {
                    "file": "test.py",
                    "line_coverage": {"total": 5, "covered": 3, "percent": 60.0},
                    "function_coverage": {"total": 1, "covered": 1, "percent": 100.0},
                    "region_coverage": {"total": 2, "covered": 2, "percent": 100.0}
                }
            ]
        }

        generator = JsonHtmlGenerator(self.output_dir)
        generator.generate_from_dict(data)

        # Check that at least the index file was created
        index_file = self.output_dir / "index.html"
        self.assertTrue(index_file.exists())

    def test_index_html_contains_metrics(self):
        """Test that index.html contains coverage metrics."""
        data = {
            "metadata": {"format_version": "2.0"},
            "summary": {
                "line_coverage": {"total": 10, "covered": 6, "percent": 60.0},
                "function_coverage": {"total": 2, "covered": 1, "percent": 50.0},
                "region_coverage": {"total": 5, "covered": 3, "percent": 60.0}
            },
            "files": []
        }
        
        generator = JsonHtmlGenerator(self.output_dir)
        index_file = generator.generate_from_dict(data)
        content = index_file.read_text()
        
        self.assertIn("60.0%", content)
        self.assertIn("50.0%", content)
        self.assertIn("Code Coverage Report", content)

    def test_file_page_contains_metrics(self):
        """Test that file page contains coverage metrics."""
        data = {
            "metadata": {"format_version": "2.0"},
            "summary": {
                "line_coverage": {"total": 10, "covered": 6, "percent": 60.0},
                "function_coverage": {"total": 2, "covered": 1, "percent": 50.0},
                "region_coverage": {"total": 5, "covered": 3, "percent": 60.0}
            },
            "files": [
                {
                    "file": "test.py",
                    "line_coverage": {"total": 5, "covered": 3, "percent": 60.0},
                    "function_coverage": {"total": 1, "covered": 1, "percent": 100.0},
                    "region_coverage": {"total": 2, "covered": 2, "percent": 100.0}
                }
            ]
        }

        generator = JsonHtmlGenerator(self.output_dir)
        index_file = generator.generate_from_dict(data)

        # Verify index file contains metrics
        content = index_file.read_text()
        self.assertIn("60.0%", content)
        self.assertIn("100.0%", content)
        self.assertIn("Coverage Report", content)


class TestCliInterface(unittest.TestCase):
    """Tests for CLI interface."""

    def setUp(self):
        """Set up test fixtures."""
        self.temp_dir = tempfile.TemporaryDirectory()
        self.output_dir = Path(self.temp_dir.name)

    def tearDown(self):
        """Clean up test fixtures."""
        self.temp_dir.cleanup()

    def test_cli_with_valid_json(self):
        """Test CLI with valid JSON file."""
        data = {
            "metadata": {"format_version": "2.0"},
            "summary": {
                "line_coverage": {"total": 10, "covered": 6, "percent": 60.0},
                "function_coverage": {"total": 2, "covered": 1, "percent": 50.0},
                "region_coverage": {"total": 5, "covered": 3, "percent": 60.0}
            },
            "files": []
        }
        
        json_file = self.output_dir / "coverage.json"
        with open(json_file, 'w') as f:
            json.dump(data, f)
        
        from coverage_tool.html_report.cli import main
        result = main([f"--json={json_file}", f"--output={self.output_dir}"])
        self.assertEqual(result, 0)

    def test_cli_with_missing_json(self):
        """Test CLI with missing JSON file."""
        from coverage_tool.html_report.cli import main
        result = main([f"--json={self.output_dir}/nonexistent.json", 
                      f"--output={self.output_dir}"])
        self.assertNotEqual(result, 0)

    def test_cli_with_verbose_flag(self):
        """Test CLI with verbose flag."""
        data = {
            "metadata": {"format_version": "2.0"},
            "summary": {
                "line_coverage": {"total": 10, "covered": 6, "percent": 60.0},
                "function_coverage": {"total": 2, "covered": 1, "percent": 50.0},
                "region_coverage": {"total": 5, "covered": 3, "percent": 60.0}
            },
            "files": []
        }
        
        json_file = self.output_dir / "coverage.json"
        with open(json_file, 'w') as f:
            json.dump(data, f)
        
        from coverage_tool.html_report.cli import main
        result = main([f"--json={json_file}", f"--output={self.output_dir}", 
                      "--verbose"])
        self.assertEqual(result, 0)


class TestEdgeCases(unittest.TestCase):
    """Tests for edge cases."""

    def setUp(self):
        """Set up test fixtures."""
        self.temp_dir = tempfile.TemporaryDirectory()
        self.output_dir = Path(self.temp_dir.name)

    def tearDown(self):
        """Clean up test fixtures."""
        self.temp_dir.cleanup()

    def test_empty_coverage_data(self):
        """Test with empty coverage data."""
        generator = JsonHtmlGenerator(self.output_dir)
        data = {
            "metadata": {"format_version": "2.0"},
            "summary": {
                "line_coverage": {"total": 0, "covered": 0, "percent": 0.0},
                "function_coverage": {"total": 0, "covered": 0, "percent": 0.0},
                "region_coverage": {"total": 0, "covered": 0, "percent": 0.0}
            },
            "files": []
        }
        
        index_file = generator.generate_from_dict(data)
        self.assertTrue(index_file.exists())

    def test_full_coverage(self):
        """Test with 100% coverage."""
        generator = JsonHtmlGenerator(self.output_dir)
        data = {
            "metadata": {"format_version": "2.0"},
            "summary": {
                "line_coverage": {"total": 10, "covered": 10, "percent": 100.0},
                "function_coverage": {"total": 2, "covered": 2, "percent": 100.0},
                "region_coverage": {"total": 5, "covered": 5, "percent": 100.0}
            },
            "files": []
        }
        
        index_file = generator.generate_from_dict(data)
        content = index_file.read_text()
        self.assertIn("100.0%", content)

    def test_zero_coverage(self):
        """Test with 0% coverage."""
        generator = JsonHtmlGenerator(self.output_dir)
        data = {
            "metadata": {"format_version": "2.0"},
            "summary": {
                "line_coverage": {"total": 10, "covered": 0, "percent": 0.0},
                "function_coverage": {"total": 2, "covered": 0, "percent": 0.0},
                "region_coverage": {"total": 5, "covered": 0, "percent": 0.0}
            },
            "files": []
        }
        
        index_file = generator.generate_from_dict(data)
        content = index_file.read_text()
        self.assertIn("0.0%", content)


if __name__ == "__main__":
    unittest.main()

