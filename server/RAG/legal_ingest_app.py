import logging
import os
import re
import subprocess
import threading
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from supabase import Client, create_client

from router.legal_document_router import create_legal_document_router


load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | [%(levelname)s] | %(message)s",
)
logger = logging.getLogger("LEGAL_INGEST_APP")

PORT_NUMBER = 8010
CLOUDFLARED_PATH = os.getenv("CLOUDFLARED_PATH", r"D:/Fishy/server/cloudflared.exe")
SUPABASE_URL = os.getenv("SUPABASE_URL", "").strip()
SUPABASE_SERVICE_ROLE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "").strip()


def start_cloudflare_tunnel(port: int, supabase_client: Client) -> None:
    cmd = [CLOUDFLARED_PATH, "tunnel", "--url", f"http://127.0.0.1:{port}"]
    logger.info("[Cloudflare] Dang khoi dong tunnel cho legal_ingest (port %s)...", port)

    try:
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            universal_newlines=True,
            encoding="utf-8",
            errors="ignore",
        )
        url_pattern = re.compile(r"https://[a-zA-Z0-9-]+\.trycloudflare\.com")

        while True:
            line = process.stderr.readline()
            if not line:
                break

            match = url_pattern.search(line)
            if not match:
                continue

            public_url = match.group(0)
            logger.info("[Cloudflare] LEGAL_INGEST URL: %s", public_url)
            try:
                supabase_client.table("app_config").upsert(
                    {
                        "key": "legal_ingest_url",
                        "value": public_url,
                        "updated_at": datetime.now(timezone.utc).isoformat(),
                    },
                    on_conflict="key",
                ).execute()
                logger.info("[Cloudflare] Da luu legal_ingest_url len Supabase.")
            except Exception as exc:
                logger.warning("[Cloudflare] Khong the cap nhat legal_ingest_url: %s", exc)
            break
    except FileNotFoundError:
        logger.warning(
            "[Cloudflare] Khong tim thay cloudflared tai %s. legal_ingest van chay local tren port %s.",
            CLOUDFLARED_PATH,
            port,
        )
    except Exception as exc:
        logger.warning("[Cloudflare] Tunnel legal_ingest loi: %s", exc)


@asynccontextmanager
async def lifespan(_: FastAPI):
    if SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY:
        try:
            supabase_client = create_client(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY)
            threading.Thread(
                target=start_cloudflare_tunnel,
                args=(PORT_NUMBER, supabase_client),
                daemon=True,
            ).start()
        except Exception as exc:
            logger.warning("Khong the khoi tao Supabase cho legal_ingest tunnel: %s", exc)
    else:
        logger.info("Bo qua legal_ingest Cloudflare vi thieu SUPABASE_URL hoac SUPABASE_SERVICE_ROLE_KEY.")

    yield


app = FastAPI(title="Fishy Legal Ingest API", version="1.0.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(create_legal_document_router())


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("legal_ingest_app:app", host="0.0.0.0", port=PORT_NUMBER, reload=True)
