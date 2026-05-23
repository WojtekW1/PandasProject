"""
Analiza trendów zanieczyszczenia powietrza w Polsce (PM2.5) - 2015-2024
Źródło danych: GIOŚ - Główny Inspektorat Ochrony Środowiska
Pytania badawcze:
  1. Czy jakość powietrza w Polsce poprawia się na przestrzeni lat?
  2. Które miasto jest najbardziej zanieczyszczone?
  3. Jak silna jest sezonowość smogu?
  4. Czy Śląsk przekracza normy WHO/EU i o ile?
  5. Kiedy Polska może osiągnąć normę WHO przy obecnym tempie poprawy?
"""

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import matplotlib.ticker as mticker
import seaborn as sns
from scipy import stats
from scipy.stats import linregress
from pathlib import Path
import warnings
warnings.filterwarnings("ignore")

# ============================================================
# KONFIGURACJA
# ============================================================

DATA_DIR = Path("./data")

# Pliki PM2.5 — uwaga na różne nazwy dla różnych lat
def get_file_path(year: int) -> Path:
    """Zwraca ścieżkę do pliku dla danego roku — obsługuje różne konwencje nazewnictwa."""
    candidates = [
        DATA_DIR / f"{year}_PM25_1g.xlsx",    # 2015-2024
        DATA_DIR / f"{year}_PM2_5_1g.xlsx",   # 2016
        DATA_DIR / f"{year}_PM2.5_1g.xlsx",   # ewentualnie
    ]
    for p in candidates:
        if p.exists():
            return p
    return candidates[0]  # fallback (nie istnieje, zostanie pominięty)

FILES = [get_file_path(year) for year in range(2015, 2025)]

STATIONS_BY_YEAR = {
    # Mapowanie: rok -> {kod_stacji: miasto}
    # Potrzebne bo niektore stacje zmienily kody na przestrzeni lat
}

# Stacje dostepne we WSZYSTKICH latach 2015-2024
# Stacje wybrane tak żeby działały we WSZYSTKICH latach 2015-2024
# Gliwice pominięte - stacja SlGliwicMewy zniknęła po 2017
# Wrocław zastępuje Gliwice jako reprezentant południa/Dolnego Śląska
# Gdańsk i Poznań mają po dwa kody (stacja zmeniła kod w trakcie lat)
STATIONS = {
    "DsWrocAlWisn":  "Wrocław",   # Dolnośląskie - 2015-2024 ✅
    "SlKatoKossut":  "Katowice",  # Śląskie       - 2015-2024 ✅
    "MpKrakAlKras":  "Kraków",    # Małopolskie   - 2017-2021, 2023-2024
    "MpKrakBulwar":  "Kraków",    # Małopolskie   - backup (2022 brak AlKras)
    "MzWarAlNiepo":  "Warszawa",  # Mazowieckie   - 2015-2024 ✅
    "WpPoznPolank":  "Poznań",    # Wielkopolskie - 2017
    "WpPoznDabrow":  "Poznań",    # Wielkopolskie - 2018-2024
    "PmGdaLeczk08":  "Gdańsk",   # Pomorskie     - 2017-2020
    "PmGdaLeczkow":  "Gdańsk",   # Pomorskie     - 2021-2024
}

# Normy PM2.5 [µg/m³]
NORMA_WHO      = 15.0   # WHO 2021
NORMA_EU       = 25.0   # EU obowiązująca
NORMA_EU_2030  = 10.0   # EU cel na 2030

CITY_COLORS = {
    "Wrocław":  "#e63946",
    "Katowice": "#f4a261",
    "Kraków":   "#2a9d8f",
    "Warszawa": "#457b9d",
    "Poznań":   "#6a4c93",
    "Gdańsk":   "#52b788",
}

# Kluczowe wydarzenia legislacyjne do zaznaczenia na wykresach
EVENTS = [
    ("2017-07-01", "Uchwala Malopolska",       "blue"),
    ("2018-09-19", "Start Czystego Powietrza", "green"),   # dokładny start naboru wniosków
    ("2019-09-01", "Krakow: zakaz wegla",      "red"),
    ("2020-03-20", "Lockdown COVID-19",        "purple"),
    ("2022-02-24", "Kryzys energetyczny",      "orange"),
    ("2024-05-01", "Zakaz kopciuchow",         "darkred"), # przesunięte z 01-01 na 05-01
]

plt.rcParams.update({
    "figure.dpi": 130,
    "font.family": "DejaVu Sans",
    "axes.spines.top": False,
    "axes.spines.right": False,
    "axes.grid": True,
    "grid.alpha": 0.3,
    "grid.linestyle": "--",
})


# ============================================================
# 1. ŁADOWANIE DANYCH
# ============================================================

def load_single_file(path: Path) -> pd.DataFrame:
    """
    Wczytuje jeden plik XLSX z GIOŚ.
    Obsługuje dwa formaty:
    - Format nowy (2016+): kody stacji w wierszu 1, dane od wiersza 6
    - Format stary (2015):  kody stacji w wierszu 0, dane od wiersza 3
    """
    raw = pd.read_excel(path, header=None, dtype=str)

    # Wykryj format na podstawie zawartości wiersza 0
    row0_val = str(raw.iloc[0, 0]).strip()
    if row0_val == "Kod stacji":
        # Format stary (2015): kody w wierszu 0, dane od wiersza 3
        station_codes = raw.iloc[0, 1:].tolist()
        data = raw.iloc[3:].copy()
    else:
        # Format nowy (2016+): kody w wierszu 1, dane od wiersza 6
        station_codes = raw.iloc[1, 1:].tolist()
        data = raw.iloc[6:].copy()

    data.columns = ["datetime"] + station_codes
    data = data.reset_index(drop=True)
    data["datetime"] = pd.to_datetime(data["datetime"], errors="coerce")
    for col in station_codes:
        data[col] = pd.to_numeric(
            data[col].astype(str).str.replace(",", ".", regex=False).str.strip(),
            errors="coerce"
        )
    return data


