import cv2
import numpy as np
import base64
import os
import sys
import logging
import subprocess
import re
import threading
from datetime import datetime, timezone
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from ultralytics import YOLO
from collections import Counter
from contextlib import asynccontextmanager
from starlette.datastructures import UploadFile as StarletteUploadFile
from supabase import create_client, Client
from dotenv import load_dotenv

# ======================================================
# 1. CẤU HÌNH HỆ THỐNG
# ======================================================
load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")

# Cấu hình đường dẫn Model
MODEL_PATH = r'D:/Fishy/server/Yolo/best11s.pt' 
PORT_NUMBER = 8001  # Port của Server YOLO

# Cấu hình Logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)

# Biến toàn cục
model = None
supabase: Client = None

# ======================================================
# 2. HÀM TỰ ĐỘNG CLOUDFLARE (Cập nhật yolo_url)
# ======================================================
def start_cloudflare_tunnel(port, supabase_client):
    """
    Chạy cloudflared tunnel ngầm, bắt lấy link và up lên Supabase vào key 'yolo_url'
    """
    cmd = [r"D:/Fishy/server/cloudflared.exe", "tunnel", "--url", f"http://127.0.0.1:{port}"]

    logger.info(f"[Cloudflare] Đang khởi động Tunnel cho YOLO (Port {port})...")
    
    try:
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            universal_newlines=True,
            encoding='utf-8',
            errors='ignore' 
        )

        public_url = None
        url_pattern = re.compile(r'https://[a-zA-Z0-9-]+\.trycloudflare\.com')

        while True:
            line = process.stderr.readline()
            if not line:
                break
            
            match = url_pattern.search(line)
            if match:
                public_url = match.group(0)
                logger.info(f"[Cloudflare] TÌM THẤY LINK YOLO: {public_url}")
                
                try:
                    supabase_client.table("app_config").update({
                        "value": public_url,
                        "updated_at": datetime.now(timezone.utc).isoformat()
                    }).eq("key", "yolo_url").execute() 
                    
                    logger.info("Đã lưu link YOLO lên Supabase thành công!")
                except Exception as e:
                    logger.error(f"Lỗi update Supabase: {e}")
                break 
    except FileNotFoundError:
        logger.critical("LỖI: Không tìm thấy file 'cloudflared'. Hãy tải và cài đặt nó vào System32 hoặc thư mục dự án.")
    except Exception as e:
        logger.error(f"Lỗi Cloudflare Process: {e}")

# ======================================================
# 3. LIFESPAN: QUẢN LÝ VÒNG ĐỜI SERVER
# ======================================================
@asynccontextmanager
async def lifespan(app: FastAPI):
    global model, supabase

    # 1. Kết nối Supabase
    try:
        supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
        logger.info("Kết nối Supabase OK.")
    except Exception as e:
        logger.error(f"Lỗi kết nối Supabase: {e}")

    # 2. Chạy Cloudflare Tunnel
    t = threading.Thread(target=start_cloudflare_tunnel, args=(PORT_NUMBER, supabase))
    t.daemon = True 
    t.start()

    # 3. Load Model YOLO (Tên class tiếng Việt đã lưu sẵn trong model)
    logger.info(f"Đang tải Model từ: {MODEL_PATH}...")
    try:
        model = YOLO(MODEL_PATH)
        logger.info("Load Model thành công.")
    except Exception as e:
        logger.critical(f"Lỗi load model: {e}")

    logger.info(f"SERVER YOLO ĐANG CHẠY TẠI PORT {PORT_NUMBER}")
    yield

app = FastAPI(lifespan=lifespan)

# --- CẤU HÌNH CORS ---
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], 
    allow_credentials=True,
    allow_methods=["*"], 
    allow_headers=["*"], 
)

