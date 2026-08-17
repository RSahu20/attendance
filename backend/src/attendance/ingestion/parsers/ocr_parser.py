from io import BytesIO

from PIL import Image, UnidentifiedImageError

from attendance.domain.attendance import ExtractionMethod, ReviewStatus
from attendance.ingestion.parsers.base import DocumentParser
from attendance.ingestion.parsers.tabular import rows_from_text, table_units
from attendance.ingestion.types import IngestionError, ParsedUnit
from attendance.providers.ocr.base import OCRProvider


class OCRParser(DocumentParser):
    name = "tesseract_ocr"

    def __init__(self, provider: OCRProvider, confidence_threshold: float) -> None:
        self.provider = provider
        self.confidence_threshold = confidence_threshold

    def parse(self, content: bytes, filename: str) -> list[ParsedUnit]:
        try:
            with Image.open(BytesIO(content)) as image:
                return self.parse_image(image.convert("RGB"), filename, {"image": 1}, "image:1")
        except UnidentifiedImageError as exc:
            raise IngestionError("unreadable_image", "The image file could not be parsed") from exc

    def parse_image(
        self, image: Image.Image, filename: str, locator: dict[str, int], key_prefix: str
    ) -> list[ParsedUnit]:
        result = self.provider.extract(image)
        review = (
            ReviewStatus.ACCEPTED
            if result.confidence >= self.confidence_threshold
            else ReviewStatus.REVIEW_REQUIRED
        )
        try:
            units = table_units(
                rows_from_text(result.text),
                filename=filename,
                location=locator,
                key_prefix=key_prefix,
                method=ExtractionMethod.OCR,
                confidence=result.confidence,
                review_status=review,
            )
            if units:
                return units
        except (ValueError, TypeError):
            pass
        return [
            ParsedUnit(
                source_unit_key=key_prefix,
                unit_type="ocr_text",
                source_locator={"file": filename, **locator},
                raw_text=result.text,
                extraction_method=ExtractionMethod.OCR,
                extraction_confidence=result.confidence,
                review_status=review,
            )
        ]
