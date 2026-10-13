package com.example.pineal

import android.net.Uri
import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.activity.result.contract.ActivityResultContracts
import androidx.activity.viewModels
import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.*
import androidx.compose.material3.*
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.example.pineal.i18n.AppLanguage
import com.example.pineal.ui.CockpitTab
import com.example.pineal.ui.PinealViewModel
import com.example.pineal.ui.PinealViewModelFactory
import com.example.pineal.ui.components.*
import com.example.pineal.ui.components.ReconInputCard
import com.example.pineal.ui.theme.*

class MainActivity : ComponentActivity() {

    private val viewModel: PinealViewModel by viewModels {
        val app = application as PinealApp
        PinealViewModelFactory(app.repository)
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()

        setContent {
            PinealTheme {
                val state by viewModel.uiState.collectAsState()
                val liveHypotheses by viewModel.liveReconState.collectAsState()

                val imagePicker = rememberLauncherForActivityResult(
                    contract = ActivityResultContracts.GetContent()
                ) { uri: Uri? ->
                    uri?.let { viewModel.setAttachedImage(it.toString()) }
                }

                val context = androidx.compose.ui.platform.LocalContext.current
            Scaffold(
                    modifier = Modifier.fillMaxSize(),
                    containerColor = Void,
                    contentWindowInsets = WindowInsets.safeDrawing
                ) { innerPadding ->
                    PinealMainScreen(
                        state = state,
                        onLanguageChange = { viewModel.setLanguage(it) },
                        onTabChange = { viewModel.selectTab(it) },
                        onUrlChange = { viewModel.setTargetUrl(it) },
                        onRitualsChange = { viewModel.setRituals(it) },
                        onPlaylistChange = { viewModel.setPlaylist(it) },
                        onEnviesChange = { viewModel.setEnvies(it) },
                        onTogglePlatform = { viewModel.togglePlatform(it) },
                        onModelChange = { viewModel.setModel(it) },
                        onToggleCloud = { viewModel.toggleCloudApi(it) },
                        onInitiate = { viewModel.triggerAnalysis() },
                        onChatInputChange = { viewModel.setChatInput(it) },
                        onSendMessage = { viewModel.sendChatMessage() },
                        onExplainState = { viewModel.askExplainState() },
                        onAttachImage = { imagePicker.launch("image/*") },
                        onApiKeyChange = { viewModel.setApiKey(it) },
                        onOsintApiKeyChange = { viewModel.setOsintApiKey(it) },
                        onToggleDeepExtraction = { viewModel.toggleDeepExtraction(it) },
                        onCookieChange = { viewModel.setCookie(it) },
                        onSealVault = { viewModel.sealVault() },
                        onLoadHistory = { viewModel.loadFromHistory(it) },
                        onDeleteHistory = { viewModel.deleteHistoryItem(it) },
                        onClearHistory = { viewModel.clearAllHistory() },
                        onFeedRecon = viewModel::feedNewEvidence,
liveHypotheses = liveHypotheses,
                        modifier = Modifier.padding(innerPadding)
                    )
                }
            }
        }
    }
}

