A small project where I fetch CPI basket weights from SCB and visualize how the composition has changed since 1980. Also shows which categories actually drove inflation each year.

**Charts:**
- [Basket shares over time](https://erikengborg-oss.github.io/cpi_sweden/)
- [Inflation contributions by category](https://erikengborg-oss.github.io/cpi_sweden/contributions.html)

Updated automatically every month.

## Run locally

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python3 scripts/cpi_sweden.py
```

Outputs `figures/index.html` and `figures/contributions.html`.
