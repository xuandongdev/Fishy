# Fishy

Fishy là ứng dụng hỗ trợ tra cứu pháp luật giao thông và nhận diện biển báo. Repo hiện tại gồm 3 phần chính:

- Flutter app cho người dùng cuối và quản trị viên
- Backend RAG/FastAPI cho hỏi đáp pháp lý
- Backend YOLO để nhận diện ảnh

![Demo GIF](./assets/okdemo.gif)

<p align="center">
  <img src="./assets/1.jpg" width="24%" />
  <img src="./assets/2.jpg" width="24%" />
  <img src="./assets/3.jpg" width="24%" />
  <img src="./assets/4.jpg" width="24%" />
</p>

## Tổng quan kiến trúc

```text
Flutter App
  |- Supabase
  |   |- Auth
  |   |- app_config
  |   |- nguoidung
  |   |- lich_su_tro_chuyen
  |   |- vanbanphapluat
  |   |- noidung
  |
  |- RAG API (:8000)
  |   |- route legal/general
  |   |- Qdrant session docs
  |   |- Qdrant global docs
  |   |- Supabase RPC match_legal_docs_v4
  |   |- CrossEncoder rerank
  |   `- OpenAI answer generation
  |
  |- YOLO API (:8001)
  |   |- /detect
  |   `- /detect-lite
  |
  `- Local YOLO on-device