@Composable
fun PinealMainScreen(
    state: com.example.pineal.ui.PinealUiState,
    onLanguageChange: (AppLanguage) -> Unit,
    onTabChange: (CockpitTab) -> Unit,
    onUrlChange: (String) -> Unit,
    onRitualsChange: (String) -> Unit,
    onPlaylistChange: (String) -> Unit,
    onEnviesChange: (String) -> Unit,
    onTogglePlatform: (String) -> Unit,
    onModelChange: (String) -> Unit,
    onToggleCloud: (Boolean) -> Unit,
    onInitiate: () -> Unit,
    onChatInputChange: (String) -> Unit,
    onSendMessage: () -> Unit,
    onExplainState: () -> Unit,
    onAttachImage: () -> Unit,
    onApiKeyChange: (String) -> Unit,
    onOsintApiKeyChange: (String) -> Unit,
    onToggleDeepExtraction: (Boolean) -> Unit,
    onCookieChange: (String) -> Unit,
    onSealVault: () -> Unit,
    onLoadHistory: (com.example.pineal.data.local.AnalysisEntity) -> Unit,
    onDeleteHistory: (Long) -> Unit,
    onClearHistory: () -> Unit,
    onFeedRecon: (String) -> Unit,
    liveHypotheses: List<com.example.pineal.engine.ForensicHypothesis>,
    modifier: Modifier = Modifier
) {
    val s = state.strings
    val scrollState = rememberScrollState()

    Column(
        modifier = modifier
            .fillMaxSize()
            .background(Void)
            .padding(horizontal = 14.dp, vertical = 8.dp)
            .verticalScroll(scrollState),
        verticalArrangement = Arrangement.spacedBy(14.dp)
    ) {
        // TOP HEADER: Brand, Status, Language Switcher
        Row(
            modifier = Modifier
                .fillMaxWidth()
                .border(BorderStroke(1.dp, BorderDim), RoundedCornerShape(16.dp))
                .background(SurfaceDark, RoundedCornerShape(16.dp))
                .padding(12.dp),
            horizontalArrangement = Arrangement.SpaceBetween,
            verticalAlignment = Alignment.CenterVertically
        ) {
            Column(modifier = Modifier.weight(1f)) {
                Text(
                    text = "${s.appTitle} v${BuildConfig.VERSION_NAME}",
                    style = MaterialTheme.typography.titleLarge,
                    color = CyberGold,
                    fontWeight = FontWeight.ExtraBold,
                    letterSpacing = 1.sp
                )
                Text(
                    text = s.appSubtitle,
                    fontSize = 9.sp,
                    color = TextMuted,
                    letterSpacing = 0.5.sp
                )
            }

            Row(
                verticalAlignment = Alignment.CenterVertically,
                horizontalArrangement = Arrangement.spacedBy(8.dp)
            ) {
                // Online badge
                Box(
                    modifier = Modifier
                        .background(MatrixGreenDim, RoundedCornerShape(16.dp))
                        .padding(horizontal = 6.dp, vertical = 3.dp)
                ) {
                    Text(
                        text = "● " + s.onlineStatus,
                        color = MatrixGreenLight,
                        fontSize = 9.sp,
                        fontWeight = FontWeight.Bold
                    )
                }

                // TR / EN Toggle
                Row(
                    modifier = Modifier
                        .background(SurfaceDark, RoundedCornerShape(16.dp))
                        .border(1.dp, BorderDim, RoundedCornerShape(16.dp))
                        .padding(2.dp)
                ) {
                    Button(
                        onClick = { onLanguageChange(AppLanguage.TR) },
                        colors = ButtonDefaults.buttonColors(
                            containerColor = if (state.language == AppLanguage.TR) CyberGold else SurfaceDark,
                            contentColor = if (state.language == AppLanguage.TR) Void else TextMuted
                        ),
                        shape = RoundedCornerShape(16.dp),
                        contentPadding = PaddingValues(horizontal = 6.dp, vertical = 2.dp),
                        modifier = Modifier
                            .height(28.dp)
                            .testTag("lang_tr_button")
                    ) {
                        Text("🇹🇷 TR", fontSize = 9.sp, fontWeight = FontWeight.Bold)
                    }

                    Button(
                        onClick = { onLanguageChange(AppLanguage.EN) },
                        colors = ButtonDefaults.buttonColors(
                            containerColor = if (state.language == AppLanguage.EN) CyberGold else SurfaceDark,
                            contentColor = if (state.language == AppLanguage.EN) Void else TextMuted
                        ),
                        shape = RoundedCornerShape(16.dp),
                        contentPadding = PaddingValues(horizontal = 6.dp, vertical = 2.dp),
                        modifier = Modifier
                            .height(28.dp)
                            .testTag("lang_en_button")
                    ) {
                        Text("🇬🇧 EN", fontSize = 9.sp, fontWeight = FontWeight.Bold)
                    }
                }
            }
        }

        // TARGET INPUT CARD
        TargetInputCard(
            state = state,
            onUrlChange = onUrlChange,
            onRitualsChange = onRitualsChange,
            onPlaylistChange = onPlaylistChange,
            onEnviesChange = onEnviesChange,
            onTogglePlatform = onTogglePlatform,
            onToggleDeepExtraction = onToggleDeepExtraction,
            onModelChange = onModelChange,
            onToggleCloud = onToggleCloud,
            onInitiate = onInitiate
        )

        // NAVIGATION TABS
        ScrollableTabRow(
            selectedTabIndex = state.selectedTab.ordinal,
            containerColor = SurfaceDark,
            contentColor = CyberGold,
            edgePadding = 4.dp,
            divider = {},
            modifier = Modifier
                .fillMaxWidth()
                .clip(RoundedCornerShape(16.dp))
                .border(1.dp, BorderDim, RoundedCornerShape(16.dp))
        ) {
            val tabs = listOf(
                CockpitTab.PROFILE_360 to "🧠 Profil",
                CockpitTab.ASPASIA_CHAT to "💬 Aspasia",
                CockpitTab.LOGS_TELEMETRY to "📡 Telemetri",
                CockpitTab.HISTORY to "📜 Arşiv"
            )

            tabs.forEach { (tab, label) ->
                Tab(
                    selected = state.selectedTab == tab,
                    onClick = { onTabChange(tab) },
                    text = {
                        Text(
                            text = label,
                            fontSize = 11.sp,
                            fontWeight = if (state.selectedTab == tab) FontWeight.Bold else FontWeight.Normal,
                            color = if (state.selectedTab == tab) CyberGold else TextMuted
                        )
                    },
                    modifier = Modifier.testTag("tab_${tab.name.lowercase()}")
                )
            }
        }

        // AGENT CHAIN (Always visible above or integrated)
        AgentChainCard(state = state)

        // ACTIVE TAB CONTENT
        when (state.selectedTab) {
            CockpitTab.PROFILE_360 -> {
                state.holisticProfile?.let { profile ->
                    Column(verticalArrangement = Arrangement.spacedBy(16.dp)) {
                        ReconInputCard(
                            isProcessing = state.isProcessing,
                            onFeedRecon = onFeedRecon
                        )
                        HolisticProfileCard(hypotheses = liveHypotheses, profile = state.holisticProfile)
                    }
                } ?: run {
                    Card(
                        modifier = Modifier
                            .fillMaxWidth()
                            .border(1.dp, BorderDim, RoundedCornerShape(16.dp)),
                        colors = CardDefaults.cardColors(containerColor = SurfaceDark)
                    ) {
                        Box(
                            modifier = Modifier
                                .fillMaxWidth()
                                .padding(32.dp),
                            contentAlignment = Alignment.Center
                        ) {
                            Text(
                                text = "Tek geçişli Gemini çıkarımı başlatıldığında doğrulanmamış model profili burada gösterilir.",
                                fontSize = 11.sp,
                                color = TextMuted
                            )
                        }
                    }
                }
            }
            CockpitTab.ASPASIA_CHAT -> {
                AspasiaChatCard(
                    state = state,
                    onInputChange = onChatInputChange,
                    onSendMessage = onSendMessage,
                    onExplainState = onExplainState,
                    onAttachImage = onAttachImage
                )
            }
            CockpitTab.LOGS_TELEMETRY -> {
                TelemetryAndLogsCard(
                    state = state,
                    onApiKeyChange = onApiKeyChange,
                    onCookieChange = onCookieChange,
                    onSealVault = onSealVault
                )
            }
            CockpitTab.HISTORY -> {
                HistorySheet(
                    state = state,
                    onLoad = onLoadHistory,
                    onDelete = onDeleteHistory,
                    onClearAll = onClearHistory
                )
            }
        }

        // FOOTER
        Box(
            modifier = Modifier
                .fillMaxWidth()
                .border(BorderStroke(1.dp, BorderDim), RoundedCornerShape(16.dp))
                .background(SurfaceDark, RoundedCornerShape(16.dp))
                .padding(10.dp),
            contentAlignment = Alignment.Center
        ) {
            Text(
                text = s.footerText,
                fontSize = 8.sp,
                color = TextMuted,
                letterSpacing = 0.5.sp
            )
        }
    }
}
