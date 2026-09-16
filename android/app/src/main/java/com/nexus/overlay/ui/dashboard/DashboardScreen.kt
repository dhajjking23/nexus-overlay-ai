package com.nexus.overlay.ui.dashboard

import androidx.compose.animation.*
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.nexus.overlay.data.*
import com.nexus.overlay.ui.theme.*
import com.nexus.overlay.viewmodel.OverlayMode
import com.nexus.overlay.viewmodel.UiState

// --- Freshness colors for dashboard ---
private val StaleYellow = Color(0xFFFFC107)
private val InvalidRed = Color(0xFFFF5252)
private val FreshGreen = Color(0xFF00E676)

/**
 * Format age in milliseconds to human-readable string.
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
 * Full dashboard screen showing all signal information,
 * MTF matrix, regime analysis, evidence graph, and freshness indicators.
 *
 * Section 81: DECISION SCORE, ENTRY, SL, TP1/TP2/TP3, RR, REGIME, MTF, AI STATUS, DATA AGE, SIGNAL AGE.
 * Section 82: Shows WAIT reason for WAIT decisions.
 * Section 26/27: WHY? tap to show evidence graph.
 */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun DashboardScreen(
    uiState: UiState,
    onNavigateToSettings: () -> Unit,
    onToggleOverlay: () -> Unit,
    onRefresh: () -> Unit
) {
    val signal = uiState.currentSignal
    val freshness = uiState.signalFreshness
    val signalAge = uiState.signalAge
    val marketDataAge = uiState.marketDataAge
    val aiStatus = uiState.aiStatus

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

    Scaffold(
        topBar = {
            TopAppBar(
                title = {
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        // Connection status dot
                        Box(
                            modifier = Modifier
                                .size(8.dp)
                                .clip(CircleShape)
                                .background(
                                    when (uiState.connectionState) {
                                        ConnectionState.CONNECTED -> NexusSuccess
                                        ConnectionState.CONNECTING -> NexusWarning
                                        else -> NexusError
                                    }
                                )
                        )
                        Spacer(modifier = Modifier.width(8.dp))
                        Text("NEXUS OVERLAY", letterSpacing = 1.sp)
                        // AI status badge
                        Spacer(modifier = Modifier.width(12.dp))
                        Text(
                            text = "AI: ${if (aiStatus == AiStatus.ONLINE) "ONLINE" else "OFFLINE"}",
                            color = if (aiStatus == AiStatus.ONLINE) NexusSuccess else NexusTextMuted,
                            fontSize = 10.sp,
                            fontFamily = FontFamily.Monospace,
                            fontWeight = FontWeight.Bold
                        )
                    }
                },
                actions = {
                    // Overlay toggle
                    IconButton(onClick = onToggleOverlay) {
                        Icon(
                            imageVector = if (uiState.isOverlayRunning)
                                Icons.Default.VisibilityOff else Icons.Default.Visibility,
                            contentDescription = "Toggle Overlay",
                            tint = if (uiState.isOverlayRunning) NexusAccent else NexusTextMuted
                        )
                    }
                    IconButton(onClick = onRefresh) {
                        Icon(
                            imageVector = Icons.Default.Refresh,
                            contentDescription = "Refresh",
                            tint = NexusTextSecondary
                        )
                    }
                    IconButton(onClick = onNavigateToSettings) {
                        Icon(
                            imageVector = Icons.Default.Settings,
                            contentDescription = "Settings",
                            tint = NexusTextSecondary
                        )
                    }
                },
                colors = TopAppBarDefaults.topAppBarColors(
                    containerColor = NexusSurface,
                    titleContentColor = NexusTextPrimary
                )
            )
        },
        containerColor = NexusBackground
    ) { padding ->
        LazyColumn(
            modifier = Modifier
                .fillMaxSize()
                .padding(padding)
                .padding(horizontal = 16.dp),
            verticalArrangement = Arrangement.spacedBy(12.dp),
            contentPadding = PaddingValues(vertical = 16.dp)
        ) {
            // === MARKET DATA HEADER ===
            item {
                MarketDataHeader(uiState.marketData, uiState.symbolInfo, marketDataAge)
            }

            // === FRESHNESS STATUS BAR ===
            if (freshness != SignalFreshness.NO_SIGNAL) {
                item {
                    FreshnessStatusBar(freshness, signalAge, marketDataAge, uiState.connectionState)
                }
            }

            // === CURRENT SIGNAL ===
            item {
                SignalCard(signal, signalColor, freshness)
            }

            // === WAIT REASON ===
            if (signal?.decision == "WAIT" && signal.waitReason.isNotEmpty()) {
                item {
                    WaitReasonCard(signal.waitReason)
                }
            }

            // === PRICE LEVELS ===
            if (signal?.entry != null && signal.entry > 0 && freshness != SignalFreshness.INVALID) {
                item {
                    PriceLevelsCard(signal)
                }
            }

            // === EVIDENCE GRAPH (WHY?) ===
            if (signal != null && freshness == SignalFreshness.FRESH &&
                (signal.evidence.isNotEmpty() || signal.counterEvidence.isNotEmpty())
            ) {
                item {
                    EvidenceGraphCard(signal)
                }
            }

            // === MTF MATRIX ===
            item {
                MTFMatrixCard(uiState.mtfMatrix)
            }

            // === REGIME ===
            if (uiState.regime.type != "unknown") {
                item {
                    RegimeCard(uiState.regime)
                }
            }

            // === SYSTEM STATUS ===
            if (uiState.systemStatus.isNotEmpty()) {
                item {
                    SystemStatusCard(uiState.systemStatus)
                }
            }

            // === SIGNAL HISTORY ===
            if (uiState.signalHistory.isNotEmpty()) {
                item {
                    Text(
                        text = "SIGNAL HISTORY",
                        color = NexusTextMuted,
                        fontSize = 11.sp,
                        fontWeight = FontWeight.Bold,
                        letterSpacing = 1.sp,
                        modifier = Modifier.padding(top = 8.dp)
                    )
                }
                items(uiState.signalHistory.take(10)) { sig ->
                    SignalHistoryItem(sig)
                }
            }

            // Bottom spacer for navigation bar
            item { Spacer(modifier = Modifier.height(16.dp)) }
        }
    }
}

