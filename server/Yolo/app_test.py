import logging
import os
import sys
from typing import Dict, Optional, Tuple, List

import cv2
import numpy as np
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import JSONResponse, Response
from ultralytics import YOLO

# ======================================================
# 1. CẤU HÌNH
# ======================================================
MODEL_PATH = r"D:/Fishy/server/Yolo/Models/12mNew.pt"

# 4 file class riêng
CLASS_CODE_PATH: Optional[str] = r"D:/Fishy/server/Yolo/class_code.txt"
CLASS_VIE_PATH: Optional[str] = r"D:/Fishy/server/Yolo/class_vie.txt"
CLASSES_EN_PATH: Optional[str] = r"D:/Fishy/server/Yolo/classes_en.txt"
CLASSES_VIE_PATH: Optional[str] = r"D:/Fishy/server/Yolo/classes_vie.txt"

ENABLE_CLASS_LOADING = True
USE_MODEL_NAMES_IF_AVAILABLE = True

# Bật/tắt từng nguồn class
USE_CLASS_CODE = False
USE_CLASS_VIE = False
USE_CLASSES_EN = True
USE_CLASSES_VIE = True

# Ghép label theo ký tự này
LABEL_SEPARATOR = " - "

DEFAULT_CONF = 0.25
DEFAULT_IMGSZ = 640
PORT_NUMBER = 8001

# ======================================================
# 2. LOGGING
# ======================================================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)

# ======================================================
# 3. BIẾN TOÀN CỤC
# ======================================================
model: Optional[YOLO] = None
classes_dict: Dict[int, str] = {}


# ======================================================
# 4. HÀM HỖ TRỢ LOAD CLASS
# ======================================================
def _read_lines(path: Optional[str]) -> List[str]:
    if not path or not os.path.exists(path):
        return []
    with open(path, "r", encoding="utf-8") as f:
        return [line.strip() for line in f if line.strip()]


def _get_model_names(loaded_model: YOLO) -> Dict[int, str]:
    names: Dict[int, str] = {}
    raw_names = getattr(loaded_model.model, "names", None)

    if isinstance(raw_names, dict):
        names = {int(k): str(v) for k, v in raw_names.items()}
    elif isinstance(raw_names, list):
        names = {i: str(v) for i, v in enumerate(raw_names)}

    return names


def get_enabled_class_sources() -> List[Tuple[str, str]]:
    """
    Trả về danh sách (source_name, path) đang được bật.
    Thứ tự ở đây cũng chính là thứ tự ưu tiên khi ghép.
    """
    sources: List[Tuple[str, str]] = []

    if USE_CLASS_CODE and CLASS_CODE_PATH:
        sources.append(("class_code", CLASS_CODE_PATH))

    if USE_CLASS_VIE and CLASS_VIE_PATH:
        sources.append(("class_vie", CLASS_VIE_PATH))

    if USE_CLASSES_EN and CLASSES_EN_PATH:
        sources.append(("classes_en", CLASSES_EN_PATH))

    if USE_CLASSES_VIE and CLASSES_VIE_PATH:
        sources.append(("classes_vie", CLASSES_VIE_PATH))

    return sources


def build_classes_dict(loaded_model: YOLO) -> Dict[int, str]:
    """
    Logic:
    - Bật 0 path -> fallback model.names
    - Bật 1 path -> dùng path đó
    - Bật 2 path -> ghép 2 path đó
    - Bật >2 path -> cảnh báo và chỉ lấy 2 path đầu tiên theo thứ tự ưu tiên
    """
    if not ENABLE_CLASS_LOADING:
        logger.info("ENABLE_CLASS_LOADING=False -> không override tên class.")
        return {}

    enabled_sources = get_enabled_class_sources()

    if len(enabled_sources) == 0:
        logger.info("Không có file class nào được bật. Fallback sang model.names.")
        if USE_MODEL_NAMES_IF_AVAILABLE:
            model_names = _get_model_names(loaded_model)
            if model_names:
                logger.info("Đã fallback sang model.names: %d lớp", len(model_names))
                return model_names
        logger.warning("Không có nguồn class nào để sử dụng.")
        return {}

    if len(enabled_sources) > 2:
        logger.warning(
            "Bạn đang bật %d nguồn class. Hệ thống chỉ ghép 2 nguồn đầu tiên: %s + %s",
            len(enabled_sources),
            enabled_sources[0][0],
            enabled_sources[1][0],
        )
        enabled_sources = enabled_sources[:2]

    loaded_lists: List[Tuple[str, List[str]]] = []
    for source_name, source_path in enabled_sources:
        lines = _read_lines(source_path)
        if not lines:
            logger.warning("Nguồn %s rỗng hoặc không đọc được: %s", source_name, source_path)
        loaded_lists.append((source_name, lines))

    valid_lists = [(name, arr) for name, arr in loaded_lists if arr]

    if not valid_lists:
        logger.warning("Các file class được bật đều rỗng hoặc lỗi.")
        if USE_MODEL_NAMES_IF_AVAILABLE:
            model_names = _get_model_names(loaded_model)
            if model_names:
                logger.info("Đã fallback sang model.names: %d lớp", len(model_names))
                return model_names
        return {}

    if len(valid_lists) == 1:
        source_name, arr = valid_lists[0]
        names = {i: arr[i] for i in range(len(arr))}
        logger.info("Đã load class từ %s: %d lớp", source_name, len(names))
        return names

    # Có đúng 2 nguồn hợp lệ
    (source_1, arr_1), (source_2, arr_2) = valid_lists[:2]
    size = min(len(arr_1), len(arr_2))

    if len(arr_1) != len(arr_2):
        logger.warning(
            "Hai nguồn %s (%d) và %s (%d) lệch số lớp, dùng min=%d",
            source_1, len(arr_1), source_2, len(arr_2), size
        )

    names: Dict[int, str] = {}
    for i in range(size):
        left = arr_1[i].strip()
        right = arr_2[i].strip()

        if left and right:
            names[i] = f"{left}{LABEL_SEPARATOR}{right}"
        else:
            names[i] = left or right or f"class_{i}"

    logger.info("Đã ghép class từ %s + %s: %d lớp", source_1, source_2, len(names))
    return names