def load_all_data(files: list) -> pd.DataFrame:
    """Wczytuje wszystkie pliki roczne i łączy je w jeden DataFrame."""
    frames = []
    for f in files:
        if not f.exists():
            print(f"  ⚠️  Brak pliku: {f.name} — pomijam")
            continue
        print(f"  📂 Wczytuję: {f.name}")
        df = load_single_file(f)
        cols = ["datetime"] + [c for c in STATIONS if c in df.columns]
        frames.append(df[cols])

    combined = pd.concat(frames, ignore_index=True)
    combined = combined.rename(columns=STATIONS)
    combined = combined.set_index("datetime").sort_index()
    combined = combined[~combined.index.duplicated(keep="first")]

    # Scal kolumny z tym samym miastem (Gdańsk i Poznań mają po 2 kody stacji)
    unique_cities = list(dict.fromkeys(combined.columns))
    result = {}
    for city in unique_cities:
        city_cols = combined.loc[:, combined.columns == city]
        if city_cols.shape[1] > 1:
            merged = city_cols.iloc[:, 0].copy()
            for i in range(1, city_cols.shape[1]):
                merged = merged.combine_first(city_cols.iloc[:, i])
            result[city] = merged
        else:
            result[city] = city_cols.iloc[:, 0]
    combined = pd.DataFrame(result)

    # Ogranicz dane do końca 2024 (2025 to niekompletny rok)
    combined = combined[combined.index.year <= 2024]

    return combined


# ============================================================
# 2. PRE-PROCESSING
# ============================================================

def preprocess(df: pd.DataFrame) -> pd.DataFrame:
    """
    Czyści dane:
    - wartości ujemne → NaN (błędy czujników)
    - wartości > 500 µg/m³ → NaN (awarie przyrządów)
    - interpolacja liniowa max 3h z rzędu (krótkie przerwy w pomiarach)
    """
    print("\n📊 Statystyki PRZED czyszczeniem:")
    print(f"  Rekordów: {len(df):,}")
    df = df.copy()
    missing = df.isna().sum()
    pct = (missing / len(df) * 100).round(1)
    for city in df.columns:
        n = int(missing[city]) if not isinstance(missing[city], pd.Series) else int(missing[city].iloc[0])
        p = float(pct[city]) if not isinstance(pct[city], pd.Series) else float(pct[city].iloc[0])
        print(f"  {city:12s}: {n:5d} brakujących ({p:.1f}%)")

    df = df.copy()
    df[df < 0] = np.nan
    df[df > 500] = np.nan
    df = df.interpolate(method="time", limit=3)

    print("\n✅ Statystyki PO czyszczeniu:")
    missing2 = df.isna().sum()
    for city in df.columns:
        n2 = int(missing2[city]) if not isinstance(missing2[city], pd.Series) else int(missing2[city].iloc[0])
        print(f"  {city:12s}: {n2:5d} brakujących")

    return df


def aggregate_daily(df: pd.DataFrame) -> pd.DataFrame:
    return df.resample("D").mean()

def aggregate_monthly(df: pd.DataFrame) -> pd.DataFrame:
    return df.resample("ME").mean()

def aggregate_yearly(df: pd.DataFrame) -> pd.DataFrame:
    agg = df.resample("YE").mean()
    agg.index = agg.index.year
    return agg


# ============================================================
# 3. ANALIZA WIZUALNA
# ============================================================

def plot_01_trend_miesięczny(monthly: pd.DataFrame):
    """
    Wykres 1: Trend miesięczny PM2.5 dla wszystkich miast.
    Odpowiada na pytanie: Czy jakość powietrza się poprawia?
    """
    fig, ax = plt.subplots(figsize=(14, 6))

    for city in CITY_COLORS:
        if city not in monthly.columns:
            continue
        ax.plot(monthly.index, monthly[city],
                label=city, color=CITY_COLORS[city], linewidth=2, alpha=0.85)

    ax.axhline(NORMA_WHO,     color="red",    linestyle="--", linewidth=1.5,
               label=f"Norma WHO ({NORMA_WHO} µg/m³)")
    ax.axhline(NORMA_EU,      color="orange", linestyle="--", linewidth=1.5,
               label=f"Norma EU ({NORMA_EU} µg/m³)")
    ax.axhline(NORMA_EU_2030, color="green",  linestyle=":",  linewidth=1.2,
               label=f"Cel EU 2030 ({NORMA_EU_2030} µg/m³)")

    ax.set_title("Miesięczne stężenie PM2.5 w polskich miastach",
                 fontsize=14, fontweight="bold", pad=15)
    ax.set_ylabel("PM2.5 [µg/m³]")
    ax.legend(loc="upper right", fontsize=9)
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
    ax.xaxis.set_major_locator(mdates.YearLocator())
    # Pionowe linie wydarzeń
    ymax = monthly.max().max()
    for date_str, label, color in EVENTS:
        dt = pd.to_datetime(date_str)
        ax.axvline(dt, color=color, linewidth=1.2, linestyle=":", alpha=0.7)
        ax.text(dt, ymax * 0.75, label, rotation=90,
                fontsize=6.5, color=color, va="top", ha="right", alpha=0.85)

    plt.xticks(rotation=45)
    plt.tight_layout()
    plt.savefig("wykresy/01_trend_miesięczny.png", dpi=150, bbox_inches="tight")
    plt.show()
    print("✅ Zapisano: 01_trend_miesięczny.png")


