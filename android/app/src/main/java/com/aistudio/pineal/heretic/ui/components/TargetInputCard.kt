package com.aistudio.pineal.heretic.ui.components
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.BasicTextField
import androidx.compose.material3.*
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.SolidColor
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.aistudio.pineal.heretic.ui.PinealUiState
import com.aistudio.pineal.heretic.ui.theme.*

@Composable
fun TargetInputCard(
    state: PinealUiState,
    onUrlChange: (String) -> Unit,
    onRitualsChange: (String) -> Unit,
    onPlaylistChange: (String) -> Unit,
    onEnviesChange: (String) -> Unit,
    onTogglePlatform: (String) -> Unit,
    onToggleDeepExtraction: (Boolean) -> Unit,
    onModelChange: (String) -> Unit,
    onToggleCloud: (Boolean) -> Unit,
    onInitiate: () -> Unit,
    modifier: Modifier = Modifier
) {
    Column(
        modifier = modifier
            .fillMaxWidth()
            .border(1.dp, NeonCyan.copy(alpha=0.3f), RoundedCornerShape(topEnd = 16.dp, bottomStart = 16.dp))
            .background(SurfaceDark, RoundedCornerShape(topEnd = 16.dp, bottomStart = 16.dp))
            .padding(16.dp),
        verticalArrangement = Arrangement.spacedBy(16.dp)
    ) {
        Text(
            text = "",
            color = NeonCyan,
            style = MaterialTheme.typography.titleMedium,
            letterSpacing = 1.sp
        )

        TerminalInputField(
            label = "TARGET_URL",
            value = state.targetUrl,
            onValueChange = onUrlChange,
            placeholder = "https://..."
        )
        TerminalInputField(
            label = "RITUALS_DATA",
            value = state.rituals,
            onValueChange = onRitualsChange,
            placeholder = "Obsessions, routines..."
        )
        TerminalInputField(
            label = "AUDIO_FINGERPRINT",
            value = state.playlist,
            onValueChange = onPlaylistChange,
            placeholder = "Artists, genres..."
        )

        TerminalInputField(
            label = "VULNERABILITIES",
            value = state.envies,
            onValueChange = onEnviesChange,
            placeholder = "Envies, triggers..."
        )

        
        Column(verticalArrangement = Arrangement.spacedBy(4.dp)) {
            Text(text = "SOCIAL_FOOTPRINT_SOURCE", color = TextMuted, fontSize = 10.sp, fontWeight = FontWeight.Bold)
            val platformsList = listOf("LinkedIn", "X (Twitter)", "Instagram", "TikTok", "Bluesky", "Mastodon", "Threads", "Snapchat", "Facebook")
            androidx.compose.foundation.lazy.LazyRow(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                items(platformsList.size) { index ->
                    val plat = platformsList[index]
                    val isSelected = state.selectedPlatforms.contains(plat)
                    FilterChip(
                        selected = isSelected,
                        onClick = { onTogglePlatform(plat) },
                        label = { Text(plat, fontSize = 10.sp, fontFamily = FontFamily.Monospace) },
                        colors = FilterChipDefaults.filterChipColors(
                            containerColor = Void,
                            labelColor = TextMuted,
                            selectedContainerColor = NeonCyan.copy(alpha = 0.2f),
                            selectedLabelColor = NeonCyan
                        ),
                        border = FilterChipDefaults.filterChipBorder(
                            enabled = true,
                            selected = isSelected,
                            borderColor = BorderHighlight,
                            selectedBorderColor = NeonCyan
                        )
                    )
                }
            }
        }
        Row(
            verticalAlignment = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.SpaceBetween,
            modifier = Modifier.fillMaxWidth().padding(top = 4.dp, bottom = 4.dp)
        ) {
            Column {
                Text("DEEP_OSINT_EXTRACTION", color = NeonCyan, fontSize = 11.sp, fontWeight = FontWeight.Bold, letterSpacing = 1.sp)
                Text("Requires Apify/PhantomBuster API Key", color = TextMuted, fontSize = 9.sp)
            }
            Switch(
                checked = state.useDeepExtraction,
                onCheckedChange = onToggleDeepExtraction,
                colors = SwitchDefaults.colors(
                    checkedThumbColor = Void,
                    checkedTrackColor = NeonCyan,
                    uncheckedThumbColor = TextMuted,
                    uncheckedTrackColor = SurfaceDark
                )
            )
        }



        Button(
            onClick = onInitiate,
            enabled = !state.isProcessing && state.targetUrl.isNotBlank(),
            shape = RoundedCornerShape(topStart = 8.dp, bottomEnd = 8.dp),
            colors = ButtonDefaults.buttonColors(
                containerColor = BloodRed,
                contentColor = Void,
                disabledContainerColor = BorderHighlight,
                disabledContentColor = TextMuted
            ),
            modifier = Modifier.fillMaxWidth().height(48.dp)
        ) {
            Text(
                text = if (state.isProcessing) "EXECUTING_RECON..." else "EXECUTE_INFILTRATION",
                fontWeight = FontWeight.Black,
                letterSpacing = 2.sp,
                fontSize = 14.sp
            )
        }
    }
}

@Composable
fun TerminalInputField(label: String, value: String, onValueChange: (String) -> Unit, placeholder: String) {
    Column(verticalArrangement = Arrangement.spacedBy(4.dp)) {
        Text(text = label, color = TextMuted, fontSize = 10.sp, fontWeight = FontWeight.Bold)
        Row(
            verticalAlignment = Alignment.CenterVertically,
            modifier = Modifier
                .fillMaxWidth()
                .background(Void)
                .border(1.dp, BorderHighlight)
                .padding(horizontal = 8.dp, vertical = 10.dp)
        ) {
            Text(text = "", color = NeonCyan, fontSize = 12.sp, fontFamily = FontFamily.Monospace)
            BasicTextField(
                value = value,
                onValueChange = onValueChange,
                textStyle = TextStyle(color = TextMain, fontSize = 12.sp, fontFamily = FontFamily.Monospace),
                cursorBrush = SolidColor(NeonCyan),
                modifier = Modifier.weight(1f),
                decorationBox = { innerTextField ->
                    if (value.isEmpty()) {
                        Text(text = placeholder, color = TextMuted, fontSize = 12.sp, fontFamily = FontFamily.Monospace)
                    }
                    innerTextField()
                }
            )
        }
    }
}