@Composable
private fun MarketDataHeader(market: MarketData, symbolInfo: SymbolInfo?, dataAge: Long) {
    Card(
        modifier = Modifier.fillMaxWidth(),
        colors = CardDefaults.cardColors(containerColor = NexusSurface),
        shape = RoundedCornerShape(12.dp)
    ) {
        Column(modifier = Modifier.padding(16.dp)) {
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween
            ) {
                Text(
                    text = "XAUUSD",
                    color = NexusTextPrimary,
                    fontSize = 16.sp,
                    fontWeight = FontWeight.Bold,
                    letterSpacing = 1.sp
                )
                if (symbolInfo != null) {
                    Text(
                        text = "spread: ${String.format("%.2f", market.spread)} | pts: ${symbolInfo.point}",
                        color = NexusTextMuted,
                        fontSize = 10.sp,
                        fontFamily = FontFamily.Monospace
                    )
                }
            }

            Spacer(modifier = Modifier.height(8.dp))

            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceEvenly
            ) {
                PriceColumn("BID", market.bid, NexusTextPrimary)
                PriceColumn("ASK", market.ask, NexusTextPrimary)
                PriceColumn("SPREAD", market.spread, NexusTextSecondary)
            }

            // Section 81: Data age
            Spacer(modifier = Modifier.height(4.dp))
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween
            ) {
                if (market.lastUpdate > 0) {
                    Text(
                        text = "Last: ${java.text.SimpleDateFormat("HH:mm:ss", java.util.Locale.US).format(java.util.Date(market.lastUpdate))}",
                        color = NexusTextMuted,
                        fontSize = 9.sp
                    )
                }
                // Section 42: Data age indicator
                if (dataAge > 0) {
                    val ageColor = when {
                        dataAge > SignalStore.CRITICAL_THRESHOLD_MS -> InvalidRed
                        dataAge > SignalStore.MARKET_STALE_THRESHOLD_MS -> StaleYellow
                        else -> NexusSuccess
                    }
                    Text(
                        text = "DATA AGE: ${formatAge(dataAge)}",
                        color = ageColor,
                        fontSize = 9.sp,
                        fontFamily = FontFamily.Monospace,
                        fontWeight = FontWeight.Bold
                    )
                }
            }
        }
    }
}

