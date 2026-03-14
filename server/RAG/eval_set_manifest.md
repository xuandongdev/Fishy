# Bộ dữ liệu đánh giá sinh từ file SQL

- File nguồn: noidung_rows (1).sql
- Tổng số câu hỏi (bản strict): 528
- Tổng số câu hỏi (bản full): 825
- Tổng số `sothutund` tham chiếu: 212

## Gợi ý dùng
- `eval_set_generated_strict.jsonl`: ưu tiên độ chính xác cao hơn, ít paraphrase mạo hiểm hơn.
- `eval_set_generated_full.jsonl`: nhiều câu hỏi hơn, có thêm paraphrase/synonym lấy từ cột `rela`.
- `sothutund_reference.jsonl`: bảng đối chiếu `sothutund` -> `noidung` -> `path`.

## Schema
Mỗi dòng JSONL:
- `query_id`
- `question`
- `gold_ids`
- `ground_truth`

## Ghi chú
- Tôi đã cố tình gắn ngữ cảnh phương tiện (ô tô/xe máy/xe đạp/...) vào câu hỏi ở các nhóm hành vi trùng nội dung giữa nhiều điều, để tránh lệch `sothutund`.
- Các câu hỏi tốc độ có thêm biến thể số cụ thể (ví dụ 8 km/h, 15 km/h, 25 km/h...) dựa trên `min_km`, `max_km` trong SQL.

Bộ file đã tạo

1) evalset_colloquial_320.jsonl
- 320 câu hỏi ngôn ngữ đời thường
- Giữ nguyên gold_ids và ground_truth
- Phủ toàn bộ 212 gold_id hiện có ít nhất 1 lần
- Có trộn cả dạng hỏi "bị lỗi gì" và "có vi phạm không"

2) evalset_600_more_colloquial.jsonl
- 600 câu tổng cộng
- 320 câu đời thường + 280 câu gốc
- Tỷ lệ câu đời thường: 53.3%
- Đã shuffle ngẫu nhiên với seed = 42
- query_id được đánh lại dạng mix_00001 ... mix_00600
