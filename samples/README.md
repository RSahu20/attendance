# Synthetic attendance samples

All people and employee identifiers in this directory are fictional.

`tenant-a` contains equivalent evidence in CSV, XLSX, DOCX, text PDF, image, and
scanned-PDF formats. It includes present, absent, leave, and WFH values across multiple
departments and dates. `tenant-b` contains a separate CSV to support tenant-isolation
demonstrations.

Regenerate binary samples with the dependency-complete API image:

```bash
docker compose run --rm -v .:/workspace -w /workspace api \
  python samples/generate_samples.py
```
