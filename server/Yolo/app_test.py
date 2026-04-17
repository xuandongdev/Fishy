import logging
import os
import sys
from typing import Dict, List, Optional, Tuple

import cv2
import numpy as np
from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import JSONResponse, Response
from ultralytics import YOLO

# ======================================================
# 1. CẤU HÌNH - CHỈ CẦN HARD CODE Ở ĐÂY
# ======================================================
MODEL_PATH = r"D:/Fishy/server/Yolo/11s2.pt"

# Hard code tối đa 2 file class.
# - Để None hoặc "" nếu không dùng.
# - Nếu chỉ có CLASS_1_PATH  -> dùng class_1
# - Nếu có cả 2            -> ghép class_1 + class_2 theo từng dòng
# - Nếu cả 2 đều trống     -> fallback sang model.names
CLASS_1_PATH: Optional[str] = r"D:/Fishy/server/Yolo/classes_en.txt"
CLASS_2_PATH: Optional[str] = r"D:/Fishy/server/Yolo/classes_vie.txt"

LABEL_SEPARATOR = " - "
USE_MODEL_NAMES_IF_NO_CLASS_FILE = True
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
def _normalize_path(path: Optional[str]) -> Optional[str]:
    if path is None:
        return None
    path = str(path).strip()
    return path if path else None


def _read_lines(path: Optional[str]) -> List[str]:
    path = _normalize_path(path)
    if not path:
        return []
    if not os.path.exists(path):
        logger.warning("Không tìm thấy file class: %s", path)
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


def get_active_class_paths() -> List[Tuple[str, str]]:
    active: List[Tuple[str, str]] = []
    c1 = _normalize_path(CLASS_1_PATH)
    c2 = _normalize_path(CLASS_2_PATH)

    if c1:
        active.append(("class_1", c1))
    if c2:
        active.append(("class_2", c2))

    return active


def build_classes_dict(loaded_model: YOLO) -> Dict[int, str]:
    active = get_active_class_paths()

    if not active:
        logger.info("Không khai báo CLASS_1_PATH/CLASS_2_PATH -> fallback sang model.names")
        if USE_MODEL_NAMES_IF_NO_CLASS_FILE:
            model_names = _get_model_names(loaded_model)
            if model_names:
                logger.info("Đã load từ model.names: %d lớp", len(model_names))
                return model_names
        logger.warning("Không có nguồn class nào khả dụng")
        return {}

    loaded_lists: List[Tuple[str, List[str], str]] = []
    for alias, path in active:
        lines = _read_lines(path)
        if lines:
            loaded_lists.append((alias, lines, path))
        else:
            logger.warning("File %s không đọc được hoặc rỗng: %s", alias, path)

    if not loaded_lists:
        logger.warning("Các file class đều rỗng/lỗi -> fallback sang model.names")
        if USE_MODEL_NAMES_IF_NO_CLASS_FILE:
            model_names = _get_model_names(loaded_model)
            if model_names:
                logger.info("Đã load từ model.names: %d lớp", len(model_names))
                return model_names
        return {}

    if len(loaded_lists) == 1:
        alias, arr, path = loaded_lists[0]
        names = {i: arr[i] for i in range(len(arr))}
        logger.info("Đã load %d lớp từ %s (%s)", len(names), alias, path)
        return names

    (alias_1, arr_1, path_1), (alias_2, arr_2, path_2) = loaded_lists[:2]
    size = min(len(arr_1), len(arr_2))

    if len(arr_1) != len(arr_2):
        logger.warning(
            "Số dòng class lệch nhau: %s=%d, %s=%d -> dùng min=%d",
            path_1,
            len(arr_1),
            path_2,
            len(arr_2),
            size,
        )

    names: Dict[int, str] = {}
    for i in range(size):
        left = arr_1[i].strip()
        right = arr_2[i].strip()
        if left and right:
            names[i] = f"{left}{LABEL_SEPARATOR}{right}"
        else:
            names[i] = left or right or f"class_{i}"

    logger.info(
        "Đã ghép class từ %s + %s: %d lớp",
        os.path.basename(path_1),
        os.path.basename(path_2),
        len(names),
    )
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
    plotted = result.plot() if hasattr(result, "plot") else image

    return {
        "summary": summary,
        "summary_text": summary,
        "boxes": detections,
        "count": len(detections),
        "w": int(image.shape[1]),
        "h": int(image.shape[0]),
    }, plotted


async def extract_upload_file(request: Request, file: Optional[UploadFile]) -> UploadFile:
    """
    Hỗ trợ cả 2 kiểu field:
    - file  : Postman / chuẩn FastAPI
    - image : app Flutter cũ trong project Fishy/Test2
    """
    if file is not None:
        return file

    form = await request.form()
    for key in ["file", "image"]:
        value = form.get(key)
        if isinstance(value, UploadFile):
            return value

    raise HTTPException(status_code=400, detail="Không tìm thấy file upload (cần field 'file' hoặc 'image')")

# ======================================================
# 6. FASTAPI APP
# ======================================================
app = FastAPI(title="YOLO Hardcode Class API", version="2.0.0")


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
            "class_1_path": _normalize_path(CLASS_1_PATH),
            "class_2_path": _normalize_path(CLASS_2_PATH),
            "active_class_paths": [path for _, path in get_active_class_paths()],
            "class_count": len(classes_dict),
            "preview_class_0": classes_dict.get(0),
        }
    )


@app.post("/detect-lite")
async def detect_lite(
    request: Request,
    file: Optional[UploadFile] = File(None),
    conf: float = Form(DEFAULT_CONF),
    imgsz: int = Form(DEFAULT_IMGSZ),
) -> JSONResponse:
    if model is None:
        raise HTTPException(status_code=500, detail="Model chưa được load")

    upload = await extract_upload_file(request, file)
    file_bytes = await upload.read()
    image = decode_upload_image(file_bytes)
    response_data, _ = run_detection(image, conf=conf, imgsz=imgsz)
    response_data["filename"] = upload.filename
    return JSONResponse(response_data)


@app.post("/detect-image")
async def detect_image(
    request: Request,
    file: Optional[UploadFile] = File(None),
    conf: float = Form(DEFAULT_CONF),
    imgsz: int = Form(DEFAULT_IMGSZ),
) -> Response:
    if model is None:
        raise HTTPException(status_code=500, detail="Model chưa được load")

    upload = await extract_upload_file(request, file)
    file_bytes = await upload.read()
    image = decode_upload_image(file_bytes)
    _, plotted = run_detection(image, conf=conf, imgsz=imgsz)

    ok, encoded = cv2.imencode(".jpg", plotted)
    if not ok:
        raise HTTPException(status_code=500, detail="Không encode được ảnh kết quả")

    return Response(content=encoded.tobytes(), media_type="image/jpeg")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app_test:app", host="0.0.0.0", port=PORT_NUMBER, reload=False)
