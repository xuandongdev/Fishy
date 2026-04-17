import base64
import logging
import os
import re
import subprocess
import sys
import threading
from collections import Counter
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Dict, Optional

import cv2
import numpy as np
from dotenv import load_dotenv
from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from starlette.datastructures import UploadFile as StarletteUploadFile
from supabase import Client, create_client
from ultralytics import YOLO

# ======================================================
# 1. CẤU HÌNH CỤC BỘ
# ======================================================
load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
PORT_NUMBER = int(os.getenv("YOLO_PORT", "8001"))
CLOUDFLARED_PATH = os.getenv("CLOUDFLARED_PATH", r"D:/Fishy/server/cloudflared.exe")

# ====== MODEL CHÍNH: CHỈ CẦN SỬA BLOCK NÀY ======
MODEL_ID = "local_best_model"
MODEL_PATH = r"D:/Fishy/server/Yolo/best.pt"
CLASSES_PATH: Optional[str] = "D:/Fishy/server/Yolo/class_vie.txt"
CLASSES_CODE_PATH: Optional[str] = "D:/Fishy/server/Yolo/class_code.txt"
ENABLE_CLASS_LOADING = True
USE_MODEL_NAMES_IF_AVAILABLE = False
COMBINE_CODE_AND_NAME = True
MODEL_DESCRIPTION = "Model YOLO chính đang dùng trong server"
# ================================================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)

model: Optional[YOLO] = None
classes_dict: Dict[int, str] = {}
supabase: Optional[Client] = None


# ======================================================
# 2. HÀM TỰ ĐỘNG CLOUDFLARE (GIỐNG APP/APP2/APP3)
# ======================================================
def start_cloudflare_tunnel(port: int, supabase_client: Optional[Client]) -> None:
    """
    Chạy cloudflared tunnel ngầm, bắt lấy link và up lên Supabase vào key 'yolo_url'.
    Cách hoạt động giữ giống app/app2/app3: server start là chạy tunnel luôn.
    """
    cmd = [CLOUDFLARED_PATH, "tunnel", "--url", f"http://127.0.0.1:{port}"]

    logger.info(f"[Cloudflare] Đang khởi động Tunnel cho YOLO (Port {port})...")

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
            if match:
                public_url = match.group(0)
                logger.info(f"[Cloudflare] TÌM THẤY LINK YOLO: {public_url}")

                if supabase_client is None:
                    logger.warning("Không có Supabase client -> không thể lưu yolo_url.")
                else:
                    try:
                        supabase_client.table("app_config").update(
                            {
                                "value": public_url,
                                "updated_at": datetime.now(timezone.utc).isoformat(),
                            }
                        ).eq("key", "yolo_url").execute()
                        logger.info("Đã lưu link YOLO lên Supabase thành công!")
                    except Exception as exc:
                        logger.error(f"Lỗi update Supabase: {exc}")
                break
    except FileNotFoundError:
        logger.critical(
            f"LỖI: Không tìm thấy file 'cloudflared' tại: {CLOUDFLARED_PATH}. "
            "Hãy kiểm tra lại CLOUDFLARED_PATH hoặc cài đặt file exe đúng vị trí."
        )
    except Exception as exc:
        logger.error(f"Lỗi Cloudflare Process: {exc}")


# ======================================================
# 3. HÀM HỖ TRỢ LOAD CLASS
# ======================================================
def _read_non_empty_lines(path: str) -> list[str]:
    with open(path, "r", encoding="utf-8") as f:
        return [line.strip() for line in f if line.strip()]


