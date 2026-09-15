package com.nexus.overlay

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.ui.Modifier
import androidx.navigation.compose.NavHost
import androidx.navigation.compose.composable
import androidx.navigation.compose.rememberNavController
import com.nexus.overlay.ui.dashboard.DashboardScreen
import com.nexus.overlay.ui.settings.SettingsScreen
import com.nexus.overlay.ui.theme.NexusTheme

/**
 * Main activity hosting all Compose screens.
 * Uses Navigation Compose for screen routing.
 */
class MainActivity : ComponentActivity() {

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()

        val app = application as NexusOverlayApp
        val viewModel = app.viewModel

        setContent {
            NexusTheme {
                Surface(
                    modifier = Modifier.fillMaxSize(),
                    color = MaterialTheme.colorScheme.background
                ) {
                    val navController = rememberNavController()
                    val uiState by viewModel.uiState.collectAsState()

                    NavHost(
                        navController = navController,
                        startDestination = "dashboard"
                    ) {
                        composable("dashboard") {
                            DashboardScreen(
                                uiState = uiState,
                                onNavigateToSettings = {
                                    navController.navigate("settings")
                                },
                                onToggleOverlay = {
                                    viewModel.toggleOverlay()
                                },
                                onRefresh = {
                                    viewModel.refreshConnection()
                                }
                            )
                        }
                        composable("settings") {
                            SettingsScreen(
                                uiState = uiState,
                                onBack = { navController.popBackStack() },
                                onServerHostChange = viewModel::updateServerHost,
                                onServerPortChange = viewModel::updateServerPort,
                                onAuthTokenChange = viewModel::updateAuthToken,
                                onOverlayModeChange = viewModel::updateOverlayMode,
                                onAutoConnectChange = viewModel::updateAutoConnect,
                                onAlertOnSignalChange = viewModel::updateAlertOnSignal,
                                onAlertOnSLHitChange = viewModel::updateAlertOnSLHit,
                                onOpacityChange = viewModel::updateOverlayOpacity,
                                onConnect = { viewModel.connect() },
                                onDisconnect = { viewModel.disconnect() }
                            )
                        }
                    }
                }
            }
        }
    }

    override fun onDestroy() {
        super.onDestroy()
        if (isFinishing) {
            val app = application as NexusOverlayApp
            app.webSocketClient.disconnect()
        }
    }
}
