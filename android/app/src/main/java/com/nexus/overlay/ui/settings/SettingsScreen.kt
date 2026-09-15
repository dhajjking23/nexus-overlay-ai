package com.nexus.overlay.ui.settings

import android.content.Intent
import android.net.Uri
import android.os.Build
import android.provider.Settings
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.nexus.overlay.NexusOverlayApp
import com.nexus.overlay.data.ConnectionState
import com.nexus.overlay.ui.theme.*
import com.nexus.overlay.viewmodel.OverlayMode
import com.nexus.overlay.viewmodel.UiState

/**
 * Settings screen for overlay modes, alert toggles, connection config.
 */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun SettingsScreen(
    uiState: UiState,
    onBack: () -> Unit,
    onServerHostChange: (String) -> Unit,
    onServerPortChange: (String) -> Unit,
    onAuthTokenChange: (String) -> Unit,
    onOverlayModeChange: (OverlayMode) -> Unit,
    onAutoConnectChange: (Boolean) -> Unit,
    onAlertOnSignalChange: (Boolean) -> Unit,
    onAlertOnSLHitChange: (Boolean) -> Unit,
    onOpacityChange: (Float) -> Unit,
    onConnect: () -> Unit,
    onDisconnect: () -> Unit
) {
    val context = LocalContext.current
    var serverHostText by remember { mutableStateOf(uiState.serverHost) }
    var serverPortText by remember { mutableStateOf(uiState.serverPort.toString()) }
    var authTokenText by remember { mutableStateOf(uiState.authToken) }

    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text("SETTINGS") },
                navigationIcon = {
                    IconButton(onClick = onBack) {
                        Icon(
                            imageVector = Icons.Default.ArrowBack,
                            contentDescription = "Back",
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
        Column(
            modifier = Modifier
                .fillMaxSize()
                .padding(padding)
                .verticalScroll(rememberScrollState())
                .padding(16.dp),
            verticalArrangement = Arrangement.spacedBy(16.dp)
        ) {
            // === CONNECTION ===
            SettingsSection("CONNECTION") {
                // Status
                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.SpaceBetween,
                    verticalAlignment = Alignment.CenterVertically
                ) {
                    Text("Status", color = NexusTextSecondary, fontSize = 14.sp)
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        Box(
                            modifier = Modifier
                                .size(8.dp)
                                .clip(RoundedCornerShape(4.dp))
                                .background(
                                    when (uiState.connectionState) {
                                        ConnectionState.CONNECTED -> NexusSuccess
                                        ConnectionState.CONNECTING -> NexusWarning
                                        else -> NexusError
                                    }
                                )
                        )
                        Spacer(modifier = Modifier.width(6.dp))
                        Text(
                            text = uiState.connectionState.name,
                            color = when (uiState.connectionState) {
                                ConnectionState.CONNECTED -> NexusSuccess
                                ConnectionState.CONNECTING -> NexusWarning
                                else -> NexusError
                            },
                            fontSize = 12.sp,
                            fontWeight = FontWeight.Bold
                        )
                    }
                }

                Spacer(modifier = Modifier.height(8.dp))

                // Server Host
                OutlinedTextField(
                    value = serverHostText,
                    onValueChange = {
                        serverHostText = it
                        onServerHostChange(it)
                    },
                    label = { Text("Server Host") },
                    placeholder = { Text("192.168.1.100") },
                    modifier = Modifier.fillMaxWidth(),
                    singleLine = true,
                    colors = OutlinedTextFieldDefaults.colors(
                        focusedBorderColor = NexusAccent,
                        unfocusedBorderColor = NexusTextMuted,
                        focusedLabelColor = NexusAccent,
                        unfocusedLabelColor = NexusTextMuted,
                        cursorColor = NexusAccent,
                        focusedTextColor = NexusTextPrimary,
                        unfocusedTextColor = NexusTextPrimary
                    )
                )

                Spacer(modifier = Modifier.height(8.dp))

                // Server Port
                OutlinedTextField(
                    value = serverPortText,
                    onValueChange = {
                        serverPortText = it
                        onServerPortChange(it)
                    },
                    label = { Text("Server Port") },
                    placeholder = { Text("8765") },
                    modifier = Modifier.fillMaxWidth(),
                    singleLine = true,
                    colors = OutlinedTextFieldDefaults.colors(
                        focusedBorderColor = NexusAccent,
                        unfocusedBorderColor = NexusTextMuted,
                        focusedLabelColor = NexusAccent,
                        unfocusedLabelColor = NexusTextMuted,
                        cursorColor = NexusAccent,
                        focusedTextColor = NexusTextPrimary,
                        unfocusedTextColor = NexusTextPrimary
                    )
                )

                Spacer(modifier = Modifier.height(8.dp))

                // Auth Token
                OutlinedTextField(
                    value = authTokenText,
                    onValueChange = {
                        authTokenText = it
                        onAuthTokenChange(it)
                    },
                    label = { Text("Auth Token") },
                    placeholder = { Text("(optional)") },
                    modifier = Modifier.fillMaxWidth(),
                    singleLine = true,
                    colors = OutlinedTextFieldDefaults.colors(
                        focusedBorderColor = NexusAccent,
                        unfocusedBorderColor = NexusTextMuted,
                        focusedLabelColor = NexusAccent,
                        unfocusedLabelColor = NexusTextMuted,
                        cursorColor = NexusAccent,
                        focusedTextColor = NexusTextPrimary,
                        unfocusedTextColor = NexusTextPrimary
                    )
                )

                Spacer(modifier = Modifier.height(8.dp))

                // Auto-connect toggle
                SettingsToggle(
                    label = "Auto-connect on start",
                    checked = uiState.autoConnect,
                    onCheckedChange = onAutoConnectChange
                )

                Spacer(modifier = Modifier.height(8.dp))

                // Connect / Disconnect button
                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.spacedBy(8.dp)
                ) {
                    Button(
                        onClick = onConnect,
                        modifier = Modifier.weight(1f),
                        colors = ButtonDefaults.buttonColors(
                            containerColor = NexusSuccess
                        ),
                        enabled = uiState.connectionState != ConnectionState.CONNECTED
                    ) {
                        Icon(Icons.Default.Link, contentDescription = null, modifier = Modifier.size(16.dp))
                        Spacer(modifier = Modifier.width(4.dp))
                        Text("Connect")
                    }
                    OutlinedButton(
                        onClick = onDisconnect,
                        modifier = Modifier.weight(1f),
                        colors = ButtonDefaults.outlinedButtonColors(
                            contentColor = NexusError
                        ),
                        enabled = uiState.connectionState == ConnectionState.CONNECTED
                    ) {
                        Icon(Icons.Default.LinkOff, contentDescription = null, modifier = Modifier.size(16.dp))
                        Spacer(modifier = Modifier.width(4.dp))
                        Text("Disconnect")
                    }
                }
            }

            // === OVERLAY ===
            SettingsSection("OVERLAY") {
                // Overlay permission check
                if (!Settings.canDrawOverlays(context)) {
                    Card(
                        modifier = Modifier.fillMaxWidth(),
                        colors = CardDefaults.cardColors(
                            containerColor = NexusWarning.copy(alpha = 0.15f)
                        ),
                        shape = RoundedCornerShape(8.dp)
                    ) {
                        Row(
                            modifier = Modifier.padding(12.dp),
                            verticalAlignment = Alignment.CenterVertically
                        ) {
                            Icon(
                                Icons.Default.Warning,
                                contentDescription = null,
                                tint = NexusWarning,
                                modifier = Modifier.size(20.dp)
                            )
                            Spacer(modifier = Modifier.width(8.dp))
                            Column(modifier = Modifier.weight(1f)) {
                                Text(
                                    "Overlay permission required",
                                    color = NexusWarning,
                                    fontSize = 12.sp,
                                    fontWeight = FontWeight.Bold
                                )
                                Text(
                                    "Grant SYSTEM_ALERT_WINDOW permission to use overlay",
                                    color = NexusTextSecondary,
                                    fontSize = 10.sp
                                )
                            }
                            TextButton(onClick = {
                                val intent = Intent(
                                    Settings.ACTION_MANAGE_OVERLAY_PERMISSION,
                                    Uri.parse("package:${context.packageName}")
                                )
                                context.startActivity(intent)
                            }) {
                                Text("GRANT", color = NexusWarning, fontSize = 12.sp)
                            }
                        }
                    }
                    Spacer(modifier = Modifier.height(8.dp))
                }

                // Overlay mode selector
                Text("Overlay Mode", color = NexusTextSecondary, fontSize = 14.sp)
                Spacer(modifier = Modifier.height(4.dp))
                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.spacedBy(8.dp)
                ) {
                    OverlayMode.entries.forEach { mode ->
                        val isSelected = uiState.overlayMode == mode
                        FilterChip(
                            selected = isSelected,
                            onClick = { onOverlayModeChange(mode) },
                            label = {
                                Text(
                                    mode.name,
                                    fontSize = 12.sp,
                                    fontWeight = if (isSelected) FontWeight.Bold else FontWeight.Normal
                                )
                            },
                            colors = FilterChipDefaults.filterChipColors(
                                selectedContainerColor = NexusAccent.copy(alpha = 0.2f),
                                selectedLabelColor = NexusAccent,
                                containerColor = NexusSurface,
                                labelColor = NexusTextMuted
                            ),
                            modifier = Modifier.weight(1f)
                        )
                    }
                }

                Spacer(modifier = Modifier.height(8.dp))

                // Mode descriptions
                Text(
                    text = when (uiState.overlayMode) {
                        OverlayMode.COMPACT -> "Compact: Small floating pill with signal direction"
                        OverlayMode.STANDARD -> "Standard: Medium panel with signal info and price levels"
                        OverlayMode.PRO -> "Pro: Full dashboard with MTF matrix, regime, and history"
                    },
                    color = NexusTextMuted,
                    fontSize = 11.sp
                )

                Spacer(modifier = Modifier.height(12.dp))

                // Opacity slider
                Text("Opacity: ${(uiState.overlayOpacity * 100).toInt()}%", color = NexusTextSecondary, fontSize = 14.sp)
                Slider(
                    value = uiState.overlayOpacity,
                    onValueChange = onOpacityChange,
                    valueRange = 0.3f..1.0f,
                    steps = 7,
                    colors = SliderDefaults.colors(
                        thumbColor = NexusAccent,
                        activeTrackColor = NexusAccent,
                        inactiveTrackColor = NexusTextMuted
                    )
                )
                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.SpaceBetween
                ) {
                    Text("30%", color = NexusTextMuted, fontSize = 10.sp)
                    Text("100%", color = NexusTextMuted, fontSize = 10.sp)
                }
            }

            // === ALERTS ===
            SettingsSection("ALERTS") {
                SettingsToggle(
                    label = "Alert on new signal",
                    checked = uiState.alertOnSignal,
                    onCheckedChange = onAlertOnSignalChange
                )
                SettingsToggle(
                    label = "Alert on SL hit",
                    checked = uiState.alertOnSLHit,
                    onCheckedChange = onAlertOnSLHitChange
                )
            }

            // === ABOUT ===
            SettingsSection("ABOUT") {
                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.SpaceBetween
                ) {
                    Text("Version", color = NexusTextSecondary, fontSize = 14.sp)
                    Text("1.0.0", color = NexusTextMuted, fontSize = 14.sp)
                }
                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.SpaceBetween
                ) {
                    Text("Symbol", color = NexusTextSecondary, fontSize = 14.sp)
                    Text("XAUUSD", color = NexusTextMuted, fontSize = 14.sp)
                }
            }

            Spacer(modifier = Modifier.height(32.dp))
        }
    }
}

