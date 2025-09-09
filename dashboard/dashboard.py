# dashboard.py
import os
import io
from typing import Optional

import streamlit as st
import pandas as pd
import plotly.express as px

st.set_page_config(page_title="Cloud Cost Analyzer", page_icon="💸", layout="wide")

# -----------------------------
# Helpers
# -----------------------------
@st.cache_data(show_spinner=False)
def load_csv_local(path: str) -> pd.DataFrame:
    df = pd.read_csv(path)
    df = df.rename(columns={
        "EstimatedCostUSD": "EstimatedCost",
        "PotentialSavingsUSD": "PotentialSavings"
    })
    # Ensure expected columns exist; add if missing
    expected = ["ResourceID", "Service", "ResourceType", "UsageMetric", "EstimatedCost", "PotentialSavings"]
    for col in expected:
        if col not in df.columns:
            df[col] = 0 if col in ("EstimatedCost", "PotentialSavings") else ""
    # Coerce numeric
    df["EstimatedCost"] = pd.to_numeric(df["EstimatedCost"], errors="coerce").fillna(0.0)
    df["PotentialSavings"] = pd.to_numeric(df["PotentialSavings"], errors="coerce").fillna(0.0)
    return df

@st.cache_data(show_spinner=False)
def load_csv_upload(file) -> pd.DataFrame:
    df = pd.read_csv(file)
    expected = ["ResourceID", "Service", "ResourceType", "UsageMetric", "EstimatedCost", "PotentialSavings"]
    for col in expected:
        if col not in df.columns:
            df[col] = 0 if col in ("EstimatedCost", "PotentialSavings") else ""
    df["EstimatedCost"] = pd.to_numeric(df["EstimatedCost"], errors="coerce").fillna(0.0)
    df["PotentialSavings"] = pd.to_numeric(df["PotentialSavings"], errors="coerce").fillna(0.0)
    return df

def kpi_card(label: str, value, help_txt: Optional[str] = None):
    with st.container(border=True):
        st.metric(label, value)
        if help_txt:
            st.caption(help_txt)

def get_download_link(df: pd.DataFrame, filename: str) -> bytes:
    return df.to_csv(index=False).encode("utf-8")

# -----------------------------
# Sidebar – data source
# -----------------------------
st.sidebar.header("Data Source")
mode = st.sidebar.radio("Choose input", ["Use local file path", "Upload CSV"], index=0)

df = pd.DataFrame()
data_loaded = False

if mode == "Use local file path":
    default_path = os.path.join(os.getcwd(), "aws_resource_report.csv")
    csv_path = st.sidebar.text_input("CSV file path", value=default_path)
    refresh = st.sidebar.button("Reload file")
    if csv_path and os.path.exists(csv_path):
        df = load_csv_local(csv_path)
        data_loaded = True
    else:
        st.sidebar.info("Provide a valid path to aws_resource_report.csv")
elif mode == "Upload CSV":
    up = st.sidebar.file_uploader("Upload aws_resource_report.csv", type=["csv"])
    refresh = st.sidebar.button("Reload upload")
    if up is not None:
        df = load_csv_upload(up)
        data_loaded = True

st.title("💸 Cloud Cost Analyzer – Streamlit Dashboard")

if not data_loaded:
    st.info("Load your `aws_resource_report.csv` using the sidebar to begin.")
    st.stop()

# -----------------------------
# Filters
# -----------------------------
st.subheader("Filters")
c1, c2, c3, c4 = st.columns([2, 2, 2, 2])

with c1:
    services = sorted(df["Service"].dropna().unique().tolist())
    selected_services = st.multiselect("Service", services, default=services)

with c2:
    # Ensure the column exists
    if "PotentialSavings" not in df.columns or df["PotentialSavings"].max() == 0:
        min_savings = 0.0
        max_savings = 1.0  # temporary small value to prevent error
    else:
        min_savings = float(df["PotentialSavings"].min())
        max_savings = float(df["PotentialSavings"].max())

    savings_filter = st.slider(
        "Minimum Potential Savings",
        min_value=0.0,
        max_value=max(max_savings, 0.01),  # avoid min==max
        value=0.0,
        step=1.0
    )


with c3:
    search_id = st.text_input("Search ResourceID (optional)").strip()

with c4:
    only_idle = st.checkbox("Show only items with savings > 0", value=False)

# Apply filters
f = df[df["Service"].isin(selected_services)]
if only_idle:
    f = f[f["PotentialSavings"] > 0]
if savings_filter > 0:
    f = f[f["PotentialSavings"] >= savings_filter]
if search_id:
    f = f[f["ResourceID"].astype(str).str.contains(search_id, case=False, na=False)]

# -----------------------------
# KPIs
# -----------------------------
total_cost = df["EstimatedCost"].sum()
total_savings = df["PotentialSavings"].sum()
flagged_count = (df["PotentialSavings"] > 0).sum()

kc1, kc2, kc3 = st.columns(3)
with kc1:
    kpi_card("Total Estimated Monthly Cost", f"${total_cost:,.2f}", "Sum of EstimatedCost")
with kc2:
    kpi_card("Total Potential Monthly Savings", f"${total_savings:,.2f}", "If you apply all suggestions")
with kc3:
    kpi_card("Resources With Savings", f"{flagged_count}", "Count of items with PotentialSavings > 0")

st.divider()

# -----------------------------
# Charts
# -----------------------------
st.subheader("Visuals")

colA, colB = st.columns(2)

with colA:
    if not f.empty and f["Service"].nunique() > 0:
        fig_cost = px.pie(f, names="Service", values="EstimatedCost", title="Cost by Service")
        st.plotly_chart(fig_cost, use_container_width=True)
    else:
        st.info("No data to display for Cost by Service.")

with colB:
    if not f.empty and f["Service"].nunique() > 0:
        savings_by_service = f.groupby("Service", as_index=False)["PotentialSavings"].sum()
        fig_sav = px.bar(savings_by_service, x="Service", y="PotentialSavings", title="Potential Savings by Service")
        st.plotly_chart(fig_sav, use_container_width=True)
    else:
        st.info("No data to display for Potential Savings by Service.")

st.divider()

# -----------------------------
# Table + Download
# -----------------------------
st.subheader("Details")
st.caption("Sorted by highest savings first")
f_sorted = f.sort_values("PotentialSavings", ascending=False)

st.dataframe(
    f_sorted,
    use_container_width=True,
    hide_index=True
)

dl1, dl2 = st.columns([1, 4])
with dl1:
    csv_bytes = get_download_link(f_sorted, "filtered_report.csv")
    st.download_button("⬇️ Download filtered CSV", data=csv_bytes, file_name="filtered_report.csv", mime="text/csv")

with dl2:
    st.write("")

with st.expander("Preview first 50 rows of the original dataset"):
    st.dataframe(df.head(50), use_container_width=True, hide_index=True)

st.caption("Tip: Re-run your analyzer script to regenerate the CSV, then click Reload in the sidebar.")
