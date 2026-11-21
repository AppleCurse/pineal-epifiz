package com.aistudio.pineal.heretic.ui.components

import androidx.compose.foundation.border
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.aistudio.pineal.heretic.ui.theme.*

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun ReconInputCard(
    isProcessing: Boolean,
    onFeedRecon: (String) -> Unit
) {
    var reconInput by remember { mutableStateOf("") }

    Card(
        modifier = Modifier
            .fillMaxWidth()
            .border(1.dp, MatrixGreen, RoundedCornerShape(16.dp)),
        colors = CardDefaults.cardColors(containerColor = SurfaceDark)
    ) {
        Column(
            modifier = Modifier
                .fillMaxWidth()
                .padding(12.dp),
            verticalArrangement = Arrangement.spacedBy(8.dp)
        ) {
            Text(
                text = "KILAVUZ GEMİ (RECON ENGINE)",
                fontSize = 11.sp,
                fontWeight = FontWeight.Bold,
                color = MatrixGreenLight
            )
            Text(
                text = "Gözlemlediğiniz yeni davranışları, konuşmaları veya eylemleri buraya girin. Kılavuz gemi bu kırıntıları işleyerek haritayı dinamik olarak güncelleyecektir.",
                fontSize = 10.sp,
                color = TextMuted,
                lineHeight = 14.sp
            )

            OutlinedTextField(
                value = reconInput,
                onValueChange = { reconInput = it },
                modifier = Modifier
                    .fillMaxWidth()
                    .heightIn(min = 60.dp),
                placeholder = { Text("Örn: Bugün bana sürekli projeyi kendisinin kurtardığını anlattı...", fontSize = 10.sp) },
                textStyle = LocalTextStyle.current.copy(fontSize = 10.sp, color = TextMain),
                colors = OutlinedTextFieldDefaults.colors(
                    focusedContainerColor = SurfaceDark, unfocusedContainerColor = SurfaceDark,
                    focusedBorderColor = MatrixGreenLight,
                    unfocusedBorderColor = BorderDim,
                    cursorColor = MatrixGreen
                ),
                enabled = !isProcessing
            )

            Button(
                onClick = {
                    if (reconInput.isNotBlank()) {
                        onFeedRecon(reconInput)
                        reconInput = ""
                    }
                },
                enabled = !isProcessing && reconInput.isNotBlank(),
                modifier = Modifier.align(Alignment.End),
                colors = ButtonDefaults.buttonColors(
                    containerColor = MatrixGreen,
                    contentColor = Void,
                    disabledContainerColor = BorderDim
                ),
                shape = RoundedCornerShape(16.dp)
            ) {
                Text(if (isProcessing) "İŞLENİYOR..." else "KAYDA GEÇ", fontSize = 10.sp, fontWeight = FontWeight.Bold)
            }
        }
    }
}
