"""Plotly chart builders for the KPI dashboard."""

from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from .constants import AMENITY_LABELS, COLORS, FLOOD_LABELS

# Flood polygon fill colours (semi-transparent) per scenario
_MZP_FILL: dict[str, str] = {
    "Q10%": "rgba(250,199,117,0.40)",
    "Q1%": "rgba(239,159, 39,0.40)",
    "Q0.2%": "rgba(226, 75, 74,0.40)",
}
_MZP_LINE: dict[str, str] = {
    "Q10%": "rgba(250,199,117,0.85)",
    "Q1%": "rgba(239,159, 39,0.85)",
    "Q0.2%": "rgba(226, 75, 74,0.85)",
}

# Consistent layout defaults — larger fonts/margins improve print/PDF legibility
_MARGIN = dict(t=80, l=60, r=30, b=60)
_TITLE_FONT = dict(size=16, family="IBM Plex Sans, sans-serif")
_AXIS_FONT = dict(size=12, family="IBM Plex Sans, sans-serif")
_TEMPLATE = "plotly_white"


def _base_layout(**kwargs) -> dict:
    """Merge per-chart kwargs with sane defaults (print-ready)."""
    return {
        "margin": _MARGIN,
        "title_font": _TITLE_FONT,
        "font": _AXIS_FONT,
        "template": _TEMPLATE,
        **kwargs,
    }


def _empty_figure(title: str) -> go.Figure:
    fig = go.Figure()
    fig.update_layout(
        **_base_layout(
            title=title,
            height=360,
            annotations=[
                dict(
                    text="Brak danych dla wybranych filtrów",
                    xref="paper",
                    yref="paper",
                    x=0.5,
                    y=0.5,
                    showarrow=False,
                    font=dict(size=14, color="#888"),
                )
            ],
        )
    )
    return fig


def ranking_chart(df: pd.DataFrame) -> go.Figure:
    if df.empty:
        return _empty_figure("Ranking miast — średnia cena ofertowa / m²")

    fig = go.Figure(
        go.Bar(
            x=df["avg_price_m2_pln"],
            y=df["city"],
            orientation="h",
            marker_color=COLORS["price"],
            hovertemplate="%{y}<br><b>%{x:,.0f} PLN/m²</b><extra></extra>",
        )
    )
    fig.update_layout(
        **_base_layout(
            title="Ranking miast — średnia cena ofertowa / m²",
            xaxis_title="PLN / m²",
            yaxis_title="",
            height=440,
            yaxis=dict(autorange="reversed"),
        )
    )
    return fig


def flood_premium_chart(df: pd.DataFrame) -> go.Figure:
    if df.empty:
        return _empty_figure("Dyskonto / premia powodziowa (KPI 5)")

    agg = (
        df.groupby("risk_scenario", as_index=False)
        .agg(flood_premium_pct=("flood_premium_pct", "mean"))
        .sort_values("risk_scenario")
    )
    agg["label"] = agg["risk_scenario"].map(FLOOD_LABELS)

    colors = [
        COLORS["flood_moderate"]
        if s == "Q10%"
        else COLORS["flood_high"]
        if s == "Q1%"
        else COLORS["flood_extreme"]
        for s in agg["risk_scenario"]
    ]

    fig = go.Figure(
        go.Bar(
            x=agg["label"],
            y=agg["flood_premium_pct"],
            marker_color=colors,
            text=[f"{v:.1f}%" for v in agg["flood_premium_pct"]],
            textposition="outside",
            hovertemplate="%{x}<br><b>%{y:.1f}%</b><extra></extra>",
        )
    )
    fig.add_hline(y=0, line_dash="dot", line_color=COLORS["nbp"])
    fig.update_layout(
        **_base_layout(
            title="Dyskonto / premia powodziowa (KPI 5)",
            xaxis_title="Scenariusz ryzyka",
            yaxis_title="Premia vs strefa bezpieczna (%)",
            height=360,
        )
    )
    return fig


