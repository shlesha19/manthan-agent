# api.py
"""
MANTHA — api.py
FastAPI wrapper. Accepts a text query from the Gmail extension,
resolves the right data file from the local folder, runs the
full pipeline, and returns a draft reply + base64 PDF report.
"""

import os
import base64
import logging
import tempfile
import traceback
import shutil
from pathlib import Path

import pandas as pd

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from pipeline import run_pipeline

# ── If your team already has a file-resolver function, import it here:
# from fetcher import resolve_file_for_query   ← swap in if it exists

log = logging.getLogger("mantha_api")
logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s  [api]  %(levelname)s — %(message)s")

app = FastAPI(title="MANTHA API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["POST", "GET"],
    allow_headers=["*"],
)

# ── IMPORTANT: Set this to your local data folder path ────────
DATA_FOLDER = os.environ.get("MANTHA_DATA_FOLDER", "./Databases")


# ── Request shape from the Gmail extension ────────────────────
class EmailRequest(BaseModel):
    query:   str        # the email body text
    context: dict       # subject, sender, thread etc.


# ── Health check ──────────────────────────────────────────────
@app.get("/health")
async def health():
    files = list_data_files()
    return {
        "status":      "ok",
        "data_folder": DATA_FOLDER,
        "files_found": len(files),
        "files":       files,
    }


# ── Main endpoint ─────────────────────────────────────────────
@app.post("/process")
async def process(req: EmailRequest):
    try:
        log.info("Query received: %s", req.query[:120])

        # ── Step 1: Find the right file for this query ────────
        filepath = resolve_file_for_query(req.query, req.context)

        if not filepath:
            raise HTTPException(
                status_code=404,
                detail=(
                    f"No matching data file found for this query in '{DATA_FOLDER}'. "
                    f"Available files: {list_data_files()}"
                )
            )

        log.info("Resolved file: %s", filepath)

        # ── Step 2: Run pipeline into a temp output folder ────
        tmp_dir    = tempfile.mkdtemp()
        tmp_pdf    = os.path.join(tmp_dir, "mantha_report.pdf")
        tmp_plots  = os.path.join(tmp_dir, "plots")

        try:
            success = run_pipeline(
                filepath=filepath,
                recipients=[],        # extension handles reply
                output_pdf=tmp_pdf,
                output_plots=tmp_plots,
                send_email=False,     # never auto-send from API
            )

            if not success:
                raise HTTPException(
                    status_code=500,
                    detail="Pipeline failed — check server logs."
                )

            # ── Step 3: Read the generated PDF ────────────────
            if not os.path.exists(tmp_pdf):
                raise HTTPException(
                    status_code=500,
                    detail="PDF was not generated."
                )

            with open(tmp_pdf, "rb") as f:
                pdf_b64 = base64.b64encode(f.read()).decode("utf-8")

            # ── Step 4: Build reply draft ──────────────────────
            draft = build_reply_draft(
                query=req.query,
                context=req.context,
                resolved_file=os.path.basename(filepath),
            )

            return JSONResponse(content={
                "success": True,
                "draft_text": draft,
                "pdf_base64": pdf_b64,
                "subject": req.context.get("subject", "MANTHA Report"),
                "recipient": req.context.get("sender", "")
            })

        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)

    except HTTPException:
        raise
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


# ═══════════════════════════════════════════════════════════════
# FILE RESOLVER
# ═══════════════════════════════════════════════════════════════

# ═══════════════════════════════════════════════════════════════
# FILE RESOLVER — LLM-powered semantic matching
# ═══════════════════════════════════════════════════════════════

import json
import requests

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
OPENROUTER_URL     = "https://openrouter.ai/api/v1/chat/completions"
OPENROUTER_MODEL   = "deepseek/deepseek-chat:free"


