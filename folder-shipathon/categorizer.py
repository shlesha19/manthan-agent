"""
MANTHA — Tool 3: data_categorizer.py
Uses OpenRouter LLM to breakdown/categorise rows or columns of a DataFrame
into user-defined or auto-detected categories/variables.
Includes a checker pass so every LLM output is validated before use.
Robust fallback: bad LLM responses are logged and replaced with "Uncategorized".
"""

import json
import logging
import re
import time
from typing import Optional

import pandas as pd
import urllib.request
import urllib.error

# ── Logging ────────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  [data_categorizer]  %(levelname)s — %(message)s",
)
log = logging.getLogger("data_categorizer")


# ── Config ─────────────────────────────────────────────────────────────────────
OPENROUTER_API_KEY = "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"          # ← replace / env var
OPENROUTER_MODEL   = "deepseek/deepseek-chat:free"
OPENROUTER_URL     = "https://openrouter.ai/deepseek/deepseek-chat:free"
BATCH_SIZE         = 20     # rows per LLM call — keeps prompts short
MAX_RETRIES        = 3
RETRY_DELAY        = 2      # seconds


# ── LLM call with retry ────────────────────────────────────────────────────────
def _call_llm(prompt: str) -> Optional[str]:
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            payload = json.dumps(
                {
                    "model": OPENROUTER_MODEL,
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0,
                    "max_tokens": 1024,
                }
            ).encode("utf-8")
            req = urllib.request.Request(
                OPENROUTER_URL,
                data=payload,
                headers={
                    "Authorization": f"Bearer {OPENROUTER_API_KEY}",
                    "Content-Type": "application/json",
                },
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=30) as resp:
                body = resp.read().decode("utf-8")
            parsed = json.loads(body)
            return parsed["choices"][0]["message"]["content"].strip()
        except urllib.error.HTTPError as exc:
            err_body = exc.read().decode("utf-8", errors="ignore")
            log.warning(
                "LLM call attempt %d/%d failed: %s %s",
                attempt,
                MAX_RETRIES,
                exc,
                err_body,
            )
        except Exception as exc:
            log.warning("LLM call attempt %d/%d failed: %s", attempt, MAX_RETRIES, exc)
        if attempt < MAX_RETRIES:
            time.sleep(RETRY_DELAY)
    log.error("All LLM retries exhausted.")
    return None


# ── Output checker ─────────────────────────────────────────────────────────────
def _parse_and_check(raw: str, expected_count: int, allowed_categories: Optional[list]) -> list:
    """
    Parse LLM JSON output and validate:
    - Must be a list of exactly `expected_count` strings.
    - Each item must be in `allowed_categories` if provided.
    Returns list of categories, substituting "Uncategorized" for bad values.
    """
    try:
        clean = re.sub(r"```[a-z]*\n?", "", raw).strip("`").strip()
        parsed = json.loads(clean)
        if not isinstance(parsed, list):
            raise ValueError("LLM did not return a JSON list.")
    except Exception as exc:
        log.warning("LLM output parse failed (%s). Raw: %r", exc, raw[:200])
        return ["Uncategorized"] * expected_count

    # Pad or truncate to expected length
    if len(parsed) != expected_count:
        log.warning(
            "LLM returned %d categories, expected %d. Padding/truncating.",
            len(parsed), expected_count,
        )
        parsed = (parsed + ["Uncategorized"] * expected_count)[:expected_count]

    # Validate against allowed set
    if allowed_categories:
        allowed_set = {c.lower() for c in allowed_categories}
        validated = []
        for item in parsed:
            if str(item).lower() in allowed_set:
                validated.append(str(item))
            else:
                log.warning("'%s' not in allowed categories — marking Uncategorized.", item)
                validated.append("Uncategorized")
        return validated

    return [str(x) for x in parsed]


