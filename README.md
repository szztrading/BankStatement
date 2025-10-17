# HSBC Monthly Bank Analyzer — Bilingual (English/中文)

A Streamlit app to analyze **HSBC bank statement PDFs**, categorize transactions, and **split all inbound credits**:
- **Chiyuan — 20%**
- **Jiahan — 80%**

The UI is fully bilingual. Use the **Language / 语言** toggle to switch.

## Features / 功能
- Fixed HSBC parsing for lines like `01 Sep 25 ... 1,234.56 7,890.12`
- Month quick-select: **This Month / Last Month** or custom range
- Categorization (eBay payout/Transfer In, AMEX, NOVUNA DD, Supplier, Salary, etc.)
- **Inbound split** per-transaction and per-month totals
- CSV export includes split columns
- 全中文界面可切换，含分成列导出

> If your PDFs are scanned images, run OCR first to make them text-searchable. / 若为扫描 PDF，请先 OCR。

## Deploy / 部署
1. Upload this folder to GitHub. / 上传到 GitHub。
2. On Streamlit Cloud, point to `app.py`. / 部署指向 `app.py`。
3. Python **3.11+**.

