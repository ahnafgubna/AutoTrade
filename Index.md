# AutoTrader

## Goal
Reactive automated day trading bot using Alpaca's paper trading API, starting with paper trading before going live.

## Phases
- [x] Phase 0: Research & setup
- [x] Phase 1: Backtesting — iterate until consistent profit
- [ ] Phase 2: Live paper trading — run for a few weeks to validate (current)
- [ ] Phase 3: Live trading with real money ($400 starting capital)

## Stack
- Language: Python 3.14
- Broker: Alpaca (paper trading endpoint)
- Asset: TQQQ (3x leveraged Nasdaq ETF)
- Capital: $400 (matches real intended live capital)
- Timeframe: 1-minute bars
- Schedule: Runs daily on weekdays, auto-stops after market hours

## Optimal Strategy (confirmed via backtesting)
- **Type:** Mean reversion scalp
- **Entry:** Z-score ≤ -1.5 (price 1.5 std deviations below 20-candle mean)
- **Exit:** Price hits +0.5% target (take profit) or -0.8% stop loss
- **Stop candles:** 2 (price must stay below stop for 2 consecutive candles)
- **Daily loss limit:** 3% of capital — halts new entries for the day if hit
- **Re-investment:** Yes — position size recalculates each trade based on current cash

## Files
- `main.py` — live paper trading loop (needs updating to match backtest logic)
- `strategy.py` — signal logic (needs updating)
- `broker.py` — Alpaca API wrapper
- `backtester.py` — backtester (finalized)

---

## Backtest Results Summary (Best Configuration)

**Asset:** TQQQ | **Timeframe:** 1-min bars | **Period:** 365 days | **Capital:** $400

| Metric | Value |
|--------|-------|
| Total return | +$276.97 (69.2%) |
| Final balance | $676.97 |
| Total trades | 1,521 |
| Win rate | 64.3% |
| Avg trade P&L | +$0.18 |
| Worst single trade | -$25.15 |
| Trading days | 251 |
| Profitable days | 152 / 251 (60.6%) |
| Avg daily P&L | +$1.10 (+0.28%) |
| Best day | +$45.06 |
| Worst day | -$25.15 |
| Halted days (loss limit) | 34 |

---

## Progress Log

### Session 1 — 2026-06-25
- Set up Alpaca paper account, confirmed API connection
- Built broker.py, strategy.py, main.py, backtester.py
- Placed successful test buy order (AAPL, 1 share)
- Tested SMA crossover strategy — too lagging, losing on 3/4 stocks

### Session 2 — 2026-06-26
- Switched to mean reversion (z-score entry) — first profitable results
- Dropped TSLA — too volatile for any strategy tested
- Validated SPY and NVDA on full year — both profitable
- Screened for $400-affordable stocks — identified AAL and BAC
- BAC: +$8/year on $400. Viable but too small
- Discovered TQQQ (3x leveraged ETF) — no price limit on shares with $400
- Iterated TQQQ through multiple configs:
  - 5-min bars: +$100.96 (25.2% annual)
  - 1-min bars, 1.5%/1.0% stop/target: +$115.07 (28.8% annual)
  - 1-min bars, 0.8%/0.5% stop/target: **+$276.97 (69.2% annual)** ← best
- Confirmed over-tuning is counterproductive — extra filters hurt results
- Locked in final parameters (see Optimal Strategy above)

---

## Mistakes & Lessons
- **Daily bars useless for day trading** — 5-min minimum, 1-min better
- **SMA crossover is lagging** — enters after the move already happened
- **Fidelity has no public API** — using Alpaca instead
- **TSLA too volatile** — gaps through stop losses on all strategies
- **One strategy doesn't fit all stocks** — tune per asset
- **SPY suits mean reversion exit** — exit at mean, not fixed target
- **More parameters ≠ better results** — time filter and z=-1.2 both hurt TQQQ
- **SQQQ decays over time** — bad for holding, avoid as a pair trade
- **Backtest 30 days for speed, validate on 1 year before trusting**
- **Tighter stop/target (0.8%/0.5%) outperforms wider (1.5%/1.0%) on 1-min bars**

---

## Paper Trading Plan
- **Start date:** TBD (after main.py is updated)
- **Duration:** 2-4 weeks minimum before evaluating
- **Success criteria:** Win rate ≥ 60%, positive total return, no single day loss > 5%
- **Run schedule:** Weekdays, auto-triggered at market open
- **Log results:** Update this file weekly with actual vs backtest comparison

## Next Steps
1. Update main.py and strategy.py to match finalized backtester logic
2. Test main.py with a single paper trade to confirm execution works
3. Set up daily Windows scheduler to run automatically
4. Run paper trading for 2-4 weeks
5. Compare live results vs backtest — if close, proceed to real money
6. Go live with $400 real capital on Alpaca
