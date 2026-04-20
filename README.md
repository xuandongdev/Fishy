# Fishy

Fishy là ứng dụng hỗ trợ tra cứu pháp luật giao thông và nhận diện biển báo giao thông. Hệ thống được xây dựng gồm 3 phần chính:

- Flutter app cho người dùng và quản trị viên
- Backend RAG/FastAPI cho hỏi đáp pháp lý
- Backend YOLO để nhận diện ảnh biển báo

Mục tiêu của hệ thống là giúp quản lý văn bản pháp luật, thêm nội dung văn bản theo hai cách khác nhau, và hỗ trợ người dùng tra cứu quy định giao thông một cách dễ hiểu, có căn cứ.

![Demo GIF](./assets/okdemo.gif)

<p align="center">
  <img src="./assets/1.jpg" width="24%" />
  <img src="./assets/2.jpg" width="24%" />
  <img src="./assets/3.jpg" width="24%" />
  <img src="./assets/4.jpg" width="24%" />
</p>

---

## Hệ thống hiện đang làm được gì

Fishy hiện đã triển khai các chức năng chính sau:

### 1. Quản lý văn bản pháp luật
Quản trị viên có thể:

- thêm mới văn bản pháp luật
- cập nhật thông tin văn bản
- quản lý trạng thái như còn hiệu lực hoặc hết hiệu lực
- xem danh sách văn bản đã lưu
- xem chi tiết nội dung văn bản

Thông tin văn bản được lưu ở bảng `vanbanphapluat`.

### 2. Thêm nội dung văn bản theo hai cách
Sau khi đã tạo văn bản pháp luật, quản trị viên có thể thêm nội dung bằng hai hướng:

- **Nhập tay**: dùng để thêm thủ công các Chương, Mục, Điều, Khoản, Điểm vào bảng `noidung`
- **Upload file**: dùng để ingest PDF, DOCX hoặc TXT, parser sẽ tách theo cấu trúc pháp lý và lưu vào bảng `noidung2`

Như vậy:

- `noidung` là nội dung nhập tay
- `noidung2` là nội dung tách tự động từ file

### 3. Hỏi đáp pháp luật bằng RAG
Người dùng có thể đặt câu hỏi pháp luật giao thông trong app. Hệ thống sẽ:

- phân loại câu hỏi là legal hay general
- nếu là câu hỏi pháp lý thì đưa vào legal RAG
- truy xuất dữ liệu từ DB
- rerank kết quả
- sinh câu trả lời cuối cùng bằng mô hình ngôn ngữ

Mục tiêu là trả lời có căn cứ, không trả lời pháp lý theo trí nhớ chung.

### 4. Nhận diện biển báo giao thông
Fishy còn có chức năng nhận diện biển báo bằng YOLO, hỗ trợ:

- gửi ảnh lên backend
- nhận ảnh đã annotate
- nhận danh sách boxes và nhãn
- có thể dùng local hoặc backend tùy flow

---

## Cách hệ thống hoạt động

## 1. Tầng dữ liệu

Hệ thống pháp lý hiện tổ chức theo 3 bảng chính:

### `vanbanphapluat`
Đây là bảng cha, lưu metadata của văn bản:

- số hiệu văn bản
- tên văn bản
- ngày ký
- ngày hiệu lực
- trạng thái
- cơ quan ban hành
- loại văn bản

Trạng thái như còn hiệu lực hoặc hết hiệu lực được quản lý ở bảng này.

### `noidung`
Đây là bảng con dùng cho nội dung **nhập tay**.

Dữ liệu ở đây được thêm theo cây pháp lý như:

- Chương
- Mục
- Điều
- Khoản
- Điểm

Bảng này phù hợp cho các nội dung đã được chuẩn hóa thủ công.

### `noidung2`
Đây là bảng con dùng cho nội dung **ingest từ file**.

Khi upload file, backend sẽ:

- đọc file
- parse theo cấu trúc pháp lý
- tách thành các node phù hợp
- sinh embedding
- lưu từng chunk vào `noidung2`

Bảng này giúp ingest các văn bản lớn nhanh hơn, không cần nhập tay từng điều khoản.

---

## 2. Tầng ứng dụng Flutter

App Flutter hiện có các nhóm màn hình chính:

### `AddLawScreen`
Dùng để tạo mới văn bản pháp luật.

Ở màn này, quản trị viên chỉ nhập metadata văn bản như:

- số hiệu
- tên văn bản
- trạng thái
- ngày ký
- ngày hiệu lực
- cơ quan ban hành
- loại văn bản

Màn này **không còn là nơi upload file**.

### `AddLawContentScreen`
Dùng để thêm nội dung cho văn bản đã có sẵn.

Màn này có 2 luồng:

- nhập tay vào `noidung`
- upload file để ingest vào `noidung2`

Đây là màn trung tâm cho việc thêm nội dung văn bản.

