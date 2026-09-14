"""HTML coverage report generation module.

This package provides comprehensive HTML report generation from coverage data,
supporting both JSON-based and direct coverage data inputs.
"""

from .html_generator import HtmlGenerator
from .json_html_generator import JsonHtmlGenerator

__all__ = ["HtmlGenerator", "JsonHtmlGenerator"]

