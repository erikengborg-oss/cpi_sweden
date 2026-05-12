import argparse
import datetime
import itertools
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import requests


API_URL = "https://api.scb.se/OV0104/v1/doris/en/ssd/START/PR/PR0101/PR0101A/KPI2020COICOP2M"

CONTENTS_CODE_WEIGHTS = "0000080F"
CONTENTS_CODE_ANNUAL_CHANGE = "00000809"

COICOP_LABELS_EN = {
    "01": "Food and non-alcoholic beverages",
    "02": "Alcoholic beverages and tobacco",
    "03": "Clothing and footwear",
    "04": "Housing",
    "05": "Furnishings and household goods",
    "06": "Health",
    "07": "Transport",
    "08": "Communication",
    "09": "Recreation and culture",
    "10": "Education",
    "11": "Restaurants and hotels",
    "12": "Miscellaneous goods and services",
    "13": "Other",
}

MUTED_PALETTE = [
    "#4E79A7",
    "#A0CBE8",
    "#F28E2B",
    "#FFBE7D",
    "#59A14F",
    "#8CD17D",
    "#E15759",
    "#FF9D9A",
    "#B07AA1",
    "#D4A6C8",
    "#9C755F",
    "#BAB0AC",
    "#76B7B2",
]


def build_query(from_year: int, to_year: int, contents_code: str = CONTENTS_CODE_WEIGHTS, month: str = "M01") -> dict:
    periods = [f"{y}{month}" for y in range(from_year, to_year + 1)]
    return {
        "query": [
            {"code": "ContentsCode", "selection": {"filter": "item", "values": [contents_code]}},
            {"code": "VaruTjanstegrupp", "selection": {"filter": "item", "values": [f"{i:02d}" for i in range(14)]}},
            {"code": "Tid", "selection": {"filter": "item", "values": periods}},
        ],
        "response": {"format": "json-stat2"},
    }


def json_stat2_to_df(payload: dict) -> pd.DataFrame:
    dims = payload["id"]
    dim_values: list[list[str]] = []
    dim_labels: dict[str, dict[str, str]] = {}
    for dim in dims:
        category = payload["dimension"][dim]["category"]
        idx = category["index"]
        labels = category.get("label", {})
        dim_labels[dim] = labels if isinstance(labels, dict) else {}
        ordered = [k for k, _ in sorted(idx.items(), key=lambda kv: kv[1])]
        dim_values.append(ordered)

    expected_rows = 1
    for values in dim_values:
        expected_rows *= len(values)

    payload_values = payload["value"]
    if len(payload_values) != expected_rows:
        raise ValueError(
            f"Unexpected JSON-stat payload size: expected {expected_rows} values, got {len(payload_values)}."
        )

    rows = []
    for combo, value in zip(itertools.product(*dim_values), payload_values):
        rec = {dims[i]: combo[i] for i in range(len(dims))}
        for i, dim in enumerate(dims):
            rec[f"{dim}_label"] = dim_labels.get(dim, {}).get(combo[i], combo[i])
        rec["value"] = value
        rows.append(rec)
    return pd.DataFrame(rows)


def build_wide_table(df: pd.DataFrame, from_year: int, to_year: int) -> pd.DataFrame:
    rename_map = {"VaruTjanstegrupp": "code", "Tid": "period"}
    if "VaruTjanstegrupp_label" in df.columns:
        rename_map["VaruTjanstegrupp_label"] = "label_raw"
    out = df.rename(columns=rename_map).copy()

    out["year"] = out["period"].str.extract(r"(\d{4})", expand=False).astype(int)
    out["value"] = pd.to_numeric(out["value"], errors="coerce")
    out["code"] = out["code"].astype(str).str.extract(r"(\d{1,2})", expand=False).str.zfill(2)

    out = out[out["code"].notna()]
    out = out[out["code"] != "00"]
    out = out[(out["year"] >= from_year) & (out["year"] <= to_year)]
    out = out.dropna(subset=["value"]).sort_values(["code", "year"])
    out = out.groupby(["code", "year"], as_index=False).tail(1)

    labels = (
        out[["code", "label_raw"]]
        .dropna()
        .drop_duplicates("code")
        .set_index("code")["label_raw"]
        .to_dict()
        if "label_raw" in out.columns
        else {}
    )

    wide = out.pivot(index="code", columns="year", values="value").sort_index().reset_index()
    wide["label"] = wide["code"].map(COICOP_LABELS_EN).fillna(wide["code"].map(labels)).fillna(wide["code"])

    year_cols = sorted([c for c in wide.columns if isinstance(c, int)])
    return wide[["code", "label"] + year_cols]


def build_contribution_table(weights_wide: pd.DataFrame, changes_wide: pd.DataFrame) -> pd.DataFrame:
    year_cols_w = {c for c in weights_wide.columns if isinstance(c, int)}
    year_cols_c = {c for c in changes_wide.columns if isinstance(c, int)}
    common_years = sorted(year_cols_w & year_cols_c)

    w = weights_wide.set_index("code")[common_years]
    c = changes_wide.set_index("code")[common_years]
    contrib = (w / 1000.0) * c

    contrib = contrib.reset_index()
    label_map = weights_wide.set_index("code")["label"]
    contrib["label"] = contrib["code"].map(label_map)
    return contrib[["code", "label"] + common_years]


