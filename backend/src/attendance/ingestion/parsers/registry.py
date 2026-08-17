from pathlib import Path

from attendance.ingestion.parsers.base import DocumentParser
from attendance.ingestion.parsers.csv_parser import CSVParser
from attendance.ingestion.parsers.docx_parser import DOCXParser
from attendance.ingestion.parsers.ocr_parser import OCRParser
from attendance.ingestion.parsers.pdf_parser import PDFParser
from attendance.ingestion.parsers.xlsx_parser import XLSXParser
from attendance.ingestion.types import IngestionError
from attendance.providers.ocr.base import OCRProvider


class ParserRegistry:
    SUPPORTED_EXTENSIONS = {
        ".csv",
        ".xlsx",
        ".docx",
        ".pdf",
        ".png",
        ".jpg",
        ".jpeg",
        ".tif",
        ".tiff",
    }

    def __init__(self, ocr_provider: OCRProvider, confidence_threshold: float) -> None:
        ocr = OCRParser(ocr_provider, confidence_threshold)
        self.parsers: dict[str, DocumentParser] = {
            ".csv": CSVParser(),
            ".xlsx": XLSXParser(),
            ".docx": DOCXParser(),
            ".pdf": PDFParser(ocr),
            ".png": ocr,
            ".jpg": ocr,
            ".jpeg": ocr,
            ".tif": ocr,
            ".tiff": ocr,
        }

    def resolve(self, filename: str) -> DocumentParser:
        suffix = Path(filename).suffix.lower()
        parser = self.parsers.get(suffix)
        if parser is None:
            raise IngestionError("unsupported_file_type", "The uploaded file type is not supported")
        return parser
