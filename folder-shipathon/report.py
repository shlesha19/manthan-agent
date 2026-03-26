"""
MANTHA — Tool 5: report_creator.py
Assembles a formatted PDF report from:
  - A summary dict / text (LLM-generated or manual)
  - A DataFrame (rendered as a table)
  - Plot image paths (from plotter.py)
Then hands the PDF path to gmail_tool.py for delivery.
"""

import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Optional

import pandas as pd
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.platypus import (
    HRFlowable,
    Image,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

# ── Logging ────────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  [report_creator]  %(levelname)s — %(message)s",
)
log = logging.getLogger("report_creator")


# ── Brand colours ──────────────────────────────────────────────────────────────
PRIMARY   = colors.HexColor("#1A1A2E")
ACCENT    = colors.HexColor("#4C72B0")
LIGHT_BG  = colors.HexColor("#F5F5F5")
WHITE     = colors.white
TEXT_DARK = colors.HexColor("#2D2D2D")


# ── Style helpers ──────────────────────────────────────────────────────────────
def _styles():
    base = getSampleStyleSheet()
    return {
        "title": ParagraphStyle(
            "ManthaTitle",
            fontSize=26, fontName="Helvetica-Bold",
            textColor=WHITE, alignment=TA_CENTER,
            spaceAfter=6,
        ),
        "subtitle": ParagraphStyle(
            "ManthaSubtitle",
            fontSize=12, fontName="Helvetica",
            textColor=colors.HexColor("#CCCCCC"), alignment=TA_CENTER,
            spaceAfter=4,
        ),
        "section": ParagraphStyle(
            "ManthaSection",
            fontSize=14, fontName="Helvetica-Bold",
            textColor=ACCENT, spaceBefore=14, spaceAfter=6,
        ),
        "body": ParagraphStyle(
            "ManthaBody",
            fontSize=10, fontName="Helvetica",
            textColor=TEXT_DARK, leading=16, spaceAfter=8,
        ),
        "caption": ParagraphStyle(
            "ManthaCaption",
            fontSize=8, fontName="Helvetica-Oblique",
            textColor=colors.grey, alignment=TA_CENTER, spaceAfter=10,
        ),
    }


# ── Cover page ─────────────────────────────────────────────────────────────────
def _cover_block(title: str, subtitle: str, styles: dict) -> list:
    elements = []
    # Dark banner
    banner = Table(
        [[Paragraph(title, styles["title"])],
         [Paragraph(subtitle, styles["subtitle"])],
         [Paragraph(datetime.now().strftime("Generated: %d %B %Y, %H:%M"), styles["subtitle"])]],
        colWidths=[16 * cm],
    )
    banner.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), PRIMARY),
        ("TOPPADDING",    (0, 0), (-1, -1), 24),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 24),
        ("LEFTPADDING",   (0, 0), (-1, -1), 16),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 16),
        ("ROWBACKGROUNDS", (0, 0), (-1, -1), [PRIMARY]),
    ]))
    elements.append(banner)
    elements.append(Spacer(1, 0.6 * cm))
    elements.append(HRFlowable(width="100%", thickness=2, color=ACCENT))
    elements.append(Spacer(1, 0.4 * cm))
    return elements


# ── Summary section ────────────────────────────────────────────────────────────
def _summary_block(summary_text: str, styles: dict) -> list:
    elements = []
    elements.append(Paragraph("Executive Summary", styles["section"]))
    elements.append(HRFlowable(width="40%", thickness=1, color=ACCENT))
    elements.append(Spacer(1, 0.3 * cm))
    # Replace newlines with <br/> for ReportLab
    html_text = summary_text.replace("\n", "<br/>")
    elements.append(Paragraph(html_text, styles["body"]))
    return elements


