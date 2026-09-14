"""
NEXUS OVERLAY AI - Transport Protocol
Protocol versioning, message serialization/deserialization, heartbeat messages,
sequence validation, duplicate detection, checksum computation.
"""
from __future__ import annotations
import json
import hashlib
import time
import logging
from dataclasses import dataclass, field
from typing import Any, Optional
from enum import Enum

from backend.models import MessageType, ProtocolMessage as BaseProtocolMessage

logger = logging.getLogger(__name__)


PROTOCOL_VERSION = "1.0"
HEARTBEAT_INTERVAL_MS = 5000
MAX_SEQUENCE_GAP = 1000
SEQUENCE_WINDOW_SIZE = 10000


class ProtocolError(Exception):
    """Base protocol error"""
    pass


class ChecksumMismatchError(ProtocolError):
    """Checksum validation failed"""
    pass


class SequenceError(ProtocolError):
    """Sequence validation failed"""
    pass


class DuplicateMessageError(ProtocolError):
    """Duplicate message detected"""
    pass


class ProtocolVersionMismatchError(ProtocolError):
    """Protocol version mismatch"""
    pass


@dataclass
class MessageValidator:
    """
    Validates protocol messages for sequence, checksum, duplicates.
    Maintains sliding window of recent sequences for duplicate detection.
    """
    expected_sequence: int = 0
    seen_sequences: set[int] = field(default_factory=set)
    sequence_window: int = SEQUENCE_WINDOW_SIZE
    allow_out_of_order: bool = False
    
    def validate_sequence(self, sequence: int) -> tuple[bool, str | None]:
        """
        Validate message sequence.
        Returns (is_valid, error_message).
        """
        if sequence <= 0:
            return False, "Invalid sequence number"
        
        if sequence in self.seen_sequences:
            return False, f"Duplicate sequence: {sequence}"
        
        if not self.allow_out_of_order:
            if sequence < self.expected_sequence:
                return False, f"Stale sequence: {sequence} < expected {self.expected_sequence}"
            if sequence > self.expected_sequence + MAX_SEQUENCE_GAP:
                return False, f"Sequence gap too large: {sequence} > {self.expected_sequence + MAX_SEQUENCE_GAP}"
        
        return True, None
    
    def accept_sequence(self, sequence: int) -> None:
        """Mark sequence as accepted, update window."""
        self.seen_sequences.add(sequence)
        if not self.allow_out_of_order:
            self.expected_sequence = max(self.expected_sequence, sequence + 1)
        
        # Clean old sequences outside window
        min_valid = sequence - self.sequence_window
        self.seen_sequences = {s for s in self.seen_sequences if s >= min_valid}
    
    def reset(self) -> None:
        """Reset validator state."""
        self.expected_sequence = 0
        self.seen_sequences.clear()


def compute_checksum(payload: dict) -> str:
    """
    Compute SHA256 checksum of payload for integrity verification.
    Returns hex string of first 16 chars.
    """
    # Deterministic JSON serialization
    json_str = json.dumps(payload, sort_keys=True, separators=(',', ':'))
    return hashlib.sha256(json_str.encode()).hexdigest()[:16]


def verify_checksum(payload: dict, expected_checksum: str) -> bool:
    """Verify payload checksum matches expected."""
    if not expected_checksum:
        return True  # Empty checksum = skip verification
    computed = compute_checksum(payload)
    return computed == expected_checksum


def create_message(
    message_type: MessageType,
    sequence: int,
    symbol: str = "XAUUSD",
    timeframe: str = "M1",
    payload: dict | None = None,
    timestamp: int | None = None,
    protocol_version: str = PROTOCOL_VERSION,
) -> ProtocolMessage:
    """Create a protocol message with computed checksum."""
    payload = payload or {}
    timestamp = timestamp or int(time.time() * 1000)
    checksum = compute_checksum(payload)
    
    return ProtocolMessage(
        protocol_version=protocol_version,
        message_type=message_type,
        sequence=sequence,
        symbol=symbol,
        timeframe=timeframe,
        timestamp=timestamp,
        payload=payload,
        checksum=checksum,
    )


