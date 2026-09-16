package com.nexus.overlay.ui.overlay

import androidx.compose.animation.*
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.alpha
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.nexus.overlay.data.*
import com.nexus.overlay.ui.theme.*
import com.nexus.overlay.viewmodel.OverlayMode

// --- Freshness indicator colors ---
val StaleYellow = Color(0xFFFFC107)
val InvalidRed = Color(0xFFFF5252)
val FreshGreen = Color(0xFF00E676)

/**
 * Format age in milliseconds to human-readable string.
 * e.g. 1500 -> "1.5s", 45000 -> "45.0s"
 */
private fun formatAge(ageMs: Long): String {
    return when {
        ageMs < 1000 -> "${ageMs}ms"
        ageMs < 60_000 -> String.format("%.1fs", ageMs / 1000.0)
        ageMs < 3600_000 -> String.format("%.0fm", ageMs / 60000.0)
        else -> String.format("%.0fh", ageMs / 3600000.0)
    }
}

/**
 * Overlay content composables for all three modes:
 * Compact, Standard, and Pro.
 *
 * Section 81: Shows decision_score, data_age, signal_age, AI status.
 * Section 82: Shows WAIT reason for WAIT decisions.
 * Section 41: Shows stale/invalid signal indicators.
 */
@Composable
fun OverlayContent(
    mode: OverlayMode,
    signalStore: SignalStore,
    opacity: Float,
    onClose: () -> Unit,
    onModeSwitch: (OverlayMode) -> Unit
) {
    val signal by signalStore.currentSignal.collectAsState()
    val market by signalStore.marketData.collectAsState()
    val mtf by signalStore.mtfMatrix.collectAsState()
    val connection by signalStore.connectionStatus.collectAsState()
    val regime by signalStore.regime.collectAsState()
    val freshness by signalStore.signalFreshness.collectAsState()
    val signalAge by signalStore.signalAge.collectAsState()
    val marketDataAge by signalStore.marketDataAge.collectAsState()
    val aiStatus by signalStore.aiStatus.collectAsState()

    Box(modifier = Modifier.alpha(opacity)) {
        when (mode) {
            OverlayMode.COMPACT -> CompactOverlay(
                signal = signal,
                market = market,
                connection = connection,
                freshness = freshness,
                signalAge = signalAge,
                onClose = onClose,
                onExpand = { onModeSwitch(OverlayMode.STANDARD) }
            )
            OverlayMode.STANDARD -> StandardOverlay(
                signal = signal,
                market = market,
                mtf = mtf,
                connection = connection,
                freshness = freshness,
                signalAge = signalAge,
                marketDataAge = marketDataAge,
                aiStatus = aiStatus,
                onClose = onClose,
                onSwitchMode = onModeSwitch
            )
            OverlayMode.PRO -> ProOverlay(
                signal = signal,
                market = market,
                mtf = mtf,
                regime = regime,
                connection = connection,
                signalStore = signalStore,
                freshness = freshness,
                signalAge = signalAge,
                marketDataAge = marketDataAge,
                aiStatus = aiStatus,
                onClose = onClose,
                onSwitchMode = onModeSwitch
            )
        }
    }
}

// ============================================================================
// COMPACT MODE
// ============================================================================

