"""
NEXUS OVERLAY AI - Event Bus
Internal pub/sub event system for decoupled module communication
"""
from __future__ import annotations
import asyncio
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable, Awaitable
from enum import Enum
import logging

from backend.models import (
    MarketRegime, TrendDirection, DecisionState, 
    SignalLifecycleState, PatternType, StructureType,
    LiquidityEventType, ZoneType, SessionType
)


logger = logging.getLogger(__name__)


class EventType(Enum):
    """Internal event types"""
    MARKET_TICK = "MARKET_TICK"
    CANDLE_CLOSED = "CANDLE_CLOSED"
    INDICATOR_UPDATED = "INDICATOR_UPDATED"
    STRUCTURE_CHANGED = "STRUCTURE_CHANGED"
    LIQUIDITY_EVENT = "LIQUIDITY_EVENT"
    ZONE_UPDATED = "ZONE_UPDATED"
    MTF_UPDATED = "MTF_UPDATED"
    REGIME_CHANGED = "REGIME_CHANGED"
    STRATEGY_ASSESSMENT = "STRATEGY_ASSESSMENT"
    CONFLUENCE_CALCULATED = "CONFLUENCE_CALCULATED"
    RISK_VALIDATED = "RISK_VALIDATED"
    SIGNAL_CREATED = "SIGNAL_CREATED"
    SIGNAL_UPDATED = "SIGNAL_UPDATED"
    SIGNAL_INVALIDATED = "SIGNAL_INVALIDATED"
    SIGNAL_EXPIRED = "SIGNAL_EXPIRED"
    SIGNAL_COMPLETED = "SIGNAL_COMPLETED"
    DATA_STALE = "DATA_STALE"
    CONNECTION_LOST = "CONNECTION_LOST"
    CONNECTION_RESTORED = "CONNECTION_RESTORED"
    AI_ANALYSIS_COMPLETE = "AI_ANALYSIS_COMPLETE"
    ERROR = "ERROR"


@dataclass
class Event:
    """Event container"""
    event_type: EventType
    source: str
    payload: dict = field(default_factory=dict)
    timestamp: int = field(default_factory=lambda: int(datetime.now().timestamp() * 1000))
    sequence: int = 0


class EventBus:
    """Async event bus for internal module communication"""
    
    def __init__(self):
        self._subscribers: dict[EventType, list[Callable[[Event], Awaitable[None]]]] = defaultdict(list)
        self._sequence = 0
        self._running = False
        self._queue: asyncio.Queue[Event] = asyncio.Queue()
        self._dispatch_task: asyncio.Task | None = None
    
    async def start(self):
        """Start event dispatch loop"""
        if self._running:
            return
        self._running = True
        self._dispatch_task = asyncio.create_task(self._dispatch_loop())
        logger.info("Event bus started")
    
    async def stop(self):
        """Stop event dispatch loop"""
        self._running = False
        if self._dispatch_task:
            self._dispatch_task.cancel()
            try:
                await self._dispatch_task
            except asyncio.CancelledError:
                pass
        logger.info("Event bus stopped")
    
    def subscribe(self, event_type: EventType, handler: Callable[[Event], Awaitable[None]]) -> None:
        """Subscribe to event type"""
        self._subscribers[event_type].append(handler)
        logger.debug(f"Subscribed {handler.__name__} to {event_type.value}")
    
    def unsubscribe(self, event_type: EventType, handler: Callable[[Event], Awaitable[None]]) -> None:
        """Unsubscribe from event type"""
        if handler in self._subscribers[event_type]:
            self._subscribers[event_type].remove(handler)
    
    async def publish(self, event_type: EventType, source: str, payload: dict | None = None) -> None:
        """Publish event to bus (async, queued)"""
        self._sequence += 1
        event = Event(
            event_type=event_type,
            source=source,
            payload=payload or {},
            sequence=self._sequence
        )
        await self._queue.put(event)
    
    async def publish_sync(self, event_type: EventType, source: str, payload: dict | None = None) -> None:
        """Publish event synchronously (immediate dispatch)"""
        self._sequence += 1
        event = Event(
            event_type=event_type,
            source=source,
            payload=payload or {},
            sequence=self._sequence
        )
        await self._dispatch_event(event)
    
    async def _dispatch_loop(self):
        """Event dispatch loop"""
        while self._running:
            try:
                event = await asyncio.wait_for(self._queue.get(), timeout=1.0)
                await self._dispatch_event(event)
            except asyncio.TimeoutError:
                continue
            except Exception as e:
                logger.error(f"Event dispatch error: {e}")
    
    async def _dispatch_event(self, event: Event):
        """Dispatch event to all subscribers"""
        handlers = self._subscribers.get(event.event_type, [])
        for handler in handlers:
            try:
                await handler(event)
            except Exception as e:
                logger.error(f"Handler {handler.__name__} error for {event.event_type.value}: {e}")
    
    def get_stats(self) -> dict:
        """Get event bus statistics"""
        return {
            "subscribers": {et.value: len(h) for et, h in self._subscribers.items()},
            "queue_size": self._queue.qsize(),
            "sequence": self._sequence,
            "running": self._running
        }


# Global event bus instance
_event_bus: EventBus | None = None


def get_event_bus() -> EventBus:
    """Get global event bus instance"""
    global _event_bus
    if _event_bus is None:
        _event_bus = EventBus()
    return _event_bus