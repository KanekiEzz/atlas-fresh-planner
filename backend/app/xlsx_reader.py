from __future__ import annotations

import re
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any


MAIN_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
REL_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
PKG_REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"
NS = {"a": MAIN_NS, "r": REL_NS}


def _column_index(cell_ref: str) -> int:
    match = re.match(r"([A-Z]+)", cell_ref)
    if not match:
        return 0
    number = 0
    for char in match.group(1):
        number = number * 26 + ord(char) - 64
    return number - 1


def _string_value(si: ET.Element) -> str:
    return "".join(node.text or "" for node in si.findall(".//a:t", NS))


def _coerce(value: str) -> Any:
    value = value.strip()
    if value == "":
        return ""
    try:
        number = float(value)
    except ValueError:
        return value
    if number.is_integer():
        return int(number)
    return number


def _cell_value(cell: ET.Element, shared_strings: list[str]) -> Any:
    cell_type = cell.attrib.get("t")
    if cell_type == "inlineStr":
        return _string_value(cell)

    value_node = cell.find("a:v", NS)
    raw = value_node.text if value_node is not None and value_node.text is not None else ""
    if cell_type == "s":
        return shared_strings[int(raw)] if raw else ""
    if cell_type == "str":
        return raw
    return _coerce(raw)


def read_workbook_tables(path: str | Path) -> dict[str, list[list[Any]]]:
    workbook_path = Path(path)
    with zipfile.ZipFile(workbook_path) as archive:
        shared_strings: list[str] = []
        if "xl/sharedStrings.xml" in archive.namelist():
            root = ET.fromstring(archive.read("xl/sharedStrings.xml"))
            shared_strings = [_string_value(si) for si in root.findall("a:si", NS)]

        workbook = ET.fromstring(archive.read("xl/workbook.xml"))
        rels = ET.fromstring(archive.read("xl/_rels/workbook.xml.rels"))
        relmap = {
            rel.attrib["Id"]: rel.attrib["Target"].lstrip("/")
            for rel in rels.findall(f"{{{PKG_REL_NS}}}Relationship")
        }

        tables: dict[str, list[list[Any]]] = {}
        sheets = workbook.find("a:sheets", NS)
        for sheet in sheets if sheets is not None else []:
            sheet_name = sheet.attrib["name"]
            rel_id = sheet.attrib[f"{{{REL_NS}}}id"]
            target = relmap[rel_id]
            target = target if target.startswith("xl/") else f"xl/{target}"
            worksheet = ET.fromstring(archive.read(target))
            rows: list[list[Any]] = []
            for row in worksheet.findall(".//a:sheetData/a:row", NS):
                values: dict[int, Any] = {}
                max_index = -1
                for cell in row.findall("a:c", NS):
                    index = _column_index(cell.attrib.get("r", "A1"))
                    values[index] = _cell_value(cell, shared_strings)
                    max_index = max(max_index, index)
                rows.append([values.get(index, "") for index in range(max_index + 1)])
            tables[sheet_name] = rows
        return tables


def table_from_header(rows: list[list[Any]], header_name: str) -> list[dict[str, Any]]:
    header_index = None
    for index, row in enumerate(rows):
        if row and str(row[0]).strip() == header_name:
            header_index = index
            break
    if header_index is None:
        return []

    headers = [str(value).strip() for value in rows[header_index]]
    records: list[dict[str, Any]] = []
    for row in rows[header_index + 1 :]:
        if not any(value != "" for value in row):
            break
        record = {headers[index]: row[index] if index < len(row) else "" for index in range(len(headers))}
        records.append(record)
    return records