def trend_chart(df: pd.DataFrame) -> go.Figure:
    if df.empty:
        return _empty_figure("Trendy cen — oferta vs NBP")

    fig = make_subplots(specs=[[{"secondary_y": True}]])

    fig.add_trace(
        go.Scatter(
            x=df["period"],
            y=df["avg_offer_m2_pln"],
            name="Cena ofertowa (Kaggle)",
            line=dict(color=COLORS["price"], width=2.5),
            mode="lines+markers",
            hovertemplate="%{x}<br>Oferta: <b>%{y:,.0f} PLN/m²</b><extra></extra>",
        ),
        secondary_y=False,
    )
    fig.add_trace(
        go.Scatter(
            x=df["period"],
            y=df["avg_transaction_m2_pln"],
            name="Cena transakcyjna (NBP)",
            line=dict(color=COLORS["nbp"], width=2.5, dash="dash"),
            mode="lines+markers",
            hovertemplate="%{x}<br>NBP: <b>%{y:,.0f} PLN/m²</b><extra></extra>",
        ),
        secondary_y=False,
    )
    fig.add_trace(
        go.Scatter(
            x=df["period"],
            y=df["deviation_pct"],
            name="Odchylenie (%)",
            line=dict(color=COLORS["deviation"], width=2.5),
            mode="lines+markers",
            hovertemplate="%{x}<br>Odchylenie: <b>%{y:.1f}%</b><extra></extra>",
        ),
        secondary_y=True,
    )

    fig.update_layout(
        **_base_layout(
            title="Trend cenowy — oferty Kaggle vs transakcje NBP BaRN (KPI 1 & 2)",
            height=420,
            legend=dict(orientation="h", yanchor="bottom", y=-0.25),
            hovermode="x unified",
        )
    )
    fig.update_yaxes(title_text="PLN / m²", secondary_y=False)
    fig.update_yaxes(title_text="Odchylenie (%)", secondary_y=True)
    return fig


def sales_velocity_chart(df: pd.DataFrame) -> go.Figure:
    if df.empty:
        return _empty_figure("Tempo sprzedaży deweloperskiej (KPI 6)")

    agg = (
        df.groupby("week_start", as_index=False)
        .agg(units=("units_sold_or_reserved", "sum"))
        .sort_values("week_start")
    )

    fig = go.Figure(
        go.Bar(
            x=agg["week_start"],
            y=agg["units"],
            marker_color=COLORS["developer"],
            hovertemplate="Tydzień %{x|%Y-%m-%d}<br><b>%{y} lokali</b><extra></extra>",
        )
    )
    fig.update_layout(
        **_base_layout(
            title="Tempo sprzedaży deweloperskiej (KPI 6)",
            xaxis_title="Tydzień",
            yaxis_title="Lokale zarezerwowane / sprzedane",
            height=320,
        )
    )
    return fig


def migration_price_scatter(df: pd.DataFrame) -> go.Figure:
    """OLAP 7 — saldo migracji netto vs dynamika wzrostu cen YoY per miasto."""
    if df.empty or "avg_migration" not in df.columns:
        return _empty_figure("Saldo migracji vs wzrost cen YoY (OLAP 7)")

    valid = df.dropna(subset=["avg_migration", "avg_yoy_pct"])
    if valid.empty:
        return _empty_figure("Saldo migracji vs wzrost cen YoY (OLAP 7)")

    max_pop = float(valid["population"].max()) if "population" in valid.columns else 1.0
    sizes = valid["population"].apply(
        lambda x: 14 + 28 * float(x) / (max_pop or 1.0)
        if pd.notna(x)
        else 14
    )

    fig = go.Figure(
        go.Scatter(
            x=valid["avg_migration"],
            y=valid["avg_yoy_pct"],
            mode="markers+text",
            text=valid["city"].str.title(),
            textposition="top center",
            textfont=dict(size=11),
            marker=dict(
                size=sizes,
                color=COLORS["price"],
                opacity=0.8,
                line=dict(width=1, color="#fff"),
            ),
            customdata=valid[["avg_migration", "avg_yoy_pct", "population"]].values,
            hovertemplate=(
                "<b>%{text}</b><br>"
                "Saldo migracji: <b>%{customdata[0]:+,.0f}</b><br>"
                "Wzrost cen r/r: <b>%{customdata[1]:+.1f}%</b><br>"
                "Populacja: %{customdata[2]:,.0f}"
                "<extra></extra>"
            ),
        )
    )
    fig.add_hline(y=0, line_dash="dot", line_color="#888", annotation_text="0% wzrost")
    fig.add_vline(x=0, line_dash="dot", line_color="#888", annotation_text="Saldo 0")
    fig.update_layout(
        **_base_layout(
            title="Saldo migracji netto vs wzrost cen ofertowych r/r (OLAP 7)",
            xaxis_title="Śr. saldo migracji netto (osoby/rok, GUS BDL)",
            yaxis_title="Śr. wzrost cen ofertowych r/r (%)",
            height=440,
        )
    )
    return fig


