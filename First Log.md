# AutoTrader

## Goal
Build a reactive automated day trading program that interfaces with Fidelity to generate profit.

## Phases
- [x] Phase 0: Research & setup
- [ ] Phase 1: Paper trading (current)
- [ ] Phase 2: Live trading on Fidelity

## Architecture Plan

### Data Feed
- Use a free/cheap market data API (e.g. **Alpaca**, **Polygon.io**, or **Yahoo Finance via yfinance**)
- Fidelity does not have a public trading API — workaround options:
  - **Alpaca** (recommended for paper trading): has a full REST + WebSocket API, free paper trading account, no Fidelity needed to start
  - **Fidelity ATP (Active Trader Pro)** automation via their unofficial API or screen scraping (fragile, not recommended)

### Strategy (start simple)
- Moving Average Crossover (SMA 9 / SMA 21) — well understood, easy to test
- Add RSI filter to reduce false signals
- Expand to more complex strategies once baseline works

### Stack
- Language: **Python**
- Data: `yfinance` or `alpaca-trade-api`
- Backtesting: `backtrader` or `vectorbt`
- Paper trading execution: Alpaca paper account
- Logging/state: saved back to this vault

## Current Status
Setting up architecture. Decided to use Alpaca for paper trading since Fidelity has no public API.

## Next Steps
1. Set up Alpaca paper trading account (free at alpaca.markets)
2. Build data fetcher script
3. Implement basic SMA crossover strategy
4. Run paper trades and log results here

## Code Files
*(to be added as we build)*

## Results Log
*(paper trade results go here)*
