import logging
from typing import Any, Dict, List, Optional

import requests
from requests import Response, Session
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

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
        self.session = self._build_session()

    @property
    def enabled(self) -> bool:
        return bool(self.settings.firecrawl_api_key)

    def fetch_and_cache(self, question: str) -> Dict[str, Any]:
        allowed_sources = self.trusted_cache_service.get_enabled_sources()
        searched_sources = allowed_sources[: self.settings.trusted_web_max_sources]
        search_hits = self.search_trusted_sources(question, searched_sources)
        cached_rows: List[Dict[str, Any]] = []
        scraped_urls_count = 0

        for hit in search_hits:
            source_row = self.trusted_cache_service.map_url_to_source(hit["url"], searched_sources)
            if not source_row:
                continue

            content = self._normalize_content(hit.get("content") or "")
            if not content:
                scraped = self.scrape_url(hit["url"])
                scraped_urls_count += 1
                content = self._normalize_content((scraped or {}).get("markdown") or "")
                if scraped:
                    metadata = scraped.get("metadata") or {}
                    hit["title"] = metadata.get("title") or hit.get("title")
                    hit["url"] = metadata.get("sourceURL") or hit["url"]

            if len(content) < 200:
                continue

            try:
                embedding = self.embedding_service.generate_embedding(content)
                cached_rows.append(
                    self.trusted_cache_service.upsert_article(
                        source_row=source_row,
                        title=hit.get("title") or hit["url"],
                        content=content,
                        url=hit["url"],
                        embedding_vector=self.embedding_service.to_pgvector(embedding),
                    )
                )
            except Exception as exc:
                logger.warning("firecrawl cache failed for %s: %s", hit.get("url"), exc)

        logger.info(
            "firecrawl fallback | called=%s | searched_sources=%s | scraped_urls=%s | cached_articles=%s",
            self.enabled,
            len(searched_sources),
            scraped_urls_count,
            len(cached_rows),
        )
        return {
            "cached_rows": cached_rows,
            "searched_sources_count": len(searched_sources),
            "scraped_urls_count": scraped_urls_count,
        }

    def search_trusted_sources(self, question: str, allowed_sources: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        if not self.enabled or not allowed_sources:
            return []

        hits: List[Dict[str, Any]] = []
        seen_urls = set()

        for source in allowed_sources:
            domain = source["normalized_domain"]
            payload = {
                "query": f"site:{domain} {question}",
                "limit": self.settings.trusted_web_search_limit,
                "sources": ["web"],
                "ignoreInvalidURLs": True,
                "scrapeOptions": {
                    "formats": ["markdown"],
                    "onlyMainContent": True,
                    "parsers": ["pdf"],
                    "timeout": self.settings.firecrawl_timeout_ms,
                },
                "timeout": self.settings.firecrawl_timeout_ms,
            }
            try:
                response = self._post_json(self.SEARCH_URL, payload)
                web_hits = self._extract_search_results(response)
                for item in web_hits:
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
                            "content": self._extract_item_content(item),
                            "source_domain": domain,
                            "muc_do_tin_cay": source.get("muc_do_tin_cay", 0),
                        }
                    )
            except Exception as exc:
                logger.warning("firecrawl search failed for %s: %s", domain, exc)

        hits.sort(key=lambda item: item.get("muc_do_tin_cay", 0), reverse=True)
        return hits[: self.settings.trusted_web_max_scrapes]

    def scrape_url(self, url: str) -> Optional[Dict[str, Any]]:
        if not self.enabled:
            return None

        payload = {
            "url": url,
            "formats": ["markdown"],
            "onlyMainContent": True,
            "parsers": ["pdf"],
            "timeout": self.settings.firecrawl_timeout_ms,
        }
        try:
            response = self._post_json(self.SCRAPE_URL, payload)
            data = response.json().get("data")
            return data if isinstance(data, dict) else None
        except Exception as exc:
            logger.warning("firecrawl scrape failed for %s: %s", url, exc)
            return None

    def _build_session(self) -> Session:
        session = requests.Session()
        retries = Retry(
            total=2,
            backoff_factor=0.5,
            status_forcelist=[408, 429, 500, 502, 503, 504],
            allowed_methods=["POST"],
        )
        adapter = HTTPAdapter(max_retries=retries)
        session.mount("https://", adapter)
        session.mount("http://", adapter)
        return session

    def _post_json(self, url: str, payload: Dict[str, Any]) -> Response:
        headers = {
            "Authorization": f"Bearer {self.settings.firecrawl_api_key}",
            "Content-Type": "application/json",
        }
        response = self.session.post(
            url,
            json=payload,
            headers=headers,
            timeout=max(1, self.settings.firecrawl_timeout_ms / 1000),
        )
        response.raise_for_status()
        return response

    def _extract_search_results(self, response: Response) -> List[Dict[str, Any]]:
        data = response.json().get("data")
        if isinstance(data, dict):
            web_hits = data.get("web")
            if isinstance(web_hits, list):
                return [item for item in web_hits if isinstance(item, dict)]
        if isinstance(data, list):
            return [item for item in data if isinstance(item, dict)]
        return []

    def _extract_item_content(self, item: Dict[str, Any]) -> str:
        for key in ("markdown", "content", "description"):
            value = item.get(key)
            if isinstance(value, str) and value.strip():
                return value
        metadata = item.get("metadata") or {}
        markdown = metadata.get("markdown")
        return markdown if isinstance(markdown, str) else ""

    def _normalize_content(self, content: str) -> str:
        normalized = " ".join((content or "").split())
        return normalized[:15000]
