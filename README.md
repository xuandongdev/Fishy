# Fishy

Fishy là hệ thống hỗ trợ tra cứu luật giao thông và nhận diện biển báo giao thông trong cùng một ứng dụng. Repository này gồm một app Flutter đa nền tảng, một backend RAG truy xuất và sinh câu trả lời từ dữ liệu luật trên Supabase, một backend YOLO để nhận diện biển báo từ ảnh và camera realtime, cùng bộ script đánh giá chất lượng RAG.

## Tổng quan

Fishy giải quyết ba bài toán chính:

- Tra cứu luật giao thông bằng ngôn ngữ tự nhiên.
- Nhận diện biển báo giao thông từ ảnh tải lên, ảnh chụp và camera realtime.
- Quản trị dữ liệu văn bản pháp luật, nội dung chi tiết và embedding phục vụ semantic retrieval.

Hệ thống hướng tới hai nhóm người dùng:

- Người dùng cuối cần hỏi đáp nhanh về lỗi vi phạm, mức phạt, quy định giao thông.
- Quản trị viên cần cập nhật dữ liệu luật, quản lý nội dung phân cấp và đồng bộ vector tìm kiếm.

## Kiến trúc hệ thống

```text
Flutter App
  |- Supabase
  |   |- Auth
  |   |- Legal content tables
  |   |- Chat history
  |   `- app_config (rag_url, yolo_url)
  |
  |- RAG API
  |   |- SentenceTransformer (multilingual-e5-large)
  |   |- LangChain retriever
  |   |- OpenAI chat model
  |   `- Supabase RPC: match_legal_docs_v2
  |
  `- YOLO API
      |- Ultralytics YOLO
      |- Image detection
      `- Realtime camera detection
```

## Flow vận hành

### 1. Khởi động ứng dụng

- `lib/main.dart` load `.env`, khởi tạo Supabase, local notifications và các `Provider`.
- `lib/Services/ChatService.dart` đọc `rag_url` và `yolo_url` từ bảng `app_config`.
- Nếu chưa có URL public, app fallback về local:
  - Android emulator: `10.0.2.2`
  - Desktop/Web: `127.0.0.1`

### 2. Đăng nhập và phân quyền

- App dùng Supabase Auth cho đăng nhập, đăng ký và đăng xuất.
- Hồ sơ người dùng được đọc từ bảng `nguoidung`.
- Người dùng có `mavaitro == 1` sẽ thấy các chức năng quản trị từ menu drawer.

### 3. Hỏi đáp luật giao thông

- Người dùng nhập câu hỏi tại `ChatScreen`.
- `ChatViewModel` giữ lại một đoạn lịch sử hội thoại gần nhất để gửi kèm truy vấn.
- App gọi `POST /chat` tới backend RAG.
- Backend `server/RAG/langchain2.py`:
  - nhúng câu hỏi bằng `intfloat/multilingual-e5-large`,
  - trích số km nếu câu hỏi liên quan tốc độ,
  - gọi RPC `match_legal_docs_v2` trên Supabase,
  - dựng prompt từ context pháp luật,
  - sinh câu trả lời bằng `gpt-4o-mini`.
- Cặp hỏi/đáp sau đó được lưu vào `lich_su_tro_chuyen`.

### 4. Nhận diện ảnh biển báo

- Người dùng có thể chọn ảnh từ gallery hoặc chụp ảnh mới.
- App gửi ảnh tới `POST /detect-lite`.
- Backend YOLO trả về:
  - `summary`,
  - `boxes`,
  - `w`, `h` của ảnh gốc.
- Flutter dùng `BBoxPainter` để vẽ lại bounding boxes trên ảnh.

### 5. Nhận diện realtime

- `RealtimeDetectScreen` mở camera sau và stream frame liên tục.
- Frame được convert sang JPEG, throttle khoảng 600ms mỗi lần gửi.
- Nếu phát hiện biển báo:
  - kết quả được đẩy vào chat,
  - hiển thị toast trên màn hình,
  - bắn local notification cảnh báo.

### 6. Quản trị dữ liệu luật

- `AddLawScreen` thêm metadata văn bản vào `vanbanphapluat`.
- `AddLawContentScreen` thêm nội dung vào `noidung` theo cấu trúc:
  - `CHUONG`
  - `MUC`
  - `DIEU`
  - `KHOAN`
  - `DIEM`
- Sau khi thêm nội dung, app có thể:
  - sinh embedding ngữ cảnh chính bằng `EmbeddingService`,
  - sinh thêm `rela_embed` nếu có từ khóa liên quan.
- `LawManageScreen` hỗ trợ lọc, sửa, đổi trạng thái văn bản và đồng bộ embedding hàng loạt.

## Thành phần chính trong repository

### Ứng dụng Flutter

- `lib/main.dart`: entrypoint ứng dụng.
- `lib/Views/`: các màn hình chính.
- `lib/ViewModels/`: logic state management với `provider`.
- `lib/Services/`: tích hợp Supabase, chat, embedding, notification.
- `lib/Models/`: model dữ liệu.
- `lib/Widgets/`: app bar, typing indicator, painter vẽ bounding box.

