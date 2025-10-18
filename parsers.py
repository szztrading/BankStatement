from __future__ import annotations
import io, re
from typing import Optional, List
import pdfplumber
import pandas as pd

AMT_RE = r"\(?[-+]?\d{1,3}(?:,\d{3})*(?:\.\d{2})?\)?"
LINE_HEAD_RE = re.compile(r"^(?P<date>\d{1,2}\s+[A-Za-z]{3}\s+\d{2,4})\s+(?P<rest>.+)$")

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

def _infer_from_keywords(desc: str) -> Optional[int]:
    # Return +1 for credit, -1 for debit, or None if unknown, based on keywords.
    s = (" " + (desc or "") + " ").upper()
    if " PAID IN " in s or " CR " in s or s.strip().startswith("CR "):
        return +1
    if " PAID OUT " in s:
        return -1
    if any(code in s for code in [" DD ", " SO ", " DR ", " OBP ", " AMERICAN EXP", " AMEX", " NOVUNA "]):
        return -1
    if (" BP " in s) or s.strip().startswith("BP "):
        return -1
    if (" TRANSFER " in s) and ((" SZZ TRADING " in s) or (" EBAY " in s) or (" PAYOUT " in s)):
        return +1
    return None

def parse_hsbc_pdf_bytes(data: bytes) -> pd.DataFrame:
    rows = []
    with pdfplumber.open(io.BytesIO(data)) as pdf:
        for page in pdf.pages:
            text = page.extract_text() or ""
            for raw in [ln.strip() for ln in text.splitlines() if ln.strip()]:
                U = raw.upper()
                if "BALANCE BROUGHT FORWARD" in U or "BALANCE CARRIED FORWARD" in U:
                    continue
                m = LINE_HEAD_RE.match(raw)
                if not m:
                    continue
                date_str = m.group("date").strip()
                rest = m.group("rest")
                # collect last up to 3 currency tokens on the line
                all_amts = list(re.finditer(AMT_RE, rest))
                if not all_amts:
                    continue
                last3 = all_amts[-3:]
                nums = [rest[m.start():m.end()] for m in last3]
                desc_end = last3[0].start() if last3 else len(rest)
                description = rest[:desc_end].strip()

                paid_out = paid_in = balance = None
                if len(nums) == 3:
                    paid_out, paid_in, balance = nums
                elif len(nums) == 2:
                    amt1, amt2 = nums
                    sign = _infer_from_keywords(description)
                    if sign == -1:
                        paid_out, balance = amt1, amt2
                    elif sign == +1:
                        paid_in, balance = amt1, amt2
                    else:
                        # default: treat as paid_in then balance
                        paid_in, balance = amt1, amt2
                elif len(nums) == 1:
                    paid_in = nums[0]
                else:
                    nums = nums[-3:]
                    paid_out, paid_in, balance = nums

                raw_amount = paid_in if paid_in is not None else paid_out
                amt = _to_amount(raw_amount) if raw_amount is not None else None
                if amt is None:
                    continue

                if paid_out is not None and (paid_in is None):
                    amt = -abs(amt)

                if paid_in is not None and paid_out is None:
                    sign = _infer_from_keywords(description)
                    if sign == -1:
                        amt = -abs(amt)
                    else:
                        amt = abs(amt)
                elif paid_out is not None and paid_in is not None:
                    amt_in = _to_amount(paid_in)
                    amt_out = _to_amount(paid_out)
                    if (amt_out or 0) != 0:
                        amt = -abs(amt_out or 0)
                    else:
                        amt = abs(amt_in or 0)

                rows.append({
                    "date_raw": date_str,
                    "description": description,
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
    if "PAID IN" in s or " CR " in s or s.startswith("CR "):
        return "Credit (Other)"
    if "PAID OUT" in s:
        return "Paid Out"
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
