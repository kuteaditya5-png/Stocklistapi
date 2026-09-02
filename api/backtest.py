from __future__ import annotations

from collections import defaultdict
from datetime import time
from math import isfinite
from typing import Iterable

import numpy as np
import pandas as pd
import yfinance as yf

from indicators import add_indicators
from intraday import _indicators, intraday_signal_from_row, trade_levels
from scoring import score_technicals


def _round(value, digits=2):
    if value is None:
        return None
    try:
        if not isfinite(float(value)):
            return None
        return round(float(value), digits)
    except Exception:
        return None


def _pct(n, d):
    return round((n / d) * 100, 1) if d else 0.0


def _extract_ticker_frame(raw: pd.DataFrame, symbol: str) -> pd.DataFrame:
    if raw is None or raw.empty:
        return pd.DataFrame()

    if isinstance(raw.columns, pd.MultiIndex):
        level0 = set(raw.columns.get_level_values(0))
        level1 = set(raw.columns.get_level_values(1))

        if symbol in level0:
            return raw[symbol].dropna(how="all").copy()

        if symbol in level1:
            return raw.xs(symbol, axis=1, level=1).dropna(how="all").copy()

        return pd.DataFrame()

    return raw.dropna(how="all").copy()


def _batch_history(symbols: list[str], period: str, interval: str) -> dict[str, pd.DataFrame]:
    raw = yf.download(
        symbols,
        period=period,
        interval=interval,
        auto_adjust=True,
        progress=False,
        threads=True,
        group_by="ticker",
    )

    return {
        symbol: _extract_ticker_frame(raw, symbol)
        for symbol in symbols
    }


def _local_index(index: pd.Index) -> pd.DatetimeIndex:
    idx = pd.DatetimeIndex(index)
    if idx.tz is None:
        # Yahoo's NSE intraday data normally carries a timezone.
        # This fallback treats a naive timestamp as India local time.
        return idx.tz_localize("Asia/Kolkata")
    return idx.tz_convert("Asia/Kolkata")


def _price_bucket(price: float) -> str:
    if price < 200:
        return "Under ₹200"
    if price < 500:
        return "₹200–₹500"
    if price < 1000:
        return "₹500–₹1,000"
    return "₹1,000+"


def _confidence_bucket(confidence: float) -> str:
    if confidence < 70:
        return "<70"
    if confidence < 80:
        return "70–79"
    return "80+"


def _time_bucket(ts: pd.Timestamp) -> str:
    t = ts.time()
    if t < time(11, 0):
        return "09:30–11:00"
    if t < time(13, 0):
        return "11:00–13:00"
    return "13:00–14:30"


def _group_metrics(trades: list[dict], key: str) -> list[dict]:
    groups = defaultdict(list)
    for t in trades:
        groups[t[key]].append(t)

    rows = []
    for name, vals in groups.items():
        total = len(vals)
        target_hits = sum(v["outcome"] == "TARGET1" for v in vals)
        positive = sum(v["r_multiple"] > 0 for v in vals)
        avg_r = np.mean([v["r_multiple"] for v in vals]) if vals else 0
        rows.append(
            {
                "group": str(name),
                "signals": total,
                "target1_hit_rate": _pct(target_hits, total),
                "positive_outcome_rate": _pct(positive, total),
                "avg_r": _round(avg_r, 2),
            }
        )

    rows.sort(key=lambda x: (-x["signals"], x["group"]))
    return rows