def area_by_market_chart(df: pd.DataFrame) -> go.Figure:
    """OLAP 9 — średnia powierzchnia mieszkania per segment rynku i kwartał."""
    if df.empty or "area_m2" not in df.columns or "market_code" not in df.columns:
        return _empty_figure("Średnia powierzchnia per segment rynku (OLAP 9)")

    valid = df.dropna(subset=["area_m2", "market_code", "year", "quarter"])
    valid = valid[valid["area_m2"].between(15, 300)]
    if valid.empty:
        return _empty_figure("Średnia powierzchnia per segment rynku (OLAP 9)")

    agg = valid.groupby(["year", "quarter", "market_code"], as_index=False).agg(
        avg_area=("area_m2", "mean"),
        count=("area_m2", "count"),
    )
    agg["period"] = agg.apply(
        lambda r: f"{int(r['year'])} Q{int(r['quarter'])}", axis=1
    )

    market_labels = {"primary": "Rynek pierwotny", "secondary": "Rynek wtórny"}
    market_colors = {"primary": COLORS["price"], "secondary": COLORS["nbp"]}

    fig = go.Figure()
    for code in ["primary", "secondary"]:
        sub = agg[agg["market_code"] == code].sort_values(["year", "quarter"])
        if sub.empty:
            continue
        fig.add_trace(
            go.Bar(
                x=sub["period"],
                y=sub["avg_area"],
                name=market_labels.get(code, code),
                marker_color=market_colors.get(code, "#888"),
                customdata=sub["count"].values,
                hovertemplate=(
                    f"<b>{market_labels.get(code, code)}</b><br>"
                    "%{x}<br>"
                    "Śr. powierzchnia: <b>%{y:.1f} m²</b><br>"
                    "Oferty: %{customdata:,d}"
                    "<extra></extra>"
                ),
            )
        )
    fig.update_layout(
        **_base_layout(
            title="Średnia powierzchnia mieszkania: rynek pierwotny vs wtórny (OLAP 9)",
            xaxis_title="Kwartał",
            yaxis_title="Średnia powierzchnia (m²)",
            barmode="group",
            height=380,
            legend=dict(orientation="h", yanchor="bottom", y=-0.25),
        )
    )
    return fig


