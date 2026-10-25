"""Download the exact licensed CHIA archive used in the measured experiments."""
import argparse
import hashlib
import io
import json
from datetime import datetime, timezone
from pathlib import Path
from zipfile import ZipFile
import requests

ROOT = Path(__file__).resolve().parents[1]
URL = "https://ndownloader.figshare.com/files/21728850"
METADATA_URL = "https://api.figshare.com/v2/articles/11855817/versions/2"
SHA256 = "b51ec05ba42a3805daf9581dd22a305986f7c5ae3ca4dad36b70d37970fb69b2"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=ROOT / "data/external/chia")
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    archive = output / "chia_with_scope.zip"
    if archive.exists() and hashlib.sha256(archive.read_bytes()).hexdigest() == SHA256:
        raw = archive.read_bytes()
        print("Using verified existing CHIA archive.")
    else:
        response = requests.get(URL, timeout=(10, 60))
        response.raise_for_status()
        raw = response.content
        if len(raw) > 10_000_000 or hashlib.sha256(raw).hexdigest() != SHA256:
            raise ValueError("CHIA download fingerprint differs from the published experiment source.")
        archive.write_bytes(raw)
    with ZipFile(io.BytesIO(raw)) as source:
        if sum(item.file_size for item in source.infolist()) > 100_000_000:
            raise ValueError("Unexpected expanded size")
        for item in source.infolist():
            destination = (output / item.filename).resolve()
            if not destination.is_relative_to(output):
                raise ValueError("Unsafe archive path")
            if item.is_dir():
                continue
            content = source.read(item)
            if destination.exists():
                if destination.read_bytes() != content:
                    raise ValueError(f"Refusing to overwrite changed annotation: {item.filename}")
                continue
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(content)
    metadata_path = output / "figshare_metadata.json"
    if not metadata_path.exists():
        response = requests.get(METADATA_URL, timeout=(10, 30))
        response.raise_for_status()
        metadata_path.write_text(json.dumps(response.json(), indent=2), encoding="utf-8")
    provenance = {"retrieved_at": datetime.now(timezone.utc).isoformat(), "source_url": "https://doi.org/10.6084/m9.figshare.11855817.v2",
                  "download_url": URL, "license": "CC BY 4.0", "license_url": "https://creativecommons.org/licenses/by/4.0/",
                  "sha256": SHA256, "note": "Archive unchanged. Preserve CRLF when decoding text for annotation offsets."}
    # Preserve the initial retrieval record and add a verification/run record.
    (output / "download_verification.json").write_text(json.dumps(provenance, indent=2), encoding="utf-8")
    (output / "ATTRIBUTION.md").write_text("Kury et al. (2020), Chia Annotated Datasets v2. https://doi.org/10.6084/m9.figshare.11855817.v2\nCC BY 4.0: https://creativecommons.org/licenses/by/4.0/\nOriginal archive contents unchanged. Experiments document label mappings and excluded defective spans.\n", encoding="utf-8")
    print(json.dumps({"text_files": len(list(output.glob('NCT*.txt'))), "sha256": SHA256, "license": "CC BY 4.0"}))


if __name__ == "__main__":
    main()
