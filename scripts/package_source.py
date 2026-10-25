"""Package only audited tracked files; never sweep the working directory/caches."""
import hashlib
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED

ROOT = Path(__file__).resolve().parents[1]


def main():
    revision = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    paths = subprocess.check_output(["git", "ls-files", "-z"], cwd=ROOT).decode("utf-8").split("\0")
    destination = ROOT / "TrialOps-Adaptive-AI-source.zip"
    count = 0
    with ZipFile(destination, "w", ZIP_DEFLATED) as archive:
        for name in paths:
            if not name:
                continue
            path = ROOT / name
            forbidden = (name.startswith(("models/", ".venv/", "data/external/", "data/index/", ".git/"))
                         or Path(name).name in {".env", "secrets.toml"}
                         or path.suffix.casefold() in {".safetensors", ".pt", ".pth", ".bin", ".sqlite", ".zip"})
            if forbidden or path.stat().st_size > 5_000_000:
                raise ValueError(f"Unsafe tracked package input: {name}")
            archive.write(path, arcname="TrialOps-Adaptive-AI/" + name)
            count += 1
    with ZipFile(destination) as archive:
        if archive.testzip() is not None:
            raise ValueError("Archive integrity verification failed")
    report = {"created_at_utc": datetime.now(timezone.utc).isoformat(), "checkpoint_commit": revision,
              "path": str(destination), "files": count, "bytes": destination.stat().st_size,
              "sha256": hashlib.sha256(destination.read_bytes()).hexdigest(),
              "contents": "Audited Git-tracked source, public registry snapshot, measured reports, tests and documentation. External corpora/models/credentials/review databases excluded."}
    (ROOT / "reports/source_archive.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
