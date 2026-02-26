## Project structure

This project fetches yearly CPI basket weights from Statistics Sweden (SCB) for **1980-2026** and produces:

- A wide CSV table with COICOP categories by year
- An interactive HTML chart of category shares over time

Live chart: [https://erikengborg-oss.github.io/cpi_sweden/](https://erikengborg-oss.github.io/cpi_sweden/)

Main files and folders:

- `scripts/cpi_sweden.py` - data fetch + transform + export
- `data/` - generated CSV output
- `figures/` - generated HTML chart

## Key takeaways
- Housing (04) dominates throughout. It's the largest CPI basket category in every year.
- Food and non-alcoholic beverages (01) show the biggest decline: 20.10% -> 13.92% (-6.18 percentage points).
- Alcoholic beverages & tobacco (02) and Clothing & footwear (03) also decline: -4.30 pp and -3.62 pp.
- Restaurants & accommodation services (11) increase the most: 4.05% -> 8.40% (+4.35 pp).
- Recreation, sport and culture (09) and Health (06) both trend upward: +1.79 pp and +1.74 pp.

## Setup
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Run
```bash
python3 scripts/cpi_sweden.py

Default outputs:
- `data/share_cpi_wide.csv`
- `figures/index.html`

## Notes
- Uses SCB API endpoint `KPI2020COICOP2M`.
- Excludes category `00` (total basket) from share chart.
