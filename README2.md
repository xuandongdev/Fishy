# Fishy

Fishy la ung dung ho tro tra cuu phap luat giao thong va nhan dien bien bao giao thong. He thong hien tai gom 3 phan chinh:

- Flutter app cho nguoi dung va quan tri vien
- Backend RAG/FastAPI cho hoi dap phap ly
- Backend YOLO de nhan dien anh bien bao

Tai lieu nay la ban README de review, bo sung ro hon phan Docker va de xuat CI/CD.

## Kien truc tong quan

### 1. Flutter app

App Flutter phuc vu 2 nhom nhu cau:

- chat phap ly giao thong
- quan ly van ban phap luat
- upload file de ingest vao `noidung2`
- nhan dien bien bao bang YOLO

### 2. RAG backend

Backend RAG chay bang FastAPI, entrypoint chinh:

- `server/RAG/trusted_rag_app.py`

Backend nay dam nhan:

- `POST /chat` cho hoi dap phap ly
- `POST /upload-global-doc` de ingest file vao `noidung2`
- `POST /global-docs/{file_id}/activate`
- `POST /global-docs/{file_id}/deactivate`
- `DELETE /global-docs/{file_id}`
- `GET /health`

Flow ingest hien tai:

- chi dung global doc
- khong con session doc
- file hop le: `pdf`, `docx`, `txt`
- backend yeu cau `so_hieu` ton tai trong `vanbanphapluat`
- chunk hop le se duoc parse va insert vao `noidung2`

### 3. YOLO backend

Backend YOLO chay bang FastAPI, entrypoint trong Docker hien tai:

- `server/Yolo/app_test.py`

Backend nay dam nhan:

- `POST /detect`
- `POST /detect-lite`
- `GET /health`

### 4. Public URL

Project hien tai khong tu tao Cloudflare tunnel trong server nua.

Public URL duoc cap nhat bang script:

- `server/upserver.py`

Script nay:

- mo Cloudflare Quick Tunnel cho port local
- lay URL `trycloudflare`
- upsert vao bang `app_config` tren Supabase

Hai key dang dung:

- `rag_url`
- `yolo_url`

## Cau truc du lieu

Ba bang phap ly chinh:

- `vanbanphapluat`: metadata van ban
- `noidung`: noi dung nhap tay
- `noidung2`: noi dung ingest tu file

He thong RAG hien uu tien retrieve tren du lieu Supabase/Postgres, khong dung Qdrant.

## Chay local

### 1. Kich hoat env Python

```powershell
D:\Fishy\.venv\Scripts\Activate.ps1
```

### 2. Chay RAG

```powershell
cd D:\Fishy\server\RAG
uvicorn trusted_rag_app:app --host 0.0.0.0 --port 8000 --reload
```

### 3. Chay YOLO

```powershell
cd D:\Fishy\server\Yolo
uvicorn app_test:app --host 0.0.0.0 --port 8001 --reload
```

### 4. Public link bang Cloudflare

RAG:

```powershell
cd D:\Fishy\server
python .\upserver.py --port 8000 --key rag_url
```

YOLO:

```powershell
cd D:\Fishy\server
python .\upserver.py --port 8001 --key yolo_url
```

## Docker

### 1. Cac file lien quan

- `server/docker-compose.yml`
- `server/RAG/Dockerfile`
- `server/Yolo/Dockerfile`

### 2. Build va chay tung service

Dung trong thu muc `server`:

Build RAG:

```powershell
docker compose build fishy-rag
```

Run RAG:

```powershell
docker compose up -d fishy-rag
```

Build YOLO:

```powershell
docker compose build fishy-yolo
```

Run YOLO:

```powershell
docker compose up -d fishy-yolo
```

### 3. Build va chay ca hai service

```powershell
cd D:\Fishy\server
docker compose up -d --build
```

### 4. Kiem tra health

RAG:

```powershell
curl http://127.0.0.1:8000/health
```

YOLO:

```powershell
curl http://127.0.0.1:8001/health
```

### 5. Docker va Cloudflare

Sau khi container da len, can chay `upserver.py` o may host de cap nhat URL moi nhat len Supabase.

Docker chi lo service local.
`upserver.py` lo tunnel va update `app_config`.

Flow de deploy va public link:

1. `docker compose up -d --build fishy-rag`
2. `python .\upserver.py --port 8000 --key rag_url`
3. `docker compose up -d --build fishy-yolo`
4. `python .\upserver.py --port 8001 --key yolo_url`
5. Flutter app goi `initializeApiUrl()` de lay `rag_url` va `yolo_url` moi nhat tu Supabase

## Bien moi truong

### RAG can

- `SUPABASE_URL`
- `SUPABASE_SERVICE_ROLE_KEY`
- `OPENAI_API_KEY`
- `HF_EMBED_MODEL` hoac `EMBEDDING_MODEL`
- `ANSWER_MODEL`
- `CLASSIFIER_MODEL`
- `RAG_LEGAL_SCORE_THRESHOLD`
- `RAG_MIN_LEGAL_EVIDENCE`
- `LEGAL_RETRIEVAL_RPC_NAME`
- `LEGACY_LEGAL_RETRIEVAL_RPC_NAME`
- `GLOBAL_DOC_TOP_K`
- `GLOBAL_DOC_SCORE_THRESHOLD`
- `RAG_PORT`
- `RERANK_MODEL_NAME`
- `RERANK_CANDIDATE_COUNT`
- `RERANK_FINAL_TOP_K`

