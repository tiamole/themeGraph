"""Corpus adapters that isolate source-specific loading from graph analysis."""

from __future__ import annotations

import csv
import io
import json
import re
import zipfile
from collections.abc import Iterable, Iterator
from pathlib import Path
from xml.etree import ElementTree

from themegraph.models import DocumentRecord


class IterableCorpusAdapter:
    def __init__(self, records: Iterable[DocumentRecord]) -> None:
        self.records = records

    def documents(self) -> Iterator[DocumentRecord]:
        yield from self.records


class DirectoryTextAdapter:
    def __init__(
        self,
        root: str | Path,
        patterns: tuple[str, ...] = ("*.txt", "*.md", "*.rst", "*.tex", "*.py"),
        max_documents: int | None = None,
    ) -> None:
        self.root = Path(root)
        self.patterns = patterns
        self.max_documents = max_documents

    def documents(self) -> Iterator[DocumentRecord]:
        paths = sorted({path for pattern in self.patterns for path in self.root.rglob(pattern)})
        if self.max_documents is not None:
            paths = paths[: self.max_documents]
        for path in paths:
            try:
                text = path.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                text = path.read_text(encoding="utf-8", errors="replace")
            relative_path = path.relative_to(self.root).as_posix()
            yield DocumentRecord(
                document_id=relative_path,
                text=text,
                metadata={"path": relative_path, "suffix": path.suffix.lower()},
                provenance=str(self.root),
            )


class JsonlCorpusAdapter:
    def __init__(self, path: str | Path, text_field: str = "text") -> None:
        self.path = Path(path)
        self.text_field = text_field

    def documents(self) -> Iterator[DocumentRecord]:
        with self.path.open(encoding="utf-8") as stream:
            for row_number, line in enumerate(stream, 1):
                item = json.loads(line)
                document_id = str(item.get("id", row_number))
                text = str(item.get(self.text_field, ""))
                metadata = {
                    str(key): str(value)
                    for key, value in item.items()
                    if key not in {"id", self.text_field}
                }
                yield DocumentRecord(document_id, text, metadata, str(self.path))


class DelimitedCorpusAdapter:
    def __init__(
        self,
        path: str | Path,
        text_fields: tuple[str, ...],
        id_field: str | None = None,
        delimiter: str = "\t",
    ) -> None:
        self.path = Path(path)
        self.text_fields = text_fields
        self.id_field = id_field
        self.delimiter = delimiter

    def documents(self) -> Iterator[DocumentRecord]:
        with self.path.open(encoding="utf-8-sig", newline="") as stream:
            reader = csv.DictReader(stream, delimiter=self.delimiter)
            for row_number, row in enumerate(reader, 1):
                document_id = str(row.get(self.id_field, row_number)) if self.id_field else str(row_number)
                text = "\n".join(str(row.get(field, "")) for field in self.text_fields)
                metadata = {
                    str(key): str(value)
                    for key, value in row.items()
                    if key not in self.text_fields and value is not None
                }
                yield DocumentRecord(document_id, text, metadata, str(self.path))


