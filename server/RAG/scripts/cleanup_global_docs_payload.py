import logging
import sys
from typing import Any, Dict, List

from config.settings import RAGSettings
from services.embedding_service import EmbeddingService
from services.qdrant_service import LEGACY_GLOBAL_FIELDS, QdrantService, qmodels


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("CLEANUP_GLOBAL_DOCS_PAYLOAD")


def main() -> int:
    settings = RAGSettings.from_env()
    embedding_service = EmbeddingService(settings)
    qdrant_service = QdrantService(settings, vector_size=embedding_service.vector_size)
    if not qdrant_service.enabled or qdrant_service.client is None:
        logger.error("Qdrant is not configured.")
        return 1

    client = qdrant_service.client
    collection_name = qdrant_service.global_collection_name
    updated = 0
    offset = None

    while True:
        records, offset = client.scroll(
            collection_name=collection_name,
            limit=64,
            with_payload=True,
            with_vectors=True,
            offset=offset,
        )
        if not records:
            break

        points: List[Any] = []
        for record in records:
            payload = dict(record.payload or {})
            if not any(field in payload for field in LEGACY_GLOBAL_FIELDS):
                continue
            cleaned_payload: Dict[str, Any] = {key: value for key, value in payload.items() if key not in LEGACY_GLOBAL_FIELDS}
            points.append(qmodels.PointStruct(id=record.id, vector=record.vector, payload=cleaned_payload))

        if points:
            client.upsert(collection_name=collection_name, points=points, wait=True)
            updated += len(points)
            logger.info("cleanup batch updated | count=%s", len(points))

        if offset is None:
            break

    logger.info("cleanup completed | updated_points=%s", updated)
    return 0


if __name__ == "__main__":
    sys.exit(main())