def plot_02_srednia_roczna_trend(yearly: pd.DataFrame):
    """
    Wykres 2: Średnia roczna PM2.5 + linia trendu liniowego.
    Odpowiada na pytanie: O ile µg/m³ rocznie spada zanieczyszczenie?
    """
    fig, ax = plt.subplots(figsize=(13, 6))
    x = np.arange(len(yearly.index))

    for city in CITY_COLORS:
        if city not in yearly.columns:
            continue
        vals = yearly[city].values
        mask = ~np.isnan(vals)
        ax.plot(yearly.index[mask], vals[mask], "o-",
                color=CITY_COLORS[city], linewidth=2,
                markersize=6, label=city)

        # Linia trendu
        if mask.sum() >= 3:
            slope, intercept, r, p, _ = linregress(x[mask], vals[mask])
            trend_line = intercept + slope * x
            ax.plot(yearly.index, trend_line,
                    color=CITY_COLORS[city], linewidth=1,
                    linestyle="--", alpha=0.5)

    ax.axhline(NORMA_WHO,     color="red",    linestyle="--", linewidth=1.5,
               label=f"Norma WHO {NORMA_WHO} µg/m³")
    ax.axhline(NORMA_EU_2030, color="green",  linestyle=":",  linewidth=1.2,
               label=f"Cel EU 2030 {NORMA_EU_2030} µg/m³")

    ax.set_title("Średnioroczne PM2.5 z trendem liniowym",
                 fontsize=14, fontweight="bold")
    ax.set_ylabel("PM2.5 [µg/m³]")
    ax.set_xlabel("Rok")

    # Pionowe linie wydarzeń (tylko najważniejsze - nie zaśmiecamy)
    key_events = [e for e in EVENTS if e[0] in [
        "2018-09-01", "2019-09-01", "2024-01-01"
    ]]
    ymax = yearly.max().max()
    for date_str, label, color in key_events:
        yr = pd.to_datetime(date_str).year + pd.to_datetime(date_str).month / 12
        ax.axvline(yr, color=color, linewidth=1.5, linestyle=":", alpha=0.8)
        ax.text(yr + 0.05, ymax * 0.7,
                label.replace("\n", " "), rotation=90,
                fontsize=7, color=color, va="top", alpha=0.9)

    ax.legend(fontsize=9)
    plt.tight_layout()
    plt.savefig("wykresy/02_trend_roczny_z_linia.png", dpi=150, bbox_inches="tight")
    plt.show()
    print("✅ Zapisano: 02_trend_roczny_z_linia.png")


def plot_03_sezonowosc(daily: pd.DataFrame):
    """
    Wykres 3: Sezonowość — średnie PM2.5 dla każdego miesiąca.
    Odpowiada na pytanie: Kiedy jest najgorzej i jak bardzo?
    """
    fig, ax = plt.subplots(figsize=(13, 6))

    months = range(1, 13)
    month_labels = ["Sty", "Lut", "Mar", "Kwi", "Maj", "Cze",
                    "Lip", "Sie", "Wrz", "Paź", "Lis", "Gru"]

    for city in CITY_COLORS:
        if city not in daily.columns:
            continue
        monthly_means = [daily[city][daily.index.month == m].mean() for m in months]
        ax.plot(month_labels, monthly_means,
                "o-", color=CITY_COLORS[city],
                linewidth=2.5, markersize=7, label=city)

    ax.axhline(NORMA_WHO, color="red", linestyle="--",
               linewidth=1.5, label=f"Norma WHO {NORMA_WHO} µg/m³")
    ax.fill_between(month_labels,
                    [NORMA_WHO] * 12, [0] * 12,
                    alpha=0.05, color="green", label="Strefa bezpieczna")

    ax.set_title("Sezonowość PM2.5 — średnia dla każdego miesiąca (wszystkie lata)",
                 fontsize=14, fontweight="bold")
    ax.set_ylabel("PM2.5 [µg/m³]")
    ax.legend(fontsize=9)
    plt.tight_layout()
    plt.savefig("wykresy/03_sezonowosc_linie.png", dpi=150, bbox_inches="tight")
    plt.show()
    print("✅ Zapisano: 03_sezonowosc_linie.png")


def plot_04_heatmapa_gliwice(daily: pd.DataFrame, city: str = "Gliwice"):
    """
    Wykres 4: Heatmapa rok x miesiąc dla Gliwic.
    Pokazuje jednocześnie trend wieloletni i sezonowość.
    """
    if city not in daily.columns:
        return

    data = daily[[city]].copy()
    data["year"]  = data.index.year
    data["month"] = data.index.month
    pivot = data.pivot_table(values=city, index="year",
                             columns="month", aggfunc="mean")
    pivot.columns = ["Sty", "Lut", "Mar", "Kwi", "Maj", "Cze",
                     "Lip", "Sie", "Wrz", "Paź", "Lis", "Gru"]

    fig, ax = plt.subplots(figsize=(13, 5))
    sns.heatmap(pivot, cmap="YlOrRd", annot=True, fmt=".0f",
                linewidths=0.5, ax=ax,
                cbar_kws={"label": "PM2.5 [µg/m³]"})
    ax.set_title(f"Heatmapa PM2.5 — {city} | czerwień = smog, zieleń = czyste",
                 fontsize=14, fontweight="bold")
    ax.set_xlabel("")
    ax.set_ylabel("Rok")
    plt.tight_layout()
    plt.savefig(f"wykresy/04_heatmapa_{city.lower()}.png", dpi=150, bbox_inches="tight")
    plt.show()
    print(f"✅ Zapisano: 04_heatmapa_{city.lower()}.png")


def plot_05_przekroczenia_norm(daily: pd.DataFrame):
    """
    Wykres 5: % dni z przekroczeniem normy WHO dla każdego miasta i roku.
    Najbardziej czytelny wykres — odpowiada wprost na pytanie o zdrowie.
    """
    years = sorted(daily.index.year.unique())
    cities = [c for c in CITY_COLORS if c in daily.columns]

    fig, ax = plt.subplots(figsize=(13, 6))
    x = np.arange(len(years))
    width = 0.13

    for i, city in enumerate(cities):
        pct_per_year = []
        for year in years:
            year_data = daily[city][daily.index.year == year].dropna()
            if len(year_data) > 0:
                pct = (year_data > NORMA_WHO).mean() * 100
            else:
                pct = np.nan
            pct_per_year.append(pct)

        offset = (i - len(cities) / 2) * width + width / 2
        ax.bar(x + offset, pct_per_year, width,
               label=city, color=CITY_COLORS[city], alpha=0.88)

    ax.axhline(50, color="red", linestyle="--", linewidth=1,
               label="50% dni (co drugi dzień przekroczenie)")
    ax.set_xticks(x)
    ax.set_xticklabels(years)
    ax.set_title("% dni w roku z przekroczeniem normy WHO (PM2.5 > 15 µg/m³)",
                 fontsize=14, fontweight="bold")
    ax.set_ylabel("% dni z przekroczeniem")
    ax.yaxis.set_major_formatter(mticker.PercentFormatter())
    ax.legend(fontsize=9)
    plt.tight_layout()
    plt.savefig("wykresy/05_przekroczenia_who.png", dpi=150, bbox_inches="tight")
    plt.show()
    print("✅ Zapisano: 05_przekroczenia_who.png")


