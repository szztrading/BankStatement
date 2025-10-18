import streamlit as st
import pandas as pd
from datetime import date, timedelta
from parsers import parse_hsbc_pdf_bytes, categorize

st.set_page_config(page_title="HSBC Monthly Analyzer · Bilingual v2.5", page_icon="🌐", layout="wide")

lang = st.radio("Language / 语言", ["English", "中文"], horizontal=True)

T = {
    "title": {"en": "HSBC Monthly Bank Analyzer (with Revenue Split)", "zh": "汇丰银行月度账单分析（含分成计算）"},
    "subtitle": {
        "en": "Upload HSBC PDFs, select a month or custom date range; all credits are split: Chiyuan 20% / Jiahan 80%.",
        "zh": "上传 HSBC PDF，选择月份或日期范围；所有入账按 智远20% / 嘉翰80% 分成。",
    },
    "uploader": {"en": "Upload HSBC PDF statements (multiple allowed)", "zh": "上传 HSBC 对账单 PDF（可多选）"},
    "btn_this_month": {"en": "📅 This Month", "zh": "📅 本月"},
    "btn_last_month": {"en": "📆 Last Month", "zh": "📆 上月"},
    "btn_clear": {"en": "🧹 Clear Selection", "zh": "🧹 清空选择"},
    "tip_info": {
        "en": "Credits are positive, debits are negative. Categorization uses keyword heuristics.",
        "zh": "入账为正、出账为负；分类基于描述关键字的启发式规则。",
    },
    "start_date": {"en": "Start date", "zh": "开始日期"},
    "end_date": {"en": "End date", "zh": "结束日期"},
    "warn_no_parse": {"en": "No valid transactions parsed (OCR may be required).", "zh": "未解析到有效交易（若为扫描件请先 OCR）。"},
    "info_no_range": {"en": "No transactions in the selected date range.", "zh": "选定日期范围内无交易。"},
    "kpi_in": {"en": "Total Credits", "zh": "入账合计"},
    "kpi_out": {"en": "Total Debits", "zh": "出账合计"},
    "kpi_net": {"en": "Net Amount", "zh": "净额"},
    "kpi_chi": {"en": "Chiyuan (20%)", "zh": "智远 20%"},
    "kpi_jia": {"en": "Jiahan (80%)", "zh": "嘉翰 80%"},
    "kpi_cnt": {"en": "Transactions", "zh": "交易笔数"},
    "inbound_sec": {"en": "Inbound Summary (Monthly, with Split)", "zh": "入账分类汇总（按月，含分成）"},
    "inbound_none": {"en": "No inbound records.", "zh": "无入账。"},
    "inbound_overview": {"en": "Inbound Overview (Monthly Totals)", "zh": "入账总览（按月合计）"},
    "outbound_sec": {"en": "Outbound Summary (Monthly)", "zh": "出账分类汇总（按月）"},
    "outbound_none": {"en": "No outbound records.", "zh": "无出账。"},
    "detail_sec": {"en": "Details (with split columns)", "zh": "明细（含分成列）"},
    "download": {"en": "⬇️ Download CSV (with split)", "zh": "⬇️ 下载明细 CSV（含分成）"},
    "upload_info": {"en": "Upload PDFs to start.", "zh": "上传 PDF 开始分析。"},
}

def tr(key):
    return T[key]["zh"] if lang == "中文" else T[key]["en"]

st.title(tr("title"))
st.caption(tr("subtitle"))

uploaded_files = st.file_uploader(tr("uploader"), type=["pdf"], accept_multiple_files=True)

def month_bounds(d: date):
    first = d.replace(day=1)
    if first.month == 12:
        nxt = first.replace(year=first.year+1, month=1, day=1)
    else:
        nxt = first.replace(month=first.month+1, day=1)
    last = nxt - timedelta(days=1)
    return first, last

today = date.today()
m_first, m_last = month_bounds(today)

col1, col2, col3, col4 = st.columns([1.2,1.2,1,2])
with col1:
    if st.button(tr("btn_this_month")):
        st.session_state["start_date"] = m_first
        st.session_state["end_date"] = m_last
with col2:
    last_month_ref = (today.replace(day=1) - timedelta(days=1))
    lm_first, lm_last = month_bounds(last_month_ref)
    if st.button(tr("btn_last_month")):
        st.session_state["start_date"] = lm_first
        st.session_state["end_date"] = lm_last
