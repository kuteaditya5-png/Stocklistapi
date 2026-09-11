"""Configurable strategy backtest with realistic Indian execution costs.

The v1.1-v2.0 research code is left frozen. This module is separate so that
changing the holding period, basket size or universe here cannot silently
alter a historical validation result.

What it adds over the frozen simulation:

* whole-share sizing from a real capital base, with leftover cash tracked
* positions carried across rebalances instead of sold and rebought, so
  turnover cost is charged only on what actually changes
* STT, stamp duty, exchange charges, GST, per-scrip DP charges and slippage
* short-term capital gains tax on realised gains, with losses carried forward
* an optional regime filter that sits in cash when the index is below its
  200-day average

Results are reported at three levels -- gross, after costs, after costs and
tax -- because the gap between them is usually larger than the strategy edge.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import yfinance as yf

from ranking_core import FEATURE_KEYS, add_features, market_regime, score_frame

BENCHMARK = "^NSEI"


class Costs:
    """Delivery-segment costs for an Indian retail account, in basis points
    of traded value unless stated otherwise.

    Defaults assume a discount broker with zero delivery brokerage. Rates
    change; check them against your own contract notes before trusting a
    net number.
    """

    def __init__(
        self,
        brokerage_bps: float = 0.0,
        stt_bps: float = 10.0,        # 0.1% on buy and on sell
        stamp_bps: float = 1.5,       # 0.015%, buy side only
        exchange_bps: float = 0.297,  # NSE transaction charge, both sides
        gst_pct: float = 18.0,        # on brokerage + exchange charge
        slippage_bps: float = 10.0,   # per side, large caps
        dp_charge: float = 15.93,     # flat, per scrip, per sell
        stcg_pct: float = 20.0,       # short-term capital gains
    ):
        self.brokerage_bps = brokerage_bps
        self.stt_bps = stt_bps
        self.stamp_bps = stamp_bps
        self.exchange_bps = exchange_bps
        self.gst_pct = gst_pct
        self.slippage_bps = slippage_bps
        self.dp_charge = dp_charge
        self.stcg_pct = stcg_pct

    def _variable(self, value: float, side: str) -> float:
        bro = value * self.brokerage_bps / 10000
        exch = value * self.exchange_bps / 10000
        gst = (bro + exch) * self.gst_pct / 100
        stt = value * self.stt_bps / 10000
        slip = value * self.slippage_bps / 10000
        stamp = value * self.stamp_bps / 10000 if side == "buy" else 0.0
        return bro + exch + gst + stt + slip + stamp

    def buy(self, value: float) -> float:
        return self._variable(value, "buy")

    def sell(self, value: float, scrips: int = 1) -> float:
        return self._variable(value, "sell") + self.dp_charge * scrips

    def describe(self) -> dict:
        return {
            "brokerage_bps": self.brokerage_bps,
            "stt_bps_per_side": self.stt_bps,
            "stamp_bps_buy": self.stamp_bps,
            "exchange_bps": self.exchange_bps,
            "gst_pct": self.gst_pct,
            "slippage_bps_per_side": self.slippage_bps,
            "dp_charge_per_scrip_sold": self.dp_charge,
            "stcg_pct": self.stcg_pct,
        }


def _frame(raw: pd.DataFrame, symbol: str) -> pd.DataFrame:
    if isinstance(raw.columns, pd.MultiIndex):
        if symbol in set(raw.columns.get_level_values(0)):
            return raw[symbol].dropna(how="all").copy()
        if symbol in set(raw.columns.get_level_values(1)):
            return raw.xs(symbol, axis=1, level=1).dropna(how="all").copy()
    return raw.copy()


def _drawdown(equity: list[float]) -> float:
    if not equity:
        return 0.0
    e = np.array(equity, dtype=float)
    peak = np.maximum.accumulate(e)
    return round(float(abs(((e / peak) - 1).min()) * 100), 2)


def _cagr(start: float, end: float, years: float) -> float:
    if start <= 0 or years <= 0:
        return 0.0
    return round(float(((end / start) ** (1 / years) - 1) * 100), 2)


def run_strategy(
    symbols: list[str],
    period: str = "10y",
    top_n: int = 8,
    hold_days: int = 21,
    regime_filter: bool = False,
    capital: float = 100000.0,
    warmup_periods: int = 6,
    costs: Costs | None = None,
) -> dict:
    costs = costs or Costs()
    hold_days = max(5, min(int(hold_days), 126))
    top_n = max(1, min(int(top_n), 20))

    raw = yf.download(
        symbols + [BENCHMARK],
        period=period,
        interval="1d",
        auto_adjust=True,
        progress=False,
        threads=True,
        group_by="ticker",
    )
    if raw is None or raw.empty:
        raise ValueError("No market data returned")

    b = _frame(raw, BENCHMARK)["Close"].copy()
    b.index = pd.DatetimeIndex(b.index).tz_localize(None).normalize()
    bench_e200 = b.ewm(span=200, adjust=False).mean()
    bench_r63 = b.pct_change(63)

    prep: dict[str, pd.DataFrame] = {}
    for s in symbols:
        try:
            f = _frame(raw, s)
            if f is None or f.empty or len(f) < 300:
                continue
            prep[s] = add_features(f, b)
        except Exception:
            continue

    if len(prep) < top_n:
        raise ValueError("Not enough symbols with usable history")

    dates = list(b.index[260:-hold_days:hold_days])
    if len(dates) < warmup_periods + 6:
        raise ValueError("Not enough history for this holding period")

    cash = capital
    holdings: dict[str, dict] = {}   # symbol -> {qty, cost_basis}
    carried_loss = 0.0
    total_costs = 0.0
    total_tax = 0.0

    equity_curve: list[float] = []
    periods: list[dict] = []
    cash_periods = 0

    def price_on(symbol: str, dt) -> float | None:
        x = prep.get(symbol)
        if x is None:
            return None
        h = x.loc[x.index <= dt]
        if h.empty:
            return None
        v = float(h.Close.iloc[-1])
        return v if np.isfinite(v) and v > 0 else None

    for n, dt in enumerate(dates):
        # Mark the book before trading.
        opening = cash + sum(
            (price_on(s, dt) or h["last_price"]) * h["qty"] for s, h in holdings.items()
        )

        in_cash = False
        if regime_filter and dt in bench_e200.index:
            if float(b.loc[dt]) < float(bench_e200.loc[dt]):
                in_cash = True

        # Rank the cross-section using only information available at dt.
        target: list[str] = []
        if not in_cash:
            q = []
            for s, x in prep.items():
                h = x.loc[x.index <= dt]
                if h.empty:
                    continue
                r = x.loc[h.index[-1]]
                if any(pd.isna(r[k]) for k in FEATURE_KEYS):
                    continue
                q.append(
                    dict(
                        symbol=s, price=float(r.Close), r21=float(r.R21), r63=float(r.R63),
                        r126=float(r.R126), rs21=float(r.RS21), rs63=float(r.RS63),
                        e50=float(r.E50), e200=float(r.E200), vol=float(r.VOL),
                        d52=float(r.D52), vr=float(r.VR),
                    )
                )
            if len(q) >= top_n:
                z = pd.DataFrame(q)
                regime = market_regime(
                    float(b.loc[dt]),
                    float(bench_e200.loc[dt]),
                    float(bench_r63.loc[dt]) if pd.notna(bench_r63.loc[dt]) else 0.0,
                )
                z["score"] = score_frame(z, regime=regime)
                target = list(z.nlargest(top_n, "score").symbol)

        # --- sell what is leaving the book ---
        realised = 0.0
        for s in list(holdings):
            if s in target:
                continue
            p = price_on(s, dt)
            if p is None:
                continue
            h = holdings.pop(s)
            gross = p * h["qty"]
            fee = costs.sell(gross, scrips=1)
            cash += gross - fee
            total_costs += fee
            realised += gross - fee - h["cost_basis"]

        # --- tax the realised gain for this rebalance ---
        taxable = realised - carried_loss
        if taxable > 0:
            tax = taxable * costs.stcg_pct / 100
            cash -= tax
            total_tax += tax
            carried_loss = 0.0
        else:
            carried_loss = -taxable

        # --- buy into the new names, equal weight, whole shares ---
        incoming = [s for s in target if s not in holdings]
        if incoming:
            book = cash + sum(
                (price_on(s, dt) or h["last_price"]) * h["qty"]
                for s, h in holdings.items()
            )
            per_name = book / max(1, len(target))
            for s in incoming:
                p = price_on(s, dt)
                if p is None:
                    continue
                qty = int(min(per_name, cash) // (p * 1.01))  # leave room for fees
                if qty <= 0:
                    continue
                gross = p * qty
                fee = costs.buy(gross)
                if gross + fee > cash:
                    continue
                cash -= gross + fee
                total_costs += fee
                holdings[s] = {"qty": qty, "cost_basis": gross + fee, "last_price": p}

        for s, h in holdings.items():
            p = price_on(s, dt)
            if p:
                h["last_price"] = p

        # --- mark forward to the end of the holding period ---
        nxt = dates[n + 1] if n + 1 < len(dates) else b.index[-1]
        closing = cash + sum(
            (price_on(s, nxt) or h["last_price"]) * h["qty"] for s, h in holdings.items()
        )

        idx_now, idx_next = float(b.loc[dt]), float(b.asof(nxt))
        bench_ret = (idx_next / idx_now - 1) * 100
        port_ret = (closing / opening - 1) * 100 if opening > 0 else 0.0

        if in_cash:
            cash_periods += 1

        if n >= warmup_periods:
            equity_curve.append(closing)
            periods.append(
                {
                    "date": str(pd.Timestamp(dt).date()),
                    "held": "cash" if in_cash else ", ".join(
                        s.replace(".NS", "") for s in target[:top_n]
                    ),
                    "portfolio_return": round(port_ret, 2),
                    "benchmark_return": round(bench_ret, 2),
                    "excess": round(port_ret - bench_ret, 2),
                }
            )

    if len(periods) < 6:
        raise ValueError("Not enough evaluated periods after warm-up")

    p = np.array([x["portfolio_return"] for x in periods], dtype=float)
    n_arr = np.array([x["benchmark_return"] for x in periods], dtype=float)

    start_equity = equity_curve[0] / (1 + p[0] / 100) if p[0] != -100 else capital
    final = equity_curve[-1]
    years = len(periods) * hold_days / 252

    # Statistical honesty: is the average excess distinguishable from zero?
    excess = p - n_arr
    se = float(excess.std(ddof=1) / np.sqrt(len(excess))) if len(excess) > 1 else 0.0
    t_stat = round(float(excess.mean() / se), 2) if se > 0 else 0.0

    bench_growth = float(np.prod(1 + n_arr / 100))

    return {
        "config": {
            "universe_size": len(symbols),
            "symbols_with_history": len(prep),
            "top_n": top_n,
            "hold_days": hold_days,
            "rebalances_per_year": round(252 / hold_days, 1),
            "regime_filter": regime_filter,
            "period": period,
            "starting_capital": capital,
        },
        "costs": costs.describe(),
        "periods_evaluated": len(periods),
        "years": round(years, 1),
        "final_capital": round(final, 2),
        "benchmark_final_capital": round(start_equity * bench_growth, 2),
        "total_return_pct": round((final / start_equity - 1) * 100, 2),
        "benchmark_return_pct": round((bench_growth - 1) * 100, 2),
        "cagr_pct": _cagr(start_equity, final, years),
        "benchmark_cagr_pct": _cagr(start_equity, start_equity * bench_growth, years),
        "beat_benchmark_pct": round(float((p > n_arr).mean() * 100), 1),
        "positive_periods_pct": round(float((p > 0).mean() * 100), 1),
        "avg_excess_pct": round(float(excess.mean()), 3),
        "excess_t_stat": t_stat,
        "significant": bool(abs(t_stat) >= 2),
        "max_drawdown_pct": _drawdown(equity_curve),
        "total_costs_paid": round(total_costs, 2),
        "total_tax_paid": round(total_tax, 2),
        # Expressed per year against average equity, so it stays readable as
        # the portfolio compounds. Reads as an annual drag on returns.
        "cost_and_tax_drag_pct_per_year": round(
            (total_costs + total_tax) / max(1.0, float(np.mean(equity_curve))) / max(years, 0.1) * 100,
            2,
        ),
        "periods_in_cash": cash_periods,
        "recent_periods": periods[-8:],
        "reading": (
            "A t-statistic below 2 means the average excess return is not "
            "distinguishable from luck at this sample size. Costs and tax are "
            "deducted from the strategy but not from the benchmark, which is an "
            "index level rather than a tradable fund. Drawdown is measured at "
            "rebalance dates only, so it understates what you would have seen "
            "intra-period."
        ),
    }


def compare_configurations(symbols: list[str], period: str = "10y") -> dict:
    """Run a small predefined grid so the cost and turnover effect is visible.

    The grid is fixed and declared up front. It is a diagnostic, not a search
    for the best-looking setting -- picking the winner here and reporting its
    number would be exactly the overfitting the earlier versions fell into.
    """
    grid = [
        {"label": "Top 3, monthly", "top_n": 3, "hold_days": 21, "regime_filter": False},
        {"label": "Top 8, monthly", "top_n": 8, "hold_days": 21, "regime_filter": False},
        {"label": "Top 8, quarterly", "top_n": 8, "hold_days": 63, "regime_filter": False},
        {"label": "Top 8, quarterly, cash below 200-DMA", "top_n": 8, "hold_days": 63,
         "regime_filter": True},
    ]

    results = []
    for cfg in grid:
        try:
            r = run_strategy(
                symbols, period=period, top_n=cfg["top_n"],
                hold_days=cfg["hold_days"], regime_filter=cfg["regime_filter"],
            )
            results.append({
                "label": cfg["label"],
                "periods": r["periods_evaluated"],
                "cagr_pct": r["cagr_pct"],
                "benchmark_cagr_pct": r["benchmark_cagr_pct"],
                "beat_benchmark_pct": r["beat_benchmark_pct"],
                "avg_excess_pct": r["avg_excess_pct"],
                "excess_t_stat": r["excess_t_stat"],
                "significant": r["significant"],
                "max_drawdown_pct": r["max_drawdown_pct"],
                "cost_and_tax_drag_pct_per_year": r["cost_and_tax_drag_pct_per_year"],
            })
        except Exception as e:
            results.append({"label": cfg["label"], "error": str(e)})

    return {
        "engine": "v2.2 cost-and-tax aware comparison",
        "period": period,
        "universe_size": len(symbols),
        "results": results,
        "warning": (
            "All four are measured on the same history, so the best-looking row "
            "is not a recommendation. Treat a t-statistic under 2 as no "
            "demonstrated edge."
        ),
    }
