# app.py — TRB Survey Explorer (Py-Shiny)
# - Sticky full-height filter sidebar
# - Pie charts without legends
# - Org bar (all orgs), Tenure pie shown side-by-side
# - Charts header shows total filtered responses
#
# Save your 4-column CSV as: trb_simplified.csv
# Required columns (case-insensitive): Last5Years, AttendTRBAM2026, Organization, HowLong

from shiny import App, reactive, render, ui
from shinywidgets import output_widget, render_widget
import pandas as pd
import plotly.express as px
import re

# ---------------------- Config ----------------------
INTENT_LEVELS = [
    "Definitely going",
    "Probably going",
    "I don't know",
    "Probably not going",
    "Definitely not going",
]
TENURE_LEVELS = ["0 to 5 years", "6 to 10 years", "11 to 15 years", "16 or more years"]

# ---------------------- Data load ----------------------
# Place your simplified dataset as "trb_simplified.csv" in the same folder as this app.py
BASE_DF = pd.read_csv("trb_simplified.csv", dtype=str).fillna("")
BASE_DF.columns = [c.strip() for c in BASE_DF.columns]
# Types
BASE_DF["Last5Years"] = pd.to_numeric(BASE_DF["Last5Years"], errors="coerce")
BASE_DF["AttendTRBAM2026"] = pd.Categorical(BASE_DF["AttendTRBAM2026"], categories=INTENT_LEVELS)
BASE_DF["HowLong"] = pd.Categorical(BASE_DF["HowLong"], categories=TENURE_LEVELS, ordered=True)

# Strip spaces, replace inconsistent variants with "Consulting"
BASE_DF["Organization"] = BASE_DF["Organization"].str.strip().replace({
    "Consultant": "Consulting",
    "consultant": "Consulting",
    "CONSULTANT": "Consulting",
    "software": "Software"
})

# ---------------------- Helpers ----------------------
def split_orgs(cell: str) -> list[str]:
    if not cell:
        return []
    parts = re.split(r"\s*(,|/|;|\+| and )\s*", str(cell))
    return [p.strip() for p in parts if p and p not in {",", "/", ";", "+", " and "}]

def _label_na(series: pd.Series, label="Unspecified") -> pd.Series:
    s = series.astype(object)
    return s.where(~pd.isna(s), other=label)

# Precompute org choices from full dataset
ORG_CHOICES = sorted({t for cell in BASE_DF["Organization"].astype(str) for t in split_orgs(cell)})

# ----------------------------- UI ------------------------------------------
app_ui = ui.page_fluid(
    ui.h2("TRB Annual Meeting Participation Poll Explorer"),
    # Full-height sticky sidebar CSS
    ui.tags.style("""
      .full-height { min-height: 100vh; }
      .sidebar-sticky {
        position: sticky;
        top: 12px;
        max-height: calc(100vh - 24px);
        overflow: auto;
        box-sizing: border-box;
      }
    """),
    ui.row(
        {"class": "full-height"},
        ui.column(
            4,
            ui.card(
                {"class": "sidebar-sticky"},
                ui.card_header("Filters"),
                ui.input_slider("yr", "Times attended (last 5 years)", 0, 5, [0, 5], step=1),
                ui.input_selectize(
                    "intent", "Intention",
                    INTENT_LEVELS, selected=INTENT_LEVELS, multiple=True
                ),
                ui.input_selectize(
                    "orgs", "Organization (any of)",
                    ORG_CHOICES, selected=None, multiple=True
                ),
                ui.input_selectize(
                    "tenure", "Years in transportation",
                    TENURE_LEVELS, selected=TENURE_LEVELS, multiple=True
                )
            ),
        ),
        ui.column(
            8,
            ui.card(
                ui.card_header(ui.output_text("charts_header")),
                ui.row(
                    ui.column(6, output_widget("pie_last5", height="340px")),
                    ui.column(6, output_widget("pie_intent", height="340px")),
                ),
                ui.row(
                    ui.column(6, output_widget("bar_orgs", height="420px")),   # side-by-side
                    ui.column(6, output_widget("pie_tenure", height="420px")), # side-by-side
                ),
            ),
        ),
    ),
)