def plot_06_ranking_miast(yearly: pd.DataFrame):
    """
    Wykres 6: Ranking miast — średnia wieloletnia z zaznaczeniem norm.
    Prosty i czytelny — idealny do prezentacji.
    """
    means = yearly.mean().sort_values(ascending=True)
    cities = means.index.tolist()
    values = means.values

    fig, ax = plt.subplots(figsize=(10, 5))
    colors = [CITY_COLORS.get(c, "steelblue") for c in cities]
    bars = ax.barh(cities, values, color=colors, alpha=0.88, edgecolor="white")

    # Etykiety wartości
    for bar, val in zip(bars, values):
        ax.text(val + 0.3, bar.get_y() + bar.get_height() / 2,
                f"{val:.1f} µg/m³", va="center", fontsize=10)

    ax.axvline(NORMA_WHO,     color="red",    linestyle="--",
               linewidth=2, label=f"WHO: {NORMA_WHO}")
    ax.axvline(NORMA_EU,      color="orange", linestyle="--",
               linewidth=2, label=f"EU: {NORMA_EU}")
    ax.axvline(NORMA_EU_2030, color="green",  linestyle=":",
               linewidth=1.5, label=f"Cel EU 2030: {NORMA_EU_2030}")

    ax.set_title("Ranking miast — średnie PM2.5 (wszystkie lata)",
                 fontsize=14, fontweight="bold")
    ax.set_xlabel("PM2.5 [µg/m³]")
    ax.legend(fontsize=9)
    plt.tight_layout()
    plt.savefig("wykresy/06_ranking_miast.png", dpi=150, bbox_inches="tight")
    plt.show()
    print("✅ Zapisano: 06_ranking_miast.png")


def plot_07_rozklady(daily: pd.DataFrame):
    """
    Wykres 7: Rozkład dobowych stężeń — histogram + linia gęstości.
    Pokazuje jak bardzo skośne są dane i gdzie leży większość pomiarów.
    """
    fig, axes = plt.subplots(2, 3, figsize=(16, 9))
    cities = [c for c in CITY_COLORS if c in daily.columns]

    for ax, city in zip(axes.flat, cities):
        data = daily[city].dropna()
        ax.hist(data, bins=60, color=CITY_COLORS[city],
                alpha=0.6, edgecolor="white", density=True)

        # KDE (wygładzona krzywa gęstości)
        from scipy.stats import gaussian_kde
        kde = gaussian_kde(data.dropna())
        x_range = np.linspace(0, data.quantile(0.99), 200)
        ax.plot(x_range, kde(x_range), color=CITY_COLORS[city],
                linewidth=2.5)

        ax.axvline(data.mean(),   color="black",  linewidth=2,
                   label=f"Średnia: {data.mean():.1f}")
        ax.axvline(data.median(), color="gray",   linewidth=1.5,
                   linestyle="--", label=f"Mediana: {data.median():.1f}")
        ax.axvline(NORMA_WHO,     color="red",    linewidth=1.5,
                   linestyle=":",  label=f"WHO: {NORMA_WHO}")

        ax.set_title(city, fontweight="bold")
        ax.set_xlabel("PM2.5 [µg/m³]")
        ax.set_ylabel("Gęstość")
        ax.set_xlim(left=0)
        ax.legend(fontsize=8)

    fig.suptitle("Rozkład dobowych stężeń PM2.5 (wszystkie lata)",
                 fontsize=14, fontweight="bold")
    plt.tight_layout()
    plt.savefig("wykresy/07_rozklady.png", dpi=150, bbox_inches="tight")
    plt.show()
    print("✅ Zapisano: 07_rozklady.png")


def plot_08_korelacja(daily: pd.DataFrame):
    """
    Wykres 8: Macierz korelacji Spearmana między miastami.
    Pokazuje że smog w Polsce ma charakter ogólnopolski (pogodowy),
    a nie tylko lokalny.
    """
    corr = daily.corr(method="spearman")
    mask = np.triu(np.ones_like(corr, dtype=bool))

    fig, ax = plt.subplots(figsize=(9, 7))
    sns.heatmap(corr, mask=mask, annot=True, fmt=".2f",
                cmap="coolwarm", center=0, ax=ax,
                vmin=0, vmax=1, linewidths=0.5,
                cbar_kws={"label": "Współczynnik Spearmana"})
    ax.set_title("Korelacja PM2.5 między miastami\n"
                 "(wysoka = smog pojawia się wszędzie jednocześnie)",
                 fontsize=13, fontweight="bold")
    plt.tight_layout()
    plt.savefig("wykresy/08_korelacja.png", dpi=150, bbox_inches="tight")
    plt.show()
    print("✅ Zapisano: 08_korelacja.png")


def plot_09_dekompozycja(daily: pd.DataFrame, city: str = "Gliwice"):
    """
    Wykres 9: Dekompozycja szeregu czasowego.
    Rozdziela dane na: trend długoterminowy + sezonowość + szum losowy.
    """
    if city not in daily.columns:
        return

    data = daily[city].dropna()
    trend = data.rolling(window=365, center=True, min_periods=30).mean()
    residual = data - trend

    fig, axes = plt.subplots(3, 1, figsize=(14, 10), sharex=True)

    axes[0].plot(data.index, data, color=CITY_COLORS.get(city, "steelblue"),
                 linewidth=0.5, alpha=0.6, label="Dane surowe")
    axes[0].plot(trend.index, trend, color="darkred",
                 linewidth=2.5, label="Trend (365-dniowa średnia krocząca)")
    axes[0].axhline(NORMA_WHO, color="red", linestyle="--",
                    linewidth=1, label=f"Norma WHO {NORMA_WHO} µg/m³")
    axes[0].set_ylabel("PM2.5 [µg/m³]")
    axes[0].set_title(f"Dekompozycja szeregu czasowego PM2.5 — {city}",
                      fontsize=13, fontweight="bold")
    axes[0].legend(fontsize=9)

    axes[1].plot(trend.index, trend, color="darkred", linewidth=2)
    axes[1].set_ylabel("Trend [µg/m³]")
    axes[1].set_title("Trend długoterminowy — widać poprawę jakości powietrza")

    axes[2].fill_between(residual.index, residual, 0,
                         where=(residual > 0), color="red",
                         alpha=0.4, label="Powyżej trendu (gorzej)")
    axes[2].fill_between(residual.index, residual, 0,
                         where=(residual < 0), color="green",
                         alpha=0.4, label="Poniżej trendu (lepiej)")
    axes[2].axhline(0, color="black", linewidth=1)
    axes[2].set_ylabel("Odchylenie [µg/m³]")
    axes[2].set_title("Sezonowość i wahania losowe")
    axes[2].legend(fontsize=9)

    plt.tight_layout()
    plt.savefig(f"wykresy/09_dekompozycja_{city.lower()}.png", dpi=150,
                bbox_inches="tight")
    plt.show()
    print(f"✅ Zapisano: 09_dekompozycja_{city.lower()}.png")


