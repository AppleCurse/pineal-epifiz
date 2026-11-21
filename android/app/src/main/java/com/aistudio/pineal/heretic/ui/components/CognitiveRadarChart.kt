package com.aistudio.pineal.heretic.ui.components

import androidx.compose.foundation.Canvas
import androidx.compose.foundation.layout.*
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.Path
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.aistudio.pineal.heretic.ui.theme.*
import kotlin.math.cos
import kotlin.math.sin
import kotlin.math.PI

@Composable
fun CognitiveRadarChart(
    metrics: List<Pair<String, Double>>,
    modifier: Modifier = Modifier
) {
    val labels = metrics.map { it.first }
    val values = metrics.map { it.second.coerceIn(0.0, 1.0) }

    Box(modifier = modifier.aspectRatio(1.2f).padding(16.dp)) {
        Canvas(modifier = Modifier.fillMaxSize()) {
            val center = Offset(size.width / 2, size.height / 2)
            // Leave space for text labels
            val radius = (size.width.coerceAtMost(size.height) / 2) * 0.7f

            // Draw background polygons
            val levels = 5
            for (level in 1..levels) {
                val currentRadius = radius * (level / levels.toFloat())
                val path = Path()
                for (i in labels.indices) {
                    val angle = (2 * PI * i / labels.size) - PI / 2
                    val x = center.x + currentRadius * cos(angle).toFloat()
                    val y = center.y + currentRadius * sin(angle).toFloat()
                    if (i == 0) path.moveTo(x, y) else path.lineTo(x, y)
                }
                path.close()
                drawPath(
                    path = path,
                    color = BorderDim,
                    style = Stroke(width = 1f)
                )
            }

            // Draw axis lines
            for (i in labels.indices) {
                val angle = (2 * PI * i / labels.size) - PI / 2
                val x = center.x + radius * cos(angle).toFloat()
                val y = center.y + radius * sin(angle).toFloat()
                drawLine(
                    color = BorderDim,
                    start = center,
                    end = Offset(x, y),
                    strokeWidth = 1f
                )
            }

            // Draw data polygon
            val dataPath = Path()
            for (i in values.indices) {
                val value = values[i]
                val angle = (2 * PI * i / values.size) - PI / 2
                val currentRadius = radius * value.toFloat()
                val x = center.x + currentRadius * cos(angle).toFloat()
                val y = center.y + currentRadius * sin(angle).toFloat()

                if (i == 0) dataPath.moveTo(x, y) else dataPath.lineTo(x, y)
            }
            dataPath.close()

            drawPath(
                path = dataPath,
                color = LuxuryPurple.copy(alpha = 0.3f)
            )
            drawPath(
                path = dataPath,
                color = LuxuryPurple,
                style = Stroke(width = 4f)
            )

            // Draw points
            for (i in values.indices) {
                val value = values[i]
                val angle = (2 * PI * i / values.size) - PI / 2
                val currentRadius = radius * value.toFloat()
                val x = center.x + currentRadius * cos(angle).toFloat()
                val y = center.y + currentRadius * sin(angle).toFloat()

                drawCircle(
                    color = TrustBlue,
                    radius = 8f,
                    center = Offset(x, y)
                )
            }
        }

        // Overlay text labels
        BoxWithConstraints(modifier = Modifier.fillMaxSize()) {
            val center = Offset(maxWidth.value / 2, maxHeight.value / 2)
            val radius = (maxWidth.value.coerceAtMost(maxHeight.value) / 2) * 0.85f

            for (i in labels.indices) {
                val angle = (2 * PI * i / labels.size) - PI / 2
                val xOffset = radius * cos(angle).toFloat()
                val yOffset = radius * sin(angle).toFloat()

                Box(
                    modifier = Modifier
                        .align(Alignment.Center)
                        .offset(x = xOffset.dp, y = yOffset.dp)
                ) {
                    Text(
                        text = labels[i],
                        color = TextDark,
                        fontSize = 11.sp,
                        fontWeight = FontWeight.Bold,
                        modifier = Modifier.align(Alignment.Center)
                    )
                }
            }
        }
    }
}
