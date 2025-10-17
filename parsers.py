from __future__ import annotations
import io
import re
from typing import Optional, Tuple
from dataclasses import dataclass

import pdfplumber
import pandas as pd
from dateutil import parser as dtparser

AMOUNT_RE = re.compile(r"[-+]?\d{1,3}(?:,\d{3})*(?:\.\d{2})?")
DATE_CANDIDATES = [
    r"\b\d{4}[-/]\d{1,2}[-/]\d{1,2}\b",   # 2025-10-17 / 2025/10/17
    r"\b\d{1,2}[-/]\d{1,2}[-/]\d{2,4}\b", # 17/10/2025, 17-10-25
]
DATE_RES = [re.compile(p) for p in DATE_CANDIDATES]

@dataclass
class ParseConfig:
    date_column_hints: Tuple[str, ...] = ("date",)
    desc_column_hints: Tuple[str, ...] = ("description", "details", "narrative")
    debit_hints: Tuple[str, ...] = ("debit", "withdrawal", "out")
    credit_hints: Tuple[str, ...] = ("credit", "deposit", "in")
    amount_hints: Tuple[str, ...] = ("amount", "value")
    custom_regex: Optional[str] = None
    custom_date_format: Optional[str] = None

def _parse_date(s: str, cfg: ParseConfig) -> Optional[pd.Timestamp]:
    s = s.strip()
    if not s:
        return None
    try:
        if cfg.custom_date_format:
            return pd.to_datetime(s, format=cfg.custom_date_format, errors="coerce")
        return pd.to_datetime(dtparser.parse(s, dayfirst=True, yearfirst=False))
    except Exception:
        return None

def _to_amount(x) -> Optional[float]:
    if x is None:
        return None
    if isinstance(x, (int, float)):
        return float(x)
    s = str(x).strip()
    if s == "":
        return None
    neg = False
    if s.startswith("(") and s.endswith(")"):
        neg = True
        s = s[1:-1]
    s = s.replace(",", "")
    m = AMOUNT_RE.search(s)
    if not m:
        return None
    val = float(m.group(0))
    return -val if neg or s.startswith("-") else val

def _standardize_columns(df: pd.DataFrame, cfg: ParseConfig) -> pd.DataFrame:
    cols = {c: str(c).strip().lower() for c in df.columns}
    df = df.rename(columns=cols)

    def pick(hints: Tuple[str, ...]) -> Optional[str]:
        for c in df.columns:
            for h in hints:
                if h in c:
                    return c
        return None

    date_col = pick(cfg.date_column_hints)
    desc_col = pick(cfg.desc_column_hints)
    debit_col = pick(cfg.debit_hints)
    credit_col = pick(cfg.credit_hints)
    amount_col = pick(cfg.amount_hints)

    out = pd.DataFrame()
    if date_col is not None:
        out["date"] = df[date_col].apply(lambda x: _parse_date(str(x), cfg))
    else:
        out["date"] = pd.NaT

    if desc_col is not None:
        out["description"] = df[desc_col].astype(str)
    else:
        non_num_cols = [c for c in df.columns if not pd.api.types.is_numeric_dtype(df[c])]
        out["description"] = df[non_num_cols].astype(str).agg(" ".join, axis=1)

    deb = df[debit_col].apply(_to_amount) if (debit_col in df.columns) else None
    cre = df[credit_col].apply(_to_amount) if (credit_col in df.columns) else None
    amt = df[amount_col].apply(_to_amount) if (amount_col in df.columns) else None

    if amt is not None:
        out["amount"] = amt
        if deb is not None:
            out.loc[pd.notna(deb) & (deb != 0), "amount"] = -deb[pd.notna(deb)]
        if cre is not None:
            out.loc[pd.notna(cre) & (cre != 0), "amount"] = cre[pd.notna(cre)]
    else:
        amount = pd.Series([None]*len(df), dtype="float")
        if deb is not None:
            amount = pd.to_numeric(deb, errors="coerce").fillna(0) * -1
        if cre is not None:
            amount = amount.add(pd.to_numeric(cre, errors="coerce").fillna(0), fill_value=0)
        out["amount"] = amount

    out["debit"] = out["amount"].apply(lambda x: -x if x is not None and x < 0 else 0)
    out["credit"] = out["amount"].apply(lambda x: x if x is not None and x > 0 else 0)

    return out