def flood_risk_chart(df: pd.DataFrame) -> go.Figure:
    """KPI 4 — liczba ofert w strefie ryzyka powodziowego, podział per scenariusz."""
    if df.empty:
        return _empty_figure("Oferty w strefie ryzyka powodziowego (KPI 4)")

    scenario_order = ["Q10%", "Q1%", "Q0.2%"]
    scenario_colors = {
        "Q10%": COLORS["flood_moderate"],
        "Q1%": COLORS["flood_high"],
        "Q0.2%": COLORS["flood_extreme"],
    }

    city_totals = (
        df.groupby("city", as_index=False)["listing_count"]
        .sum()
        .sort_values("listing_count", ascending=False)
        .head(10)
    )
    top_cities = city_totals["city"].tolist()
    filtered = df[df["city"].isin(top_cities)]

    fig = go.Figure()
    for scenario in scenario_order:
        sub = filtered[filtered["scenario"] == scenario].copy()
        sub["city_label"] = sub["city"].str.title()
        agg = sub.groupby("city_label", as_index=False)["listing_count"].sum()
        fig.add_trace(
            go.Bar(
                x=agg["city_label"],
                y=agg["listing_count"],
                name=FLOOD_LABELS.get(scenario, scenario),
                marker_color=scenario_colors.get(scenario, "#888"),
                hovertemplate="%{x}<br>%{y} ofert<extra></extra>",
            )
        )

    fig.update_layout(
        **_base_layout(
            title="Oferty w strefie ryzyka powodziowego (KPI 4)",
            xaxis_title="Miasto",
            yaxis_title="Liczba ogłoszeń",
            barmode="stack",
            height=380,
            legend=dict(orientation="h", yanchor="bottom", y=-0.25),
        )
    )
    return fig


def affordability_chart(df: pd.DataFrame) -> go.Figure:
    if df.empty:
        return _empty_figure("Dostępność mieszkaniowa (KPI 3)")

    agg = (
        df.groupby("city", as_index=False)
        .agg(months=("months_salary_per_m2", "mean"))
        .sort_values("months")
    )
    agg["city_label"] = agg["city"].str.title()

    colors = [
        COLORS["affordability"]
        if m <= 1.2
        else "#EF9F27"
        if m <= 1.6
        else COLORS["flood_extreme"]
        for m in agg["months"]
    ]
    median = agg["months"].median()

    fig = go.Figure(
        go.Bar(
            x=agg["months"],
            y=agg["city_label"],
            orientation="h",
            marker_color=colors,
            text=[f"{m:.2f}" for m in agg["months"]],
            textposition="outside",
            hovertemplate="%{y}<br><b>%{x:.2f} mies./m²</b><extra></extra>",
        )
    )
    fig.add_vline(
        x=median,
        line_dash="dash",
        line_color=COLORS["nbp"],
        annotation_text=f"Mediana {median:.2f}",
        annotation_position="top",
    )
    fig.update_layout(
        **_base_layout(
            title="Dostępność mieszkaniowa — miesięcy pracy na 1 m² (KPI 3)",
            xaxis_title="Miesięcy wynagrodzenia brutto",
            height=420,
            yaxis=dict(autorange="reversed"),
        )
    )
    return fig


def primary_share_chart(df: pd.DataFrame) -> go.Figure:
    if df.empty:
        return _empty_figure("Udział rynku pierwotnego w ogłoszeniach (KPI 9)")

    agg = (
        df.groupby(df["city"].str.title(), as_index=False)
        .agg(share=("primary_market_share_pct", "mean"))
        .sort_values("share", ascending=False)
    )

    fig = go.Figure(
        go.Bar(
            x=agg["city"],
            y=agg["share"],
            marker_color=COLORS["price"],
            text=[f"{s:.1f}%" for s in agg["share"]],
            textposition="outside",
            hovertemplate="%{x}<br>Rynek pierwotny: <b>%{y:.1f}%</b><extra></extra>",
        )
    )
    fig.update_layout(
        **_base_layout(
            title="Udział rynku pierwotnego w ogłoszeniach (KPI 9)",
            yaxis_title="Udział (%)",
            height=380,
        )
    )
    return fig


