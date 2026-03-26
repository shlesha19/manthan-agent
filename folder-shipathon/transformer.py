"""
MANTHA — Tool 2: data_transformer.py
Cleans, normalises, and reshapes a raw DataFrame for downstream use.
Uses an LLM (via OpenRouter) to infer column semantics when needed.
Robust fallback: every step is try/except; partial success is still returned.
"""

import logging
import re
from typing import Optional

import pandas as pd
import requests

# ── Logging ────────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  [data_transformer]  %(levelname)s — %(message)s",
)
log = logging.getLogger("data_transformer")


# ── Config ─────────────────────────────────────────────────────────────────────
OPENROUTER_API_KEY = "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"          # ← replace / env var
OPENROUTER_MODEL   = "mistralai/mistral-7b-instruct"    # cheap, fast default
OPENROUTER_URL     = "https://openrouter.ai/api/v1/chat/completions"


# ── LLM helper ─────────────────────────────────────────────────────────────────
def _llm_infer_column_types(columns: list[str], sample_values: dict) -> dict:
    """
    Ask the LLM what semantic type each column is:
    e.g. {"order_date": "datetime", "revenue": "numeric", "city": "categorical"}
    Returns {} on any failure — caller falls back to pandas inference.
    """
    prompt = (
        "You are a data-engineering assistant. "
        "Given these DataFrame column names and sample values, "
        "return a JSON dict mapping each column name to one of: "
        "'datetime', 'numeric', 'categorical', 'text', 'id', 'boolean', 'unknown'.\n\n"
        f"Columns and samples:\n{sample_values}\n\n"
        "Return ONLY the JSON dict, no explanation."
    )
    try:
        resp = requests.post(
            OPENROUTER_URL,
            headers={
                "Authorization": f"Bearer {OPENROUTER_API_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "model": OPENROUTER_MODEL,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0,
                "max_tokens": 512,
            },
            timeout=20,
        )
        resp.raise_for_status()
        import json
        raw = resp.json()["choices"][0]["message"]["content"].strip()
        # Strip markdown fences if present
        raw = re.sub(r"```[a-z]*\n?", "", raw).strip("`").strip()
        return json.loads(raw)
    except Exception as exc:
        log.warning("LLM column-type inference failed (%s) — using pandas fallback.", exc)
        return {}


# ── Core transformation steps ──────────────────────────────────────────────────
def _coerce_types(df: pd.DataFrame, type_map: dict) -> pd.DataFrame:
    """Apply the type_map produced by LLM or inferred heuristically."""
    for col, dtype in type_map.items():
        if col not in df.columns:
            continue
        try:
            if dtype == "datetime":
                df[col] = pd.to_datetime(df[col], errors="coerce")
            elif dtype == "numeric":
                df[col] = pd.to_numeric(df[col].astype(str).str.replace(",", ""), errors="coerce")
            elif dtype == "boolean":
                df[col] = df[col].map(
                    {"true": True, "false": False, "1": True, "0": False,
                     "yes": True, "no": False}
                )
            elif dtype in {"categorical", "id"}:
                df[col] = df[col].astype("category")
            # 'text' and 'unknown' — leave as-is
        except Exception as exc:
            log.warning("Could not coerce column '%s' to %s: %s", col, dtype, exc)
    return df


def _clean_strings(df: pd.DataFrame) -> pd.DataFrame:
    """Strip whitespace and normalise case for all object columns."""
    for col in df.select_dtypes(include="object").columns:
        try:
            df[col] = df[col].astype(str).str.strip()
        except Exception as exc:
            log.warning("String clean failed on '%s': %s", col, exc)
    return df


