from io import BytesIO

from pdf2image import convert_from_bytes
from pypdf import PdfReader
from pypdf.errors import PdfReadError

from attendance.domain.attendance import ExtractionMethod
from attendance.ingestion.parsers.base import DocumentParser
from attendance.ingestion.parsers.ocr_parser import OCRParser
from attendance.ingestion.parsers.tabular import rows_from_text, table_units
from attendance.ingestion.types import IngestionError, ParsedUnit


class PDFParser(DocumentParser):
    name = "pdf"

    def __init__(self, ocr_parser: OCRParser) -> None:
        self.ocr_parser = ocr_parser

    def parse(self, content: bytes, filename: str) -> list[ParsedUnit]:
        try:
            reader = PdfReader(BytesIO(content), strict=True)
            if not reader.pages:
                raise ValueError("PDF contains no pages")
            units: list[ParsedUnit] = []
            for page_number, page in enumerate(reader.pages, start=1):
                text = (page.extract_text() or "").strip()
                if text:
                    units.extend(self._text_page_units(text, filename, page_number))
                else:
                    images = convert_from_bytes(
                        content,
                        first_page=page_number,
                        last_page=page_number,
                        dpi=200,
                    )
                    if not images:
                        raise IngestionError(
                            "ocr_failure", "A scanned PDF page could not be rendered"
                        )
                    units.extend(
                        self.ocr_parser.parse_image(
                            images[0], filename, {"page": page_number}, f"page:{page_number}:ocr"
                        )
                    )
            return units
        except IngestionError:
            raise
        except (PdfReadError, ValueError, OSError) as exc:
            raise IngestionError("unreadable_pdf", "The PDF file could not be parsed") from exc

    @staticmethod
    def _text_page_units(text: str, filename: str, page_number: int) -> list[ParsedUnit]:
        try:
            units = table_units(
                rows_from_text(text),
                filename=filename,
                location={"page": page_number},
                key_prefix=f"page:{page_number}",
                method=ExtractionMethod.PDF_TEXT,
            )
            if units:
                return units
        except (ValueError, TypeError):
            pass
        return [
            ParsedUnit(
                source_unit_key=f"page:{page_number}",
                unit_type="page",
                source_locator={"file": filename, "page": page_number},
                raw_text=text,
                extraction_method=ExtractionMethod.PDF_TEXT,
            )
        ]
