import json

import httpx
from demo_ingestion import access_token, seed_scope


def main() -> None:
    subject, product_id, tenant_id, entity_id = seed_scope()
    token = access_token(subject, lifetime_minutes=120)
    response = httpx.get(
        "http://api:8000/api/v1/auth/context",
        headers={
            "Authorization": f"Bearer {token}",
            "X-Product-ID": product_id,
            "X-Tenant-ID": tenant_id,
        },
        timeout=30,
    )
    response.raise_for_status()
    print(
        json.dumps(
            {
                "bearer_token": token,
                "product_id": product_id,
                "tenant_id": tenant_id,
                "authorized_entity_id": entity_id,
                "verified": True,
                "note": "The verified local demo token expires after 2 hours.",
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
