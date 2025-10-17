# HSBC Monthly Bank Analyzer — Bilingual v2.1 (Improved OUT detection)

Enhancements:
- Better **debit/outgoing** detection using transaction codes & keywords (DD, SO, DR, OBP, AMERICAN EXP, NOVUNA, BP).
- Exceptions for inbound transfers (e.g., 'Transfer' + 'SZZ TRADING'/'EBAY'/'PAYOUT' treated as inbound).
- Optional trailing balance parsing (ignored in calculations).
- Bilingual UI (English/中文) with full revenue split (Chiyuan 20% / Jiahan 80%).

If your PDFs are scanned images, OCR them first.