def amenity_premium_chart(df: pd.DataFrame) -> go.Figure:
    if df.empty:
        return _empty_figure("Premia cenowa za udogodnienia (KPI 10)")

    rows = []
    for amenity, group in df.groupby("amenity"):
        without = group["avg_price_without_amenity_m2"].mean()
        premium = group["premium_pln_m2"].mean()
        pct = (premium / without * 100) if without and without > 0 else 0
        rows.append({"amenity": amenity, "premium_pct": pct, "premium_pln": premium})
    agg = pd.DataFrame(rows).sort_values("premium_pct", ascending=False)
    agg["label"] = agg["amenity"].map(AMENITY_LABELS)

    fig = go.Figure(
        go.Bar(
            x=agg["label"],
            y=agg["premium_pct"],
            marker_color=COLORS["deviation"],
            text=[f"+{p:.1f}%" for p in agg["premium_pct"]],
            textposition="outside",
            hovertemplate=(
                "%{x}<br>Premia: <b>%{y:.1f}%</b>"
                " (%{customdata:,.0f} PLN/m²)<extra></extra>"
            ),
            customdata=agg["premium_pln"],
        )
    )
    fig.update_layout(
        **_base_layout(
            title="Premia cenowa za udogodnienia (KPI 10)",
            yaxis_title="Premia vs lokale bez udogodnienia (%)",
            height=360,
        )
    )
    return fig


def rooms_price_chart(df: pd.DataFrame) -> go.Figure:
    """Box plot of price/m² per number of rooms."""
    if df.empty or "rooms" not in df.columns:
        return _empty_figure("Rozkład cen/m² wg liczby pokoi")

    valid = df.dropna(subset=["rooms", "price_per_m2_pln"])
    valid = valid[valid["rooms"].between(1, 6)]
    if valid.empty:
        return _empty_figure("Rozkład cen/m² wg liczby pokoi")

    room_labels = {
        1: "1 pokój",
        2: "2 pokoje",
        3: "3 pokoje",
        4: "4 pokoje",
        5: "5 pokoi",
        6: "6+ pokoi",
    }

    fig = go.Figure()
    for rooms in sorted(valid["rooms"].unique()):
        subset = valid[valid["rooms"] == rooms]["price_per_m2_pln"]
        label = room_labels.get(int(rooms), f"{int(rooms)} pokoi")
        fig.add_trace(
            go.Box(
                y=subset,
                name=label,
                boxpoints=False,
                marker_color=COLORS["price"],
                line_color=COLORS["price"],
                hovertemplate=f"<b>{label}</b><br>Mediana: %{{median:,.0f}} PLN/m²<extra></extra>",
            )
        )
    fig.update_layout(
        **_base_layout(
            title="Rozkład cen/m² wg liczby pokoi",
            yaxis_title="PLN / m²",
            height=420,
            showlegend=False,
        )
    )
    return fig


def yoy_growth_chart(df: pd.DataFrame) -> go.Figure:
    """Year-over-year price growth % per city."""
    if df.empty or "year" not in df.columns or "avg_price_m2_pln" not in df.columns:
        return _empty_figure("Wzrost cen rok do roku per miasto")

    city_col = "city" if "city" in df.columns else df.columns[0]
    agg = df.groupby([city_col, "year"], as_index=False).agg(
        avg_price=("avg_price_m2_pln", "mean")
    )
    agg = agg.sort_values([city_col, "year"])
    agg["prev_price"] = agg.groupby(city_col)["avg_price"].shift(1)
    agg["yoy_pct"] = (
        (agg["avg_price"] - agg["prev_price"]) / agg["prev_price"].abs() * 100
    )
    agg = agg.dropna(subset=["yoy_pct"])
    if agg.empty:
        return _empty_figure("Wzrost cen rok do roku per miasto")

    years = sorted(agg["year"].unique())
    cities = sorted(agg[city_col].unique())

    palette = [
        "#185FA5",
        "#533AB7",
        "#1D9E75",
        "#E24B4A",
        "#EF9F27",
        "#D4537E",
        "#1D3557",
        "#3B6D11",
        "#888780",
        "#633806",
    ]

    fig = go.Figure()
    for i, city in enumerate(cities):
        sub = agg[agg[city_col] == city].sort_values("year")
        fig.add_trace(
            go.Bar(
                x=sub["year"].astype(str),
                y=sub["yoy_pct"],
                name=city.title(),
                marker_color=palette[i % len(palette)],
                hovertemplate=f"<b>{city.title()}</b><br>%{{x}}: <b>%{{y:+.1f}}%</b><extra></extra>",
            )
        )
    fig.add_hline(y=0, line_dash="dot", line_color="#888")
    fig.update_layout(
        **_base_layout(
            title="Wzrost cen ofertowych rok do roku per miasto",
            yaxis_title="Zmiana r/r (%)",
            barmode="group",
            height=420,
            legend=dict(orientation="h", yanchor="bottom", y=-0.35, font=dict(size=11)),
        )
    )
    return fig