with col3:
    if st.button(tr("btn_clear")):
        st.session_state.pop("start_date", None)
        st.session_state.pop("end_date", None)
with col4:
    st.info(tr("tip_info"), icon="ℹ️")

start_date = st.date_input(tr("start_date"), value=st.session_state.get("start_date", m_first))
end_date = st.date_input(tr("end_date"), value=st.session_state.get("end_date", m_last))

if uploaded_files:
    frames = []
    for f in uploaded_files:
        df = parse_hsbc_pdf_bytes(f.read())
        if df.empty:
            st.warning(f"{f.name}: " + tr("warn_no_parse"))
        else:
            df["source_file"] = f.name
            frames.append(df)
    if frames:
        all_df = pd.concat(frames, ignore_index=True)
        mask = (all_df["date"] >= pd.to_datetime(start_date)) & (all_df["date"] <= pd.to_datetime(end_date))
        view = all_df.loc[mask].copy()
        if view.empty:
            st.info(tr("info_no_range"))
        else:
            view["category"] = view.apply(lambda r: categorize(r["description"], r["amount"]), axis=1)
            view["Chiyuan_20pct"] = view["credit"] * 0.20
            view["Jiahan_80pct"] = view["credit"] * 0.80

            total_in = view["credit"].sum()
            total_out = view["debit"].sum()
            net = view["amount"].sum()
            k1,k2,k3,k4,k5,k6 = st.columns(6)
            k1.metric(tr("kpi_in"), f"{total_in:,.2f}")
            k2.metric(tr("kpi_out"), f"{total_out:,.2f}")
            k3.metric(tr("kpi_net"), f"{net:,.2f}")
            k4.metric(tr("kpi_chi"), f"{view['Chiyuan_20pct'].sum():,.2f}")
            k5.metric(tr("kpi_jia"), f"{view['Jiahan_80pct'].sum():,.2f}")
            k6.metric(tr("kpi_cnt"), f"{len(view)}")

            view["month"] = view["date"].dt.to_period("M").astype(str)

            st.subheader(tr("inbound_sec"))
            inbound = view[view["amount"] > 0].copy()
            if inbound.empty:
                st.write(tr("inbound_none"))
            else:
                inbound_sum = inbound.groupby(["month","category"], as_index=False).agg(
                    **({ ("入账金额" if lang=="中文" else "Inbound Amount"): ("credit","sum") }),
                    **({ ("笔数" if lang=="中文" else "Count"): ("credit","count") }),
                    Chiyuan_20pct=("Chiyuan_20pct","sum"),
                    Jiahan_80pct=("Jiahan_80pct","sum"),
                )
                st.dataframe(inbound_sum, use_container_width=True)

                st.markdown("**" + tr("inbound_overview") + "**")
                inbound_month = inbound.groupby("month", as_index=False).agg(
                    **({ ("入账金额" if lang=="中文" else "Inbound Amount"): ("credit","sum") }),
                    Chiyuan_20pct=("Chiyuan_20pct","sum"),
                    Jiahan_80pct=("Jiahan_80pct","sum"),
                    **({ ("笔数" if lang=="中文" else "Count"): ("credit","count") }),
                ).sort_values("month")
                st.dataframe(inbound_month, use_container_width=True)

            st.subheader(tr("outbound_sec"))
            outbound = view[view["amount"] < 0]
            if outbound.empty:
                st.write(tr("outbound_none"))
            else:
                outbound_sum = outbound.groupby(["month","category"], as_index=False).agg(
                    **({ ("出账金额" if lang=="中文" else "Outbound Amount"): ("debit","sum") }),
                    **({ ("笔数" if lang=="中文" else "Count"): ("debit","count") }),
                )
                st.dataframe(outbound_sum, use_container_width=True)

            st.markdown("### " + tr("detail_sec"))
            show_cols = ["date","description","category","debit","credit","amount","Chiyuan_20pct","Jiahan_80pct","source_file"]
            st.dataframe(view[show_cols].sort_values("date"), use_container_width=True)

            csv_bytes = view[show_cols].to_csv(index=False).encode("utf-8-sig")
            fname = f"hsbc_tx_split_{'en' if lang=='English' else 'cn'}_{start_date}_{end_date}.csv"
            st.download_button(tr("download"), data=csv_bytes, file_name=fname, mime="text/csv")
else:
    st.info(tr("upload_info"))