### Backend RAG

- `server/RAG/langchain2.py`: entrypoint backend RAG hiện đang khớp với app Flutter.
- `server/RAG/danh_gia_rag.py`: pipeline đánh giá có resume cho retrieval và generation.
- `server/RAG/evaluate_rag.py`: script đánh giá cũ hơn.
- `server/RAG/eval.jsonl`, `server/RAG/danh_gia_rag.jsonl`, `server/RAG/eval_set_manifest.md`: bộ dữ liệu đánh giá.

### Backend YOLO

- `server/Yolo/app.py`: entrypoint YOLO hiện đang khớp với app Flutter.
- `server/Yolo/app2.py`, `server/Yolo/app3.py`: các biến thể thử nghiệm của server YOLO.
- `server/Yolo/model/`, `best.pt`, `best11s.pt`, `v8h.pt`: trọng số mô hình.
- `server/Yolo/classes_*.txt`, `class_*.txt`: mapping class và tên biển báo.

### Thành phần bổ sung

- `lib/AdminDashboard/`: một nhánh giao diện quản trị cũ/riêng cho web.
- `server/run.txt`: lệnh chạy nhanh cho backend.
- `assets/`: logo và tài nguyên hiển thị.

## Công nghệ sử dụng

- Flutter
- Provider
- Supabase Auth / Database / RPC
- FastAPI
- LangChain
- OpenAI API
- SentenceTransformers
- Hugging Face Inference API
- Ultralytics YOLO
- RAGAS
- Ollama

## Phụ thuộc dữ liệu Supabase

Các bảng và RPC đang được dùng trực tiếp trong code:

- `nguoidung`
- `lich_su_tro_chuyen`
- `vanbanphapluat`
- `noidung`
- `coquanbanhanh`
- `loaivanban`
- `app_config`
- `match_legal_docs_v2`

## Cấu hình môi trường

### Root `.env`

Được Flutter load như asset. Nên chỉ chứa biến an toàn phía client.

Tối thiểu theo flow hiện tại:

- `SUPABASE_URL`
- `SUPABASE_ANON_KEY`
- `HF_API_KEY` nếu dùng tính năng sinh embedding ngay từ app

Biến có thể tồn tại do quá trình phát triển trước đó:

- `GEMINI_API_KEY`

Khuyến nghị: không để `SUPABASE_SERVICE_ROLE_KEY` trong `.env` của Flutter app.

### `server/RAG/.env`

Bắt buộc theo mã hiện tại:

- `SUPABASE_URL`
- `SUPABASE_SERVICE_ROLE_KEY`
- `OPENAI_API_KEY`

Biến có thể đang được dùng trong môi trường local hoặc script mở rộng:

- `SUPABASE_ANON_KEY`
- `OPENROUTER_API_KEY`
- `HF_API_KEY`
- `GEMINI_API_KEY`

### `server/Yolo/.env`

Bắt buộc theo mã hiện tại:

- `SUPABASE_URL`
- `SUPABASE_SERVICE_ROLE_KEY`

Lưu ý: các file `.env` đều đang bị `.gitignore`, nên khi chuyển máy cần tự tạo lại.

## Cách chạy local

### 1. Chạy RAG backend

```bash
cd server/RAG
python -m uvicorn langchain2:app --host 0.0.0.0 --port 8000 --reload
```

### 2. Chạy YOLO backend

```bash
cd server/Yolo
pip install -r requirements.txt
python -m uvicorn app:app --host 0.0.0.0 --port 8001 --reload
```

### 3. Chạy ứng dụng Flutter

```bash
flutter pub get
flutter run
```

## Đánh giá chất lượng RAG

Chạy từng bước:

```bash
cd server/RAG
python danh_gia_rag.py --mode generate_only --eval-file danh_gia_rag.jsonl
python danh_gia_rag.py --mode judge_only
python danh_gia_rag.py --mode build_report
```

Hoặc chạy trọn pipeline:

```bash
cd server/RAG
python danh_gia_rag.py --mode full --eval-file danh_gia_rag.jsonl
```

Lưu ý:

- `langchain2.py` dùng OpenAI cho trả lời chính.
- `danh_gia_rag.py` dùng Ollama/Qwen cho phase generate và RAGAS/OpenAI cho phase judge.
- Vì vậy Ollama không phải là phụ thuộc bắt buộc để chạy ứng dụng, nhưng là phụ thuộc của pipeline đánh giá hiện tại.

## Tóm tắt

Fishy là codebase kết hợp legal RAG và computer vision cho bài toán giao thông. Người dùng có thể hỏi luật, xem lịch sử trao đổi, tải ảnh hoặc dùng camera để nhận diện biển báo; quản trị viên có thể quản lý dữ liệu luật, cập nhật nội dung và đồng bộ embedding trong cùng một hệ thống.
