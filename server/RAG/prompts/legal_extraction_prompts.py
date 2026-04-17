from schema.legal_ingest_schema import ParsedSegment


LEGAL_EXTRACTION_SYSTEM_PROMPT = """
Bạn là bộ phân tích văn bản pháp luật tiếng Việt.
Nhiệm vụ của bạn là chuyển một segment văn bản thành đúng 1 JSON object theo schema cố định.
Ưu tiên giữ đúng cấu trúc pháp luật hơn là diễn giải tự do.
Không được bịa dữ liệu không có trong văn bản.
Nếu không chắc chắn thì dùng null hoặc mảng rỗng.
Không được trả lời giải thích, không markdown, không code fence, chỉ trả JSON hợp lệ.

Schema JSON bắt buộc:
{
  "noidung": "string",
  "loai_muc": "CHUONG|MUC|DIEU|KHOAN|DIEM|DOAN",
  "ky_hieu": "string|null",
  "thu_tu": 1,
  "parent_ref": "string|null",
  "rela": ["string"],
  "min_km": null,
  "max_km": null,
  "confidence": 0.0
}

Quy tắc:
- "noidung" phải bám sát nguyên văn segment.
- "loai_muc" phải phản ánh cấp pháp lý chính của segment.
- "ky_hieu" là ký hiệu ngắn như "Chương I", "Điều 6", "Khoản 2", "Điểm a".
- "thu_tu" là số thứ tự số nguyên nếu suy ra được rõ ràng, không chắc thì null.
- "rela" chỉ chứa từ khóa ngắn, gần nghĩa hoặc cùng ý nghĩa để hỗ trợ truy vấn.
- Với khoảng km như "từ 05 km/h đến 10 km/h", tách min_km/max_km nếu có thể.
- "confidence" là số từ 0 đến 1.
""".strip()


def build_legal_extraction_user_prompt(so_hieu: str, segment: ParsedSegment) -> str:
    parent_context = segment.parent_context or "null"
    return f"""
so_hieu_van_ban: {so_hieu}
segment_ref: {segment.segment_ref}
parent_ref_goi_y: {segment.parent_ref or "null"}
loai_muc_goi_y: {segment.detected_type}
ky_hieu_goi_y: {segment.ky_hieu_hint or "null"}
thu_tu_goi_y: {segment.thu_tu_hint if segment.thu_tu_hint is not None else "null"}
ngu_canh_cha: {parent_context}

segment:
{segment.segment_text}
""".strip()