# ============================================================
# 4. ANALIZA STATYSTYCZNA
# ============================================================

def basic_statistics(daily: pd.DataFrame) -> pd.DataFrame:
    """Statystyki opisowe dla każdego miasta."""
    stats_df = daily.describe().T
    stats_df["median"]   = daily.median()
    stats_df["skewness"] = daily.skew()
    stats_df = stats_df[["count", "mean", "median", "std", "min", "max", "skewness"]]
    stats_df.columns = ["Dni", "Średnia", "Mediana", "Odch.std",
                        "Min", "Max", "Skośność"]
    print("\n📈 STATYSTYKI OPISOWE [µg/m³]:")
    print(stats_df.round(2).to_string())
    return stats_df


def exceedance_analysis(daily: pd.DataFrame) -> pd.DataFrame:
    """Ile dni w roku przekraczamy normy WHO i EU."""
    results = []
    for city in daily.columns:
        d = daily[city].dropna()
        results.append({
            "Miasto":           city,
            "Dni danych":       len(d),
            "Przekr. WHO (dni)": int((d > NORMA_WHO).sum()),
            "Przekr. WHO (%)":  round((d > NORMA_WHO).mean() * 100, 1),
            "Przekr. EU (dni)": int((d > NORMA_EU).sum()),
            "Przekr. EU (%)":   round((d > NORMA_EU).mean() * 100, 1),
        })
    df = pd.DataFrame(results).set_index("Miasto")
    print("\n🚨 ANALIZA PRZEKROCZEŃ NORM:")
    print(df.to_string())
    return df


def trend_analysis(yearly: pd.DataFrame):
    """
    Analiza trendu liniowego dla każdego miasta.
    Oblicza tempo poprawy [µg/m³/rok] i szacuje kiedy osiągniemy normę WHO.
    """
    print("\n📉 ANALIZA TRENDU (regresja liniowa):")
    print(f"  {'Miasto':12s} {'Zmiana/rok':>12s} {'R²':>8s} {'p-value':>10s} "
          f"{'Kiedy WHO?':>12s}")
    print("  " + "-" * 60)

    years = yearly.index.values.astype(float)
    current_year = int(years.max())

    for city in yearly.columns:
        vals = yearly[city].values
        mask = ~np.isnan(vals)
        if mask.sum() < 3:
            continue
        slope, intercept, r, p, _ = linregress(years[mask], vals[mask])
        r2 = r ** 2

        # Kiedy osiągniemy normę WHO przy obecnym tempie?
        if slope < 0:
            years_to_who = (NORMA_WHO - intercept) / slope
            year_who = int(years_to_who)
            when = str(year_who) if year_who > current_year else "już osiągnięta"
        else:
            when = "trend wzrostowy!"

        print(f"  {city:12s} {slope:>+10.2f}  {r2:>8.3f} {p:>10.4f} {when:>12s}")


def normality_test(daily: pd.DataFrame):
    """Test Shapiro-Wilka — czy rozkład jest normalny?"""
    print("\n🔬 TEST NORMALNOŚCI (Shapiro-Wilk, próbka 500 dni):")
    for city in daily.columns:
        sample = daily[city].dropna().sample(
            min(500, len(daily[city].dropna())), random_state=42)
        stat, p = stats.shapiro(sample)
        result = "✅ normalny" if p > 0.05 else "❌ nie-normalny (prawostronnie skośny)"
        print(f"  {city:12s}: p={p:.4f} → {result}")


def kruskal_wallis_test(daily: pd.DataFrame):
    """Test Kruskala-Wallisa — czy różnice między miastami są istotne?"""
    print("\n📊 TEST KRUSKALA-WALLISA:")
    groups = [daily[c].dropna().values for c in daily.columns]
    stat, p = stats.kruskal(*groups)
    print(f"  H={stat:.2f}, p={p:.6f}")
    if p < 0.05:
        print("  ✅ Różnice między miastami są ISTOTNE statystycznie (p < 0.05)")
        print("  → Gliwice/Kraków to nie przypadek — Śląsk i Małopolska")
        print("    mają strukturalnie gorsze powietrze niż Gdańsk/Poznań")
    else:
        print("  ❌ Brak istotnych różnic")


# ============================================================
# 5. PREDYKCJA (Prophet)
# ============================================================