def parse_pdf_bytes(data: bytes, cfg: Optional[ParseConfig] = None) -> pd.DataFrame:
    cfg = cfg or ParseConfig()
    rows = []

    with pdfplumber.open(io.BytesIO(data)) as pdf:
        # table-first
        for page in pdf.pages:
            try:
                tables = page.extract_tables() or []
            except Exception:
                tables = []
            for t in tables:
                df = pd.DataFrame(t).dropna(axis=1, how="all")
                if len(df) >= 2:
                    df.columns = [str(x).strip() for x in df.iloc[0]]
                    df = df.iloc[1:].reset_index(drop=True)
                    std = _standardize_columns(df, cfg)
                    rows.append(std)

        # fallback regex-on-text
        if not rows or sum(len(r) for r in rows) < 3:
            for page in pdf.pages:
                text = page.extract_text() or ""
                lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
                for ln in lines:
                    if cfg.custom_regex:
                        m = re.search(cfg.custom_regex, ln)
                        if m:
                            d = m.groupdict()
                            date = _parse_date(d.get("date", ""), cfg)
                            desc = d.get("description", "").strip()
                            amount = _to_amount(d.get("amount")) if d.get("amount") else None
                            debit = _to_amount(d.get("debit")) if d.get("debit") else None
                            credit = _to_amount(d.get("credit")) if d.get("credit") else None
                            if amount is None:
                                if debit is not None and debit != 0:
                                    amount = -abs(debit)
                                elif credit is not None and credit != 0:
                                    amount = abs(credit)
                            rows.append(pd.DataFrame({
                                "date": [date],
                                "description": [desc],
                                "amount": [amount],
                                "debit": [max(0, -(amount or 0))],
                                "credit": [max(0, (amount or 0))],
                            }))
                    else:
                        date_match = None
                        for d_re in DATE_RES:
                            date_match = d_re.search(ln)
                            if date_match:
                                break
                        amt_match = AMOUNT_RE.search(ln[::-1])
                        amt = None
                        if amt_match:
                            amt_str = amt_match.group(0)[::-1]
                            amt = _to_amount(amt_str)
                        if date_match and amt is not None:
                            date = _parse_date(date_match.group(0), cfg)
                            desc = ln.replace(date_match.group(0), "").strip()
                            m2 = AMOUNT_RE.search(desc)
                            if m2:
                                desc = desc[:m2.start()].strip()
                            rows.append(pd.DataFrame({
                                "date": [date],
                                "description": [desc],
                                "amount": [amt],
                                "debit": [max(0, -(amt or 0))],
                                "credit": [max(0, (amt or 0))],
                            }))

    if not rows:
        return pd.DataFrame(columns=["date", "description", "debit", "credit", "amount"])

    df_all = pd.concat(rows, ignore_index=True)
    df_all["date"] = pd.to_datetime(df_all["date"], errors="coerce")
    df_all = df_all.dropna(subset=["date"])
    df_all["amount"] = pd.to_numeric(df_all["amount"], errors="coerce")
    df_all["debit"] = pd.to_numeric(df_all["debit"], errors="coerce").fillna(0)
    df_all["credit"] = pd.to_numeric(df_all["credit"], errors="coerce").fillna(0)
    df_all["description"] = df_all["description"].astype(str).str.replace(r"\s+", " ", regex=True).str.strip()
    df_all = df_all.drop_duplicates(subset=["date", "amount", "description"]).sort_values("date").reset_index(drop=True)
    return df_all
