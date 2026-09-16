"""
NEXUS OVERLAY AI - Market Data Engine
Normalized market data layer with rolling candle windows, tick processing,
candle construction, timeframe aggregation, and data quality monitoring.
"""
from __future__ import annotations

import asyncio
import logging
import time
import math
from collections import defaultdict, deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

from backend.models import (
    CandleData, TickData, SymbolInfo, now_ms
)
from backend.event_bus import EventType, EventBus

logger = logging.getLogger(__name__)

# ── Timeframe definitions (seconds) ──────────────────────────────────────────
TIMEFRAME_SECONDS: dict[str, int] = {
    "M1": 60,
    "M3": 180,
    "M5": 300,
    "M15": 900,
    "M30": 1800,
    "H1": 3600,
    "H4": 14400,
    "D1": 86400,
}

# Aggregation chain: which higher timeframe a lower one feeds into
AGGREGATION_CHAIN: dict[str, str] = {
    "M1": "M5",
    "M3": "M15",
    "M5": "M15",
    "M15": "H1",
    "M30": "H1",
    "H1": "H4",
    "H4": "D1",
}

# Default rolling candle window sizes per timeframe
DEFAULT_CANDLE_HISTORY: dict[str, int] = {
    "M1": 2000,
    "M3": 1500,
    "M5": 1500,
    "M15": 1000,
    "M30": 500,
    "H1": 500,
    "H4": 300,
    "D1": 200,
}

# Outlier detection thresholds (multipplier of median ATR)
OUTLIER_ATR_MULTIPLIER = 5.0
MAX_SPREAD_PIPS = 50.0  # absolute sanity check


@dataclass
class DataQualityReport:
    """Data quality assessment."""
    score: float  # 0-100
    missing_candles: int
    duplicate_candles: int
    outliers_detected: int
    spread_violations: int
    staleness_ms: int
    is_fresh: bool
    timestamp: int = field(default_factory=now_ms)


@dataclass
class TickBuffer:
    """Buffer of ticks for a single candle period."""
    open: float = 0.0
    high: float = 0.0
    low: float = 0.0
    close: float = 0.0
    volume: int = 0
    spread_sum: float = 0.0
    tick_count: int = 0
    start_time: int = 0
    end_time: int = 0


