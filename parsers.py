from __future__ import annotations
import io, re
from typing import Optional, List
import pdfplumber
import pandas as pd

LINE_RE = re.compile(
    r"^(?P<date>\d{1,2}\s+[A-Za-z]{3}\s+\d{2,4})\s+(?P<description>.+?)\s+(?P<amount>\(?[-+]?\d{1,3}(?:,\d{3})*(?:\.\d{2})?\)?)\s*(?:£?\s*\d{1,3}(?:,\d{3})*(?:\.\d{2})?)?$"
)

def _to_amount(s: str) -> float | None:
    if s is None:
        return None
    s = str(s).strip().replace(",", "")
    if not s:
        return None
    neg = False
    if s.startswith("(") and s.endswith(")"):
        neg = True
        s = s[1:-1]
    try:
        v = float(s)
        return -v if neg else v
    except Exception:
        return None

def parse_hsbc_pdf_bytes(data: bytes) -> pd.DataFrame:
    rows = []
    with pdfplumber.open(io.BytesIO(data)) as pdf:
        for page in pdf.pages:
            text = page.extract_text() or ""
            for ln in [ln.strip() for ln in text.splitlines() if ln.strip()]:
                m = LINE_RE.match(ln)
                if not m:
                    continue
                d = m.groupdict()
                date_str = d["date"].strip()
                amt = _to_amount(d["amount"])
                if amt is None:
                    continue
                rows.append({
                    "date_raw": date_str,
                    "description": d["description"].strip(),
                    "amount": amt,
                })
    if not rows:
        return pd.DataFrame(columns=["date","description","amount","debit","credit"])
    df = pd.DataFrame(rows)
    df["date"] = pd.to_datetime(df["date_raw"], format="%d %b %y", errors="coerce")
    bad = df["date"].isna()
    if bad.any():
        df.loc[bad, "date"] = pd.to_datetime(df.loc[bad, "date_raw"], format="%d %b %Y", errors="coerce")
    df = df.dropna(subset=["date"]).copy()
    df["debit"] = df["amount"].apply(lambda x: -x if x < 0 else 0.0)
    df["credit"] = df["amount"].apply(lambda x: x if x > 0 else 0.0)
    return df[["date","description","debit","credit","amount"]]

def categorize(description: str, amount: float) -> str:
    s = (description or "").upper()
    inbound = amount > 0
    if "EBAY" in s or "SZZ TRADING" in s or "PAYOUT" in s or ("TRANSFER" in s and inbound):
        return "eBay payout/Transfer In"
    if "CR " in s or s.startswith("CR "):
        return "Credit (Other)"
    if "NOVUNA" in s:
        return "DD NOVUNA"
    if "AMERICAN EXP" in s or "AMEX" in s:
        return "Card Payment AMEX"
    if "TRI-TECH" in s or "INDUSTRIA" in s:
        return "Supplier Payment"
    if "SALARY" in s or s.startswith("SO "):
        return "Salary/Standing Order Out"
    if "BP " in s and not inbound:
        return "Bill Payment Out"
    if "DR " in s and not inbound:
        return "Debit Out"
    return "Other In" if inbound else "Other Out"
