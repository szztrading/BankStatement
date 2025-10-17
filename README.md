# HSBC Monthly Bank Analyzer (Streamlit)

A minimized Streamlit app tailored for **HSBC statement PDFs**.
- Fixed regex and date format for lines like `01 Sep 25 ... 1,234.56 7,890.12`
- Monthly filter (quick buttons: This month / Last month / Custom range)
- Categorizes **inbound**/**outbound** by simple rules (eBay payouts, transfers, DDs, card payments, suppliers, salary, other)
- Summaries by category (monthly) + detail export

> If PDF is scanned image, OCR first to a searchable PDF.
