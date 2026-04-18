import logging
from typing import Any, Dict, List, Optional

import requests

from config.settings import RAGSettings
from services.embedding_service import EmbeddingService
from services.trusted_web_cache_service import TrustedWebCacheService


logger = logging.getLogger("FIRECRAWL_SERVICE")


class FirecrawlService:
    SEARCH_URL = "https://api.firecrawl.dev/v2/search"
    SCRAPE_URL = "https://api.firecrawl.dev/v2/scrape"

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

    def fetch_and_cache(self, question: str) -> Dict[str, Any]:
        allowed_sources = self.trusted_cache_service.get_enabled_sources()
        search_hits = self.search_trusted_sources(question, allowed_sources)
        cached_rows: List[Dict[str, Any]] = []
        scraped_count = 0

        for hit in search_hits[: self.settings.trusted_web_max_scrapes]:
            url = (hit.get("url") or "").strip()
            if not url or not self.trusted_cache_service.is_allowed_url(url, allowed_sources):
                continue
            scraped = self.scrape_url(url)
            if not scraped:
                continue
            scraped_count += 1
            content = (scraped.get("content") or "").strip()
            if len(content) < 200:
                continue
            source_row = self.trusted_cache_service.map_url_to_source(url, allowed_sources)
            if source_row is None:
                continue
            vector = self.embedding_service.generate_embedding(content[:5000])
            cached_rows.append(
                self.trusted_cache_service.upsert_article(
                    source_row=source_row,
                    title=(scraped.get("title") or hit.get("title") or url),
                    content=content,
                    url=url,
                    embedding_vector=self.embedding_service.to_pgvector(vector),
                )
            )

        logger.info(
            "firecrawl fallback | called=%s | searched_sources=%s | scraped_urls=%s | cached_articles=%s",
            True,
            len(allowed_sources),
            scraped_count,
            len(cached_rows),
        )
        return {
            "cached_rows": cached_rows,
            "searched_sources_count": len(allowed_sources),
            "scraped_urls_count": scraped_count,
        }

    def search_trusted_sources(self, question: str, allowed_sources: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        if not self.enabled:
            return []
        results: List[Dict[str, Any]] = []
        for source in allowed_sources[: self.settings.trusted_web_max_sources]:
            domain = source.get("normalized_domain")
            if not domain:
                continue
            payload = {
                "query": question,
                "limit": self.settings.trusted_web_search_limit,
                "sources": [{"type": "web", "site": domain}],
            }
            try:
                response = requests.post(
                    self.SEARCH_URL,
                    headers=self._headers(),
                    json=payload,
                    timeout=max(1, self.settings.firecrawl_timeout_ms / 1000),
                )
                response.raise_for_status()
                data = response.json()
            except Exception as exc:
                logger.warning("firecrawl search failed for %s: %s", domain, exc)
                continue

            for item in data.get("data") or []:
                url = (item.get("url") or "").strip()
                if not url or not self.trusted_cache_service.is_allowed_url(url, allowed_sources):
                    continue
                results.append(
                    {
                        "url": url,
                        "title": item.get("title") or "",
                        "description": item.get("description") or "",
                        "trust_score": float(source.get("muc_do_tin_cay") or 0),
                    }
                )
        results.sort(key=lambda row: row.get("trust_score", 0), reverse=True)
        return results

    def scrape_url(self, url: str) -> Optional[Dict[str, Any]]:
        if not self.enabled:
            return None
        allowed_sources = self.trusted_cache_service.get_enabled_sources()
        if not self.trusted_cache_service.is_allowed_url(url, allowed_sources):
            logger.info("firecrawl scrape skipped | reason=url_not_whitelisted | url=%s", url)
            return None
        try:
            response = requests.post(
                self.SCRAPE_URL,
                headers=self._headers(),
                json={"url": url, "formats": ["markdown"]},
                timeout=max(1, self.settings.firecrawl_timeout_ms / 1000),
            )
            response.raise_for_status()
            data = response.json().get("data") or {}
        except Exception as exc:
            logger.warning("firecrawl scrape failed for %s: %s", url, exc)
            return None

        final_url = (data.get("metadata") or {}).get("url") or url
        if not self.trusted_cache_service.is_allowed_url(final_url, allowed_sources):
            logger.info("firecrawl scrape skipped | reason=redirect_outside_whitelist | url=%s", final_url)
            return None
        return {
            "url": final_url,
            "title": (data.get("metadata") or {}).get("title") or "",
            "content": (data.get("markdown") or "").strip(),
        }

    def _headers(self) -> Dict[str, str]:
        return {
            "Authorization": f"Bearer {self.settings.firecrawl_api_key}",
            "Content-Type": "application/json",
        }
