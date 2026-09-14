"""Command-line interface for HTML coverage report generation.

This module provides a convenient command-line tool to convert JSON coverage
reports into HTML reports for viewing in a web browser or CI/CD systems.

Usage:
    python -m html_report.cli --json=<json_file> --output=<output_dir>
    python -m html_report.cli --json=coverage_report.json --output=html_report
"""

import argparse
import sys
from pathlib import Path

from .json_html_generator import JsonHtmlGenerator


def main(argv=None):
    """Main entry point for the HTML generator CLI.

    Args:
        argv: Optional list of command-line arguments for testing.
              If None, uses sys.argv.

    Returns:
        Exit code (0 for success, 1 for failure).
    """
    parser = argparse.ArgumentParser(
        description="Generate HTML coverage reports from JSON coverage data"
    )

    parser.add_argument(
        "--json",
        required=True,
        help="Path to the JSON coverage report file"
    )

    parser.add_argument(
        "--output",
        default="html_report",
        help="Output directory for HTML reports (default: html_report)"
    )

    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Print verbose output"
    )

    args = parser.parse_args(argv)

    # Validate input file
    json_file = Path(args.json)
    if not json_file.exists():
        print(f"Error: JSON file not found: {json_file}", file=sys.stderr)
        return 1

    if not json_file.is_file():
        print(f"Error: JSON path is not a file: {json_file}", file=sys.stderr)
        return 1

    # Create output directory
    output_dir = Path(args.output)
    try:
        output_dir.mkdir(parents=True, exist_ok=True)
    except Exception as e:
        print(f"Error: Failed to create output directory: {e}", file=sys.stderr)
        return 1

    # Generate HTML report
    try:
        if args.verbose:
            print(f"Reading JSON from: {json_file}")
            print(f"Output directory: {output_dir}")

        generator = JsonHtmlGenerator(output_dir)
        index_file = generator.generate_from_json(json_file)

        if args.verbose:
            print(f"HTML report generated successfully")
            print(f"Index file: {index_file}")

        print(f"✓ HTML report generated at: {index_file}")
        return 0

    except FileNotFoundError as e:
        print(f"Error: File not found: {e}", file=sys.stderr)
        return 1
    except ValueError as e:
        print(f"Error: Invalid JSON format: {e}", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"Error: Failed to generate HTML report: {e}", file=sys.stderr)
        if args.verbose:
            import traceback
            traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())

