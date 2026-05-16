package com.o2monitor.app.ui.dashboard

import android.content.SharedPreferences
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.unit.dp
import com.patrykandpatrick.vico.compose.cartesian.CartesianChartHost
import com.patrykandpatrick.vico.compose.cartesian.axis.rememberBottom
import com.patrykandpatrick.vico.compose.cartesian.axis.rememberStart
import com.patrykandpatrick.vico.compose.cartesian.layer.rememberLine
import com.patrykandpatrick.vico.compose.cartesian.layer.rememberLineCartesianLayer
import com.patrykandpatrick.vico.compose.cartesian.rememberCartesianChart
import com.patrykandpatrick.vico.compose.cartesian.rememberVicoScrollState
import com.patrykandpatrick.vico.compose.common.fill
import com.patrykandpatrick.vico.core.cartesian.axis.HorizontalAxis
import com.patrykandpatrick.vico.core.cartesian.axis.VerticalAxis
import com.patrykandpatrick.vico.core.cartesian.data.CartesianChartModelProducer
import com.patrykandpatrick.vico.core.cartesian.data.CartesianLayerRangeProvider
import com.patrykandpatrick.vico.core.cartesian.data.CartesianValueFormatter
import com.patrykandpatrick.vico.core.cartesian.data.lineSeries
import com.patrykandpatrick.vico.core.cartesian.layer.LineCartesianLayer
import com.o2monitor.app.network.ApiClient
import com.o2monitor.app.network.ReadingRecord
import okhttp3.OkHttpClient
import java.time.Instant
import java.time.ZoneId
import java.time.format.DateTimeFormatter

private val SPO2_COLOR = Color(0xFF22c55e)
private val HR_COLOR = Color(0xFF3b82f6)
private val CHART_AXIS_COLOR = Color(0xFF9CA3AF)

private val TIME_RANGES = listOf(1, 6, 24)
private val TIME_RANGE_LABELS = listOf("1h", "6h", "24h")

@Composable
fun VitalsChart(
    patientId: String,
    prefs: SharedPreferences,
    httpClient: OkHttpClient,
    modifier: Modifier = Modifier
) {
    val serverUrl = remember { prefs.getString("server_url", "") ?: "" }
    val apiKey = remember { prefs.getString("api_key", "") ?: "" }

    val apiClient = remember(serverUrl, apiKey) {
        ApiClient(
            httpClient = httpClient,
            baseUrl = serverUrl,
            apiKey = apiKey
        )
    }

    var selectedHours by remember { mutableIntStateOf(1) }
    var readings by remember { mutableStateOf<List<ReadingRecord>>(emptyList()) }
    var isLoading by remember { mutableStateOf(false) }
    var errorMessage by remember { mutableStateOf<String?>(null) }

    LaunchedEffect(patientId, selectedHours, serverUrl, apiKey) {
        if (patientId.isBlank() || serverUrl.isBlank()) return@LaunchedEffect
        isLoading = true
        errorMessage = null
        val result = apiClient.getReadings(patientId, selectedHours)
        result.onSuccess { response ->
            readings = response.readings
        }.onFailure { ex ->
            errorMessage = ex.message ?: "Failed to load readings"
            readings = emptyList()
        }
        isLoading = false
    }

    Column(modifier = modifier.fillMaxWidth()) {
        Row(
            modifier = Modifier.fillMaxWidth(),
            horizontalArrangement = Arrangement.spacedBy(8.dp)
        ) {
            TIME_RANGES.forEachIndexed { index, hours ->
                val isSelected = hours == selectedHours
                Button(
                    onClick = { selectedHours = hours },
                    colors = ButtonDefaults.buttonColors(
                        containerColor = if (isSelected) MaterialTheme.colorScheme.primary
                        else MaterialTheme.colorScheme.surface
                    ),
                    modifier = Modifier.weight(1f)
                ) {
                    Text(
                        text = TIME_RANGE_LABELS[index],
                        style = MaterialTheme.typography.labelMedium,
                        color = if (isSelected) MaterialTheme.colorScheme.onPrimary
                        else MaterialTheme.colorScheme.onSurface
                    )
                }
            }
        }

        Spacer(modifier = Modifier.height(12.dp))

        Box(
            modifier = Modifier
                .fillMaxWidth()
                .height(200.dp),
            contentAlignment = Alignment.Center
        ) {
            when {
                isLoading -> CircularProgressIndicator(color = SPO2_COLOR)
                errorMessage != null -> Text(
                    text = errorMessage ?: "Error loading data",
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.error
                )
                readings.isEmpty() -> Text(
                    text = "No data for the last ${selectedHours}h",
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onBackground.copy(alpha = 0.5f)
                )
                else -> VitalsChartContent(
                    readings = readings,
                    modifier = Modifier.fillMaxSize()
                )
            }
        }

        if (readings.isNotEmpty() && !isLoading) {
            Spacer(modifier = Modifier.height(8.dp))
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.spacedBy(24.dp, Alignment.CenterHorizontally)
            ) {
                ChartLegendItem(color = SPO2_COLOR, label = "SpO2 (%)")
                ChartLegendItem(color = HR_COLOR, label = "Heart Rate (bpm)")
            }
        }
    }
}