### `LawManageScreen`
Dùng để quản lý danh sách văn bản pháp luật.

Có thể:

- xem danh sách
- lọc
- tìm kiếm
- sửa metadata
- mở màn thêm nội dung

### `LawDetailScreen`
Dùng để xem chi tiết văn bản.

Màn này hiển thị:

- thông tin metadata từ `vanbanphapluat`
- nội dung liên quan từ `noidung`
- nội dung ingest từ `noidung2`

### Chat pháp lý
Người dùng gửi câu hỏi pháp luật, app gọi backend RAG để lấy câu trả lời có căn cứ.

### Nhận diện biển báo
Người dùng chọn ảnh hoặc camera, app gọi YOLO để nhận diện biển báo.

---

## 3. Tầng backend RAG

Backend RAG dùng FastAPI và đóng vai trò xử lý toàn bộ logic legal chat.

Entrypoint chính:

- `server/RAG/trusted_rag_app.py`

Các thành phần quan trọng:

- `router/chat_router.py`
- `langchain_adapter.py`
- `services/retrieval_service.py`
- `services/answer_service.py`
- `services/document_parser_service.py`
- `services/global_doc_service.py`
- `services/noidung2_ingest_service.py`

### Legal chat hoạt động như sau

1. Flutter gửi câu hỏi tới `POST /chat`
2. `LangChainAdapter` phân loại câu hỏi
3. Nếu là legal:
   - chuẩn hóa câu hỏi
   - sinh câu hỏi hiệu lực (`effective_question`)
   - tạo embedding
4. `RetrievalService` truy xuất dữ liệu từ DB
5. Hệ thống ưu tiên dùng dữ liệu phù hợp từ `noidung`
6. Nếu `noidung` không đủ mạnh hoặc không đủ chi tiết thì dùng `noidung2`
7. Candidate results được rerank
8. `AnswerService` sinh câu trả lời cuối
9. App nhận câu trả lời cùng nguồn tham khảo

### Điểm quan trọng của legal flow mới

Legal flow hiện tại **không còn dùng Qdrant**.

Thay vào đó, hệ thống dùng trực tiếp dữ liệu trong Supabase/Postgres:

- `vanbanphapluat`
- `noidung`
- `noidung2`

Điều này giúp legal flow dễ kiểm soát hơn, rõ ràng hơn, và bám sát dữ liệu thật trong hệ thống.

---

## 4. Tầng ingest file

Khi quản trị viên upload file pháp luật, flow hoạt động như sau:

1. Người dùng đã có sẵn `sohieuvanban` trong `vanbanphapluat`
2. Chọn file tại `AddLawContentScreen`
3. App gọi endpoint upload file
4. Backend kiểm tra:
   - có file hay không
   - có `so_hieu` hay không
   - `so_hieu` đó có tồn tại trong `vanbanphapluat` hay không
5. Nếu hợp lệ:
   - parse file
   - nhận diện cấu trúc pháp lý
   - sinh chunk
   - lưu vào `noidung2`

### Nguyên tắc ingest hiện tại

- không ingest nếu chưa có văn bản cha trong `vanbanphapluat`
- `noidung2` chỉ dành cho file upload
- không dùng `AddLawScreen` để upload file trực tiếp nữa

---

## Các flow chính của hệ thống

## Flow 1: Tạo văn bản mới
1. Quản trị viên mở `AddLawScreen`
2. Nhập metadata văn bản
3. Lưu vào `vanbanphapluat`
4. Chuyển sang `AddLawContentScreen`

## Flow 2: Thêm nội dung thủ công
1. Chọn văn bản cần thêm nội dung
2. Chọn vị trí trong cây pháp lý
3. Nhập nội dung thủ công
4. Lưu vào `noidung`

## Flow 3: Thêm nội dung bằng file
1. Chọn văn bản đã có `sohieuvanban`
2. Chọn file PDF/DOCX/TXT
3. Gửi file sang backend
4. Backend parse và ingest
5. Lưu chunk vào `noidung2`

## Flow 4: Quản lý và xem chi tiết văn bản
1. Quản trị viên vào `LawManageScreen`
2. Chọn một văn bản
3. Xem metadata
4. Xem nội dung từ `noidung` và `noidung2`
5. Chỉnh sửa khi cần

## Flow 5: Chat pháp lý
1. Người dùng nhập câu hỏi
2. Backend xác định đây có phải câu hỏi legal không
3. Nếu đúng:
   - truy xuất dữ liệu liên quan
   - rerank
   - sinh câu trả lời cuối
4. Trả về câu trả lời cùng nguồn tham khảo

## Flow 6: Nhận diện biển báo
1. Người dùng chọn ảnh
2. App gửi ảnh đến YOLO backend
3. Backend detect
4. Trả về nhãn, boxes, hoặc ảnh annotate