@Composable
private fun PriceColumn(label: String, value: Double, valueColor: Color) {
    Column(horizontalAlignment = Alignment.CenterHorizontally) {
        Text(
            text = label,
            color = NexusTextMuted,
            fontSize = 9.sp,
            letterSpacing = 0.5.sp
        )
        Text(
            text = if (value > 0) String.format("%.2f", value) else "---",
            color = valueColor,
            fontSize = 18.sp,
            fontWeight = FontWeight.Bold,
            fontFamily = FontFamily.Monospace
        )
    }
}

/**
 * Section 41/42: Freshness status bar on dashboard.
 */
@Composable
private fun FreshnessStatusBar(
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

    Card(
        modifier = Modifier.fillMaxWidth(),
        colors = CardDefaults.cardColors(containerColor = barColor.copy(alpha = 0.1f)),
        shape = RoundedCornerShape(8.dp)
    ) {
        Row(
            modifier = Modifier
                .fillMaxWidth()
                .padding(horizontal = 12.dp, vertical = 8.dp),
            horizontalArrangement = Arrangement.SpaceBetween,
            verticalAlignment = Alignment.CenterVertically
        ) {
            // Freshness label
            Text(
                text = when (freshness) {
                    SignalFreshness.FRESH -> "● FRESH"
                    SignalFreshness.STALE -> "● STALE"
                    SignalFreshness.INVALID -> "✗ DATA STALE"
                    SignalFreshness.NO_SIGNAL -> "— NO SIGNAL"
                },
                color = barColor,
                fontSize = 11.sp,
                fontWeight = FontWeight.Bold,
                letterSpacing = 0.5.sp
            )

            // Ages
            Text(
                text = "SIG: ${formatAge(signalAge)} | MKT: ${formatAge(marketDataAge)}",
                color = NexusTextSecondary,
                fontSize = 9.sp,
                fontFamily = FontFamily.Monospace
            )

            // Connection
            Text(
                text = when (connection) {
                    ConnectionState.CONNECTED -> "CONN ✓"
                    ConnectionState.CONNECTING -> "CONN ..."
                    ConnectionState.STALE -> "CONN ⚠"
                    ConnectionState.ERROR -> "CONN ✗"
                    ConnectionState.DISCONNECTED -> "CONN ✗"
                },
                color = when (connection) {
                    ConnectionState.CONNECTED -> NexusSuccess
                    ConnectionState.CONNECTING -> NexusWarning
                    else -> NexusError
                },
                fontSize = 9.sp,
                fontFamily = FontFamily.Monospace,
                fontWeight = FontWeight.Bold
            )
        }
    }
}

/**
 * Section 81/82: Signal card with decision score (not confidence %).
 */
@Composable
private fun SignalCard(signal: SignalData?, signalColor: Color, freshness: SignalFreshness) {
    Card(
        modifier = Modifier.fillMaxWidth(),
        colors = CardDefaults.cardColors(containerColor = NexusSurface),
        shape = RoundedCornerShape(12.dp)
    ) {
        Column(modifier = Modifier.padding(16.dp)) {
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically
            ) {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Box(
                        modifier = Modifier
                            .size(12.dp)
                            .clip(CircleShape)
                            .background(signalColor)
                    )
                    Spacer(modifier = Modifier.width(8.dp))
                    // Section 82: Show DATA STALE instead of old signal when INVALID
                    val displayText = when (freshness) {
                        SignalFreshness.INVALID -> "DATA STALE"
                        SignalFreshness.STALE -> (signal?.signalType ?: "NO SIGNAL") + " ⚠"
                        SignalFreshness.NO_SIGNAL -> "NO SIGNAL"
                        SignalFreshness.FRESH -> signal?.signalType ?: "NO SIGNAL"
                    }
                    Text(
                        text = displayText,
                        color = signalColor,
                        fontSize = 20.sp,
                        fontWeight = FontWeight.Bold
                    )
                }

                // Section 81: Decision score (not confidence %)
                if (freshness == SignalFreshness.FRESH && signal != null) {
                    val score = signal.decisionScore
                    if (score > 0) {
                        Column(horizontalAlignment = Alignment.End) {
                            Text(
                                text = "DECISION SCORE",
                                color = NexusTextMuted,
                                fontSize = 8.sp,
                                letterSpacing = 1.sp
                            )
                            Text(
                                text = "${String.format("%.0f", score)}/100",
                                color = signalColor,
                                fontSize = 18.sp,
                                fontWeight = FontWeight.Bold,
                                fontFamily = FontFamily.Monospace
                            )
                        }
                    }
                }
            }

            // Signal age indicator
            if (freshness != SignalFreshness.NO_SIGNAL && signal != null) {
                Spacer(modifier = Modifier.height(4.dp))
                val ageColor = when (freshness) {
                    SignalFreshness.FRESH -> NexusSuccess
                    SignalFreshness.STALE -> StaleYellow
                    SignalFreshness.INVALID -> InvalidRed
                    SignalFreshness.NO_SIGNAL -> NexusTextMuted
                }
                Text(
                    text = "Signal age: ${formatAge(System.currentTimeMillis() - signal.timestamp)}",
                    color = ageColor,
                    fontSize = 11.sp,
                    fontFamily = FontFamily.Monospace
                )
            }
        }
    }
}