def build_classes_dict(loaded_model: YOLO) -> Dict[int, str]:
    """
    Ưu tiên:
    1) classes_code + classes_vie (giống app2)
    2) classes_vie בלבד (giống app1)
    3) model.names (giống app3)
    """
    mapping: Dict[int, str] = {}

    try:
        has_vie = bool(CLASSES_PATH) and os.path.exists(CLASSES_PATH)
        has_code = bool(CLASSES_CODE_PATH) and os.path.exists(CLASSES_CODE_PATH)

        if has_vie and has_code:
            vie_lines = _read_non_empty_lines(CLASSES_PATH)
            code_lines = _read_non_empty_lines(CLASSES_CODE_PATH)
            n = min(len(vie_lines), len(code_lines))

            if len(vie_lines) != len(code_lines):
                logger.warning(
                    "Mismatch số dòng giữa classes_vie và classes_code: code=%s, vie=%s. Sẽ lấy min=%s.",
                    len(code_lines),
                    len(vie_lines),
                    n,
                )

            if COMBINE_CODE_AND_NAME:
                mapping = {i: f"{code_lines[i]} - {vie_lines[i]}" for i in range(n)}
            else:
                mapping = {i: vie_lines[i] for i in range(n)}

            logger.info("Đã load mapping class từ code + vie: %s class.", len(mapping))
            return mapping

        if has_vie:
            vie_lines = _read_non_empty_lines(CLASSES_PATH)
            mapping = {i: name for i, name in enumerate(vie_lines)}
            logger.info("Đã load class từ file tiếng Việt: %s class.", len(mapping))
            return mapping

        if USE_MODEL_NAMES_IF_AVAILABLE:
            names = getattr(loaded_model, "names", None)
            if isinstance(names, dict) and names:
                mapping = {int(k): str(v) for k, v in names.items()}
                logger.info("Đã load class từ model.names dạng dict: %s class.", len(mapping))
                return mapping
            if isinstance(names, list) and names:
                mapping = {i: str(v) for i, v in enumerate(names)}
                logger.info("Đã load class từ model.names dạng list: %s class.", len(mapping))
                return mapping

        logger.warning("Không có CLASSES_PATH / CLASSES_CODE_PATH / model.names hợp lệ.")
        return {}
    except Exception as exc:
        logger.error(f"Lỗi khi build classes_dict: {exc}")
        return {}


# ======================================================
# 4. HÀM HỖ TRỢ XỬ LÝ ẢNH VÀ REQUEST
# ======================================================
def get_class_name(result, cls_id: int) -> str:
    if classes_dict:
        return classes_dict.get(cls_id, f"Class {cls_id}")

    names = getattr(result, "names", None)
    if isinstance(names, dict):
        return str(names.get(cls_id, f"Class {cls_id}"))
    if isinstance(names, list) and 0 <= cls_id < len(names):
        return str(names[cls_id])
    return f"Class {cls_id}"


async def extract_upload_file(request: Request, file: Optional[UploadFile]) -> UploadFile:
    """
    Ưu tiên nhận field 'file' chuẩn cho Postman/Flutter mới.
    Nếu thiếu thì fallback scan form như app/app2/app3 cũ.
    """
    if file is not None:
        return file

    form = await request.form()
    for value in form.values():
        if isinstance(value, StarletteUploadFile):
            return value

    raise HTTPException(status_code=422, detail="Thiếu file upload. Hãy gửi multipart/form-data với field 'file'.")


async def decode_image(upload_file: UploadFile) -> np.ndarray:
    contents = await upload_file.read()
    nparr = np.frombuffer(contents, np.uint8)
    img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
    if img is None:
        raise HTTPException(status_code=400, detail="File bị hỏng hoặc không phải ảnh hợp lệ.")
    return img


# ======================================================
# 5. LIFESPAN
# ======================================================
@asynccontextmanager
async def lifespan(app: FastAPI):
    global model, classes_dict, supabase

    if SUPABASE_URL and SUPABASE_KEY:
        try:
            supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
            logger.info("Kết nối Supabase OK.")
        except Exception as exc:
            supabase = None
            logger.error(f"Lỗi kết nối Supabase: {exc}")
    else:
        logger.info("Thiếu SUPABASE_URL hoặc SUPABASE_SERVICE_ROLE_KEY -> bỏ qua Supabase.")

    # Giống app/app2/app3: startup là chạy cloudflare luôn
    t = threading.Thread(target=start_cloudflare_tunnel, args=(PORT_NUMBER, supabase), daemon=True)
    t.start()

    logger.info("Đang tải model '%s' từ: %s", MODEL_ID, MODEL_PATH)
    if not os.path.exists(MODEL_PATH):
        logger.critical("Không tìm thấy model tại: %s", MODEL_PATH)
        model = None
    else:
        try:
            model = YOLO(MODEL_PATH)
            logger.info("Load model thành công. %s", MODEL_DESCRIPTION)
        except Exception as exc:
            logger.critical(f"Lỗi load model: {exc}")
            model = None

    if model is not None:
        if ENABLE_CLASS_LOADING:
            classes_dict = build_classes_dict(model)
            if classes_dict:
                preview = classes_dict.get(0)
                logger.info("Preview class[0]=%s", preview)
            else:
                logger.warning("Server sẽ dùng fallback tên class từ result.names nếu có.")
        else:
            classes_dict = {}
            logger.info("ENABLE_CLASS_LOADING=False -> tạm tắt load class để kiểm tra model/raw names.")

    logger.info("SERVER YOLO đang chạy tại port %s", PORT_NUMBER)
    yield


