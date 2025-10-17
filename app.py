import streamlit as st
import pandas as pd
from io import BytesIO
from datetime import datetime
import re

from parsers import parse_pdf_bytes, ParseConfig

st.set_page_config(page_title="PDF 银行账单分析", page_icon="💳", layout="wide")

st.title("💳 银行账单（PDF）分析器")
st.caption("上传 PDF，对指定时间内的入账/出账/净额进行统计。支持多文件与自定义正则。")

with st.sidebar:
    st.header("⚙️ 解析设置")
    st.markdown("**日期解析**默认 dayfirst=True（17/10/2025 视为 17 Oct 2025）。")
    custom_date_fmt = st.text_input("自定义日期格式（可选，如 %d/%m/%Y）")
    st.markdown("**自定义正则（可选）** 必须包含命名组：`date`、`description`，以及 `amount` 或 `debit/credit`。")
    st.code(r"^(?P<date>\d{2}/\d{2}/\d{4})\s+(?P<description>.*?)\s+(?P<amount>[-+]?[\d,]+\.\d{2})$", language="regex")
    custom_regex = st.text_area("粘贴你的正则（可留空）")

cfg = ParseConfig(custom_regex=custom_regex.strip() or None, custom_date_format=custom_date_fmt.strip() or None)

uploaded_files = st.file_uploader("上传 1 个或多个银行 PDF", type=["pdf"], accept_multiple_files=True)

if uploaded_files:
    dfs = []
    for f in uploaded_files:
        data = f.read()
        df = parse_pdf_bytes(data, cfg)
        if df.empty:
            st.warning(f"❗️ {f.name} 未解析出有效交易。若为扫描件，请先 OCR 转文本 PDF，或设置自定义正则。")
        else:
            df["source_file"] = f.name
            dfs.append(df)

    if dfs:
        df_all = pd.concat(dfs, ignore_index=True)

        min_d, max_d = df_all["date"].min().date(), df_all["date"].max().date()
        st.subheader("📅 时间筛选")
        col_a, col_b, col_c = st.columns([1,1,1])
        with col_a:
            start_date = st.date_input("起始日期", value=min_d, min_value=min_d, max_value=max_d)
        with col_b:
            end_date = st.date_input("截止日期", value=max_d, min_value=min_d, max_value=max_d)
        with col_c:
            st.write("")
            st.write("")
            st.info("入账为正，出账为负。")

        mask = (df_all["date"] >= pd.to_datetime(start_date)) & (df_all["date"] <= pd.to_datetime(end_date))
        view = df_all.loc[mask].copy()

        with st.expander("🔎 关键词过滤（可选）"):
            inc_kw = st.text_input("仅保留包含这些关键词（逗号分隔）")
            exc_kw = st.text_input("排除包含这些关键词（逗号分隔）")
            if inc_kw:
                keys = [k.strip().lower() for k in inc_kw.split(',') if k.strip()]
                if keys:
                    view = view[view["description"].str.lower().str.contains("|".join(map(re.escape, keys)))]
            if exc_kw:
                keys = [k.strip().lower() for k in exc_kw.split(',') if k.strip()]
                if keys:
                    view = view[~view["description"].str.lower().str.contains("|".join(map(re.escape, keys)))]

        total_in = view["credit"].sum()
        total_out = view["debit"].sum()
        net = view["amount"].sum()

        st.subheader("📊 结果概览")
        k1, k2, k3, k4 = st.columns(4)
        k1.metric("入账合计", f"{total_in:,.2f}")
        k2.metric("出账合计", f"{total_out:,.2f}")
        k3.metric("净额", f"{net:,.2f}")
        k4.metric("交易笔数", len(view))

        st.markdown("### 📅 按月汇总")
        mv = view.copy()
        mv["month"] = mv["date"].dt.to_period("M").astype(str)
        monthly = mv.groupby("month").agg(
            入账=("credit", "sum"),
            出账=("debit", "sum"),
            净额=("amount", "sum"),
            笔数=("amount", "count"),
        ).reset_index()
        st.dataframe(monthly, use_container_width=True)

        st.markdown("### 📄 交易明细（标准化）")
        show_cols = ["date", "description", "debit", "credit", "amount", "source_file"]
        st.dataframe(view[show_cols], use_container_width=True)

        csv_bytes = view[show_cols].to_csv(index=False).encode("utf-8-sig")
        st.download_button("⬇️ 下载筛选后的 CSV", data=csv_bytes, file_name=f"bank_tx_{start_date}_{end_date}.csv", mime="text/csv")

        with st.expander("🛠️ 解析调试信息"):
            st.write("如果某些 PDF 没有解析出来，可以：")
            st.write("1) 打开自定义正则，并根据实际行样式编写；")
            st.write("2) 将扫描件做 OCR 转换；")
            st.write("3) 提供样例 PDF，扩展 parsers.py 的适配逻辑。")
    else:
        st.info("尚无可展示数据。")
else:
    st.info("请上传 PDF 文件开始分析。")