def create_heartbeat(sequence: int, source: str = "backend") -> ProtocolMessage:
    """Create a heartbeat message."""
    return create_message(
        message_type=MessageType.HEARTBEAT,
        sequence=sequence,
        payload={"source": source, "server_time": int(time.time() * 1000)},
    )


def parse_message(json_str: str, validator: MessageValidator | None = None) -> ProtocolMessage:
    """
    Parse and validate a protocol message from JSON string.
    Raises ProtocolError on validation failure.
    """
    try:
        data = json.loads(json_str)
    except json.JSONDecodeError as e:
        raise ProtocolError(f"Invalid JSON: {e}")
    
    # Validate protocol version
    protocol_version = data.get("protocol_version", "1.0")
    if protocol_version != PROTOCOL_VERSION:
        logger.warning(f"Protocol version mismatch: {protocol_version} != {PROTOCOL_VERSION}")
        # Don't reject, just warn
    
    # Extract fields
    message_type_str = data.get("message_type")
    if not message_type_str:
        raise ProtocolError("Missing message_type")
    
    try:
        message_type = MessageType(message_type_str)
    except ValueError:
        raise ProtocolError(f"Unknown message type: {message_type_str}")
    
    sequence = data.get("sequence", 0)
    symbol = data.get("symbol", "XAUUSD")
    timeframe = data.get("timeframe", "M1")
    timestamp = data.get("timestamp", int(time.time() * 1000))
    payload = data.get("payload", {})
    checksum = data.get("checksum", "")
    
    # Verify checksum
    if not verify_checksum(payload, checksum):
        raise ChecksumMismatchError(f"Checksum mismatch: expected {checksum}, got {compute_checksum(payload)}")
    
    # Validate sequence
    if validator:
        valid, error = validator.validate_sequence(sequence)
        if not valid:
            raise SequenceError(error)
        validator.accept_sequence(sequence)
    
    return ProtocolMessage(
        protocol_version=protocol_version,
        message_type=message_type,
        sequence=sequence,
        symbol=symbol,
        timeframe=timeframe,
        timestamp=timestamp,
        payload=payload,
        checksum=checksum,
    )


def serialize_message(message: ProtocolMessage) -> str:
    """Serialize ProtocolMessage to JSON string."""
    return message.to_json()


def deserialize_message(json_str: str, validator: MessageValidator | None = None) -> ProtocolMessage:
    """Deserialize JSON string to ProtocolMessage with validation."""
    return parse_message(json_str, validator)


class HeartbeatManager:
    """Manages heartbeat sending and stale connection detection."""
    
    def __init__(self, interval_ms: int = HEARTBEAT_INTERVAL_MS):
        self.interval_ms = interval_ms
        self.last_sent: int = 0
        self.last_received: int = 0
        self.sequence: int = 0
        self.is_running: bool = False
        self._task: Optional[asyncio.Task] = None
    
    async def start(self, send_callback) -> None:
        """Start heartbeat loop with send callback."""
        self.is_running = True
        self.last_sent = int(time.time() * 1000)
        self._task = asyncio.create_task(self._heartbeat_loop(send_callback))
    
    async def stop(self) -> None:
        """Stop heartbeat loop."""
        self.is_running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
    
    async def _heartbeat_loop(self, send_callback) -> None:
        """Send heartbeats at regular intervals."""
        while self.is_running:
            await asyncio.sleep(self.interval_ms / 1000.0)
            if not self.is_running:
                break
            
            self.sequence += 1
            hb_msg = create_heartbeat(self.sequence)
            try:
                await send_callback(hb_msg)
            except Exception as e:
                logger.error(f"Heartbeat send failed: {e}")
    
    def record_received(self) -> None:
        """Record heartbeat received."""
        self.last_received = int(time.time() * 1000)
    
    def is_stale(self, timeout_ms: int = 30000) -> bool:
        """Check if connection is stale (no heartbeat received)."""
        if self.last_received == 0:
            return False
        return (int(time.time() * 1000) - self.last_received) > timeout_ms


# Import asyncio at module level for HeartbeatManager
import asyncio