"""
NEXUS OVERLAY AI - Main Application Entry Point

Orchestrates the full analysis pipeline:
MT5 Data -> Market Data Engine -> Indicators -> PriceAction -> Structure -> Liquidity ->
Zones -> MTF -> Session -> Regime -> Strategies -> Confluence -> Entry -> SL -> TP ->
Risk -> Confidence -> Decision -> Signal -> (Optional AI Advisory) -> WebSocket Broadcast
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import signal
import sys
from pathlib import Path
from datetime import datetime

# Ensure project root on path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.config_loader import Config, get_config
from backend.event_bus import get_event_bus, EventBus, EventType
from backend.engines.market_data_engine import MarketDataEngine
from backend.engines.indicator_engine import IndicatorEngine
from backend.engines.price_action_engine import PriceActionEngine
from backend.engines.structure_engine import StructureEngine
from backend.engines.liquidity_engine import LiquidityEngine
from backend.engines.zone_engine import ZoneEngine
from backend.engines.mtf_engine import MTFEngine
from backend.engines.session_engine import SessionEngine
from backend.engines.regime_engine import RegimeEngine
from backend.engines.strategy_engine import StrategyEngine
from backend.engines.confluence_engine import ConfluenceEngine
from backend.engines.risk_engine import RiskEngine
from backend.engines.entry_engine import EntryEngine
from backend.engines.sl_engine import SLEngine
from backend.engines.tp_engine import TPEngine
from backend.engines.confidence_model import ConfidenceModelEngine
from backend.engines.decision_engine import DecisionEngine, DecisionEngineOutput
from backend.engines.safety_governor import SafetyGovernor
from backend.transport.websocket_server import NexusWebSocketServer
from backend.transport.http_bridge import HTTPBridgeServer
from backend.health import HealthServer
from backend.database.db import DatabaseManager
from backend.replay.replay_engine import MarketReplayEngine
from backend.models import (
    CandleData, IndicatorValue, MarketStructure, MarketRegime,
    PriceActionPattern, LiquidityEvent, Zone, SLTPCalculation,
    SLMethod, TPMethod, TrendDirection, DecisionState,
    MarketSnapshot, AIAssessment, AIProviderType, now_ms,
)
from backend.strategies.base import MarketState

logger = logging.getLogger("nexus_overlay")


def _build_indicator_value_dict(
    indicator_engine: IndicatorEngine,
    candles: list[CandleData],
) -> dict[str, IndicatorValue]:
    """
    Build a dict[str, IndicatorValue] by calling individual indicator
    compute methods.  Returns IndicatorValue objects keyed by their
    indicator name (e.g. 'ADX', 'EMA_20', 'RSI', 'MACD', ...).

    This bridges the gap between IndicatorEngine (which has individual
    compute methods returning IndicatorValue) and the StrategyEngine
    (which expects dict[str, IndicatorValue] in MarketState).
    """
    iv_map: dict[str, IndicatorValue] = {}

    individual_methods = [
        ("EMA_20", lambda: indicator_engine.compute_ema(candles, 20)),
        ("EMA_50", lambda: indicator_engine.compute_ema(candles, 50)),
        ("EMA_100", lambda: indicator_engine.compute_ema(candles, 100)),
        ("EMA_200", lambda: indicator_engine.compute_ema(candles, 200)),
        ("SMA_50", lambda: indicator_engine.compute_sma(candles, 50)),
        ("SMA_200", lambda: indicator_engine.compute_sma(candles, 200)),
        ("RSI", lambda: indicator_engine.compute_rsi(candles)),
        ("MACD", lambda: indicator_engine.compute_macd(candles)),
        ("ROC", lambda: indicator_engine.compute_roc(candles)),
        ("ATR", lambda: indicator_engine.compute_atr(candles)),
        ("ATR_PCT", lambda: indicator_engine.compute_atr_pct(candles)),
        ("BB", lambda: indicator_engine.compute_bollinger_bands(candles)),
    ]

    for name, method in individual_methods:
        try:
            iv = method()
            if iv is not None:
                iv_map[name] = iv
        except Exception:
            pass

    # ADX returns a dict-like result from compute_adx
    try:
        adx_result = indicator_engine.compute_adx(candles)
        if adx_result is not None:
            iv_map["ADX"] = adx_result
    except Exception:
        pass

    # Volume
    try:
        vol_result = indicator_engine.compute_volume(candles)
        if vol_result is not None:
            iv_map["VOLUME"] = vol_result
    except Exception:
        pass

    return iv_map


def _build_market_snapshot(
    price: float,
    spread: float,
    flat_indicators: dict,
    structure: MarketStructure | None,
    liquidity_events: list[LiquidityEvent],
    price_action_patterns: list[PriceActionPattern],
    session_info: dict,
    regime_result: dict,
    dq_score: float,
) -> MarketSnapshot:
    """Build a MarketSnapshot for optional AI advisory."""
    trend = {}
    if structure:
        trend["primary"] = structure.trend.value
        trend["structure"] = structure.structure.value
    else:
        trend["primary"] = "NEUTRAL"

    struct_dict = {}
    if structure:
        struct_dict["type"] = structure.structure.value
        struct_dict["bos"] = str(structure.bos)
        struct_dict["choch"] = str(structure.choch)

    liq_dict = {
        "event_count": len(liquidity_events),
        "events": [
            {"type": e.event.value, "direction": e.direction, "price": e.price}
            for e in liquidity_events[:10]
        ],
    }

    pa_dict = {
        "pattern_count": len(price_action_patterns),
        "patterns": [
            {"pattern": p.pattern.value, "location": p.location, "strength": p.strength}
            for p in price_action_patterns[:10]
        ],
    }

    mom_dict = {
        "rsi": flat_indicators.get("rsi", 0),
        "adx": flat_indicators.get("adx", 0),
        "macd": flat_indicators.get("macd", 0),
    }

    vol_dict = {
        "atr": flat_indicators.get("atr", 0),
        "atr_pct": flat_indicators.get("atr_pct", 0),
        "vol_ratio": regime_result.get("vol_ratio", 1.0),
    }

    regime_val = regime_result.get("regime", MarketRegime.UNCERTAIN)
    regime_str = regime_val.value if hasattr(regime_val, "value") else str(regime_val)

    return MarketSnapshot(
        symbol="XAUUSD",
        price=price,
        spread=spread,
        trend=trend,
        structure=struct_dict,
        liquidity=liq_dict,
        price_action=pa_dict,
        momentum=mom_dict,
        volatility=vol_dict,
        session=session_info.get("primary_session", "off"),
        regime=regime_str,
        data_quality=dq_score / 100.0,  # MarketSnapshot expects 0-1
        timestamp=now_ms(),
    )


class NexusOverlayApp:
    """Main application orchestrator."""

    def __init__(self):
        self._config = get_config()
        self._running = False

        # Event bus
        self._event_bus = get_event_bus()

        # Engines
        cfg = self._config.all()
        self.market_data = MarketDataEngine(cfg, self._event_bus)
        self.indicators = IndicatorEngine(cfg, self._event_bus)
        self.price_action = PriceActionEngine(cfg, self._event_bus)
        self.structure = StructureEngine(cfg, self._event_bus)
        self.liquidity = LiquidityEngine(cfg, self._event_bus)
        self.zones = ZoneEngine(cfg, self._event_bus)
        self.mtf = MTFEngine(cfg, self._event_bus)
        self.session = SessionEngine(cfg, self._event_bus)
        self.regime = RegimeEngine(cfg, self._event_bus)
        self.strategy = StrategyEngine(cfg)
        self.confluence = ConfluenceEngine(cfg, self._event_bus)
        self.risk = RiskEngine(cfg, self._event_bus)
        self.entry = EntryEngine(cfg, self._event_bus)
        self.sl = SLEngine(cfg, self._event_bus)
        self.tp = TPEngine(cfg, self._event_bus)
        self.confidence = ConfidenceModelEngine(cfg, self._event_bus)
        self.safety = SafetyGovernor(cfg)
        self.decision = DecisionEngine()

        # AI providers (OPTIONAL advisory — not authoritative)
        self._ai_manager = self._init_ai_providers(cfg)

        # Transport
        self.ws_server = NexusWebSocketServer(cfg)
        self.ws_server.on_tick(self._on_tick)
        self.ws_server.on_candle(self._on_candle)
        self.ws_server.on_symbol_info(self._on_symbol_info)

        # Health check server
        self.health_server = HealthServer(cfg)

        # HTTP bridge for MQL5 EA (EA cannot use WebSocket)
        self.http_bridge = HTTPBridgeServer(cfg)
        self.http_bridge.on_tick(self._on_tick)
        self.http_bridge.on_candle(self._on_candle)
        self.http_bridge.on_symbol_info(self._on_symbol_info)

        # DB
        self.db = DatabaseManager(cfg.get("database", {}).get("path", "data/nexus_overlay.db"))

        self._last_signal_id: str | None = None

    def _init_ai_providers(self, cfg: dict):
        """
        Initialise the AI provider manager with available providers.
        AI is OPTIONAL advisory — the trading core is deterministic.
        """
        try:
            from backend.ai.provider import AIProviderManager
            from backend.ai.openai_provider import OpenAIProvider
            from backend.ai.claude_provider import ClaudeProvider
            from backend.ai.local_provider import LocalProvider

            manager = AIProviderManager()
            # Try adding providers — each will mark itself unavailable
            # if its API key / endpoint is missing.
            manager.add_provider(OpenAIProvider())
            manager.add_provider(ClaudeProvider())
            manager.add_provider(LocalProvider())
            available = [p.provider_type().value for p in manager.providers if p.is_available]
            if available:
                logger.info(f"AI providers ready: {available}")
            else:
                logger.warning("No AI providers available — AI advisory disabled")
            return manager
        except Exception as e:
            logger.warning(f"AI provider init failed (non-critical): {e}")
            return None

    async def start(self):
        logger.info("=== Nexus Overlay AI starting ===")
        self._running = True
        await self.safety.start()
        await self.decision.start()
        await self.strategy.start()
        self.ws_server.set_event_bus(get_event_bus())
        asyncio.create_task(self.ws_server.start())
        await self.health_server.start()
        self.health_server.update_status("engines_loaded", 16)
        asyncio.create_task(self.http_bridge.start())
        await self.db.initialize()
        logger.info("All engines started. Waiting for MT5 connection...")
        try:
            while self._running:
                await asyncio.sleep(1)
        except asyncio.CancelledError:
            pass
        finally:
            await self.stop()

    async def stop(self):
        logger.info("Nexus Overlay AI shutting down...")
        self._running = False
        await self.http_bridge.stop()
        await self.health_server.stop()
        await self.ws_server.stop()
        await self.decision.stop()
        await self.safety.stop()
        await self.strategy.stop()
        await self.db.close()
        logger.info("Shutdown complete.")

    # ────────────────────────────────────────────────────────────────────
    #  Callbacks from MT5 EA
    # ────────────────────────────────────────────────────────────────────
    async def _on_tick(self, client, message):
        """
        FULL PIPELINE — called on every tick.

        Pipeline order:
          MarketData → Indicators → PriceAction → Structure → Liquidity →
          Zones → MTF → Session → Regime → Strategies → Confluence →
          Entry → SL → TP → Risk → Confidence → Decision → (AI advisory)
        """
        payload = message.payload
        bid = payload.get("bid", 0)
        ask = payload.get("ask", 0)
        spread = payload.get("spread", 0)

        logger.info(f"_on_tick: bid={bid} ask={ask}")

        # ── 1. Market Data ─────────────────────────────────────────────
        try:
            await self.market_data.process_tick(payload)
        except Exception as e:
            logger.error(f"process_tick error: {e}")
            return

        # ── 2. Indicators (flat dict for regime/confluence + IV dict for strategies) ──
        m5_candles = self.market_data.get_candles("M5")
        if not m5_candles or len(m5_candles) < 20:
            return

        flat_indicators = self.indicators.compute(m5_candles) or {}
        iv_indicators = _build_indicator_value_dict(self.indicators, m5_candles)

        # ── 3. Safety check ────────────────────────────────────────────
        tick_age = self._get_tick_age_ms()
        dq = self.market_data.get_data_quality()
        dq_score = dq.score if hasattr(dq, "score") else float(dq) if dq else 0.0
        safety_result = await self.safety.validate(
            bid=bid, ask=ask, price=bid, spread=spread,
            data_age_ms=tick_age, data_quality=dq_score,
            transport_connected=True, mtf=None, market_open=True,
        )
        if safety_result.block:
            logger.debug(f"Safety block: {safety_result.blocks}")
            return

        # ── 4. Structure ───────────────────────────────────────────────
        structure = self.structure.analyze(m5_candles)

        # ── 5. Price Action (NEW — was skipped) ────────────────────────
        price_action_patterns = self.price_action.analyze(m5_candles, structure)
        logger.debug(f"Price action: {len(price_action_patterns)} patterns detected")

        # ── 6. Liquidity ───────────────────────────────────────────────
        liq = self.liquidity.analyze(m5_candles, structure)

        # ── 7. Zones ───────────────────────────────────────────────────
        zones = self.zones.analyze(m5_candles)

        # ── 8. MTF ─────────────────────────────────────────────────────
        mtf_data = {tf: self.market_data.get_candles(tf) for tf in ["H4", "H1", "M30", "M15", "M5", "M3", "M1"]}
        mtf_result = self.mtf.analyze(mtf_data)

        # ── 9. Session ─────────────────────────────────────────────────
        sess = self.session.analyze()

        # ── 10. Regime ─────────────────────────────────────────────────
        regime_result = self.regime.analyze(m5_candles, iv_indicators)

        # ── 11. Strategies (build proper MarketState) ──────────────────
        # Determine session type for MarketState
        from backend.models import SessionType as _ST
        primary = sess.get("primary_session", "off")
        session_type_map = {
            "asian": _ST.ASIAN, "london": _ST.LONDON,
            "new_york": _ST.NEW_YORK, "overlap": _ST.OVERLAP,
        }
        session_type = session_type_map.get(primary, _ST.ASIAN)

        # Extract regime for MarketState
        regime_val = regime_result.get("regime", MarketRegime.UNCERTAIN)
        if hasattr(regime_val, "value"):
            ms_regime = regime_val  # already a MarketRegime enum
        else:
            ms_regime = MarketRegime.UNCERTAIN

        mid_price = (bid + ask) / 2 if bid > 0 and ask > 0 else bid or ask

        market_state = MarketState(
            symbol="XAUUSD",
            timeframe="M5",
            price=mid_price,
            bid=bid,
            ask=ask,
            spread=spread,
            candles=m5_candles,
            indicators=iv_indicators,
            structure=structure,
            liquidity_events=liq,
            patterns=price_action_patterns,
            mtf=mtf_result,
            regime=ms_regime,
            session=session_type,
            data_quality=dq_score / 100.0,
            data_age_ms=tick_age,
            timestamp=now_ms(),
        )

        strategies = await self.strategy.evaluate(market_state)

        # ── 12. Confluence ─────────────────────────────────────────────
        conf = self.confluence.calculate(
            indicators=flat_indicators,
            structure=structure,
            price_action=price_action_patterns,
            liquidity=liq,
            mtf=mtf_result,
            regime=regime_result,
            session_active=sess.get("session_active", True),
            volatility_atr=float(regime_result.get("adx", 20)),
            atr_avg=float(flat_indicators.get("atr", 2.0)),
        )

        # ── Determine trade direction from strategies ──────────────────
        active_assessments = [
            a for a in strategies if a.direction != DecisionState.WAIT
        ]

        buy_count = sum(1 for a in active_assessments if a.direction == DecisionState.BUY)
        sell_count = sum(1 for a in active_assessments if a.direction == DecisionState.SELL)

        if buy_count >= sell_count and buy_count > 0:
            trade_direction = "BUY"
        elif sell_count > buy_count:
            trade_direction = "SELL"
        else:
            trade_direction = None  # no active direction

        # ── 13. Entry Engine (NEW — was skipped) ───────────────────────
        entry_calc = self.entry.calculate(
            candles=m5_candles,
            structure=structure,
            zones=zones,
            regime=regime_result.get("regime", "UNCERTAIN"),
            price_action=price_action_patterns,
        )

        # ── 14. SL Engine (NEW — was skipped) ──────────────────────────
        atr_val = float(flat_indicators.get("atr", 0))
        sltp_calc = self.sl.calculate(
            candles=m5_candles,
            entry_price=entry_calc.price if entry_calc.price > 0 else mid_price,
            direction=trade_direction or "BUY",  # default to BUY for SL calc
            atr=atr_val,
            structure=structure,
            swing_highs=structure.swing_highs if structure else [],
            swing_lows=structure.swing_lows if structure else [],
            zones=zones,
        )

        # ── 15. TP Engine (NEW — was skipped) ──────────────────────────
        effective_entry = entry_calc.price if entry_calc.price > 0 else mid_price
        effective_sl = sltp_calc.sl_price

        # Extract liquidity levels and S/R levels from events and zones
        liq_levels = [e.price for e in liq if e.price > 0]
        sr_levels = [z.midpoint for z in zones if z.midpoint > 0]

        tp_result = self.tp.calculate(
            entry_price=effective_entry,
            sl_price=effective_sl,
            direction=trade_direction or "BUY",
            atr=atr_val,
            liquidity_levels=liq_levels,
            sr_levels=sr_levels,
        )

        # Merge TP results into SLTPCalculation
        merged_sltp = SLTPCalculation(
            sl_method=sltp_calc.sl_method,
            sl_price=sltp_calc.sl_price,
            sl_reason=sltp_calc.sl_reason,
            tp1_method=tp_result.get("tp1_method", TPMethod.RISK_REWARD),
            tp1_price=tp_result.get("tp1", 0.0),
            tp2_method=tp_result.get("tp2_method", TPMethod.RISK_REWARD),
            tp2_price=tp_result.get("tp2", 0.0),
            tp3_method=tp_result.get("tp3_method", TPMethod.RISK_REWARD),
            tp3_price=tp_result.get("tp3", 0.0),
            invalidation_reason=sltp_calc.invalidation_reason,
            timestamp=now_ms(),
        )

        # ── 16. Risk Engine (NEW — was skipped, THIS was the P0 bug) ───
        sl_distance = abs(effective_entry - effective_sl) if effective_sl > 0 else 0
        tp1_distance = abs(merged_sltp.tp1_price - effective_entry) if merged_sltp.tp1_price > 0 else 0

        # Calculate RR
        rr = 0.0
        if sl_distance > 0 and tp1_distance > 0:
            rr = tp1_distance / sl_distance

        # Count MTF conflicts
        mtf_conflicts = len(mtf_result.conflicts) if mtf_result else 0

        risk_validation = self.risk.validate(
            spread=spread,
            volatility_atr=atr_val,
            rr=rr,
            sl_distance=sl_distance,
            tp1_distance=tp1_distance,
            regime=regime_result.get("regime", MarketRegime.UNCERTAIN),
            data_quality=dq_score,
            session_active=sess.get("session_active", True),
            signal_age_candles=0,  # fresh signal
            mtf_conflicts=mtf_conflicts,
            last_tick_age_ms=tick_age,
        )

        # ── 17. Confidence Model (NEW — was skipped) ───────────────────
        # Compute component scores for confidence model
        tech_confluence = conf.total_score if conf else 50.0

        # MTF agreement score (0-100)
        mtf_agreement = 50.0
        if mtf_result:
            if mtf_result.alignment == "aligned":
                mtf_agreement = 90.0
            elif mtf_result.alignment == "partially_aligned":
                mtf_agreement = 65.0
            elif mtf_result.alignment == "conflicting":
                mtf_agreement = 20.0

        # Risk quality (0-100) — based on how many checks passed
        risk_quality = 50.0
        if risk_validation and risk_validation.checks:
            passed = sum(1 for v in risk_validation.checks.values() if v)
            total = len(risk_validation.checks)
            risk_quality = (passed / total * 100.0) if total > 0 else 50.0

        # AI confidence (0) — we don't have AI assessment yet at this point
        ai_confidence = 0.0

        confidence_model = self.confidence.calculate(
            technical_confluence=tech_confluence,
            mtf_agreement=mtf_agreement,
            risk_quality=risk_quality,
            data_quality=dq_score,
            ai_confidence=ai_confidence,
        )

        # ── 18. Build DecisionEngineOutput (NOW with all fields!) ──────
        output = DecisionEngineOutput()
        output.strategy_assessments = strategies
        output.confluence = conf
        output.risk_validation = risk_validation       # ← THIS was None before!
        output.entry_calc = entry_calc                  # ← NEW
        output.sltp_calc = merged_sltp                  # ← NEW
        output.confidence_model = confidence_model      # ← NEW
        output.price = mid_price
        output.spread = spread
        output.trend = regime_result.get("trend", "NEUTRAL")
        output.regime = ms_regime
        output.data_quality = dq_score
        output.data_age_ms = tick_age
        output.mtf = mtf_result
        output.transport_connected = True
        output.market_open = True
        output.symbol = "XAUUSD"

        # ── 19. Decision Engine ────────────────────────────────────────
        try:
            signal_result = await self.decision.evaluate(output)
            signal_json = signal_result.to_dict() if hasattr(signal_result, "to_dict") else signal_result
            decision_val = signal_result.decision.value if hasattr(signal_result.decision, "value") else str(signal_result.decision)
            msg_type = "SIGNAL_CREATED" if decision_val not in ("WAIT",) else "MARKET_SNAPSHOT"

            # ── 20. AI Advisory (OPTIONAL, post-decision) ──────────────
            # AI does NOT override the decision. It only adds advisory context.
            ai_assessment = None
            if self._ai_manager is not None:
                try:
                    snapshot = _build_market_snapshot(
                        price=mid_price, spread=spread,
                        flat_indicators=flat_indicators,
                        structure=structure,
                        liquidity_events=liq,
                        price_action_patterns=price_action_patterns,
                        session_info=sess,
                        regime_result=regime_result,
                        dq_score=dq_score,
                    )
                    ai_assessment = await self._ai_manager.analyze(snapshot)
                    # Attach AI assessment to the signal for transparency
                    if hasattr(signal_json, "get") or isinstance(signal_json, dict):
                        if isinstance(signal_json, dict):
                            signal_json["ai_advisory"] = {
                                "assessment": ai_assessment.assessment,
                                "confidence": ai_assessment.confidence,
                                "explanation": ai_assessment.explanation,
                                "provider": ai_assessment.provider.value,
                            }
                    # Log but do NOT override the decision
                    if ai_assessment.assessment != "neutral":
                        logger.info(
                            f"AI advisory: {ai_assessment.assessment} "
                            f"(conf={ai_assessment.confidence:.2f}) — "
                            f"decision remains {decision_val}"
                        )
                except Exception as e:
                    logger.debug(f"AI advisory failed (non-critical): {e}")

            await self.ws_server.broadcast_to_android({
                "message_type": msg_type,
                "payload": signal_json,
            })

        except Exception as e:
            logger.error(f"Decision engine error: {e}")

    async def _on_candle(self, client, message):
        """Store closed candles — pipeline runs on _on_tick."""
        payload = message.payload
        tf = message.timeframe or "M5"
        logger.info(f"_on_candle called: tf=" + tf + " open=" + str(payload.get("open")) + " close=" + str(payload.get("close")))
        try:
            await self.market_data.process_candle(payload, tf)
            candles = self.market_data.get_candles(tf)
            logger.info(f"Candle stored {tf}: total={len(candles)}")
        except Exception as e:
            logger.error(f"process_candle error: {e}", exc_info=True)

    async def _on_symbol_info(self, client, message):
        logger.info(f"Symbol info: {message.payload}")

    def _get_tick_age_ms(self) -> int:
        last_tick = self.market_data.get_last_tick_time()
        if last_tick == 0:
            return 999999
        return int(datetime.now().timestamp() * 1000) - last_tick


async def main():
    logging.basicConfig(
        level=get_config().get("system.log_level", "INFO"),
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
        datefmt="%H:%M:%S"
    )
    app = NexusOverlayApp()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, lambda: asyncio.create_task(app.stop()))

    logger.info("Starting Nexus Overlay AI...")
    await app.start()


if __name__ == "__main__":
    asyncio.run(main())
