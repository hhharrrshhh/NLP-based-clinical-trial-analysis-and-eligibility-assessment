"""Run real verification commands and save machine-readable results and source hash."""
import argparse
import hashlib
import json
import os
import subprocess
import sys
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def source_hash():
    digest = hashlib.sha256()
    for folder in ("backend", "frontend", "experiments", "scripts", "tests"):
        for path in sorted((ROOT / folder).rglob("*.py")):
            digest.update(path.relative_to(ROOT).as_posix().encode())
            digest.update(path.read_bytes())
    return digest.hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--live", action="store_true", help="Also exercise the running HTTP/API and Streamlit application")
    args = parser.parse_args()
    reports = ROOT / "reports"
    reports.mkdir(exist_ok=True)
    environment = dict(os.environ, PYTHONUTF8="1", PYTHONIOENCODING="utf-8")
    commands = [
        ("pytest", [sys.executable, "-m", "pytest", "-q", "--junitxml=reports/pytest.xml"]),
        ("dependencies", [sys.executable, "-m", "pip", "check"]),
        ("legacy_separate", [sys.executable, "legacy/TrialOps_Adaptive_Demo/trialops_adaptive_demo.py", "--test"]),
        ("compile", [sys.executable, "-m", "compileall", "-q", "backend", "frontend", "experiments", "scripts"]),
    ]
    if args.live:
        commands.extend([(name, [sys.executable, "-m", "scripts." + name]) for name in ("integration_smoke", "ui_smoke")])
    results = []
    before_hash = source_hash()
    for name, command in commands:
        started = time.perf_counter()
        completed = subprocess.run(command, cwd=ROOT, env=environment, capture_output=True, text=True, encoding="utf-8", errors="replace")
        log = completed.stdout + completed.stderr
        (reports / f"verification_{name}.log").write_text(log, encoding="utf-8")
        row = {"name": name, "command": command, "exit_code": completed.returncode, "status": "passed" if completed.returncode == 0 else "failed",
               "elapsed_seconds": round(time.perf_counter() - started, 3), "log": f"reports/verification_{name}.log"}
        results.append(row)
        print(f"{name}: {row['status']} ({row['elapsed_seconds']} s)", flush=True)
        if completed.returncode:
            print(log[-7000:], flush=True)
    suites = list(ET.parse(reports / "pytest.xml").getroot().iter("testsuite"))
    totals = {name: sum(int(suite.get(name, 0)) for suite in suites) for name in ("tests", "failures", "errors", "skipped")}
    totals["passed"] = totals["tests"] - totals["failures"] - totals["errors"] - totals["skipped"]
    after_hash = source_hash()
    report = {"run_at_utc": datetime.now(timezone.utc).isoformat(), "status": "passed" if all(x["exit_code"] == 0 for x in results) and before_hash == after_hash else "failed",
              "source_sha256": after_hash, "source_unchanged_during_verification": before_hash == after_hash,
              "pytest": totals, "commands": results, "live_checks_requested": args.live,
              "legacy_isolation": "Active pytest discovers tests/ only; untouched legacy sanity checks execute separately and remain visible."}
    (reports / "test_results.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    raise SystemExit(0 if report["status"] == "passed" else 1)


if __name__ == "__main__":
    main()
