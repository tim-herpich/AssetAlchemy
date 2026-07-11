# Portfolio Tracker (Streamlit)

A Streamlit portfolio-analysis app built around a strict three-sheet Excel template. It ingests transactions, historical prices, and target portfolio composition, then produces dynamic performance, risk, allocation, rebalancing, and export outputs for any number of positions.

## Features

- Downloadable blank and sample Excel templates
- Strict upload parsing for exactly three input sheets:
  - Portfolio Composition
  - Historical Prices
  - Transactions
- Dynamic asset detection from ISIN/Product values
- Multi-tab analysis UI:
  - Upload & Validation
  - Portfolio Overview
  - Performance
  - Positions
  - Allocation & Rebalancing
  - Risk Metrics
  - Rolling Analysis
  - Transactions
  - Historical Prices
  - Export
- Metrics include:
  - Portfolio value, invested capital, fees, and cash flows
  - Daily, annual, rolling, time-weighted, and money-weighted returns
  - Allocation drift and rebalance suggestions
  - Drawdown, volatility, VaR/CVaR, concentration, and diversification
  - Sharpe and Sortino
- Interactive Plotly visuals:
  - Value vs invested curve
  - Drawdown curve
  - Current/target allocation charts
  - Position value, quantity, and weight charts
  - Monthly return heatmap
  - Rolling performance charts
  - Trade timeline, fee charts, and price history

## Input Expectations

The required workbook contains exactly these input sheets:

1. `Portfolio Composition`
2. `Historical Prices`
3. `Transactions`

Use the in-app template downloads for the exact structure. The Transactions sheet parses only columns A:J under `All Transactions`; Historical Prices use repeating `Product / ISIN / Date / Price` blocks; Portfolio Composition uses dynamic `Instrument / Target Weight in Portfolio` pairs plus a final tolerance column.

## Project Structure

```text
app.py
src/portfolio_analytics/
  models.py          # Shared workbook, validation, settings, and analysis models
  workbook.py        # Excel template generation, parsing, and validation
  engine.py          # Portfolio calculation engine
  pipeline.py        # Parse-and-analyze workflow used by Streamlit
  charts.py          # Plotly chart builders
  exports.py         # CSV/XLSX export helpers
  ui/
    app.py           # Streamlit pages and navigation
    design.py        # CSS and visual system
    formatting.py    # Display formatting helpers
tests/
  test_portfolio_tracker.py
```

## Local Run

```bash
pip install -r requirements.txt
streamlit run app.py
```

Then open http://localhost:8501

## Hosting Options

### Streamlit Community Cloud

1. Push this folder to GitHub.
2. Create a new app in Streamlit Community Cloud.
3. Set the main file to `app.py`.
4. Deploy.

### Docker

```bash
docker build -t portfolio-intel .
docker run -p 8501:8501 portfolio-intel
```

Then open http://localhost:8501

## Notes

- Transaction cash-flow values are entered as positive EUR amounts.
- `Buy` increases quantity and invested capital; `Sell` decreases both; `Transfer` rows are preserved but ignored for quantity and cash-flow calculations.
- The old tax sheet and all tax calculations are intentionally removed.
