# HSBC Monthly Bank Analyzer — Bilingual v2.4

**What's new (v2.4):**
- **Balance-driven sign inference**: sequences of lines without an explicit balance are grouped;
  when a subsequent line provides the new balance, signs for the pending lines are backfilled to match
  the net balance change (typical for consecutive 'Paid out' items printed as positives).
- Keeps column semantics (Paid out/ Paid in), keyword rules, and bilingual UI with revenue split.

If PDFs are scanned images, OCR first.
