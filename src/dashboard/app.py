"""Streamlit dashboard — Wielowymiarowa analiza polskiego rynku mieszkaniowego."""

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
from src.dashboard.auth import render_login_form
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
    load_dimension_stats,
    load_kpi_views,
    load_map_points,
    load_material_price_data,
    load_migration_growth_data,
    load_mzp_from_db,
    load_nbp_benchmark,
    load_pipeline_stats,
    load_price_drops_detail,
    parse_period_label,
    period_bounds_from_data,
    ranking_table,
    trend_data,
)

st.set_page_config(
    page_title="Analiza rynku nieruchomości — BI",
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
        "role": None,
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
    st.sidebar.caption("Wielowymiarowa analiza polskiego rynku mieszkaniowego")

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
) -> None:
    st.markdown("#### Interaktywna mapa cen i stref powodziowych")
    st.caption(
        "Warstwa 1 (kolory): poligony MZP (Wody Polskie) — strefy zagrożenia powodzią. "
        "Warstwa 2 (punkty): ogłoszenia Kaggle — kolor od zielonego (tanie) do czerwonego (drogie). "
        "Warstwa 3 (bąbelki): wybrany KPI zagregowany per miasto. "
        "Warstwa 4 (kwadraty): inwestycje deweloperskie z rejestru dane.gov.pl."
    )

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

    geojson = load_mzp_from_db(config.analyst_database_url)
    points_df = load_map_points(
        config.analyst_database_url,
        city_filter=tuple(flt.cities),
        year_start=flt.period_start[0],
        year_end=flt.period_end[0],
        max_points=max_pts,
    )
    dev_df = load_developer_map_points(
        config.analyst_database_url, city_filter=tuple(flt.cities)
    )
    city_kpi_df = build_city_kpi(kpi_data, MAP_KPI_OPTIONS[kpi_label], flt)

    fig = charts.map_chart(
        points_df, city_kpi_df, geojson, active_scenarios, kpi_label, dev_df
    )
    st.plotly_chart(fig, width="stretch", on_select="ignore", key="map_chart")


