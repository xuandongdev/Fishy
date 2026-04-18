import logging
import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Sequence, Tuple

try:
    from qdrant_client import QdrantClient
    from qdrant_client.http import models as qmodels
except ImportError:  # pragma: no cover
    QdrantClient = None
    qmodels = None

from config.settings import RAGSettings


logger = logging.getLogger("QDRANT_SERVICE")


class QdrantService:
    def __init__(self, settings: RAGSettings, vector_size: int) -> None:
        self.settings = settings
        self.vector_size = vector_size
        self.session_collection_name = settings.qdrant_collection_session_docs or "session_docs"
        self.global_collection_name = settings.qdrant_collection_global_docs or "global_docs"
        self.client: Optional[QdrantClient] = None
        self._collections_ready = False

        if QdrantClient is not None and settings.qdrant_url:
            self.client = QdrantClient(url=settings.qdrant_url, api_key=settings.qdrant_api_key or None)

    @property
    def enabled(self) -> bool:
        return self.client is not None and self.vector_size > 0

    def ensure_collections(self) -> None:
        if self._collections_ready:
            logger.info("qdrant ensure skipped | collections_ready=True")
            return
        logger.info("qdrant ensure_collections begin")
        self._ensure_collection(self.session_collection_name)
        self._ensure_collection(self.global_collection_name)
        self._ensure_session_indexes()
        self._ensure_global_indexes()
        self._collections_ready = True
        logger.info("qdrant ensure_collections end | collections_ready=True")

    def ensure_collection(self) -> None:
        self.ensure_collections()

    def _ensure_collection(self, collection_name: str) -> None:
        if not self.enabled or qmodels is None:
            return
        existing = [item.name for item in self.client.get_collections().collections]
        if collection_name in existing:
            return
        self.client.create_collection(
            collection_name=collection_name,
            vectors_config=qmodels.VectorParams(size=self.vector_size, distance=qmodels.Distance.COSINE),
        )

    def _ensure_session_indexes(self) -> None:
        self._ensure_payload_indexes(
            self.session_collection_name,
            [
                ("session_id", qmodels.PayloadSchemaType.KEYWORD),
                ("source_type", qmodels.PayloadSchemaType.KEYWORD),
                ("file_id", qmodels.PayloadSchemaType.KEYWORD),
                ("doc_type", qmodels.PayloadSchemaType.KEYWORD),
                ("filename", qmodels.PayloadSchemaType.KEYWORD),
                ("expires_at", qmodels.PayloadSchemaType.KEYWORD),
            ],
        )

    def _ensure_global_indexes(self) -> None:
        self._ensure_payload_indexes(
            self.global_collection_name,
            [
                ("scope", qmodels.PayloadSchemaType.KEYWORD),
                ("source_type", qmodels.PayloadSchemaType.KEYWORD),
                ("is_active", qmodels.PayloadSchemaType.BOOL),
                ("file_id", qmodels.PayloadSchemaType.KEYWORD),
                ("filename", qmodels.PayloadSchemaType.KEYWORD),
                ("doc_type", qmodels.PayloadSchemaType.KEYWORD),
                ("title", qmodels.TextIndexParams(type="text", tokenizer="word", lowercase=True)),
                ("ten_van_ban", qmodels.TextIndexParams(type="text", tokenizer="word", lowercase=True)),
                ("filename", qmodels.TextIndexParams(type="text", tokenizer="word", lowercase=True)),
                ("section_path", qmodels.TextIndexParams(type="text", tokenizer="word", lowercase=True)),
                ("content", qmodels.TextIndexParams(type="text", tokenizer="word", lowercase=True)),
                ("so_hieu", qmodels.PayloadSchemaType.KEYWORD),
                ("loai_van_ban", qmodels.PayloadSchemaType.KEYWORD),
                ("trang_thai", qmodels.PayloadSchemaType.KEYWORD),
                ("linh_vuc", qmodels.PayloadSchemaType.KEYWORD),
                ("co_quan_ban_hanh", qmodels.PayloadSchemaType.KEYWORD),
                ("dieu", qmodels.PayloadSchemaType.KEYWORD),
                ("khoan", qmodels.PayloadSchemaType.KEYWORD),
                ("diem", qmodels.PayloadSchemaType.KEYWORD),
            ],
        )

    def _ensure_payload_indexes(self, collection_name: str, index_specs: Sequence[Tuple[str, Any]]) -> None:
        if not self.enabled or qmodels is None:
            return
        for field_name, schema_type in index_specs:
            try:
                self.client.create_payload_index(
                    collection_name=collection_name,
                    field_name=field_name,
                    field_schema=schema_type,
                    wait=True,
                )
            except Exception as exc:
                message = str(exc).lower()
                if "already exists" in message or "duplicate" in message:
                    continue
                logger.warning(
                    "qdrant payload index ensure failed | collection=%s | field=%s | reason=%s",
                    collection_name,
                    field_name,
                    exc,
                )

    def upsert_session_chunks(self, chunks: List[Dict[str, Any]]) -> int:
        return self._upsert_chunks(self.session_collection_name, chunks)

    def upsert_global_chunks(self, chunks: List[Dict[str, Any]]) -> int:
        return self._upsert_chunks(self.global_collection_name, chunks)

    def _upsert_chunks(self, collection_name: str, chunks: List[Dict[str, Any]]) -> int:
        if not self.enabled or qmodels is None or not chunks:
            return 0
        if not self._collections_ready:
            logger.warning("qdrant upsert called before collections ready | collection=%s", collection_name)
            self.ensure_collections()
        points = []
        for item in chunks:
            vector = item.get("vector")
            if not vector:
                continue
            payload = dict(item.get("payload") or {})
            points.append(qmodels.PointStruct(id=item["id"], vector=vector, payload=payload))
        if not points:
            return 0
        self.client.upsert(collection_name=collection_name, points=points, wait=True)
        return len(points)

    def search_session_docs(self, session_id: str, query_vector: List[float], limit: int = 5) -> List[Dict[str, Any]]:
        if not session_id:
            return []
        return self._search(
            collection_name=self.session_collection_name,
            query_vector=query_vector,
            limit=limit,
            query_filter=qmodels.Filter(
                must=[
                    qmodels.FieldCondition(key="session_id", match=qmodels.MatchValue(value=session_id)),
                    qmodels.FieldCondition(key="source_type", match=qmodels.MatchValue(value="user_upload")),
                ]
            ),
            source_type="user_upload",
        )

    def search_global_docs(self, question: str, query_vector: List[float], limit: int = 5) -> List[Dict[str, Any]]:
        if not self.enabled or qmodels is None:
            return []

        branch_limit = max(int(limit), 5)
        query_meta = self._parse_legal_query(question)
        exact_hits = self._search_global_exact(question=question, query_meta=query_meta, limit=branch_limit)
        text_hits = self._search_global_text(question=question, limit=branch_limit)
        dense_hits = self._search(
            collection_name=self.global_collection_name,
            query_vector=query_vector,
            limit=branch_limit,
            query_filter=self._global_base_filter(),
            source_type="admin_upload",
        )
        fused_hits = self._fuse_global_hits(
            question=question,
            exact_hits=exact_hits,
            text_hits=text_hits,
            dense_hits=dense_hits,
            limit=limit,
        )
        logger.info(
            "global qdrant hybrid | collections_ready=%s | exact_hits=%s | text_hits=%s | dense_hits=%s | fused_hits=%s",
            self._collections_ready,
            len(exact_hits),
            len(text_hits),
            len(dense_hits),
            len(fused_hits),
        )
        return fused_hits

    def _global_base_filter(self) -> Any:
        return qmodels.Filter(
            must=[
                qmodels.FieldCondition(key="scope", match=qmodels.MatchValue(value="global")),
                qmodels.FieldCondition(key="source_type", match=qmodels.MatchValue(value="admin_upload")),
                qmodels.FieldCondition(key="is_active", match=qmodels.MatchValue(value=True)),
            ]
        )

    def _search(
        self,
        collection_name: str,
        query_vector: List[float],
        limit: int,
        query_filter: Any,
        source_type: str,
    ) -> List[Dict[str, Any]]:
        if not self.enabled or qmodels is None or not query_vector:
            return []
        if not self._collections_ready:
            logger.warning("qdrant search skipped ensure | collections_ready=False | collection=%s", collection_name)
        now_iso = datetime.now(timezone.utc).isoformat()
        search_response = self.client.query_points(
            collection_name=collection_name,
            query=query_vector,
            limit=limit,
            query_filter=query_filter,
            with_payload=True,
            with_vectors=False,
        )
        search_results = getattr(search_response, "points", None) or getattr(search_response, "result", None) or []
        return self._normalize_hits(
            items=search_results,
            source_type=source_type,
            source_table=collection_name,
            now_iso=now_iso,
            score_key="semantic_score",
        )

    def _search_global_exact(self, question: str, query_meta: Dict[str, Optional[str]], limit: int) -> List[Dict[str, Any]]:
        if not self.enabled or qmodels is None:
            return []
        filters: List[Any] = []
        base_must = list(self._global_base_filter().must or [])
        if query_meta.get("so_hieu"):
            filters.append(
                qmodels.Filter(
                    must=base_must + [qmodels.FieldCondition(key="so_hieu", match=qmodels.MatchValue(value=query_meta["so_hieu"]))]
                )
            )
        for field_name in ["dieu", "khoan", "diem"]:
            if query_meta.get(field_name):
                filters.append(
                    qmodels.Filter(
                        must=base_must
                        + [qmodels.FieldCondition(key=field_name, match=qmodels.MatchValue(value=query_meta[field_name]))]
                    )
                )
        if query_meta.get("loai_van_ban"):
            filters.append(
                qmodels.Filter(
                    must=base_must
                    + [qmodels.FieldCondition(key="loai_van_ban", match=qmodels.MatchValue(value=query_meta["loai_van_ban"]))]
                )
            )
        if query_meta.get("trang_thai"):
            filters.append(
                qmodels.Filter(
                    must=base_must
                    + [qmodels.FieldCondition(key="trang_thai", match=qmodels.MatchValue(value=query_meta["trang_thai"]))]
                )
            )
        if query_meta.get("code"):
            filters.append(
                qmodels.Filter(
                    must=base_must + [qmodels.FieldCondition(key="filename", match=qmodels.MatchText(text=query_meta["code"]))]
                )
            )
            filters.append(
                qmodels.Filter(
                    must=base_must + [qmodels.FieldCondition(key="title", match=qmodels.MatchText(text=query_meta["code"]))]
                )
            )
            filters.append(
                qmodels.Filter(
                    must=base_must + [qmodels.FieldCondition(key="ten_van_ban", match=qmodels.MatchText(text=query_meta["code"]))]
                )
            )

        collected: List[Any] = []
        for query_filter in filters[:4]:
            records, _ = self.client.scroll(
                collection_name=self.global_collection_name,
                scroll_filter=query_filter,
                limit=limit,
                with_payload=True,
                with_vectors=False,
            )
            collected.extend(records)

        hits = self._normalize_hits(
            items=collected,
            source_type="admin_upload",
            source_table=self.global_collection_name,
            now_iso=datetime.now(timezone.utc).isoformat(),
            score_key="exact_score",
        )
        normalized_question = self._normalize_text(question)
        for hit in hits:
            local_exact = 0.0
            probe = self._normalize_text(
                " ".join(
                    str(hit.get(key) or "")
                    for key in ["title", "ten_van_ban", "filename", "so_hieu", "section_path", "label", "content", "trang_thai"]
                )
            )
            if query_meta.get("so_hieu") and query_meta["so_hieu"].lower() in probe:
                local_exact += 1.0
            if query_meta.get("code") and query_meta["code"].lower() in probe:
                local_exact += 0.9
            for field_name in ["dieu", "khoan", "diem"]:
                value = query_meta.get(field_name)
                if value and str(hit.get(field_name) or "").lower() == value.lower():
                    local_exact += 0.7
            if query_meta.get("loai_van_ban") and str(hit.get("loai_van_ban") or "").lower() == query_meta["loai_van_ban"].lower():
                local_exact += 0.4
            if query_meta.get("trang_thai") and str(hit.get("trang_thai") or "").lower() == query_meta["trang_thai"].lower():
                local_exact += 0.35
            if normalized_question and normalized_question in probe:
                local_exact += 0.3
            hit["exact_score"] = local_exact
            hit["hybrid_score"] = max(float(hit.get("hybrid_score") or 0.0), local_exact)
        hits.sort(key=lambda item: float(item.get("exact_score") or 0.0), reverse=True)
        return hits[:limit]

    def _search_global_text(self, question: str, limit: int) -> List[Dict[str, Any]]:
        if not self.enabled or qmodels is None:
            return []
        base_must = list(self._global_base_filter().must or [])
        filters = [
            qmodels.Filter(must=base_must + [qmodels.FieldCondition(key="title", match=qmodels.MatchText(text=question))]),
            qmodels.Filter(must=base_must + [qmodels.FieldCondition(key="ten_van_ban", match=qmodels.MatchText(text=question))]),
            qmodels.Filter(must=base_must + [qmodels.FieldCondition(key="filename", match=qmodels.MatchText(text=question))]),
            qmodels.Filter(must=base_must + [qmodels.FieldCondition(key="section_path", match=qmodels.MatchText(text=question))]),
            qmodels.Filter(must=base_must + [qmodels.FieldCondition(key="content", match=qmodels.MatchText(text=question))]),
        ]
        collected: List[Any] = []
        for query_filter in filters:
            records, _ = self.client.scroll(
                collection_name=self.global_collection_name,
                scroll_filter=query_filter,
                limit=limit,
                with_payload=True,
                with_vectors=False,
            )
            collected.extend(records)

        hits = self._normalize_hits(
            items=collected,
            source_type="admin_upload",
            source_table=self.global_collection_name,
            now_iso=datetime.now(timezone.utc).isoformat(),
            score_key="text_score",
        )
        for hit in hits:
            text_score = self._text_overlap_score(question, hit)
            hit["text_score"] = text_score
            hit["lexical_score"] = max(float(hit.get("lexical_score") or 0.0), text_score)
            hit["hybrid_score"] = max(float(hit.get("hybrid_score") or 0.0), text_score)
        hits.sort(key=lambda item: float(item.get("text_score") or 0.0), reverse=True)
        return hits[:limit]

    def _normalize_hits(
        self,
        items: List[Any],
        source_type: str,
        source_table: str,
        now_iso: str,
        score_key: str,
    ) -> List[Dict[str, Any]]:
        hits: List[Dict[str, Any]] = []
        seen_ids = set()
        for item in items:
            payload = dict(getattr(item, "payload", None) or {})
            expires_at = str(payload.get("expires_at") or "")
            if expires_at and expires_at < now_iso:
                continue
            primary_id = str(getattr(item, "id", None) or payload.get("primary_id") or "")
            if primary_id and primary_id in seen_ids:
                continue
            if primary_id:
                seen_ids.add(primary_id)
            score = float(getattr(item, "score", 0.0) or 0.0)
            section_path = payload.get("section_path")
            filename = payload.get("filename")
            page_start = payload.get("page_start")
            page_end = payload.get("page_end")
            label_parts = [part for part in [payload.get("ten_van_ban") or payload.get("title") or filename, section_path] if part]
            if page_start is not None:
                label_parts.append(f"trang {page_start}-{page_end}" if page_end not in {None, page_start} else f"trang {page_start}")
            hits.append(
                {
                    "primary_id": primary_id,
                    "label": " | ".join(label_parts) if label_parts else filename or f"chunk_{payload.get('chunk_index', 0)}",
                    "content": payload.get("content") or "",
                    "url": None,
                    "source_type": source_type,
                    "source_table": source_table,
                    "hybrid_score": score,
                    "semantic_score": score if score_key == "semantic_score" else 0.0,
                    "lexical_score": score if score_key == "text_score" else 0.0,
                    "exact_score": score if score_key == "exact_score" else 0.0,
                    "session_id": payload.get("session_id"),
                    "file_id": payload.get("file_id"),
                    "filename": filename,
                    "title": payload.get("title"),
                    "ten_van_ban": payload.get("ten_van_ban"),
                    "chunk_index": payload.get("chunk_index"),
                    "section_path": section_path,
                    "page_start": page_start,
                    "page_end": page_end,
                    "doc_type": payload.get("doc_type"),
                    "uploaded_at": payload.get("uploaded_at"),
                    "expires_at": payload.get("expires_at"),
                    "scope": payload.get("scope"),
                    "is_active": payload.get("is_active"),
                    "so_hieu": payload.get("so_hieu"),
                    "loai_van_ban": payload.get("loai_van_ban"),
                    "trang_thai": payload.get("trang_thai"),
                    "ngay_ban_hanh": payload.get("ngay_ban_hanh"),
                    "ngay_hieu_luc": payload.get("ngay_hieu_luc"),
                    "linh_vuc": payload.get("linh_vuc"),
                    "co_quan_ban_hanh": payload.get("co_quan_ban_hanh"),
                    "chapter": payload.get("chapter"),
                    "muc": payload.get("muc"),
                    "dieu": payload.get("dieu"),
                    "khoan": payload.get("khoan"),
                    "diem": payload.get("diem"),
                }
            )
        return hits

    def _fuse_global_hits(
        self,
        question: str,
        exact_hits: List[Dict[str, Any]],
        text_hits: List[Dict[str, Any]],
        dense_hits: List[Dict[str, Any]],
        limit: int,
    ) -> List[Dict[str, Any]]:
        fused: Dict[str, Dict[str, Any]] = {}
        query_tokens = set(self._tokenize(question))
        for branch_name, hits in [("exact", exact_hits), ("text", text_hits), ("dense", dense_hits)]:
            for rank, hit in enumerate(hits[: max(limit, 5)], start=1):
                item = fused.setdefault(hit["primary_id"], dict(hit))
                item["exact_score"] = max(float(item.get("exact_score") or 0.0), float(hit.get("exact_score") or 0.0))
                item["text_score"] = max(float(item.get("text_score") or 0.0), float(hit.get("text_score") or 0.0))
                item["semantic_score"] = max(float(item.get("semantic_score") or 0.0), float(hit.get("semantic_score") or 0.0))
                item[f"{branch_name}_rank"] = min(int(item.get(f"{branch_name}_rank") or 9999), rank)

        for item in fused.values():
            title_overlap = len(query_tokens & set(self._tokenize(str(item.get("ten_van_ban") or item.get("title") or ""))))
            path_overlap = len(query_tokens & set(self._tokenize(str(item.get("section_path") or ""))))
            exact_bonus = 0.35 if float(item.get("exact_score") or 0.0) > 0 else 0.0
            overlap_bonus = min(0.24, title_overlap * 0.08 + path_overlap * 0.06)
            item["hybrid_score"] = (
                float(item.get("exact_score") or 0.0) * 0.75
                + float(item.get("text_score") or 0.0) * 0.55
                + float(item.get("semantic_score") or 0.0) * 0.45
                + exact_bonus
                + overlap_bonus
            )
            item["final_rerank_score"] = item["hybrid_score"]

        return sorted(fused.values(), key=lambda item: float(item.get("hybrid_score") or 0.0), reverse=True)[:limit]

    def _parse_legal_query(self, question: str) -> Dict[str, Optional[str]]:
        normalized = self._normalize_text(question)
        so_hieu_match = re.search(r"\b\d{1,4}/\d{4}(?:/[a-z0-9\-]+)?\b", normalized, re.I)
        loai_van_ban = None
        for candidate in ["nghị định", "nghi dinh", "luật", "luat", "thông tư", "thong tu", "quyết định", "quyet dinh"]:
            if candidate in normalized:
                loai_van_ban = candidate.replace("nghi dinh", "nghị định").replace("luat", "luật").replace("thong tu", "thông tư").replace("quyet dinh", "quyết định")
                break
        code_match = re.search(r"\b[a-z]{1,4}\d{4,}\b", normalized, re.I)
        dieu_match = re.search(r"(điều|dieu)\s+(\d+[a-z]?)", normalized, re.I)
        khoan_match = re.search(r"(khoản|khoan)\s+(\d+[a-z]?)", normalized, re.I)
        diem_match = re.search(r"(điểm|diem)\s+([a-z0-9]+)", normalized, re.I)
        return {
            "so_hieu": so_hieu_match.group(0).upper() if so_hieu_match else None,
            "loai_van_ban": loai_van_ban,
            "dieu": dieu_match.group(2) if dieu_match else None,
            "khoan": khoan_match.group(2) if khoan_match else None,
            "diem": diem_match.group(2) if diem_match else None,
            "code": code_match.group(0).upper() if code_match else None,
        }

    def _text_overlap_score(self, question: str, hit: Dict[str, Any]) -> float:
        query_tokens = set(self._tokenize(question))
        probe = " ".join(str(hit.get(key) or "") for key in ["title", "filename", "section_path", "content"])
        hit_tokens = set(self._tokenize(probe))
        overlap = len(query_tokens & hit_tokens)
        if not query_tokens:
            return 0.0
        score = overlap / max(len(query_tokens), 1)
        if str(hit.get("so_hieu") or "").lower() and str(hit.get("so_hieu") or "").lower() in self._normalize_text(question):
            score += 0.4
        return score

    def _tokenize(self, text: str) -> List[str]:
        return [token for token in re.findall(r"\w+", self._normalize_text(text)) if len(token) >= 2]

    def _normalize_text(self, text: str) -> str:
        return re.sub(r"\s+", " ", (text or "").strip().lower())

    def _parse_legal_query(self, question: str) -> Dict[str, Optional[str]]:
        normalized = self._normalize_text(question)
        so_hieu_match = re.search(r"\b\d{1,4}/\d{4}(?:/[a-z0-9\-]+)?\b", normalized, re.I)
        loai_van_ban = None
        for candidate in ["nghi dinh", "luat", "thong tu", "quyet dinh"]:
            if candidate in normalized:
                loai_van_ban = {
                    "nghi dinh": "nghị định",
                    "luat": "luật",
                    "thong tu": "thông tư",
                    "quyet dinh": "quyết định",
                }[candidate]
                break
        code_match = re.search(r"\b[a-z]{1,4}\d{4,}\b", normalized, re.I)
        dieu_match = re.search(r"\bdieu\s+(\d+[a-z]?)", normalized, re.I)
        khoan_match = re.search(r"\bkhoan\s+(\d+[a-z]?)", normalized, re.I)
        diem_match = re.search(r"\bdiem\s+([a-z0-9]+)", normalized, re.I)
        trang_thai = None
        if "con hieu luc" in normalized:
            trang_thai = "conHieuLuc"
        elif "het hieu luc" in normalized:
            trang_thai = "hetHieuLuc"
        return {
            "so_hieu": so_hieu_match.group(0).upper() if so_hieu_match else None,
            "loai_van_ban": loai_van_ban,
            "trang_thai": trang_thai,
            "dieu": dieu_match.group(1) if dieu_match else None,
            "khoan": khoan_match.group(1) if khoan_match else None,
            "diem": diem_match.group(1) if diem_match else None,
            "code": code_match.group(0).upper() if code_match else None,
        }

    def _text_overlap_score(self, question: str, hit: Dict[str, Any]) -> float:
        query_tokens = set(self._tokenize(question))
        probe = " ".join(
            str(hit.get(key) or "")
            for key in ["title", "ten_van_ban", "filename", "section_path", "content", "trang_thai", "so_hieu"]
        )
        hit_tokens = set(self._tokenize(probe))
        overlap = len(query_tokens & hit_tokens)
        if not query_tokens:
            return 0.0
        score = overlap / max(len(query_tokens), 1)
        if str(hit.get("so_hieu") or "").lower() and str(hit.get("so_hieu") or "").lower() in self._normalize_text(question):
            score += 0.4
        if str(hit.get("trang_thai") or "").lower() and str(hit.get("trang_thai") or "").lower() in self._normalize_text(question):
            score += 0.15
        return score

    def delete_session_docs(self, session_id: str) -> int:
        if not self.enabled or qmodels is None or not session_id:
            return 0
        self.client.delete(
            collection_name=self.session_collection_name,
            points_selector=qmodels.FilterSelector(
                filter=qmodels.Filter(
                    must=[qmodels.FieldCondition(key="session_id", match=qmodels.MatchValue(value=session_id))]
                )
            ),
            wait=True,
        )
        return 1

    def delete_expired_docs(self) -> int:
        if not self.enabled or qmodels is None:
            return 0
        deleted_ids: List[Any] = []
        deleted_ids.extend(self._collect_expired_ids(self.session_collection_name))
        deleted_ids.extend(self._collect_expired_ids(self.global_collection_name))
        return len(deleted_ids)

    def _collect_expired_ids(self, collection_name: str) -> List[Any]:
        now_iso = datetime.now(timezone.utc).isoformat()
        deleted_ids: List[Any] = []
        offset = None
        while True:
            records, offset = self.client.scroll(
                collection_name=collection_name,
                limit=128,
                with_vectors=False,
                with_payload=True,
                offset=offset,
            )
            if not records:
                break
            expired_ids = []
            for record in records:
                payload = dict(record.payload or {})
                expires_at = str(payload.get("expires_at") or "")
                if expires_at and expires_at < now_iso:
                    expired_ids.append(record.id)
            if expired_ids:
                self.client.delete(
                    collection_name=collection_name,
                    points_selector=qmodels.PointIdsList(points=expired_ids),
                    wait=True,
                )
                deleted_ids.extend(expired_ids)
            if offset is None:
                break
        return deleted_ids

    def has_session_docs(self, session_id: str) -> bool:
        if not self.enabled or qmodels is None or not session_id:
            return False
        records, _ = self.client.scroll(
            collection_name=self.session_collection_name,
            limit=1,
            with_vectors=False,
            with_payload=False,
            scroll_filter=qmodels.Filter(
                must=[
                    qmodels.FieldCondition(key="session_id", match=qmodels.MatchValue(value=session_id)),
                    qmodels.FieldCondition(key="source_type", match=qmodels.MatchValue(value="user_upload")),
                ]
            ),
        )
        return bool(records)

    def has_global_docs(self) -> bool:
        if not self.enabled or qmodels is None:
            return False
        records, _ = self.client.scroll(
            collection_name=self.global_collection_name,
            limit=1,
            with_vectors=False,
            with_payload=False,
            scroll_filter=qmodels.Filter(
                must=[
                    qmodels.FieldCondition(key="scope", match=qmodels.MatchValue(value="global")),
                    qmodels.FieldCondition(key="source_type", match=qmodels.MatchValue(value="admin_upload")),
                    qmodels.FieldCondition(key="is_active", match=qmodels.MatchValue(value=True)),
                ]
            ),
        )
        return bool(records)

    def deactivate_global_doc(self, file_id: str) -> int:
        return self._update_global_doc_active(file_id, False)

    def activate_global_doc(self, file_id: str) -> int:
        return self._update_global_doc_active(file_id, True)

    def _update_global_doc_active(self, file_id: str, is_active: bool) -> int:
        if not self.enabled or qmodels is None or not file_id:
            return 0
        points = self._scroll_global_doc_ids(file_id)
        if not points:
            return 0
        self.client.set_payload(
            collection_name=self.global_collection_name,
            payload={"is_active": is_active},
            points=points,
            wait=True,
        )
        return len(points)

    def delete_global_doc(self, file_id: str) -> int:
        if not self.enabled or qmodels is None or not file_id:
            return 0
        points = self._scroll_global_doc_ids(file_id)
        if not points:
            return 0
        self.client.delete(
            collection_name=self.global_collection_name,
            points_selector=qmodels.PointIdsList(points=points),
            wait=True,
        )
        return len(points)

    def _scroll_global_doc_ids(self, file_id: str) -> List[Any]:
        ids: List[Any] = []
        offset = None
        while True:
            records, offset = self.client.scroll(
                collection_name=self.global_collection_name,
                limit=128,
                with_vectors=False,
                with_payload=False,
                offset=offset,
                scroll_filter=qmodels.Filter(
                    must=[qmodels.FieldCondition(key="file_id", match=qmodels.MatchValue(value=file_id))]
                ),
            )
            if not records:
                break
            ids.extend(record.id for record in records)
            if offset is None:
                break
        return ids
