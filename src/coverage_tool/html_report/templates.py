"""Shared HTML templates and CSS styles for coverage reports.

This module provides consolidated HTML templates and CSS styles used across
all HTML generation modules to eliminate duplication and ensure consistency.
"""

# CSS styles used in all HTML reports
COMMON_CSS = """
body { font-family: Arial, sans-serif; margin: 20px; background-color: #f5f5f5; }
.container { max-width: 1200px; margin: 0 auto; background-color: white; padding: 20px; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }
h1 { color: #333; border-bottom: 3px solid #007bff; padding-bottom: 10px; }
h2 { color: #555; margin-top: 30px; }
.summary { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 15px; margin: 20px 0; }
.metric { background-color: #f8f9fa; padding: 15px; border-radius: 5px; border-left: 4px solid #007bff; }
.metric-label { font-size: 12px; color: #666; text-transform: uppercase; }
.metric-value { font-size: 24px; font-weight: bold; color: #333; }
.coverage-bar { width: 100%; height: 20px; background-color: #e9ecef; border-radius: 3px; overflow: hidden; margin-top: 5px; }
.coverage-fill { height: 100%; background-color: #28a745; }
table { width: 100%; border-collapse: collapse; margin-top: 20px; }
th { background-color: #007bff; color: white; padding: 12px; text-align: left; }
td { padding: 10px; border-bottom: 1px solid #ddd; }
tr:hover { background-color: #f5f5f5; }
a { color: #007bff; text-decoration: none; }
a:hover { text-decoration: underline; }
.metadata { font-size: 12px; color: #999; margin-top: 20px; padding-top: 20px; border-top: 1px solid #ddd; }
"""

# CSS styles for file detail pages
FILE_DETAIL_CSS = """
body { font-family: 'Courier New', monospace; margin: 0; background-color: #f5f5f5; }
.container { max-width: 1400px; margin: 0 auto; background-color: white; }
.header { background-color: #007bff; color: white; padding: 20px; }
.header h1 { margin: 0; font-size: 24px; color: white; border: none; padding: 0; }
.header p { margin: 5px 0 0 0; font-size: 14px; }
.stats { display: grid; grid-template-columns: repeat(4, 1fr); gap: 10px; padding: 20px; background-color: #f8f9fa; }
.stat { padding: 10px; background-color: white; border-radius: 5px; border-left: 4px solid #007bff; }
.stat-label { font-size: 12px; color: #666; }
.stat-value { font-size: 18px; font-weight: bold; }
.code { padding: 20px; }
.line { display: flex; border-bottom: 1px solid #eee; }
.line.covered-line { background-color: #f0f8f5; }
.line.uncovered-line { background-color: #fef5f5; }
.line:hover { opacity: 0.9; }
.line-number { width: 50px; text-align: right; padding-right: 10px; color: #999; background-color: #f5f5f5; user-select: none; }
.coverage-status { width: 30px; text-align: center; padding: 0 10px; font-weight: bold; user-select: none; font-size: 16px; }
.covered { background-color: #28a745; color: white; border-radius: 3px; }
.uncovered { background-color: #dc3545; color: white; border-radius: 3px; }
.neutral { background-color: #6c757d; color: white; border-radius: 3px; }
.line-content { flex: 1; padding: 0 10px; white-space: pre-wrap; word-wrap: break-word; }
.back-link { padding: 20px; }
.back-link a { color: #007bff; text-decoration: none; }
.back-link a:hover { text-decoration: underline; }
"""


def get_index_html_template(coverage_percent: float, total_covered: int,
                            total_uncovered: int, total_lines: int,
                            files_table_rows: str,
                            dirs_table_rows: str = "") -> str:
    """Generate HTML content for the index/summary page.

    Args:
        coverage_percent: Overall coverage percentage.
        total_covered: Total number of covered lines.
        total_uncovered: Total number of uncovered lines.
        total_lines: Total number of lines.
        files_table_rows: HTML table rows for files.
        dirs_table_rows: Optional HTML table rows for directories.

    Returns:
        Complete HTML content for the index page.
    """
    dirs_section = ""
    if dirs_table_rows:
        dirs_section = f"""
        <h2>Directories</h2>
        <table>
            <tr>
                <th>Directory</th>
                <th>Coverage</th>
                <th>Covered</th>
                <th>Uncovered</th>
                <th>Total</th>
            </tr>
{dirs_table_rows}        </table>
"""

    return f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>Code Coverage Report</title>
    <style>
        {COMMON_CSS}
        h2 {{ margin-top: 30px; }}
    </style>
</head>
<body>
    <div class="container">
        <h1>Code Coverage Report</h1>

        <div class="summary">
            <div class="metric">
                <div class="metric-label">Overall Coverage</div>
                <div class="metric-value">{coverage_percent:.1f}%</div>
                <div class="coverage-bar">
                    <div class="coverage-fill" style="width: {coverage_percent}%;"></div>
                </div>
            </div>
            <div class="metric">
                <div class="metric-label">Lines Covered</div>
                <div class="metric-value">{total_covered}</div>
            </div>
            <div class="metric">
                <div class="metric-label">Lines Uncovered</div>
                <div class="metric-value">{total_uncovered}</div>
            </div>
            <div class="metric">
                <div class="metric-label">Total Lines</div>
                <div class="metric-value">{total_lines}</div>
            </div>
        </div>
{dirs_section}
        <h2>Files</h2>
        <table>
            <tr>
                <th>File</th>
                <th>Coverage</th>
                <th>Covered</th>
                <th>Uncovered</th>
                <th>Total</th>
            </tr>
{files_table_rows}        </table>
    </div>
