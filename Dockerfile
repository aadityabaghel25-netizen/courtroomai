# CourtroomAI backend. Data (judgment library, search index, statute tables) is not in git.
# Pass --build-arg DATA_URL=<archive> to bake it into the image (Cloud Run: no volume, fast cold
# start); otherwise mount it at /data or let scripts/fetch_data.sh download it on first start.
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 TOKENIZERS_PARALLELISM=false \
    DATA_DIR=/data HF_HOME=/opt/hf

WORKDIR /app

COPY requirements.txt .
ENV PIP_DEFAULT_TIMEOUT=120 PIP_RETRIES=10
RUN pip install --no-cache-dir torch==2.14.1 --index-url https://download.pytorch.org/whl/cpu
RUN pip install --no-cache-dir -r requirements.txt

# Bake the two open models into the image so start-up does not download ~500 MB.
RUN python -c "from sentence_transformers import SentenceTransformer, CrossEncoder; \
SentenceTransformer('BAAI/bge-base-en-v1.5'); CrossEncoder('cross-encoder/ms-marco-MiniLM-L-6-v2')"

COPY core core
COPY backend backend
COPY rag rag
COPY ingestion ingestion
COPY prompts prompts
COPY samples samples
COPY scripts scripts

ARG DATA_URL=""
RUN DATA_URL="$DATA_URL" sh scripts/fetch_data.sh

EXPOSE 8000
CMD ["sh", "-c", "sh scripts/fetch_data.sh && uvicorn backend.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
