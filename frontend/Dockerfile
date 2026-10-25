FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    API_BASE_URL=http://backend:8000 \
    STREAMLIT_BROWSER_GATHER_USAGE_STATS=false

WORKDIR /app
RUN python -m pip install --no-cache-dir \
    streamlit==1.45.1 requests==2.32.3 pandas==2.2.3
COPY frontend ./frontend
COPY .streamlit ./.streamlit
RUN useradd --create-home --uid 10001 trialops \
    && chown -R trialops:trialops /app
USER trialops

EXPOSE 8501
HEALTHCHECK --interval=20s --timeout=5s --start-period=20s --retries=5 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8501/_stcore/health', timeout=4)"
CMD ["python", "-m", "streamlit", "run", "frontend/app.py", "--server.address", "0.0.0.0", "--server.port", "8501", "--server.headless", "true"]