### YOLO can

- `YOLO_PORT`
- `MODEL_PATH` neu muon override model trong Docker

### Khuyen nghi

- khong commit secret that vao repo
- dung `.env` rieng cho local
- dung secret manager hoac CI secrets cho production

## CI/CD Docker

Hien tai repo chua co workflow GitHub Actions trong `.github/workflows`.

Phan duoi day la de xuat CI/CD de ban review.

### Muc tieu

- verify code co the build duoc Docker image
- tach rieng RAG va YOLO
- co the push image len registry
- deploy thu cong hoac ban tu dong o buoc sau

### Phuong an de xuat

#### CI

Moi pull request hoac push vao `main`:

- chay lint/test neu co
- build image `fishy-rag`
- build image `fishy-yolo`
- fail som neu Dockerfile hoac dependency loi

#### CD

Khi merge `main`:

- build image moi
- tag image theo commit SHA
- push len registry
- tren server deploy, pull image moi
- `docker compose up -d`
- chay lai `upserver.py` de cap nhat `rag_url` va `yolo_url`

### Registry phu hop

Co the dung:

- GitHub Container Registry
- Docker Hub
- private registry noi bo

### GitHub Actions mau

Vi du workflow build Docker images:

```yaml
name: docker-build

on:
  push:
    branches: [main]
  pull_request:

jobs:
  build-rag:
    runs-on: ubuntu-latest
    steps:
      - name: Checkout
        uses: actions/checkout@v4

      - name: Set up Docker Buildx
        uses: docker/setup-buildx-action@v3

      - name: Build RAG image
        uses: docker/build-push-action@v6
        with:
          context: ./server/RAG
          file: ./server/RAG/Dockerfile
          push: false
          tags: fishy-rag:ci

  build-yolo:
    runs-on: ubuntu-latest
    steps:
      - name: Checkout
        uses: actions/checkout@v4

      - name: Set up Docker Buildx
        uses: docker/setup-buildx-action@v3

      - name: Build YOLO image
        uses: docker/build-push-action@v6
        with:
          context: ./server/Yolo
          file: ./server/Yolo/Dockerfile
          push: false
          tags: fishy-yolo:ci
```

### GitHub Actions mau de push len GHCR

```yaml
name: docker-publish

on:
  push:
    branches: [main]

jobs:
  publish:
    runs-on: ubuntu-latest
    permissions:
      contents: read
      packages: write
    strategy:
      matrix:
        include:
          - name: fishy-rag
            context: ./server/RAG
            file: ./server/RAG/Dockerfile
          - name: fishy-yolo
            context: ./server/Yolo
            file: ./server/Yolo/Dockerfile
    steps:
      - name: Checkout
        uses: actions/checkout@v4

      - name: Log in to GHCR
        uses: docker/login-action@v3
        with:
          registry: ghcr.io
          username: ${{ github.actor }}
          password: ${{ secrets.GITHUB_TOKEN }}

      - name: Set up Docker Buildx
        uses: docker/setup-buildx-action@v3

      - name: Build and push
        uses: docker/build-push-action@v6
        with:
          context: ${{ matrix.context }}
          file: ${{ matrix.file }}
          push: true
          tags: |
            ghcr.io/<your-org>/${{ matrix.name }}:latest
            ghcr.io/<your-org>/${{ matrix.name }}:${{ github.sha }}
```

### Deploy workflow de xuat

Neu ban deploy len 1 may Windows hoac Linux tu quan ly:

1. Pull source hoac pull image moi
2. `docker compose up -d`
3. Chay:

```powershell
python .\upserver.py --port 8000 --key rag_url
python .\upserver.py --port 8001 --key yolo_url
```

4. Kiem tra:

```powershell
curl http://127.0.0.1:8000/health
curl http://127.0.0.1:8001/health
```

### Diem can luu y khi dua vao CI/CD

- RAG dang load model Hugging Face luc startup, nen may deploy can co internet hoac cache model truoc
- `upserver.py` hien phu thuoc `cloudflared.exe` tren host Windows
- neu deploy Linux, can co ban `cloudflared` phu hop va chinh `CLOUDFLARED_PATH`
- `docker compose` chi chay service local, khong tu cap nhat public URL
- phan update `rag_url` va `yolo_url` van la buoc deploy can thuc hien sau khi container len

## Khuyen nghi toi uu sau khi review README2

Neu ban thay huong nay hop ly, buoc tiep theo nen la:

1. tao `.github/workflows/docker-build.yml`
2. tao `.github/workflows/docker-publish.yml`
3. tach secret local khoi repo
4. viet them file deploy script, vi du:
   - `server/deploy-rag.ps1`
   - `server/deploy-yolo.ps1`
   - hoac `server/deploy-all.ps1`

## Tom tat

Trang thai hien tai:

- RAG va YOLO da co Dockerfile
- Compose da co 2 service rieng
- Cloudflare public URL duoc cap nhat thu cong qua `upserver.py`
- ingest file vao `noidung2` di thang qua RAG chinh
- session doc da bi loai bo
- repo chua co CI/CD chinh thuc, nhung co the bo sung theo mau trong tai lieu nay
