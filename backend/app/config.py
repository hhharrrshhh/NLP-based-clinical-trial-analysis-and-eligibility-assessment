"""Environment configuration; values containing secrets are never returned."""
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = Path(os.getenv("DATA_DIR", str(ROOT / "data"))).resolve()
REPORTS_DIR = ROOT / "reports"
CORS_ORIGINS = [x.strip() for x in os.getenv("CORS_ORIGINS", "http://localhost:8501,http://127.0.0.1:8501").split(",") if x.strip()]
MAX_BODY_BYTES = 256_000
NOTICE = "Research demonstration using synthetic profiles. Not a clinical decision or full eligibility determination."
