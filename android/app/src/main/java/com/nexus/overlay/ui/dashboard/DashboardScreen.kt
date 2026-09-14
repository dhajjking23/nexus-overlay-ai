package com.nexus.overlay.ui.dashboard

import androidx.compose.animation.*
import androidx.compose.foundation.background
import androidx.compose.foundation.border
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

/**
 * Full dashboard screen showing all signal information,
 * MTF matrix, regime analysis, and evidence.
 */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun DashboardScreen(
    uiState: UiState,
    onNavigateToSettings: () -> Unit,
    onToggleOverlay: () -> Unit,
    onRefresh: () -> Unit
) {
    val signalColor = when (uiState.currentSignal?.signalType) {
        "BUY" -> SignalBuy
        "SELL" -> SignalSell
        else -> SignalWait
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
                MarketDataHeader(uiState.marketData, uiState.symbolInfo)
            }

            // === CURRENT SIGNAL ===
            item {
                SignalCard(uiState.currentSignal, signalColor)
            }

            // === PRICE LEVELS ===
            if (uiState.currentSignal?.entry != null && uiState.currentSignal.entry > 0) {
                item {
                    PriceLevelsCard(uiState.currentSignal)
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

            // === EVIDENCE / REASON ===
            if (uiState.currentSignal?.reason?.isNotEmpty() == true) {
                item {
                    EvidenceCard(uiState.currentSignal.reason)
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
private fun MarketDataHeader(market: MarketData, symbolInfo: SymbolInfo?) {
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

            if (market.lastUpdate > 0) {
                Spacer(modifier = Modifier.height(4.dp))
                Text(
                    text = "Last update: ${java.text.SimpleDateFormat("HH:mm:ss", java.util.Locale.US).format(java.util.Date(market.lastUpdate))}",
                    color = NexusTextMuted,
                    fontSize = 9.sp
                )
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

@Composable
private fun SignalCard(signal: SignalData?, signalColor: Color) {
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
                    Text(
                        text = signal?.signalType ?: "NO SIGNAL",
                        color = signalColor,
                        fontSize = 20.sp,
                        fontWeight = FontWeight.Bold
                    )
                }
                if (signal?.confidence != null && signal.confidence > 0) {
                    Column(horizontalAlignment = Alignment.End) {
                        Text(
                            text = "CONFIDENCE",
                            color = NexusTextMuted,
                            fontSize = 8.sp,
                            letterSpacing = 1.sp
                        )
                        Text(
                            text = "${(signal.confidence * 100).toInt()}%",
                            color = signalColor,
                            fontSize = 18.sp,
                            fontWeight = FontWeight.Bold,
                            fontFamily = FontFamily.Monospace
                        )
                    }
                }
            }

            if (signal?.timeframe?.isNotEmpty() == true) {
                Spacer(modifier = Modifier.height(4.dp))
                Text(
                    text = "Timeframe: ${signal.timeframe}",
                    color = NexusTextSecondary,
                    fontSize = 12.sp
                )
            }
        }
    }
}

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

            // Risk/Reward calculation
            if (signal.entry > 0 && signal.sl > 0 && signal.tp1 > 0) {
                val risk = Math.abs(signal.entry - signal.sl)
                val reward = Math.abs(signal.tp1 - signal.entry)
                val rr = if (risk > 0) reward / risk else 0.0

                Spacer(modifier = Modifier.height(8.dp))
                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.Center
                ) {
                    Text(
                        text = "R:R = 1:${String.format("%.1f", rr)}",
                        color = if (rr >= 2.0) NexusSuccess else if (rr >= 1.0) NexusWarning else NexusError,
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

@Composable
private fun EvidenceCard(reason: String) {
    Card(
        modifier = Modifier.fillMaxWidth(),
        colors = CardDefaults.cardColors(containerColor = NexusSurface),
        shape = RoundedCornerShape(12.dp)
    ) {
        Column(modifier = Modifier.padding(16.dp)) {
            Text(
                text = "SIGNAL EVIDENCE",
                color = NexusTextMuted,
                fontSize = 11.sp,
                fontWeight = FontWeight.Bold,
                letterSpacing = 1.sp
            )
            Spacer(modifier = Modifier.height(8.dp))
            Text(
                text = reason,
                color = NexusTextSecondary,
                fontSize = 12.sp,
                lineHeight = 18.sp
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
        if (signal.confidence > 0) {
            Text(
                text = "${(signal.confidence * 100).toInt()}%",
                color = NexusTextSecondary,
                fontSize = 10.sp,
                fontFamily = FontFamily.Monospace,
                modifier = Modifier.width(36.dp),
                textAlign = androidx.compose.ui.text.style.TextAlign.End
            )
        }
    }
}