def list_data_files(full_path: bool = False) -> list[str]:
    """Return all CSV/Excel files in DATA_FOLDER."""
    supported = {".csv", ".xlsx", ".xls", ".tsv"}
    folder = Path(DATA_FOLDER)

    if not folder.exists():
        log.warning("DATA_FOLDER does not exist: %s", DATA_FOLDER)
        return []

    files = [
        str(f) if full_path else f.name
        for f in folder.iterdir()
        if f.suffix.lower() in supported
    ]
    return files

def resolve_file_for_query(query: str, context: dict) -> str | None:
    """
    Uses the LLM to semantically pick the best matching file
    from DATA_FOLDER based on the email query + each file's columns.
    Falls back to most recent file if LLM fails.
    """
    files = list_data_files(full_path=True)
    if not files:
        log.error("No data files found in %s", DATA_FOLDER)
        return None

    # ── Single file shortcut ───────────────────────────────────
    if len(files) == 1:
        log.info("Only one file available, using it: %s", files[0])
        return files[0]

    # ── Build file context: filename + column headers ──────────
    file_summaries = []
    for fp in files:
        try:
            ext = Path(fp).suffix.lower()
            if ext in {".xlsx", ".xls"}:
                df_peek = pd.read_excel(fp, nrows=2)
            else:
                df_peek = pd.read_csv(fp, nrows=2)
            columns = df_peek.columns.tolist()
        except Exception:
            columns = ["(unreadable)"]

        file_summaries.append({
            "filename": Path(fp).name,
            "columns":  columns
        })

    # ── Ask LLM to pick the best file ─────────────────────────
    subject = context.get("subject", "")
    prompt = (
        f"You are a data assistant. A user sent this email:\n"
        f"Subject: {subject}\n"
        f"Body: {query[:500]}\n\n"
        f"Available data files and their columns:\n"
        f"{json.dumps(file_summaries, indent=2)}\n\n"
        f"Which single filename best matches the user's query? "
        f"Reply with ONLY the filename, nothing else. "
        f"Example: revenue_data.csv"
    )

    try:
        resp = requests.post(
            OPENROUTER_URL,
            headers={
                "Authorization": f"Bearer {OPENROUTER_API_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "model":       OPENROUTER_MODEL,
                "messages":    [{"role": "user", "content": prompt}],
                "temperature": 0,
                "max_tokens":  32,
            },
            timeout=20,
        )
        resp.raise_for_status()
        chosen_name = resp.json()["choices"][0]["message"]["content"].strip().strip('"').strip("'")
        log.info("LLM chose file: %s", chosen_name)

        # Match back to full path
        for fp in files:
            if Path(fp).name.lower() == chosen_name.lower():
                log.info("Resolved to: %s", fp)
                return fp

        # LLM returned something slightly off — fuzzy match
        for fp in files:
            if chosen_name.lower() in Path(fp).name.lower():
                log.info("Fuzzy matched to: %s", fp)
                return fp

        log.warning("LLM chose '%s' but no file matched. Falling back.", chosen_name)

    except Exception as exc:
        log.warning("LLM file resolution failed: %s. Falling back.", exc)

    # ── Fallback: most recently modified file ──────────────────
    fallback = sorted(files, key=os.path.getmtime, reverse=True)[0]
    log.warning("Fallback to most recent file: %s", fallback)
    return fallback


# ═══════════════════════════════════════════════════════════════
# DRAFT BUILDER
# ═══════════════════════════════════════════════════════════════

def build_reply_draft(query: str, context: dict, resolved_file: str) -> str:
    sender  = context.get("sender", "")
    name    = sender.split("<")[0].strip() or "there"
    subject = context.get("subject", "your query")

    return (
        f"Hi {name},\n\n"
        f"Thank you for your message regarding \"{subject}\".\n\n"
        f"I've run your query through our data pipeline and pulled the relevant "
        f"analysis from {resolved_file}. Please find the full report attached — "
        f"it includes data breakdowns, visualisations, and key insights.\n\n"
        f"Let me know if you'd like a different cut of the data or have any follow-up questions.\n\n"
        f"Best regards"
    )
