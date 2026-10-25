"""FastAPI application for a local synthetic clinical NLP demonstration."""
import csv
import html
import io
import json
import logging
from pathlib import Path
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response
from fastapi.exceptions import RequestValidationError
from .config import CORS_ORIGINS, DATA_DIR, MAX_BODY_BYTES, NOTICE, REPORTS_DIR
from .schemas import ExtractRequest, CompareRequest, EvaluateRequest, ReviewRequest, AskRequest
from .store import get_studies, get_metadata
from .services import require_study, extract_study, evaluate_study, compare_studies, dashboard
from .nlp import extract
from .neural import BiomedicalNER
from .reviews import save_review
from .workflow import run_workflow, get_index

log = logging.getLogger("trialops")
app = FastAPI(title="TrialOps-Adaptive AI", version="0.1.0", description=NOTICE)
app.add_middleware(CORSMiddleware, allow_origins=CORS_ORIGINS, allow_credentials=False,
                   allow_methods=["GET", "POST"], allow_headers=["Content-Type"])
ner = BiomedicalNER()


@app.middleware("http")
async def payload_limit(request: Request, call_next):
    if request.method in {"POST", "PUT", "PATCH"}:
        try:
            declared = int(request.headers.get("content-length", "0"))
        except ValueError:
            return JSONResponse(status_code=400, content={"detail": "Invalid content length"})
        if declared > MAX_BODY_BYTES:
            return JSONResponse(status_code=413, content={"detail": "Payload exceeds 256 KB limit"})
        # Bound chunked bodies while reading; never buffer an unlimited upload.
        body = bytearray()
        async for chunk in request.stream():
            body.extend(chunk)
            if len(body) > MAX_BODY_BYTES:
                return JSONResponse(status_code=413, content={"detail": "Payload exceeds 256 KB limit"})
        request._body = bytes(body)
    return await call_next(request)


@app.exception_handler(KeyError)
async def missing_study(request, error):
    return JSONResponse(status_code=404, content={"detail": "Study not found in the local corpus"})


@app.exception_handler(ValueError)
async def bad_input(request, error):
    return JSONResponse(status_code=422, content={"detail": str(error)[:500]})


@app.exception_handler(RequestValidationError)
async def invalid_request(request, error):
    # Do not echo submitted profiles or non-JSON float values in error responses.
    details = [{"loc": list(item["loc"]), "msg": item["msg"], "type": item["type"]} for item in error.errors()]
    return JSONResponse(status_code=422, content={"detail": details})


@app.get("/health")
def health():
    return {"status": "ok", "study_count": len(get_studies()), "version": "0.1.0", "notice": NOTICE}


@app.get("/dashboard")
def overview():
    return dashboard()


@app.get("/studies")
def studies(country: str | None = Query(None, max_length=80), condition: str | None = Query(None, max_length=160),
            status: str | None = Query(None, max_length=80), study_id: str | None = Query(None, max_length=80)):
    rows = get_studies()
    if country:
        rows = [s for s in rows if country.casefold() in [x.casefold() for x in s.get("countries", [])]]
    if condition:
        rows = [s for s in rows if condition.casefold() in " ".join(s.get("conditions", [])).casefold()]
    if status:
        rows = [s for s in rows if (s.get("status") or "UNKNOWN").casefold() == status.casefold()]
    if study_id:
        rows = [s for s in rows if study_id.upper() in s["study_id"].upper()]
    return {"count": len(rows), "studies": rows}


@app.get("/studies/{study_id}")
def study_detail(study_id: str):
    return {"study": require_study(study_id), "extraction": extract_study(study_id)}


@app.post("/extract")
def extract_endpoint(request: ExtractRequest):
    if request.study_id:
        study = require_study(request.study_id)
        if request.text and request.text != study.get("eligibility_text", ""):
            raise HTTPException(422, "Text must match source when a study_id is supplied; omit study_id for a standalone example.")
        text = study.get("eligibility_text") or ""
        result = extract_study(request.study_id)
    else:
        text = request.text
        result = extract(text)
    return {"baseline": result, "transformer": ner.predict(text) if request.transformer else {"status": "not_requested"}, "notice": NOTICE}


