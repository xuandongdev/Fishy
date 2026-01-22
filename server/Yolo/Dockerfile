FROM ultralytics/ultralytics:latest

WORKDIR /app

# Cài thư viện cần thiết cho OpenCV
RUN apt-get update && apt-get install -y libgl1 libglib2.0-0

# Copy code
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000

CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]