class MarketDataEngine:
    """
    Normalized market data layer.

    Manages rolling candle windows per timeframe, constructs candles from ticks,
    aggregates lower timeframes into higher ones, detects data quality issues,
    and emits CANDLE_CLOSED / MARKET_TICK events via the event bus.
    """

    def __init__(self, config: dict, event_bus: EventBus):
        self._config = config
        self._bus = event_bus

        # Per-timeframe candle windows: timeframe -> deque of CandleData
        history_cfg = config.get("candle_history", DEFAULT_CANDLE_HISTORY)
        self._candle_windows: dict[str, deque[CandleData]] = {}
        for tf in TIMEFRAME_SECONDS:
            max_len = history_cfg.get(tf, DEFAULT_CANDLE_HISTORY.get(tf, 500))
            self._candle_windows[tf] = deque(maxlen=max_len)

        # Active (incomplete) candle buffers per timeframe
        self._active_candles: dict[str, TickBuffer] = {}

        # Tick-level buffers for constructing M1 candles
        self._tick_buffer: dict[str, list[TickData]] = defaultdict(list)

        # Tracking for data quality
        self._last_tick_time: dict[str, int] = {}
        self._last_candle_time: dict[str, int] = {}
        self._duplicate_count: int = 0
        self._outlier_count: int = 0
        self._missing_candle_count: int = 0
        self._spread_violations: int = 0

        # Symbol info cache
        self._symbol_info: Optional[SymbolInfo] = None

        # Dirty flags so downstream engines know what to recompute
        self._dirty_timeframes: set[str] = set()

        logger.info("MarketDataEngine initialised")

    # ── Lifecycle ─────────────────────────────────────────────────────────
    async def start(self) -> None:
        """Start the engine; subscribe to tick events if needed."""
        logger.info("MarketDataEngine started")

    async def stop(self) -> None:
        """Graceful shutdown."""
        logger.info("MarketDataEngine stopped")

    # ── Symbol info ───────────────────────────────────────────────────────
    def set_symbol_info(self, info: SymbolInfo) -> None:
        """Cache symbol contract specification."""
        self._symbol_info = info
        logger.info(f"Symbol info set for {info.name}")

    # ── Tick ingestion ────────────────────────────────────────────────────
    async def on_tick(self, tick: TickData) -> None:
        """
        Process an incoming tick. Normalises, validates, appends to
        the M1 tick buffer, and publishes a MARKET_TICK event.
        """
        ts = tick.timestamp

        # Normalise: ensure mid price is valid
        mid = (tick.bid + tick.ask) / 2.0
        if mid <= 0:
            logger.warning(f"Invalid tick price: bid={tick.bid} ask={tick.ask}")
            return

        # Spread monitoring
        spread = tick.ask - tick.bid
        self._spread_violations += 1 if spread > MAX_SPREAD_PIPS else 0

        # Update last-tick tracker for all timeframes
        self._last_tick_time["M1"] = ts

        # Determine which M1 candle this tick belongs to
        candle_ts = self._floor_timestamp(ts, 60)  # M1 = 60 s

        # Append to tick buffer
        self._tick_buffer["M1"].append(tick)

        # Publish MARKET_TICK
        await self._bus.publish(
            EventType.MARKET_TICK,
            source="market_data_engine",
            payload={
                "tick": tick,
                "mid": mid,
                "spread": spread,
            },
        )

        # Check if the M1 candle boundary has been crossed → close the candle
        if len(self._tick_buffer["M1"]) > 0:
            first_ts = self._tick_buffer["M1"][0].timestamp
            first_candle_ts = self._floor_timestamp(first_ts, 60)
            if candle_ts > first_candle_ts:
                # The candle has closed
                await self._close_candle_from_ticks("M1", first_candle_ts)

    # ── Candle ingestion (direct from MT5) ────────────────────────────────
    async def on_candle(self, candle: CandleData) -> None:
        """
        Process a closed candle directly from the transport layer.
        Validates, deduplicates, checks for outliers, and cascades into
        higher timeframes via aggregation.
        """
        tf = candle.timeframe
        ts = candle.timestamp

        if tf not in self._candle_windows:
            logger.warning(f"Unknown timeframe: {tf}")
            return

        # Duplicate detection
        if self._is_duplicate(tf, ts):
            self._duplicate_count += 1
            logger.debug(f"Duplicate candle ignored: {tf} ts={ts}")
            return

        # Outlier detection
        if self._is_outlier(tf, candle):
            self._outlier_count += 1
            logger.warning(f"Outlier candle detected: {tf} ts={ts} "
                           f"range={candle.high - candle.low:.4f}")

        # Store
        self._candle_windows[tf].append(candle)
        self._last_candle_time[tf] = ts
        self._dirty_timeframes.add(tf)

        # Missing candle detection
        self._detect_missing_candles(tf, ts)

        # Publish CANDLE_CLOSED
        await self._bus.publish(
            EventType.CANDLE_CLOSED,
            source="market_data_engine",
            payload={
                "candle": candle,
                "timeframe": tf,
            },
        )

        # Aggregate into higher timeframe
        higher = AGGREGATION_CHAIN.get(tf)
        if higher:
            await self._aggregate_into(higher)

    # ── Candle construction from M1 ticks ─────────────────────────────────
    async def _close_candle_from_ticks(self, tf: str, candle_ts: int) -> None:
        """Build a CandleData from accumulated ticks and close it."""
        ticks = self._tick_buffer.get(tf, [])
        if not ticks:
            return

        candle = self._build_candle_from_ticks(ticks, tf, candle_ts)

        # Clear tick buffer
        self._tick_buffer[tf] = []

        if candle:
            await self.on_candle(candle)

    def _build_candle_from_ticks(
        self, ticks: list[TickData], tf: str, candle_ts: int
    ) -> Optional[CandleData]:
        """Construct OHLCV from a list of ticks."""
        if not ticks:
            return None

        bids = [t.bid for t in ticks]
        asks = [t.ask for t in ticks]
        mids = [(b + a) / 2.0 for b, a in zip(bids, asks)]

        o = mids[0]
        h = max(mids)
        l = min(mids)
        c = mids[-1]
        vol = sum(t.volume for t in ticks)
        avg_spread = sum(t.ask - t.bid for t in ticks) / len(ticks)

        return CandleData(
            open=o, high=h, low=l, close=c,
            volume=vol, spread=avg_spread,
            timestamp=candle_ts, timeframe=tf, complete=True,
        )

    # ── Timeframe aggregation ─────────────────────────────────────────────
    async def _aggregate_into(self, target_tf: str) -> None:
        """
        Rebuild the most recent candle of *target_tf* by aggregating
        its constituent lower-timeframe candles.
        """
        target_secs = TIMEFRAME_SECONDS.get(target_tf)
        if target_secs is None:
            return

        # Find the source timeframes that feed into target_tf
        sources = [src for src, dst in AGGREGATION_CHAIN.items()
                   if dst == target_tf]

        if not sources:
            return

        # Collect all constituent candles from the lowest source(s)
        # For simplicity, aggregate from the direct sub-timeframe
        for src_tf in sources:
            src_candles = self._candle_windows.get(src_tf, [])
            if not src_candles:
                continue

            target_ts = self._floor_timestamp(
                src_candles[-1].timestamp, target_secs
            )

            # Gather all source candles in this target period
            constituent = [
                c for c in src_candles
                if self._floor_timestamp(c.timestamp, target_secs) == target_ts
            ]

            if not constituent:
                continue

            aggregated = self._aggregate_candles(constituent, target_tf, target_ts)

            # Replace or append in target window
            existing = self._candle_windows[target_tf]
            if existing and existing[-1].timestamp == target_ts:
                existing[-1] = aggregated  # update in place
            else:
                if existing:
                    # Remove stale target candles
                    while existing and existing[-1].timestamp >= target_ts:
                        existing.pop()
                existing.append(aggregated)

            self._dirty_timeframes.add(target_tf)
            self._last_candle_time[target_tf] = target_ts

            # If the target candle is complete (next period started), emit
            now_ts = int(time.time() * 1000)
            if now_ts > target_ts + target_secs * 1000:
                await self._bus.publish(
                    EventType.CANDLE_CLOSED,
                    source="market_data_engine",
                    payload={
                        "candle": aggregated,
                        "timeframe": target_tf,
                    },
                )

            break  # use first matching source

    def _aggregate_candles(
        self, candles: list[CandleData], tf: str, timestamp: int
    ) -> CandleData:
        """Merge a list of candles into one aggregated candle."""
        if not candles:
            return CandleData(
                open=0, high=0, low=0, close=0,
                volume=0, spread=0, timestamp=timestamp,
                timeframe=tf, complete=True,
            )

        o = candles[0].open
        h = max(c.high for c in candles)
        l = min(c.low for c in candles)
        c = candles[-1].close
        vol = sum(candle.volume for candle in candles)
        avg_spread = sum(candle.spread for candle in candles) / len(candles)

        return CandleData(
            open=o, high=h, low=l, close=c,
            volume=vol, spread=avg_spread,
            timestamp=timestamp, timeframe=tf, complete=True,
        )

    # ── Deduplication ─────────────────────────────────────────────────────
    def _is_duplicate(self, tf: str, ts: int) -> bool:
        """Check if candle with this timestamp already exists."""
        candles = self._candle_windows.get(tf)
        if not candles:
            return False
        return any(c.timestamp == ts for c in list(candles)[-5:])

    # ── Outlier detection ─────────────────────────────────────────────────
    def _is_outlier(self, tf: str, candle: CandleData) -> bool:
        """Detect outlier candles via ATR-based range check."""
        candles = self._candle_windows.get(tf, [])
        if len(candles) < 20:
            return False

        # Compute median true range over last 20 candles
        trs = []
        recent = list(candles)[-20:]
        for i in range(len(recent)):
            curr = recent[i]
            if i == 0:
                trs.append(curr.high - curr.low)
            else:
                prev_close = recent[i - 1].close
                tr = max(
                    curr.high - curr.low,
                    abs(curr.high - prev_close),
                    abs(curr.low - prev_close),
                )
                trs.append(tr)

        trs_sorted = sorted(trs)
        median_tr = trs_sorted[len(trs_sorted) // 2]

        candle_range = candle.high - candle.low
        return candle_range > median_tr * OUTLIER_ATR_MULTIPLIER

    # ── Missing candle detection ──────────────────────────────────────────
    def _detect_missing_candles(self, tf: str, new_ts: int) -> None:
        """Check for gaps between the last stored candle and the new one."""
        candles = self._candle_windows.get(tf, [])
        if len(candles) < 2:
            return

        prev_ts = candles[-2].timestamp  # the one before the just-appended
        expected_interval = TIMEFRAME_SECONDS.get(tf, 60) * 1000
        gap = new_ts - prev_ts

        if gap > expected_interval * 1.5:
            missing = int(gap / expected_interval) - 1
            self._missing_candle_count += missing
            logger.warning(
                f"Missing {missing} candle(s) in {tf}: "
                f"gap={gap}ms expected={expected_interval}ms"
            )

    # ── Data freshness ────────────────────────────────────────────────────
    def is_data_fresh(self, timeframe: str = "M1", max_staleness_ms: int = 10000) -> bool:
        """Return True if the most recent candle for timeframe is within staleness limit."""
        last_ts = self._last_candle_time.get(timeframe, 0)
        if last_ts == 0:
            return False
        now = now_ms()
        return (now - last_ts) <= max_staleness_ms

    # ── Public getters ────────────────────────────────────────────────────
    def get_candles(self, timeframe: str, count: Optional[int] = None) -> list[CandleData]:
        """Return the last N candles for a timeframe (newest last)."""
        candles = list(self._candle_windows.get(timeframe, []))
        if count is not None:
            return candles[-count:]
        return candles

    def get_latest_candle(self, timeframe: str) -> Optional[CandleData]:
        """Return the most recent closed candle for a timeframe."""
        candles = self._candle_windows.get(timeframe, [])
        return candles[-1] if candles else None

    def get_current_price(self) -> Optional[float]:
        """Return the latest mid price from the most recent tick."""
        m1 = self._candle_windows.get("M1", [])
        if m1:
            return m1[-1].close
        return None

    def get_latest_spread(self) -> float:
        """Return the spread from the latest candle."""
        m1 = self._candle_windows.get("M1", [])
        return m1[-1].spread if m1 else 0.0

    def get_dirty_timeframes(self) -> set[str]:
        """Return and clear the set of timeframes with new data."""
        dirty = self._dirty_timeframes.copy()
        self._dirty_timeframes.clear()
        return dirty

    def is_timeframe_dirty(self, tf: str) -> bool:
        """Check if a specific timeframe has new data since last check."""
        return tf in self._dirty_timeframes

    # ── Convenience methods called by main.py pipeline ─────────────────
    async def process_tick(self, payload: dict) -> None:
        """Accept raw tick dict from transport, convert to TickData, delegate to on_tick."""
        tick = TickData(
            bid=float(payload.get("bid", 0)),
            ask=float(payload.get("ask", 0)),
            spread=float(payload.get("spread", 0)),
            volume=int(payload.get("volume", 0)),
            timestamp=int(payload.get("timestamp", now_ms())),
            flags=int(payload.get("flags", 0)),
        )
        self._last_tick_time["M1"] = tick.timestamp
        await self.on_tick(tick)

    async def process_candle(self, payload: dict, timeframe: str = "M5") -> None:
        """Accept raw candle dict from transport, convert to CandleData, delegate to on_candle."""
        candle = CandleData(
            open=float(payload.get("open", 0)),
            high=float(payload.get("high", 0)),
            low=float(payload.get("low", 0)),
            close=float(payload.get("close", 0)),
            volume=int(payload.get("volume", 0)),
            spread=float(payload.get("spread", 0)),
            timestamp=int(payload.get("timestamp", now_ms())),
            timeframe=timeframe,
            complete=True,
        )
        await self.on_candle(candle)

    # ── Dual-path processing (audit section XVIII) ───────────────────────
    # Tick path:  fast, lightweight — price, spread, freshness, signal monitoring
    # Candle path: slow, full analysis — indicators, structure, strategy run

    async def process_tick_fast(self, payload: dict) -> dict:
        """
        FAST TICK PATH — lightweight processing for every tick.

        Does NOT trigger full engine analysis. Only:
          - Validates tick price
          - Tracks spread
          - Updates freshness
          - Emits MARKET_TICK for active signal monitoring

        Returns a minimal result dict with the tick summary for
        downstream consumers that need fast tick-level data.
        """
        bid = float(payload.get("bid", 0))
        ask = float(payload.get("ask", 0))
        volume = int(payload.get("volume", 0))
        timestamp = int(payload.get("timestamp", now_ms()))
        flags = int(payload.get("flags", 0))

        mid = (bid + ask) / 2.0
        spread = ask - bid

        # Validate
        if mid <= 0:
            return {"valid": False, "reason": "invalid_price"}

        # Track freshness
        self._last_tick_time["M1"] = timestamp

        # Spread monitoring (fast check)
        if spread > MAX_SPREAD_PIPS:
            self._spread_violations += 1

        # Compute data age
        last_candle_ts = self._last_candle_time.get("M1", 0)
        data_age_ms = (timestamp - last_candle_ts) if last_candle_ts > 0 else 999999

        # Determine if a candle boundary was crossed (check for M1)
        candle_ts = self._floor_timestamp(timestamp, 60)
        candle_crossed = False
        if len(self._tick_buffer.get("M1", [])) > 0:
            first_ts = self._tick_buffer["M1"][0].timestamp
            first_candle_ts = self._floor_timestamp(first_ts, 60)
            candle_crossed = candle_ts > first_candle_ts

        # Append to tick buffer (same as on_tick but without full event publishing)
        tick = TickData(
            bid=bid, ask=ask, spread=spread,
            volume=volume, timestamp=timestamp, flags=flags,
        )
        self._tick_buffer["M1"].append(tick)

        # Emit lightweight MARKET_TICK for signal monitoring
        await self._bus.publish(
            EventType.MARKET_TICK,
            source="market_data_engine",
            payload={
                "tick": tick,
                "mid": mid,
                "spread": spread,
                "fast_path": True,
                "data_age_ms": data_age_ms,
            },
        )

        # If candle boundary crossed, close the candle (triggers aggregation)
        if candle_crossed and self._tick_buffer["M1"]:
            first_candle_ts = self._floor_timestamp(
                self._tick_buffer["M1"][0].timestamp, 60
            )
            await self._close_candle_from_ticks("M1", first_candle_ts)

        return {
            "valid": True,
            "fast_path": True,
            "mid": mid,
            "bid": bid,
            "ask": ask,
            "spread": spread,
            "data_age_ms": data_age_ms,
            "candle_crossed": candle_crossed,
            "timestamp_ms": timestamp,
        }

    async def process_candle_full(self, payload: dict, timeframe: str = "M5") -> dict:
        """
        SLOW CANDLE PATH — full analysis on candle close.

        Called when a candle closes on a significant timeframe.
        Triggers the full analysis chain:
          - Candle validation + deduplication
          - Outlier detection
          - Timeframe aggregation (lower → higher)
          - CANDLE_CLOSED event (triggers indicator/structure/regime engines)
          - Data quality recalculation

        Returns a detailed result dict with analysis status.
        """
        candle = CandleData(
            open=float(payload.get("open", 0)),
            high=float(payload.get("high", 0)),
            low=float(payload.get("low", 0)),
            close=float(payload.get("close", 0)),
            volume=int(payload.get("volume", 0)),
            spread=float(payload.get("spread", 0)),
            timestamp=int(payload.get("timestamp", now_ms())),
            timeframe=timeframe,
            complete=True,
        )

        # Process via the existing full pipeline
        await self.on_candle(candle)

        # Compute current data quality after candle processing
        dq = self.get_data_quality()

        # Return detailed analysis result
        return {
            "valid": True,
            "fast_path": False,
            "timeframe": timeframe,
            "candle_timestamp": candle.timestamp,
            "candle_close": candle.close,
            "aggregated_higher": AGGREGATION_CHAIN.get(timeframe),
            "data_quality_score": dq.score,
            "is_fresh": dq.is_fresh,
            "dirty_timeframes": list(self._dirty_timeframes),
            "timestamp_ms": now_ms(),
        }

    # ── Signal monitoring helpers (for active signal tracking on ticks) ──

    def get_tick_freshness(self) -> Dict[str, Any]:
        """
        Quick freshness check for active signal monitoring.
        Returns a lightweight dict with freshness metrics.
        """
        now = now_ms()
        last_tick = self._last_tick_time.get("M1", 0)
        last_candle = self._last_candle_time.get("M1", 0)

        tick_age_ms = (now - last_tick) if last_tick > 0 else 999999
        candle_age_ms = (now - last_candle) if last_candle > 0 else 999999

        return {
            "tick_age_ms": tick_age_ms,
            "candle_age_ms": candle_age_ms,
            "tick_fresh": tick_age_ms < 5000,
            "candle_fresh": candle_age_ms < 60_000,
            "spread": self.get_latest_spread(),
            "current_price": self.get_current_price(),
        }

    def get_last_tick_time(self) -> int:
        """Return timestamp of last tick (ms), 0 if none."""
        return self._last_tick_time.get("M1", 0)

    # ── Data quality report ───────────────────────────────────────────────
    def get_data_quality(self) -> DataQualityReport:
        """Compute a composite data-quality score."""
        # Staleness
        last_m1 = self._last_candle_time.get("M1", 0)
        staleness = now_ms() - last_m1 if last_m1 else 999999

        # Missing candles ratio
        total_candles = sum(len(q) for q in self._candle_windows.values())
        missing_ratio = (
            self._missing_candle_count / max(total_candles, 1)
        )

        # Score breakdown: start at 100, deduct
        score = 100.0
        # Deduct for staleness (1 point per second stale)
        staleness_penalty = min(30.0, staleness / 1000.0 * 0.5)
        score -= staleness_penalty
        # Deduct for missing candles
        score -= min(20.0, missing_ratio * 100.0)
        # Deduct for duplicates
        score -= min(10.0, self._duplicate_count * 0.1)
        # Deduct for outliers
        score -= min(15.0, self._outlier_count * 1.0)
        # Deduct for spread violations
        score -= min(15.0, self._spread_violations * 0.05)

        score = max(0.0, min(100.0, score))

        return DataQualityReport(
            score=round(score, 1),
            missing_candles=self._missing_candle_count,
            duplicate_candles=self._duplicate_count,
            outliers_detected=self._outlier_count,
            spread_violations=self._spread_violations,
            staleness_ms=staleness,
            is_fresh=staleness <= 10000,
        )

    # ── Utilities ─────────────────────────────────────────────────────────
    @staticmethod
    def _floor_timestamp(ts_ms: int, interval_secs: int) -> int:
        """Floor a millisecond timestamp to the nearest interval boundary."""
        interval_ms = interval_secs * 1000
        return (ts_ms // interval_ms) * interval_ms

    def reset_quality_counters(self) -> None:
        """Reset data quality tracking counters."""
        self._duplicate_count = 0
        self._outlier_count = 0
        self._missing_candle_count = 0
        self._spread_violations = 0