```

## Flow hiện tại

### 1. Chat pháp lý

Entrypoint backend hiện tại là:

- `server/RAG/trusted_rag_app.py`
- router chat: `server/RAG/router/chat_router.py`
- điều phối route: `server/RAG/langchain_adapter.py`

Flow đang chạy:

1. Flutter gửi câu hỏi tới `POST /chat` hoặc `POST /api/chat/ask`
2. `LangChainAdapter` phân loại:
   - `legal_rag`
   - `general_chat`
3. Nếu là legal:
   - build `effective_question` từ câu hiện tại + history
   - sinh query embedding bằng `intfloat/multilingual-e5-large`
4. Retrieval ưu tiên theo thứ tự:
   - Qdrant global docs
   - nếu chưa đủ thì Supabase RPC `match_legal_docs_v4`
5. Candidate hits được rerank bằng `BAAI/bge-reranker-v2-m3`
6. `AnswerService` sinh câu trả lời cuối bằng OpenAI
7. Nguồn trả về cho user được format theo kiểu pháp lý thân thiện, không lộ nhãn backend nội bộ

### 2. Global docs trong Qdrant

Global docs hiện là kho văn bản admin upload để phục vụ retrieval chung.

Đặc điểm hiện tại:

- collection mặc định: `global_docs`
- embedding model: `intfloat/multilingual-e5-large`
- vector size: `1024`
- query prefix: `query: `
- passage prefix: `passage: `
- distance: `cosine`

Payload global docs hiện chỉ giữ:

- nội dung gốc của tài liệu
- metadata văn bản/pháp lý

Không còn dùng:

- `canonical_action`
- `rela`
- `rela_text`
- `rela_embed`
- `rela_source`
- `rela_reviewed`

Chunking global docs hiện bám cấu trúc pháp lý:

- `Điều` là đơn vị chính
- nếu `Điều` dài thì tách theo `Khoản`
- nếu cần thì tách tiếp theo `Điểm`
- nếu có mục con kiểu `1.`, `2.`, `3.` ở đầu dòng thì coi như đơn vị con hợp lệ
- chỉ token split khi đơn vị con vẫn quá dài

Các endpoint liên quan:

- `POST /upload-global-doc`
- `POST /global-docs/{file_id}/activate`
- `POST /global-docs/{file_id}/deactivate`
- `DELETE /global-docs/{file_id}`

### 3. Session docs trong Qdrant

Session docs là tài liệu người dùng upload cho riêng một phiên chat.

Flow:

1. User upload file qua `POST /upload-session-doc`
2. File được parse text
3. Chunk theo section/text
4. Upsert vào Qdrant collection `session_docs`
5. Dùng cho retrieval trong phạm vi session đó

Lưu ý:

- hiện retrieval chính vẫn ưu tiên global docs
- session docs đã có service và endpoint upload
- TTL session docs được đọc từ `.env`

### 4. Nguồn hiển thị cho user

Nguồn trong answer hiện đã được thống nhất theo format pháp lý, ví dụ:

- `Nguồn: Khoản 2, Điều 2, LUẬT TRẬT TỰ, AN TOÀN GIAO THÔNG ĐƯỜNG BỘ (36/2024/QH15)`
- `Nguồn: Điểm a, Khoản 6, Điều 18, NGHỊ ĐỊNH 168/2024/NĐ-CP (168/2024/NĐ-CP)`

Không còn hiển thị các nhãn backend như:

- `legal_db`
- `admin_upload`
- `source_type`

Formatter chung nằm ở:

- `server/RAG/services/source_formatter.py`

### 5. YOLO backend

Entrypoint:

- `server/Yolo/app.py`

Endpoint:

- `POST /detect`
- `POST /detect-lite`

Flow:

1. Server load model YOLO từ `server/Yolo/model/best.pt`
2. Load nhãn tiếng Việt từ `server/Yolo/classes_vie.txt`
3. Nhận ảnh upload
4. Chạy detect
5. Trả về:
   - summary
   - ảnh annotate base64 với `/detect`
   - boxes + width/height với `/detect-lite`

## Cấu trúc thư mục đáng chú ý

### Flutter app

- `lib/main.dart`: entrypoint app
- `lib/Views/`: các màn hình
- `lib/ViewModels/`: state management
- `lib/Services/ChatService.dart`: gọi chat API
- `lib/Services/LegalIngestService.dart`: gọi legal ingest API
- `lib/Services/LocalYoloService.dart`: nhận diện local trên mobile

### RAG backend

- `server/RAG/trusted_rag_app.py`: app FastAPI chính cho RAG
- `server/RAG/router/chat_router.py`: các route chat và upload docs
- `server/RAG/langchain_adapter.py`: route legal/general, orchestration
- `server/RAG/services/retrieval_service.py`: retrieval pipeline
- `server/RAG/services/qdrant_service.py`: session/global docs trên Qdrant
- `server/RAG/services/global_doc_service.py`: ingest global docs
- `server/RAG/services/session_doc_service.py`: ingest session docs
- `server/RAG/services/document_parser_service.py`: parse section/cấu trúc pháp lý
- `server/RAG/services/answer_service.py`: sinh answer cuối
- `server/RAG/services/source_formatter.py`: format nguồn hiển thị
### YOLO backend

- `server/Yolo/app.py`
- `server/Yolo/model/best.pt`
- `server/Yolo/classes_vie.txt`

## Biến môi trường chính

### RAG backend

`server/RAG/.env`

Các biến quan trọng:

- `SUPABASE_URL`
- `SUPABASE_SERVICE_ROLE_KEY`
- `OPENAI_API_KEY`
- `HF_EMBED_MODEL`
- `ANSWER_MODEL`
- `QDRANT_URL`
- `QDRANT_API_KEY`
- `QDRANT_COLLECTION_SESSION_DOCS`
- `QDRANT_COLLECTION_GLOBAL_DOCS`
- `RAG_PORT`
- `RAG_LEGAL_SCORE_THRESHOLD`
- `RAG_MIN_LEGAL_EVIDENCE`
- `SESSION_DOC_TOP_K`
- `SESSION_DOC_SCORE_THRESHOLD`
- `SESSION_DOC_TTL_HOURS`
- `SESSION_DOC_CHUNK_SIZE`
- `SESSION_DOC_CHUNK_OVERLAP`
- `GLOBAL_DOC_TOP_K`
- `GLOBAL_DOC_SCORE_THRESHOLD`
- `RERANK_MODEL_NAME`
- `RERANK_CANDIDATE_COUNT`
- `RERANK_FINAL_TOP_K`

Mặc định đáng chú ý:

- embedding model: `intfloat/multilingual-e5-large`
- answer model: `gpt-4o-mini`
- reranker: `BAAI/bge-reranker-v2-m3`

## Cách chạy local

### 1. Flutter

```bash
flutter pub get
flutter run
```

### 2. Cài Python dependency

RAG:

```bash
cd server/RAG
pip install -r requirements.txt
```

YOLO:

```bash
cd server/Yolo
pip install -r requirements.txt
```

### 3. Chạy RAG API

```bash
cd server/RAG
uvicorn trusted_rag_app:app --host 0.0.0.0 --port 8000 --reload
```

### 4. Chạy YOLO API

```bash
cd server/Yolo
uvicorn app:app --host 0.0.0.0 --port 8001 --reload
```

## Endpoint chính

### Chat / retrieval

- `POST /chat`
- `POST /api/chat/ask`
- `GET /health`

### Document upload cho RAG

- `POST /upload-session-doc`
- `POST /upload-global-doc`
- `POST /global-docs/{file_id}/activate`
- `POST /global-docs/{file_id}/deactivate`
- `DELETE /global-docs/{file_id}`

### YOLO

- `POST /detect`
- `POST /detect-lite`

## Ghi chú triển khai

- `trusted_rag_app.py`, `legal_ingest_app.py` và `server/Yolo/app.py` đều có logic mở Cloudflare tunnel và cập nhật URL về `app_config` trong Supabase
- Flutter app lấy `rag_url`, `legal_ingest_url`, `yolo_url` từ `app_config`
- Nếu không có Qdrant hoặc dữ liệu global docs chưa đủ, hệ thống sẽ fallback về `match_legal_docs_v4`
## Tóm tắt ngắn

Flow hiện tại của Fishy là:

1. Ưu tiên trả lời từ global docs/session docs trong Qdrant khi có dữ liệu phù hợp
2. Nếu chưa đủ thì fallback sang legal DB qua `match_legal_docs_v4`
3. Tất cả được rerank rồi mới sinh answer cuối
4. Nguồn hiển thị cho user theo format pháp lý thân thiện, không lộ nhãn debug/backend