def main() -> None:
    _init_session_state()

    config = Config()

    if not st.session_state.get("role"):
        render_login_form(config)
        return

    if st.sidebar.button("Wyloguj"):
        st.session_state["role"] = None
        st.rerun()

    st.title("Wielowymiarowa analiza polskiego rynku mieszkaniowego")
    st.caption(
        "System BI analizuje ceny ofertowe i transakcyjne, ryzyko powodziowe, dostępność mieszkaniową "
        "oraz aktywność deweloperską w 15 największych miastach Polski. "
        "Źródła: ogłoszenia Kaggle (266k+) · dane.gov.pl · NBP BaRN · GUS BDL · Wody Polskie MZP."
    )
    st.info("**Odbiorca:** Dyrektor ds. Inwestycji", icon="👤")
    st.caption(
        "**Scenariusz użycia:** Dyrektor ds. Inwestycji poszukuje optymalnej lokalizacji pod nowy projekt "
        "deweloperski. Priorytetem jest **bezpieczna inwestycja pod względem ryzyka powodziowego** — "
        "wybierane są wyłącznie miasta, w których znikomy odsetek ofert leży w strefach zagrożenia, "
        "co chroni wartość portfela nieruchomości i minimalizuje ryzyko strat w przypadku podtopień. "
        "Analiza obejmuje identyfikację miast o wysokim popycie mieszkaniowym — "
        "rosnące ceny transakcyjne, niski czas ekspozycji ofert, korzystne saldo migracji oraz "
        "ograniczone ryzyko powodziowe — tak aby wybudowane lokale cieszyły się realnym zainteresowaniem "
        "nabywców i zapewniały zwrot z inwestycji. "
        "Docelową grupą nabywców są mieszkańcy danego miasta — osoby poszukujące lokalu na własne potrzeby, "
        "a nie inwestorzy zewnętrzni czy migranci — co oznacza priorytet dla rynków z ugruntowaną "
        "lokalną siłą nabywczą i rosnącym popytem wewnętrznym. "
        "Lokalizacje z wysokim udziałem ofert w strefach zagrożenia powodziowego są wykluczane, "
        "ponieważ świadomi lokalnych warunków nabywcy unikają takich nieruchomości, "
        "co bezpośrednio obniża płynność sprzedaży i osiągalne ceny."
    )

    try:
        with st.spinner("Ładowanie danych z hurtowni..."):
            kpi_data = load_kpi_views(config.analyst_database_url)
            nbp = load_nbp_benchmark(config.analyst_database_url)
            demographics = load_demographics(config.analyst_database_url)
            drops_detail = load_price_drops_detail(config.analyst_database_url)
            pipeline = load_pipeline_stats(config.analyst_database_url)
            material_df = load_material_price_data(config.analyst_database_url)
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
        f"Dostępne dane: {bounds[0][0]} Q{bounds[0][1]} – {bounds[1][0]} Q{bounds[1][1]} · "
        f"Aktywny filtr: {flt.period_start[0]} Q{flt.period_start[1]} – "
        f"{flt.period_end[0]} Q{flt.period_end[1]}"
    )

    dev_summary_df = load_developer_summary(config.analyst_database_url, tuple(flt.cities))

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

    # ── SEKCJA 1: Kluczowe wskaźniki ─────────────────────────────────────────
    st.markdown("### Kluczowe wskaźniki rynku")
    st.caption(
        "Wartości zagregowane dla wybranego okresu i filtrów. "
        "Delty (strzałki) pokazują zmianę względem poprzedniego kwartału. "
        "Czerwona strzałka przy 'Odchyleniu od NBP' i 'Dostępności' oznacza pogorszenie sytuacji nabywców."
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

    # ── SEKCJA 2: Mapa + Ranking miast ───────────────────────────────────────
    st.markdown("### Mapa i ranking miast")
    map_col, side_col = st.columns([0.65, 0.35])
    with map_col:
        try:
            _render_map_section(kpi_data, flt, config)
        except Exception as exc:
            st.error(f"Błąd renderowania mapy: {exc}")
            st.caption("Sprawdź logi serwera po szczegóły.")
    with side_col:
        st.markdown("#### Ranking miast — śr. cena ofertowa / m²")
        st.caption(
            "Średnia cena ofertowa za m² z ogłoszeń Kaggle per miasto, w wybranym przedziale "
            "czasowym i filtrach. Pozwala szybko porównać poziom cen między rynkami."
        )
        st.plotly_chart(charts.ranking_chart(rank_df), width="stretch")

    st.divider()

    # ── SEKCJA 3: Ceny i trendy (OLAP 1) ────────────────────────────────────
    st.markdown("### Trendy cenowe — oferty vs transakcje (OLAP 1)")
    st.caption(
        "**Pytanie:** Jaka jest procentowa różnica między średnią ceną ofertową (Kaggle) "
        "a ceną transakcyjną (NBP BaRN) per miasto i kwartał? "
        "Identyfikuje miasta o największym przewartościowaniu rynku."
    )
    st.plotly_chart(charts.trend_chart(trend_df), width="stretch")
    st.caption(
        "**Linia niebieska** = średnia cena ofertowa (Kaggle, ogłoszenia kupna). "
        "**Linia pomarańczowa przerywana** = średnia cena transakcyjna z aktów notarialnych (NBP BaRN, rynek pierwotny). "
        "**Odchylenie** (prawa oś, szara linia) = o ile % oferty są droższe od faktycznych transakcji — "
        "wskaźnik 'przegrzania' rynku. Wartość +20% oznacza, że sprzedający żądają o 20% więcej niż rynek płaci."
    )

    st.divider()

    # ── SEKCJA 4: Ryzyko powodziowe (OLAP 2, 5) ──────────────────────────────
    st.markdown("### Ryzyko powodziowe a ceny mieszkań (OLAP 2, 5)")
    st.caption(
        "**OLAP 2:** Czy i o ile % mieszkania w strefach najwyższego zagrożenia powodziowego "
        "są tańsze od lokali w bezpiecznych rejonach tej samej dzielnicy? "
        "**OLAP 5:** Liczba i wartość ofert z rynku pierwotnego narażonych na ryzyko powodzi."
    )
    flood_col1, flood_col2 = st.columns(2)
    with flood_col1:
        st.markdown("#### Dyskonto / premia powodziowa per scenariusz (OLAP 2, KPI 5)")
        st.plotly_chart(charts.flood_premium_chart(views["kpi05"]), width="stretch")
        st.caption(
            "Różnica między średnią ceną/m² ofert w strefie ryzyka MZP "
            "a ofertami w bezpiecznych lokalizacjach **tej samej dzielnicy**. "
            "**Wartość ujemna** (dyskonto) = oferty w strefie są tańsze — szansa negocjacyjna dla kupujących. "
            "**Wartość dodatnia** (premia) = strefa ryzykowna paradoksalnie droższa (np. atrakcyjna lokalizacja). "
            "Q10% = powódź raz na 10 lat, Q1% = raz na 100 lat, Q0,2% = ekstremalna."
        )
    with flood_col2:
        st.markdown("#### Oferty w strefach zagrożenia powodziowego per miasto (OLAP 5, KPI 4)")
        st.plotly_chart(charts.flood_risk_chart(views["kpi04"]), width="stretch")
        st.caption(
            "Liczba ogłoszeń Kaggle zlokalizowanych w poligonach MZP (Mapy Zagrożenia Powodziowego, Wody Polskie) "
            "per miasto i scenariusz. "
            "Dane obejmują wszystkie typy rynku (pierwotny + wtórny). "
            "Filtr 'Scenariusz ryzyka powodziowego' w panelu bocznym ogranicza widoczne strefy."
        )

    st.divider()

    # ── SEKCJA 5: Dostępność i demografia (OLAP 3, 7) ────────────────────────
    st.markdown("### Dostępność mieszkaniowa i demografia (OLAP 3, 7)")
    st.caption(
        "**OLAP 3:** Ile miesięcy przeciętnego wynagrodzenia brutto potrzeba na zakup 1 m²? "
        "**OLAP 7:** Jak saldo migracji netto koreluje ze wzrostem cen — gdzie rośnie presja popytowa?"
    )
    dem_col1, dem_col2, dem_col3 = st.columns(3)
    with dem_col1:
        st.markdown("#### Miesięcy pracy na 1 m² (OLAP 3, KPI 3)")
        st.plotly_chart(charts.affordability_chart(views["kpi03"]), width="stretch")
        st.caption(
            "Wskaźnik dostępności mieszkaniowej: śr. cena/m² podzielona przez śr. wynagrodzenie brutto (GUS BDL). "
            "Im **niższa wartość**, tym bardziej dostępny rynek. "
            "Kolory: zielony ≤ 1,2 mies., pomarańczowy 1,2–1,6 mies., czerwony > 1,6 mies. "
            "Przerywana linia = mediana dla wybranych miast. "
            "Wynagrodzenia GUS mogą dotyczyć poprzedniego roku (dane roczne)."
        )
    with dem_col2:
        st.markdown("#### Wynagrodzenie vs cena/m² per miasto (KPI 3)")
        st.plotly_chart(charts.salary_vs_price_scatter(views["kpi03"]), width="stretch")
        st.caption(
            "Każda bańka = jedno miasto. Oś X = śr. wynagrodzenie brutto (GUS BDL), "
            "oś Y = śr. cena ofertowa/m² (Kaggle). "
            "Rozmiar bańki = liczba ofert. "
            "Miasta wysoko ponad linią trendu mają ceny nieproporcjonalnie wysokie względem zarobków."
        )
    with dem_col3:
        st.markdown("#### Saldo migracji vs wzrost cen r/r (OLAP 7)")
        migration_df = load_migration_growth_data(
            config.analyst_database_url, tuple(flt.cities)
        )
        st.plotly_chart(charts.migration_price_scatter(migration_df), width="stretch")
        st.caption(
            "Oś X = śr. saldo migracji netto (napływ minus odpływ mieszkańców, GUS BDL). "
            "Oś Y = śr. roczny wzrost cen ofertowych (YoY %). "
            "**Prawy górny kwadrant** (migracja dodatnia + wzrost cen) = rynki wschodzące pod presją popytu. "
            "Rozmiar bańki = populacja miasta."
        )

    st.divider()

    # ── SEKCJA 6: Struktura rynku (OLAP 9, OLAP 1 YoY) ──────────────────────
    st.markdown("### Struktura rynku i dynamika cen (OLAP 9, OLAP 1)")
    st.caption(
        "**OLAP 9:** Jaki jest udział rynku pierwotnego w ofertach i jak zmienia się "
        "przeciętna oferowana powierzchnia w segmencie pierwotnym vs wtórnym? "
        "**OLAP 1 (YoY):** Jak dynamika wzrostu cen różni się między miastami rok do roku?"
    )
    struct_col1, struct_col2, struct_col3 = st.columns(3)
    with struct_col1:
        st.markdown("#### Udział rynku pierwotnego w ofertach (OLAP 9, KPI 9)")
        st.plotly_chart(charts.primary_share_chart(views["kpi09"]), width="stretch")
        st.caption(
            "Procentowy udział ogłoszeń z rynku pierwotnego (nowe budownictwo) "
            "w całkowitej liczbie ofert Kaggle per miasto (pierwotny + wtórny). "
            "Wysoki udział = miasto zdominowane przez deweloperów i nowe inwestycje."
        )
    with struct_col2:
        st.markdown("#### Średnia powierzchnia: pierwotny vs wtórny (OLAP 9)")
        st.plotly_chart(charts.area_by_market_chart(views["listings"]), width="stretch")
        st.caption(
            "Porównanie średniej oferowanej powierzchni (m²) per segment rynku i kwartał. "
            "Jeśli rynek pierwotny wykazuje trend malejący, deweloperzy budują coraz mniejsze lokale "
            "— efekt rosnących cen/m² i ograniczonej zdolności kredytowej kupujących."
        )
    with struct_col3:
        kpi01_raw = kpi_data.get("vw_kpi_01_avg_offer_price_m2", pd.DataFrame())
        kpi01_flt = kpi01_raw if kpi01_raw is not None else pd.DataFrame()
        if not kpi01_flt.empty and flt.cities:
            kpi01_flt = filter_cities(kpi01_flt, "city", flt.cities)
        st.markdown("#### Wzrost cen rok do roku per miasto (OLAP 1, KPI 1)")
        st.plotly_chart(charts.yoy_growth_chart(kpi01_flt), width="stretch")
        st.caption(
            "Procentowa zmiana średniej ceny ofertowej/m² rok do roku (YoY) per miasto. "
            "Słupki powyżej 0% = wzrost cen w danym roku. "
            "Pozwala porównać, które rynki rosły szybciej i czy dynamika zwalnia."
        )

    st.divider()

    # ── SEKCJA 7: Cechy lokali i udogodnienia (OLAP 10) ──────────────────────
    st.markdown("### Cechy lokali — premia i rozkład cen (OLAP 10)")
    st.caption(
        "**OLAP 10:** O ile średnio droższy jest lokal z balkonem, windą lub miejscem parkingowym "
        "w porównaniu do podobnych lokali bez tych udogodnień? "
        "Dane pomocnicze dla flipperów i doradców klientów."
    )
    feat_col1, feat_col2, feat_col3 = st.columns(3)
    with feat_col1:
        st.markdown("#### Premia za udogodnienia (OLAP 10, KPI 10)")
        st.plotly_chart(charts.amenity_premium_chart(views["kpi10"]), width="stretch")
        st.caption(
            "Różnica średniej ceny/m² między lokalami **z** danym udogodnieniem "
            "a lokalami **bez** niego (kontrolowana per miasto i liczba pokoi). "
            "Premia wyrażona w %. "
            "Klimatyzacja niedostępna w zbiorze Kaggle — brak w danych źródłowych."
        )
    with feat_col2:
        st.markdown("#### Rozkład cen/m² wg liczby pokoi")
        st.plotly_chart(charts.rooms_price_chart(views["listings"]), width="stretch")
        st.caption(
            "Box plot cen ofertowych/m² per liczba pokoi (mediana + kwartyle, bez wartości odstających). "
            "Kawalerki i małe mieszkania często droższe/m² ze względu na lokalizację i standard. "
            "Szersze pudełko = większe zróżnicowanie cen w tej kategorii."
        )
    with feat_col3:
        mat_flt = material_df if not material_df.empty else pd.DataFrame()
        if not mat_flt.empty and flt.cities:
            mat_flt = filter_cities(mat_flt, "city", flt.cities)
        st.markdown("#### Śr. cena/m² wg materiału budowlanego")
        st.plotly_chart(charts.material_price_chart(mat_flt), width="stretch")
        st.caption(
            "Średnia cena ofertowa/m² per materiał budowlany (Kaggle). "
            "Dane pomocnicze przy wycenie remontów i ocenie standardu budynku. "
            "Obejmuje tylko materiały z co najmniej 5 ogłoszeniami w wybranym filtrze."
        )

    st.divider()

    # ── SEKCJA 8: Panel deweloperski (OLAP 4, 8) ─────────────────────────────
    st.markdown("### Panel deweloperski — dane.gov.pl (OLAP 4, 8)")
    st.caption(
        "**OLAP 4:** Jak zmienia się liczba i wartość lokali przechodzących ze statusu "
        "'dostępny' na 'zarezerwowany'/'sprzedany' w kolejnych tygodniach? "
        "**OLAP 8:** Gdzie i jak często deweloperzy obniżają ceny dostępnych lokali? "
        "Dane wyłącznie z rejestru deweloperów, którzy opublikowali pliki CSV/XLSX w rejestrze dane.gov.pl."
    )
    dev_col1, dev_col2 = st.columns(2)
    with dev_col1:
        sold_value = (
            views["kpi07"]["total_value_pln"].sum()
            if not views["kpi07"].empty
            else None
        )
        st.metric(
            "Łączna wartość sprzedanych / zarezerwowanych lokali (KPI 7)",
            format_pln(sold_value),
            help=(
                "Suma cen lokali deweloperskich, które przeszły na status sprzedany lub zarezerwowany "
                "w wybranym okresie i miastach. Źródło: Fact_Change z rejestru dane.gov.pl."
            ),
        )
        st.markdown("#### Tygodniowe tempo sprzedaży (OLAP 4, KPI 6)")
        st.plotly_chart(charts.sales_velocity_chart(views["kpi06"]), width="stretch")
        st.caption(
            "Liczba lokali deweloperskich ze zmianą statusu na **zarezerwowany** lub **sprzedany** "
            "per tydzień (dane.gov.pl). "
            "Nagły wzrost = ożywienie popytu lub otwarcie nowej inwestycji. "
            "Spadek przez kilka tygodni = sygnał słabnącego popytu."
        )
    with dev_col2:
        st.markdown("#### Obniżki cen lokali deweloperskich (OLAP 8, KPI 8)")
        st.caption(
            "Zdarzenia, w których cena konkretnego lokalu **spadła** w stosunku do poprzedniego "
            "snapshota (dane.gov.pl). Częste obniżki w tym samym mieście = sygnał problemu ze sprzedażą. "
            "Tabela pokazuje 50 największych obniżek dla wybranego okresu i miast."
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

        st.markdown("#### TOP 15 deweloperów wg wartości lokali")
        st.plotly_chart(charts.developer_ranking_chart(dev_summary_df), width="stretch")
        st.caption(
            "Ranking deweloperów z rejestru dane.gov.pl według łącznej wartości "
            "sprzedanych i zarezerwowanych lokali. "
            "Rozmiar słupka = suma cen lokali (mln PLN). "
            "Obejmuje wyłącznie deweloperów z opublikowanymi plikami z historią statusów."
        )

    st.divider()

    # ── SEKCJA 9: Statystyki wymiarów (tylko admin) ───────────────────────────
    if st.session_state.get("role") == "admin":
        with st.expander("Statystyki tabel wymiarów (admin)", expanded=False):
            dim_stats = load_dimension_stats(config.analyst_database_url)

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

    # ── SEKCJA 10: Status ETL (tylko admin) ───────────────────────────────────
    if st.session_state.get("role") == "admin":
        with st.expander("Status danych i pipeline ETL (admin)", expanded=False):
            total = int(pipeline["row_count"].sum())  # type: ignore[arg-type]
            st.metric(
                "Łączna liczba rekordów w tabelach faktów i wymiarów",
                f"{total:,}".replace(",", " "),
            )
            st.caption(
                "Kolejność uruchamiania pipeline'ów: "
                "mzp_pipeline → gus_bdl_pipeline → kaggle_pipeline → gov_data_pipeline → nbp_pipeline"
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
