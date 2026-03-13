"""
Signal Engine — Ports Pine Script C10/C20 momentum indicators to Python.
Detects: C10L, C20L, L20L, C10S, C20S, L20S, M2L-M5L, M2S-M5S
"""

import numpy as np
import pandas as pd
import ta as ta_lib
import math
import logging
from dataclasses import dataclass, field
from typing import Optional
from config import config

logger = logging.getLogger(__name__)


@dataclass
class Signal:
    symbol: str
    signal_type: str  # C10L, C20L, C10S, etc.
    direction: str  # long or short
    candle_high: float
    candle_low: float
    candle_close: float
    candle_volume: float
    buy_momentum: float
    timestamp: float
    entry_levels: dict = field(default_factory=dict)

    def __post_init__(self):
        if self.direction == "long" and not self.entry_levels:
            self.entry_levels = self.calculate_entry_levels()

    def calculate_entry_levels(self) -> dict:
        H = self.candle_high
        L = self.candle_low
        rng = H - L
        if rng <= 0:
            return {}
        p66 = L + rng * 0.66
        p44 = L + rng * 0.44
        mid = L + rng * 0.5
        p10 = mid * 0.9
        avg = (p66 + p44 + p10) / 3
        tp = avg * (1 + config.ROI_TARGET)
        return {
            "p66": round(p66, 8),
            "p44": round(p44, 8),
            "p10": round(p10, 8),
            "avg_entry": round(avg, 8),
            "tp": round(tp, 8),
        }


def compute_rsi(series: pd.Series, period: int = 14) -> pd.Series:
    delta = series.diff()
    gain = delta.where(delta > 0, 0.0)
    loss = (-delta).where(delta < 0, 0.0)
    avg_gain = gain.ewm(alpha=1 / period, min_periods=period).mean()
    avg_loss = loss.ewm(alpha=1 / period, min_periods=period).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    return 100 - (100 / (1 + rs))


def crossover(series: pd.Series, level: float) -> pd.Series:
    return (series > level) & (series.shift(1) <= level)


def crossunder(series: pd.Series, level: float) -> pd.Series:
    return (series < level) & (series.shift(1) >= level)


