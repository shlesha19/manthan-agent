"""
MANTHA — pipeline_runner.py
Orchestrates the full pipeline:
  1. Fetch      → data_fetcher.py
  2. Transform  → data_transformer.py
  3. Categorise → data_categorizer.py
  4. Plot       → plotter.py
  5. Report     → report_creator.py
  6. Send       → gmail_tool.py

Usage:
  python pipeline_runner.py --file data.csv --to analyst@example.com
"""

import argparse
import logging
import sys

log = logging.getLogger("pipeline_runner")
logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s  [pipeline]  %(levelname)s — %(message)s")

# ── Tool imports ───────────────────────────────────────────────────────────────
from fetcher import fetch_data
from transformer import transform_data
from categorizer import categorise_column, auto_breakdown
from plotter        import auto_plot
from report   import create_report
from mail       import send_report


def run_pipeline(
    filepath:       str,
    recipients:     list[str],
    source_column:  str | None = None,
    categories:     list[str] | None = None,
    output_pdf:     str = "mantha_report.pdf",
    output_plots:   str = "mantha_plots",
    send_email:     bool = True,
):
    log.info("═" * 60)
    log.info("MANTHA pipeline starting  —  file: %s", filepath)
    log.info("═" * 60)

    # ── Step 1: Fetch ──────────────────────────────────────────────────────────
    df = fetch_data(filepath)
    if df is None:
        log.error("Pipeline aborted: could not load data.")
        return False

    # ── Step 2: Transform ──────────────────────────────────────────────────────
    df = transform_data(df, use_llm=True)
    if df is None:
        log.error("Pipeline aborted: transformation failed.")
        return False

    # ── Step 3: Categorise (optional) ─────────────────────────────────────────
    breakdown = auto_breakdown(df, context="General data pipeline")

    if source_column and source_column in df.columns:
        df = categorise_column(
            df,
            source_column=source_column,
            output_column="llm_category",
            categories=categories,
            context="Categorise these data values meaningfully.",
        )

    # ── Step 4: Plot ───────────────────────────────────────────────────────────
    plot_paths = auto_plot(df, breakdown=breakdown, output_dir=output_plots)

    # ── Step 5: Report ─────────────────────────────────────────────────────────
    summary = (
        f"Pipeline run completed successfully.\n"
        f"Rows processed: {len(df):,}  |  Columns: {len(df.columns)}\n"
        f"Plots generated: {len(plot_paths)}\n"
        f"Breakdown: {breakdown}"
    )
    pdf_path = create_report(
        report_title="MANTHA — Data Pipeline Report",
        report_subtitle=f"Source: {filepath}",
        summary_text=summary,
        dataframes=[("Processed Data", df)],
        plot_paths=plot_paths,
        output_path=output_pdf,
    )
    if pdf_path is None:
        log.error("Pipeline aborted: PDF generation failed.")
        return False

    # ── Step 6: Send ───────────────────────────────────────────────────────────
    if send_email and recipients:
        sent = send_report(
            to=recipients,
            subject="MANTHA — Pipeline Report Ready",
            summary=summary,
            attachment_paths=[pdf_path],
        )
        log.info("Email sent: %s", sent)

    log.info("═" * 60)
    log.info("Pipeline complete. PDF: %s", pdf_path)
    log.info("═" * 60)
    return True


# ── CLI ────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="MANTHA Data Pipeline")
    parser.add_argument("--file", required=True, help="Path to CSV/Excel input file")
    parser.add_argument("--to",     nargs="+", default=[], help="Recipient email(s)")
    parser.add_argument("--col",    default=None, help="Column to categorise with LLM")
    parser.add_argument("--cats",   nargs="+", default=None, help="Allowed category labels")
    parser.add_argument("--no-email", action="store_true", help="Skip email delivery")
    args = parser.parse_args()

    ok = run_pipeline(
        filepath=args.file,
        recipients=args.to,
        source_column=args.col,
        categories=args.cats,
        send_email=not args.no_email,
    )
    sys.exit(0 if ok else 1)