/**
 * Section 82: Show WAIT reason.
 */
@Composable
private fun WaitReasonCard(reason: String) {
    Card(
        modifier = Modifier.fillMaxWidth(),
        colors = CardDefaults.cardColors(containerColor = NexusSurfaceVariant),
        shape = RoundedCornerShape(12.dp)
    ) {
        Row(
            modifier = Modifier.padding(12.dp),
            verticalAlignment = Alignment.CenterVertically
        ) {
            Text(
                text = "⬡",
                color = NexusWarning,
                fontSize = 16.sp
            )
            Spacer(modifier = Modifier.width(8.dp))
            Column {
                Text(
                    text = "WAIT REASON",
                    color = NexusWarning,
                    fontSize = 9.sp,
                    fontWeight = FontWeight.Bold,
                    letterSpacing = 1.sp
                )
                Text(
                    text = reason,
                    color = NexusTextPrimary,
                    fontSize = 14.sp,
                    fontWeight = FontWeight.Bold
                )
            }
        }
    }
}

/**
 * Section 81: Price levels card showing ENTRY, SL, TP1/TP2/TP3, RR.
 */
@Composable
private fun PriceLevelsCard(signal: SignalData) {
    Card(
        modifier = Modifier.fillMaxWidth(),
        colors = CardDefaults.cardColors(containerColor = NexusSurface),
        shape = RoundedCornerShape(12.dp)
    ) {
        Column(modifier = Modifier.padding(16.dp)) {
            Text(
                text = "PRICE LEVELS",
                color = NexusTextMuted,
                fontSize = 11.sp,
                fontWeight = FontWeight.Bold,
                letterSpacing = 1.sp
            )
            Spacer(modifier = Modifier.height(8.dp))

            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceEvenly
            ) {
                LevelColumn("ENTRY", signal.entry, EntryLine)
                LevelColumn("SL", signal.sl, StopLossLine)
                LevelColumn("TP1", signal.tp1, TP1Line)
                LevelColumn("TP2", signal.tp2, TP2Line)
                LevelColumn("TP3", signal.tp3, TP3Line)
            }

            // Risk/Reward (from backend or calculated)
            Spacer(modifier = Modifier.height(8.dp))
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.Center
            ) {
                val rrDisplay = if (signal.rr > 0) {
                    signal.rr
                } else if (signal.entry > 0 && signal.sl > 0 && signal.tp1 > 0) {
                    val risk = Math.abs(signal.entry - signal.sl)
                    val reward = Math.abs(signal.tp1 - signal.entry)
                    if (risk > 0) reward / risk else 0.0
                } else 0.0

                if (rrDisplay > 0) {
                    Text(
                        text = "R:R = 1:${String.format("%.1f", rrDisplay)}",
                        color = if (rrDisplay >= 2.0) NexusSuccess else if (rrDisplay >= 1.0) NexusWarning else NexusError,
                        fontSize = 12.sp,
                        fontWeight = FontWeight.Bold,
                        fontFamily = FontFamily.Monospace
                    )
                }
            }
        }
    }
}