# ======================================================
# 4. API DETECT
# ======================================================
@app.post("/detect")
async def detect(request: Request):
    global model
    
    if model is None:
        return {"summary": "Lỗi: Model chưa sẵn sàng", "image_base64": None}

    try:
        form = await request.form()
        upload_file = None
        
        for value in form.values():
            if isinstance(value, StarletteUploadFile):
                upload_file = value
                break 
        
        if upload_file is None:
            return {"summary": "Lỗi: Không tìm thấy file ảnh.", "image_base64": None}

        # Đọc ảnh
        contents = await upload_file.read()
        nparr = np.frombuffer(contents, np.uint8)
        img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

        if img is None:
            return {"summary": "Lỗi: File bị hỏng/không phải ảnh.", "image_base64": None}

        # Chạy YOLO
        results = model(img, conf=0.25, verbose=False)
        
        detected_names = []
        annotated_img = img

        for result in results:
            annotated_img = result.plot()
            
            if result.boxes:
                for box in result.boxes:
                    cls_id = int(box.cls[0])
                    # Lấy tên class trực tiếp từ model
                    detected_names.append(result.names[cls_id])

        # Tạo Summary Text
        if detected_names:
            counts = Counter(detected_names)
            summary_parts = [f"{count} {name}" for name, count in counts.items()]
            summary_text = "Phát hiện: " + ", ".join(summary_parts)
        else:
            summary_text = "Không phát hiện thấy vật thể nào."

        logger.info(f"Kết quả: {summary_text}")

        # Encode ảnh kết quả sang Base64
        success, buffer = cv2.imencode('.jpg', annotated_img)
        jpg_as_text = base64.b64encode(buffer).decode('utf-8') if success else None

        return {
            "summary": summary_text,
            "image_base64": jpg_as_text
        }

    except Exception as e:
        logger.error(f"Lỗi xử lý: {e}")
        return {"summary": f"Lỗi Server: {str(e)}", "image_base64": None}
    

@app.post("/detect-lite")
async def detect_lite(request: Request):
    global model

    if model is None:
        return {"summary": "Lỗi: Model chưa sẵn sàng", "boxes": [], "w": 0, "h": 0}

    try:
        form = await request.form()
        upload_file = None
        for value in form.values():
            if isinstance(value, StarletteUploadFile):
                upload_file = value
                break

        if upload_file is None:
            return {"summary": "Lỗi: Không tìm thấy file ảnh.", "boxes": [], "w": 0, "h": 0}

        contents = await upload_file.read()
        nparr = np.frombuffer(contents, np.uint8)
        img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        if img is None:
            return {"summary": "Lỗi: File bị hỏng/không phải ảnh.", "boxes": [], "w": 0, "h": 0}

        h, w = img.shape[:2]

        results = model(img, conf=0.25, verbose=False)

        boxes_out = []
        detected_names = []

        for result in results:
            if result.boxes is not None and len(result.boxes) > 0:
                xyxy = result.boxes.xyxy.cpu().numpy()
                conf = result.boxes.conf.cpu().numpy()
                cls = result.boxes.cls.cpu().numpy()

                for (x1, y1, x2, y2), c, cl in zip(xyxy, conf, cls):
                    cl = int(cl)
                    # Lấy tên class trực tiếp từ model
                    name = result.names[cl]
                    detected_names.append(name)
                    boxes_out.append({
                        "x1": float(x1), "y1": float(y1),
                        "x2": float(x2), "y2": float(y2),
                        "conf": float(c),
                        "name": name
                    })

        if detected_names:
            counts = Counter(detected_names)
            summary_parts = [f"{count} {name}" for name, count in counts.items()]
            summary_text = "Phát hiện: " + ", ".join(summary_parts)
        else:
            summary_text = "Không phát hiện thấy vật thể nào."

        logger.info(f"Kết quả: {summary_text}")
        logger.info(f"Lite: boxes={len(boxes_out)} | w={w} h={h}")

        for i, b in enumerate(boxes_out[:5], start=1):
            logger.info(
                f"BOX#{i} name={b['name']} conf={b['conf']:.2f} "
                f"xyxy=({b['x1']:.1f},{b['y1']:.1f},{b['x2']:.1f},{b['y2']:.1f})"
            )

        return {"summary": summary_text, "boxes": boxes_out, "w": w, "h": h}

    except Exception as e:
        logger.error(f"Lỗi xử lý detect-lite: {e}")
        return {"summary": f"Lỗi Server: {str(e)}", "boxes": [], "w": 0, "h": 0}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=PORT_NUMBER)