class XlsxJobAdsAdapter:
    """Stream job advertisements from an OOXML workbook without optional dependencies."""

    expected_columns = ("Job Title", "Company Name", "Location", "Description", "Skills")

    def __init__(self, path: str | Path, max_documents: int | None = None) -> None:
        self.path = Path(path)
        self.max_documents = max_documents

    @staticmethod
    def _column_index(reference: str) -> int:
        letters = re.match(r"[A-Z]+", reference.upper())
        if letters is None:
            return 0
        index = 0
        for letter in letters.group():
            index = index * 26 + ord(letter) - ord("A") + 1
        return index - 1

    @staticmethod
    def _shared_strings(archive: zipfile.ZipFile) -> list[str]:
        if "xl/sharedStrings.xml" not in archive.namelist():
            return []
        root = ElementTree.parse(archive.open("xl/sharedStrings.xml")).getroot()
        return [
            "".join(node.text or "" for node in item.iter() if node.tag.endswith("}t"))
            for item in root
        ]

    @classmethod
    def _row_values(cls, row: ElementTree.Element, shared: list[str]) -> list[str]:
        values: dict[int, str] = {}
        for cell in row:
            if not cell.tag.endswith("}c"):
                continue
            index = cls._column_index(cell.attrib.get("r", "A1"))
            cell_type = cell.attrib.get("t", "")
            if cell_type == "inlineStr":
                value = "".join(
                    node.text or "" for node in cell.iter() if node.tag.endswith("}t")
                )
            else:
                raw = next(
                    (node.text or "" for node in cell if node.tag.endswith("}v")), ""
                )
                value = shared[int(raw)] if cell_type == "s" and raw else raw
            values[index] = value
        width = max(values, default=-1) + 1
        return [values.get(index, "") for index in range(width)]

    def raw_rows(self) -> Iterator[dict[str, str]]:
        with zipfile.ZipFile(self.path) as archive:
            shared = self._shared_strings(archive)
            with archive.open("xl/worksheets/sheet1.xml") as stream:
                header: list[str] | None = None
                for _, element in ElementTree.iterparse(stream, events=("end",)):
                    if not element.tag.endswith("}row"):
                        continue
                    values = self._row_values(element, shared)
                    element.clear()
                    if header is None:
                        header = values
                        continue
                    padded = values + [""] * max(0, len(header) - len(values))
                    yield dict(zip(header, padded, strict=False))

    def documents(self) -> Iterator[DocumentRecord]:
        for row_number, row in enumerate(self.raw_rows(), 1):
            if self.max_documents is not None and row_number > self.max_documents:
                break
            description = row.get("Description", "").strip()
            skills = row.get("Skills", "").strip()
            text_parts = [description]
            if skills and skills != description:
                text_parts.append(skills)
            metadata = {
                "job_title": row.get("Job Title", "").strip(),
                "company_name": row.get("Company Name", "").strip(),
                "location": row.get("Location", "").strip(),
            }
            yield DocumentRecord(
                document_id=f"job-ad-{row_number}",
                text="\n".join(part for part in text_parts if part),
                metadata=metadata,
                provenance=str(self.path),
            )


class ONetZipAdapter:
    """Join occupation descriptions and tasks from an O*NET text database archive."""

    occupation_entry = "db_30_3_text/Occupation Data.txt"
    task_entry = "db_30_3_text/Task Statements.txt"

    def __init__(self, path: str | Path, max_documents: int | None = None) -> None:
        self.path = Path(path)
        self.max_documents = max_documents

    @staticmethod
    def _reader(archive: zipfile.ZipFile, entry: str) -> csv.DictReader:
        binary_stream = archive.open(entry)
        text_stream = io.TextIOWrapper(binary_stream, encoding="utf-8-sig", newline="")
        return csv.DictReader(text_stream, delimiter="\t")

    def documents(self) -> Iterator[DocumentRecord]:
        with zipfile.ZipFile(self.path) as archive:
            tasks: dict[str, list[str]] = {}
            for row in self._reader(archive, self.task_entry):
                code = row.get("O*NET-SOC Code", "")
                task = row.get("Task", "").strip()
                if task:
                    tasks.setdefault(code, []).append(task)

            for index, row in enumerate(self._reader(archive, self.occupation_entry), 1):
                if self.max_documents is not None and index > self.max_documents:
                    break
                code = row.get("O*NET-SOC Code", "").strip()
                title = row.get("Title", "").strip()
                description = row.get("Description", "").strip()
                text = "\n".join([description, *tasks.get(code, [])])
                yield DocumentRecord(
                    document_id=code,
                    text=text,
                    metadata={"occupation_title": title, "onet_soc_code": code},
                    provenance=(
                        "O*NET 30.3 Database, USDOL/ETA, CC BY 4.0, "
                        "https://www.onetcenter.org/database.html"
                    ),
                )
