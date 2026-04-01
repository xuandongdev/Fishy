import logging
from typing import Any, Dict, List, Optional

import requests

from config.settings import RAGSettings
from services.embedding_service import EmbeddingService
from services.trusted_web_cache_service import TrustedWebCacheService


logger = logging.getLogger("FIRECRAWL_SERVICE")


class FirecrawlService:
    SEARCH_URL = "https://api.firecrawl.dev/v2/search"
    SCRAPE_URL = "https://api.firecrawl.dev/v1/scrape"

    def __init__(
        self,
        settings: RAGSettings,
        trusted_cache_service: TrustedWebCacheService,
        embedding_service: EmbeddingService,
    ) -> None:
        self.settings = settings
        self.trusted_cache_service = trusted_cache_service
        self.embedding_service = embedding_service

    @property
    def enabled(self) -> bool:
        return bool(self.settings.firecrawl_api_key)

    def search_trusted_sources(self, question: str, allowed_sources: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        if not self.enabled:
            return []

        headers = {
            "Authorization": f"Bearer {self.settings.firecrawl_api_key}",
            "Content-Type": "application/json",
        }
        hits: List[Dict[str, Any]] = []
        seen_urls = set()

        for source in allowed_sources[: self.settings.trusted_web_max_scrapes]:
            domain = source["normalized_domain"]
            payload = {
                "query": f'site:{domain} "{question}"',
                "limit": self.settings.trusted_web_search_limit,
                "sources": ["web"],
                "timeout": self.settings.firecrawl_timeout_ms,
            }
            try:
                response = requests.post(self.SEARCH_URL, json=payload, headers=headers, timeout=self.settings.firecrawl_timeout_ms / 1000)
                response.raise_for_status()
                data = response.json().get("data", {})
                web_hits = data.get("web", []) if isinstance(data, dict) else data
                for item in web_hits or []:
                    url = (item.get("url") or "").strip()
                    if not url or url in seen_urls:
                        continue
                    if not self.trusted_cache_service.is_allowed_url(url, allowed_sources):
                        continue
                    seen_urls.add(url)
                    hits.append(
                        {
                            "url": url,
                            "title": item.get("title") or url,
                            "description": item.get("description") or "",
                            "source_domain": domain,
                            "muc_do_tin_cay": source.get("muc_do_tin_cay", 0),
                        }
                    )
            except Exception as exc:
                logger.warning("firecrawl search failed for %s: %s", domain, exc)

            if len(hits) >= self.settings.trusted_web_max_scrapes * 2:
                break

        hits.sort(key=lambda item: item.get("muc_do_tin_cay", 0), reverse=True)
        return hits

    def scrape_url(self, url: str) -> Optional[Dict[str, Any]]:
        headers = {
            "Authorization": f"Bearer {self.settings.firecrawl_api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "url": url,
            "formats": ["markdown"],
            "onlyMainContent": True,
            "timeout": self.settings.firecrawl_timeout_ms,
            "parsePDF": True,
        }
        response = requests.post(self.SCRAPE_URL, json=payload, headers=headers, timeout=self.settings.firecrawl_timeout_ms / 1000)
        response.raise_for_status()
        return response.json().get("data")

    def fetch_and_cache(self, question: str) -> List[Dict[str, Any]]:
        allowed_sources = self.trusted_cache_service.get_enabled_sources()
        search_hits = self.search_trusted_sources(question, allowed_sources)
        cached_rows: List[Dict[str, Any]] = []

        for hit in search_hits[: self.settings.trusted_web_max_scrapes]:
            try:
                scraped = self.scrape_url(hit["url"])
                if not scraped:
                    continue
                content = self._normalize_content(scraped.get("markdown") or "")
                if len(content) < 200:
                    continue
                source_row = self.trusted_cache_service.map_url_to_source(hit["url"], allowed_sources)
                if not source_row:
                    continue
                embedding = self.embedding_service.generate_embedding(content)
                cached_rows.append(
                    self.trusted_cache_service.upsert_article(
                        source_row=source_row,
                        title=(scraped.get("metadata") or {}).get("title") or hit["title"],
                        content=content,
                        url=(scraped.get("metadata") or {}).get("sourceURL") or hit["url"],
                        embedding_vector=self.embedding_service.to_pgvector(embedding),
                    )
                )
            except Exception as exc:
                logger.warning("firecrawl scrape failed for %s: %s", hit.get("url"), exc)

        return cached_rows

    def _normalize_content(self, content: str) -> str:
        normalized = " ".join((content or "").split())
        return normalized[:15000]