@Composable
fun CompactOverlay(
    signal: SignalData?,
    market: MarketData,
    connection: ConnectionState,
    freshness: SignalFreshness,
    signalAge: Long,
    onClose: () -> Unit,
    onExpand: () -> Unit
) {
    // Section 41/82: Show DATA STALE instead of old signal when INVALID
    val displayDecision = when (freshness) {
        SignalFreshness.INVALID -> "DATA STALE"
        SignalFreshness.STALE -> signal?.signalType ?: "WAIT"
        SignalFreshness.NO_SIGNAL -> "NO SIGNAL"
        SignalFreshness.FRESH -> signal?.signalType ?: "WAIT"
    }

    val signalColor = when (freshness) {
        SignalFreshness.INVALID -> InvalidRed
        SignalFreshness.STALE -> StaleYellow
        SignalFreshness.NO_SIGNAL -> SignalWait
        SignalFreshness.FRESH -> when (signal?.signalType) {
            "BUY" -> SignalBuy
            "SELL" -> SignalSell
            else -> SignalWait
        }
    }
    val bgShape = RoundedCornerShape(24.dp)

    Box(
        modifier = Modifier
            .size(320.dp, 56.dp)
            .clip(bgShape)
            .background(NexusSurface.copy(alpha = 0.95f))
            .border(1.dp, signalColor.copy(alpha = 0.5f), bgShape)
            .clickable { onExpand() }
            .padding(horizontal = 16.dp),
        contentAlignment = Alignment.Center
    ) {
        Row(
            verticalAlignment = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.SpaceBetween,
            modifier = Modifier.fillMaxWidth()
        ) {
            // Signal indicator
            Row(verticalAlignment = Alignment.CenterVertically) {
                // Pulsing dot with freshness color
                Box(
                    modifier = Modifier
                        .size(10.dp)
                        .clip(RoundedCornerShape(5.dp))
                        .background(signalColor)
                )
                Spacer(modifier = Modifier.width(8.dp))
                Column {
                    Text(
                        text = displayDecision,
                        color = signalColor,
                        fontSize = 14.sp,
                        fontWeight = FontWeight.Bold,
                        fontFamily = FontFamily.Monospace
                    )
                    // Section 42: Signal age + data age
                    if (freshness != SignalFreshness.NO_SIGNAL) {
                        Text(
                            text = if (market.bid > 0) String.format("%.2f", market.bid) else "---",
                            color = NexusTextSecondary,
                            fontSize = 10.sp,
                            fontFamily = FontFamily.Monospace
                        )
                    }
                }
            }

            // Entry price (only show when FRESH)
            if (freshness == SignalFreshness.FRESH && signal?.entry != null && signal.entry > 0) {
                Column(horizontalAlignment = Alignment.End) {
                    Text(
                        text = "ENTRY",
                        color = NexusTextMuted,
                        fontSize = 8.sp,
                        letterSpacing = 1.sp
                    )
                    Text(
                        text = String.format("%.2f", signal.entry),
                        color = NexusTextPrimary,
                        fontSize = 13.sp,
                        fontWeight = FontWeight.Bold,
                        fontFamily = FontFamily.Monospace
                    )
                }
            }

            // Connection indicator + close
            Row(verticalAlignment = Alignment.CenterVertically) {
                // Freshness dot
                if (freshness != SignalFreshness.FRESH) {
                    Text(
                        text = formatAge(signalAge),
                        color = signalColor,
                        fontSize = 8.sp,
                        fontFamily = FontFamily.Monospace
                    )
                    Spacer(modifier = Modifier.width(4.dp))
                }
                Box(
                    modifier = Modifier
                        .size(6.dp)
                        .clip(RoundedCornerShape(3.dp))
                        .background(
                            when (connection) {
                                ConnectionState.CONNECTED -> NexusSuccess
                                ConnectionState.CONNECTING -> NexusWarning
                                else -> NexusError
                            }
                        )
                )
                Spacer(modifier = Modifier.width(4.dp))
                Icon(
                    imageVector = Icons.Default.Close,
                    contentDescription = "Close",
                    tint = NexusTextMuted,
                    modifier = Modifier
                        .size(16.dp)
                        .clickable { onClose() }
                )
            }
        }
    }
}

// ============================================================================
// STANDARD MODE
// ============================================================================

