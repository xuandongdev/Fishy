from sentence_transformers import SentenceTransformer

# 1. Load model (phải giống model server)
print("Đang load model...")
model = SentenceTransformer("intfloat/multilingual-e5-large")

# 2. Câu hỏi test
question = "vượt quá 5km/h bị phạt bao nhiêu"
print(f"Đang tạo vector cho câu hỏi: {question}...")

# 3. Tạo vector
vector = model.encode("query: " + question).tolist()
vector_str = str(vector) 

# 4. Lệnh SQL đã sửa đúng tên cột
sql_query = f"""
SELECT 
    sothutund,       -- Đã sửa từ r_id
    noidung,         -- Đã sửa từ r_content
    sohieu,          -- Đã sửa từ r_sohieu
    similarity,      -- Đã sửa từ sim
    hierarchy_path   -- Đã sửa từ h_path
FROM match_legal_docs(
    '{vector_str}', 
    0.5, 
    5
);
"""

print("-" * 50)
print("COPY VÀO SUPABASE SQL EDITOR:")
print("-" * 50)
print(sql_query)
print("-" * 50)