@Composable
private fun LevelColumn(label: String, price: Double, color: Color) {
    Column(horizontalAlignment = Alignment.CenterHorizontally) {
        Text(
            text = label,
            color = color.copy(alpha = 0.7f),
            fontSize = 9.sp,
            letterSpacing = 0.5.sp
        )
        Spacer(modifier = Modifier.height(2.dp))
        Box(
            modifier = Modifier
                .width(1.dp)
                .height(12.dp)
                .background(color.copy(alpha = 0.3f))
        )
        Text(
            text = if (price > 0) String.format("%.1f", price) else "---",
            color = color,
            fontSize = 12.sp,
            fontWeight = FontWeight.Bold,
            fontFamily = FontFamily.Monospace
        )
    }
}

/**
 * Section 26/27/81: Evidence graph card with supporting + counter evidence.
 * User taps "WHY?" to see reasoning chain.
 */
@Composable
private fun EvidenceGraphCard(signal: SignalData) {
    var expanded by remember { mutableStateOf(false) }

    Card(
        modifier = Modifier.fillMaxWidth(),
        colors = CardDefaults.cardColors(containerColor = NexusSurface),
        shape = RoundedCornerShape(12.dp)
    ) {
        Column(modifier = Modifier.padding(16.dp)) {
            // WHY? header (tappable)
            Row(
                modifier = Modifier
                    .fillMaxWidth()
                    .clickable { expanded = !expanded },
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically
            ) {
                Text(
                    text = "WHY ${signal.signalType}?",
                    color = NexusAccent,
                    fontSize = 13.sp,
                    fontWeight = FontWeight.Bold,
                    letterSpacing = 1.sp
                )
                Icon(
                    imageVector = if (expanded) Icons.Default.ExpandLess else Icons.Default.ExpandMore,
                    contentDescription = if (expanded) "Collapse" else "Expand",
                    tint = NexusAccent,
                    modifier = Modifier.size(18.dp)
                )
            }

            // Collapsed preview: top evidence items
            if (!expanded) {
                Spacer(modifier = Modifier.height(6.dp))
                signal.evidence.take(3).forEach { item ->
                    Text(
                        text = "+ $item",
                        color = NexusTextSecondary,
                        fontSize = 11.sp,
                        maxLines = 1
                    )
                }
                if (signal.counterEvidence.isNotEmpty()) {
                    signal.counterEvidence.take(2).forEach { item ->
                        Text(
                            text = "- $item",
                            color = NexusTextSecondary,
                            fontSize = 11.sp,
                            maxLines = 1
                        )
                    }
                }
            }

            // Expanded evidence graph
            if (expanded) {
                Spacer(modifier = Modifier.height(8.dp))

                // Supporting evidence
                if (signal.evidence.isNotEmpty()) {
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        Text(
                            text = "▲ SUPPORTING",
                            color = SignalBuy,
                            fontSize = 11.sp,
                            fontWeight = FontWeight.Bold,
                            letterSpacing = 0.5.sp
                        )
                        Spacer(modifier = Modifier.width(4.dp))
                        Text(
                            text = "(${signal.evidence.size})",
                            color = NexusTextMuted,
                            fontSize = 10.sp
                        )
                    }
                    Spacer(modifier = Modifier.height(4.dp))
                    signal.evidence.forEach { item ->
                        Text(
                            text = "  + $item",
                            color = NexusTextSecondary,
                            fontSize = 11.sp,
                            modifier = Modifier.padding(start = 12.dp)
                        )
                    }
                    Spacer(modifier = Modifier.height(8.dp))
                }

                // Counter evidence
                if (signal.counterEvidence.isNotEmpty()) {
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        Text(
                            text = "▼ COUNTER",
                            color = SignalSell,
                            fontSize = 11.sp,
                            fontWeight = FontWeight.Bold,
                            letterSpacing = 0.5.sp
                        )
                        Spacer(modifier = Modifier.width(4.dp))
                        Text(
                            text = "(${signal.counterEvidence.size})",
                            color = NexusTextMuted,
                            fontSize = 10.sp
                        )
                    }
                    Spacer(modifier = Modifier.height(4.dp))
                    signal.counterEvidence.forEach { item ->
                        Text(
                            text = "  - $item",
                            color = NexusTextSecondary,
                            fontSize = 11.sp,
                            modifier = Modifier.padding(start = 12.dp)
                        )
                    }
                    Spacer(modifier = Modifier.height(8.dp))
                }

                // Invalidation conditions
                if (signal.invalidations.isNotEmpty()) {
                    Text(
                        text = "✗ INVALIDATION CONDITIONS",
                        color = NexusError,
                        fontSize = 11.sp,
                        fontWeight = FontWeight.Bold,
                        letterSpacing = 0.5.sp
                    )
                    Spacer(modifier = Modifier.height(4.dp))
                    signal.invalidations.forEach { item ->
                        Text(
                            text = "  ✗ $item",
                            color = NexusTextMuted,
                            fontSize = 11.sp,
                            modifier = Modifier.padding(start = 12.dp)
                        )
                    }
                }
            }
        }
    }
}