@Composable
fun StandardOverlay(
    signal: SignalData?,
    market: MarketData,
    mtf: Map<String, TimeframeSignal>,
    connection: ConnectionState,
    freshness: SignalFreshness,
    signalAge: Long,
    marketDataAge: Long,
    aiStatus: AiStatus,
    onClose: () -> Unit,
    onSwitchMode: (OverlayMode) -> Unit
) {
    val bgShape = RoundedCornerShape(12.dp)
    val signalColor = when (freshness) {
        SignalFreshness.INVALID -> InvalidRed
        SignalFreshness.STALE -> StaleYellow
        SignalFreshness.NO_SIGNAL -> SignalWait
        SignalFreshness.FRESH -> when (signal?.signalType) {
            "BUY" -> SignalBuy
            "SELL" -> SignalSell
            else -> SignalWait
        }
    }

    Box(
        modifier = Modifier
            .width(340.dp)
            .clip(bgShape)
            .background(NexusSurface.copy(alpha = 0.95f))
            .border(1.dp, signalColor.copy(alpha = 0.3f), bgShape)
            .padding(12.dp)
    ) {
        Column {
            // Header
            StandardHeader(signal, market, connection, freshness, aiStatus, onClose, onSwitchMode)

            Spacer(modifier = Modifier.height(8.dp))

            // Signal card
            StandardSignalCard(signal, signalColor, freshness)

            Spacer(modifier = Modifier.height(8.dp))

            // Signal freshness bar (Section 41/42)
            if (freshness != SignalFreshness.NO_SIGNAL) {
                FreshnessBar(
                    freshness = freshness,
                    signalAge = signalAge,
                    marketDataAge = marketDataAge,
                    connection = connection
                )
                Spacer(modifier = Modifier.height(8.dp))
            }

            // Price levels
            if (signal != null && signal.entry > 0 && freshness != SignalFreshness.INVALID) {
                PriceLevels(signal)
            }

            Spacer(modifier = Modifier.height(8.dp))

            // Mini MTF bar
            if (mtf.isNotEmpty()) {
                MiniMTFBar(mtf)
            }
        }
    }
}

@Composable
private fun StandardHeader(
    signal: SignalData?,
    market: MarketData,
    connection: ConnectionState,
    freshness: SignalFreshness,
    aiStatus: AiStatus,
    onClose: () -> Unit,
    onSwitchMode: (OverlayMode) -> Unit
) {
    Row(
        modifier = Modifier.fillMaxWidth(),
        horizontalArrangement = Arrangement.SpaceBetween,
        verticalAlignment = Alignment.CenterVertically
    ) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            // Connection dot
            Box(
                modifier = Modifier
                    .size(6.dp)
                    .clip(RoundedCornerShape(3.dp))
                    .background(
                        when (connection) {
                            ConnectionState.CONNECTED -> NexusSuccess
                            ConnectionState.CONNECTING -> NexusWarning
                            else -> NexusError
                        }
                    )
            )
            Spacer(modifier = Modifier.width(6.dp))
            Text(
                text = "XAUUSD",
                color = NexusTextPrimary,
                fontSize = 12.sp,
                fontWeight = FontWeight.Bold,
                letterSpacing = 1.sp
            )
            if (market.bid > 0) {
                Spacer(modifier = Modifier.width(8.dp))
                Text(
                    text = "${String.format("%.2f", market.bid)} / ${String.format("%.2f", market.ask)}",
                    color = NexusTextSecondary,
                    fontSize = 10.sp,
                    fontFamily = FontFamily.Monospace
                )
            }
            // AI Status indicator
            Spacer(modifier = Modifier.width(8.dp))
            Text(
                text = "AI:${if (aiStatus == AiStatus.ONLINE) "ON" else "OFF"}",
                color = if (aiStatus == AiStatus.ONLINE) NexusSuccess else NexusTextMuted,
                fontSize = 8.sp,
                fontFamily = FontFamily.Monospace,
                fontWeight = FontWeight.Bold
            )
        }

        Row {
            // Mode switch
            Icon(
                imageVector = Icons.Default.Settings,
                contentDescription = "Switch mode",
                tint = NexusTextMuted,
                modifier = Modifier
                    .size(14.dp)
                    .clickable { onSwitchMode(OverlayMode.COMPACT) }
            )
            Spacer(modifier = Modifier.width(8.dp))
            Icon(
                imageVector = Icons.Default.Close,
                contentDescription = "Close",
                tint = NexusTextMuted,
                modifier = Modifier
                    .size(14.dp)
                    .clickable { onClose() }
            )
        }
    }
}

