import streamlit as st
import pandas as pd
import re
from datetime import date, datetime, timedelta
from parsers import parse_hsbc_pdf_bytes, categorize

st.set_page_config(page_title="HSBC 月度账单分析（含分成）", page_icon="🧮", layout="wide")
st.title("🧮 HSBC 月度账单分析（全部进账按 Chiyuan 20% / Jiahan 80% 分成）")
st.caption("上传 HSBC PDF，选择月份或日期范围，系统自动解析并对**所有入账**进行分成。")

uploaded_files = st.file_uploader("上传 HSBC 对账单 PDF（可多选）", type=["pdf"], accept_multiple_files=True)

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
    if st.button("📅 本月"):
        st.session_state["start_date"] = m_first
        st.session_state["end_date"] = m_last
with col2:
    last_month_ref = (today.replace(day=1) - timedelta(days=1))
    lm_first, lm_last = month_bounds(last_month_ref)
    if st.button("📆 上月"):
        st.session_state["start_date"] = lm_first
        st.session_state["end_date"] = lm_last
with col3:
    if st.button("🧹 清空选择"):
        st.session_state.pop("start_date", None)
        st.session_state.pop("end_date", None)
with col4:
    st.info("入账为正、出账为负；分类基于描述关键字的启发式规则。", icon="ℹ️")

start_date = st.date_input("开始日期", value=st.session_state.get("start_date", m_first))
end_date = st.date_input("结束日期", value=st.session_state.get("end_date", m_last))

if uploaded_files:
    frames = []
    for f in uploaded_files:
        df = parse_hsbc_pdf_bytes(f.read())
        if df.empty:
            st.warning(f"{f.name} 未解析到有效交易（若为扫描件请先 OCR）。")
        else:
            df["source_file"] = f.name
            frames.append(df)
    if frames:
        all_df = pd.concat(frames, ignore_index=True)
        mask = (all_df["date"] >= pd.to_datetime(start_date)) & (all_df["date"] <= pd.to_datetime(end_date))
        view = all_df.loc[mask].copy()
        if view.empty:
            st.info("选定日期范围内无交易。")
        else:
            # 分类
            view["category"] = view.apply(lambda r: categorize(r["description"], r["amount"]), axis=1)

            # 分成（仅针对入账金额>0的记录；出账分成为0）
            view["Chiyuan_20pct"] = view["credit"] * 0.20
            view["Jiahan_80pct"] = view["credit"] * 0.80

            # KPI
            total_in = view["credit"].sum()
            total_out = view["debit"].sum()
            net = view["amount"].sum()
            k1,k2,k3,k4,k5,k6 = st.columns(6)
            k1.metric("入账合计", f"{total_in:,.2f}")
            k2.metric("出账合计", f"{total_out:,.2f}")
            k3.metric("净额", f"{net:,.2f}")
            k4.metric("Chiyuan 分成（20%）", f"{view['Chiyuan_20pct'].sum():,.2f}")
            k5.metric("Jiahan 分成（80%）", f"{view['Jiahan_80pct'].sum():,.2f}")
            k6.metric("交易笔数", len(view))

            # 按月入账汇总 + 分成
            view["month"] = view["date"].dt.to_period("M").astype(str)
            inbound = view[view["amount"] > 0].copy()
            st.subheader("📥 入账分类汇总（按月，含分成）")
            if inbound.empty:
                st.write("无入账。")
            else:
                inbound_sum = inbound.groupby(["month","category"], as_index=False).agg(
                    入账金额=("credit","sum"),
                    笔数=("credit","count"),
                    Chiyuan_20pct=("Chiyuan_20pct","sum"),
                    Jiahan_80pct=("Jiahan_80pct","sum"),
                )
                st.dataframe(inbound_sum, use_container_width=True)

                st.markdown("**📦 入账总览（按月合计）**")
                inbound_month = inbound.groupby("month", as_index=False).agg(
                    入账金额=("credit","sum"),
                    Chiyuan_20pct=("Chiyuan_20pct","sum"),
                    Jiahan_80pct=("Jiahan_80pct","sum"),
                    笔数=("credit","count"),
                ).sort_values("month")
                st.dataframe(inbound_month, use_container_width=True)

            # 出账分类汇总
            st.subheader("📤 出账分类汇总（按月）")
            outbound = view[view["amount"] < 0]
            if outbound.empty:
                st.write("无出账。")
            else:
                outbound_sum = outbound.groupby(["month","category"], as_index=False).agg(
                    出账金额=("debit","sum"), 笔数=("debit","count")
                )
                st.dataframe(outbound_sum, use_container_width=True)

            st.markdown("### 📄 明细（含个人分成列）")
            show_cols = ["date","description","category","debit","credit","amount","Chiyuan_20pct","Jiahan_80pct","source_file"]
            st.dataframe(view[show_cols].sort_values("date"), use_container_width=True)

            # 导出
            csv_bytes = view[show_cols].to_csv(index=False).encode("utf-8-sig")
            st.download_button("⬇️ 下载明细 CSV（含分成）", data=csv_bytes, file_name=f"hsbc_tx_split_{start_date}_{end_date}.csv", mime="text/csv")
else:
    st.info("上传 PDF 开始分析。")
