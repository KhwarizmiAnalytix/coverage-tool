"""Directory-level coverage aggregation for hierarchical reports.

This module provides functionality to aggregate coverage metrics at the
directory level, enabling hierarchical navigation and folder-level summaries.
"""

from pathlib import Path
from typing import Dict, Set, Tuple, List, Optional


class DirectoryAggregator:
    """Aggregates coverage metrics at the directory level.

    This class calculates coverage statistics for directories by analyzing
    the coverage data of all files within each directory.
    """

    def __init__(self, source_root: str = ""):
        """Initialize the directory aggregator.

        Args:
            source_root: Root directory for source files (for relative paths).
        """
        self.source_root = source_root
        self.directory_stats = {}  # Maps directory paths to coverage stats

    def _normalize_path(self, path: str) -> str:
        """Normalize path to use forward slashes.

        Args:
            path: Path string to normalize.

        Returns:
            Normalized path using forward slashes.
        """
        return Path(path).as_posix()

    def _resolve_relative_path(self, file_path: str) -> Path:
        """Resolve relative path from source_root.

        Args:
            file_path: Absolute path to source file.

        Returns:
            Path object relative to source_root.

        Raises:
            ValueError: If file_path is not under source_root.
        """
        if not self.source_root:
            return Path(Path(file_path).name)

        file_norm = self._normalize_path(file_path)
        root_norm = self._normalize_path(self.source_root)

        if not root_norm.endswith('/'):
            root_norm += '/'

        if file_norm.lower().startswith(root_norm.lower()):
            rel = file_norm[len(root_norm):]
            return Path(rel)

        raise ValueError(f"{file_path} not under {self.source_root}")

    def aggregate(self, covered_lines: Dict[str, Set[int]],
                  uncovered_lines: Dict[str, Set[int]]) -> Dict[str, Dict]:
        """Aggregate coverage metrics by directory.

        Args:
            covered_lines: Dictionary mapping file paths to covered line sets.
            uncovered_lines: Dictionary mapping file paths to uncovered line sets.

        Returns:
            Dictionary mapping directory paths to coverage statistics.
        """
        self.directory_stats = {}

        # Process each file and aggregate by directory
        for file_path in set(list(covered_lines.keys()) +
                             list(uncovered_lines.keys())):
            try:
                rel_path = self._resolve_relative_path(file_path)
                # Get all parent directories
                parts = rel_path.parent.parts
                for i in range(len(parts)):
                    dir_path = '/'.join(parts[:i + 1])
                    self._add_file_to_directory(
                        dir_path, file_path, covered_lines, uncovered_lines)
            except ValueError:
                # Skip files that can't be resolved
                pass

        return self.directory_stats

    def _add_file_to_directory(self, dir_path: str, file_path: str,
                               covered_lines: Dict[str, Set[int]],
                               uncovered_lines: Dict[str, Set[int]]) -> None:
        """Add file coverage to directory statistics.

        Args:
            dir_path: Directory path (relative).
            file_path: File path (absolute).
            covered_lines: Dictionary of covered lines.
            uncovered_lines: Dictionary of uncovered lines.
        """
        if dir_path not in self.directory_stats:
            self.directory_stats[dir_path] = {
                'covered': 0,
                'uncovered': 0,
                'total': 0,
                'files': []
            }

        covered = len(covered_lines.get(file_path, set()))
        uncovered = len(uncovered_lines.get(file_path, set()))

        self.directory_stats[dir_path]['covered'] += covered
        self.directory_stats[dir_path]['uncovered'] += uncovered
        self.directory_stats[dir_path]['total'] += covered + uncovered
        self.directory_stats[dir_path]['files'].append(file_path)

    def get_directory_coverage(self, dir_path: str) -> Optional[Dict]:
        """Get coverage statistics for a specific directory.

        Args:
            dir_path: Directory path (relative).

        Returns:
            Dictionary with coverage statistics or None if not found.
        """
        if dir_path not in self.directory_stats:
            return None

        stats = self.directory_stats[dir_path]
        total = stats['total']
        if total > 0:
            coverage_percent = (stats['covered'] / total) * 100
        else:
            coverage_percent = 0.0

        return {
            'covered': stats['covered'],
            'uncovered': stats['uncovered'],
            'total': total,
            'coverage_percent': coverage_percent,
            'file_count': len(stats['files'])
        }

    def get_subdirectories(self, parent_dir: str = "") -> List[str]:
        """Get immediate subdirectories of a parent directory.

        Args:
            parent_dir: Parent directory path (relative). Empty string for root.

        Returns:
            List of subdirectory paths.
        """
        subdirs = set()
        prefix = parent_dir + '/' if parent_dir else ''

        for dir_path in self.directory_stats.keys():
            if dir_path.startswith(prefix):
                # Get the next level directory
                remainder = dir_path[len(prefix):]
                if '/' in remainder:
                    subdir = prefix + remainder.split('/')[0]
                else:
                    subdir = dir_path

                if subdir != parent_dir:
                    subdirs.add(subdir)

        return sorted(list(subdirs))

    def get_files_in_directory(self, dir_path: str) -> List[str]:
        """Get files directly in a directory (not in subdirectories).

        Args:
            dir_path: Directory path (relative).

        Returns:
            List of file paths in the directory.
        """
        if dir_path not in self.directory_stats:
            return []

        files = []
        for file_path in self.directory_stats[dir_path]['files']:
            try:
                rel_path = self._resolve_relative_path(file_path)
                # Normalize parent path to use forward slashes
                parent_path = self._normalize_path(str(rel_path.parent))
                # Only include files directly in this directory
                if parent_path == dir_path or (
                    not dir_path and len(rel_path.parent.parts) == 0):
                    files.append(file_path)
            except ValueError:
                pass

        return files