def salary_vs_price_scatter(df: pd.DataFrame) -> go.Figure:
    """Scatter: avg salary vs avg price/m² per city."""
    if df.empty:
        return _empty_figure("Wynagrodzenie vs cena/m² per miasto")

    city_col = "city" if "city" in df.columns else df.columns[0]
    agg = (
        df.groupby(city_col, as_index=False).agg(
            avg_salary=("avg_gross_salary_pln", "mean"),
            avg_price=("avg_price_m2_pln", "mean"),
            listing_count=("listing_count", "sum"),
        )
    ).dropna(subset=["avg_salary", "avg_price"])
    if agg.empty:
        return _empty_figure("Wynagrodzenie vs cena/m² per miasto")

    max_count = float(agg["listing_count"].max()) or 1.0
    sizes = agg["listing_count"].apply(lambda x: 12 + 30 * float(x) / max_count)

    fig = go.Figure(
        go.Scatter(
            x=agg["avg_salary"],
            y=agg["avg_price"],
            mode="markers+text",
            text=agg[city_col].str.title(),
            textposition="top center",
            textfont=dict(size=11),
            marker=dict(
                size=sizes,
                color=COLORS["affordability"],
                opacity=0.8,
                line=dict(width=1, color="#fff"),
            ),
            customdata=agg[["avg_salary", "avg_price", "listing_count"]].values,
            hovertemplate=(
                "<b>%{text}</b><br>"
                "Wynagrodzenie: <b>%{customdata[0]:,.0f} PLN</b><br>"
                "Cena/m²: <b>%{customdata[1]:,.0f} PLN</b><br>"
                "Ofert: %{customdata[2]:,d}"
                "<extra></extra>"
            ),
        )
    )
    fig.update_layout(
        **_base_layout(
            title="Wynagrodzenie brutto (GUS) vs cena/m² per miasto",
            xaxis_title="Śr. wynagrodzenie brutto (PLN/mies.)",
            yaxis_title="Śr. cena ofertowa / m² (PLN)",
            height=420,
        )
    )
    return fig



def material_price_chart(df: pd.DataFrame) -> go.Figure:
    """Avg price/m² by building material (horizontal bar)."""
    if df.empty or "building_material" not in df.columns:
        return _empty_figure("Cena/m² wg materiału budowlanego")

    agg = (
        df.groupby("building_material", as_index=False)
        .agg(avg_price=("avg_price_m2_pln", "mean"), count=("listing_count", "sum"))
        .sort_values("avg_price")
    )
    agg = agg[agg["count"] >= 5]
    if agg.empty:
        return _empty_figure("Cena/m² wg materiału budowlanego")

    fig = go.Figure(
        go.Bar(
            x=agg["avg_price"],
            y=agg["building_material"].str.replace("_", " ").str.title(),
            orientation="h",
            marker_color=COLORS["deviation"],
            text=[f"{p:,.0f}" for p in agg["avg_price"]],
            textposition="outside",
            customdata=agg["count"].values,
            hovertemplate=(
                "<b>%{y}</b><br>"
                "Śr. cena/m²: <b>%{x:,.0f} PLN</b><br>"
                "Oferty: %{customdata:,d}"
                "<extra></extra>"
            ),
        )
    )
    fig.update_layout(
        **_base_layout(
            title="Śr. cena/m² wg materiału budowlanego",
            xaxis_title="PLN / m²",
            height=max(320, len(agg) * 32 + 80),
        )
    )
    return fig