@Composable
private fun MTFMatrixCard(mtf: Map<String, TimeframeSignal>) {
    val timeframes = listOf("M1", "M3", "M5", "M15", "M30", "H1", "H4")

    Card(
        modifier = Modifier.fillMaxWidth(),
        colors = CardDefaults.cardColors(containerColor = NexusSurface),
        shape = RoundedCornerShape(12.dp)
    ) {
        Column(modifier = Modifier.padding(16.dp)) {
            Text(
                text = "MULTI-TIMEFRAME ANALYSIS",
                color = NexusTextMuted,
                fontSize = 11.sp,
                fontWeight = FontWeight.Bold,
                letterSpacing = 1.sp
            )
            Spacer(modifier = Modifier.height(10.dp))

            // Header row
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween
            ) {
                timeframes.forEach { tf ->
                    Text(
                        text = tf,
                        color = NexusTextMuted,
                        fontSize = 10.sp,
                        fontWeight = FontWeight.Bold,
                        modifier = Modifier.weight(1f),
                        textAlign = androidx.compose.ui.text.style.TextAlign.Center
                    )
                }
            }

            Spacer(modifier = Modifier.height(6.dp))

            // Signal row
            Row(
                modifier = Modifier
                    .fillMaxWidth()
                    .clip(RoundedCornerShape(6.dp))
                    .background(NexusBackground)
                    .padding(vertical = 8.dp),
                horizontalArrangement = Arrangement.SpaceEvenly
            ) {
                timeframes.forEach { tf ->
                    val tfSignal = mtf[tf]
                    val color = when (tfSignal?.signal) {
                        "BUY" -> SignalBuy
                        "SELL" -> SignalSell
                        else -> SignalNeutral
                    }
                    Column(
                        horizontalAlignment = Alignment.CenterHorizontally,
                        modifier = Modifier.weight(1f)
                    ) {
                        Text(
                            text = when (tfSignal?.signal) {
                                "BUY" -> "▲ BUY"
                                "SELL" -> "▼ SELL"
                                else -> "● ---"
                            },
                            color = color,
                            fontSize = 9.sp,
                            fontWeight = FontWeight.Bold
                        )
                        if (tfSignal?.strength != null && tfSignal.strength > 0) {
                            Text(
                                text = "${(tfSignal.strength * 100).toInt()}%",
                                color = NexusTextMuted,
                                fontSize = 8.sp,
                                fontFamily = FontFamily.Monospace
                            )
                        }
                    }
                }
            }
        }
    }
}

/**
 * Section 81: Regime card.
 */
