"""
NEXUS OVERLAY AI - Indicator Engine
Technical indicator computation using pure Python math (no numpy/pandas).
Computes EMA, SMA, RSI, MACD, ROC, ATR, ATR%, Bollinger Bands, ADX+DI,
tick volume, relative volume, and volume expansion/contraction.
"""
from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from typing import Optional

from backend.models import CandleData, IndicatorValue, now_ms
from backend.event_bus import EventType, EventBus

logger = logging.getLogger(__name__)


class IndicatorEngine:
    """
    Pure-Python technical indicator engine.

    Each public method returns an ``IndicatorValue`` with structured output
    and is deterministic given the same candle window.
    """

    def __init__(self, config: dict, event_bus: EventBus):
        self._config = config
        self._bus = event_bus

        # Pull indicator config
        ind_cfg = config.get("indicators", {})
        trend_cfg = ind_cfg.get("trend", {})
        mom_cfg = ind_cfg.get("momentum", {})
        vol_cfg = ind_cfg.get("volatility", {})
        strength_cfg = ind_cfg.get("trend_strength", {})
        volume_cfg = ind_cfg.get("volume", {})

        # Trend
        self.ema_periods: list[int] = trend_cfg.get("ema_periods", [20, 50, 100, 200])
        self.sma_periods: list[int] = trend_cfg.get("sma_periods", [50, 200])

        # Momentum
        self.rsi_period: int = mom_cfg.get("rsi_period", 14)
        self.rsi_oversold: float = mom_cfg.get("rsi_oversold", 30.0)
        self.rsi_overbought: float = mom_cfg.get("rsi_overbought", 70.0)
        self.macd_fast: int = mom_cfg.get("macd_fast", 12)
        self.macd_slow: int = mom_cfg.get("macd_slow", 26)
        self.macd_signal: int = mom_cfg.get("macd_signal", 9)
        self.roc_period: int = mom_cfg.get("roc_period", 10)

        # Volatility
        self.atr_period: int = vol_cfg.get("atr_period", 14)
        self.bb_period: int = vol_cfg.get("bb_period", 20)
        self.bb_std: float = vol_cfg.get("bb_std", 2.0)

        # ADX
        self.adx_period: int = strength_cfg.get("adx_period", 14)
        self.adx_strong: float = strength_cfg.get("adx_strong", 25.0)
        self.adx_weak: float = strength_cfg.get("adx_weak", 20.0)

        # Volume
        self.vol_ma_period: int = volume_cfg.get("volume_ma_period", 20)
        self.expansion_threshold: float = volume_cfg.get("expansion_threshold", 1.5)

        logger.info("IndicatorEngine initialised")

    # ── Lifecycle ─────────────────────────────────────────────────────────
    async def start(self) -> None:
        logger.info("IndicatorEngine started")

    async def stop(self) -> None:
        logger.info("IndicatorEngine stopped")

    # ── EMA ───────────────────────────────────────────────────────────────
    def compute_ema(self, candles: list[CandleData], period: int) -> Optional[IndicatorValue]:
        """
        Exponential Moving Average of close prices.

        Formula:
            EMA_t = close_t * k + EMA_{t-1} * (1 - k)
            where k = 2 / (period + 1)

        Returns the latest EMA value or None if insufficient data.
        """
        if len(candles) < period:
            return None

        closes = [c.close for c in candles]
        k = 2.0 / (period + 1)

        # Seed with SMA of first 'period' closes
        sma_seed = sum(closes[:period]) / period
        ema = sma_seed
        for price in closes[period:]:
            ema = price * k + ema * (1.0 - k)

        # Determine state relative to current price
        current_price = closes[-1]
        if current_price > ema:
            state = "ABOVE"
        elif current_price < ema:
            state = "BELOW"
        else:
            state = "AT"

        iv = IndicatorValue(
            indicator=f"EMA_{period}",
            timeframe=candles[-1].timeframe,
            value=round(ema, 6),
            state=state,
            timestamp=candles[-1].timestamp,
            auxiliary={"price": current_price, "distance": round(current_price - ema, 6)},
        )

        asyncio.get_event_loop().call_soon(
            lambda: asyncio.ensure_future(
                self._bus.publish(
                    EventType.INDICATOR_UPDATED,
                    source="indicator_engine",
                    payload={"indicator": iv.indicator, "value": iv.value, "state": iv.state},
                )
            )
        )

        return iv

    # ── SMA ───────────────────────────────────────────────────────────────
    def compute_sma(self, candles: list[CandleData], period: int) -> Optional[IndicatorValue]:
        """
        Simple Moving Average of close prices.

        SMA = (sum of last N closes) / N
        """
        if len(candles) < period:
            return None

        closes = [c.close for c in candles]
        sma = sum(closes[-period:]) / period

        current_price = closes[-1]
        state = "ABOVE" if current_price > sma else ("BELOW" if current_price < sma else "AT")

        return IndicatorValue(
            indicator=f"SMA_{period}",
            timeframe=candles[-1].timeframe,
            value=round(sma, 6),
            state=state,
            timestamp=candles[-1].timestamp,
            auxiliary={"price": current_price, "distance": round(current_price - sma, 6)},
        )

    # ── RSI ───────────────────────────────────────────────────────────────
    def compute_rsi(self, candles: list[CandleData]) -> Optional[IndicatorValue]:
        """
        Relative Strength Index (Wilder's smoothing).

        RSI = 100 - (100 / (1 + RS))
        RS  = avg_gain / avg_loss   (exponentially smoothed)
        """
        period = self.rsi_period
        if len(candles) < period + 1:
            return None

        closes = [c.close for c in candles]

        # Initial gains/losses
        gains = []
        losses = []
        for i in range(1, len(closes)):
            diff = closes[i] - closes[i - 1]
            gains.append(max(diff, 0.0))
            losses.append(max(-diff, 0.0))

        if len(gains) < period:
            return None

        avg_gain = sum(gains[:period]) / period
        avg_loss = sum(losses[:period]) / period

        # Wilder's smoothing
        for i in range(period, len(gains)):
            avg_gain = (avg_gain * (period - 1) + gains[i]) / period
            avg_loss = (avg_loss * (period - 1) + losses[i]) / period

        if avg_loss == 0:
            rsi = 100.0
        else:
            rs = avg_gain / avg_loss
            rsi = 100.0 - (100.0 / (1.0 + rs))

        # Determine state
        if rsi <= self.rsi_oversold:
            state = "OVERSOLD"
        elif rsi >= self.rsi_overbought:
            state = "OVERBOUGHT"
        elif rsi < 45:
            state = "BEARISH"
        elif rsi > 55:
            state = "BULLISH"
        else:
            state = "NEUTRAL"

        return IndicatorValue(
            indicator="RSI",
            timeframe=candles[-1].timeframe,
            value=round(rsi, 2),
            state=state,
            timestamp=candles[-1].timestamp,
            auxiliary={
                "period": period,
                "oversold": self.rsi_oversold,
                "overbought": self.rsi_overbought,
            },
        )

    # ── MACD ──────────────────────────────────────────────────────────────
    def compute_macd(self, candles: list[CandleData]) -> Optional[IndicatorValue]:
        """
        MACD (Moving Average Convergence Divergence).

        MACD_line  = EMA(fast) - EMA(slow)
        Signal     = EMA(MACD_line, signal_period)
        Histogram  = MACD_line - Signal
        """
        min_needed = self.macd_slow + self.macd_signal
        if len(candles) < min_needed:
            return None

        closes = [c.close for c in candles]

        fast_ema = self._ema_series(closes, self.macd_fast)
        slow_ema = self._ema_series(closes, self.macd_slow)

        # Align: slow EMA starts later
        offset = self.macd_slow - self.macd_fast
        macd_line = [f - s for f, s in zip(fast_ema[offset:], slow_ema)]

        if len(macd_line) < self.macd_signal:
            return None

        signal_line = self._ema_series(macd_line, self.macd_signal)
        if not signal_line:
            return None

        macd_val = macd_line[-1]
        sig_val = signal_line[-1]
        hist = macd_val - sig_val

        # Determine state
        if macd_val > 0 and hist > 0:
            state = "BULLISH_MOMENTUM"
        elif macd_val > 0 and hist < 0:
            state = "BULLISH_FADING"
        elif macd_val < 0 and hist < 0:
            state = "BEARISH_MOMENTUM"
        elif macd_val < 0 and hist > 0:
            state = "BEARISH_FADING"
        else:
            state = "NEUTRAL"

        return IndicatorValue(
            indicator="MACD",
            timeframe=candles[-1].timeframe,
            value=round(macd_val, 6),
            state=state,
            timestamp=candles[-1].timestamp,
            auxiliary={
                "macd_line": round(macd_val, 6),
                "signal_line": round(sig_val, 6),
                "histogram": round(hist, 6),
                "fast_period": self.macd_fast,
                "slow_period": self.macd_slow,
                "signal_period": self.macd_signal,
            },
        )

    # ── ROC ───────────────────────────────────────────────────────────────
    def compute_roc(self, candles: list[CandleData]) -> Optional[IndicatorValue]:
        """
        Rate of Change (percentage).

        ROC = ((close - close_n_periods_ago) / close_n_periods_ago) * 100
        """
        period = self.roc_period
        if len(candles) < period + 1:
            return None

        closes = [c.close for c in candles]
        current = closes[-1]
        past = closes[-(period + 1)]

        if past == 0:
            return None

        roc = ((current - past) / past) * 100.0

        state = "BULLISH" if roc > 0 else ("BEARISH" if roc < 0 else "NEUTRAL")

        return IndicatorValue(
            indicator="ROC",
            timeframe=candles[-1].timeframe,
            value=round(roc, 4),
            state=state,
            timestamp=candles[-1].timestamp,
            auxiliary={"period": period, "past_close": past, "current_close": current},
        )

    # ── ATR ───────────────────────────────────────────────────────────────
    def compute_atr(self, candles: list[CandleData]) -> Optional[IndicatorValue]:
        """
        Average True Range (Wilder's smoothing).

        TR = max(H-L, |H-C_prev|, |L-C_prev|)
        ATR = smoothed average of TR
        """
        period = self.atr_period
        if len(candles) < period + 1:
            return None

        trs = self._true_ranges(candles)

        # Initial ATR = simple average of first 'period' TRs
        atr = sum(trs[:period]) / period

        # Smooth remaining
        for i in range(period, len(trs)):
            atr = (atr * (period - 1) + trs[i]) / period

        # ATR as percentage of price
        price = candles[-1].close
        atr_pct = (atr / price * 100.0) if price > 0 else 0.0

        # State: normal vs elevated vs low volatility
        if atr_pct > 1.5:
            state = "HIGH_VOLATILITY"
        elif atr_pct > 0.8:
            state = "ELEVATED"
        elif atr_pct > 0.3:
            state = "NORMAL"
        else:
            state = "LOW_VOLATILITY"

        return IndicatorValue(
            indicator="ATR",
            timeframe=candles[-1].timeframe,
            value=round(atr, 6),
            state=state,
            timestamp=candles[-1].timestamp,
            auxiliary={
                "atr_pct": round(atr_pct, 4),
                "period": period,
                "price": price,
            },
        )

    # ── ATR% ──────────────────────────────────────────────────────────────
    def compute_atr_pct(self, candles: list[CandleData]) -> Optional[IndicatorValue]:
        """ATR as a percentage of the current close price."""
        atr_iv = self.compute_atr(candles)
        if atr_iv is None:
            return None

        price = candles[-1].close
        atr_pct = (atr_iv.value / price * 100.0) if price > 0 else 0.0

        return IndicatorValue(
            indicator="ATR_PCT",
            timeframe=candles[-1].timeframe,
            value=round(atr_pct, 4),
            state=atr_iv.state,
            timestamp=candles[-1].timestamp,
            auxiliary={"atr": atr_iv.value, "price": price},
        )

    # ── Bollinger Bands ───────────────────────────────────────────────────
    def compute_bollinger_bands(self, candles: list[CandleData]) -> Optional[IndicatorValue]:
        """
        Bollinger Bands.

        Middle = SMA(close, period)
        Upper  = Middle + std_dev * deviation
        Lower  = Middle - std_dev * deviation
        Width  = (Upper - Lower) / Middle  (bandwidth)
        %B     = (close - Lower) / (Upper - Lower)
        """
        period = self.bb_period
        if len(candles) < period:
            return None

        closes = [c.close for c in candles]
        window = closes[-period:]

        middle = sum(window) / period
        variance = sum((x - middle) ** 2 for x in window) / period
        std_dev = math.sqrt(variance)

        upper = middle + self.bb_std * std_dev
        lower = middle - self.bb_std * std_dev
        price = closes[-1]

        bandwidth = (upper - lower) / middle if middle != 0 else 0.0
        pct_b = (price - lower) / (upper - lower) if (upper - lower) != 0 else 0.5

        # State
        if price >= upper:
            state = "ABOVE_UPPER"
        elif price <= lower:
            state = "BELOW_LOWER"
        elif pct_b > 0.8:
            state = "NEAR_UPPER"
        elif pct_b < 0.2:
            state = "NEAR_LOWER"
        else:
            state = "INSIDE"

        return IndicatorValue(
            indicator="BB",
            timeframe=candles[-1].timeframe,
            value=round(middle, 6),
            state=state,
            timestamp=candles[-1].timestamp,
            auxiliary={
                "upper": round(upper, 6),
                "lower": round(lower, 6),
                "middle": round(middle, 6),
                "bandwidth": round(bandwidth, 6),
                "pct_b": round(pct_b, 4),
                "std_dev": round(std_dev, 6),
            },
        )

    # ── ADX + DI+/DI- ────────────────────────────────────────────────────
    def compute_adx(self, candles: list[CandleData]) -> Optional[IndicatorValue]:
        """
        Average Directional Index with +DI and -DI.

        +DM = H - H_prev  (if > 0 and > -DM)
        -DM = L_prev - L  (if > 0 and > +DM)
        TR  = max(H-L, |H-C_prev|, |L-C_prev|)

        +DI = 100 * smoothed(+DM) / smoothed(TR)
        -DI = 100 * smoothed(-DM) / smoothed(TR)
        DX  = 100 * |+DI - -DI| / (+DI + -DI)
        ADX = smoothed(DX)
        """
        period = self.adx_period
        if len(candles) < period * 2:
            return None

        highs = [c.high for c in candles]
        lows = [c.low for c in candles]
        closes = [c.close for c in candles]

        plus_dm = []
        minus_dm = []
        trs = []

        for i in range(1, len(candles)):
            up_move = highs[i] - highs[i - 1]
            down_move = lows[i - 1] - lows[i]

            pdm = up_move if (up_move > down_move and up_move > 0) else 0.0
            mdm = down_move if (down_move > up_move and down_move > 0) else 0.0

            plus_dm.append(pdm)
            minus_dm.append(mdm)

            # True range
            tr = max(
                highs[i] - lows[i],
                abs(highs[i] - closes[i - 1]),
                abs(lows[i] - closes[i - 1]),
            )
            trs.append(tr)

        if len(trs) < period:
            return None

        # Wilder's smoothing for DM and TR
        sm_plus_dm = sum(plus_dm[:period]) / period
        sm_minus_dm = sum(minus_dm[:period]) / period
        sm_tr = sum(trs[:period]) / period

        dx_values = []

        for i in range(period, len(trs)):
            sm_plus_dm = (sm_plus_dm * (period - 1) + plus_dm[i]) / period
            sm_minus_dm = (sm_minus_dm * (period - 1) + minus_dm[i]) / period
            sm_tr = (sm_tr * (period - 1) + trs[i]) / period

            if sm_tr == 0:
                plus_di = 0.0
                minus_di = 0.0
            else:
                plus_di = 100.0 * sm_plus_dm / sm_tr
                minus_di = 100.0 * sm_minus_dm / sm_tr

            di_sum = plus_di + minus_di
            if di_sum == 0:
                dx_values.append(0.0)
            else:
                dx_values.append(100.0 * abs(plus_di - minus_di) / di_sum)

        if not dx_values:
            return None

        # ADX = EMA-smoothed DX (Wilder)
        adx = sum(dx_values[:period]) / period
        for dx in dx_values[period:]:
            adx = (adx * (period - 1) + dx) / period

        # Re-compute final DI values for state
        if sm_tr > 0:
            final_plus_di = 100.0 * sm_plus_dm / sm_tr
            final_minus_di = 100.0 * sm_minus_dm / sm_tr
        else:
            final_plus_di = 0.0
            final_minus_di = 0.0

        # Determine state
        if adx >= self.adx_strong:
            if final_plus_di > final_minus_di:
                state = "STRONG_BULLISH"
            else:
                state = "STRONG_BEARISH"
        elif adx >= self.adx_weak:
            if final_plus_di > final_minus_di:
                state = "MODERATE_BULLISH"
            else:
                state = "MODERATE_BEARISH"
        else:
            state = "WEAK_TREND"

        return IndicatorValue(
            indicator="ADX",
            timeframe=candles[-1].timeframe,
            value=round(adx, 2),
            state=state,
            timestamp=candles[-1].timestamp,
            auxiliary={
                "plus_di": round(final_plus_di, 2),
                "minus_di": round(final_minus_di, 2),
                "adx_strong": self.adx_strong,
                "adx_weak": self.adx_weak,
            },
        )

    # ── Volume analysis ───────────────────────────────────────────────────
    def compute_volume(self, candles: list[CandleData]) -> Optional[IndicatorValue]:
        """
        Tick volume with moving average, relative volume, and
        expansion/contraction detection.
        """
        period = self.vol_ma_period
        if len(candles) < period:
            return None

        volumes = [c.volume for c in candles]
        current_vol = volumes[-1]
        vol_ma = sum(volumes[-period:]) / period

        relative_vol = current_vol / vol_ma if vol_ma > 0 else 1.0

        # Expansion / contraction
        if relative_vol >= self.expansion_threshold:
            state = "EXPANSION"
        elif relative_vol >= self.expansion_threshold * 0.7:
            state = "ABOVE_AVERAGE"
        elif relative_vol <= 0.5:
            state = "CONTRACTION"
        elif relative_vol <= 0.75:
            state = "BELOW_AVERAGE"
        else:
            state = "NORMAL"

        return IndicatorValue(
            indicator="VOLUME",
            timeframe=candles[-1].timeframe,
            value=round(relative_vol, 4),
            state=state,
            timestamp=candles[-1].timestamp,
            auxiliary={
                "current_volume": current_vol,
                "volume_ma": round(vol_ma, 1),
                "relative_volume": round(relative_vol, 4),
                "expansion_threshold": self.expansion_threshold,
            },
        )

    # ── Compute all indicators for a timeframe ────────────────────────────
    async def compute_all(self, candles: list[CandleData]) -> dict[str, IndicatorValue]:
        """
        Compute every configured indicator for the given candle window.
        Returns a dict keyed by indicator name.
        """
        results: dict[str, IndicatorValue] = {}

        # EMAs
        for period in self.ema_periods:
            iv = self.compute_ema(candles, period)
            if iv:
                results[iv.indicator] = iv

        # SMAs
        for period in self.sma_periods:
            iv = self.compute_sma(candles, period)
            if iv:
                results[iv.indicator] = iv

        # RSI
        iv = self.compute_rsi(candles)
        if iv:
            results[iv.indicator] = iv

        # MACD
        iv = self.compute_macd(candles)
        if iv:
            results[iv.indicator] = iv

        # ROC
        iv = self.compute_roc(candles)
        if iv:
            results[iv.indicator] = iv

        # ATR
        iv = self.compute_atr(candles)
        if iv:
            results[iv.indicator] = iv

        # ATR%
        iv = self.compute_atr_pct(candles)
        if iv:
            results[iv.indicator] = iv

        # Bollinger Bands
        iv = self.compute_bollinger_bands(candles)
        if iv:
            results[iv.indicator] = iv

        # ADX
        iv = self.compute_adx(candles)
        if iv:
            results[iv.indicator] = iv

        # Volume
        iv = self.compute_volume(candles)
        if iv:
            results[iv.indicator] = iv

        # Publish bulk update event
        await self._bus.publish(
            EventType.INDICATOR_UPDATED,
            source="indicator_engine",
            payload={
                "count": len(results),
                "indicators": list(results.keys()),
            },
        )

        return results

    # ── Internal helpers ──────────────────────────────────────────────────
    @staticmethod
    def _ema_series(data: list[float], period: int) -> list[float]:
        """Compute full EMA series from a list of floats."""
        if len(data) < period:
            return []

        k = 2.0 / (period + 1)
        sma_seed = sum(data[:period]) / period
        ema_values = [sma_seed]
        for val in data[period:]:
            ema_values.append(val * k + ema_values[-1] * (1.0 - k))
        return ema_values

    @staticmethod
    def _true_ranges(candles: list[CandleData]) -> list[float]:
        """Compute True Range series from candles."""
        trs = []
        for i in range(len(candles)):
            if i == 0:
                trs.append(candles[i].high - candles[i].low)
            else:
                h = candles[i].high
                l = candles[i].low
                pc = candles[i - 1].close
                trs.append(max(h - l, abs(h - pc), abs(l - pc)))
        return trs
