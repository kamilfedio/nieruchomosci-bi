"""Streamlit dashboard — Mapa ryzyka i cen polskiego rynku mieszkaniowego."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Literal, cast

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import pandas as pd
import streamlit as st
from src.api.config import Config
from src.dashboard import charts
from src.dashboard.constants import (
    CITIES,
    FLOOD_LABELS,
    FLOOD_SCENARIOS,
    MAP_KPI_OPTIONS,
    MARKET_OPTIONS,
)
from src.dashboard.data import (
    DashboardFilters,
    all_period_labels,
    build_city_kpi,
    compute_kpi_metrics,
    filter_cities,
    filter_price_drops_detail,
    format_delta,
    format_delta_count,
    format_pct,
    format_pln,
    format_price_m2,
    get_filtered_views,
    has_data,
    load_demographics,
    load_developer_map_points,
    load_developer_summary,
    load_kpi_views,
    load_map_points,
    load_material_price_data,
    load_mzp_from_db,
    load_nbp_benchmark,
    load_pipeline_stats,
    load_dimension_stats,
    load_price_drops_detail,
    parse_period_label,
    period_bounds_from_data,
    ranking_table,
    trend_data,
)

st.set_page_config(
    page_title="Mapa ryzyka i cen — BI",
    page_icon="🏠",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown(
    """
    <style>
    @import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:wght@400;500;600&display=swap');
    html, body, [class*="css"] { font-family: 'IBM Plex Sans', sans-serif; }

    /* ── Przycisk drukowania ───────────────────────────────────────────── */
    #print-btn {
        position: fixed;
        top: 0.6rem;
        right: 1rem;
        z-index: 9999;
        background: #1D3557;
        color: #fff;
        border: none;
        border-radius: 6px;
        padding: 0.4rem 0.9rem;
        font-size: 0.85rem;
        font-family: 'IBM Plex Sans', sans-serif;
        cursor: pointer;
        box-shadow: 0 2px 6px rgba(0,0,0,0.2);
    }
    #print-btn:hover { background: #185FA5; }

    /* ── Tryb druku (@media print) ─────────────────────────────────────── */
    @media print {
        /* Ukryj elementy interaktywne */
        [data-testid="stSidebar"],
        [data-testid="stToolbar"],
        [data-testid="stDecoration"],
        [data-testid="stStatusWidget"],
        .stButton,
        #print-btn { display: none !important; }

        /* Pełna szerokość treści */
        .main .block-container {
            max-width: 100% !important;
            padding: 0.5rem 1.5rem !important;
        }

        /* Łamanie stron na dividerach */
        hr { page-break-after: always; border: none; margin: 0; }

        /* Zapobieganie łamaniu w środku wykresu / metryki */
        [data-testid="stPlotlyChart"],
        [data-testid="metric-container"],
        [data-testid="stDataFrame"] { page-break-inside: avoid; }

        /* Nagłówki — nie zostaną odcięte na dole strony */
        h2, h3, h4 { page-break-after: avoid; }

        /* Wydruk w kolorze — zachowaj kolory Plotly */
        * { -webkit-print-color-adjust: exact; print-color-adjust: exact; }
    }
    </style>

    <button id="print-btn" onclick="window.print()">&#128438; Eksportuj do PDF</button>
    """,
    unsafe_allow_html=True,
)


def _init_session_state() -> None:
    defaults = {
        "cities": CITIES,
        "market_label": "Wszystkie",
        "flood_scenarios": FLOOD_SCENARIOS,
        "rooms_range": (1, 5),
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


def _sync_period_filters(period_labels: list[str]) -> None:
    if (
        "period_start_label" not in st.session_state
        or st.session_state["period_start_label"] not in period_labels
    ):
        st.session_state["period_start_label"] = period_labels[0]
    if (
        "period_end_label" not in st.session_state
        or st.session_state["period_end_label"] not in period_labels
    ):
        st.session_state["period_end_label"] = period_labels[-1]


def _sidebar_filters(period_labels: list[str]) -> DashboardFilters:
    st.sidebar.title("Filtry")
    st.sidebar.caption("Mapa ryzyka i cen polskiego rynku mieszkaniowego")

    if st.sidebar.button("Zresetuj filtry"):
        for key in list(st.session_state.keys()):
            del st.session_state[key]
        st.rerun()

    cities = st.sidebar.multiselect(
        "Miasto",
        options=CITIES,
        default=st.session_state.get("cities", CITIES),
    )
    st.session_state["cities"] = cities or CITIES

    market_label = st.sidebar.radio(
        "Typ rynku",
        options=list(MARKET_OPTIONS.keys()),
        index=list(MARKET_OPTIONS.keys()).index(
            st.session_state.get("market_label", "Wszystkie")
        ),
    )
    st.session_state["market_label"] = market_label

    start_label = st.sidebar.select_slider(
        "Okres — od",
        options=period_labels,
        value=st.session_state.get("period_start_label", period_labels[0]),
    )
    end_label = st.sidebar.select_slider(
        "Okres — do",
        options=period_labels,
        value=st.session_state.get("period_end_label", period_labels[-1]),
    )
    st.session_state["period_start_label"] = start_label
    st.session_state["period_end_label"] = end_label

    flood = st.sidebar.multiselect(
        "Scenariusz ryzyka powodziowego",
        options=FLOOD_SCENARIOS,
        format_func=lambda x: FLOOD_LABELS[x],
        default=st.session_state.get("flood_scenarios", FLOOD_SCENARIOS),
    )
    st.session_state["flood_scenarios"] = flood or FLOOD_SCENARIOS

    rooms = cast(
        tuple[int, int],
        st.sidebar.slider(
            "Liczba pokoi",
            min_value=1,
            max_value=5,
            value=st.session_state.get("rooms_range", (1, 5)),
        ),
    )
    st.session_state["rooms_range"] = rooms

    st.sidebar.markdown("---")
    st.sidebar.markdown("**Źródła danych**")
    st.sidebar.caption("Kaggle · dane.gov.pl · NBP BaRN · GUS BDL · Wody Polskie MZP")

    start = parse_period_label(str(start_label))
    end = parse_period_label(str(end_label))
    if start > end:
        start, end = end, start

    return DashboardFilters(
        cities=st.session_state["cities"],
        market=MARKET_OPTIONS[market_label],
        period_start=start,
        period_end=end,
        flood_scenarios=st.session_state["flood_scenarios"],
        rooms_min=rooms[0],
        rooms_max=rooms[1],
    )


def _render_kpi_bar(metrics) -> None:
    cols = st.columns(6)
    price_label = (
        "Śr. czynsz / m²" if metrics.price_kind == "rent" else "Śr. cena ofertowa / m²"
    )
    aff_val = (
        f"{metrics.affordability_months:.1f}"
        if metrics.affordability_months is not None
        else "—"
    )
    items: list[tuple[str, str, str | None, Literal["normal", "inverse"]]] = [
        (
            price_label,
            format_price_m2(metrics.avg_price_m2, metrics.price_kind),
            format_delta(metrics.avg_price_m2_delta),
            "normal",
        ),
        (
            "Odchylenie od NBP",
            format_pct(metrics.nbp_deviation_pct),
            format_delta(metrics.nbp_deviation_delta, " pp"),
            "inverse",
        ),
        (
            "Dostępność (mies./m²)",
            aff_val,
            format_delta(metrics.affordability_delta),
            "inverse",
        ),
        (
            "Oferty w strefie ryzyka",
            str(metrics.flood_listing_count or "—"),
            format_delta_count(metrics.flood_listing_delta),
            "inverse",
        ),
        (
            "Tempo sprzedaży",
            str(metrics.sales_velocity or "—"),
            format_delta_count(metrics.sales_velocity_delta),
            "normal",
        ),
        (
            "Obniżki cen",
            str(metrics.drop_count or "—"),
            format_delta_count(metrics.drop_count_delta),
            "normal",
        ),
    ]
    for col, (label, value, delta, color) in zip(cols, items, strict=True):
        with col:
            col.metric(label, value, delta, delta_color=color)


def _render_map_section(
    kpi_data: dict,
    flt: DashboardFilters,
    config: Config,
) -> str | None:
    """Render interactive map. Returns clicked district name or None."""
    st.subheader("Mapa cen i ryzyka powodziowego")

    # Controls row
    ctrl1, ctrl2, ctrl3 = st.columns([2, 2, 1])
    with ctrl1:
        kpi_label = st.selectbox(
            "KPI na mapie",
            options=list(MAP_KPI_OPTIONS.keys()),
            key="map_kpi",
        )
    with ctrl2:
        active_scenarios = st.multiselect(
            "Strefy ryzyka MZP",
            options=["Q10%", "Q1%", "Q0.2%"],
            default=["Q1%", "Q0.2%"],
            format_func=lambda x: FLOOD_LABELS[x],
            key="map_scenarios",
        )
    with ctrl3:
        max_pts = st.select_slider(
            "Maks. punktów",
            options=[500, 1000, 3000, 5000],
            value=3000,
            key="map_pts",
        )

    # Load data — simplified polygons from PostGIS (~few MB vs 384 MB flat file)
    geojson = load_mzp_from_db(config.database_url)
    points_df = load_map_points(
        config.database_url,
        city_filter=tuple(flt.cities),
        year_start=flt.period_start[0],
        year_end=flt.period_end[0],
        max_points=max_pts,
    )
    dev_df = load_developer_map_points(
        config.database_url, city_filter=tuple(flt.cities)
    )
    city_kpi_df = build_city_kpi(kpi_data, MAP_KPI_OPTIONS[kpi_label], flt)

    # Render map — on_select="ignore" prevents zoom/pan from triggering full reruns
    fig = charts.map_chart(
        points_df, city_kpi_df, geojson, active_scenarios, kpi_label, dev_df
    )
    st.plotly_chart(fig, width="stretch", on_select="ignore", key="map_chart")

    st.caption(
        "Warstwa 1: poligony MZP (Wody Polskie) · "
        "Warstwa 2: ogłoszenia Kaggle (kolor = cena/m²) · "
        "Warstwa 3: KPI per miasto (rozmiar = liczba ofert) · "
        "Warstwa 4: inwestycje deweloperskie dane.gov.pl (kwadraty)."
    )
    return None


def main() -> None:
    _init_session_state()

    st.title("Mapa ryzyka i cen polskiego rynku mieszkaniowego")

    config = Config()
    try:
        with st.spinner("Ładowanie danych z hurtowni..."):
            kpi_data = load_kpi_views(config.database_url)
            nbp = load_nbp_benchmark(config.database_url)
            demographics = load_demographics(config.database_url)
            drops_detail = load_price_drops_detail(config.database_url)
            pipeline = load_pipeline_stats(config.database_url)
            material_df = load_material_price_data(config.database_url)
    except Exception as exc:
        st.error(f"Nie udało się połączyć z bazą danych: {exc}")
        st.info("Uruchom `docker compose up -d` i załaduj dane pipeline'ami Airflow.")
        return

    if not has_data(kpi_data):
        st.warning(
            "Hurtownia jest pusta. Uruchom pipeline'y ELT przed korzystaniem z dashboardu."
        )
        return

    bounds = period_bounds_from_data(kpi_data)
    period_labels = all_period_labels(bounds[0], bounds[1])
    _sync_period_filters(period_labels)
    flt = _sidebar_filters(period_labels)

    st.caption(
        "Ceny ofertowe (Kaggle / deweloperzy) vs ceny transakcyjne (NBP BaRN) · "
        f"Dostępne dane: {bounds[0][0]} Q{bounds[0][1]} – {bounds[1][0]} Q{bounds[1][1]} · "
        f"Filtr: {flt.period_start[0]} Q{flt.period_start[1]} – "
        f"{flt.period_end[0]} Q{flt.period_end[1]}"
    )

    dev_summary_df = load_developer_summary(config.database_url, tuple(flt.cities))

    metrics = compute_kpi_metrics(kpi_data, nbp, flt, demographics)
    views = get_filtered_views(kpi_data, flt)
    rank_df = ranking_table(kpi_data, nbp, flt)
    trend_df = trend_data(kpi_data, nbp, flt)
    drops_df = filter_price_drops_detail(drops_detail, flt)

    if views["listings"].empty:
        st.warning(
            "Brak danych dla wybranych filtrów. Rozszerz zakres okresu "
            f"(dane: {bounds[0][0]} Q{bounds[0][1]} – {bounds[1][0]} Q{bounds[1][1]}) "
            "lub zmień miasta / typ rynku."
        )

    st.markdown("### Kluczowe wskaźniki")
    st.caption(
        "Delty w stosunku do poprzedniego kwartału. "
        "Źródła: ogłoszenia Kaggle (195k+) · deweloperzy dane.gov.pl · NBP BaRN · GUS BDL."
    )
    if metrics.price_kind == "rent":
        st.warning(
            "Źródło Kaggle zawiera **ceny najmu** (nie sprzedaży). "
            "Uruchom ponownie pipeline Kaggle po aktualizacji scrapera."
        )
    if metrics.nbp_deviation_pct is None:
        st.info(
            "Odchylenie od NBP niedostępne — brak wspólnych kwartałów "
            "między ogłoszeniami a benchmarkiem NBP BaRN dla wybranych miast."
        )
    _render_kpi_bar(metrics)

    st.divider()

    # ── Mapa + rankingi boczne ────────────────────────────────────────────────
    map_col, side_col = st.columns([0.65, 0.35])
    with map_col:
        try:
            _render_map_section(kpi_data, flt, config)
        except Exception as exc:
            st.error(f"Błąd renderowania mapy: {exc}")
            st.caption("Sprawdź logi serwera po szczegóły.")
    with side_col:
        st.plotly_chart(charts.ranking_chart(rank_df), width="stretch")
        st.caption(
            "Średnia cena ofertowa/m² z ogłoszeń Kaggle per miasto "
            "w wybranym przedziale czasowym."
        )
        st.plotly_chart(charts.flood_premium_chart(views["kpi05"]), width="stretch")
        st.caption(
            "Różnica ceny/m² między ofertami w strefie ryzyka MZP "
            "a ofertami poza strefą w tym samym mieście. "
            "Wartość dodatnia = premia, ujemna = dyskonto."
        )
        st.plotly_chart(charts.flood_risk_chart(views["kpi04"]), width="stretch")
        st.caption(
            "Liczba ogłoszeń Kaggle zlokalizowanych w poligonach MZP "
            "(Mapy Zagrożenia Powodziowego, Wody Polskie). "
            "Q10% = raz na 10 lat, Q1% = raz na 100 lat, Q0,2% = ekstremalne."
        )

    st.divider()

    # ── Trendy cenowe ─────────────────────────────────────────────────────────
    trend_col, dev_col = st.columns(2)
    with trend_col:
        st.markdown("#### Trendy cenowe i odchylenie od NBP")
        st.caption(
            "Ogłoszenia Kaggle (ceny ofertowe) zestawione z cenami transakcyjnymi "
            "NBP BaRN. Odchylenie dodatnie oznacza, że oferty są droższe od "
            "faktycznie zawieranych transakcji."
        )
        st.plotly_chart(charts.trend_chart(trend_df), width="stretch")
        st.plotly_chart(charts.offer_vs_nbp_chart(views["kpi02"]), width="stretch")
        st.caption(
            "Źródło cen ofertowych: Kaggle Apartment Prices in Poland. "
            "Źródło cen transakcyjnych: NBP BaRN (Baza Rynku Nieruchomości)."
        )

    with dev_col:
        st.markdown("#### Panel deweloperski — dane.gov.pl")
        st.caption(
            "Dane z rejestru cen lokali deweloperskich (ustawa o jawności cen). "
            "Obejmuje tylko deweloperów, którzy opublikowali pliki CSV/XLSX."
        )
        sold_value = (
            views["kpi07"]["total_value_pln"].sum()
            if not views["kpi07"].empty
            else None
        )
        st.metric(
            "Łączna wartość sprzedanych / zarezerwowanych lokali (KPI 7)",
            format_pln(sold_value),
            help="SUM(cena_calkowita) dla lokali ze statusem sprzedany lub zarezerwowany.",
        )

        st.plotly_chart(charts.sales_velocity_chart(views["kpi06"]), width="stretch")
        st.caption(
            "Liczba lokali deweloperskich z tygodniową zmianą statusu "
            "na zarezerwowany lub sprzedany. Wymaga załadowania plików "
            "ze starszym formatem dane.gov.pl (ze statusem dostępności)."
        )

        st.markdown("**Obniżki cen lokali deweloperskich (KPI 8)**")
        st.caption(
            "Zdarzenia, w których cena lokalu spadła w stosunku do poprzedniego snapshota."
        )
        if drops_df.empty:
            st.info("Brak obniżek cen dla wybranych filtrów.")
        else:
            display = drops_df[
                [
                    "developer_name",
                    "investment_id",
                    "city",
                    "drop_date",
                    "change_amount_pln",
                    "unit_value_pln",
                ]
            ].rename(  # type: ignore[call-overload]
                columns={
                    "developer_name": "Deweloper",
                    "investment_id": "Inwestycja",
                    "city": "Miasto",
                    "drop_date": "Data obniżki",
                    "change_amount_pln": "Kwota obniżki PLN",
                    "unit_value_pln": "Cena po obniżce PLN",
                }
            )
            st.dataframe(display, width="stretch", hide_index=True)

    st.divider()

    # ── Dostępność, struktura rynku, udogodnienia ─────────────────────────────
    aff_col, share_col, amen_col = st.columns(3)
    with aff_col:
        st.plotly_chart(charts.affordability_chart(views["kpi03"]), width="stretch")
        st.caption(
            "Ile miesięcy wynagrodzenia brutto (GUS BDL) kosztuje 1 m² mieszkania "
            "per miasto. Im niższa wartość, tym większa dostępność. "
            "Wynagrodzenia GUS mogą pochodzić z roku poprzedniego (dane roczne)."
        )
    with share_col:
        st.plotly_chart(charts.primary_share_chart(views["kpi09"]), width="stretch")
        st.caption(
            "Udział ogłoszeń z rynku pierwotnego (nowe budownictwo) "
            "w całkowitej liczbie ofert Kaggle per miasto. "
            "Rynek pierwotny = apartamentBuilding."
        )
    with amen_col:
        st.plotly_chart(charts.amenity_premium_chart(views["kpi10"]), width="stretch")
        st.caption(
            "Różnica średniej ceny/m² między lokalami posiadającymi "
            "dane udogodnienie a lokalami bez niego (kontrolowana per miasto i pokoje). "
            "Klimatyzacja niedostępna w zbiorze Kaggle."
        )

    st.divider()

    # ── Analiza pogłębiona ────────────────────────────────────────────────────
    st.markdown("### Analiza rynku — wykresy pogłębione")
    st.caption(
        "Rozkłady, korelacje i rankingi wykraczające poza podstawowe KPI. "
        "Filtry miasta i okresu są aktywne."
    )

    adv_col1, adv_col2 = st.columns(2)
    with adv_col1:
        st.plotly_chart(charts.rooms_price_chart(views["listings"]), width="stretch")
        st.caption(
            "Rozkład cen ofertowych/m² (mediana + kwartyle) per liczba pokoi. "
            "Mniejsze mieszkania często osiągają wyższą cenę/m² ze względu na lokalizację i standard."
        )
    with adv_col2:
        kpi01_raw = kpi_data.get("vw_kpi_01_avg_offer_price_m2", pd.DataFrame())
        kpi01_flt = kpi01_raw if kpi01_raw is not None else pd.DataFrame()
        if not kpi01_flt.empty and flt.cities:
            kpi01_flt = filter_cities(kpi01_flt, "city", flt.cities)
        st.plotly_chart(charts.yoy_growth_chart(kpi01_flt), width="stretch")
        st.caption(
            "Procentowa zmiana średniej ceny ofertowej/m² rok do roku per miasto. "
            "Umożliwia porównanie dynamiki wzrostu cen między rynkami."
        )

    adv_col3, adv_col4 = st.columns(2)
    with adv_col3:
        st.plotly_chart(charts.salary_vs_price_scatter(views["kpi03"]), width="stretch")
        st.caption(
            "Zależność między średnim wynagrodzeniem brutto (GUS BDL) "
            "a średnią ceną/m² per miasto. "
            "Miasta powyżej linii trendu mają relatywnie droższe mieszkania."
        )
    with adv_col4:
        st.plotly_chart(charts.area_price_chart(views["listings"]), width="stretch")
        st.caption(
            "Średnia cena/m² w zależności od przedziału powierzchni mieszkania. "
            "Efekt skali: większe lokale zwykle tańsze per m²."
        )

    adv_col5, adv_col6 = st.columns(2)
    with adv_col5:
        mat_flt = material_df if not material_df.empty else pd.DataFrame()
        if not mat_flt.empty and flt.cities:
            mat_flt = filter_cities(mat_flt, "city", flt.cities)
        st.plotly_chart(charts.material_price_chart(mat_flt), width="stretch")
        st.caption(
            "Średnia cena ofertowa/m² wg materiału budowlanego (dane Kaggle). "
            "Cegła i beton komórkowy dominują w starszych zasobach."
        )
    with adv_col6:
        st.plotly_chart(charts.developer_ranking_chart(dev_summary_df), width="stretch")
        st.caption(
            "TOP 15 deweloperów wg łącznej wartości lokali (sprzedanych/zarezerwowanych) "
            "z rejestru dane.gov.pl. Rozmiar = suma cen lokali."
        )

    st.divider()

    # ── Statystyki tabel wymiarów ─────────────────────────────────────────────
    with st.expander("Statystyki tabel wymiarów", expanded=False):
        dim_stats = load_dimension_stats(config.database_url)

        st.markdown("#### Dim_Geo_Location — zasięg geograficzny")
        if not dim_stats["geo"].empty:
            st.dataframe(dim_stats["geo"], hide_index=True, width="stretch")
        st.caption(
            "Unikalne lokalizacje (city + lat_r/lon_r ≈ 111 m) i dzielnice per miasto."
        )

        dcol1, dcol2 = st.columns(2)
        with dcol1:
            st.markdown("#### Dim_Unit_Type — rozkład atrybutów")
            if not dim_stats["unit_type"].empty:
                st.dataframe(
                    dim_stats["unit_type"], hide_index=True, width="stretch"
                )
            st.caption(
                "Rozkład liczby pokoi. Kolumny pct_* = % typów lokali z danym udogodnieniem."
            )
        with dcol2:
            st.markdown("#### Dim_Demographics — wskaźniki GUS BDL")
            if not dim_stats["demographics"].empty:
                st.dataframe(
                    dim_stats["demographics"],
                    hide_index=True,
                    width="stretch",
                )
            st.caption("Zakres lat, śr. wynagrodzenie brutto i populacja per miasto.")

        dcol3, dcol4 = st.columns(2)
        with dcol3:
            st.markdown("#### Dim_Investment — aktywność deweloperska")
            if not dim_stats["investment"].empty:
                st.dataframe(
                    dim_stats["investment"],
                    hide_index=True,
                    width="stretch",
                )
            st.caption("Unikalnych deweloperów i inwestycji per miasto (SCD2).")
        with dcol4:
            st.markdown("#### Dim_Flood_Risk + flood_zones")
            if not dim_stats["flood_risk"].empty:
                st.dataframe(
                    dim_stats["flood_risk"],
                    hide_index=True,
                    width="stretch",
                )
            st.caption("Słownik 4-wierszowy + liczba poligonów MZP per scenariusz.")

        st.markdown("#### Dim_Time — zakres danych")
        tr = dim_stats.get("time_range", pd.DataFrame())
        if not tr.empty:
            tm1, tm2, tm3 = st.columns(3)
            tm1.metric("Najstarszy wpis", str(tr["min_date"].iloc[0]))
            tm2.metric("Najnowszy wpis", str(tr["max_date"].iloc[0]))
            tm3.metric(
                "Zakres (lata)",
                f"{tr['min_year'].iloc[0]} – {tr['max_year'].iloc[0]}",
            )

    st.divider()

    # ── Status ETL ────────────────────────────────────────────────────────────
    with st.expander("Status danych i pipeline ETL", expanded=False):
        total = int(pipeline["row_count"].sum())  # type: ignore[arg-type]
        st.metric(
            "Łączna liczba rekordów w tabelach faktów i wymiarów",
            f"{total:,}".replace(",", " "),
        )
        st.caption(
            "Pipelines Airflow: mzp_pipeline → gus_bdl_pipeline → "
            "kaggle_pipeline → gov_data_pipeline → nbp_pipeline"
        )
        st.dataframe(
            pipeline.rename(
                columns={"source": "Źródło", "row_count": "Liczba rekordów"}
            ),
            width="stretch",
            hide_index=True,
        )


if __name__ == "__main__":
    main()
