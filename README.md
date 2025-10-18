# HSBC Monthly Bank Analyzer — Bilingual v2.5

**Fixes**
- Ignore footer/help lines (phone numbers, opening hours, guidance text).
- Stricter amount token: must have **two decimals** (prevents phone numbers like 03457... from being treated as money).
- More tolerant skip for balance headers: `BALANCE BROUGHT FORWARD`, `BALANCE CARRIED FORWARD` (with punctuation).
- Keeps Paid out / Paid in column semantics, balance-driven backfill, bilingual UI, and revenue split.
