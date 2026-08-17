# Attendance Intelligence Synthetic Test Data

All data is synthetic.

## Positive attendance evidence
- attendance_august.csv
- attendance_august.xlsx
- attendance_august.docx
- attendance_august.pdf
- attendance_scanned.png
- attendance_handwritten_simulated.png

## Negative/non-attendance evidence
- non_attendance_valid.csv
- non_attendance_document.docx

## Suggested test questions
1. Who was present on 2026-08-10?
2. What was the average attendance percentage from 2026-08-10 to 2026-08-12?
3. Which employee had the highest attendance?
4. Which department had the highest attendance?
5. Show the source evidence for Rahul Demo on 2026-08-11.
6. What was EMP-999's attendance? (Expected unavailable)
7. What was the attendance for a date not present in the files? (Expected unavailable)

## Expected ingestion behavior
Positive attendance files should produce canonical attendance records with source lineage.

`non_attendance_valid.csv` should be rejected as:
ATTENDANCE_SCHEMA_NOT_DETECTED

`non_attendance_document.docx` should be rejected as:
NON_ATTENDANCE_DOCUMENT

OCR/image files should preserve extraction confidence and may become REVIEW_REQUIRED if confidence is below the configured threshold.