def _intraday_metrics(trades: list[dict]) -> dict:
    total = len(trades)
    if not total:
        return {
            "signals_tested": 0,
            "target1_hits": 0,
            "stop_hits": 0,
            "timeouts": 0,
            "target1_hit_rate": 0.0,
            "positive_outcome_rate": 0.0,
            "avg_r": 0.0,
            "avg_winner_r": 0.0,
            "avg_loser_r": 0.0,
            "profit_factor": 0.0,
            "max_drawdown_r": 0.0,
        }

    rvals = [float(t["r_multiple"]) for t in trades]
    wins = [r for r in rvals if r > 0]
    losses = [r for r in rvals if r < 0]

    target_hits = sum(t["outcome"] == "TARGET1" for t in trades)
    stop_hits = sum(t["outcome"] == "STOP" for t in trades)
    timeouts = sum(t["outcome"] == "TIMEOUT" for t in trades)

    gross_profit = sum(wins)
    gross_loss = abs(sum(losses))
    profit_factor = gross_profit / gross_loss if gross_loss > 0 else (99.0 if gross_profit > 0 else 0.0)

    cumulative = np.cumsum(rvals)
    running_peak = np.maximum.accumulate(np.insert(cumulative, 0, 0.0))[1:]
    drawdowns = cumulative - running_peak
    max_dd = abs(float(drawdowns.min())) if len(drawdowns) else 0.0

    return {
        "signals_tested": total,
        "target1_hits": target_hits,
        "stop_hits": stop_hits,
        "timeouts": timeouts,
        "target1_hit_rate": _pct(target_hits, total),
        "positive_outcome_rate": _pct(len(wins), total),
        "avg_r": _round(np.mean(rvals), 2),
        "avg_winner_r": _round(np.mean(wins), 2) if wins else 0.0,
        "avg_loser_r": _round(np.mean(losses), 2) if losses else 0.0,
        "profit_factor": _round(profit_factor, 2),
        "max_drawdown_r": _round(max_dd, 2),
    }


def run_intraday_backtest(
    symbols: list[str],
    period: str = "1mo",
    max_hold_bars: int = 12,
) -> dict:
    """
    Backtest the SAME live intraday rule set.

    Method:
    - 5-minute bars
    - one first valid signal per stock per trading session
    - signal window 09:30 to 14:30 India time
    - Target 1 = +1.5R, stop = -1R
    - max hold defaults to 12 bars (~60 minutes)
    - if target and stop both occur in one OHLC bar, count STOP conservatively
    """
    period = period if period in {"5d", "1mo"} else "1mo"
    max_hold_bars = max(3, min(int(max_hold_bars), 24))

    histories = _batch_history(symbols, period=period, interval="5m")
    trades = []
    errors = []

    for symbol in symbols:
        try:
            df = histories.get(symbol, pd.DataFrame())
            if df is None or len(df) < 40:
                raise ValueError("Insufficient 5-minute history")

            x = _indicators(df).dropna(subset=["EMA9", "EMA20", "VWAP", "ATR"]).copy()
            if x.empty:
                raise ValueError("Indicators unavailable")

            local_idx = _local_index(x.index)
            x["_local_time"] = local_idx
            x["_session"] = [ts.date() for ts in local_idx]

            for _, day in x.groupby("_session", sort=True):
                eligible = day[
                    day["_local_time"].map(
                        lambda ts: time(9, 30) <= ts.time() <= time(14, 30)
                    )
                ]

                if len(eligible) < 3:
                    continue

                selected_index = None
                selected_sig = None

                # Use the first tradeable setup of the day to avoid repeatedly
                # counting highly correlated signals from the same move.
                for idx, row in eligible.iterrows():
                    sig = intraday_signal_from_row(row)
                    if sig["signal"] != "NO TRADE":
                        selected_index = idx
                        selected_sig = sig
                        break

                if selected_index is None:
                    continue

                pos = day.index.get_loc(selected_index)
                if isinstance(pos, slice):
                    pos = pos.start

                entry_row = day.iloc[pos]
                future = day.iloc[pos + 1 : pos + 1 + max_hold_bars]
                if future.empty:
                    continue

                entry = float(entry_row["Close"])
                atr = float(entry_row["ATR"])
                levels = trade_levels(entry, atr, selected_sig["signal"])
                stop = float(levels["stop_loss"])
                target = float(levels["target1"])
                risk = float(levels["risk_per_share"])
                direction = 1 if selected_sig["signal"] == "BUY" else -1

                outcome = "TIMEOUT"
                exit_price = float(future.iloc[-1]["Close"])

                for _, bar in future.iterrows():
                    high = float(bar["High"])
                    low = float(bar["Low"])

                    if selected_sig["signal"] == "BUY":
                        stop_hit = low <= stop
                        target_hit = high >= target
                    else:
                        stop_hit = high >= stop
                        target_hit = low <= target

                    # Conservative treatment when OHLC cannot tell which level
                    # was reached first inside the same 5-minute bar.
                    if stop_hit:
                        outcome = "STOP"
                        exit_price = stop
                        break
                    if target_hit:
                        outcome = "TARGET1"
                        exit_price = target
                        break

                r_multiple = direction * (exit_price - entry) / risk

                ts = entry_row["_local_time"]
                trades.append(
                    {
                        "symbol": symbol.replace(".NS", ""),
                        "date": str(ts.date()),
                        "time": ts.strftime("%H:%M"),
                        "signal": selected_sig["signal"],
                        "confidence": float(selected_sig["confidence"]),
                        "entry": _round(entry, 2),
                        "outcome": outcome,
                        "r_multiple": _round(r_multiple, 3),
                        "price_bucket": _price_bucket(entry),
                        "confidence_bucket": _confidence_bucket(selected_sig["confidence"]),
                        "time_bucket": _time_bucket(ts),
                    }
                )

        except Exception as e:
            errors.append({"symbol": symbol, "error": str(e)})

    metrics = _intraday_metrics(trades)

    return {
        "engine": "intraday",
        "scope": "Same rule set as the live StockLens intraday engine",
        "period": period,
        "symbols_tested": [s.replace(".NS", "") for s in symbols],
        "metrics": metrics,
        "by_signal": _group_metrics(trades, "signal"),
        "by_confidence": _group_metrics(trades, "confidence_bucket"),
        "by_price": _group_metrics(trades, "price_bucket"),
        "by_time": _group_metrics(trades, "time_bucket"),
        "recent_trades": trades[-12:],
        "errors": errors,
        "methodology": [
            "Uses historical 5-minute Yahoo Finance bars.",
            "Tests only the first valid StockLens setup per stock per session.",
            "Target 1 is +1.5R and stop-loss is -1R.",
            "Trade expires after the selected hold window if neither level is hit.",
            "If stop and target appear in the same OHLC bar, the test counts a stop conservatively.",
        ],
        "limitations": [
            "Gross backtest: brokerage, taxes, slippage and bid/ask spread are not included.",
            "Yahoo 5-minute data can contain gaps or revisions.",
            "Current NIFTY 50 constituents introduce survivorship bias.",
            "Historical results do not guarantee future performance.",
        ],
    }