# ── DataFrame table ────────────────────────────────────────────────────────────
def _df_block(df: pd.DataFrame, title: str, styles: dict, max_rows: int = 20) -> list:
    elements = []
    elements.append(Paragraph(title, styles["section"]))
    elements.append(HRFlowable(width="40%", thickness=1, color=ACCENT))
    elements.append(Spacer(1, 0.3 * cm))

    display = df.head(max_rows)
    col_count = len(display.columns)
    page_width = 16 * cm
    col_width = page_width / col_count

    # Header + data rows
    table_data = [list(display.columns)] + display.astype(str).values.tolist()

    tbl = Table(table_data, colWidths=[col_width] * col_count, repeatRows=1)
    tbl.setStyle(TableStyle([
        # Header
        ("BACKGROUND",   (0, 0), (-1, 0), PRIMARY),
        ("TEXTCOLOR",    (0, 0), (-1, 0), WHITE),
        ("FONTNAME",     (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE",     (0, 0), (-1, 0), 9),
        ("ALIGN",        (0, 0), (-1, 0), "CENTER"),
        ("BOTTOMPADDING",(0, 0), (-1, 0), 8),
        ("TOPPADDING",   (0, 0), (-1, 0), 8),
        # Body
        ("FONTNAME",     (0, 1), (-1, -1), "Helvetica"),
        ("FONTSIZE",     (0, 1), (-1, -1), 8),
        ("ALIGN",        (0, 1), (-1, -1), "LEFT"),
        ("ROWBACKGROUNDS",(0, 1), (-1, -1), [WHITE, LIGHT_BG]),
        ("TOPPADDING",   (0, 1), (-1, -1), 5),
        ("BOTTOMPADDING",(0, 1), (-1, -1), 5),
        # Grid
        ("GRID",         (0, 0), (-1, -1), 0.4, colors.HexColor("#DDDDDD")),
        ("BOX",          (0, 0), (-1, -1), 0.8, ACCENT),
    ]))
    elements.append(tbl)

    if len(df) > max_rows:
        elements.append(Paragraph(
            f"(Showing first {max_rows} of {len(df)} rows)", styles["caption"]
        ))
    elements.append(Spacer(1, 0.5 * cm))
    return elements


# ── Plot images ────────────────────────────────────────────────────────────────
def _plots_block(plot_paths: list[str], styles: dict) -> list:
    elements = []
    elements.append(Paragraph("Data Visualisations", styles["section"]))
    elements.append(HRFlowable(width="40%", thickness=1, color=ACCENT))
    elements.append(Spacer(1, 0.3 * cm))

    for path in plot_paths:
        if not os.path.exists(path):
            log.warning("Plot not found, skipping: %s", path)
            continue
        try:
            img = Image(path, width=14 * cm, height=8 * cm, kind="proportional")
            elements.append(img)
            caption = Path(path).stem.replace("_", " ").title()
            elements.append(Paragraph(caption, styles["caption"]))
            elements.append(Spacer(1, 0.4 * cm))
        except Exception as exc:
            log.warning("Could not embed image %s: %s", path, exc)
    return elements


# ── Public API ─────────────────────────────────────────────────────────────────
def create_report(
    report_title:   str             = "MANTHA — Data Pipeline Report",
    report_subtitle: str            = "Automated Analysis",
    summary_text:   str             = "",
    dataframes:     Optional[list[tuple[str, pd.DataFrame]]] = None,
    plot_paths:     Optional[list[str]]  = None,
    output_path:    str             = "mantha_report.pdf",
    max_table_rows: int             = 20,
) -> Optional[str]:
    """
    Build and save a formatted PDF report.

    Parameters
    ----------
    report_title    : Main title shown on the cover banner.
    report_subtitle : Sub-title / pipeline run description.
    summary_text    : Executive summary paragraph(s).
    dataframes      : List of (section_title, DataFrame) tuples.
    plot_paths      : List of PNG file paths from plotter.py.
    output_path     : Destination PDF path.
    max_table_rows  : Max rows to render per DataFrame table.

    Returns
    -------
    Path to the saved PDF, or None on failure.
    """
    try:
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        styles = _styles()

        doc = SimpleDocTemplate(
            output_path,
            pagesize=A4,
            leftMargin=2 * cm, rightMargin=2 * cm,
            topMargin=2 * cm, bottomMargin=2 * cm,
        )

        story = []

        # Cover
        story.extend(_cover_block(report_title, report_subtitle, styles))

        # Summary
        if summary_text:
            story.extend(_summary_block(summary_text, styles))
            story.append(Spacer(1, 0.5 * cm))

        # Data tables
        if dataframes:
            story.append(PageBreak())
            story.append(Paragraph("Data Overview", styles["section"]))
            for section_title, df in dataframes:
                story.extend(_df_block(df, section_title, styles, max_table_rows))

        # Plots
        if plot_paths:
            story.append(PageBreak())
            story.extend(_plots_block(plot_paths, styles))

        # Footer note
        story.append(Spacer(1, 1 * cm))
        story.append(HRFlowable(width="100%", thickness=1, color=ACCENT))
        story.append(Paragraph(
            f"MANTHA Pipeline · {datetime.now().strftime('%Y-%m-%d %H:%M')} · Confidential",
            _styles()["caption"],
        ))

        doc.build(story)
        log.info("Report saved: %s", output_path)
        return output_path

    except Exception as exc:
        log.exception("create_report failed: %s", exc)
        return None


# ── Quick smoke-test ───────────────────────────────────────────────────────────
# if __name__ == "__main__":
#     import numpy as np
#     rng = np.random.default_rng(0)
#     df = pd.DataFrame({
#         "city":    rng.choice(["Delhi", "Mumbai", "Bangalore"], 30),
#         "revenue": rng.integers(1000, 50000, 30),
#         "qty":     rng.integers(1, 100, 30),
#     })
#     path = create_report(
#         report_title="MANTHA Test Report",
#         report_subtitle="Smoke Test Run",
#         summary_text=(
#             "This is a test run of the MANTHA pipeline report generator.\n"
#             "All systems nominal. Data was loaded, transformed, and plotted successfully."
#         ),
#         dataframes=[("Sample Data", df)],
#         plot_paths=[],
#         output_path="test_report.pdf",
#     )
#     print("PDF created at:", path)
    

# ── Quick smoke-test ───────────────────────────────────────────────────────────
if __name__ == "__main__":
    import pandas as pd
    import os
    import sys

    # Accept the CSV path as a CLI argument: python report.py path/to/data.csv
    local_csv_file = sys.argv[1] if len(sys.argv) > 1 else "data.csv"

    if not os.path.exists(local_csv_file):
        print(f"Error: Could not find '{local_csv_file}'.")
    else:
        print(f"Loading data from {local_csv_file}...")
        
        # Read the local file into a Pandas DataFrame
        df = pd.read_csv(local_csv_file)

        # Pass that real data into your report generator
        path = create_report(
            report_title="MANTHA Local Data Test",
            report_subtitle=f"Source: {local_csv_file}",
            summary_text=(
                "This is a local smoke test using real CSV data instead of Numpy.\n"
                "Review the table below to ensure columns and rows render correctly."
            ),
            dataframes=[("Analyzed Local Data", df)],
            plot_paths=[], # Add local image paths like ["my_chart.png"] if you have them
            output_path="real_data_test_report.pdf",
        )
        print("PDF created at:", path)