@Composable
private fun StandardSignalCard(signal: SignalData?, signalColor: Color, freshness: SignalFreshness) {
    Column(
        modifier = Modifier
            .fillMaxWidth()
            .clip(RoundedCornerShape(8.dp))
            .background(NexusBackground)
            .padding(10.dp)
    ) {
        Row(
            modifier = Modifier.fillMaxWidth(),
            horizontalArrangement = Arrangement.SpaceBetween,
            verticalAlignment = Alignment.CenterVertically
        ) {
            // Section 82: Show DATA STALE instead of old BUY/SELL
            val displayText = when (freshness) {
                SignalFreshness.INVALID -> "DATA STALE"
                SignalFreshness.STALE -> (signal?.signalType ?: "NO SIGNAL") + " ⚠"
                SignalFreshness.NO_SIGNAL -> "NO SIGNAL"
                SignalFreshness.FRESH -> signal?.signalType ?: "NO SIGNAL"
            }

            Text(
                text = displayText,
                color = signalColor,
                fontSize = 16.sp,
                fontWeight = FontWeight.Bold
            )

            // Section 81: Decision score instead of confidence %
            if (freshness == SignalFreshness.FRESH && signal != null) {
                val score = signal.decisionScore
                if (score > 0) {
                    Text(
                        text = "SCR ${String.format("%.0f", score)}/100",
                        color = NexusTextSecondary,
                        fontSize = 11.sp,
                        fontFamily = FontFamily.Monospace
                    )
                }
            }
        }

        // Section 82: Show WAIT reason
        if (signal?.decision == "WAIT" && signal.waitReason.isNotEmpty()) {
            Spacer(modifier = Modifier.height(4.dp))
            Row(verticalAlignment = Alignment.CenterVertically) {
                Text(
                    text = "⬡",
                    color = NexusWarning,
                    fontSize = 10.sp
                )
                Spacer(modifier = Modifier.width(4.dp))
                Text(
                    text = signal.waitReason,
                    color = NexusWarning,
                    fontSize = 10.sp,
                    fontWeight = FontWeight.Bold
                )
            }
        }

        if (signal?.reason != null && signal.reason.isNotEmpty() && freshness == SignalFreshness.FRESH) {
            Spacer(modifier = Modifier.height(4.dp))
            Text(
                text = signal.reason,
                color = NexusTextMuted,
                fontSize = 10.sp,
                maxLines = 2
            )
        }
    }
}

/**
 * Section 41/42: Signal freshness bar showing age indicators.
 */
@Composable
private fun FreshnessBar(
    freshness: SignalFreshness,
    signalAge: Long,
    marketDataAge: Long,
    connection: ConnectionState
) {
    val barColor = when (freshness) {
        SignalFreshness.FRESH -> NexusSuccess
        SignalFreshness.STALE -> StaleYellow
        SignalFreshness.INVALID -> InvalidRed
        SignalFreshness.NO_SIGNAL -> NexusTextMuted
    }

    Row(
        modifier = Modifier
            .fillMaxWidth()
            .clip(RoundedCornerShape(4.dp))
            .background(barColor.copy(alpha = 0.1f))
            .padding(horizontal = 8.dp, vertical = 4.dp),
        horizontalArrangement = Arrangement.SpaceBetween,
        verticalAlignment = Alignment.CenterVertically
    ) {
        // Signal age
        Text(
            text = "SIG: ${formatAge(signalAge)}",
            color = barColor,
            fontSize = 8.sp,
            fontFamily = FontFamily.Monospace,
            fontWeight = FontWeight.Bold
        )

        // Market data age
        Text(
            text = "MKT: ${formatAge(marketDataAge)}",
            color = if (marketDataAge > SignalStore.MARKET_STALE_THRESHOLD_MS) StaleYellow else NexusTextSecondary,
            fontSize = 8.sp,
            fontFamily = FontFamily.Monospace
        )

        // Connection state
        Text(
            text = when (connection) {
                ConnectionState.CONNECTED -> "CONN: OK"
                ConnectionState.CONNECTING -> "CONN: ..."
                ConnectionState.STALE -> "CONN: STALE"
                ConnectionState.ERROR -> "CONN: ERR"
                ConnectionState.DISCONNECTED -> "CONN: OFF"
            },
            color = when (connection) {
                ConnectionState.CONNECTED -> NexusSuccess
                ConnectionState.CONNECTING -> NexusWarning
                else -> NexusError
            },
            fontSize = 8.sp,
            fontFamily = FontFamily.Monospace
        )
    }
}

