package com.aistudio.pineal.heretic.ui.components

import androidx.compose.foundation.border
import com.aistudio.pineal.heretic.ui.theme.*
import androidx.compose.ui.unit.sp
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.*
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import com.aistudio.pineal.heretic.engine.ForensicHypothesis
import com.aistudio.pineal.heretic.engine.ReconConfidence
import com.aistudio.pineal.heretic.data.model.HolisticProfile
import android.content.Intent
import androidx.compose.ui.platform.LocalContext
import androidx.compose.material.icons.filled.Share
import androidx.compose.material.icons.Icons


    @Composable
    fun HolisticProfileCard(
        hypotheses: List<ForensicHypothesis>,
        profile: HolisticProfile? = null,
        modifier: Modifier = Modifier
    ) {
        val operationalFindings = hypotheses.filter {
            it.status == ReconConfidence.KANITLANDI.name || it.status == ReconConfidence.KRITIK_FIRSAT.name
        }

        Card(
            modifier = modifier
                .fillMaxWidth()
                .border(1.dp, BorderDim.copy(alpha=0.5f), RoundedCornerShape(16.dp)),
            shape = RoundedCornerShape(16.dp),
            colors = CardDefaults.cardColors(containerColor = SurfaceDark.copy(alpha=0.9f))
        ) {
            Column(modifier = Modifier.padding(16.dp)) {
                val context = LocalContext.current
                Row(modifier = Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween, verticalAlignment = androidx.compose.ui.Alignment.CenterVertically) {
                    Text(
                        text = "BİLİŞSEL PROFİL ÖZETİ",
                        style = MaterialTheme.typography.titleMedium,
                        color = BloodRed,
                        fontWeight = FontWeight.Black,
                        letterSpacing = 1.sp
                    )
                    if (profile != null) {
                        IconButton(onClick = {
                            val shareIntent = Intent().apply {
                                action = Intent.ACTION_SEND
                                type = "text/plain"
                                val text = """
                                    PINEAL-GLAND BİLİŞSEL PROFİL ÖZETİ
                                    Profil: @${profile.username}
                                    Yaratıcılık: ${profile.cognitive.metrics.creativity}
                                    Liderlik: ${profile.cognitive.metrics.leadership}

                                    Motivasyonlar: ${profile.passions.corePassions.joinToString()}
                                    Tavsiye: ${profile.bridge?.conversationStarterRationale}
                                    """.trimIndent()
                                putExtra(Intent.EXTRA_TEXT, text)
                            }
                            context.startActivity(Intent.createChooser(shareIntent, "Profili Paylaş"))
                        }) {
                            Icon(Icons.Default.Share, contentDescription = "Dışa Aktar", tint = TrustBlue)
                        }
                    }
                }
                Spacer(modifier = Modifier.height(2.dp))
                Text(
                    text = "Derin Motivasyonlar & Bilişsel Dalga Formları",
                    style = MaterialTheme.typography.bodySmall,
                    color = TextMuted,
                    fontWeight = FontWeight.Bold,
                    letterSpacing = 0.5.sp
                )

                Spacer(modifier = Modifier.height(16.dp))
                if (profile != null) {
                    val m = profile.cognitive.metrics
                    if (m.creativity > 0.0 || m.analytical > 0.0 || m.empathy > 0.0 || m.leadership > 0.0 || m.adaptability > 0.0) {
                        CognitiveRadarChart(
                            metrics = listOf(
                                "Yaratıcılık" to m.creativity,
                                "Analitik" to m.analytical,
                                "Empati" to m.empathy,
                                "Liderlik" to m.leadership,
                                "Adaptasyon" to m.adaptability
                            ),
                            modifier = Modifier.fillMaxWidth().height(250.dp)
                        )
                        Spacer(modifier = Modifier.height(16.dp))
                    }
                }


                if (operationalFindings.isEmpty()) {
                    Text(
                        text = "Henüz derinlemesine bir motivasyon belirlenmedi. Daha fazla veri akışı bekleniyor.",
                        color = TextMuted,
                        style = MaterialTheme.typography.bodySmall
                    )
                } else {
                    Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                        operationalFindings.forEach { finding ->
                            val isCritical = finding.status == ReconConfidence.KRITIK_FIRSAT.name
                            Surface(
                                modifier = Modifier
                                    .fillMaxWidth()
                                    .border(
                                        1.dp,
                                        if (isCritical) BloodRed.copy(alpha=0.4f) else MatrixGreenDim,
                                        RoundedCornerShape(16.dp)
                                    ),
                                shape = RoundedCornerShape(16.dp),
                                color = SurfaceDark
                            ) {
                                Column(modifier = Modifier.padding(12.dp)) {
                                    Row(
                                        horizontalArrangement = Arrangement.SpaceBetween,
                                        modifier = Modifier.fillMaxWidth()
                                    ) {
                                        Text(
                                            text = "🎯 ${finding.psychologicalTrait.uppercase()}",
                                            color = if (isCritical) BloodRed else MatrixGreenLight,
                                            fontWeight = FontWeight.ExtraBold,
                                            style = MaterialTheme.typography.labelMedium,
                                            letterSpacing = 0.5.sp
                                        )
                                        Text(
                                            text = "[${finding.status}]",
                                            color = if (isCritical) BloodRed else MatrixGreenLight,
                                            fontWeight = FontWeight.Black,
                                            style = MaterialTheme.typography.labelSmall
                                        )
                                    }
                                    Spacer(modifier = Modifier.height(6.dp))
                                    Text(
                                        text = finding.forensicImplication,
                                        color = TextMain,
                                        style = MaterialTheme.typography.bodySmall
                                    )
                                }
                            }
                        }
                    }
                }
            }
        }
    }