# --------------------------- Server logic -----------------------------------
def server(input, output, session):
    @reactive.Calc
    def df_filtered():
        df = BASE_DF.copy()

        # Last5Years range
        yr0, yr1 = input.yr()
        df = df[(df["Last5Years"].isna()) | ((df["Last5Years"] >= yr0) & (df["Last5Years"] <= yr1))]

        # Intention
        intents = set(input.intent())
        if intents:
            df = df[df["AttendTRBAM2026"].astype(str).isin(intents) | df["AttendTRBAM2026"].isna()]

        # Tenure
        tens = set(input.tenure())
        if tens:
            df = df[df["HowLong"].astype(str).isin(tens) | df["HowLong"].isna()]

        # Organizations (any-of)
        sel_orgs = set(input.orgs() or [])
        if sel_orgs:
            keep = []
            for _, row in df.iterrows():
                toks = set(split_orgs(row["Organization"]))
                keep.append((not toks) or bool(toks & sel_orgs))
            df = df[pd.Series(keep, index=df.index)]

        return df.reset_index(drop=True)

    # Header with response count
    @render.text
    def charts_header():
        n = len(df_filtered())
        return f"Charts (update with filters) — {n} response{'s' if n != 1 else ''}"

    # ---------- Pie helper (no legend) ----------
    def pie_from_counts(df_count: pd.DataFrame, label_col: str, value_col: str, title: str):
        d = df_count[df_count[value_col] > 0].copy()
        d[label_col] = d[label_col].astype(str).fillna("Unspecified")
        if d.empty:
            fig = px.pie(names=[title], values=[1], title=f"{title} (no data)")
            fig.update_layout(showlegend=False)
            return fig
        fig = px.pie(d, names=label_col, values=value_col, hole=0.3, title=title)
        fig.update_traces(textposition="inside", textinfo="percent+label")
        fig.update_layout(showlegend=False)  # hide legend
        return fig

    # Last5Years pie
    @render_widget
    def pie_last5():
        d = df_filtered()
        tmp = d.copy()
        tmp["Last5Years"] = tmp["Last5Years"].astype("Int64").astype(object)
        tmp["Last5Years"] = _label_na(tmp["Last5Years"], "Unspecified").astype(str)
        order = [str(i) for i in range(0, 6)] + ["Unspecified"]
        agg = tmp.groupby("Last5Years").size().rename("n").reset_index()
        agg["Last5Years"] = pd.Categorical(agg["Last5Years"], categories=order, ordered=True)
        agg = agg.sort_values("Last5Years").rename(columns={"Last5Years": "label"})

        # Add " year(s)" suffix to labels, except Unspecified
        agg["label"] = agg["label"].apply(
            lambda x: f"{x} time{'s' if x not in ['1','Unspecified'] else ''}"
        )

        return pie_from_counts(agg, "label", "n", "Times attended (last 5 years)")

    # Intention pie
    @render_widget
    def pie_intent():
        d = df_filtered()
        tmp = d.copy()
        tmp["AttendTRBAM2026"] = _label_na(tmp["AttendTRBAM2026"], "Unspecified")
        order = INTENT_LEVELS + ["Unspecified"]
        agg = tmp.groupby("AttendTRBAM2026").size().rename("n").reset_index()
        agg["AttendTRBAM2026"] = pd.Categorical(agg["AttendTRBAM2026"], categories=order, ordered=True)
        agg = agg.sort_values("AttendTRBAM2026").rename(columns={"AttendTRBAM2026": "label"})
        return pie_from_counts(agg, "label", "n", "Intention to attend")

    # Organization bar (ALL orgs, sorted)
    @render_widget
    def bar_orgs():
        d = df_filtered()
        rows = []
        for _, r in d.iterrows():
            rows.extend(split_orgs(r["Organization"]))
        if not rows:
            return px.bar(title="Organization (no data)")
        org = pd.Series(rows, name="org")
        agg = org.value_counts().rename_axis("org").reset_index(name="n")
        fig = px.bar(
            agg.sort_values("n", ascending=True),
            x="n", y="org", orientation="h",
            labels={"n": "Mentions", "org": "Organization"},
            title="Organization (all)"
        )
        fig.update_layout(yaxis_categoryorder="total ascending")
        return fig

    # Tenure pie
    @render_widget
    def pie_tenure():
        d = df_filtered()
        tmp = d.copy()
        tmp["HowLong"] = _label_na(tmp["HowLong"], "Unspecified")
        order = TENURE_LEVELS + ["Unspecified"]
        agg = tmp.groupby("HowLong").size().rename("n").reset_index()
        agg["HowLong"] = pd.Categorical(agg["HowLong"], categories=order, ordered=True)
        agg = agg.sort_values("HowLong").rename(columns={"HowLong": "label"})
        return pie_from_counts(agg, "label", "n", "Years in transportation")

app = App(app_ui, server)
