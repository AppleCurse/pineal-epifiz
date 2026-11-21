package com.aistudio.pineal.heretic.ui.components

import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.lazy.rememberLazyListState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Lock
import androidx.compose.material.icons.filled.LockOpen
import androidx.compose.material3.*
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.aistudio.pineal.heretic.ui.PinealUiState
import com.aistudio.pineal.heretic.ui.theme.*

@Composable
fun TelemetryAndLogsCard(
    state: PinealUiState,
    onApiKeyChange: (String) -> Unit,
    onCookieChange: (String) -> Unit,
    onSealVault: () -> Unit,
    modifier: Modifier = Modifier
) {
    val s = state.strings
    val logListState = rememberLazyListState()

    LaunchedEffect(state.logs.size) {
        if (state.logs.isNotEmpty()) {
            logListState.animateScrollToItem(state.logs.size - 1)
        }
    }

    Column(
        modifier = modifier.fillMaxWidth(),
        verticalArrangement = Arrangement.spacedBy(12.dp)
    ) {
        // Telemetry Gauge Card
        Card(
            modifier = Modifier
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
                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.SpaceBetween,
                    verticalAlignment = Alignment.CenterVertically
                ) {
                    Text(
                        text = s.engineTelemetry,
                        style = MaterialTheme.typography.titleMedium,
                        color = CyberGold,
                        fontWeight = FontWeight.Bold
                    )
                    Text(
                        text = "● " + s.active,
                        color = MatrixGreenLight,
                        fontSize = 10.sp,
                        fontWeight = FontWeight.Bold
                    )
                }

                // Resonance Score Meter
                Card(
                    modifier = Modifier
                        .fillMaxWidth()
                        .border(1.dp, BorderDim, RoundedCornerShape(16.dp)),
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
                            Text(text = s.resonanceScoreLabel, fontSize = 10.sp, color = TextMuted)
                            Text(
                                text = String.format("%%%.0f", state.resonanceScore * 100),
                                fontSize = 12.sp,
                                fontWeight = FontWeight.Bold,
                                color = MatrixGreenLight
                            )
                        }

                        LinearProgressIndicator(
                            progress = { state.resonanceScore.toFloat() },
                            modifier = Modifier
                                .fillMaxWidth()
                                .height(6.dp)
                                .clip(RoundedCornerShape(16.dp)),
                            color = MatrixGreen,
                            trackColor = SurfaceLighter
                        )

                        if (state.resonanceApproach.isNotBlank()) {
                            Text(
                                text = "${s.approachLabel}: ${state.resonanceApproach}",
                                fontSize = 9.sp,
                                color = TextMuted
                            )
                        }

                        if (state.redFlags.isNotEmpty()) {
                            Row(
                                modifier = Modifier.fillMaxWidth(),
                                horizontalArrangement = Arrangement.spacedBy(4.dp)
                            ) {
                                state.redFlags.forEach { flag ->
                                    Box(
                                        modifier = Modifier
                                            .background(BloodRed.copy(alpha = 0.15f), RoundedCornerShape(16.dp))
                                            .border(1.dp, BloodRed.copy(alpha = 0.4f), RoundedCornerShape(16.dp))
                                            .padding(horizontal = 6.dp, vertical = 2.dp)
                                    ) {
                                        Text(text = flag, fontSize = 8.sp, color = BloodRedLight)
                                    }
                                }
                            }
                        }
                    }
                }

                // Telemetry Stats Row
                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.spacedBy(6.dp)
                ) {
                    Card(
                        modifier = Modifier
                            .weight(1f)
                            .border(1.dp, BorderDim, RoundedCornerShape(16.dp)),
                        colors = CardDefaults.cardColors(containerColor = SurfaceDark)
                    ) {
                        Column(modifier = Modifier.padding(6.dp)) {
                            Text(text = "CACHE HIT", fontSize = 8.sp, color = TextMuted, fontWeight = FontWeight.Bold)
                            Text(text = state.telemetry.cacheHitRate, fontSize = 11.sp, color = CyberCyanLight, fontWeight = FontWeight.Bold)
                        }
                    }
                    Card(
                        modifier = Modifier
                            .weight(1f)
                            .border(1.dp, BorderDim, RoundedCornerShape(16.dp)),
                        colors = CardDefaults.cardColors(containerColor = SurfaceDark)
                    ) {
                        Column(modifier = Modifier.padding(6.dp)) {
                            Text(text = "HITS", fontSize = 8.sp, color = TextMuted, fontWeight = FontWeight.Bold)
                            Text(text = "${state.telemetry.cacheHits}", fontSize = 11.sp, color = MatrixGreenLight, fontWeight = FontWeight.Bold)
                        }
                    }
                    Card(
                        modifier = Modifier
                            .weight(1f)
                            .border(1.dp, BorderDim, RoundedCornerShape(16.dp)),
                        colors = CardDefaults.cardColors(containerColor = SurfaceDark)
                    ) {
                        Column(modifier = Modifier.padding(6.dp)) {
                            Text(text = "LLM ÇAĞRISI", fontSize = 8.sp, color = TextMuted, fontWeight = FontWeight.Bold)
                            Text(text = "${state.telemetry.llmCallsObserved}", fontSize = 11.sp, color = CyberGoldLight, fontWeight = FontWeight.Bold)
                        }
                    }
                }
            }
        }

        // Live SIGINT Feed Terminal
        Card(
            modifier = Modifier
                .fillMaxWidth()
                .height(200.dp)
                .border(BorderStroke(1.dp, BorderDim), RoundedCornerShape(16.dp)),
            colors = CardDefaults.cardColors(containerColor = SurfaceDark),
            shape = RoundedCornerShape(16.dp)
        ) {
            Column(
                modifier = Modifier
                    .fillMaxSize()
                    .padding(10.dp)
            ) {
                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.SpaceBetween,
                    verticalAlignment = Alignment.CenterVertically
                ) {
                    Text(
                        text = s.sigintFeed,
                        fontSize = 11.sp,
                        fontWeight = FontWeight.Bold,
                        color = CyberGold
                    )
                    Text(
                        text = "ROOM:LOCAL",
                        fontSize = 9.sp,
                        color = TextMuted,
                        fontFamily = FontFamily.Monospace
                    )
                }

                Spacer(modifier = Modifier.height(6.dp))

                Box(
                    modifier = Modifier
                        .fillMaxSize()
                        .background(Void, RoundedCornerShape(16.dp))
                        .padding(6.dp)
                ) {
                    LazyColumn(
                        state = logListState,
                        modifier = Modifier.fillMaxSize(),
                        verticalArrangement = Arrangement.spacedBy(3.dp)
                    ) {
                        items(state.logs) { log ->
                            val color = when (log.level) {
                                "ERROR" -> BloodRedLight
                                "WARNING" -> WarningGoldLight
                                "SUCCESS" -> MatrixGreenLight
                                else -> MatrixGreen
                            }
                            Text(
                                text = "[${log.ts}] ${log.msg}",
                                color = color,
                                fontSize = 9.sp,
                                fontFamily = FontFamily.Monospace,
                                lineHeight = 13.sp
                            )
                        }
                    }
                }
            }
        }

        // Secure Vault (Kasa) Card
        Card(
            modifier = Modifier
                .fillMaxWidth()
                .border(BorderStroke(1.dp, BorderDim), RoundedCornerShape(16.dp)),
            colors = CardDefaults.cardColors(containerColor = SurfaceDark),
            shape = RoundedCornerShape(16.dp)
        ) {
            Column(
                modifier = Modifier
                    .fillMaxWidth()
                    .padding(14.dp),
                verticalArrangement = Arrangement.spacedBy(8.dp)
            ) {
                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.SpaceBetween,
                    verticalAlignment = Alignment.CenterVertically
                ) {
                    Text(
                        text = s.vaultTitle,
                        style = MaterialTheme.typography.titleMedium,
                        color = CyberGold,
                        fontWeight = FontWeight.Bold
                    )
                    Text(
                        text = if (state.isVaultSealed) s.vaultActive else s.vaultReady,
                        fontSize = 9.sp,
                        fontWeight = FontWeight.Bold,
                        color = if (state.isVaultSealed) MatrixGreenLight else CyberGoldLight
                    )
                }

                Text(
                    text = s.vaultDesc,
                    fontSize = 10.sp,
                    color = TextMuted
                )

                OutlinedTextField(
                    value = state.apiKey,
                    onValueChange = onApiKeyChange,
                    placeholder = { Text(s.apiKeyPlaceholder, fontSize = 10.sp, color = TextMuted) },
                    visualTransformation = PasswordVisualTransformation(),
                    singleLine = true,
                    modifier = Modifier.fillMaxWidth(),
                    colors = OutlinedTextFieldDefaults.colors(
                        focusedBorderColor = CyberGold,
                        unfocusedBorderColor = BorderDim,
                        focusedTextColor = TextMain,
                        unfocusedTextColor = TextMain,
                        focusedContainerColor = SurfaceDark,
                        unfocusedContainerColor = SurfaceDark
                    ),
                    shape = RoundedCornerShape(16.dp)
                )

                OutlinedTextField(
                    value = state.cookie,
                    onValueChange = onCookieChange,
                    placeholder = { Text(s.cookiePlaceholder, fontSize = 10.sp, color = TextMuted) },
                    visualTransformation = PasswordVisualTransformation(),
                    singleLine = true,
                    modifier = Modifier.fillMaxWidth(),
                    colors = OutlinedTextFieldDefaults.colors(
                        focusedBorderColor = CyberGold,
                        unfocusedBorderColor = BorderDim,
                        focusedTextColor = TextMain,
                        unfocusedTextColor = TextMain,
                        focusedContainerColor = SurfaceDark,
                        unfocusedContainerColor = SurfaceDark
                    ),
                    shape = RoundedCornerShape(16.dp)
                )

                Button(
                    onClick = onSealVault,
                    colors = ButtonDefaults.buttonColors(
                        containerColor = if (state.isVaultSealed) MatrixGreen else CyberGold,
                        contentColor = Void
                    ),
                    shape = RoundedCornerShape(16.dp),
                    modifier = Modifier
                        .fillMaxWidth()
                        .testTag("seal_vault_button")
                ) {
                    Icon(
                        imageVector = if (state.isVaultSealed) Icons.Default.Lock else Icons.Default.LockOpen,
                        contentDescription = null,
                        modifier = Modifier.size(16.dp)
                    )
                    Spacer(modifier = Modifier.width(6.dp))
                    Text(s.sealBtn, fontSize = 11.sp, fontWeight = FontWeight.Bold)
                }
            }
        }
    }
}
