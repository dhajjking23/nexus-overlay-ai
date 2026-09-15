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
        self.indicators = IndicatorEngine(cfg)
        self.price_action = PriceActionEngine(cfg)
        self.structure = StructureEngine(cfg)
        self.liquidity = LiquidityEngine(cfg)
        self.zones = ZoneEngine(cfg)
        self.mtf = MTFEngine(cfg)
        self.session = SessionEngine(cfg)
        self.regime = RegimeEngine(cfg)
        self.strategy = StrategyEngine(cfg)
        self.confluence = ConfluenceEngine(cfg)
        self.risk = RiskEngine(cfg)
        self.entry = EntryEngine(cfg)
        self.sl = SLEngine(cfg)
        self.tp = TPEngine(cfg)
        self.confidence = ConfidenceModelEngine(cfg)
        self.safety = SafetyGovernor(cfg)
        self.decision = DecisionEngine(cfg)

        # Transport
        self.ws_server = NexusWebSocketServer(cfg)
        self.ws_server.on_tick(self._on_tick)
        self.ws_server.on_candle(self._on_candle)
        self.ws_server.on_symbol_info(self._on_symbol_info)

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
        await self.ws_server.stop()
        await self.decision.stop()
        await self.safety.stop()
        await self.strategy.stop()
        await self.db.close()
        logger.info("Shutdown complete.")

    # --- Callbacks from MT5 EA ---
    async def _on_tick(self, client, message):
        payload = message.payload
        await self.market_data.process_tick(payload)
        indicators = self.indicators.compute(self.market_data.get_candles("M5"))
        tick_age = self._get_tick_age_ms()
        safety_result = await self.safety.validate(
            spread=payload.get("spread", 0), last_tick_age_ms=tick_age,
            data_live=True, connected=True, mtf_aligned=True,
            data_quality=self.market_data.get_data_quality()
        )
        if not safety_result.all_passed:
            return
        candles = self.market_data.get_candles("M5")
        if not candles or len(candles) < 20:
            return
        structure = self.structure.analyze(candles)
        liq = self.liquidity.analyze(candles, structure)
        zones = self.zones.analyze(candles)
        mtf_data = {tf: self.market_data.get_candles(tf) for tf in ["H4", "H1", "M30", "M15", "M5", "M3", "M1"]}
        mtf_result = self.mtf.analyze(mtf_data)
        sess = self.session.analyze()
        regime_result = self.regime.analyze(candles, indicators)
        strategies = await self.strategy.evaluate({
            "candles": candles, "indicators": indicators, "structure": structure,
            "liquidity": liq, "zones": zones, "mtf": mtf_result, "regime": regime_result,
            "session": sess, "price_action": []
        })
        conf = self.confluence.calculate(
            indicators=indicators, structure=structure, mtf=mtf_result,
            liquidity=liq, regime=regime_result, session_active=sess.get("session_active", True),
            volatility_atr=regime_result.get("adx", 20), atr_avg=2.0
        )
        output = DecisionEngineOutput(
            indicators=indicators, structure=structure, liquidity_events=liq,
            price_action_patterns=[], mtf_analysis=mtf_result, regime=regime_result,
            session=sess, strategy_assessments=strategies, confluence_score=conf,
            current_price=payload.get("bid", 0), current_spread=payload.get("spread", 0),
            data_quality=self.market_data.get_data_quality(),
            atr=regime_result.get("adx", 20), atr_avg=2.0,
            swing_highs=structure.swing_highs if structure else [],
            swing_lows=structure.swing_lows if structure else [],
            zones=zones
        )
        signal_result = await self.decision.evaluate(output)
        signal_json = signal_result.to_dict() if hasattr(signal_result, "to_dict") else signal_result
        await self.ws_server.broadcast_to_android({
            "message_type": "SIGNAL_CREATED" if signal_result.decision.value not in ("WAIT",) else "MARKET_SNAPSHOT",
            "payload": signal_json
        })

    async def _on_candle(self, client, message):
        payload = message.payload
        tf = message.timeframe or "M5"
        await self.market_data.process_candle(payload, tf)
        logger.debug(f"Candle closed {tf}: O={payload.get('open')} C={payload.get('close')}")

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
        loop.add_signal_handler(sig, lambda: asyncio.create_task(app.start()))

    logger.info("Starting Nexus Overlay AI...")
    await app.start()


if __name__ == "__main__":
    asyncio.run(main())