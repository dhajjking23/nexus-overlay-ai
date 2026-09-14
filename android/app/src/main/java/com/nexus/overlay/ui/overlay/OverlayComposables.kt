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

/**
 * Overlay content composables for all three modes:
 * Compact, Standard, and Pro.
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

    Box(modifier = Modifier.alpha(opacity)) {
        when (mode) {
            OverlayMode.COMPACT -> CompactOverlay(
                signal = signal,
                market = market,
                connection = connection,
                onClose = onClose,
                onExpand = { onModeSwitch(OverlayMode.STANDARD) }
            )
            OverlayMode.STANDARD -> StandardOverlay(
                signal = signal,
                market = market,
                mtf = mtf,
                connection = connection,
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
    onClose: () -> Unit,
    onExpand: () -> Unit
) {
    val signalColor = when (signal?.signalType) {
        "BUY" -> SignalBuy
        "SELL" -> SignalSell
        else -> SignalWait
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
                // Pulsing dot
                Box(
                    modifier = Modifier
                        .size(10.dp)
                        .clip(RoundedCornerShape(5.dp))
                        .background(signalColor)
                )
                Spacer(modifier = Modifier.width(8.dp))
                Column {
                    Text(
                        text = signal?.signalType ?: "WAIT",
                        color = signalColor,
                        fontSize = 14.sp,
                        fontWeight = FontWeight.Bold,
                        fontFamily = FontFamily.Monospace
                    )
                    Text(
                        text = if (market.bid > 0) String.format("%.2f", market.bid) else "---",
                        color = NexusTextSecondary,
                        fontSize = 10.sp,
                        fontFamily = FontFamily.Monospace
                    )
                }
            }

            // Entry price
            if (signal?.entry != null && signal.entry > 0) {
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
    onClose: () -> Unit,
    onSwitchMode: (OverlayMode) -> Unit
) {
    val bgShape = RoundedCornerShape(12.dp)
    val signalColor = when (signal?.signalType) {
        "BUY" -> SignalBuy
        "SELL" -> SignalSell
        else -> SignalWait
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
            StandardHeader(signal, market, connection, onClose, onSwitchMode)

            Spacer(modifier = Modifier.height(8.dp))

            // Signal card
            StandardSignalCard(signal, signalColor)

            Spacer(modifier = Modifier.height(8.dp))

            // Price levels
            if (signal != null && signal.entry > 0) {
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
private fun StandardSignalCard(signal: SignalData?, signalColor: Color) {
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
            Text(
                text = signal?.signalType ?: "NO SIGNAL",
                color = signalColor,
                fontSize = 16.sp,
                fontWeight = FontWeight.Bold
            )
            if (signal?.confidence != null && signal.confidence > 0) {
                Text(
                    text = "${(signal.confidence * 100).toInt()}%",
                    color = NexusTextSecondary,
                    fontSize = 12.sp,
                    fontFamily = FontFamily.Monospace
                )
            }
        }
        if (signal?.reason != null && signal.reason.isNotEmpty()) {
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
    onClose: () -> Unit,
    onSwitchMode: (OverlayMode) -> Unit
) {
    val bgShape = RoundedCornerShape(12.dp)
    val signalColor = when (signal?.signalType) {
        "BUY" -> SignalBuy
        "SELL" -> SignalSell
        else -> SignalWait
    }
    val signalHistory by signalStore.signalHistory.collectAsState()

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
            ProHeader(connection, market, onClose, onSwitchMode)

            Spacer(modifier = Modifier.height(8.dp))

            // Signal card (larger)
            StandardSignalCard(signal, signalColor)

            Spacer(modifier = Modifier.height(8.dp))

            // Price levels
            if (signal != null && signal.entry > 0) {
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
        }

        Row {
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