@Composable
private fun PriceLevels(signal: SignalData) {
    Row(
        modifier = Modifier.fillMaxWidth(),
        horizontalArrangement = Arrangement.SpaceEvenly
    ) {
        PriceLevelChip("SL", signal.sl, StopLossLine)
        PriceLevelChip("ENTRY", signal.entry, EntryLine)
        PriceLevelChip("TP1", signal.tp1, TP1Line)
        PriceLevelChip("TP2", signal.tp2, TP2Line)
        PriceLevelChip("TP3", signal.tp3, TP3Line)
    }
}

@Composable
private fun PriceLevelChip(label: String, price: Double, color: Color) {
    Column(horizontalAlignment = Alignment.CenterHorizontally) {
        Text(
            text = label,
            color = color.copy(alpha = 0.7f),
            fontSize = 8.sp,
            letterSpacing = 0.5.sp
        )
        if (price > 0) {
            Text(
                text = String.format("%.1f", price),
                color = color,
                fontSize = 10.sp,
                fontWeight = FontWeight.Bold,
                fontFamily = FontFamily.Monospace
            )
        }
    }
}

@Composable
private fun MiniMTFBar(mtf: Map<String, TimeframeSignal>) {
    val timeframes = listOf("M1", "M3", "M5", "M15", "M30", "H1", "H4")

    Row(
        modifier = Modifier.fillMaxWidth(),
        horizontalArrangement = Arrangement.SpaceBetween
    ) {
        timeframes.forEach { tf ->
            val tfSignal = mtf[tf]
            val color = when (tfSignal?.signal) {
                "BUY" -> SignalBuy
                "SELL" -> SignalSell
                else -> SignalNeutral
            }
            Column(horizontalAlignment = Alignment.CenterHorizontally) {
                Text(
                    text = tf,
                    color = NexusTextMuted,
                    fontSize = 7.sp
                )
                Box(
                    modifier = Modifier
                        .size(24.dp, 4.dp)
                        .clip(RoundedCornerShape(2.dp))
                        .background(color.copy(alpha = 0.6f))
                )
            }
        }
    }
}

// ============================================================================
// PRO MODE
// ============================================================================

