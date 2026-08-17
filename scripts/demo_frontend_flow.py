import json
from pathlib import Path

import httpx
from demo_ingestion import access_token, seed_scope


def main() -> None:
    subject, product_id, tenant_id, entity_id = seed_scope()
    headers = {
        "Authorization": f"Bearer {access_token(subject)}",
        "X-Product-ID": product_id,
        "X-Tenant-ID": tenant_id,
    }
    context = {
        "entity_id": entity_id,
        "module": "attendance",
        "classification": 1,
    }
    sample = Path("/workspace/samples/tenant-a/attendance.csv")
    frontend_base = "http://frontend:5173"
    with httpx.Client(timeout=60) as client:
        frontend = client.get(frontend_base)
        frontend.raise_for_status()
        auth = client.get(f"{frontend_base}/api/v1/auth/context", headers=headers)
        auth.raise_for_status()
        upload = client.post(
            f"{frontend_base}/api/v1/documents",
            headers=headers,
            files={"file": (sample.name, sample.read_bytes(), "text/csv")},
            data={**context, "logical_name": "demo-attendance"},
        )
        upload.raise_for_status()
        upload_result = upload.json()
        status = client.get(
            f"{frontend_base}/api/v1/ingestion-jobs/{upload_result['job_id']}",
            headers=headers,
        )
        status.raise_for_status()

        answers = {}
        for name, question in {
            "structured": "How many attendance records?",
            "cited": "Engineering",
            "unsupported": "??",
        }.items():
            response = client.post(
                f"{frontend_base}/api/v1/queries",
                headers=headers,
                json={**context, "question": question, "filters": {}},
            )
            response.raise_for_status()
            answers[name] = response.json()

        exports = {}
        for format_name in ("json", "xlsx", "pdf"):
            response = client.post(
                f"{frontend_base}/api/v1/exports",
                headers=headers,
                json={**context, "format": format_name, "dataset": "attendance"},
            )
            response.raise_for_status()
            export = response.json()
            download = client.get(
                f"{frontend_base}/api/v1/exports/{export['export_id']}/download",
                headers=headers,
            )
            download.raise_for_status()
            exports[format_name] = {
                "status": export["status"],
                "record_count": export["record_count"],
                "bytes": len(download.content),
            }

    cited = answers["cited"]
    result = {
        "frontend": {
            "status": frontend.status_code,
            "title_present": "Attendance Intelligence" in frontend.text,
        },
        "authorized_grants": len(auth.json()["grants"]),
        "upload": {
            "status": upload_result["status"],
            "idempotent": upload_result["idempotent"],
            "job_status": status.json()["status"],
            "normalized_records": status.json()["normalized_record_count"],
        },
        "structured_answer": {
            "status": answers["structured"]["status"],
            "answer": answers["structured"]["answer"],
            "confidence": answers["structured"]["confidence"],
        },
        "cited_answer": {
            "status": cited["status"],
            "citation_count": len(cited["citations"]),
            "source_locator": cited["citations"][0]["source_locator"]
            if cited["citations"]
            else None,
            "confidence": cited["confidence"],
        },
        "unsupported_answer": {
            "status": answers["unsupported"]["status"],
            "reason": answers["unsupported"]["unavailable_reason"],
        },
        "exports": exports,
    }
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