@Composable
private fun VitalsChartContent(
    readings: List<ReadingRecord>,
    modifier: Modifier = Modifier
) {
    val modelProducer = remember { CartesianChartModelProducer() }

    LaunchedEffect(readings) {
        modelProducer.runTransaction {
            lineSeries {
                series(readings.map { it.spo2.toFloat() })
                series(readings.map { it.heartRate.toFloat() })
            }
        }
    }

    val timeFormatter = remember {
        DateTimeFormatter.ofPattern("HH:mm").withZone(ZoneId.systemDefault())
    }

    val step = readings.size.coerceAtLeast(1) / 4
    val xValueFormatter = CartesianValueFormatter { _, x, _ ->
        val idx = x.toInt()
        if (step > 0 && idx % step == 0) {
            readings.getOrNull(idx)?.let { record ->
                runCatching { timeFormatter.format(Instant.parse(record.timestamp)) }.getOrDefault("")
            } ?: ""
        } else ""
    }

    val spo2Layer = rememberLineCartesianLayer(
        lineProvider = LineCartesianLayer.LineProvider.series(
            LineCartesianLayer.rememberLine(
                fill = LineCartesianLayer.LineFill.single(fill(SPO2_COLOR))
            )
        ),
        rangeProvider = CartesianLayerRangeProvider.fixed(minY = 80.0, maxY = 100.0)
    )

    val hrLayer = rememberLineCartesianLayer(
        lineProvider = LineCartesianLayer.LineProvider.series(
            LineCartesianLayer.rememberLine(
                fill = LineCartesianLayer.LineFill.single(fill(HR_COLOR))
            )
        ),
        rangeProvider = CartesianLayerRangeProvider.fixed(minY = 40.0, maxY = 140.0)
    )

    CartesianChartHost(
        chart = rememberCartesianChart(
            spo2Layer,
            hrLayer,
            startAxis = VerticalAxis.rememberStart(),
            bottomAxis = HorizontalAxis.rememberBottom(valueFormatter = xValueFormatter)
        ),
        modelProducer = modelProducer,
        scrollState = rememberVicoScrollState(scrollEnabled = false),
        modifier = modifier
    )
}

@Composable
private fun ChartLegendItem(color: Color, label: String) {
    Row(
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.spacedBy(6.dp)
    ) {
        Canvas(modifier = Modifier.size(10.dp)) {
            drawRect(color = color)
        }
        Text(
            text = label,
            style = MaterialTheme.typography.labelSmall,
            color = CHART_AXIS_COLOR
        )
    }
}