# ── Batch categorisation ───────────────────────────────────────────────────────
def _categorise_batch(
    texts: list[str],
    categories: Optional[list[str]],
    context: str,
) -> list[str]:
    cat_instruction = (
        f"Categories to choose from: {categories}.\n"
        if categories
        else "Infer the most appropriate category for each item.\n"
    )
    prompt = (
        f"You are a data categorisation assistant. {context}\n"
        f"{cat_instruction}"
        f"For each item in the list below, return its category.\n"
        f"Return ONLY a JSON array of strings (same length as input). No explanation.\n\n"
        f"Items:\n{json.dumps(texts, ensure_ascii=False)}"
    )
    raw = _call_llm(prompt)
    if raw is None:
        return ["Uncategorized"] * len(texts)
    return _parse_and_check(raw, len(texts), categories)


# ── Public API ─────────────────────────────────────────────────────────────────
def categorise_column(
    df: pd.DataFrame,
    source_column: str,
    output_column: str = "category",
    categories: Optional[list[str]] = None,
    context: str = "Categorise the following data items.",
) -> pd.DataFrame:
    """
    Add a new column to `df` with LLM-assigned categories based on `source_column`.

    Parameters
    ----------
    df            : Input DataFrame (from data_transformer).
    source_column : Column whose values will be categorised.
    output_column : Name of the new category column.
    categories    : Allowed category list. If None, LLM chooses freely.
    context       : Domain hint for the LLM (e.g. "These are product descriptions").

    Returns
    -------
    DataFrame with `output_column` added.
    """
    if source_column not in df.columns:
        log.error("Source column '%s' not found in DataFrame.", source_column)
        return df

    values = df[source_column].fillna("").astype(str).tolist()
    all_categories: list[str] = []

    log.info(
        "Categorising %d rows from '%s' in batches of %d …",
        len(values), source_column, BATCH_SIZE,
    )

    for i in range(0, len(values), BATCH_SIZE):
        batch = values[i : i + BATCH_SIZE]
        result = _categorise_batch(batch, categories, context)
        all_categories.extend(result)
        log.info("Batch %d/%d done.", i // BATCH_SIZE + 1, -(-len(values) // BATCH_SIZE))

    df[output_column] = all_categories
    log.info("Categorisation complete. Value counts:\n%s", df[output_column].value_counts().to_string())
    return df


def auto_breakdown(
    df: pd.DataFrame,
    context: str = "General data pipeline",
) -> dict:
    """
    Ask the LLM to suggest a breakdown structure for the entire DataFrame:
    which columns map to which variable types (dimension, measure, date, id, text).

    Returns a dict like:
    {
      "dimensions": ["city", "category"],
      "measures":   ["revenue", "quantity"],
      "dates":      ["order_date"],
      "ids":        ["order_id"],
    }
    """
    schema_summary = {col: str(df[col].dtype) for col in df.columns}
    sample = df.head(5).to_dict(orient="records")

    prompt = (
        f"You are a data-engineering assistant. Context: {context}.\n"
        f"Given this DataFrame schema and sample, classify each column into: "
        f"'dimensions', 'measures', 'dates', 'ids', or 'text'.\n\n"
        f"Schema: {json.dumps(schema_summary)}\n"
        f"Sample rows: {json.dumps(sample, default=str)}\n\n"
        f"Return ONLY a JSON dict with keys: dimensions, measures, dates, ids, text. "
        f"Each key maps to a list of column names. No explanation."
    )

    raw = _call_llm(prompt)
    if raw is None:
        return {}

    try:
        clean = re.sub(r"```[a-z]*\n?", "", raw).strip("`").strip()
        breakdown = json.loads(clean)
        log.info("Auto-breakdown result: %s", breakdown)
        return breakdown
    except Exception as exc:
        log.warning("Could not parse auto_breakdown response: %s", exc)
        return {}


# ── Quick smoke-test ───────────────────────────────────────────────────────────
if __name__ == "__main__":
    sample_df = pd.DataFrame({
        "product": ["Laptop", "Rice 5kg", "Running Shoes", "Bread", "Headphones"],
        "revenue": [55000, 400, 3200, 60, 8500],
    })
    result = categorise_column(
        sample_df,
        source_column="product",
        output_column="product_category",
        categories=["Electronics", "Food", "Apparel", "Other"],
        context="These are retail product names. Assign each to the best category.",
    )
    print(result)