@app.post("/compare")
def compare(request: CompareRequest):
    return compare_studies(request.study_ids)


@app.post("/reviews")
def review(request: ReviewRequest):
    extraction = extract_study(request.study_id)
    if request.extraction_hash != extraction["extraction_hash"]:
        raise HTTPException(409, "Extraction changed. Reload source text and rules before reviewing.")
    valid = {r["id"] for r in extraction["rules"]}
    if not set(request.rule_ids).issubset(valid):
        raise HTTPException(422, "Only supported source-linked rules may be reviewed.")
    return {"reviews": save_review(**request.model_dump()), "scope": "synthetic demonstration only; not expert validation"}


@app.post("/evaluate")
def evaluate(request: EvaluateRequest):
    return evaluate_study(request.study_id, request.profile.model_dump())


@app.post("/ask")
def ask(request: AskRequest):
    return run_workflow(request)


@app.get("/metrics")
def metrics():
    artifacts = {}
    for name in ("entity_benchmark", "adaptation_benchmark", "research_metrics", "model_smoke", "generation_smoke", "integration_smoke", "retrieval_benchmark", "ui_smoke", "deployment"):
        path = REPORTS_DIR / f"{name}.json"
        if not path.exists():
            path = REPORTS_DIR / "experiments" / f"{name}.json"
        if path.exists():
            artifacts[name] = json.loads(path.read_text(encoding="utf-8"))
    return {"artifacts": artifacts, "availability": "measured_files_only", "dataset": get_metadata(), "notice": NOTICE}


@app.get("/reports/{study_id}")
def report(study_id: str, format: str = Query("json", pattern="^(json|csv|html)$")):
    study = require_study(study_id)
    extraction = extract_study(study_id)
    payload = {"study": study, "extraction": extraction, "notice": NOTICE}
    safe_name = re_safe_id(study_id)
    if format == "json":
        return Response(json.dumps(payload, indent=2, ensure_ascii=False), media_type="application/json",
                        headers={"Content-Disposition": f'attachment; filename="{safe_name}.json"'})
    if format == "csv":
        output = io.StringIO(newline="")
        writer = csv.DictWriter(output, fieldnames=["study_id", "kind", "source_text", "structured_rule", "source_url"])
        writer.writeheader()
        for kind, rows in (("supported_rule", extraction["rules"]), ("needs_review", extraction["unresolved"])):
            for row in rows:
                text = row.get("source_text", "")
                # Prevent formula execution when the export is opened in spreadsheet apps.
                if text.lstrip().startswith(("=", "+", "-", "@")):
                    text = "'" + text
                writer.writerow({"study_id": study_id, "kind": kind, "source_text": text, "structured_rule": json.dumps(row, ensure_ascii=False), "source_url": study["source_url"]})
        return Response(output.getvalue(), media_type="text/csv", headers={"Content-Disposition": f'attachment; filename="{safe_name}.csv"'})
    body = f'<!doctype html><html lang="en"><meta charset="utf-8"><title>TrialOps study report</title><style>body{{font:16px system-ui;max-width:960px;margin:40px auto;padding:20px}}pre{{white-space:pre-wrap;overflow-wrap:anywhere;background:#eef4f7;padding:24px}}a{{color:#12637a}}</style><h1>{html.escape(study["title"])}</h1><p>{html.escape(NOTICE)}</p><p><a href="{html.escape(study["source_url"], quote=True)}">{html.escape(study_id)}</a></p><pre>{html.escape(json.dumps(payload, indent=2, ensure_ascii=False))}</pre></html>'
    return Response(body, media_type="text/html", headers={"Content-Disposition": f'attachment; filename="{safe_name}.html"'})


def re_safe_id(value):
    import re
    return re.sub(r"[^A-Za-z0-9_-]", "_", value)[:80]
