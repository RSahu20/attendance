"""End-to-end feature test — runs inside the API container with mock LLM."""
import json, sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from generate_token import seed_demo, generate_token
import httpx

BASE = "http://api:8000"
SAMPLES = Path(__file__).resolve().parent.parent / "samples" / "tenant-a"
RESULTS = {}

def log(name, passed, detail=""):
    icon = "✅" if passed else "❌"
    RESULTS[name] = passed
    print(f"{icon} {name}" + (f" — {detail}" if detail else ""))

def main():
    subject, pid, tid, eid = seed_demo()
    token = generate_token(subject, lifetime_hours=1)
    headers = {
        "Authorization": f"Bearer {token}",
        "X-Product-ID": pid,
        "X-Tenant-ID": tid,
    }
    c = httpx.Client(base_url=BASE, timeout=60, headers=headers)

    # 1. Health
    r = c.get("/health/live")
    log("Health: Liveness", r.status_code == 200, r.text)

    r = c.get("/health/ready")
    log("Health: Readiness", r.status_code == 200 and "pgvector" in r.text, r.text)

    # 2. Auth context
    r = c.get("/api/v1/auth/context")
    log("Auth: Context", r.status_code == 200 and r.json().get("tenant_id") == tid,
        f"grants={len(r.json().get('grants', []))}")

    # 3. Upload CSV
    csv_path = SAMPLES / "attendance.csv"
    r = c.post("/api/v1/documents",
        files={"file": ("attendance.csv", csv_path.read_bytes(), "text/csv")},
        data={"entity_id": eid, "module": "attendance", "classification": "1"})
    log("Ingestion: CSV upload", r.status_code == 201, f"status={r.json().get('status')}")
    csv_job = r.json().get("job_id")
    csv_doc = r.json().get("document_id")
    csv_checksum = r.json().get("checksum")

    # 4. Upload XLSX
    xlsx_path = SAMPLES / "attendance.xlsx"
    r = c.post("/api/v1/documents",
        files={"file": ("attendance.xlsx", xlsx_path.read_bytes(),
               "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
        data={"entity_id": eid, "module": "attendance", "classification": "1"})
    log("Ingestion: XLSX upload", r.status_code == 201, f"status={r.json().get('status')}")

    # 5. Upload DOCX
    docx_path = SAMPLES / "attendance.docx"
    r = c.post("/api/v1/documents",
        files={"file": ("attendance.docx", docx_path.read_bytes(),
               "application/vnd.openxmlformats-officedocument.wordprocessingml.document")},
        data={"entity_id": eid, "module": "attendance", "classification": "1"})
    log("Ingestion: DOCX upload", r.status_code == 201, f"status={r.json().get('status')}")

    # 6. Upload text PDF
    pdf_path = SAMPLES / "attendance-text.pdf"
    r = c.post("/api/v1/documents",
        files={"file": ("attendance-text.pdf", pdf_path.read_bytes(), "application/pdf")},
        data={"entity_id": eid, "module": "attendance", "classification": "1"})
    log("Ingestion: Text PDF upload", r.status_code == 201, f"status={r.json().get('status')}")

    # 7. Upload scanned image (OCR)
    img_path = SAMPLES / "attendance-scan.png"
    r = c.post("/api/v1/documents",
        files={"file": ("attendance-scan.png", img_path.read_bytes(), "image/png")},
        data={"entity_id": eid, "module": "attendance", "classification": "1"})
    log("Ingestion: OCR image upload", r.status_code == 201, f"status={r.json().get('status')}")

    # 8. Upload scanned PDF (OCR)
    spdf_path = SAMPLES / "attendance-scanned.pdf"
    r = c.post("/api/v1/documents",
        files={"file": ("attendance-scanned.pdf", spdf_path.read_bytes(), "application/pdf")},
        data={"entity_id": eid, "module": "attendance", "classification": "1"})
    log("Ingestion: Scanned PDF upload", r.status_code == 201, f"status={r.json().get('status')}")

    # 9. Idempotency — re-upload same CSV
    r = c.post("/api/v1/documents",
        files={"file": ("attendance.csv", csv_path.read_bytes(), "text/csv")},
        data={"entity_id": eid, "module": "attendance", "classification": "1"})
    log("Ingestion: Idempotency (re-upload)", r.status_code == 201 and r.json().get("idempotent") == True,
        f"idempotent={r.json().get('idempotent')}, checksum_match={r.json().get('checksum')==csv_checksum}")

    # 10. Ingestion job status
    r = c.get(f"/api/v1/ingestion-jobs/{csv_job}")
    j = r.json()
    log("Ingestion: Job status", r.status_code == 200 and j.get("status") == "completed",
        f"records={j.get('normalized_record_count')}, review={j.get('review_required_count')}, errors={j.get('error_count')}")

    # 11. Structured query — count
    r = c.post("/api/v1/queries", json={
        "question": "How many employees were present?",
        "entity_id": eid, "module": "attendance", "classification": 1})
    a = r.json()
    log("Query: Structured (count)", r.status_code == 200 and a.get("status") in ("answered","unavailable"),
        f"mode={a.get('retrieval_mode')}, confidence={a.get('confidence',{}).get('band')}")

    # 12. Document query — evidence
    r = c.post("/api/v1/queries", json={
        "question": "Show supporting evidence for Asha Fiction's attendance",
        "entity_id": eid, "module": "attendance", "classification": 1})
    a = r.json()
    log("Query: Document (evidence)", r.status_code == 200,
        f"mode={a.get('retrieval_mode')}, citations={len(a.get('citations',[]))}, conf={a.get('confidence',{}).get('score')}")

    # 13. Hybrid query
    r = c.post("/api/v1/queries", json={
        "question": "How many employees were present with supporting evidence?",
        "entity_id": eid, "module": "attendance", "classification": 1})
    a = r.json()
    log("Query: Hybrid", r.status_code == 200,
        f"mode={a.get('retrieval_mode')}, status={a.get('status')}")

    # 14. Unavailable query (out-of-evidence)
    r = c.post("/api/v1/queries", json={
        "question": "Predict next year's attendance rates",
        "entity_id": eid, "module": "attendance", "classification": 1})
    a = r.json()
    log("Query: Unavailable/low-confidence", r.status_code == 200,
        f"status={a.get('status')}, reason={a.get('unavailable_reason')}, conf={a.get('confidence',{}).get('band')}")

    # 15–17. Exports
    for fmt in ("json", "xlsx", "pdf"):
        r = c.post("/api/v1/exports", json={
            "entity_id": eid, "module": "attendance", "classification": 1,
            "format": fmt, "dataset": "attendance"})
        if r.status_code == 201:
            exp = r.json()
            exp_id = exp["export_id"]
            # Download
            dl = c.get(f"/api/v1/exports/{exp_id}/download")
            log(f"Export: {fmt.upper()}", dl.status_code == 200,
                f"records={exp.get('record_count')}, size={len(dl.content)} bytes")
        else:
            log(f"Export: {fmt.upper()}", False, f"status={r.status_code}, body={r.text[:200]}")

    # 18. Cross-tenant isolation (wrong tenant)
    bad_headers = {
        "Authorization": f"Bearer {token}",
        "X-Product-ID": pid,
        "X-Tenant-ID": "00000000-0000-0000-0000-000000000000",
    }
    r = httpx.get(f"{BASE}/api/v1/auth/context", headers=bad_headers, timeout=10)
    log("Security: Cross-tenant denial", r.status_code == 403,
        f"status={r.status_code}")

    # 19. Missing auth
    r = httpx.get(f"{BASE}/api/v1/auth/context", timeout=10)
    log("Security: Missing JWT denial", r.status_code in (401, 403, 422),
        f"status={r.status_code}")

    c.close()

    # Summary
    passed = sum(1 for v in RESULTS.values() if v)
    total = len(RESULTS)
    print(f"\n{'='*50}")
    print(f"Results: {passed}/{total} passed")
    if passed < total:
        for name, ok in RESULTS.items():
            if not ok: print(f"  FAILED: {name}")
        sys.exit(1)
    else:
        print("All feature tests passed!")

if __name__ == "__main__":
    main()
