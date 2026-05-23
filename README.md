# 🌫️ Analiza jakości powietrza w Polsce (2015–2024)

> Projekt zaliczeniowy — Analiza i Wizualizacja Danych (Pandas DataFrame)  
> Wyższa Szkoła Bankowa w Chorzowie

---

## 👥 Skład sekcji

| Imię i nazwisko | Zakres prac |
|-----------------|-------------|
| Dominik Szczepanik | Ładowanie danych, pre-processing, analiza wizualna |
| Wojciech Wróbel | Analiza statystyczna, predykcja, wnioski |

---

## 📋 Opis problemu

Projekt analizuje jakość powietrza w 6 polskich miastach na podstawie pomiarów stężenia pyłu zawieszonego **PM2.5** [µg/m³] w latach 2015–2024. Celem analizy jest:

- ocena trendów wieloletnich i skuteczności polityki antysmogowej w Polsce,
- porównanie jakości powietrza między miastami o różnej charakterystyce geograficznej i przemysłowej,
- identyfikacja sezonowości zjawiska smogu,
- predykcja stężeń PM2.5 do roku 2030 z oceną realności osiągnięcia norm WHO.

**PM2.5** (pył zawieszony o średnicy < 2.5 µm) jest jednym z najgroźniejszych zanieczyszczeń powietrza — przenika do układu oddechowego i krwionośnego, powodując choroby serca, płuc i przedwczesne zgony.

---

## 📦 Źródło danych

| Parametr | Wartość |
|----------|---------|
| **Źródło** | GIOŚ — Główny Inspektorat Ochrony Środowiska |
| **URL** | https://powietrze.gios.gov.pl/pjp/archives |
| **Sekcja** | „Przygotowane dane do pobrania" → „Wyniki pomiarów z 20XX roku" |
| **Format** | Pliki ZIP zawierające arkusze XLSX (jeden plik na rok) |
| **Wskaźnik** | Pył zawieszony PM2.5, pomiary automatyczne 1-godzinne |
| **Lata** | 2015–2024 (10 lat) |
| **Rekordy** | 78 956 rekordów godzinowych |
| **Miasta** | Wrocław, Katowice, Kraków, Warszawa, Poznań, Gdańsk |

### Stacje pomiarowe

| Miasto | Kod stacji (lata) |
|--------|-------------------|
| Wrocław | `DsWrocAlWisn` (2015–2024) |
| Katowice | `SlKatoKossut` (2015–2024) |
| Kraków | `MpKrakAlKras` (2015–2021, 2023–2024) + `MpKrakBulwar` (backup 2022) |
| Warszawa | `MzWarAlNiepo` (2015–2024) |
| Poznań | `WpPoznPolank` (2015–2017) + `WpPoznDabrow` (2018–2024) |
| Gdańsk | `PmGdaLeczk08` (2015–2020) + `PmGdaLeczkow` (2021–2024) |

> **Uwaga:** Niektóre stacje zmieniały kody identyfikacyjne na przestrzeni lat — kod obsługuje scalanie danych z wielu kodów w jedną ciągłą serię czasową metodą `combine_first`.

---

## 🗂️ Struktura projektu

```
analiza_powietrza/
├── analiza_powietrza.py          # Główny skrypt analizy
├── README.md                     # Ten plik
├── data/                         # Dane źródłowe (nie w repo — patrz niżej)
│   ├── 2015_PM25_1g.xlsx
│   ├── 2016_PM2_5_1g.xlsx
│   ├── 2017_PM25_1g.xlsx
│   ├── ...
│   └── 2024_PM25_1g.xlsx
├── wykresy/                      # Wykresy generowane automatycznie
│   ├── 01_trend_miesięczny.png
│   ├── 02_trend_roczny_z_linia.png
│   ├── 03_sezonowosc_linie.png
│   ├── 04_heatmapa_kraków.png
│   ├── 05_przekroczenia_who.png
│   ├── 06_ranking_miast.png
│   ├── 07_rozklady.png
│   ├── 08_korelacja.png
│   ├── 09_dekompozycja_kraków.png
│   ├── 10_predykcja_wszystkie_2030.png
│   └── 11_kiedy_who.png
├── raport.docx                   # Raport Word (do uzupełnienia)
└── prezentacja.pptx              # Prezentacja PowerPoint
```

> **Dane nie są commitowane do repozytorium** ze względu na rozmiar plików. Pobierz je ręcznie z GIOŚ (link powyżej) i umieść w folderze `data/`.

---

## ⚙️ Instalacja i uruchomienie

### Wymagania

- Python 3.12+
- pip

### Krok 1 — Sklonuj repozytorium

```bash
git clone https://github.com/TwojaNazwaUzytkownika/analiza_powietrza.git
cd analiza_powietrza
```

### Krok 2 — Utwórz środowisko wirtualne i zainstaluj zależności

```bash
python -m venv venv_analiza_powietrza
# Windows:
venv_analiza_powietrza\Scripts\activate
# Linux/Mac:
source venv_analiza_powietrza/bin/activate

pip install pandas openpyxl matplotlib seaborn scipy prophet scikit-learn
```

### Krok 3 — Pobierz dane

Wejdź na https://powietrze.gios.gov.pl/pjp/archives i pobierz pliki ZIP dla lat 2015–2024.  
Rozpakuj i umieść pliki XLSX w folderze `data/`.

> Nazewnictwo plików: `2015_PM25_1g.xlsx`, `2016_PM2_5_1g.xlsx`, `2017_PM25_1g.xlsx` ... `2024_PM25_1g.xlsx`

### Krok 4 — Uruchom analizę

```bash
python analiza_powietrza.py
```

Wykresy zostaną zapisane automatycznie w folderze `wykresy/`.

---