@Composable
fun ProOverlay(
    signal: SignalData?,
    market: MarketData,
    mtf: Map<String, TimeframeSignal>,
    regime: RegimeData,
    connection: ConnectionState,
    signalStore: SignalStore,
    freshness: SignalFreshness,
    signalAge: Long,
    marketDataAge: Long,
    aiStatus: AiStatus,
    onClose: () -> Unit,
    onSwitchMode: (OverlayMode) -> Unit
) {
    val bgShape = RoundedCornerShape(12.dp)
    val signalColor = when (freshness) {
        SignalFreshness.INVALID -> InvalidRed
        SignalFreshness.STALE -> StaleYellow
        SignalFreshness.NO_SIGNAL -> SignalWait
        SignalFreshness.FRESH -> when (signal?.signalType) {
            "BUY" -> SignalBuy
            "SELL" -> SignalSell
            else -> SignalWait
        }
    }
    val signalHistory by signalStore.signalHistory.collectAsState()
    var showEvidence by remember { mutableStateOf(false) }

    Box(
        modifier = Modifier
            .width(400.dp)
            .clip(bgShape)
            .background(NexusSurface.copy(alpha = 0.95f))
            .border(1.dp, NexusAccent.copy(alpha = 0.3f), bgShape)
            .padding(12.dp)
    ) {
        Column {
            // Header with close/mode controls
            ProHeader(connection, market, freshness, aiStatus, onClose, onSwitchMode)

            Spacer(modifier = Modifier.height(8.dp))

            // Signal card (larger) with freshness awareness
            StandardSignalCard(signal, signalColor, freshness)

            Spacer(modifier = Modifier.height(8.dp))

            // Freshness bar
            if (freshness != SignalFreshness.NO_SIGNAL) {
                FreshnessBar(
                    freshness = freshness,
                    signalAge = signalAge,
                    marketDataAge = marketDataAge,
                    connection = connection
                )
                Spacer(modifier = Modifier.height(8.dp))
            }

            // Price levels (only when fresh)
            if (signal != null && signal.entry > 0 && freshness != SignalFreshness.INVALID) {
                PriceLevels(signal)
            }

            Spacer(modifier = Modifier.height(10.dp))

            // MTF Matrix (full)
            FullMTFMatrix(mtf)

            Spacer(modifier = Modifier.height(10.dp))

            // Regime indicator
            if (regime.type != "unknown") {
                RegimeIndicator(regime)
            }

            // Section 81: WHY? tap to show evidence graph
            if (signal != null && freshness == SignalFreshness.FRESH &&
                (signal.evidence.isNotEmpty() || signal.counterEvidence.isNotEmpty())
            ) {
                Spacer(modifier = Modifier.height(8.dp))
                Row(
                    modifier = Modifier
                        .fillMaxWidth()
                        .clip(RoundedCornerShape(6.dp))
                        .background(NexusBackground)
                        .clickable { showEvidence = !showEvidence }
                        .padding(horizontal = 10.dp, vertical = 6.dp),
                    horizontalArrangement = Arrangement.SpaceBetween,
                    verticalAlignment = Alignment.CenterVertically
                ) {
                    Text(
                        text = "WHY?",
                        color = NexusAccent,
                        fontSize = 10.sp,
                        fontWeight = FontWeight.Bold,
                        letterSpacing = 1.sp
                    )
                    Icon(
                        imageVector = if (showEvidence) Icons.Default.ExpandLess else Icons.Default.ExpandMore,
                        contentDescription = null,
                        tint = NexusAccent,
                        modifier = Modifier.size(14.dp)
                    )
                }

                // Evidence graph (supporting + counter evidence)
                if (showEvidence) {
                    Spacer(modifier = Modifier.height(4.dp))
                    EvidenceGraph(signal)
                }
            }

            Spacer(modifier = Modifier.height(8.dp))

            // Recent signals
            if (signalHistory.isNotEmpty()) {
                RecentSignals(signalHistory.take(3))
            }
        }
    }
}

@Composable
private fun ProHeader(
    connection: ConnectionState,
    market: MarketData,
    freshness: SignalFreshness,
    aiStatus: AiStatus,
    onClose: () -> Unit,
    onSwitchMode: (OverlayMode) -> Unit
) {
    Row(
        modifier = Modifier.fillMaxWidth(),
        horizontalArrangement = Arrangement.SpaceBetween,
        verticalAlignment = Alignment.CenterVertically
    ) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Box(
                modifier = Modifier
                    .size(8.dp)
                    .clip(RoundedCornerShape(4.dp))
                    .background(
                        when (connection) {
                            ConnectionState.CONNECTED -> NexusSuccess
                            ConnectionState.CONNECTING -> NexusWarning
                            else -> NexusError
                        }
                    )
            )
            Spacer(modifier = Modifier.width(6.dp))
            Text(
                text = "NEXUS PRO",
                color = NexusAccent,
                fontSize = 11.sp,
                fontWeight = FontWeight.Bold,
                letterSpacing = 1.5.sp
            )
            // AI status
            Spacer(modifier = Modifier.width(6.dp))
            Text(
                text = "AI:${if (aiStatus == AiStatus.ONLINE) "ON" else "OFF"}",
                color = if (aiStatus == AiStatus.ONLINE) NexusSuccess else NexusTextMuted,
                fontSize = 8.sp,
                fontFamily = FontFamily.Monospace
            )
        }

        Row(verticalAlignment = Alignment.CenterVertically) {
            // Freshness badge
            if (freshness != SignalFreshness.FRESH) {
                Text(
                    text = when (freshness) {
                        SignalFreshness.STALE -> "⚠ STALE"
                        SignalFreshness.INVALID -> "✗ DATA STALE"
                        SignalFreshness.NO_SIGNAL -> "— NO SIGNAL"
                        else -> ""
                    },
                    color = when (freshness) {
                        SignalFreshness.STALE -> StaleYellow
                        SignalFreshness.INVALID -> InvalidRed
                        else -> NexusTextMuted
                    },
                    fontSize = 8.sp,
                    fontWeight = FontWeight.Bold
                )
                Spacer(modifier = Modifier.width(6.dp))
            }
            Text(
                text = if (market.bid > 0) "${String.format("%.2f", market.bid)} | sp:${String.format("%.2f", market.spread)}" else "",
                color = NexusTextMuted,
                fontSize = 9.sp,
                fontFamily = FontFamily.Monospace
            )
            Spacer(modifier = Modifier.width(8.dp))
            Icon(
                imageVector = Icons.Default.KeyboardArrowDown,
                contentDescription = "Compact",
                tint = NexusTextMuted,
                modifier = Modifier
                    .size(14.dp)
                    .clickable { onSwitchMode(OverlayMode.STANDARD) }
            )
            Icon(
                imageVector = Icons.Default.Close,
                contentDescription = "Close",
                tint = NexusTextMuted,
                modifier = Modifier
                    .size(14.dp)
                    .clickable { onClose() }
            )
        }
    }
}