def save_contribution_html(contrib: pd.DataFrame, out_html: Path) -> None:
    year_cols = [c for c in contrib.columns if isinstance(c, int)]
    if not year_cols:
        raise ValueError("No year columns available for chart export.")

    total_by_year = contrib[year_cols].sum(axis=0)

    fig = go.Figure()
    for (_, share_row), row, color in zip(contrib.set_index("code")[year_cols].iterrows(), contrib.itertuples(index=False), itertools.cycle(MUTED_PALETTE)):
        label = f"{row.code} {row.label}"
        vals = share_row[year_cols].fillna(0.0).values
        fig.add_trace(
            go.Bar(
                x=year_cols,
                y=vals,
                name=label,
                marker=dict(color=color),
                hovertemplate=f"Year: %{{x}}<br>Category: {label}<br>Contribution: %{{y:.2f}} pp<extra></extra>",
            )
        )

    fig.add_trace(
        go.Scatter(
            x=year_cols,
            y=total_by_year[year_cols].values,
            name="Sum of contributions",
            mode="lines+markers",
            line=dict(color="black", width=2),
            hovertemplate="Year: %{x}<br>Sum of contributions: %{y:.2f}%<extra></extra>",
        )
    )

    fig.update_layout(
        title="Category contributions to CPI inflation (percentage points)",
        barmode="relative",
        xaxis_title="Year",
        yaxis_title="Contribution (pp)",
        hovermode="closest",
    )
    out_html.parent.mkdir(parents=True, exist_ok=True)
    fig.write_html(out_html, include_plotlyjs="cdn")


def save_stacked_share_html(wide: pd.DataFrame, out_html: Path) -> None:
    year_cols = [c for c in wide.columns if isinstance(c, int)]
    if not year_cols:
        raise ValueError("No year columns available for chart export.")

    totals = wide[year_cols].sum(axis=0, min_count=1)
    invalid_years = [str(year) for year, total in totals.items() if pd.isna(total) or total <= 0]
    if invalid_years:
        raise ValueError(f"Cannot compute yearly shares for invalid totals: {', '.join(invalid_years)}.")

    share_pct = wide[year_cols].div(totals, axis=1) * 100.0

    fig = go.Figure()
    for (_, share_row), row, color in zip(share_pct.iterrows(), wide.itertuples(index=False), itertools.cycle(MUTED_PALETTE)):
        label = f"{row.code} {row.label}"
        vals = share_row[year_cols].fillna(0.0).values
        fig.add_trace(
            go.Bar(
                x=year_cols,
                y=vals,
                name=label,
                marker=dict(color=color),
                hovertemplate=f"Year: %{{x}}<br>Category: {label}<br>Share: %{{y:.2f}}%<extra></extra>",
            )
        )

    fig.update_layout(
        title="Share of the CPI-basket over time",
        barmode="stack",
        xaxis_title="Year",
        yaxis_title="Share (%)",
        yaxis=dict(range=[0, 100]),
        hovermode="closest",
    )
    out_html.parent.mkdir(parents=True, exist_ok=True)
    fig.write_html(out_html, include_plotlyjs="cdn")


def run(
    out_csv: Path,
    out_html: Path,
    out_html_contrib: Path,
    from_year: int,
    to_year: int,
    timeout: int,
    api_url: str,
    contents_code: str,
) -> None:
    # SCB publishes basket weights once per year; January is the reference month.
    weights_query = build_query(from_year=from_year, to_year=to_year, contents_code=contents_code, month="M01")
    weights_resp = requests.post(api_url, json=weights_query, timeout=timeout)
    weights_resp.raise_for_status()
    wide = build_wide_table(json_stat2_to_df(weights_resp.json()), from_year=from_year, to_year=to_year)
    if wide.empty:
        raise ValueError("The weights table is empty after filtering.")

    # December annual changes give the full-year inflation figure for each category.
    # Cap to_year so we never request a December that hasn't been published yet.
    today = datetime.date.today()
    changes_to_year = min(to_year, today.year if today.month == 12 else today.year - 1)
    changes_query = build_query(from_year=from_year, to_year=changes_to_year, contents_code=CONTENTS_CODE_ANNUAL_CHANGE, month="M12")
    changes_resp = requests.post(api_url, json=changes_query, timeout=timeout)
    changes_resp.raise_for_status()
    changes_wide = build_wide_table(json_stat2_to_df(changes_resp.json()), from_year=from_year, to_year=to_year)

    out_csv.parent.mkdir(parents=True, exist_ok=True)
    wide.to_csv(out_csv, index=False)
    save_stacked_share_html(wide, out_html)
    print(f"CSV saved: {out_csv}")
    print(f"HTML saved: {out_html}")

    if not changes_wide.empty:
        contrib = build_contribution_table(wide, changes_wide)
        save_contribution_html(contrib, out_html_contrib)
        print(f"Contribution HTML saved: {out_html_contrib}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Fetch CPI weights from SCB API and export CSV + HTML.")
    base_dir = Path.home() / "python" / "kpi_scb"
    parser.add_argument("--out-csv", type=Path, default=base_dir / "data" / "share_cpi_wide.csv")
    parser.add_argument("--out-html", type=Path, default=base_dir / "figures" / "index.html")
    parser.add_argument("--out-html-contrib", type=Path, default=base_dir / "figures" / "contributions.html")
    parser.add_argument("--from-year", type=int, default=1980)
    parser.add_argument("--to-year", type=int, default=2026)
    parser.add_argument("--timeout", type=int, default=60)
    parser.add_argument("--api-url", type=str, default=API_URL)
    parser.add_argument("--contents-code", type=str, default=CONTENTS_CODE_WEIGHTS)
    args = parser.parse_args()

    if args.from_year > args.to_year:
        raise ValueError("--from-year must be less than or equal to --to-year.")

    run(
        out_csv=args.out_csv,
        out_html=args.out_html,
        out_html_contrib=args.out_html_contrib,
        from_year=args.from_year,
        to_year=args.to_year,
        timeout=args.timeout,
        api_url=args.api_url,
        contents_code=args.contents_code,
    )