## 🔬 Zakres analizy

### 1. Ładowanie danych
- Wczytywanie plików XLSX z obsługą **dwóch formatów GIOŚ** (2015 vs 2016+)
- Automatyczne scalanie stacji które zmieniły kody (`combine_first`)
- Usuwanie duplikatów, parsowanie dat

### 2. Pre-processing
- Usuwanie wartości ujemnych (błędy czujników)
- Usuwanie outlierów > 500 µg/m³ (awarie przyrządów)
- Interpolacja liniowa brakujących danych (max 3 godziny z rzędu)
- Agregacja godzinowa → dobowa → miesięczna → roczna

### 3. Analiza wizualna (11 wykresów)
| Nr | Wykres | Odpowiada na pytanie |
|----|--------|---------------------|
| 01 | Trend miesięczny z pionowymi liniami regulacji | Czy polityka antysmogowa działa? |
| 02 | Średnia roczna + linia trendu liniowego | O ile µg/m³ rocznie spada PM2.5? |
| 03 | Sezonowość — średnia dla każdego miesiąca | Kiedy smog jest najgorszy? |
| 04 | Heatmapa Kraków (rok × miesiąc) | Jak zmieniała się sezonowość w czasie? |
| 05 | % dni z przekroczeniem normy WHO per rok | Ile dni w roku oddychamy złym powietrzem? |
| 06 | Ranking miast (poziomy bar chart) | Które miasto jest najgorsze? |
| 07 | Rozkłady PM2.5 z krzywą KDE | Jak wygląda rozkład stężeń? |
| 08 | Macierz korelacji Spearmana | Czy smog ma charakter ogólnopolski? |
| 09 | Dekompozycja szeregu czasowego Kraków | Trend + sezonowość + szum |
| 10 | Predykcja Prophet do 2030 — wszystkie miasta | Kiedy osiągniemy normę WHO? |
| 11 | Ekstrapolacja trendu — średnia krajowa | Trajektoria całej Polski |

### 4. Analiza statystyczna
- Statystyki opisowe: średnia, mediana, odchylenie standardowe, skośność
- Analiza przekroczeń norm WHO (15 µg/m³) i EU (25 µg/m³)
- **Test Shapiro-Wilka** — normalność rozkładu
- **Test Kruskala-Wallisa** — istotność różnic między miastami
- **Regresja liniowa** — trend i tempo poprawy per miasto

### 5. Analiza zaawansowana
- **Dekompozycja szeregu czasowego** — trend + sezonowość + reszty (rolling 365 dni)
- **Predykcja Prophet (Meta)** — model szeregów czasowych z sezonowością roczną, predykcja do 2030
- **Tabela kwartalna** — średnie PM2.5 Q1–Q4 dla każdego roku i miasta, porównanie rok do roku

---

## 📊 Kluczowe wyniki

| Wskaźnik | Wartość |
|----------|---------|
| Kraków 2015 | **52.0 µg/m³** — 3.5× powyżej normy WHO |
| Kraków 2024 | **18.7 µg/m³** — poprawa o **−64%** |
| Gdańsk (średnia) | **13.9 µg/m³** — jedyne miasto poniżej normy WHO |
| Kraków — % dni z przekroczeniem WHO | **70.5%** dni przez 10 lat |
| Trend krajowy | **−1.55 µg/m³/rok** (R²=0.85) |
| Predykcja WHO — Kraków | **~2030** (wg modelu Prophet) |
| Predykcja WHO — Warszawa/Wrocław | **~2025** |

---

## 📅 Kluczowe regulacje uwzględnione w analizie

| Data | Wydarzenie |
|------|-----------|
| 2017-07-01 | Uchwała antysmogowa Małopolska (zakaz mułów węglowych) |
| 2018-09-19 | Start programu Czyste Powietrze (103 mld zł) |
| 2019-09-01 | Kraków: całkowity zakaz węgla i drewna (1. miasto w Polsce) |
| 2020-03-20 | Lockdown COVID-19 — efekt czystego nieba |
| 2022-02-24 | Kryzys energetyczny (inwazja Rosji na Ukrainę) |
| 2024-05-01 | Zakaz kopciuchów w Małopolsce (przesunięty z 01-01) |

---

## 📝 Normy jakości powietrza PM2.5

| Norma | Wartość | Źródło |
|-------|---------|--------|
| WHO (2021) | **15 µg/m³** | World Health Organization |
| EU obowiązująca | **25 µg/m³** | Dyrektywa 2008/50/WE |
| Cel EU 2030 | **10 µg/m³** | Dyrektywa 2022/2464 |

---

## 🛠️ Technologie

```
Python 3.12        — język programowania
Pandas             — manipulacja i analiza danych
OpenPyXL           — wczytywanie plików XLSX
Matplotlib         — wykresy statyczne
Seaborn            — zaawansowane wizualizacje statystyczne
SciPy              — testy statystyczne (Shapiro-Wilk, Kruskal-Wallis, regresja)
Prophet (Meta)     — predykcja szeregów czasowych
NumPy              — obliczenia numeryczne
```

## 📚 Źródła i bibliografia

1. GIOŚ — Bank Danych Pomiarowych: https://powietrze.gios.gov.pl/pjp/archives
2. WHO Global Air Quality Guidelines (2021): https://www.who.int/publications/i/item/9789240034228
3. Dyrektywa EU ws. jakości powietrza 2008/50/WE
4. Program Czyste Powietrze — NFOŚiGW: https://czystepowietrze.gov.pl
5. Prophet — dokumentacja Meta AI: https://facebook.github.io/prophet/

---

*Projekt wykonany w ramach przedmiotu „Analiza i Wizualizacja Danych" — WSB Chorzów - Szczepanik Dominik, Wojciech Wróbel*