def developer_ranking_chart(df: pd.DataFrame) -> go.Figure:
    """Top developers by total sold/reserved unit value."""
    if df.empty or "developer_name" not in df.columns:
        return _empty_figure("Ranking deweloperów wg wartości lokali")

    top = df.nlargest(15, "total_value_pln").sort_values("total_value_pln")
    labels = top["developer_name"].str[:35]

    fig = go.Figure(
        go.Bar(
            x=top["total_value_pln"] / 1_000_000,
            y=labels,
            orientation="h",
            marker_color=COLORS["developer"],
            customdata=top[["unit_count", "avg_price_m2_pln"]].values,
            hovertemplate=(
                "<b>%{y}</b><br>"
                "Wartość: <b>%{x:,.1f} mln PLN</b><br>"
                "Lokale: %{customdata[0]:,d}<br>"
                "Śr. cena/m²: %{customdata[1]:,.0f} PLN"
                "<extra></extra>"
            ),
        )
    )
    fig.update_layout(
        **_base_layout(
            title="TOP 15 deweloperów — łączna wartość lokali",
            xaxis_title="Wartość (mln PLN)",
            height=520,
        )
    )
    return fig


def map_chart(
    points_df: pd.DataFrame,
    city_kpi_df: pd.DataFrame,
    geojson: dict,
    active_scenarios: list[str],
    kpi_label: str,
    dev_df: pd.DataFrame | None = None,
) -> go.Figure:
    """Interaktywna mapa z 4 warstwami: poligony MZP, punkty ofert, bubble KPI per miasto, inwestycje deweloperskie."""
    fig = go.Figure()

    # ── Layer 1: MZP flood polygons — 1 trace per scenario ───────────────────
    features = geojson.get("features", [])
    for scenario in ["Q10%", "Q1%", "Q0.2%"]:
        if scenario not in active_scenarios:
            continue
        lats: list[float | None] = []
        lons: list[float | None] = []
        for feat in features:
            if feat.get("properties", {}).get("scenario") != scenario:
                continue
            geom = feat.get("geometry", {})
            rings = geom.get("coordinates", [])
            if not rings:
                continue
            for c in rings[0]:
                lons.append(float(c[0]))
                lats.append(float(c[1]))
            lons.append(None)
            lats.append(None)

        if lats:
            fig.add_trace(
                go.Scattermapbox(
                    lat=lats,
                    lon=lons,
                    mode="lines",
                    fill="toself",
                    fillcolor=_MZP_FILL.get(scenario, "rgba(128,128,128,0.3)"),
                    line=dict(
                        color=_MZP_LINE.get(scenario, "rgba(128,128,128,0.8)"),
                        width=1,
                    ),
                    name=FLOOD_LABELS.get(scenario, scenario),
                    hoverinfo="skip",
                    showlegend=True,
                )
            )

    # ── Layer 2: Kaggle listing scatter points ────────────────────────────────
    if not points_df.empty and "lat" in points_df.columns:
        pts = points_df.dropna(subset=["lat", "lon", "price_per_m2_pln"])
        district_col = pts["district"].fillna(pts["city"].str.title())
        custom = pts[["price_per_m2_pln", "area_m2", "rooms", "flood_scenario"]].copy()
        custom.insert(0, "district_display", district_col)

        # Clamp price colorscale to 5th–95th percentile so outliers don't wash out the gradient
        p5 = float(pts["price_per_m2_pln"].quantile(0.05))
        p95 = float(pts["price_per_m2_pln"].quantile(0.95))

        fig.add_trace(
            go.Scattermapbox(
                lat=pts["lat"],
                lon=pts["lon"],
                mode="markers",
                marker=dict(
                    size=9,
                    color=pts["price_per_m2_pln"],
                    colorscale="RdYlGn_r",
                    cmin=p5,
                    cmax=p95,
                    colorbar=dict(
                        title=dict(text="PLN/m²", side="right"),
                        x=0.88,
                        thickness=10,
                        len=0.4,
                        y=0.25,
                    ),
                    showscale=True,
                    opacity=0.75,
                ),
                customdata=custom.values,
                hovertemplate=(
                    "<b>%{customdata[0]}</b><br>"
                    "Cena/m²: <b>%{customdata[1]:,.0f} PLN</b><br>"
                    "Pow.: %{customdata[2]:.0f} m²"
                    " · Pokoje: %{customdata[3]}<br>"
                    "Strefa ryzyka: %{customdata[4]}"
                    "<extra></extra>"
                ),
                name="Ogłoszenia Kaggle",
                showlegend=True,
            )
        )

    # ── Layer 3: City KPI bubbles ─────────────────────────────────────────────
    if not city_kpi_df.empty:
        max_count = float(city_kpi_df["listing_count"].max()) or 1.0
        sizes = city_kpi_df["listing_count"].apply(
            lambda x: 20 + 35 * (float(x) / max_count)
        )
        custom_city = city_kpi_df[["city", "kpi_value", "listing_count"]].copy()

        fig.add_trace(
            go.Scattermapbox(
                lat=city_kpi_df["lat"],
                lon=city_kpi_df["lon"],
                mode="markers+text",
                marker=dict(
                    size=sizes,
                    color=city_kpi_df["kpi_value"],
                    colorscale="RdYlGn_r",
                    colorbar=dict(
                        title=dict(text=kpi_label, side="right"),
                        x=1.01,
                        thickness=12,
                    ),
                    showscale=True,
                    opacity=0.85,
                    sizemode="diameter",
                ),
                text=city_kpi_df["city"].str.title(),
                textfont=dict(size=11, color="#222"),
                textposition="top center",
                customdata=custom_city.values,
                hovertemplate=(
                    "<b>%{customdata[0]|title}</b><br>"
                    "KPI: <b>%{customdata[1]:.2f}</b><br>"
                    "Oferty: %{customdata[2]:,d}"
                    "<extra></extra>"
                ),
                name="KPI per miasto",
                showlegend=True,
            )
        )

    # ── Layer 4: Developer investment locations ───────────────────────────────
    if dev_df is not None and not dev_df.empty:
        dev = dev_df.dropna(subset=["lat", "lon"])
        if not dev.empty:
            custom_dev = dev[
                [
                    "developer_name",
                    "investment_name",
                    "city",
                    "street",
                    "unit_count",
                    "avg_price_m2_pln",
                ]
            ].copy()
            fig.add_trace(
                go.Scattermapbox(
                    lat=dev["lat"],
                    lon=dev["lon"],
                    mode="markers",
                    marker=dict(
                        size=14,
                        symbol="square",
                        color=COLORS["developer"],
                        opacity=0.9,
                    ),
                    customdata=custom_dev.values,
                    hovertemplate=(
                        "<b>%{customdata[1]}</b><br>"
                        "%{customdata[0]}<br>"
                        "%{customdata[3]}, %{customdata[2]}<br>"
                        "Lokale: <b>%{customdata[4]:,d}</b><br>"
                        "Śr. cena/m²: <b>%{customdata[5]:,.0f} PLN</b>"
                        "<extra></extra>"
                    ),
                    name="Inwestycje deweloperskie",
                    showlegend=True,
                )
            )

    fig.update_layout(
        mapbox=dict(
            style="open-street-map",
            zoom=5.5,
            center=dict(lat=52.1, lon=19.4),
        ),
        height=600,
        margin=dict(t=10, b=0, l=0, r=0),
        legend=dict(
            x=0.01,
            y=0.99,
            bgcolor="rgba(255,255,255,0.88)",
            bordercolor="#ccc",
            borderwidth=1,
            font=dict(size=12),
        ),
        uirevision="map",
    )
    return fig
