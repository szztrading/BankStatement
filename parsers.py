from __future__ import annotations
import io, re
from typing import Optional, List, Dict, Any
import pdfplumber
import pandas as pd

# Require decimals to avoid phone numbers / ids; allow parentheses for negatives
AMT_RE = r"\(?[-+]?\d{1,3}(?:,\d{3})*\.\d{2}\)?"
DATE_RE = re.compile(r"^(?P<date>\d{1,2}\s+[A-Za-z]{3}\s+\d{2,4})\s+(?P<rest>.+)$", re.I)

SKIP_PATTERNS = [
    r"BALANCE\s+BROUGHT\s+FORWARD", r"BALANCE\s+CARRIED\s+FORWARD",
    r"\bCALLING\b", r"\bIF\s+YOU[’']?RE\s+CALLING\b", r"\b8AM\s+TO\b", r"\bMONDAY\b", r"\bFRIDAY\b",
    r"\b0345[0-9 ]+\b", r"\+\s?44\s?\d", r"\bCONTACT\s+US\b", r"\bHELP\b", r"\bPAGE\s+\d+",
]

def _skip_line(s: str) -> bool:
    u = s.upper()
    for pat in SKIP_PATTERNS:
        if re.search(pat, u, flags=re.I):
            return True
    return False

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

def _kw_sign(desc: str) -> Optional[int]:
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
    entries: List[Dict[str, Any]] = []
    with pdfplumber.open(io.BytesIO(data)) as pdf:
        current_date = None
        for page in pdf.pages:
            text = page.extract_text() or ""
            for raw in [ln.strip() for ln in text.splitlines() if ln.strip()]:
                if _skip_line(raw):
                    continue
                m = DATE_RE.match(raw)
                if m:
                    current_date = m.group("date").strip()
                    rest = m.group("rest")
                else:
                    if current_date is None:
                        continue
                    rest = raw

                # Identify last up to 3 monetary tokens (strict decimals)
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
                    sign = _kw_sign(description)
                    if sign == -1:
                        paid_out, balance = amt1, amt2
                    elif sign == +1:
                        paid_in, balance = amt1, amt2
                    else:
                        paid_out, balance = amt1, amt2  # conservative
                elif len(nums) == 1:
                    sign = _kw_sign(description)
                    if sign == -1:
                        paid_out = nums[0]
                    else:
                        paid_in = nums[0]
                else:
                    nums = nums[-3:]
                    paid_out, paid_in, balance = nums

                amount = None
                if paid_out is not None and paid_in is not None:
                    out_v = _to_amount(paid_out) or 0.0
                    in_v  = _to_amount(paid_in) or 0.0
                    if abs(out_v) > 0:
                        amount = -abs(out_v)
                    elif abs(in_v) > 0:
                        amount = abs(in_v)
                    else:
                        continue
                else:
                    raw_amount = paid_in if paid_in is not None else paid_out
                    if raw_amount is None:
                        continue
                    v = _to_amount(raw_amount)
                    if v is None:
                        continue
                    if paid_out is not None:
                        amount = -abs(v)
                    else:
                        amount = abs(v)

                entries.append({
                    "date_raw": current_date,
                    "description": description,
                    "amount": amount,
                })

    if not entries:
        return pd.DataFrame(columns=["date","description","debit","credit","amount"])

    df = pd.DataFrame(entries)
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