@Composable
private fun FullMTFMatrix(mtf: Map<String, TimeframeSignal>) {
    val timeframes = listOf("M1", "M3", "M5", "M15", "M30", "H1", "H4")

    Column {
        Text(
            text = "MULTI-TIMEFRAME MATRIX",
            color = NexusTextMuted,
            fontSize = 9.sp,
            letterSpacing = 1.sp
        )
        Spacer(modifier = Modifier.height(4.dp))
        Row(
            modifier = Modifier.fillMaxWidth(),
            horizontalArrangement = Arrangement.SpaceBetween
        ) {
            timeframes.forEach { tf ->
                val tfSignal = mtf[tf]
                Column(
                    horizontalAlignment = Alignment.CenterHorizontally,
                    modifier = Modifier
                        .weight(1f)
                        .clip(RoundedCornerShape(4.dp))
                        .background(NexusBackground)
                        .padding(vertical = 4.dp)
                ) {
                    Text(
                        text = tf,
                        color = NexusTextMuted,
                        fontSize = 8.sp
                    )
                    Spacer(modifier = Modifier.height(2.dp))
                    Text(
                        text = when (tfSignal?.signal) {
                            "BUY" -> "▲"
                            "SELL" -> "▼"
                            else -> "●"
                        },
                        color = when (tfSignal?.signal) {
                            "BUY" -> SignalBuy
                            "SELL" -> SignalSell
                            else -> SignalNeutral
                        },
                        fontSize = 12.sp,
                        fontWeight = FontWeight.Bold
                    )
                    Text(
                        text = String.format("%.0f%%", (tfSignal?.strength ?: 0.0) * 100),
                        color = NexusTextMuted,
                        fontSize = 7.sp,
                        fontFamily = FontFamily.Monospace
                    )
                }
                Spacer(modifier = Modifier.width(2.dp))
            }
        }
    }
}

@Composable
private fun RegimeIndicator(regime: RegimeData) {
    val color = when {
        regime.type.contains("trending_up", true) -> RegimeTrendingUp
        regime.type.contains("trending_down", true) -> RegimeTrendingDown
        regime.type.contains("ranging", true) -> RegimeRanging
        regime.type.contains("volatile", true) -> RegimeVolatile
        else -> SignalNeutral
    }

    Row(
        modifier = Modifier
            .fillMaxWidth()
            .clip(RoundedCornerShape(6.dp))
            .background(color.copy(alpha = 0.1f))
            .padding(8.dp),
        verticalAlignment = Alignment.CenterVertically
    ) {
        Box(
            modifier = Modifier
                .size(8.dp)
                .clip(RoundedCornerShape(4.dp))
                .background(color)
        )
        Spacer(modifier = Modifier.width(8.dp))
        Column {
            Text(
                text = "REGIME: ${regime.type.uppercase()}",
                color = color,
                fontSize = 10.sp,
                fontWeight = FontWeight.Bold,
                letterSpacing = 0.5.sp
            )
            if (regime.description.isNotEmpty()) {
                Text(
                    text = regime.description,
                    color = NexusTextMuted,
                    fontSize = 9.sp
                )
            }
        }
        Spacer(modifier = Modifier.weight(1f))
        Text(
            text = "${(regime.strength * 100).toInt()}%",
            color = color,
            fontSize = 10.sp,
            fontFamily = FontFamily.Monospace
        )
    }
}