@Composable
private fun RegimeCard(regime: RegimeData) {
    val color = when {
        regime.type.contains("trending_up", true) -> RegimeTrendingUp
        regime.type.contains("trending_down", true) -> RegimeTrendingDown
        regime.type.contains("ranging", true) -> RegimeRanging
        regime.type.contains("volatile", true) -> RegimeVolatile
        else -> SignalNeutral
    }

    Card(
        modifier = Modifier.fillMaxWidth(),
        colors = CardDefaults.cardColors(containerColor = NexusSurface),
        shape = RoundedCornerShape(12.dp)
    ) {
        Row(
            modifier = Modifier
                .fillMaxWidth()
                .padding(16.dp),
            verticalAlignment = Alignment.CenterVertically
        ) {
            Box(
                modifier = Modifier
                    .size(40.dp)
                    .clip(RoundedCornerShape(8.dp))
                    .background(color.copy(alpha = 0.15f)),
                contentAlignment = Alignment.Center
            ) {
                Icon(
                    imageVector = when {
                        regime.type.contains("trending_up", true) -> Icons.Default.TrendingUp
                        regime.type.contains("trending_down", true) -> Icons.Default.TrendingDown
                        else -> Icons.Default.ShowChart
                    },
                    contentDescription = null,
                    tint = color,
                    modifier = Modifier.size(24.dp)
                )
            }
            Spacer(modifier = Modifier.width(12.dp))
            Column(modifier = Modifier.weight(1f)) {
                Text(
                    text = "MARKET REGIME",
                    color = NexusTextMuted,
                    fontSize = 9.sp,
                    letterSpacing = 0.5.sp
                )
                Text(
                    text = regime.type.replace("_", " ").uppercase(),
                    color = color,
                    fontSize = 14.sp,
                    fontWeight = FontWeight.Bold
                )
                if (regime.description.isNotEmpty()) {
                    Text(
                        text = regime.description,
                        color = NexusTextSecondary,
                        fontSize = 11.sp
                    )
                }
            }
            Text(
                text = "${(regime.strength * 100).toInt()}%",
                color = color,
                fontSize = 16.sp,
                fontWeight = FontWeight.Bold,
                fontFamily = FontFamily.Monospace
            )
        }
    }
}

/**
 * System status card showing backend system information.
 */
@Composable
private fun SystemStatusCard(status: String) {
    Card(
        modifier = Modifier.fillMaxWidth(),
        colors = CardDefaults.cardColors(containerColor = NexusSurfaceVariant),
        shape = RoundedCornerShape(12.dp)
    ) {
        Row(
            modifier = Modifier.padding(12.dp),
            verticalAlignment = Alignment.CenterVertically
        ) {
            Box(
                modifier = Modifier
                    .size(8.dp)
                    .clip(CircleShape)
                    .background(NexusAccent)
            )
            Spacer(modifier = Modifier.width(8.dp))
            Text(
                text = "SYSTEM: $status",
                color = NexusTextSecondary,
                fontSize = 10.sp,
                fontFamily = FontFamily.Monospace
            )
        }
    }
}

@Composable
private fun SignalHistoryItem(signal: SignalData) {
    val color = when (signal.signalType) {
        "BUY" -> SignalBuy
        "SELL" -> SignalSell
        else -> SignalWait
    }

    Row(
        modifier = Modifier
            .fillMaxWidth()
            .clip(RoundedCornerShape(8.dp))
            .background(NexusSurface)
            .padding(horizontal = 12.dp, vertical = 8.dp),
        verticalAlignment = Alignment.CenterVertically
    ) {
        Box(
            modifier = Modifier
                .size(8.dp)
                .clip(CircleShape)
                .background(color)
        )
        Spacer(modifier = Modifier.width(8.dp))
        Text(
            text = signal.signalType,
            color = color,
            fontSize = 12.sp,
            fontWeight = FontWeight.Bold,
            modifier = Modifier.width(40.dp)
        )
        Text(
            text = String.format("%.2f", signal.entry),
            color = NexusTextPrimary,
            fontSize = 12.sp,
            fontFamily = FontFamily.Monospace,
            modifier = Modifier.weight(1f)
        )
        Text(
            text = signal.timeframe,
            color = NexusTextMuted,
            fontSize = 10.sp,
            modifier = Modifier.width(40.dp),
            textAlign = androidx.compose.ui.text.style.TextAlign.End
        )
        // Decision score instead of confidence
        if (signal.decisionScore > 0) {
            Text(
                text = "${String.format("%.0f", signal.decisionScore)}",
                color = NexusTextSecondary,
                fontSize = 10.sp,
                fontFamily = FontFamily.Monospace,
                modifier = Modifier.width(36.dp),
                textAlign = androidx.compose.ui.text.style.TextAlign.End
            )
        }
    }
}
