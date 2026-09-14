# NEXUS OVERLAY AI — Decision Model

## Philosophy

```
DATA → EVIDENCE → ANALYSIS → RISK → DECISION → VISUALIZATION
```

NEVER: `PRICE → AI → BUY`

## Decision Engine = Single Source of Truth

The DecisionEngine is the ONLY component authorized to create a final signal. All other modules produce evidence and analysis — none may independently publish a trading decision.

## Decision Flow

```
1. Data Quality Check
   ├── Stale? → WAIT (DATA_STALE)
   ├── Malformed? → WAIT (DATA_UNAVAILABLE)
   └── Below threshold? → WAIT (DATA_UNAVAILABLE)

2. Safety Governor Check
   ├── Spread too high? → WAIT
   ├── Abnormal volatility? → WAIT
   ├── Transport disconnected? → WAIT
   └── Any critical safety flag? → WAIT

3. MTF Alignment Check
   ├── Conflicting higher TF? → WAIT (CONFLICT)
   └── Partially aligned? → lower confidence

4. Strategy Assessment
   ├── 6 strategies evaluate independently
   ├── Each produces direction + score + evidence
   └── Confluence engine weights and combines

5. Risk Validation
   ├── Spread check
   ├── Min RR check (default >= 1.5)
   ├── SL/TP distance validation
   ├── Market regime check
   ├── Session check
   └── Failed? → WAIT (RISK_REJECTED)

6. Entry + SL/TP Calculation
   ├── Entry type: market/limit/confirmation/zone
   ├── SL: ATR/structure/swing/zone-based
   └── TP1/TP2/TP3: RR/liquidity/SR/ATR-based

7. Confidence Calculation
   ├── Technical confluence (35%)
   ├── MTF agreement (25%)
   ├── Risk quality (15%)
   ├── Data quality (15%)
   └── AI assessment (10%)

8. AI Analysis (optional)
   ├── Structured snapshot → AI provider
   ├── AI returns: assessment + confidence + explanation
   ├── AI failure → fallback to deterministic mode
   └── AI CANNOT override risk rules

9. Final Decision
   ├── Confidence >= min_confidence? → BUY or SELL
   ├── Otherwise → WAIT (NO_SETUP)
   └── Create TradingSignal with full evidence chain
```

## Decision States

| State | Meaning |
|-------|---------|
| BUY | Bullish setup meets all criteria |
| SELL | Bearish setup meets all criteria |
| WAIT | No actionable setup |
| DATA_UNAVAILABLE | No or insufficient market data |
| DATA_STALE | Data too old for analysis |
| RISK_REJECTED | Setup exists but fails risk validation |
| CONFLICT | Higher timeframe conflicts with entry |
| NO_SETUP | No valid trading setup detected |
| AI_UNAVAILABLE | AI provider failed (deterministic fallback active) |
| MARKET_CLOSED | Market is closed or paused |

## Signal Lifecycle

```
NEW → CONFIRMED → ACTIVE → WEAKENING → INVALIDATED / EXPIRED / COMPLETED
```

- **NEW**: Signal just created
- **CONFIRMED**: Multiple confirmations received
- **ACTIVE**: Signal is valid and tracking
- **WEAKENING**: Evidence weakening, near invalidation
- **INVALIDATED**: Thesis broken (e.g., structure changed)
- **EXPIRED**: Signal age exceeded candle threshold
- **COMPLETED**: TP or SL hit

## Confidence Model

```
final_confidence = (
    technical_confluence × 0.35 +
    mtf_agreement × 0.25 +
    risk_quality × 0.15 +
    data_quality × 0.15 +
    ai_assessment × 0.10
)
```

Where each component is normalized 0-100:
- technical_confluence: weighted sum from confluence engine
- mtf_agreement: 100 if aligned, 60 if partial, 20 if conflicting
- risk_quality: 100 if all checks pass, scaled by number of checks
- data_quality: data freshness/coverage score
- ai_assessment: AI confidence (0 if AI unavailable)

## Evidence Chain

Every signal must carry:
- **evidence[]**: Why this decision was made (bullet points)
- **invalidations[]**: What would invalidate this signal
- **strategy_scores{}**: Per-strategy score breakdown
- **indicator_snapshot{}**: Key indicator values at decision time
- **confluence**: Weighted score breakdown

## Safety Rules

1. AI can never bypass Risk Engine
2. AI can never bypass Decision Engine
3. Missing data = WAIT (never fabricate)
4. Conflicting evidence = WAIT
5. Old signals must be visually marked stale
6. Offline mode: show LAST SIGNAL + stale indicator
