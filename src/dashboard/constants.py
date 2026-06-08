"""Dashboard constants — palette, cities, KPI labels."""

from src.api.config import Config

COLORS = {
    "price": "#185FA5",
    "deviation": "#533AB7",
    "affordability": "#1D9E75",
    "flood_extreme": "#E24B4A",
    "flood_high": "#EF9F27",
    "flood_moderate": "#FAC775",
    "developer": "#1D3557",
    "price_drop": "#D4537E",
    "nbp": "#888780",
    "sold": "#3B6D11",
    "reserved": "#633806",
}

CITIES: list[str] = Config().cities

# Kaggle ASCII / lowercase → display name from Config
CITY_DISPLAY: dict[str, str] = {
    "warszawa": "Warszawa",
    "krakow": "Kraków",
    "kraków": "Kraków",
    "wroclaw": "Wrocław",
    "wrocław": "Wrocław",
    "gdansk": "Gdańsk",
    "gdańsk": "Gdańsk",
    "poznan": "Poznań",
    "poznań": "Poznań",
    "lodz": "Łódź",
    "łódź": "Łódź",
    "katowice": "Katowice",
    "lublin": "Lublin",
    "szczecin": "Szczecin",
    "bydgoszcz": "Bydgoszcz",
}

FLOOD_SCENARIOS: list[str] = ["Q10%", "Q1%", "Q0.2%", "none"]
FLOOD_LABELS: dict[str, str] = {
    "Q10%": "Q10%",
    "Q1%": "Q1%",
    "Q0.2%": "Q0,2%",
    "none": "Brak ryzyka",
}

MARKET_OPTIONS: dict[str, str | None] = {
    "Wszystkie": None,
    "Pierwotny": "primary",
    "Wtórny": "secondary",
}

AMENITY_LABELS: dict[str, str] = {
    "balcony": "Balkon",
    "elevator": "Winda",
    "parking": "Parking",
    "security": "Ochrona",
}

DEFAULT_PERIOD_START = (2023, 1)
DEFAULT_PERIOD_END = (2024, 4)

# City center coordinates (WGS84) derived from AVG(lat/lon) of Dim_Geo_Location
CITY_COORDS: dict[str, tuple[float, float]] = {
    "warszawa": (52.230, 21.010),
    "krakow": (50.059, 19.956),
    "wroclaw": (51.108, 17.024),
    "gdansk": (54.362, 18.603),
    "lodz": (51.765, 19.457),
    "poznan": (52.410, 16.919),
    "gdynia": (54.514, 18.500),
    "lublin": (51.243, 22.548),
    "szczecin": (53.431, 14.553),
    "bydgoszcz": (53.122, 18.012),
    "katowice": (50.251, 19.012),
    "bialystok": (53.134, 23.143),
}

MAP_KPI_OPTIONS: dict[str, str] = {
    "Cena / m² (KPI 1)": "avg_price_m2",
    "Dostępność mieszk. (KPI 3)": "months_salary_per_m2",
    "Odchylenie od NBP (KPI 2)": "deviation_pct",
    "Dyskonto powodziowe (KPI 5)": "flood_premium_pct",
}