/**
 * Section 26/27: Evidence Graph showing supporting + counter evidence.
 * User taps "WHY?" to see reasoning chain.
 */
@Composable
private fun EvidenceGraph(signal: SignalData) {
    Column(
        modifier = Modifier
            .fillMaxWidth()
            .clip(RoundedCornerShape(6.dp))
            .background(NexusBackground)
            .padding(8.dp)
    ) {
        // Supporting evidence
        if (signal.evidence.isNotEmpty()) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Text(
                    text = "▲",
                    color = SignalBuy,
                    fontSize = 10.sp,
                    fontWeight = FontWeight.Bold
                )
                Spacer(modifier = Modifier.width(4.dp))
                Text(
                    text = "SUPPORTING (${signal.evidence.size})",
                    color = SignalBuy,
                    fontSize = 8.sp,
                    fontWeight = FontWeight.Bold,
                    letterSpacing = 0.5.sp
                )
            }
            signal.evidence.forEach { item ->
                Text(
                    text = "  + $item",
                    color = NexusTextSecondary,
                    fontSize = 8.sp,
                    modifier = Modifier.padding(start = 12.dp)
                )
            }
            Spacer(modifier = Modifier.height(6.dp))
        }

        // Counter evidence
        if (signal.counterEvidence.isNotEmpty()) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Text(
                    text = "▼",
                    color = SignalSell,
                    fontSize = 10.sp,
                    fontWeight = FontWeight.Bold
                )
                Spacer(modifier = Modifier.width(4.dp))
                Text(
                    text = "COUNTER (${signal.counterEvidence.size})",
                    color = SignalSell,
                    fontSize = 8.sp,
                    fontWeight = FontWeight.Bold,
                    letterSpacing = 0.5.sp
                )
            }
            signal.counterEvidence.forEach { item ->
                Text(
                    text = "  - $item",
                    color = NexusTextSecondary,
                    fontSize = 8.sp,
                    modifier = Modifier.padding(start = 12.dp)
                )
            }
            Spacer(modifier = Modifier.height(6.dp))
        }

        // Invalidation conditions
        if (signal.invalidations.isNotEmpty()) {
            Text(
                text = "INVALIDATION:",
                color = NexusError,
                fontSize = 8.sp,
                fontWeight = FontWeight.Bold,
                letterSpacing = 0.5.sp
            )
            signal.invalidations.forEach { item ->
                Text(
                    text = "  ✗ $item",
                    color = NexusTextMuted,
                    fontSize = 8.sp,
                    modifier = Modifier.padding(start = 12.dp)
                )
            }
        }
    }
}

@Composable
private fun RecentSignals(signals: List<SignalData>) {
    Column {
        Text(
            text = "RECENT SIGNALS",
            color = NexusTextMuted,
            fontSize = 9.sp,
            letterSpacing = 1.sp
        )
        Spacer(modifier = Modifier.height(4.dp))
        signals.forEach { sig ->
            val color = when (sig.signalType) {
                "BUY" -> SignalBuy
                "SELL" -> SignalSell
                else -> SignalWait
            }
            Row(
                modifier = Modifier
                    .fillMaxWidth()
                    .padding(vertical = 2.dp),
                horizontalArrangement = Arrangement.SpaceBetween
            ) {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Box(
                        modifier = Modifier
                            .size(6.dp)
                            .clip(RoundedCornerShape(3.dp))
                            .background(color)
                    )
                    Spacer(modifier = Modifier.width(6.dp))
                    Text(
                        text = sig.signalType,
                        color = color,
                        fontSize = 9.sp,
                        fontWeight = FontWeight.Bold
                    )
                    Spacer(modifier = Modifier.width(4.dp))
                    Text(
                        text = String.format("%.2f", sig.entry),
                        color = NexusTextSecondary,
                        fontSize = 9.sp,
                        fontFamily = FontFamily.Monospace
                    )
                }
                Text(
                    text = sig.timeframe,
                    color = NexusTextMuted,
                    fontSize = 8.sp
                )
            }
        }
    }
}
