from collections import defaultdict

import pytesseract
from PIL.Image import Image
from pytesseract import Output

from attendance.ingestion.types import IngestionError
from attendance.providers.ocr.base import OCRProvider, OCRResult


class TesseractProvider(OCRProvider):
    def extract(self, image: Image) -> OCRResult:
        try:
            data = pytesseract.image_to_data(image, output_type=Output.DICT, config="--psm 6")
        except pytesseract.TesseractError as exc:
            raise IngestionError("ocr_failure", "OCR could not process the image") from exc

        lines: dict[tuple[int, int, int], list[str]] = defaultdict(list)
        confidences: list[float] = []
        for index, value in enumerate(data["text"]):
            word = value.strip()
            try:
                confidence = float(data["conf"][index])
            except (TypeError, ValueError):
                confidence = -1
            if not word or confidence < 0:
                continue
            key = (data["block_num"][index], data["par_num"][index], data["line_num"][index])
            lines[key].append(word)
            confidences.append(confidence)
        text = "\n".join(" ".join(words) for words in lines.values())
        if not text:
            raise IngestionError("ocr_failure", "OCR found no readable text")
        mean_confidence = sum(confidences) / len(confidences) / 100 if confidences else 0
        return OCRResult(text=text, confidence=max(0.0, min(1.0, mean_confidence)))
