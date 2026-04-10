import logging
import re
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

from supabase import Client

from config.settings import RAGSettings


logger = logging.getLogger("TRUSTED_WEB_CACHE")


class TrustedWebCacheService:
    def __init__(self, supabase: Client, settings: RAGSettings) -> None:
        self.supabase = supabase
        self.settings = settings

    def get_enabled_sources(self) -> List[Dict[str, Any]]:
        response = (
            self.supabase.table("nguon_uy_tin")
            .select("*")
            .eq("bat", True)
            .eq("loai", "web")
            .order("muc_do_tin_cay", desc=True)
            .execute()
        )
        sources = response.data or []
        for source in sources:
            source["normalized_domain"] = self.normalize_domain(source.get("base_url", ""))
        return [source for source in sources if source.get("normalized_domain")]

    def normalize_domain(self, base_url: str) -> str:
        raw = (base_url or "").strip()
        if not raw:
            return ""
        if "://" not in raw:
            raw = "https://" + raw
        parsed = urlparse(raw)
        domain = (parsed.hostname or parsed.netloc or parsed.path or "").strip().lower().rstrip(".")
        domain = re.sub(r"^www\.", "", domain)
        return domain

    def is_allowed_url(self, url: str, sources: List[Dict[str, Any]]) -> bool:
        target_domain = self.normalize_domain(url)
        return self.map_url_to_source(url, sources) is not None

    def map_url_to_source(self, url: str, sources: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        target_domain = self.normalize_domain(url)
        matched_sources = []
        for source in sources:
            domain = source["normalized_domain"]
            if target_domain == domain or target_domain.endswith("." + domain):
                matched_sources.append(source)
        if not matched_sources:
            return None
        matched_sources.sort(key=lambda item: len(item["normalized_domain"]), reverse=True)
        return matched_sources[0]

    def upsert_article(
        self,
        source_row: Dict[str, Any],
        title: str,
        content: str,
        url: str,
        embedding_vector: Optional[str],
    ) -> Dict[str, Any]:
        existing = self.supabase.table("bai_viet_uy_tin").select("*").eq("url", url).limit(1).execute()
        payload = {
            "manguon": source_row["manguon"],
            "tieu_de": title[:500] if title else url,
            "noidung": content,
            "url": url,
            "embedding": embedding_vector,
        }
        try:
            upserted = self.supabase.table("bai_viet_uy_tin").upsert(payload, on_conflict="url").execute()
            if upserted.data:
                return upserted.data[0]
        except Exception as exc:
            logger.warning("trusted cache upsert by url failed, fallback to update/insert: %s", exc)

        if existing.data:
            updated = self.supabase.table("bai_viet_uy_tin").update(payload).eq("id", existing.data[0]["id"]).execute()
            return updated.data[0]
        inserted = self.supabase.table("bai_viet_uy_tin").insert(payload).execute()
        return inserted.data[0]

    def search_trusted_cache(self, question: str, query_vector: List[float], limit: int = 5) -> List[Dict[str, Any]]:
        try:
            rpc_response = self.supabase.rpc(
                "match_web_docs",
                {
                    "vector_truy_van": query_vector,
                    "nguong_khop": self.settings.rag_trusted_score_threshold,
                    "so_luong_ket_qua": limit,
                },
            ).execute()
            rows = rpc_response.data or []
            logger.info("trusted retrieval rpc | function=match_web_docs | results=%s", len(rows))
            return [
                {
                    "source_type": "trusted_web_cache",
                    "source_table": "bai_viet_uy_tin",
                    "primary_id": row.get("id"),
                    "label": row.get("tieu_de") or row.get("url"),
                    "content": row.get("noidung", ""),
                    "url": row.get("url"),
                    "lexical_score": float(row.get("do_tuong_dong", 0.0)),
                    "semantic_score": float(row.get("do_tuong_dong", 0.0)),
                    "hybrid_score": float(row.get("do_tuong_dong", 0.0)),
                }
                for row in rows
            ]
        except Exception as exc:
            logger.warning("match_web_docs unavailable, fallback to hybrid/python ranking: %s", exc)
            return self._fallback_trusted_cache_search(question, query_vector, limit)

    def _fallback_trusted_cache_search(self, question: str, query_vector: List[float], limit: int) -> List[Dict[str, Any]]:
        vector_literal = "[" + ",".join(f"{value:.10f}" for value in query_vector) + "]"
        try:
            rpc_response = self.supabase.rpc(
                "hybrid_search_trusted_articles",
                {
                    "query_text": question,
                    "query_embedding": vector_literal,
                    "result_limit": limit,
                },
            ).execute()
            rows = rpc_response.data or []
            logger.info("trusted retrieval rpc | function=hybrid_search_trusted_articles | results=%s", len(rows))
            return rows
        except Exception as exc:
            logger.warning("trusted cache rpc unavailable, fallback to python ranking: %s", exc)
            response = self.supabase.table("bai_viet_uy_tin").select("*").limit(50).execute()
            rows = response.data or []
            keywords = set(re.findall(r"\w+", question.lower()))
            ranked = []
            for row in rows:
                haystack = f"{row.get('tieu_de', '')} {row.get('noidung', '')}".lower()
                lexical = sum(1 for token in keywords if token in haystack)
                if lexical:
                    ranked.append(
                        {
                            "source_type": "trusted_web_cache",
                            "source_table": "bai_viet_uy_tin",
                            "primary_id": row.get("id"),
                            "label": row.get("tieu_de") or row.get("url"),
                            "content": row.get("noidung", ""),
                            "url": row.get("url"),
                            "lexical_score": float(lexical),
                            "semantic_score": 0.0,
                            "hybrid_score": float(lexical),
                        }
                    )
            ranked.sort(key=lambda item: item["hybrid_score"], reverse=True)
            return ranked[:limit]