</body>
</html>
"""


def get_file_html_template(file_path: str, coverage_percent: float,
                          covered_count: int, uncovered_count: int,
                          total_lines: int, lines_html: str,
                          back_link: str = "index.html") -> str:
    """Generate HTML content for a file detail page.

    Args:
        file_path: Path to the source file.
        coverage_percent: Coverage percentage for the file.
        covered_count: Number of covered lines.
        uncovered_count: Number of uncovered lines.
        total_lines: Total number of lines.
        lines_html: HTML content for code lines.
        back_link: Relative path to the index/summary page (default: "index.html").

    Returns:
        Complete HTML content for the file page.
    """
    return f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>Coverage: {file_path}</title>
    <style>
        {FILE_DETAIL_CSS}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>Coverage Report: {file_path}</h1>
            <p>Line-by-line coverage analysis</p>
        </div>

        <div class="stats">
            <div class="stat">
                <div class="stat-label">Coverage</div>
                <div class="stat-value">{coverage_percent:.1f}%</div>
            </div>
            <div class="stat">
                <div class="stat-label">Covered Lines</div>
                <div class="stat-value">{covered_count}</div>
            </div>
            <div class="stat">
                <div class="stat-label">Uncovered Lines</div>
                <div class="stat-value">{uncovered_count}</div>
            </div>
            <div class="stat">
                <div class="stat-label">Total Lines</div>
                <div class="stat-value">{total_lines}</div>
            </div>
        </div>

        <div class="code">
{lines_html}        </div>

        <div class="back-link">
            <a href="{back_link}">← Back to Summary</a>
        </div>
    </div>
</body>
</html>
"""


def get_directory_html_template(dir_path: str, coverage_percent: float,
                               covered_count: int, uncovered_count: int,
                               total_lines: int, breadcrumb_html: str,
                               subdirs_table_rows: str,
                               files_table_rows: str,
                               back_link: str = "index.html") -> str:
    """Generate HTML content for a directory summary page.

    Args:
        dir_path: Path to the directory.
        coverage_percent: Coverage percentage for the directory.
        covered_count: Number of covered lines.
        uncovered_count: Number of uncovered lines.
        total_lines: Total number of lines.
        breadcrumb_html: HTML for breadcrumb navigation.
        subdirs_table_rows: HTML table rows for subdirectories.
        files_table_rows: HTML table rows for files.
        back_link: Relative path to parent directory or index.

    Returns:
        Complete HTML content for the directory page.
    """
    return f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>Coverage: {dir_path}</title>
    <style>
        {COMMON_CSS}
        .breadcrumb {{ padding: 10px 0; margin-bottom: 20px; }}
        .breadcrumb a {{ color: #007bff; text-decoration: none; margin: 0 5px; }}
        .breadcrumb a:hover {{ text-decoration: underline; }}
        .breadcrumb span {{ margin: 0 5px; color: #666; }}
        .section-title {{ margin-top: 30px; margin-bottom: 15px; font-size: 18px; font-weight: bold; color: #333; }}
    </style>
</head>
<body>
    <div class="container">
        <h1>Coverage Report: {dir_path}</h1>

        <div class="breadcrumb">
            {breadcrumb_html}
        </div>

        <div class="summary">
            <div class="metric">
                <div class="metric-label">Coverage</div>
                <div class="metric-value">{coverage_percent:.1f}%</div>
                <div class="coverage-bar">
                    <div class="coverage-fill" style="width: {coverage_percent}%;"></div>
                </div>
            </div>
            <div class="metric">
                <div class="metric-label">Lines Covered</div>
                <div class="metric-value">{covered_count}</div>
            </div>
            <div class="metric">
                <div class="metric-label">Lines Uncovered</div>
                <div class="metric-value">{uncovered_count}</div>
            </div>
            <div class="metric">
                <div class="metric-label">Total Lines</div>
                <div class="metric-value">{total_lines}</div>
            </div>
        </div>

        {f'<h2 class="section-title">Subdirectories</h2><table><tr><th>Directory</th><th>Coverage</th><th>Covered</th><th>Uncovered</th><th>Total</th></tr>{subdirs_table_rows}</table>' if subdirs_table_rows else ''}

        {f'<h2 class="section-title">Files</h2><table><tr><th>File</th><th>Coverage</th><th>Covered</th><th>Uncovered</th><th>Total</th></tr>{files_table_rows}</table>' if files_table_rows else ''}

        <div class="back-link">
            <a href="{back_link}">← Back</a>
        </div>
    </div>
</body>
</html>
"""


def get_line_html(line_num: int, status_class: str, status_text: str,
                  line_content: str, hit_count: int = 0,
                  line_class: str = "") -> str:
    """Generate HTML for a single code line.

    Args:
        line_num: Line number.
        status_class: CSS class for coverage status (covered/uncovered/neutral).
        status_text: Text to display for coverage status.
        line_content: The actual source code line (HTML-escaped).
        hit_count: Optional execution count for the line.
        line_class: Optional CSS class for the line div (e.g., 'covered-line').

    Returns:
        HTML for the line.
    """
    hit_text = f" ({hit_count}x)" if hit_count > 0 else ""
    line_class_attr = f' class="line {line_class}"' if line_class else ' class="line"'
    return f"""            <div{line_class_attr}>
                <div class="line-number">{line_num}</div>
                <div class="coverage-status {status_class}">{status_text}{hit_text}</div>
                <div class="line-content">{line_content}</div>
            </div>
"""