def _technical_snapshot_from_row(r: pd.Series) -> dict:
    def val(key):
        x = r.get(key)
        return None if pd.isna(x) else float(x)

    return {
        "close": val("Close"),
        "ema20": val("EMA20"),
        "ema50": val("EMA50"),
        "ema200": val("EMA200"),
        "rsi14": val("RSI14"),
        "macd": val("MACD"),
        "macd_signal": val("MACD_SIGNAL"),
        "macd_hist": val("MACD_HIST"),
        "volume_ratio": val("VOLUME_RATIO"),
        "high_20": val("HIGH_20"),
    }


def _monthly_score_bucket(score: float) -> str:
    if score >= 85:
        return "85+"
    if score >= 75:
        return "75–84"
    return "65–74"


def run_monthly_technical_backtest(
    symbols: list[str],
    period: str = "2y",
    horizon_days: int = 21,
    min_technical_score: float = 65,
) -> dict:
    """
    Historical proxy for the 1-month engine.

    This intentionally backtests only the technical timing component because
    free Yahoo data does not provide reliable point-in-time historical
    fundamentals/valuation/shareholding snapshots. Calling this a full-model
    accuracy test would be misleading.
    """
    period = period if period in {"1y", "2y"} else "2y"
    horizon_days = max(10, min(int(horizon_days), 30))
    min_technical_score = max(50, min(float(min_technical_score), 90))

    benchmark = "^NSEI"
    all_symbols = symbols + [benchmark]
    histories = _batch_history(all_symbols, period=period, interval="1d")
    bench = histories.get(benchmark, pd.DataFrame())

    if bench is None or bench.empty or "Close" not in bench:
        raise ValueError("NIFTY benchmark history unavailable")

    bench_close = bench["Close"].copy()
    bench_close.index = pd.DatetimeIndex(bench_close.index).normalize()

    samples = []
    errors = []

    for symbol in symbols:
        try:
            df = histories.get(symbol, pd.DataFrame())
            if df is None or len(df) < 230:
                raise ValueError("Insufficient daily history")

            x = add_indicators(df).copy()
            x.index = pd.DatetimeIndex(x.index).normalize()
            x["BENCH_CLOSE"] = bench_close.reindex(x.index).ffill()
            x = x.dropna(
                subset=[
                    "Close",
                    "EMA20",
                    "EMA50",
                    "EMA200",
                    "RSI14",
                    "MACD",
                    "MACD_SIGNAL",
                    "BENCH_CLOSE",
                ]
            )

            i = 0
            while i + horizon_days < len(x):
                row = x.iloc[i]
                technical = _technical_snapshot_from_row(row)
                tech_score = float(score_technicals(technical)[0])

                if tech_score < min_technical_score:
                    i += 1
                    continue

                future = x.iloc[i + horizon_days]
                entry = float(row["Close"])
                exit_price = float(future["Close"])
                stock_return = (exit_price / entry - 1) * 100

                bench_entry = float(row["BENCH_CLOSE"])
                bench_exit = float(future["BENCH_CLOSE"])
                nifty_return = (bench_exit / bench_entry - 1) * 100

                samples.append(
                    {
                        "symbol": symbol.replace(".NS", ""),
                        "date": str(x.index[i].date()),
                        "technical_score": round(tech_score, 1),
                        "score_bucket": _monthly_score_bucket(tech_score),
                        "stock_return_pct": _round(stock_return, 2),
                        "nifty_return_pct": _round(nifty_return, 2),
                        "excess_return_pct": _round(stock_return - nifty_return, 2),
                        "positive": stock_return > 0,
                        "beat_nifty": stock_return > nifty_return,
                    }
                )

                # Avoid overlapping 1-month observations from nearly identical windows.
                i += horizon_days

        except Exception as e:
            errors.append({"symbol": symbol, "error": str(e)})

    total = len(samples)

    if total:
        stock_returns = [s["stock_return_pct"] for s in samples]
        nifty_returns = [s["nifty_return_pct"] for s in samples]
        excess_returns = [s["excess_return_pct"] for s in samples]
        positive = sum(s["positive"] for s in samples)
        beat = sum(s["beat_nifty"] for s in samples)

        metrics = {
            "samples_tested": total,
            "positive_after_1m_rate": _pct(positive, total),
            "beat_nifty_rate": _pct(beat, total),
            "avg_stock_return_pct": _round(np.mean(stock_returns), 2),
            "avg_nifty_return_pct": _round(np.mean(nifty_returns), 2),
            "avg_excess_return_pct": _round(np.mean(excess_returns), 2),
            "median_stock_return_pct": _round(np.median(stock_returns), 2),
        }
    else:
        metrics = {
            "samples_tested": 0,
            "positive_after_1m_rate": 0.0,
            "beat_nifty_rate": 0.0,
            "avg_stock_return_pct": 0.0,
            "avg_nifty_return_pct": 0.0,
            "avg_excess_return_pct": 0.0,
            "median_stock_return_pct": 0.0,
        }

    by_score = []
    groups = defaultdict(list)
    for sample in samples:
        groups[sample["score_bucket"]].append(sample)

    for bucket, vals in groups.items():
        n = len(vals)
        by_score.append(
            {
                "group": bucket,
                "samples": n,
                "positive_after_1m_rate": _pct(sum(v["positive"] for v in vals), n),
                "beat_nifty_rate": _pct(sum(v["beat_nifty"] for v in vals), n),
                "avg_return_pct": _round(np.mean([v["stock_return_pct"] for v in vals]), 2),
            }
        )

    by_score.sort(key=lambda r: r["group"])

    return {
        "engine": "1month_technical_proxy",
        "scope": "Historical technical-timing proxy, NOT the full StockLens 1-month model",
        "period": period,
        "horizon_trading_days": horizon_days,
        "minimum_technical_score": min_technical_score,
        "symbols_tested": [s.replace(".NS", "") for s in symbols],
        "metrics": metrics,
        "by_score": by_score,
        "recent_samples": samples[-12:],
        "errors": errors,
        "methodology": [
            f"Tests a {horizon_days}-trading-day forward return after a technical score of at least {min_technical_score:.0f}.",
            "Uses non-overlapping sample windows to reduce repeated counting of the same move.",
            "Compares each stock return with NIFTY 50 over the same dates.",
        ],
        "limitations": [
            "This is NOT a full 1-month StockLens accuracy test.",
            "Reliable point-in-time historical fundamentals, valuation and shareholding data are not included.",
            "Current NIFTY 50 constituents introduce survivorship bias.",
            "Corporate actions/data quality can affect historical results.",
            "Historical results do not guarantee future performance.",
        ],
    }
