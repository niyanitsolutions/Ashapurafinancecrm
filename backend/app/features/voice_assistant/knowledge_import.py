"""Bounded, non-executing extraction. No network fetches or model-weight training."""

import csv
import io
import re
from pathlib import PurePath
from zipfile import ZipFile

from defusedxml.ElementTree import fromstring  # type: ignore[import-untyped]

from app.core.exceptions import ValidationError

MAX_IMPORT_BYTES = 5 * 1024 * 1024
MAX_TEXT = 50000
SUPPORTED = {".txt", ".csv", ".docx", ".xlsx"}
MIME_TYPES = {
    ".txt": {"text/plain"},
    ".csv": {"text/csv", "application/csv", "text/plain", "application/vnd.ms-excel"},
    ".docx": {"application/vnd.openxmlformats-officedocument.wordprocessingml.document"},
    ".xlsx": {"application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"},
}


def decode_text(data: bytes) -> str:
    encoding = "utf-16" if data.startswith((b"\xff\xfe", b"\xfe\xff")) else "utf-8-sig"
    text = data.decode(encoding)
    if any(ord(char) < 32 and char not in "\n\r\t" for char in text):
        raise ValueError("binary content")
    return text


def extract_document(data: bytes, filename: str, content_type: str | None) -> str:
    extension = PurePath(filename).suffix.casefold()
    if extension == ".pdf":
        raise ValidationError(
            "PDF ingestion requires an isolated, resource-limited parser and scanning integration. "
            "Export reviewed text as TXT for this release; PDF is not silently processed."
        )
    if extension not in SUPPORTED:
        raise ValidationError(
            "Supported knowledge files: TXT, CSV, DOCX and XLSX; no macros or XLS."
        )
    if not data or len(data) > MAX_IMPORT_BYTES:
        raise ValidationError("Choose a non-empty knowledge file no larger than 5 MB.")
    if content_type not in {None, "", "application/octet-stream", *MIME_TYPES[extension]}:
        raise ValidationError("The filename and file content type do not match.")
    try:
        if extension == ".txt":
            text = decode_text(data)
        elif extension == ".csv":
            rows = []
            for number, row in enumerate(csv.reader(io.StringIO(decode_text(data)), strict=True)):
                if number >= 500 or len(row) > 32:
                    raise ValueError("row bounds")
                if any(
                    len(cell) > 4000 or cell.lstrip().startswith(("=", "+", "-", "@"))
                    for cell in row
                ):
                    raise ValueError("formula or cell bounds")
                rows.append(" | ".join(row))
            text = "\n".join(rows)
        else:
            with ZipFile(io.BytesIO(data)) as archive:
                entries = archive.infolist()
                names = [item.filename for item in entries]
                if len(names) != len(set(names)) or len(entries) > 300:
                    raise ValueError("archive entries")
                if sum(item.file_size for item in entries) > 10 * 1024 * 1024:
                    raise ValueError("expanded archive bounds")
                for item in entries:
                    name = item.filename.casefold()
                    if (
                        item.flag_bits & 1
                        or item.file_size > MAX_IMPORT_BYTES
                        or name.startswith(("/", "\\"))
                        or ".." in name.split("/")
                        or any(
                            part in name
                            for part in ("vbaproject", "embeddings/", "externallinks/", "activex/")
                        )
                    ):
                        raise ValueError("unsafe archive")
                    if name.endswith(".rels"):
                        root = fromstring(archive.read(item), forbid_dtd=True)
                        if any(
                            node.attrib.get("TargetMode", "").casefold() == "external"
                            for node in root
                        ):
                            raise ValueError("external relationship")
                if extension == ".docx":
                    root = fromstring(archive.read("word/document.xml"), forbid_dtd=True)
                    text = "\n".join(
                        "".join(
                            node.text or "" for node in paragraph.iter() if node.tag.endswith("}t")
                        )
                        for paragraph in root.iter()
                        if paragraph.tag.endswith("}p")
                    )
                else:
                    text = extract_spreadsheet(archive, names)
        text = text.replace("\r\n", "\n").strip()
        if not 20 <= len(text) <= MAX_TEXT:
            raise ValueError("extracted text bounds")
        return text
    except ValidationError:
        raise
    except Exception:  # noqa: BLE001 -- untrusted parser failures must not expose content/XML
        # Never return parser errors: they can include document text, paths or XML.
        raise ValidationError(
            "Unable to extract knowledge. Check encoding/format; remove formulas, macros, "
            "external links and embedded files. Limits: 50,000 characters, 500 rows, 32 columns."
        ) from None


def extract_spreadsheet(archive: ZipFile, names: list[str]) -> str:
    shared = []
    if "xl/sharedStrings.xml" in names:
        root = fromstring(archive.read("xl/sharedStrings.xml"), forbid_dtd=True)
        shared = [
            "".join(part.text or "" for part in node.iter() if part.tag.endswith("}t"))
            for node in root
        ]
        if len(shared) > 16000 or any(len(value) > 4000 for value in shared):
            raise ValueError("shared string bounds")
    sheets = sorted(name for name in names if re.fullmatch(r"xl/worksheets/sheet\d+\.xml", name))
    if not 1 <= len(sheets) <= 3:
        raise ValueError("sheet bounds")
    lines = []
    rows = 0
    for sheet in sheets:
        root = fromstring(archive.read(sheet), forbid_dtd=True)
        for row in root.iter():
            if not row.tag.endswith("}row"):
                continue
            rows += 1
            if rows > 500 or int(row.attrib.get("r", "0")) > 500 or len(row) > 32:
                raise ValueError("row bounds")
            cells = []
            for cell in row:
                coordinate = re.fullmatch(r"([A-Z]{1,3})([1-9]\d*)", cell.attrib.get("r", ""))
                if not coordinate:
                    raise ValueError("invalid coordinate")
                column = 0
                for letter in coordinate[1]:
                    column = column * 26 + ord(letter) - 64
                if column > 32 or int(coordinate[2]) > 500:
                    raise ValueError("coordinate bounds")
                if any(part.tag.endswith("}f") for part in cell):
                    raise ValueError("formula")
                if cell.attrib.get("t") == "inlineStr":
                    value = "".join(
                        part.text or "" for part in cell.iter() if part.tag.endswith("}t")
                    )
                else:
                    value = next((part.text or "" for part in cell if part.tag.endswith("}v")), "")
                    if cell.attrib.get("t") == "s":
                        index = int(value)
                        if not 0 <= index < len(shared):
                            raise ValueError("shared string reference")
                        value = shared[index]
                if len(value) > 4000 or value.lstrip().startswith(("=", "+", "@")):
                    raise ValueError("cell bounds/formula")
                cells.append(value)
            lines.append(" | ".join(cells))
    return "\n".join(lines)
