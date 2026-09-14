"""Shared Cobertura XML parser, used by the MSVC (OpenCppCoverage) backend.

OpenCppCoverage's ``--export_type=cobertura`` output is parsed here once;
previously the MSVC backend parsed the same XML twice — once (totals only)
for the JSON summary and once (per-line) for the HTML report — with two
independently-maintained implementations.
"""

import logging
import xml.etree.ElementTree as ET
from pathlib import Path

from .model import FileCoverage

logger = logging.getLogger(__name__)


def parse_cobertura(xml_file: Path) -> dict[str, FileCoverage]:
    """Parse a Cobertura XML coverage file into the canonical model.

    Handles the ``coverage > package > classes > class > lines > line``
    structure that OpenCppCoverage's Cobertura export uses. Filenames are
    returned exactly as written in the XML (relative or absolute,
    forward-slash separated) — path resolution against the source tree is
    caller-specific (Windows drive-letter handling, source-root filtering)
    and is not this module's concern.

    A missing file returns an empty mapping rather than raising, since
    callers commonly probe several XML files and skip ones that don't
    exist yet.

    Args:
        xml_file: Path to the Cobertura XML file.

    Returns:
        Mapping of source file path (as written in the XML) to its parsed
        FileCoverage.
    """
    xml_file = Path(xml_file)
    files: dict[str, FileCoverage] = {}

    if not xml_file.exists():
        return files

    tree = ET.parse(xml_file)
    root = tree.getroot()

    for package in root.findall(".//package"):
        for class_elem in package.findall("classes/class"):
            filename = class_elem.get("filename", "")
            if not filename or filename in files:
                continue

            coverage = FileCoverage()
            for line_elem in class_elem.findall("lines/line"):
                try:
                    line_num = int(line_elem.get("number", "0"))
                    hits = int(line_elem.get("hits", "0"))
                except (TypeError, ValueError):
                    logger.debug("Skipping malformed <line> in %s", xml_file)
                    continue
                if line_num == 0:
                    continue
                coverage.execution_counts[line_num] = hits

            files[filename] = coverage

    return files
