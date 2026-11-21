package com.aistudio.pineal.heretic.ui.components

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Radar
import androidx.compose.material.icons.filled.Warning
import androidx.compose.material3.*
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.aistudio.pineal.heretic.engine.ForensicHypothesis
import com.aistudio.pineal.heretic.engine.ReconConfidence
import com.aistudio.pineal.heretic.ui.theme.*

@Composable
fun ReconRadarCard(
    hypotheses: List<ForensicHypothesis>,
    modifier: Modifier = Modifier
) {
    Card(
        modifier = modifier
            .fillMaxWidth()
            .border(1.dp, BorderDim.copy(alpha=0.5f), RoundedCornerShape(16.dp)),
        shape = RoundedCornerShape(16.dp),
        colors = CardDefaults.cardColors(containerColor = SurfaceDark.copy(alpha=0.9f))
    ) {
        Column(modifier = Modifier.padding(16.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Icon(Icons.Default.Radar, contentDescription = null, tint = MatrixGreen)
                Spacer(modifier = Modifier.width(8.dp))
                Text(
                    text = "CANLI SENTEZ AĞI",
                    style = MaterialTheme.typography.titleMedium,
                    color = CyberGold,
                    fontWeight = FontWeight.Black,
                    letterSpacing = 1.sp
                )
            }

            
            Spacer(modifier = Modifier.height(16.dp))
            if (hypotheses.isEmpty()) {
                Text(
                    text = "Sentez ağı boş. Analiz için veri girişi bekleniyor...",
                    color = TextMuted,
                    style = MaterialTheme.typography.bodySmall
                )
            } else {
                Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
                    hypotheses.forEach { hypothesis ->
                        HypothesisItem(hypothesis)
                    }
                }
            }
        }
    }
}

@Composable
fun HypothesisItem(hypothesis: ForensicHypothesis) {
    val statusColor = when (hypothesis.status) {
        ReconConfidence.SONAR_ATILDI.name -> WarningGold
        ReconConfidence.KANITLANDI.name -> CyberCyan
        ReconConfidence.KRITIK_FIRSAT.name -> BloodRed
        else -> TextMuted
    }

    
    Surface(
        modifier = Modifier
            .fillMaxWidth()
            .border(1.dp, statusColor.copy(alpha=0.3f), RoundedCornerShape(16.dp)),
        shape = RoundedCornerShape(16.dp),
        color = SurfaceDark
    ) {
        Column(modifier = Modifier.padding(12.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Surface(shape = RoundedCornerShape(16.dp), color = statusColor.copy(alpha = 0.1f)) {
                    Text(
                        text = hypothesis.status.replace("_", " "),
                        color = statusColor,
                        fontWeight = FontWeight.Bold,
                        style = MaterialTheme.typography.labelSmall,
                        modifier = Modifier.padding(horizontal = 8.dp, vertical = 4.dp)
                    )
                }
                Spacer(modifier = Modifier.width(12.dp))
                Text(
                    text = hypothesis.psychologicalTrait,
                    color = TextMain,
                    style = MaterialTheme.typography.titleSmall,
                    fontWeight = FontWeight.Bold
                )
            }

            Spacer(modifier = Modifier.height(8.dp))
            Text(
                text = hypothesis.forensicImplication,
                color = TextMuted,
                style = MaterialTheme.typography.bodySmall
            )

            Spacer(modifier = Modifier.height(8.dp))

            Surface(
                modifier = Modifier
                    .fillMaxWidth()
                    .border(1.dp, MatrixGreenDim.copy(alpha=0.5f), RoundedCornerShape(16.dp)),
                shape = RoundedCornerShape(16.dp),
                color = SurfaceLighter
            ) {
                Text(
                    text = "📎 KANIT: ${hypothesis.extractedEvidence}",
                    color = MatrixGreenLight,
                    style = MaterialTheme.typography.bodySmall,
                    modifier = Modifier.padding(8.dp)
                )
            }

            
            if (hypothesis.missingDataVectors.isNotEmpty()) {
                Spacer(modifier = Modifier.height(8.dp))
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Icon(Icons.Default.Warning, contentDescription = null, tint = WarningGold, modifier = Modifier.size(16.dp))
                    Spacer(modifier = Modifier.width(4.dp))
                    Text(
                        text = "Eksik Vektör: ${hypothesis.missingDataVectors.joinToString(", ")}",
                        color = WarningGoldLight,
                        style = MaterialTheme.typography.labelSmall
                    )
                }
            }
        }
    }
}
