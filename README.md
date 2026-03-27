# MANTHA 🚀
### Automated Data Pipeline Agent

> Load → Clean → Categorise → Plot → Report → Email — fully automated.

MANTHA is a modular Python data pipeline that takes a raw CSV or Excel file, runs it through an LLM-assisted processing chain, generates publication-quality charts, assembles a formatted PDF report, and emails it — all from a single command.

---

## Project Structure

```
draft-coffee-main/
├── pipeline.py        # Orchestrator — runs all steps end-to-end
├── fetcher.py         # Step 1: Load & validate CSV/Excel files
├── transformer.py     # Step 2: Clean, normalise, type-coerce data (LLM-assisted)
├── categorizer.py     # Step 3: LLM-based column categorisation & breakdown
├── plotter.py         # Step 4: Auto-generate charts (bar, line, pie, heatmap, histogram)
├── report.py          # Step 5: Build formatted PDF report (ReportLab)
├── mail.py            # Step 6: Send PDF via Gmail API (SMTP fallback)
├── requirements.txt   # All Python dependencies
```

---

## How It Works

```
your_data.csv
      │
      ▼
 fetcher.py        → validates file, loads into DataFrame
      │
      ▼
transformer.py     → snake_cases columns, removes dupes, fills nulls,
                     calls OpenRouter LLM to infer column types
      │
      ▼
categorizer.py     → LLM assigns categories to any column you choose,
                     auto-detects dimensions/measures/dates
      │
      ▼
  plotter.py       → generates bar, line, pie, heatmap & histogram PNGs
                     saved to mantha_plots/
      │
      ▼
  report.py        → assembles cover page + summary + data table + charts
                     into a branded PDF (mantha_report.pdf)
      │
      ▼
   mail.py         → emails the PDF via Gmail API
                     falls back to SMTP if API unavailable
```

---

## Quickstart

**1. Clone / download the project**
```bash
cd draft-coffee-main
```

**2. Install dependencies**
```bash
pip install -r requirements.txt
```

**3. Set your API keys**

In `transformer.py` and `categorizer.py`, replace:
```python
OPENROUTER_API_KEY = "your-openrouter-api-key"
```

**4. Run the pipeline**
```bash
# Basic run — no email
python pipeline.py --file product_financials.csv --no-email

# With email delivery
python pipeline.py --file product_financials.csv --to you@email.com

# With LLM categorisation on a specific column
python pipeline.py --file product_financials.csv --col product_name --to you@email.com
```

---

## CLI Reference

| Flag | Description | Example |
|------|-------------|---------|
| `--file` | Path to input CSV/Excel **(required)** | `--file data.csv` |
| `--to` | Recipient email address(es) | `--to a@x.com b@x.com` |
| `--col` | Column to LLM-categorise | `--col category` |
| `--cats` | Allowed category labels | `--cats Electronics Food Apparel` |
| `--no-email` | Skip email step | `--no-email` |

---

## Supported Input Formats

| Format | Extension |
|--------|-----------|
| CSV | `.csv` |
| Excel | `.xlsx`, `.xls` |
| TSV | `.tsv` |

---

## Environment Variables

You can set credentials as environment variables instead of hardcoding them:

```bash
# Windows
set OPENROUTER_API_KEY=your-key
set GMAIL_USER=you@gmail.com
set GMAIL_APP_PASSWORD=your-app-password

# Mac/Linux
export OPENROUTER_API_KEY=your-key
export GMAIL_USER=you@gmail.com
export GMAIL_APP_PASSWORD=your-app-password
```

---

## Gmail Setup

MANTHA tries Gmail API first, then falls back to SMTP.

**Option A — Gmail API (recommended)**
1. Go to [console.cloud.google.com](https://console.cloud.google.com)
2. Create a project → Enable **Gmail API**
3. Create OAuth credentials → **Desktop app** type
4. Download as `credentials.json` → place in project folder
5. Run `python mail.py` once → browser opens for auth → `token.json` is created

**Option B — SMTP fallback**
1. Go to Google Account → Security → **App Passwords**
2. Generate a password for "Mail"
3. Set `GMAIL_USER` and `GMAIL_APP_PASSWORD` as environment variables

---

## Output Files

| File | Description |
|------|-------------|
| `mantha_report.pdf` | Final formatted PDF report |
| `mantha_plots/` | Folder containing all generated chart PNGs |

---

## Dependencies

| Package | Purpose |
|---------|---------|
| `pandas` | Data loading and manipulation |
| `openpyxl` / `xlrd` | Excel file support |
| `requests` | OpenRouter API calls |
| `matplotlib` + `seaborn` | Chart generation |
| `reportlab` | PDF report creation |
| `google-auth` + `google-api-python-client` | Gmail API |

Install all at once:
```bash
pip install -r requirements.txt
```

---

## LLM Models Used

| File | Model | Purpose |
|------|-------|---------|
| `transformer.py` | `mistralai/mistral-7b-instruct` | Column type inference |
| `categorizer.py` | `deepseek/deepseek-chat:free` | Row categorisation & breakdown |

Both route through **[OpenRouter](https://openrouter.ai)** — swap models by changing `OPENROUTER_MODEL` in each file.

---

## Docker Deployment

```bash
# One-time network setup
docker network create agents-net

# Build and run
docker-compose up
```

> ⚠️ Run `python mail.py` locally first to generate `token.json` before dockerising — Gmail OAuth cannot open a browser inside a container.

---

## Troubleshooting

| Error | Fix |
|-------|-----|
| `Gmail API send failed (Client secrets must be for a web or installed app)` | Re-create credentials as **Desktop app** type in Google Console |
| `SMTP credentials not set` | Set `GMAIL_USER` and `GMAIL_APP_PASSWORD` env vars |
| `File not found` | Check the `--file` path is correct and the file exists |
| `LLM column-type inference failed` | Check `OPENROUTER_API_KEY` is valid — pipeline falls back to pandas heuristics automatically |
| `ModuleNotFoundError` | Run `pip install -r requirements.txt` |

---

## Project Name

**MANTHA** — General Data Pipeline Agent, built on the [A2A framework] as well as a mail-extension that is dockerised and can be used over a browser
