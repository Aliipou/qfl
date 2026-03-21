<div align="center">

[![Python](https://img.shields.io/badge/Python-3.10+-3776AB?style=flat&amp;logo=python)](https://python.org)
[![License](https://img.shields.io/badge/License-MIT-green?style=flat)](LICENSE)

# qfl — Quantitative Finance Library

**Backtesting engine, portfolio optimization, and market data pipelines.**

</div>

## What It Does

`qfl` is a Python library for systematic strategy development. It handles the tedious parts — data ingestion, position management, transaction costs, and performance attribution — so you can focus on the strategy logic.

## Modules

**Backtesting Engine**
Event-driven simulation. Processes historical data bar-by-bar, executes orders at realistic prices, and tracks portfolio state throughout. Handles splits, dividends, and corporate actions.

**Portfolio Optimization**
Mean-variance optimization, risk parity, and Black-Litterman model. Uses `cvxpy` for convex optimization problems and `scipy` for constrained numerical methods.

**Market Data Pipelines**
Connectors for common data sources with normalization and validation. Returns a consistent DataFrame format regardless of source.

**Performance Attribution**
Factor decomposition, Brinson attribution, and drawdown analysis. Generates standard tearsheet metrics: Sharpe, Sortino, Calmar, max drawdown.

## Quick Start

```python
from qfl.data import load_prices
from qfl.backtest import Backtest, Strategy
from qfl.portfolio import optimize_weights

prices = load_prices(["AAPL", "MSFT", "GOOG"], start="2020-01-01", end="2024-01-01")

class MomentumStrategy(Strategy):
    def generate_signals(self, prices):
        returns_12m = prices.pct_change(252)
        return (returns_12m > 0).astype(float)

bt = Backtest(strategy=MomentumStrategy(), prices=prices, initial_capital=100_000)
results = bt.run()
print(results.summary())
```

## License

MIT
