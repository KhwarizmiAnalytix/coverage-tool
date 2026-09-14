"""HTML coverage report generator for direct coverage data.

This module provides functionality to generate professional HTML coverage reports
from direct coverage data (covered/uncovered lines and execution counts).
"""

from pathlib import Path
from typing import Dict, Set, Optional

from .templates import (get_index_html_template, get_file_html_template,
                        get_line_html, get_directory_html_template)
from .directory_aggregator import DirectoryAggregator


class HtmlGenerator:
    """Generates HTML coverage reports from direct coverage data.

    This class creates professional HTML reports with line-by-line coverage
    display, execution counts, and summary statistics.
    """

    def __init__(self, coverage_dir: Path, source_root: str = "",
                 preserve_hierarchy: bool = True):
        """Initialize the HTML report generator.

        Args:
            coverage_dir: Directory where HTML reports will be generated.
            source_root: Root directory for source files (for relative paths).
            preserve_hierarchy: If True, preserve directory hierarchy in output.
                               If False, use flat structure (legacy behavior).
        """
        self.coverage_dir = Path(coverage_dir)
        self.source_root = source_root
        self.preserve_hierarchy = preserve_hierarchy
        self.file_map = {}  # Maps source paths to HTML paths
        self.coverage_dir.mkdir(parents=True, exist_ok=True)

    def _normalize_path(self, path: str) -> str:
        """Normalize path to use forward slashes for cross-platform compatibility.

        Args:
            path: Path string to normalize.

        Returns:
            Normalized path using forward slashes.
        """
        return Path(path).as_posix()

    def _resolve_relative_path(self, file_path: str) -> Path:
        """Resolve relative path from source_root.

        Extracts the relative path of a file from the source_root directory.
        Handles both Windows and Unix paths correctly.

        Args:
            file_path: Absolute path to source file.

        Returns:
            Path object relative to source_root.

        Raises:
            ValueError: If file_path is not under source_root.
        """
        if not self.source_root:
            return Path(file_path).name

        file_norm = self._normalize_path(file_path)
        root_norm = self._normalize_path(self.source_root)

        # Ensure root_norm ends with / for proper prefix matching
        if not root_norm.endswith('/'):
            root_norm += '/'

        # Handle case-insensitive comparison on Windows
        if file_norm.lower().startswith(root_norm.lower()):
            rel = file_norm[len(root_norm):]
            return Path(rel)

        raise ValueError(f"{file_path} not under {self.source_root}")

    def _calculate_relative_link(self, from_file: Path, to_file: Path) -> str:
        """Calculate relative path from one HTML file to another.

        Args:
            from_file: Path to the source HTML file.
            to_file: Path to the target HTML file.

        Returns:
            Relative path string using forward slashes.
        """
        try:
            rel = to_file.relative_to(from_file.parent)
            return rel.as_posix()
        except ValueError:
            # Fallback to absolute path if relative path cannot be computed
            return str(to_file)

    def generate_report(self, covered_lines: Dict[str, Set[int]],
                       uncovered_lines: Dict[str, Set[int]],
                       execution_counts: Optional[Dict] = None) -> None:
        """Generate HTML coverage report.

        Args:
            covered_lines: Dictionary mapping file paths to sets of covered line numbers.
            uncovered_lines: Dictionary mapping file paths to sets of uncovered line numbers.
            execution_counts: Optional dictionary with execution counts per line.
        """
        if execution_counts is None:
            execution_counts = {}

        # Aggregate coverage by directory
        aggregator = DirectoryAggregator(self.source_root)
        aggregator.aggregate(covered_lines, uncovered_lines)

        # Generate index page
        self._generate_index(covered_lines, uncovered_lines, aggregator)

        # Generate directory pages
        if self.preserve_hierarchy:
            self._generate_directory_pages(aggregator, covered_lines,
                                          uncovered_lines)

        # Generate per-file pages
        for file_path in set(list(covered_lines.keys()) +
                             list(uncovered_lines.keys())):
            covered = covered_lines.get(file_path, set())
            uncovered = uncovered_lines.get(file_path, set())
            file_counts = execution_counts.get(file_path, {})

            self._generate_file_report(file_path, covered, uncovered,
                                      file_counts)

    def _generate_index(self, covered_lines: Dict[str, Set[int]],
                       uncovered_lines: Dict[str, Set[int]],
                       aggregator: Optional[DirectoryAggregator] = None
                       ) -> None:
        """Generate the index/summary page.

        Args:
            covered_lines: Dictionary mapping file paths to sets of covered line numbers.
            uncovered_lines: Dictionary mapping file paths to sets of uncovered line numbers.
            aggregator: Optional DirectoryAggregator for directory-level stats.
        """
        total_covered = sum(len(lines) for lines in covered_lines.values())
        total_uncovered = sum(len(lines) for lines in uncovered_lines.values())
        total_lines = total_covered + total_uncovered

        if total_lines > 0:
            coverage_percent = (total_covered / total_lines) * 100
        else:
            coverage_percent = 0.0

        # Build directory list if aggregator is provided
        dirs_table_rows = ""
        if aggregator and self.preserve_hierarchy:
            dirs_table_rows = self._build_directory_table_rows(
                aggregator, "")

        # Build file list with coverage percentages for sorting
        file_list = []
        for file_path in set(list(covered_lines.keys()) +
                             list(uncovered_lines.keys())):
            covered = len(covered_lines.get(file_path, set()))
            uncovered = len(uncovered_lines.get(file_path, set()))
            total = covered + uncovered

            if total > 0:
                file_coverage = (covered / total) * 100
            else:
                file_coverage = 0.0

            file_list.append((file_path, covered, uncovered, total,
                             file_coverage))

        # Sort by coverage percentage in descending order (highest first)
        file_list.sort(key=lambda x: x[4], reverse=True)

        # Build file table rows
        files_table_rows = ""
        for file_path, covered, uncovered, total, file_coverage in file_list:
            # Generate link using hierarchical or flat structure
            if self.preserve_hierarchy and self.source_root:
                try:
                    rel_path = self._resolve_relative_path(file_path)
                    html_file = str(rel_path.with_suffix(
                        rel_path.suffix + '.html')).replace('\\', '/')
                except ValueError:
                    # Fallback to flat structure if path resolution fails
                    html_file = f"{Path(file_path).name}.html"
            else:
                html_file = f"{Path(file_path).name}.html"

            files_table_rows += f"""            <tr>
                <td><a href="{html_file}">{file_path}</a></td>
                <td>{file_coverage:.1f}%</td>
                <td>{covered}</td>
                <td>{uncovered}</td>
                <td>{total}</td>
            </tr>
"""

        html_content = get_index_html_template(
            coverage_percent, total_covered, total_uncovered, total_lines,
            files_table_rows, dirs_table_rows
        )

        index_path = self.coverage_dir / "index.html"
        with open(index_path, 'w', encoding='utf-8') as f:
            f.write(html_content)

    def _generate_file_report(self, file_path: str, covered: Set[int],
                             uncovered: Set[int], execution_counts: Dict) -> None:
        """Generate a per-file coverage report.

        Args:
            file_path: Path to the source file.
            covered: Set of covered line numbers.
            uncovered: Set of uncovered line numbers.
            execution_counts: Dictionary with execution counts per line.
        """
        try:
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                lines = f.readlines()
        except FileNotFoundError:
            print(f"Warning: Source file not found: {file_path}")
            return

        total_lines = len(lines)
        covered_count = len(covered)
        uncovered_count = len(uncovered)

        if total_lines > 0:
            if (covered_count + uncovered_count) > 0:
                coverage_percent = (covered_count /
                                   (covered_count + uncovered_count)) * 100
            else:
                coverage_percent = 0
        else:
            coverage_percent = 0.0

        # Build lines HTML
        lines_html = ""
        for line_num, line_content in enumerate(lines, 1):
            if line_num in covered:
                status_class = "covered"
                status_text = "✓"
                line_class = "covered-line"
            elif line_num in uncovered:
                status_class = "uncovered"
                status_text = "✗"
                line_class = "uncovered-line"
            else:
                status_class = "neutral"
                status_text = "-"
                line_class = ""

            hit_count = execution_counts.get(line_num, 0)
            line_content = line_content.rstrip('\n')
            line_content = (line_content.replace('&', '&amp;')
                           .replace('<', '&lt;').replace('>', '&gt;'))

            lines_html += get_line_html(line_num, status_class, status_text,
                                       line_content, hit_count, line_class)

        # Calculate relative path to index.html from this file
        back_link = "index.html"
        if self.preserve_hierarchy and self.source_root:
            try:
                rel_path = self._resolve_relative_path(file_path)
                # Calculate how many levels deep this file is
                depth = len(rel_path.parent.parts)
                if depth > 0:
                    # Go up the required number of levels
                    back_link = "/".join([".."] * depth) + "/index.html"
            except ValueError:
                pass

        html_content = get_file_html_template(
            file_path, coverage_percent, covered_count, uncovered_count,
            total_lines, lines_html, back_link
        )

        # Generate output file path using hierarchical or flat structure
        if self.preserve_hierarchy and self.source_root:
            try:
                rel_path = self._resolve_relative_path(file_path)
                output_dir = self.coverage_dir / rel_path.parent
                output_dir.mkdir(parents=True, exist_ok=True)
                output_file = output_dir / f"{rel_path.name}.html"
                # Store mapping for potential future use
                self.file_map[file_path] = output_file
            except ValueError:
                # Fallback to flat structure if path resolution fails
                file_name = Path(file_path).name
                output_file = self.coverage_dir / f"{file_name}.html"
        else:
            file_name = Path(file_path).name
            output_file = self.coverage_dir / f"{file_name}.html"

        with open(output_file, 'w', encoding='utf-8') as f:
            f.write(html_content)

    def _generate_directory_pages(self, aggregator: DirectoryAggregator,
                                  covered_lines: Dict[str, Set[int]],
                                  uncovered_lines: Dict[str, Set[int]]
                                  ) -> None:
        """Generate directory summary pages.

        Args:
            aggregator: DirectoryAggregator with directory statistics.
            covered_lines: Dictionary mapping file paths to covered line sets.
            uncovered_lines: Dictionary mapping file paths to uncovered line sets.
        """
        for dir_path in aggregator.directory_stats.keys():
            self._generate_directory_page(dir_path, aggregator, covered_lines,
                                         uncovered_lines)

    def _generate_directory_page(self, dir_path: str,
                                 aggregator: DirectoryAggregator,
                                 covered_lines: Dict[str, Set[int]],
                                 uncovered_lines: Dict[str, Set[int]]
                                 ) -> None:
        """Generate a single directory summary page.

        Args:
            dir_path: Directory path (relative).
            aggregator: DirectoryAggregator with directory statistics.
            covered_lines: Dictionary mapping file paths to covered line sets.
            uncovered_lines: Dictionary mapping file paths to uncovered line sets.
        """
        stats = aggregator.get_directory_coverage(dir_path)
        if not stats:
            return

        # Build breadcrumb navigation
        breadcrumb_html = self._build_breadcrumb(dir_path)

        # Build subdirectories table
        subdirs_table_rows = self._build_directory_table_rows(aggregator,
                                                              dir_path)

        # Build files table
        files_table_rows = self._build_files_table_rows(aggregator, dir_path,
                                                        covered_lines,
                                                        uncovered_lines)

        # Calculate back link
        parts = dir_path.split('/')
        if len(parts) > 1:
            back_link = '/'.join(['..'] * len(parts)) + '/index.html'
        else:
            back_link = '../index.html'

        html_content = get_directory_html_template(
            dir_path, stats['coverage_percent'], stats['covered'],
            stats['uncovered'], stats['total'], breadcrumb_html,
            subdirs_table_rows, files_table_rows, back_link
        )

        # Create directory and write file
        output_dir = self.coverage_dir / dir_path
        output_dir.mkdir(parents=True, exist_ok=True)
        output_file = output_dir / "index.html"

        with open(output_file, 'w', encoding='utf-8') as f:
            f.write(html_content)

    def _build_breadcrumb(self, dir_path: str) -> str:
        """Build breadcrumb navigation HTML.

        Args:
            dir_path: Directory path (relative).

        Returns:
            HTML for breadcrumb navigation.
        """
        parts = dir_path.split('/')
        depth = len(parts)
        # Link to root index.html from current directory
        root_link = '/'.join(['..'] * depth) + '/index.html'
        breadcrumb = f'<a href="{root_link}">Coverage</a>'

        for i, part in enumerate(parts):
            # Calculate how many levels up from current directory
            levels_up = depth - i - 1
            if levels_up > 0:
                link = '/'.join(['..'] * levels_up) + '/index.html'
            else:
                # Current directory
                link = 'index.html'
            breadcrumb += f' <span>/</span> <a href="{link}">{part}</a>'

        return breadcrumb

    def _build_directory_table_rows(self, aggregator: DirectoryAggregator,
                                    parent_dir: str) -> str:
        """Build HTML table rows for subdirectories.

        Args:
            aggregator: DirectoryAggregator with directory statistics.
            parent_dir: Parent directory path (relative).

        Returns:
            HTML table rows for subdirectories.
        """
        subdirs = aggregator.get_subdirectories(parent_dir)
        table_rows = ""

        for subdir in subdirs:
            stats = aggregator.get_directory_coverage(subdir)
            if not stats:
                continue

            # Get directory name (last part of path)
            dir_name = subdir.split('/')[-1]
            link = f"{dir_name}/index.html"

            table_rows += f"""            <tr>
                <td><a href="{link}">{dir_name}/</a></td>
                <td>{stats['coverage_percent']:.1f}%</td>
                <td>{stats['covered']}</td>
                <td>{stats['uncovered']}</td>
                <td>{stats['total']}</td>
            </tr>
"""

        return table_rows

    def _build_files_table_rows(self, aggregator: DirectoryAggregator,
                                dir_path: str,
                                covered_lines: Dict[str, Set[int]],
                                uncovered_lines: Dict[str, Set[int]]
                                ) -> str:
        """Build HTML table rows for files in a directory.

        Args:
            aggregator: DirectoryAggregator with directory statistics.
            dir_path: Directory path (relative).
            covered_lines: Dictionary mapping file paths to covered line sets.
            uncovered_lines: Dictionary mapping file paths to uncovered line sets.

        Returns:
            HTML table rows for files.
        """
        files = aggregator.get_files_in_directory(dir_path)
        # Debug: print number of files found
        # print(f"DEBUG: Found {len(files)} files in {dir_path}")
        table_rows = ""

        for file_path in files:
            covered = len(covered_lines.get(file_path, set()))
            uncovered = len(uncovered_lines.get(file_path, set()))
            total = covered + uncovered

            if total > 0:
                file_coverage = (covered / total) * 100
            else:
                file_coverage = 0.0

            try:
                rel_path = self._resolve_relative_path(file_path)
                file_name = rel_path.name
                html_file = f"{file_name}.html"
            except ValueError:
                file_name = Path(file_path).name
                html_file = f"{file_name}.html"

            table_rows += f"""            <tr>
                <td><a href="{html_file}">{file_name}</a></td>
                <td>{file_coverage:.1f}%</td>
                <td>{covered}</td>
                <td>{uncovered}</td>
                <td>{total}</td>
            </tr>
"""

        return table_rows