def predict_prophet_all_cities(daily: pd.DataFrame, target_year: int = 2030):
    """
    Predykcja PM2.5 dla wszystkich miast do wybranego roku.
    Prophet dla każdego miasta osobno, wyniki na jednym wykresie.
    Zaznacza kiedy każde miasto osiągnie normę WHO.
    """
    try:
        from prophet import Prophet
    except ImportError:
        print("⚠️  Prophet nie zainstalowany.")
        return

    last_date   = daily.index.max()
    target_date = pd.Timestamp(f"{target_year}-12-31")
    periods     = (target_date - last_date).days
    if periods <= 0:
        print(f"⚠️  target_year={target_year} jest w przeszłości")
        return

    fig, ax = plt.subplots(figsize=(15, 7))
    print(f"\n🔮 Predykcja Prophet dla wszystkich miast do {target_year}:")

    for city in CITY_COLORS:
        if city not in daily.columns:
            continue

        df_p = daily[[city]].dropna().reset_index()
        df_p.columns = ["ds", "y"]
        if len(df_p) < 365:
            print(f"  ⚠️  {city}: za mało danych")
            continue

        print(f"  🔮 Trenuję: {city} ({len(df_p)} dni)...")
        model = Prophet(
            yearly_seasonality=True,
            weekly_seasonality=False,
            daily_seasonality=False,
            changepoint_prior_scale=0.05,
        )
        model.fit(df_p)

        future   = model.make_future_dataframe(periods=periods)
        forecast = model.predict(future)
        forecast["yhat"]       = forecast["yhat"].clip(lower=0)
        forecast["yhat_lower"] = forecast["yhat_lower"].clip(lower=0)
        forecast["yhat_upper"] = forecast["yhat_upper"].clip(lower=0)

        color       = CITY_COLORS[city]
        pred_future = forecast[forecast["ds"] > df_p["ds"].max()]

        # Dane historyczne - cienka przezroczysta linia
        ax.plot(df_p["ds"], df_p["y"],
                color=color, linewidth=0.6, alpha=0.2)

        # Predykcja - gruba linia
        ax.plot(pred_future["ds"], pred_future["yhat"],
                color=color, linewidth=2.2, label=city)

        # Przedział ufności
        ax.fill_between(pred_future["ds"],
                        pred_future["yhat_lower"],
                        pred_future["yhat_upper"],
                        alpha=0.07, color=color)

        # Punkt przecięcia z normą WHO - używamy ROCZNEJ średniej kroczącej
        # żeby uniknąć fałszywych wyników (wiosna zawsze <15 µg/m³)
        pred_future_copy = pred_future.copy()
        pred_future_copy = pred_future_copy.set_index("ds")
        # Roczna średnia krocząca predykcji
        rolling_annual = pred_future_copy["yhat"].rolling(window=365, min_periods=180).mean()
        crossing_annual = rolling_annual[rolling_annual <= NORMA_WHO]

        if not crossing_annual.empty:
            cross_date = crossing_annual.index[0]
            cross_val  = float(crossing_annual.iloc[0])
            ax.plot(cross_date, cross_val, "o",
                    color=color, markersize=9, zorder=5)
            ax.annotate(f"{city}\n{cross_date.strftime('%Y')}",
                        xy=(cross_date, cross_val),
                        xytext=(cross_date, cross_val + 2.5),
                        fontsize=8, color=color, fontweight="bold",
                        ha="center")
            print(f"     → {city} średnioroczna osiągnie WHO: {cross_date.strftime('%Y-%m')}")
        else:
            # Pokaż gdzie będzie w ostatnim roku
            last_annual = rolling_annual.dropna()
            if not last_annual.empty:
                print(f"     → {city}: nie osiągnie WHO do {target_year} "
                      f"(predykcja {target_year}: {last_annual.iloc[-1]:.1f} µg/m³)")
            else:
                print(f"     → {city}: nie osiągnie WHO do {target_year}")

    ax.axhline(NORMA_WHO, color="red", linestyle="--",
               linewidth=2, label=f"Norma WHO {NORMA_WHO} µg/m³", zorder=4)
    ax.axhline(NORMA_EU_2030, color="green", linestyle=":",
               linewidth=1.5, label=f"Cel EU 2030: {NORMA_EU_2030} µg/m³", zorder=4)
    ax.axvline(last_date, color="gray", linestyle=":",
               linewidth=1.5, label="Koniec danych")

    ax.set_title(f"Predykcja PM2.5 dla polskich miast do {target_year} (Prophet/Meta)",
                 fontsize=14, fontweight="bold")
    ax.set_ylabel("PM2.5 [µg/m³]")
    ax.set_ylim(bottom=0)
    ax.legend(fontsize=9, loc="upper right")
    plt.tight_layout()
    plt.savefig(f"wykresy/10_predykcja_wszystkie_{target_year}.png",
                dpi=150, bbox_inches="tight")
    plt.show()
    print(f"✅ Zapisano: 10_predykcja_wszystkie_{target_year}.png")

    # ── Tabela kwartalna dla wszystkich miast ──────────────────────────────
    print(f"\n📋 PREDYKCJA KWARTALNA — średnie PM2.5 [µg/m³]")
    print(f"   Porównanie rok do roku vs 2025 (rok bazowy)")
    print()

    # Zbierz forecasts ponownie (szybko, bez wykresu)
    all_forecasts = {}
    for city in CITY_COLORS:
        if city not in daily.columns:
            continue
        df_p2 = daily[[city]].dropna().reset_index()
        df_p2.columns = ["ds", "y"]
        if len(df_p2) < 365:
            continue
        m2 = Prophet(
            yearly_seasonality=True,
            weekly_seasonality=False,
            daily_seasonality=False,
            changepoint_prior_scale=0.05,
        )
        m2.fit(df_p2)
        fut2     = m2.make_future_dataframe(periods=periods)
        fcast2   = m2.predict(fut2)
        fcast2["yhat"] = fcast2["yhat"].clip(lower=0)
        # Tylko przyszłe daty
        future_only = fcast2[fcast2["ds"] > df_p2["ds"].max()].copy()
        future_only = future_only.set_index("ds")["yhat"]
        all_forecasts[city] = future_only

    if not all_forecasts:
        return

    # Kwartały do sprawdzenia
    quarters = []
    for yr in range(2025, target_year + 1):
        for q, (m_start, m_end, label) in enumerate([
            (1, 3, "Q1"), (4, 6, "Q2"), (7, 9, "Q3"), (10, 12, "Q4")
        ], 1):
            quarters.append((yr, q, label, m_start, m_end))

    # Policz średnie kwartalne dla każdego miasta
    city_quarterly = {}
    for city, fc in all_forecasts.items():
        city_quarterly[city] = {}
        for yr, q, label, ms, me in quarters:
            mask = (fc.index.year == yr) & (fc.index.month >= ms) & (fc.index.month <= me)
            vals = fc[mask]
            city_quarterly[city][(yr, q)] = vals.mean() if len(vals) > 0 else np.nan

    # Nagłówek tabeli
    cities_list = list(all_forecasts.keys())
    header = f"  {'Rok':>4} {'Q':>2} | " + " | ".join(f"{c:>10}" for c in cities_list)
    print(header)
    print("  " + "-" * len(header))

    # Baseline: średnia z 2025
    baseline = {}
    for city in cities_list:
        vals_2025 = [city_quarterly[city].get((2025, q), np.nan) for q in range(1, 5)]
        vals_2025 = [v for v in vals_2025 if not np.isnan(v)]
        baseline[city] = np.mean(vals_2025) if vals_2025 else np.nan

    prev_year_vals = {city: {} for city in cities_list}

    for yr, q, label, ms, me in quarters:
        row_vals = []
        row_diff_yoy = []
        row_diff_base = []

        for city in cities_list:
            val = city_quarterly[city].get((yr, q), np.nan)
            row_vals.append(val)

            # Różnica rok do roku
            prev = city_quarterly[city].get((yr - 1, q), np.nan)
            yoy  = val - prev if not np.isnan(val) and not np.isnan(prev) else np.nan
            row_diff_yoy.append(yoy)

            # Różnica vs 2025 baseline
            base_q = city_quarterly[city].get((2025, q), np.nan)
            vs_base = val - base_q if not np.isnan(val) and not np.isnan(base_q) else np.nan
            row_diff_base.append(vs_base)

        # Drukuj wartość
        vals_str = " | ".join(
            f"{v:>10.1f}" if not np.isnan(v) else f"{'—':>10}" for v in row_vals
        )
        print(f"  {yr:>4} {label:>2} | {vals_str}")

        # Co rok drukuj różnicę r/r i vs 2025
        if q == 4:
            yoy_str = " | ".join(
                f"{v:>+10.1f}" if not np.isnan(v) else f"{'—':>10}" for v in row_diff_yoy
            )
            base_str = " | ".join(
                f"{v:>+10.1f}" if not np.isnan(v) else f"{'—':>10}" for v in row_diff_base
            )
            print(f"  {'Δr/r':>4} {'':>2} | {yoy_str}  ← zmiana vs rok wcześniej")
            print(f"  {'Δ25':>4} {'':>2} | {base_str}  ← zmiana vs 2025")
            print()

