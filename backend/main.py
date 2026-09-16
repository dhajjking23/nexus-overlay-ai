"""
NEXUS OVERLAY AI - Main Application Entry Point

Orchestrates the full analysis pipeline:
MT5 Data -> Market Data Engine -> Indicators -> Structure -> Liquidity ->
Zones -> MTF -> Session -> Regime -> Strategies -> Risk -> Entry/SL/TP ->
Confidence -> AI -> Decision Engine -> Signal -> WebSocket Broadcast
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

logger = logging.getLogger("nexus_overlay")


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

    # --- Callbacks from MT5 EA ---
    async def _on_tick(self, client, message):
        logger.info(f"_on_tick: bid={message.payload.get("bid")} ask={message.payload.get("ask")}")
        payload = message.payload
        try:
            await self.market_data.process_tick(payload)
        except Exception as e:
            logger.error(f"process_tick error: {e}")
            return

        # Compute indicators
        m5_candles = self.market_data.get_candles("M5")
        indicators = self.indicators.compute(m5_candles) if m5_candles and len(m5_candles) >= 20 else {}

        # Safety check
        tick_age = self._get_tick_age_ms()
        dq = self.market_data.get_data_quality()
        dq_score = dq.score if hasattr(dq, "score") else float(dq) if dq else 0.0
        bid = payload.get("bid", 0)
        ask = payload.get("ask", 0)
        safety_result = await self.safety.validate(
            bid=bid,
            ask=ask,
            price=bid,
            spread=payload.get("spread", 0),
            data_age_ms=tick_age,
            data_quality=dq_score,
            transport_connected=True,
            mtf=None,
            market_open=True,
        )
        if safety_result.block:
            logger.debug(f"Safety block: {safety_result.blocks}")
            return

        # Need at least 20 M5 candles for analysis
        if not m5_candles or len(m5_candles) < 20:
            return

        # Run engine pipeline
        structure = self.structure.analyze(m5_candles)
        liq = self.liquidity.analyze(m5_candles, structure)
        zones = self.zones.analyze(m5_candles)
        mtf_data = {tf: self.market_data.get_candles(tf) for tf in ["H4", "H1", "M30", "M15", "M5", "M3", "M1"]}
        mtf_result = self.mtf.analyze(mtf_data)
        sess = self.session.analyze()
        regime_result = self.regime.analyze(m5_candles, indicators)

        # Strategies
        strategies = await self.strategy.evaluate({
            "candles": m5_candles, "indicators": indicators, "structure": structure,
            "liquidity": liq, "zones": zones, "mtf": mtf_result, "regime": regime_result,
            "session": sess, "price_action": []
        })

        # Confluence
        conf = self.confluence.calculate(
            indicators=indicators, structure=structure, mtf=mtf_result,
            liquidity=liq, regime=regime_result,
            session_active=sess.get("session_active", True),
            volatility_atr=float(regime_result.get("adx", 20)),
            atr_avg=float(indicators.get("atr", 2.0)),
        )

        # Build DecisionEngineOutput
        output = DecisionEngineOutput()
        output.strategy_assessments = strategies
        output.confluence = conf
        output.price = payload.get("bid", 0)
        output.spread = payload.get("spread", 0)
        output.trend = regime_result.get("trend", "NEUTRAL")
        output.regime = regime_result.get("regime", "UNCERTAIN")
        output.data_quality = dq_score
        output.data_age_ms = tick_age
        output.mtf = mtf_result
        output.transport_connected = True
        output.market_open = True

        # Evaluate
        try:
            signal_result = await self.decision.evaluate(output)
            signal_json = signal_result.to_dict() if hasattr(signal_result, "to_dict") else signal_result
            decision_val = signal_result.decision.value if hasattr(signal_result.decision, "value") else str(signal_result.decision)
            msg_type = "SIGNAL_CREATED" if decision_val not in ("WAIT",) else "MARKET_SNAPSHOT"
            await self.ws_server.broadcast_to_android({
                "message_type": msg_type,
                "payload": signal_json
            })
        except Exception as e:
            logger.error(f"Decision engine error: {e}")

    async def _on_candle(self, client, message):
        payload = message.payload
        tf = message.timeframe or "M5"
        logger.info(f"_on_candle called: tf={tf} open={payload.get('open')} close={payload.get('close')}")
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
