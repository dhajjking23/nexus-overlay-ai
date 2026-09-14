# NEXUS OVERLAY AI — Development Guide

## Project Structure

```
nexus-overlay-ai/
├── bridge/MQL5/           # MT5 Expert Advisor + Indicator
├── backend/               # Python analysis backend
│   ├── models/            # Data models (dataclasses)
│   ├── engines/           # Analysis engines
│   ├── strategies/        # Trading strategies
│   ├── ai/                # AI provider abstraction
│   ├── transport/         # WebSocket server + protocol
│   ├── database/          # SQLite persistence
│   ├── event_bus/         # Internal pub/sub
│   ├── replay/            # Backtesting engine
│   ├── tests/             # Unit + integration tests
│   ├── config_loader.py   # YAML config with env overrides
│   └── main.py            # Application entry point
├── android/               # Android Kotlin/Compose app
├── config/                # Configuration files
├── docs/                  # Documentation
├── deployment/            # Deployment scripts
└── requirements.txt       # Python dependencies
```

## Adding New Indicators

1. Open `backend/engines/indicator_engine.py`
2. Add computation method following pattern:

```python
async def _compute_my_indicator(self, candles: list[CandleData], config: dict) -> IndicatorValue:
    period = config.get("period", 14)
    # ... compute using pure Python math ...
    return IndicatorValue(
        indicator="MY_INDICATOR",
        timeframe=candles[0].timeframe if candles else "M1",
        value=computed_value,
        state="BULLISH" if condition else "BEARISH",
        timestamp=now_ms()
    )
```

3. Register in `_compute_all_indicators()`
4. Add to `default_config.yaml`
5. Write unit test in `tests/unit/`

## Adding New Strategies

1. Create `backend/strategies/my_strategy.py`
2. Extend `BaseStrategy`:

```python
from backend.strategies.base import BaseStrategy

class MyStrategy(BaseStrategy):
    name = "my_strategy"
    
    async def evaluate(self, market_state: dict) -> StrategyAssessment:
        # ... analyze market_state ...
        return StrategyAssessment(
            strategy=self.name,
            direction=DecisionState.BUY,
            score=75,
            confidence=0.75,
            evidence=["reason 1", "reason 2"],
        )
```

3. Register in `backend/strategies/__init__.py`
4. Add weight in config: `strategies.weights.my_strategy`
5. Write unit test

## Adding New AI Providers

1. Create `backend/ai/my_provider.py`
2. Extend `AIProvider`:

```python
from backend.ai.provider import AIProvider

class MyProvider(AIProvider):
    async def analyze(self, snapshot: MarketSnapshot) -> AIAssessment:
        # ... call API ...
        return AIAssessment(
            provider=AIProviderType.MY,
            assessment="bullish",
            confidence=0.85,
            explanation="...",
            timestamp=now_ms()
        )
```

3. Register in config
4. Add fallback handling

## Testing

### Unit Tests
```bash
cd backend
python -m pytest tests/unit/ -v
```

### Integration Tests
```bash
cd backend
python -m pytest tests/integration/ -v
```

### Replay Testing
```bash
python -m backend.replay.replay_engine --input data/historical/XAUUSD_M5.csv --output results/
```

## Configuration

- Primary: `config/default_config.yaml`
- Override: environment variables (e.g., `TRANSPORT_PORT=8766`)
- Runtime: Android settings or API endpoint

## Code Conventions

- Type hints everywhere
- Docstrings on public methods
- Dataclasses for data structures (not dicts)
- Async/await for I/O operations
- Structured logging (not print)
- No hardcoded values in engine logic
- Every decision must have an evidence chain
