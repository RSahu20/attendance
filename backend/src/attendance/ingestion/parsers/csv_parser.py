import csv
import io

from attendance.domain.attendance import ExtractionMethod
from attendance.ingestion.parsers.base import DocumentParser
from attendance.ingestion.parsers.tabular import AttendanceHeaderNotFound, table_units
from attendance.ingestion.types import IngestionError, ParsedUnit


class CSVParser(DocumentParser):
    name = "csv"

    def parse(self, content: bytes, filename: str) -> list[ParsedUnit]:
        try:
            text = content.decode("utf-8-sig")
            dialect = csv.Sniffer().sniff(text[:8192], delimiters=",;\t|")
            rows = list(csv.reader(io.StringIO(text), dialect=dialect, strict=True))
            return table_units(
                rows,
                filename=filename,
                location={},
                key_prefix="csv",
                method=ExtractionMethod.CSV,
            )
        except AttendanceHeaderNotFound as exc:
            raise IngestionError(
                "no_attendance_header",
                "The CSV is readable, but no attendance header row was detected",
            ) from exc
        except (UnicodeDecodeError, csv.Error, ValueError) as exc:
            raise IngestionError("malformed_csv", "The CSV file could not be parsed") from exc