# ======================================================
# 5. HÀM HỖ TRỢ ẢNH / DETECT
# ======================================================
def decode_upload_image(file_bytes: bytes) -> np.ndarray:
    np_arr = np.frombuffer(file_bytes, np.uint8)
    image = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)
    if image is None:
        raise HTTPException(status_code=400, detail="Không đọc được file ảnh")
    return image


def get_label_for_class_id(cls_id: int, result_names: Optional[dict] = None) -> str:
    if classes_dict and cls_id in classes_dict:
        return classes_dict[cls_id]

    if result_names:
        if isinstance(result_names, dict) and cls_id in result_names:
            return str(result_names[cls_id])
        if isinstance(result_names, list) and 0 <= cls_id < len(result_names):
            return str(result_names[cls_id])

    return f"class_{cls_id}"


def run_detection(image: np.ndarray, conf: float, imgsz: int) -> Tuple[dict, np.ndarray]:
    if model is None:
        raise HTTPException(status_code=500, detail="Model chưa được load")

    try:
        results = model.predict(source=image, conf=conf, imgsz=imgsz, verbose=False)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Lỗi predict YOLO: {e}")

    if not results:
        return {
            "summary": "Không có kết quả từ model",
            "summary_text": "Không có kết quả từ model",
            "boxes": [],
            "count": 0,
            "w": int(image.shape[1]),
            "h": int(image.shape[0]),
        }, image

    result = results[0]
    result_names = getattr(result, "names", None)
    detections = []

    if result.boxes is not None:
        for box in result.boxes:
            xyxy = box.xyxy[0].tolist()
            cls_id = int(box.cls[0].item())
            confidence = float(box.conf[0].item())
            label = get_label_for_class_id(cls_id, result_names)

            detections.append(
                {
                    "label": label,
                    "class_id": cls_id,
                    "confidence": round(confidence, 4),
                    "x1": int(xyxy[0]),
                    "y1": int(xyxy[1]),
                    "x2": int(xyxy[2]),
                    "y2": int(xyxy[3]),
                }
            )

    summary = f"Phát hiện {len(detections)} đối tượng"

    return {
        "summary": summary,
        "summary_text": summary,
        "boxes": detections,
        "count": len(detections),
        "w": int(image.shape[1]),
        "h": int(image.shape[0]),
    }, result.plot() if hasattr(result, "plot") else image


# ======================================================
# 6. FASTAPI APP
# ======================================================
app = FastAPI(title="YOLO Postman Test API", version="1.0.0")


@app.on_event("startup")
def on_startup() -> None:
    global model, classes_dict

    if not os.path.exists(MODEL_PATH):
        logger.error("Không tìm thấy model tại: %s", MODEL_PATH)
        return

    logger.info("Đang tải model từ: %s", MODEL_PATH)
    model = YOLO(MODEL_PATH)
    logger.info("Load model thành công")

    classes_dict = build_classes_dict(model)
    if classes_dict:
        logger.info("Preview class[0] = %s", classes_dict.get(0))

    logger.info("API test Postman sẵn sàng tại port %s", PORT_NUMBER)


@app.get("/health")
def health() -> JSONResponse:
    return JSONResponse(
        {
            "status": "ok" if model is not None else "model_not_loaded",
            "model_path": MODEL_PATH,
            "enable_class_loading": ENABLE_CLASS_LOADING,
            "use_class_code": USE_CLASS_CODE,
            "use_class_vie": USE_CLASS_VIE,
            "use_classes_en": USE_CLASSES_EN,
            "use_classes_vie": USE_CLASSES_VIE,
            "enabled_sources": [name for name, _ in get_enabled_class_sources()],
            "class_count": len(classes_dict),
        }
    )


@app.post("/detect-lite")
async def detect_lite(
    file: UploadFile = File(...),
    conf: float = Form(DEFAULT_CONF),
    imgsz: int = Form(DEFAULT_IMGSZ),
) -> JSONResponse:
    if model is None:
        raise HTTPException(status_code=500, detail="Model chưa được load")

    file_bytes = await file.read()
    image = decode_upload_image(file_bytes)
    response_data, _ = run_detection(image, conf=conf, imgsz=imgsz)
    response_data["filename"] = file.filename
    return JSONResponse(response_data)


@app.post("/detect-image")
async def detect_image(
    file: UploadFile = File(...),
    conf: float = Form(DEFAULT_CONF),
    imgsz: int = Form(DEFAULT_IMGSZ),
) -> Response:
    if model is None:
        raise HTTPException(status_code=500, detail="Model chưa được load")

    file_bytes = await file.read()
    image = decode_upload_image(file_bytes)
    _, plotted = run_detection(image, conf=conf, imgsz=imgsz)

    ok, encoded = cv2.imencode(".jpg", plotted)
    if not ok:
        raise HTTPException(status_code=500, detail="Không encode được ảnh kết quả")

    return Response(content=encoded.tobytes(), media_type="image/jpeg")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app_test:app", host="0.0.0.0", port=PORT_NUMBER, reload=False)