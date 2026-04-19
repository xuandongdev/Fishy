from __future__ import annotations

import os
import sys
from typing import Any

from dotenv import load_dotenv
from qdrant_client import QdrantClient, models


COLLECTION_NAME = "global_docs"


def get_existing_schema_map(collection_info: Any) -> dict[str, dict]:
    """
    Trả về payload schema hiện có của collection.
    Hỗ trợ cả object-style lẫn dict-style để đỡ lệch version client.
    """
    payload_schema = None

    if hasattr(collection_info, "payload_schema"):
        payload_schema = collection_info.payload_schema
    elif isinstance(collection_info, dict):
        payload_schema = collection_info.get("payload_schema")

    if payload_schema is None:
        return {}

    if isinstance(payload_schema, dict):
        return payload_schema

    # fallback nếu client trả object lạ
    try:
        return dict(payload_schema)
    except Exception:
        return {}


def has_field_index(schema_map: dict[str, dict], field_name: str) -> bool:
    return field_name in schema_map


def create_index_if_missing(
    client: QdrantClient,
    collection_name: str,
    schema_map: dict[str, dict],
    field_name: str,
    field_schema: Any,
) -> bool:
    """
    Trả True nếu vừa tạo mới, False nếu đã tồn tại.
    """
    if has_field_index(schema_map, field_name):
        print(f"[SKIP] {field_name}: already indexed")
        return False

    print(f"[CREATE] {field_name}: {field_schema}")
    client.create_payload_index(
        collection_name=collection_name,
        field_name=field_name,
        field_schema=field_schema,
        wait=True,
    )
    return True


def main() -> int:
    load_dotenv()

    qdrant_url = os.getenv("QDRANT_URL") or os.getenv("QDRANT_ENDPOINT")
    qdrant_api_key = os.getenv("QDRANT_API_KEY") or os.getenv("QDRANT_KEY")
    collection_name = os.getenv("QDRANT_COLLECTION_GLOBAL_DOCS", COLLECTION_NAME)

    if not qdrant_url:
        print("ERROR: Missing QDRANT_URL in environment")
        return 1

    client = QdrantClient(
        url=qdrant_url,
        api_key=qdrant_api_key,
        timeout=30.0,
    )

    print(f"Connecting to Qdrant: {qdrant_url}")
    print(f"Collection: {collection_name}")

    try:
        collection_info = client.get_collection(collection_name=collection_name)
    except Exception as exc:
        print(f"ERROR: Cannot load collection '{collection_name}': {exc}")
        return 1

    schema_map = get_existing_schema_map(collection_info)

    print("\nExisting payload schema fields:")
    if not schema_map:
        print("  (none)")
    else:
        for key in sorted(schema_map.keys()):
            print(f"  - {key}")

    created_count = 0

    # Keyword indexes
    keyword_fields = [
        "scope",
        "source_type",
        "file_id",
        "filename",
        "so_hieu",
        "loai_van_ban",
        "chapter",
        "muc",
        "dieu",
        "khoan",
        "diem",
        "anchor_type",
        "trang_thai",
        "co_quan_ban_hanh",
        "doc_type",
    ]

    for field in keyword_fields:
        if create_index_if_missing(
            client,
            collection_name,
            schema_map,
            field,
            models.PayloadSchemaType.KEYWORD,
        ):
            created_count += 1
            schema_map[field] = {"data_type": "keyword"}

    # Bool indexes
    bool_fields = [
        "is_active",
    ]

    for field in bool_fields:
        if create_index_if_missing(
            client,
            collection_name,
            schema_map,
            field,
            models.PayloadSchemaType.BOOL,
        ):
            created_count += 1
            schema_map[field] = {"data_type": "bool"}

    # Text indexes
    text_fields = [
        "title",
        "ten_van_ban",
        "section_path",
        "content",
    ]

    for field in text_fields:
        if create_index_if_missing(
            client,
            collection_name,
            schema_map,
            field,
            models.TextIndexParams(
                type="text",
                tokenizer=models.TokenizerType.WORD,
                lowercase=True,
            ),
        ):
            created_count += 1
            schema_map[field] = {"data_type": "text"}

    print(f"\nDone. Created {created_count} new payload index(es).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())