def plot_10_predykcja_kiedy_who(daily: pd.DataFrame, yearly: pd.DataFrame):
    """
    Wykres 10: Kiedy Polska osiągnie normę WHO?
    - Liczy średnią krajową ze wszystkich miast
    - Dopasowuje trend liniowy na danych rocznych
    - Ekstrapoluje do momentu przecięcia z normą WHO
    - Rysuje wykres z przedziałem ufności
    """
    # Średnia krajowa - średnia ze wszystkich miast dla każdego roku
    yearly_mean = yearly.mean(axis=1).dropna()
    years = yearly_mean.index.astype(float)

    # Regresja liniowa
    from scipy.stats import linregress
    slope, intercept, r, p, se = linregress(years, yearly_mean.values)

    print("\n🇵🇱 PREDYKCJA ŚREDNIEJ KRAJOWEJ:")
    print(f"   Trend: {slope:+.2f} µg/m³/rok (R²={r**2:.3f}, p={p:.4f})")

    if slope >= 0:
        print("   ⚠️  Trend nie jest spadkowy — predykcja niemożliwa")
        return

    # Kiedy średnia krajowa osiągnie normę WHO?
    year_who    = (NORMA_WHO    - intercept) / slope
    year_eu2030 = (NORMA_EU_2030 - intercept) / slope

    # Zamień ułamkowy rok na dokładną datę
    def year_float_to_date(yr):
        year_int = int(yr)
        month = int((yr - year_int) * 12) + 1
        return f"{year_int}-{month:02d}"

    print(f"   📅 Średnia krajowa osiągnie normę WHO ({NORMA_WHO} µg/m³): "
          f"~{year_who:.1f} ({year_float_to_date(year_who)})")
    print(f"   📅 Średnia krajowa osiągnie cel EU 2030 ({NORMA_EU_2030} µg/m³): "
          f"~{year_eu2030:.1f} ({year_float_to_date(year_eu2030)})")

    # Per miasto
    print("\n   Per miasto (przy obecnym tempie):")
    for city in yearly.columns:
        city_data = yearly[city].dropna()
        if len(city_data) < 3:
            continue
        city_years = city_data.index.astype(float)
        s, i, r2, pv, _ = linregress(city_years, city_data.values)
        last_val = city_data.iloc[-1]
        if s < 0:
            yr = (NORMA_WHO - i) / s
            if yr <= city_data.index.max():
                when = f"już osiągnięta (ostatnia: {last_val:.1f})"
            elif yr > 2050:
                when = "> 2050"
            else:
                year_int = int(yr)
                month = int((yr - year_int) * 12) + 1
                when = f"~{year_int}-{month:02d} (za ~{yr - city_data.index.max():.1f} lat)"
        else:
            when = f"trend wzrostowy (ostatnia: {last_val:.1f})"
        print(f"   {city:12s}: {last_val:.1f} µg/m³ → WHO: {when}")

    # Wykres
    fig, ax = plt.subplots(figsize=(13, 6))

    # Dane historyczne - każde miasto szaro
    for city in yearly.columns:
        city_data = yearly[city].dropna()
        ax.plot(city_data.index, city_data.values,
                color=CITY_COLORS.get(city, "gray"),
                linewidth=1.2, alpha=0.35, linestyle="--")

    # Średnia krajowa - gruba linia
    ax.plot(yearly_mean.index, yearly_mean.values,
            color="black", linewidth=3, marker="o",
            markersize=7, label="Średnia krajowa", zorder=5)

    # Ekstrapolacja trendu do 2040
    future_years = np.arange(yearly_mean.index.min(), 2041)
    trend_line   = intercept + slope * future_years

    # Tylko część przyszła
    hist_end = int(yearly_mean.index.max())
    future_mask = future_years > hist_end

    ax.plot(future_years[~future_mask], trend_line[~future_mask],
            color="black", linewidth=2, linestyle="-", alpha=0.4)
    ax.plot(future_years[future_mask], trend_line[future_mask],
            color="black", linewidth=2, linestyle="--",
            alpha=0.7, label=f"Trend liniowy (ekstrapolacja)")

    # Przedział ufności (±1 se * sqrt(n))
    n = len(years)
    years_arr = np.array(years, dtype=float)
    x_mean = years_arr.mean()
    se_pred = se * np.sqrt(1 + 1/n + (future_years - x_mean)**2 / ((years_arr - x_mean)**2).sum())
    ax.fill_between(future_years[future_mask],
                    trend_line[future_mask] - 1.96 * se_pred[future_mask],
                    trend_line[future_mask] + 1.96 * se_pred[future_mask],
                    alpha=0.15, color="black", label="Przedział ufności 95%")

    # Normy
    ax.axhline(NORMA_WHO, color="red", linestyle="--",
               linewidth=2, label=f"Norma WHO {NORMA_WHO} µg/m³")
    ax.axhline(NORMA_EU_2030, color="green", linestyle=":",
               linewidth=1.5, label=f"Cel EU 2030: {NORMA_EU_2030} µg/m³")

    # Punkt przecięcia z WHO
    if 2017 < year_who < 2050:
        ax.axvline(year_who, color="red", linestyle=":",
                   linewidth=1.5, alpha=0.7)
        ax.annotate(f"WHO ~{year_who:.0f}",
                    xy=(year_who, NORMA_WHO),
                    xytext=(year_who + 0.5, NORMA_WHO + 2),
                    fontsize=11, fontweight="bold", color="red",
                    arrowprops=dict(arrowstyle="->", color="red"))

    ax.set_xlim(2017, 2040)
    ax.set_ylim(bottom=0)
    ax.set_title("Kiedy Polska osiągnie normę WHO? — ekstrapolacja trendu 2015–2024",
                 fontsize=14, fontweight="bold")
    ax.set_ylabel("PM2.5 [µg/m³]")
    ax.set_xlabel("Rok")
    ax.legend(fontsize=9)
    plt.tight_layout()
    plt.savefig("wykresy/11_kiedy_who.png", dpi=150, bbox_inches="tight")
    plt.show()
    print("✅ Zapisano: 11_kiedy_who.png")


