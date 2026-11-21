package com.aistudio.pineal.heretic.ui.components

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.geometry.Offset
import com.aistudio.pineal.heretic.ui.theme.EliteBackground
import com.aistudio.pineal.heretic.ui.theme.EliteSurfaceElevated

@Composable
fun PinealBackground(modifier: Modifier = Modifier, content: @Composable () -> Unit) {
    Box(
        modifier = modifier
            .fillMaxSize()
            .background(
                brush = Brush.radialGradient(
                    colors = listOf(EliteSurfaceElevated, EliteBackground),
                    center = Offset(0f, 0f),
                    radius = 2000f
                )
            )
    ) {
        content()
    }
}
