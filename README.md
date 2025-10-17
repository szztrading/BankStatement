# PDF Bank Statement Analyzer (Streamlit)

A Streamlit app to **analyze PDF bank statements**: upload 1 or more PDFs, parse transactions, filter by date range/keywords, and export CSV.

## Features
- Upload multiple **PDF** statements
- Table extraction (pdfplumber) with fallback **regex-on-text** parsing
- Standardized columns: `date`, `description`, `debit`, `credit`, `amount` (credits positive, debits negative)
- Date range filter, KPI totals, **monthly aggregation**, CSV export
- Optional **custom regex** (must include named groups: `date`, `description`, and `amount` or `debit/credit`)
- Keyword include/exclude filters

> Note: If your PDFs are **scanned images**, please OCR to a text-PDF first (e.g., with Adobe, OCRmyPDF, etc.).

## Deploy (Streamlit Cloud)
1. Push this folder to GitHub.
2. Create a new Streamlit app and point to `app.py`.
3. (Optional) Choose Europe region; Python 3.11+.

## Custom Regex Example
```
^(?P<date>\d{2}/\d{2}/\d{4})\s+(?P<description>.*?)\s+(?P<amount>[-+]?[\d,]+\.\d{2})$
```
