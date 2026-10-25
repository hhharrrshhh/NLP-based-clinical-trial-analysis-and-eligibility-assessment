FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    DATA_DIR=/app/data \
    TRIALOPS_MODEL_CACHE=/app/models/hf \
    TRIALOPS_TORCH_THREADS=4

WORKDIR /app
# CPU wheels avoid downloading CUDA runtimes for this CPU research app.
COPY requirements.txt ./requirements.txt
RUN python -m pip install --upgrade pip \
    && python -m pip install --index-url https://download.pytorch.org/whl/cpu torch==2.14.1 \
    && python -m pip install -r requirements.txt

COPY backend ./backend
COPY data/processed ./data/processed
COPY data/synthetic ./data/synthetic
COPY reports ./reports
RUN mkdir -p /app/models/hf /app/data/index \
    && useradd --create-home --uid 10001 trialops \
    && chown -R trialops:trialops /app
USER trialops

EXPOSE 8000
HEALTHCHECK --interval=20s --timeout=5s --start-period=30s --retries=5 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=4)"
CMD ["python", "-m", "uvicorn", "backend.app.main:app", "--host", "0.0.0.0", "--port", "8000"]