app = FastAPI(lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ======================================================
# 6. API
# ======================================================
@app.get("/")
async def root():
    return {
        "service": "yolo-server",
        "status": "ok" if model is not None else "model_not_ready",
        "model_id": MODEL_ID,
        "model_path": MODEL_PATH,
    }


@app.get("/health")
async def health():
    return {
        "status": "ok" if model is not None else "model_not_ready",
        "model_id": MODEL_ID,
        "model_path": MODEL_PATH,
        "has_classes_file": bool(CLASSES_PATH and os.path.exists(CLASSES_PATH)),
        "has_classes_code_file": bool(CLASSES_CODE_PATH and os.path.exists(CLASSES_CODE_PATH)),
        "class_count": len(classes_dict),
    }


@app.post("/detect")
async def detect(
    request: Request,
    file: Optional[UploadFile] = File(default=None),
    conf: float = Form(default=0.25),
):
    global model

    if model is None:
        raise HTTPException(status_code=500, detail="Model chưa sẵn sàng.")

    upload_file = await extract_upload_file(request, file)
    img = await decode_image(upload_file)

    try:
        results = model(img, conf=conf, verbose=False)
        detected_names: list[str] = []
        annotated_img = img

        for result in results:
            if classes_dict:
                result.names = classes_dict
            annotated_img = result.plot()
            if result.boxes is not None and len(result.boxes) > 0:
                for box in result.boxes:
                    cls_id = int(box.cls[0])
                    detected_names.append(get_class_name(result, cls_id))

        if detected_names:
            counts = Counter(detected_names)
            summary_parts = [f"{count} {name}" for name, count in counts.items()]
            summary_text = "Phát hiện: " + ", ".join(summary_parts)
        else:
            summary_text = "Không phát hiện thấy vật thể nào."

        success, buffer = cv2.imencode(".jpg", annotated_img)
        image_base64 = base64.b64encode(buffer).decode("utf-8") if success else None

        logger.info("Kết quả detect: %s", summary_text)
        return {"summary": summary_text, "image_base64": image_base64}
    except HTTPException:
        raise
    except Exception as exc:
        logger.error(f"Lỗi xử lý /detect: {exc}")
        raise HTTPException(status_code=500, detail=f"Lỗi Server: {exc}")


@app.post("/detect-lite")
async def detect_lite(
    request: Request,
    file: Optional[UploadFile] = File(default=None),
    conf: float = Form(default=0.25),
):
    global model

    if model is None:
        raise HTTPException(status_code=500, detail="Model chưa sẵn sàng.")

    upload_file = await extract_upload_file(request, file)
    img = await decode_image(upload_file)

    try:
        h, w = img.shape[:2]
        results = model(img, conf=conf, verbose=False)

        boxes_out = []
        detected_names: list[str] = []

        for result in results:
            if classes_dict:
                result.names = classes_dict

            if result.boxes is not None and len(result.boxes) > 0:
                xyxy = result.boxes.xyxy.cpu().numpy()
                confs = result.boxes.conf.cpu().numpy()
                classes = result.boxes.cls.cpu().numpy()

                for (x1, y1, x2, y2), score, cls_idx in zip(xyxy, confs, classes):
                    cls_id = int(cls_idx)
                    name = get_class_name(result, cls_id)
                    detected_names.append(name)
                    boxes_out.append(
                        {
                            "x1": float(x1),
                            "y1": float(y1),
                            "x2": float(x2),
                            "y2": float(y2),
                            "conf": float(score),
                            "name": name,
                        }
                    )

        if detected_names:
            counts = Counter(detected_names)
            summary_parts = [f"{count} {name}" for name, count in counts.items()]
            summary_text = "Phát hiện: " + ", ".join(summary_parts)
        else:
            summary_text = "Không phát hiện thấy vật thể nào."

        logger.info("Kết quả detect-lite: %s", summary_text)
        logger.info("Lite: boxes=%s | w=%s h=%s", len(boxes_out), w, h)
        for i, b in enumerate(boxes_out[:5], start=1):
            logger.info(
                "BOX#%s name=%s conf=%.2f xyxy=(%.1f,%.1f,%.1f,%.1f)",
                i,
                b["name"],
                b["conf"],
                b["x1"],
                b["y1"],
                b["x2"],
                b["y2"],
            )

        return {
            "summary": summary_text,
            "boxes": boxes_out,
            "w": w,
            "h": h,
        }
    except HTTPException:
        raise
    except Exception as exc:
        logger.error(f"Lỗi xử lý /detect-lite: {exc}")
        raise HTTPException(status_code=500, detail=f"Lỗi Server: {exc}")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app4_oldstyle_cloudflare_merge:app", host="0.0.0.0", port=PORT_NUMBER, reload=False)