@Composable
private fun SettingsSection(
    title: String,
    content: @Composable ColumnScope.() -> Unit
) {
    Column(
        modifier = Modifier
            .fillMaxWidth()
            .clip(RoundedCornerShape(12.dp))
            .background(NexusSurface)
            .padding(16.dp)
    ) {
        Text(
            text = title,
            color = NexusAccent,
            fontSize = 11.sp,
            fontWeight = FontWeight.Bold,
            letterSpacing = 1.5.sp
        )
        Spacer(modifier = Modifier.height(12.dp))
        content()
    }
}

@Composable
private fun SettingsToggle(
    label: String,
    checked: Boolean,
    onCheckedChange: (Boolean) -> Unit
) {
    Row(
        modifier = Modifier.fillMaxWidth(),
        horizontalArrangement = Arrangement.SpaceBetween,
        verticalAlignment = Alignment.CenterVertically
    ) {
        Text(label, color = NexusTextSecondary, fontSize = 14.sp)
        Switch(
            checked = checked,
            onCheckedChange = onCheckedChange,
            colors = SwitchDefaults.colors(
                checkedThumbColor = NexusAccent,
                checkedTrackColor = NexusAccent.copy(alpha = 0.3f),
                uncheckedThumbColor = NexusTextMuted,
                uncheckedTrackColor = NexusSurfaceVariant
            )
        )
    }
}
