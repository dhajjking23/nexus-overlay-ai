package com.nexus.overlay.ui.theme

import androidx.compose.ui.graphics.Color
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.darkColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.runtime.SideEffect
import androidx.compose.ui.graphics.toArgb
import androidx.compose.ui.platform.LocalView
import androidx.core.view.WindowCompat

/**
 * Dark trading terminal theme.
 * Deep navy/charcoal background with high-contrast signal colors.
 */
private val DarkColorScheme = darkColorScheme(
    primary = NexusAccent,
    onPrimary = NexusTextPrimary,
    primaryContainer = NexusAccentLight,
    onPrimaryContainer = NexusBackground,

    secondary = SignalBuy,
    onSecondary = NexusBackground,
    secondaryContainer = SignalBuyDark,
    onSecondaryContainer = SignalBuy,

    tertiary = SignalWait,
    onTertiary = NexusBackground,
    tertiaryContainer = SignalWaitDark,
    onTertiaryContainer = SignalWait,

    background = NexusBackground,
    onBackground = NexusTextPrimary,

    surface = NexusSurface,
    onSurface = NexusTextPrimary,
    surfaceVariant = NexusSurfaceVariant,
    onSurfaceVariant = NexusTextSecondary,

    error = NexusError,
    onError = NexusTextPrimary,
    errorContainer = Color(0xFF3B1111),
    onErrorContainer = NexusError,

    outline = NexusTextMuted,
    outlineVariant = NexusCard,
)

@Composable
fun NexusTheme(
    content: @Composable () -> Unit
) {
    val colorScheme = DarkColorScheme
    val view = LocalView.current

    if (!view.isInEditMode) {
        SideEffect {
            val window = (view.context as android.app.Activity).window
            window.statusBarColor = NexusBackground.toArgb()
            window.navigationBarColor = NexusBackground.toArgb()
            WindowCompat.getInsetsController(window, view).isAppearanceLightStatusBars = false
        }
    }

    MaterialTheme(
        colorScheme = colorScheme,
        typography = NexusTypography,
        content = content
    )
}
