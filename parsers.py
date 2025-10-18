from __future__ import annotations
import io, re
from typing import Optional, List, Dict, Any
import pdfplumber
import pandas as pd

AMT_RE = r"\(?[-+]?\d{1,3}(?:,\d{3})*(?:\.\d{2})?\)?"
DATE_RE = re.compile(r"^(?P<date>\d{1,2}\s+[A-Za-z]{3}\s+\d{2,4})\s+(?P<rest>.+)$")

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
                U = raw.upper()
                if "BALANCE BROUGHT FORWARD" in U or "BALANCE CARRIED FORWARD" in U:
                    continue
                m = DATE_RE.match(raw)
                if m:
                    current_date = m.group("date").strip()
                    rest = m.group("rest")
                else:
                    if current_date is None:
                        continue
                    rest = raw

                # find numeric tokens (use last up to 3: [Paid out] [Paid in] [Balance])
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
                        # unknown: treat as amount + balance; sign to be inferred by balance later
                        paid_in, balance = amt1, amt2  # provisional
                elif len(nums) == 1:
                    paid_in = nums[0]  # provisional
                else:
                    nums = nums[-3:]
                    paid_out, paid_in, balance = nums

                amount_raw = paid_in if paid_in is not None else paid_out
                amount_val = _to_amount(amount_raw) if amount_raw is not None else None
                bal_val = _to_amount(balance) if balance is not None else None

                entries.append({
                    "date_raw": current_date,
                    "description": description,
                    "amount_abs": abs(amount_val) if amount_val is not None else None,
                    "has_paid_out": paid_out is not None and paid_in is None,
                    "has_paid_in": paid_in is not None and paid_out is None,
                    "has_both_cols": paid_out is not None and paid_in is not None,
                    "balance": bal_val,
                    "kw_sign": _kw_sign(description),
                })

    if not entries:
        return pd.DataFrame(columns=["date","description","amount","debit","credit"])

    # Pass 1: date parsing
    for e in entries:
        e["date"] = pd.to_datetime(e["date_raw"], format="%d %b %y", errors="coerce")
        if pd.isna(e["date"]):
            e["date"] = pd.to_datetime(e["date_raw"], format="%d %b %Y", errors="coerce")

    # Pass 2: sign resolution with balance-driven segments
    out_rows = []
    last_balance = None
    pending = []  # list of indices for entries since last known balance
    for idx, e in enumerate(entries):
        # skip non-dated lines that failed parsing
        if pd.isna(e["date"]):
            continue
        amt_abs = e["amount_abs"]
        if amt_abs is None:
            continue

        signed = None

        if e["has_both_cols"]:
            # choose non-zero; out takes precedence
            # but we don't have zeros here; assume paid_out means debit
            signed = -amt_abs  # conservative
        elif e["has_paid_out"]:
            signed = -amt_abs
        elif e["has_paid_in"]:
            signed = +amt_abs
        else:
            # provisional; decide via balance or keyword later
            signed = None

        # If this entry has a balance, we can reconcile the segment
        if e["balance"] is not None:
            # Include current in segment
            segment = pending + [(idx, signed)]
            # Compute known sum
            known = sum(v for (_, v) in segment if v is not None)
            unknown_count = sum(1 for (_, v) in segment if v is None)

            if last_balance is None:
                # No prior balance; use keywords for unknowns defaulting to credit
                for (j, v) in segment:
                    if v is None:
                        sign = entries[j]["kw_sign"]
                        entries[j]["signed"] = (amt := entries[j]["amount_abs"]) * (1 if sign == +1 else -1 if sign == -1 else +1)
                    else:
                        entries[j]["signed"] = v
                last_balance = e["balance"]
            else:
                target_delta = e["balance"] - last_balance
                # Assign unknowns to make known + assigned == target_delta
                # If multiple unknowns, assign all the same sign matching (target_delta - known)
                remaining = target_delta - known
                for (j, v) in segment:
                    if v is None:
                        amt = entries[j]["amount_abs"]
                        # If remaining is negative -> debit, positive -> credit
                        s = -1 if remaining < 0 else +1
                        entries[j]["signed"] = s * amt
                        remaining -= entries[j]["signed"]
                    else:
                        entries[j]["signed"] = v
                last_balance = e["balance"]

            # Flush segment to out_rows
            for (j, _) in segment:
                ee = entries[j]
                out_rows.append({
                    "date": ee["date"],
                    "description": ee["description"],
                    "amount": ee["signed"],
                })
            pending = []
        else:
            # no balance yet; hold in pending
            pending.append((idx, signed))

    # Flush remaining pending (no trailing balance): fall back to keywords or assume credits
    for (j, v) in pending:
        ee = entries[j]
        amt = ee["amount_abs"]
        if amt is None:
            continue
        if v is not None:
            signed = v
        else:
            sign = ee["kw_sign"]
            signed = amt * (1 if sign == +1 else -1 if sign == -1 else +1)
        out_rows.append({"date": ee["date"], "description": ee["description"], "amount": signed})

    df = pd.DataFrame(out_rows)
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