class SignalEngine:
    def __init__(self):
        self.candle_buffers: dict[str, pd.DataFrame] = {}
        self.last_signals: dict[str, Optional[Signal]] = {}

    def update_candles(self, symbol: str, df: pd.DataFrame) -> list[Signal]:
        self.candle_buffers[symbol] = df.copy()
        return self.detect_signals(symbol)

    def add_candle(self, symbol: str, candle: dict) -> list[Signal]:
        new_row = pd.DataFrame(
            [
                {
                    "timestamp": candle["timestamp"],
                    "open": float(candle["open"]),
                    "high": float(candle["high"]),
                    "low": float(candle["low"]),
                    "close": float(candle["close"]),
                    "volume": float(candle["volume"]),
                }
            ]
        )

        if symbol not in self.candle_buffers:
            self.candle_buffers[symbol] = new_row
        else:
            buf = self.candle_buffers[symbol]
            if len(buf) > 0 and buf.iloc[-1]["timestamp"] == candle["timestamp"]:
                self.candle_buffers[symbol].iloc[-1] = new_row.iloc[0]
            else:
                self.candle_buffers[symbol] = pd.concat(
                    [buf, new_row], ignore_index=True
                ).tail(200)

        return self.detect_signals(symbol)

    def detect_signals(self, symbol: str) -> list[Signal]:
        df = self.candle_buffers.get(symbol)
        if df is None or len(df) < 30:
            return []

        signals = []

        # ── RSI calculations on log prices ──
        log_high = np.log(df["high"])
        log_low = np.log(df["low"])
        log_close = np.log(df["close"])

        rsi_high = compute_rsi(log_high, config.RSI_PERIOD)
        rsi_low = compute_rsi(log_low, config.RSI_PERIOD)
        rsi_close = compute_rsi(log_close, config.RSI_PERIOD)

        rsi_change_high = rsi_high.diff()
        rsi_change_low = rsi_low.diff()
        rsi_change_close = rsi_close.diff()

        # ── Buy momentum ──
        raw_momentum = np.where(
            df["close"] > df["low"],
            np.log(df["volume"] + 1) * ((df["close"] - df["low"]) / df["low"]),
            0.0,
        )

        # ── RSI-based signals ──
        c20l = crossover(rsi_change_close, 20)
        c10l = crossover(rsi_change_close, 10)
        l20l = crossover(rsi_change_low, 20)
        c20s = crossunder(rsi_change_close, -20)
        c10s = crossunder(rsi_change_close, -10)
        l20s = crossunder(rsi_change_low, -20)

        # ── MACD-based signals ──
        fast_ma = df["close"].ewm(span=config.MACD_FAST, adjust=False).mean()
        slow_ma = df["close"].ewm(span=config.MACD_SLOW, adjust=False).mean()
        macd_raw = fast_ma - slow_ma
        macd_rsi = compute_rsi(macd_raw, 100)
        macd = macd_rsi.diff()
        signal_line_raw = macd.ewm(span=config.MACD_SIGNAL, adjust=False).mean()
        signal_rsi = compute_rsi(signal_line_raw, 100)
        signal_val = signal_rsi.diff()
        top = (macd + signal_val) / 2

        macd_long = {
            "M2L": 2,
            "M3L": 3,
            "M4L": 4,
            "M5L": 5,
        }
        macd_short = {
            "M2S": -2,
            "M3S": -3,
            "M4S": -4,
            "M5S": -5,
        }

        # Check last candle only
        idx = len(df) - 1
        last = df.iloc[idx]
        mom = raw_momentum[idx] if idx < len(raw_momentum) else 0

        def make_signal(sig_type: str, direction: str) -> Signal:
            return Signal(
                symbol=symbol,
                signal_type=sig_type,
                direction=direction,
                candle_high=float(last["high"]),
                candle_low=float(last["low"]),
                candle_close=float(last["close"]),
                candle_volume=float(last["volume"]),
                buy_momentum=float(mom),
                timestamp=float(last["timestamp"]),
            )

        # C10L / C20L with momentum filter
        if idx < len(c10l) and c10l.iloc[idx] and mom >= config.MIN_MOMENTUM:
            signals.append(make_signal("C10L", "long"))

        if idx < len(c20l) and c20l.iloc[idx] and mom >= config.MIN_MOMENTUM:
            signals.append(make_signal("C20L", "long"))

        if idx < len(l20l) and l20l.iloc[idx]:
            signals.append(make_signal("L20L", "long"))

        # Short signals (no momentum filter)
        if idx < len(c20s) and c20s.iloc[idx]:
            signals.append(make_signal("C20S", "short"))
        if idx < len(c10s) and c10s.iloc[idx]:
            signals.append(make_signal("C10S", "short"))
        if idx < len(l20s) and l20s.iloc[idx]:
            signals.append(make_signal("L20S", "short"))

        # MACD longs
        for sig_name, threshold in macd_long.items():
            if idx < len(macd):
                co_macd = crossover(macd, threshold)
                co_sig = crossover(signal_val, threshold)
                co_top = crossover(top, threshold)
                if (
                    (idx < len(co_macd) and co_macd.iloc[idx])
                    or (idx < len(co_sig) and co_sig.iloc[idx])
                    or (idx < len(co_top) and co_top.iloc[idx])
                ):
                    signals.append(make_signal(sig_name, "long"))

        # MACD shorts
        for sig_name, threshold in macd_short.items():
            if idx < len(macd):
                cu_macd = crossunder(macd, threshold)
                cu_sig = crossunder(signal_val, threshold)
                cu_top = crossunder(top, threshold)
                if (
                    (idx < len(cu_macd) and cu_macd.iloc[idx])
                    or (idx < len(cu_sig) and cu_sig.iloc[idx])
                    or (idx < len(cu_top) and cu_top.iloc[idx])
                ):
                    signals.append(make_signal(sig_name, "short"))

        for sig in signals:
            logger.info(f"Signal detected: {sig.signal_type} on {symbol} mom={mom:.2f}")

        return signals