def _handle_missing(
    df: pd.DataFrame,
    numeric_fill: str = "median",   # "median" | "mean" | "zero" | "drop"
    categorical_fill: str = "mode", # "mode"   | "unknown" | "drop"
) -> pd.DataFrame:
    """Fill or drop missing values column-by-column."""
    for col in df.columns:
        n_missing = df[col].isna().sum()
        if n_missing == 0:
            continue

        pct = n_missing / len(df) * 100
        log.info("Column '%s' — %d missing (%.1f%%)", col, n_missing, pct)

        # Drop column if > 70 % missing
        if pct > 70:
            log.warning("Dropping column '%s' (%.1f%% missing)", col, pct)
            df = df.drop(columns=[col])
            continue

        try:
            if pd.api.types.is_numeric_dtype(df[col]):
                if numeric_fill == "median":
                    df[col] = df[col].fillna(df[col].median())
                elif numeric_fill == "mean":
                    df[col] = df[col].fillna(df[col].mean())
                elif numeric_fill == "zero":
                    df[col] = df[col].fillna(0)
                elif numeric_fill == "drop":
                    df = df.dropna(subset=[col])
            else:
                if categorical_fill == "mode":
                    mode_val = df[col].mode()
                    df[col] = df[col].fillna(mode_val[0] if not mode_val.empty else "Unknown")
                elif categorical_fill == "unknown":
                    df[col] = df[col].fillna("Unknown")
                elif categorical_fill == "drop":
                    df = df.dropna(subset=[col])
        except Exception as exc:
            log.warning("Missing-value fill failed on '%s': %s", col, exc)

    return df.reset_index(drop=True)


def _remove_duplicates(df: pd.DataFrame) -> pd.DataFrame:
    before = len(df)
    df = df.drop_duplicates().reset_index(drop=True)
    removed = before - len(df)
    if removed:
        log.info("Removed %d duplicate rows.", removed)
    return df


def _normalise_column_names(df: pd.DataFrame) -> pd.DataFrame:
    """snake_case column names."""
    df.columns = [
        re.sub(r"\s+", "_", str(c).strip().lower())
          .replace("-", "_")
          .replace("(", "")
          .replace(")", "")
        for c in df.columns
    ]
    return df


# ── Public API ─────────────────────────────────────────────────────────────────
def transform_data(
    df: pd.DataFrame,
    use_llm: bool = True,
    numeric_fill: str = "median",
    categorical_fill: str = "mode",
) -> Optional[pd.DataFrame]:
    """
    Full transformation pipeline.

    Steps:
      1. Normalise column names → snake_case
      2. Clean string whitespace
      3. Remove duplicates
      4. Infer column types (LLM or pandas heuristic)
      5. Coerce types
      6. Handle missing values

    Parameters
    ----------
    df               : Raw DataFrame from data_fetcher.
    use_llm          : Use OpenRouter LLM to infer column semantics.
    numeric_fill     : Strategy for numeric NaN — "median"|"mean"|"zero"|"drop".
    categorical_fill : Strategy for categorical NaN — "mode"|"unknown"|"drop".

    Returns
    -------
    Transformed DataFrame, or None on unrecoverable error.
    """
    if df is None or df.empty:
        log.error("transform_data received empty/None DataFrame.")
        return None

    try:
        log.info("Transform start — shape=%s", df.shape)

        df = _normalise_column_names(df)
        df = _clean_strings(df)
        df = _remove_duplicates(df)

        # Build sample for LLM
        sample_values = {
            col: df[col].dropna().head(3).tolist()
            for col in df.columns
        }

        if use_llm:
            type_map = _llm_infer_column_types(list(df.columns), sample_values)
        else:
            type_map = {}

        # Heuristic fallback for columns not covered by LLM
        for col in df.columns:
            if col not in type_map:
                sample = df[col].dropna().head(10)
                numeric_check = pd.to_numeric(sample, errors="coerce").notna().mean()
                # Check numeric FIRST — plain numbers (e.g. 1200) also parse
                # as datetimes (Unix epoch), so numeric takes priority.
                if numeric_check > 0.7:
                    type_map[col] = "numeric"
                else:
                    datetime_check = pd.to_datetime(sample, errors="coerce").notna().mean()
                    if datetime_check > 0.7:
                        type_map[col] = "datetime"
                    else:
                        type_map[col] = "categorical"

        log.info("Type map: %s", type_map)
        df = _coerce_types(df, type_map)
        df = _handle_missing(df, numeric_fill, categorical_fill)

        log.info("Transform complete — shape=%s", df.shape)
        return df

    except Exception as exc:
        log.exception("Unexpected error in transform_data: %s", exc)
        return None


# ── Quick smoke-test ───────────────────────────────────────────────────────────
if __name__ == "__main__":
    sample = pd.DataFrame({
        "Order ID":    ["001", "002", "002", "004"],
        "Order Date":  ["2024-01-01", "2024-01-02", "2024-01-02", None],
        "Revenue":     ["1,200", "850", "850", "300"],
        "City  ":      [" Delhi", "Mumbai ", "Mumbai", "Bangalore"],
    })
    result = transform_data(sample, use_llm=False)
    print(result)
    print(result.dtypes)