import json
from abc import ABC, abstractmethod
from io import BytesIO
from typing import Any
from xml.sax.saxutils import escape

from openpyxl import Workbook
from openpyxl.styles import Font
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import LongTable, Paragraph, SimpleDocTemplate, Spacer, TableStyle

from attendance.domain.exports import ExportArtifact, ExportFormat, ExportMetadata, ExportRecord

HEADERS = [
    "attendance_date",
    "employee_id",
    "employee_name",
    "department",
    "status",
    "check_in",
    "check_out",
    "total_hours",
    "attendance_percentage",
    "source_file",
    "source_page",
    "source_sheet",
    "source_row",
    "source_record_id",
    "extraction_confidence",
    "review_status",
]


def logical_row(record: ExportRecord) -> dict[str, Any]:
    return record.model_dump(mode="json")


def sanitize_spreadsheet_value(value: Any) -> Any:
    if isinstance(value, str) and value.startswith(("=", "+", "-", "@")):
        return f"'{value}"
    return value


class ExportRenderer(ABC):
    @abstractmethod
    def render(self, records: list[ExportRecord], metadata: ExportMetadata) -> ExportArtifact:
        pass


class JSONRenderer(ExportRenderer):
    def render(self, records: list[ExportRecord], metadata: ExportMetadata) -> ExportArtifact:
        content = json.dumps(
            {
                "metadata": metadata.model_dump(mode="json"),
                "records": [logical_row(record) for record in records],
            },
            ensure_ascii=False,
            indent=2,
        ).encode("utf-8")
        return ExportArtifact(
            content=content,
            media_type="application/json",
            extension="json",
        )


class XLSXRenderer(ExportRenderer):
    def render(self, records: list[ExportRecord], metadata: ExportMetadata) -> ExportArtifact:
        workbook = Workbook()
        sheet = workbook.active
        sheet.title = "Attendance"
        sheet.append(HEADERS)
        for cell in sheet[1]:
            cell.font = Font(bold=True)
        for record in records:
            values = logical_row(record)
            sheet.append([sanitize_spreadsheet_value(values[header]) for header in HEADERS])
        sheet.freeze_panes = "A2"
        sheet.auto_filter.ref = sheet.dimensions
        for column in sheet.columns:
            width = min(40, max(12, max(len(str(cell.value or "")) for cell in column) + 2))
            sheet.column_dimensions[column[0].column_letter].width = width

        metadata_sheet = workbook.create_sheet("Export Metadata")
        for key, value in metadata.model_dump(mode="json").items():
            if isinstance(value, dict):
                value = json.dumps(value, sort_keys=True)
            metadata_sheet.append([key, sanitize_spreadsheet_value(value)])
        metadata_sheet.column_dimensions["A"].width = 24
        metadata_sheet.column_dimensions["B"].width = 80

        output = BytesIO()
        workbook.save(output)
        return ExportArtifact(
            content=output.getvalue(),
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            extension="xlsx",
        )


class PDFRenderer(ExportRenderer):
    def render(self, records: list[ExportRecord], metadata: ExportMetadata) -> ExportArtifact:
        output = BytesIO()
        document = SimpleDocTemplate(
            output,
            pagesize=landscape(A4),
            leftMargin=8 * mm,
            rightMargin=8 * mm,
            topMargin=8 * mm,
            bottomMargin=8 * mm,
            title="Authorized Attendance Export",
        )
        styles = getSampleStyleSheet()
        story = [
            Paragraph("Authorized Attendance Export", styles["Title"]),
            Paragraph(
                escape(
                    f"Exported: {metadata.exported_at.isoformat()} | "
                    f"Tenant: {metadata.tenant_id} | Entity: {metadata.entity_id} | "
                    f"Module: {metadata.module} | Classification: {metadata.classification}"
                ),
                styles["BodyText"],
            ),
            Spacer(1, 4 * mm),
        ]
        table_headers = [
            "Date",
            "Employee",
            "Name",
            "Department",
            "Status",
            "In",
            "Out",
            "Hours",
            "%",
            "Source",
            "Confidence",
            "Review",
        ]
        table_data: list[list[Any]] = [table_headers]
        for record in records:
            locator_parts = [record.source_file]
            if record.source_sheet:
                locator_parts.append(f"sheet {record.source_sheet}")
            if record.source_page is not None:
                locator_parts.append(f"page {record.source_page}")
            if record.source_row is not None:
                locator_parts.append(f"row {record.source_row}")
            locator_parts.append(record.source_record_id)
            values = [
                record.attendance_date.isoformat(),
                record.employee_id,
                record.employee_name or "",
                record.department or "",
                record.status,
                record.check_in.isoformat() if record.check_in else "",
                record.check_out.isoformat() if record.check_out else "",
                "" if record.total_hours is None else str(record.total_hours),
                "" if record.attendance_percentage is None else str(record.attendance_percentage),
                " / ".join(locator_parts),
                f"{record.extraction_confidence:.4f}",
                record.review_status,
            ]
            table_data.append(
                [Paragraph(escape(str(value)), styles["BodyText"]) for value in values]
            )
        table = LongTable(
            table_data,
            repeatRows=1,
            colWidths=[45, 70, 75, 65, 45, 78, 78, 38, 35, 145, 55, 65],
        )
        table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#D9EAF7")),
                    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                    ("FONTSIZE", (0, 0), (-1, -1), 6),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("GRID", (0, 0), (-1, -1), 0.25, colors.grey),
                    ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.whitesmoke]),
                ]
            )
        )
        story.append(table)
        document.build(story)
        return ExportArtifact(
            content=output.getvalue(), media_type="application/pdf", extension="pdf"
        )


RENDERERS: dict[ExportFormat, ExportRenderer] = {
    ExportFormat.JSON: JSONRenderer(),
    ExportFormat.XLSX: XLSXRenderer(),
    ExportFormat.PDF: PDFRenderer(),
}
