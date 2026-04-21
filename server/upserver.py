import argparse
import logging
import os
import re
import subprocess
import sys
import time
from datetime import datetime, timezone

from dotenv import load_dotenv
from supabase import create_client

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | [%(levelname)s] | %(message)s",
)
logger = logging.getLogger("CLOUDFLARE_TUNNEL_UPDATER")

SUPABASE_URL = os.getenv("SUPABASE_URL", "").strip()
SUPABASE_SERVICE_ROLE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "").strip()
CLOUDFLARED_PATH = os.getenv("CLOUDFLARED_PATH", r"D:/Fishy/server/cloudflared.exe").strip()

URL_PATTERN = re.compile(r"https://[a-zA-Z0-9-]+\.trycloudflare\.com")


def update_app_config(key: str, value: str) -> None:
    if not SUPABASE_URL or not SUPABASE_SERVICE_ROLE_KEY:
        raise RuntimeError("Thiếu SUPABASE_URL hoặc SUPABASE_SERVICE_ROLE_KEY trong .env")

    supabase = create_client(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY)
    supabase.table("app_config").upsert(
        {
            "key": key,
            "value": value,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        },
        on_conflict="key",
    ).execute()


def start_quick_tunnel(port: int, app_key: str) -> None:
    if not os.path.exists(CLOUDFLARED_PATH):
        raise FileNotFoundError(f"Không tìm thấy cloudflared tại: {CLOUDFLARED_PATH}")

    cmd = [CLOUDFLARED_PATH, "tunnel", "--url", f"http://127.0.0.1:{port}"]
    logger.info("[Cloudflare] Khởi động Quick Tunnel | key=%s | port=%s", app_key, port)

    process = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        universal_newlines=True,
        encoding="utf-8",
        errors="ignore",
        bufsize=1,
    )

    public_url = None

    try:
        # Quick Tunnel thường in URL ở stderr
        while True:
            line = process.stderr.readline()
            if not line:
                # process chết sớm
                if process.poll() is not None:
                    raise RuntimeError("cloudflared đã thoát trước khi tạo được tunnel")
                time.sleep(0.1)
                continue

            line = line.strip()
            if line:
                logger.info("[cloudflared] %s", line)

            match = URL_PATTERN.search(line)
            if match:
                public_url = match.group(0)
                break

        logger.info("[Cloudflare] URL mới: %s", public_url)
        update_app_config(app_key, public_url)
        logger.info("[Cloudflare] Đã cập nhật %s lên Supabase.", app_key)

        logger.info("[Cloudflare] Tunnel đang chạy. Nhấn Ctrl+C để dừng.")
        while True:
            if process.poll() is not None:
                logger.warning("[Cloudflare] cloudflared đã dừng.")
                break
            time.sleep(1)

    except KeyboardInterrupt:
        logger.info("[Cloudflare] Dừng tunnel theo yêu cầu người dùng...")
    finally:
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()


def main() -> None:
    parser = argparse.ArgumentParser(description="Chạy Cloudflare Quick Tunnel và update app_config trên Supabase.")
    parser.add_argument("--port", type=int, required=True, help="Port local của service, ví dụ 8000 hoặc 8001")
    parser.add_argument("--key", type=str, required=True, help="Key trong app_config, ví dụ rag_url hoặc yolo_url")
    args = parser.parse_args()

    start_quick_tunnel(port=args.port, app_key=args.key)


if __name__ == "__main__":
    main()