# ============================================================
# 6. WNIOSKI
# ============================================================

def generate_conclusions(daily: pd.DataFrame, yearly: pd.DataFrame):
    """Drukuje automatyczne wnioski gotowe do wklejenia do raportu."""
    print("\n" + "=" * 65)
    print("📋 WNIOSKI Z ANALIZY — gotowe do raportu")
    print("=" * 65)

    # Ranking miast
    means = daily.mean().sort_values(ascending=False)
    print(f"\n🏆 RANKING MIAST (średnia PM2.5 wszystkich lat):")
    for i, (city, val) in enumerate(means.items(), 1):
        norm = "❌ POWYŻEJ WHO" if val > NORMA_WHO else "✅ PONIŻEJ WHO"
        print(f"  {i}. {city:12s}: {val:.1f} µg/m³  {norm}")

    # Trend
    print(f"\n📉 ZMIANA PM2.5 "
          f"({yearly.index.min()} → {yearly.index.max()}):")
    for city in daily.columns:
        if city in yearly.columns:
            first = yearly[city].dropna().iloc[0]
            last  = yearly[city].dropna().iloc[-1]
            change = last - first
            pct    = change / first * 100
            arrow  = "📉" if change < 0 else "📈"
            print(f"  {city:12s}: {first:.1f} → {last:.1f} µg/m³  "
                  f"{arrow} {change:+.1f} ({pct:+.0f}%)")

    # Przekroczenia
    print(f"\n🚨 PRZEKROCZENIA NORMY WHO ({NORMA_WHO} µg/m³):")
    for city in daily.columns:
        pct = (daily[city] > NORMA_WHO).mean() * 100
        days = int((daily[city] > NORMA_WHO).sum())
        print(f"  {city:12s}: {pct:.0f}% dni ({days} dni łącznie)")

    print("\n" + "=" * 65)


# ============================================================
# MAIN
# ============================================================

if __name__ == "__main__":
    import os
    os.makedirs("wykresy", exist_ok=True)

    print("🌫️  ANALIZA PM2.5 W POLSCE")
    print("=" * 65)

    # 1. Ładowanie
    print("\n📂 KROK 1: Ładowanie danych...")
    df_raw = load_all_data(FILES)
    print(f"\n✅ Wczytano: {df_raw.shape[0]:,} rekordów")
    print(f"   Zakres: {df_raw.index.min().date()} → {df_raw.index.max().date()}")
    print(f"   Miasta: {list(df_raw.columns)}")

    # 2. Pre-processing
    print("\n🔧 KROK 2: Pre-processing...")
    df_clean = preprocess(df_raw)
    daily    = aggregate_daily(df_clean)
    monthly  = aggregate_monthly(df_clean)
    yearly   = aggregate_yearly(df_clean)

    # 3. Wykresy
    print("\n📊 KROK 3: Generowanie wykresów...")
    plot_01_trend_miesięczny(monthly)
    plot_02_srednia_roczna_trend(yearly)
    plot_03_sezonowosc(daily)
    plot_04_heatmapa_gliwice(daily, city="Kraków")
    plot_05_przekroczenia_norm(daily)
    plot_06_ranking_miast(yearly)
    plot_07_rozklady(daily)
    plot_08_korelacja(daily)
    plot_09_dekompozycja(daily, city="Kraków")

    # 4. Statystyki
    print("\n🔬 KROK 4: Analiza statystyczna...")
    stats_df = basic_statistics(daily)
    exc_df   = exceedance_analysis(daily)
    trend_analysis(yearly)
    normality_test(daily)
    kruskal_wallis_test(daily)

    # 5. Predykcja
    print("\n🔮 KROK 5: Predykcja...")
    predict_prophet_all_cities(daily, target_year=2030)

    # Predykcja kiedy WHO
    plot_10_predykcja_kiedy_who(daily, yearly)

    # 6. Wnioski
    generate_conclusions(daily, yearly)

    print("\n🎉 Gotowe! Wykresy w folderze ./wykresy/")