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
import androidx.compose.material.icons.filled.AddPhotoAlternate
import androidx.compose.material.icons.filled.Lightbulb
import androidx.compose.material.icons.filled.Send

import android.content.Intent
import android.speech.RecognizerIntent
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.material.icons.filled.Mic

import androidx.compose.material3.*
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.aistudio.pineal.heretic.ui.PinealUiState
import com.aistudio.pineal.heretic.ui.theme.*

@Composable
fun AspasiaChatCard(
    state: PinealUiState,
    onInputChange: (String) -> Unit,
    onSendMessage: () -> Unit,
    onExplainState: () -> Unit,
    onAttachImage: () -> Unit,
    modifier: Modifier = Modifier
) {
    val s = state.strings
    val listState = rememberLazyListState()

    val voiceLauncher = rememberLauncherForActivityResult(ActivityResultContracts.StartActivityForResult()) { result ->
        if (result.resultCode == android.app.Activity.RESULT_OK) {
            val data = result.data
            val results = data?.getStringArrayListExtra(RecognizerIntent.EXTRA_RESULTS)
            val text = results?.get(0)
            if (!text.isNullOrBlank()) {
                onInputChange((state.chatInput + " " + text).trim())
            }
        }
    }


    LaunchedEffect(state.chatMessages.size) {
        if (state.chatMessages.isNotEmpty()) {
            listState.animateScrollToItem(state.chatMessages.size - 1)
        }
    }

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
                Column {
                    Text(
                        text = "🏛️ " + s.agentDeckTitle,
                        style = MaterialTheme.typography.titleMedium,
                        color = CyberGold,
                        fontWeight = FontWeight.Bold
                    )
                    Text(
                        text = s.aspasiaRole,
                        fontSize = 10.sp,
                        color = TextMuted
                    )
                }


                IconButton(
                    onClick = {
                        val intent = Intent(RecognizerIntent.ACTION_RECOGNIZE_SPEECH).apply {
                            putExtra(RecognizerIntent.EXTRA_LANGUAGE_MODEL, RecognizerIntent.LANGUAGE_MODEL_FREE_FORM)
                            putExtra(RecognizerIntent.EXTRA_PROMPT, "Dinliyorum...")
                        }
                        try {
                            voiceLauncher.launch(intent)
                        } catch (e: Exception) {
                            // Voice not supported
                        }
                    },
                    modifier = Modifier.padding(end = 4.dp)
                ) {
                    Icon(
                        imageVector = Icons.Default.Mic,
                        contentDescription = "Sesli Yaz",
                        tint = MatrixGreenLight
                    )
                }

                Button(
                    onClick = onExplainState,
                    enabled = !state.isChatSending,
                    colors = ButtonDefaults.buttonColors(
                        containerColor = SurfaceDark,
                        contentColor = CyberGold
                    ),
                    shape = RoundedCornerShape(16.dp),
                    border = BorderStroke(1.dp, BorderDim),
                    contentPadding = PaddingValues(horizontal = 8.dp, vertical = 4.dp),
                    modifier = Modifier.height(32.dp)
                ) {
                    Icon(
                        imageVector = Icons.Default.Lightbulb,
                        contentDescription = null,
                        modifier = Modifier.size(14.dp),
                        tint = CyberGold
                    )
                    Spacer(modifier = Modifier.width(4.dp))
                    Text(s.explainStateBtn, fontSize = 9.sp, fontWeight = FontWeight.Bold)
                }
            }

            // Message Stream Box
            Box(
                modifier = Modifier
                    .fillMaxWidth()
                    .height(240.dp)
                    .background(Void, RoundedCornerShape(16.dp))
                    .border(1.dp, BorderDim, RoundedCornerShape(16.dp))
                    .padding(8.dp)
            ) {
                LazyColumn(
                    state = listState,
                    modifier = Modifier.fillMaxSize(),
                    verticalArrangement = Arrangement.spacedBy(8.dp)
                ) {
                    items(state.chatMessages) { msg ->
                        val isYou = msg.sender == s.you || msg.sender == "SİZ" || msg.sender == "YOU"
                        val isSystem = msg.sender == "SİSTEM" || msg.sender == "SYSTEM"

                        Box(
                            modifier = Modifier.fillMaxWidth(),
                            contentAlignment = if (isYou) Alignment.CenterEnd else if (isSystem) Alignment.Center else Alignment.CenterStart
                        ) {
                            if (isSystem) {
                                Box(
                                    modifier = Modifier
                                        .background(CyberGold.copy(alpha = 0.15f), RoundedCornerShape(16.dp))
                                        .border(1.dp, CyberGold, RoundedCornerShape(16.dp))
                                        .padding(horizontal = 8.dp, vertical = 4.dp)
                                ) {
                                    Text(text = "⚙️ ${msg.text}", color = CyberGoldLight, fontSize = 10.sp, fontWeight = FontWeight.Bold)
                                }
                            } else if (isYou) {
                                Box(
                                    modifier = Modifier
                                        .fillMaxWidth(0.85f)
                                        .background(SurfaceLighter, RoundedCornerShape(16.dp))
                                        .border(1.dp, BorderDimLight, RoundedCornerShape(16.dp))
                                        .padding(8.dp)
                                ) {
                                    Column {
                                        Text(text = "${msg.sender}:", fontSize = 9.sp, fontWeight = FontWeight.Bold, color = TextMuted)
                                        Text(text = msg.text, fontSize = 11.sp, color = TextMain)
                                    }
                                }
                            } else {
                                Box(
                                    modifier = Modifier
                                        .fillMaxWidth(0.90f)
                                        .background(SurfaceDark, RoundedCornerShape(16.dp))
                                        .border(1.dp, BorderDimLight, RoundedCornerShape(16.dp))
                                        .padding(8.dp)
                                ) {
                                    Column {
                                        Text(text = "ASPASIA:", fontSize = 9.sp, fontWeight = FontWeight.Bold, color = CyberGold)
                                        Text(text = msg.text, fontSize = 11.sp, color = TextMain, lineHeight = 16.sp)
                                    }
                                }
                            }
                        }
                    }
                }
            }

            // Chat Input & Actions
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.spacedBy(6.dp),
                verticalAlignment = Alignment.CenterVertically
            ) {
                OutlinedTextField(
                    value = state.chatInput,
                    onValueChange = onInputChange,
                    placeholder = { Text(s.chatPlaceholder, fontSize = 11.sp, color = TextMuted) },
                    enabled = !state.isChatSending,
                    singleLine = true,
                    modifier = Modifier
                        .weight(1f)
                        .testTag("chat_input_field"),
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

                IconButton(
                    onClick = onAttachImage,
                    modifier = Modifier
                        .size(40.dp)
                        .background(SurfaceDark, RoundedCornerShape(16.dp))
                        .border(1.dp, BorderDim, RoundedCornerShape(16.dp))
                ) {
                    Icon(
                        imageVector = Icons.Default.AddPhotoAlternate,
                        contentDescription = "Attach image",
                        tint = CyberGold,
                        modifier = Modifier.size(18.dp)
                    )
                }


                IconButton(
                    onClick = {
                        val intent = Intent(RecognizerIntent.ACTION_RECOGNIZE_SPEECH).apply {
                            putExtra(RecognizerIntent.EXTRA_LANGUAGE_MODEL, RecognizerIntent.LANGUAGE_MODEL_FREE_FORM)
                            putExtra(RecognizerIntent.EXTRA_PROMPT, "Dinliyorum...")
                        }
                        try {
                            voiceLauncher.launch(intent)
                        } catch (e: Exception) {
                            // Voice not supported
                        }
                    },
                    modifier = Modifier.padding(end = 4.dp)
                ) {
                    Icon(
                        imageVector = Icons.Default.Mic,
                        contentDescription = "Sesli Yaz",
                        tint = MatrixGreenLight
                    )
                }

                Button(
                    onClick = onSendMessage,
                    enabled = !state.isChatSending && (state.chatInput.isNotBlank() || state.attachedImageUri != null),
                    colors = ButtonDefaults.buttonColors(
                        containerColor = CyberGold,
                        contentColor = Void
                    ),
                    shape = RoundedCornerShape(16.dp),
                    contentPadding = PaddingValues(horizontal = 12.dp, vertical = 8.dp),
                    modifier = Modifier
                        .height(40.dp)
                        .testTag("send_chat_button")
                ) {
                    Icon(
                        imageVector = Icons.Default.Send,
                        contentDescription = null,
                        modifier = Modifier.size(16.dp)
                    )
                }
            }
        }
    }
}
