package com.aistudio.pineal.heretic.ui.components

import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.*
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.aistudio.pineal.heretic.ui.PinealUiState
import com.aistudio.pineal.heretic.ui.theme.*

@Composable
fun AgentChainCard(
    state: PinealUiState,
    modifier: Modifier = Modifier
) {
    val s = state.strings

    Card(
        modifier = modifier
            .fillMaxWidth()
            .border(BorderStroke(1.dp, BorderDim), RoundedCornerShape(16.dp)),
        colors = CardDefaults.cardColors(containerColor = SurfaceDark),
        shape = RoundedCornerShape(16.dp)
    ) {
        Column(
            modifier = Modifier
                .fillMaxWidth()
                .padding(14.dp),
            verticalArrangement = Arrangement.spacedBy(10.dp)
        ) {
            // Header
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically
            ) {
                Text(
                    text = "⚙️ " + s.agentChainTitle,
                    style = MaterialTheme.typography.titleMedium,
                    color = CyberGold,
                    fontWeight = FontWeight.Bold
                )

                val (badgeBg, badgeText, badgeColor) = when (state.taskState) {
                    "COMPLETED" -> Triple(MatrixGreen.copy(alpha=0.15f), "COMPLETED", MatrixGreenLight)
                    "PROCESSING" -> Triple(WarningGold.copy(alpha=0.2f), "PROCESSING", WarningGoldLight)
                    "FAILED", "HALTED" -> Triple(BloodRed.copy(alpha=0.2f), "HALTED", BloodRedLight)
                    else -> Triple(SurfaceDark, "IDLE", TextMuted)
                }

                Box(
                    modifier = Modifier
                        .background(badgeBg, RoundedCornerShape(16.dp))
                        .padding(horizontal = 8.dp, vertical = 2.dp)
                ) {
                    Text(
                        text = badgeText,
                        color = badgeColor,
                        fontSize = 9.sp,
                        fontWeight = FontWeight.Bold
                    )
                }
            }

            if (state.taskId.isNotBlank()) {
                Text(
                    text = "GÖREV ID: " + state.taskId,
                    fontSize = 10.sp,
                    color = TextMuted
                )
            }

            // Agents list
            Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
                state.agents.forEachIndexed { index, agent ->
                    val isDone = agent.status == "COMPLETED"
                    val isRunning = agent.status == "RUNNING"
                    val isHalted = agent.status == "HALTED" || agent.status == "FAILED"

                    Row(
                        modifier = Modifier
                            .fillMaxWidth()
                            .background(SurfaceDark, RoundedCornerShape(16.dp))
                            .border(
                                1.dp,
                                if (isRunning) CyberGold else BorderDim,
                                RoundedCornerShape(16.dp)
                            )
                            .padding(8.dp),
                        verticalAlignment = Alignment.CenterVertically,
                        horizontalArrangement = Arrangement.spacedBy(10.dp)
                    ) {
                        // Badge Index or Status Icon
                        Box(
                            modifier = Modifier
                                .size(22.dp)
                                .clip(CircleShape)
                                .background(Color(agent.colorHex)),
                            contentAlignment = Alignment.Center
                        ) {
                            Text(
                                text = when {
                                    isDone -> "✓"
                                    isRunning -> "▶"
                                    isHalted -> "✗"
                                    else -> "${index + 1}"
                                },
                                color = Void,
                                fontSize = 10.sp,
                                fontWeight = FontWeight.ExtraBold
                            )
                        }

                        // Agent Name and Progress Bar
                        Column(modifier = Modifier.weight(1f)) {
                            Row(
                                modifier = Modifier.fillMaxWidth(),
                                horizontalArrangement = Arrangement.SpaceBetween
                            ) {
                                Text(
                                    text = agent.name,
                                    fontSize = 11.sp,
                                    fontWeight = FontWeight.Bold,
                                    color = if (isDone) CyberGoldLight else if (isRunning) CyberGold else TextMuted
                                )
                                if (agent.confidence > 0.0) {
                                    Text(
                                        text = String.format("%.2f", agent.confidence),
                                        fontSize = 10.sp,
                                        fontWeight = FontWeight.SemiBold,
                                        color = MatrixGreenLight
                                    )
                                }
                            }

                            // Progress track
                            Box(
                                modifier = Modifier
                                    .fillMaxWidth()
                                    .height(4.dp)
                                    .background(Void, RoundedCornerShape(16.dp))
                            ) {
                                val fillFraction = when {
                                    isDone -> 1f
                                    isRunning -> 0.5f
                                    isHalted -> 1f
                                    else -> 0f
                                }
                                val fillColor = when {
                                    isDone -> MatrixGreen
                                    isHalted -> BloodRed
                                    isRunning -> WarningGold
                                    else -> Color.Transparent
                                }
                                Box(
                                    modifier = Modifier
                                        .fillMaxHeight()
                                        .fillMaxWidth(fillFraction)
                                        .background(fillColor, RoundedCornerShape(16.dp))
                                )
                            }
                        }

                        // Status Label
                        Text(
                            text = when {
                                isDone -> "TAMAM"
                                isRunning -> "AKTİF"
                                isHalted -> "DURDU"
                                else -> "BEKLİYOR"
                            },
                            fontSize = 9.sp,
                            fontWeight = FontWeight.Bold,
                            color = when {
                                isDone -> MatrixGreenLight
                                isRunning -> WarningGoldLight
                                isHalted -> BloodRedLight
                                else -> TextMuted
                            }
                        )
                    }
                }
            }

            // Overall Confidence Gauge
            Card(
                modifier = Modifier
                    .fillMaxWidth()
                    .border(BorderStroke(1.dp, BorderDim), RoundedCornerShape(16.dp)),
                colors = CardDefaults.cardColors(containerColor = Void)
            ) {
                Column(
                    modifier = Modifier
                        .fillMaxWidth()
                        .padding(10.dp),
                    verticalArrangement = Arrangement.spacedBy(6.dp)
                ) {
                    Row(
                        modifier = Modifier.fillMaxWidth(),
                        horizontalArrangement = Arrangement.SpaceBetween
                    ) {
                        Text(
                            text = s.overallConfidence,
                            fontSize = 11.sp,
                            fontWeight = FontWeight.Bold,
                            color = CyberGold
                        )
                        Text(
                            text = String.format("%%%.0f", state.overallConfidence * 100),
                            fontSize = 12.sp,
                            fontWeight = FontWeight.Bold,
                            color = MatrixGreenLight
                        )
                    }
                    LinearProgressIndicator(
                        progress = { state.overallConfidence.toFloat() },
                        modifier = Modifier
                            .fillMaxWidth()
                            .height(6.dp)
                            .clip(RoundedCornerShape(16.dp)),
                        color = MatrixGreen,
                        trackColor = SurfaceLighter
                    )
                }
            }
        }
    }
}
