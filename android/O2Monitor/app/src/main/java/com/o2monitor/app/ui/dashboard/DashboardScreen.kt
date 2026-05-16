package com.o2monitor.app.ui.dashboard

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.content.IntentFilter
import android.content.SharedPreferences
import android.net.Uri
import android.os.PowerManager
import android.provider.Settings
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Settings
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.hilt.navigation.compose.hiltViewModel
import androidx.lifecycle.ViewModel
import androidx.localbroadcastmanager.content.LocalBroadcastManager
import com.o2monitor.app.ble.BleService
import com.o2monitor.app.ble.BleState
import dagger.hilt.android.lifecycle.HiltViewModel
import javax.inject.Inject

@HiltViewModel
class DashboardViewModel @Inject constructor(
    val prefs: SharedPreferences,
    val httpClient: okhttp3.OkHttpClient
) : ViewModel() {
    val patientName: String
        get() = prefs.getString("patient_name", "Unknown Patient") ?: "Unknown Patient"
    val patientId: String
        get() = prefs.getString("patient_id", "") ?: ""
}

private data class OxiDisplayState(
    val spo2: Int? = null,
    val heartRate: Int? = null,
    val batteryLevel: Int? = null,
    val movement: Int? = null,
    val uploadOk: Boolean? = null,
    val queueCount: Int = 0
)

private fun spo2Color(spo2: Int): Color = when {
    spo2 >= 95 -> Color(0xFF4CAF50)
    spo2 >= 92 -> Color(0xFFFFEB3B)
    spo2 >= 90 -> Color(0xFFFF9800)
    else -> Color(0xFFF44336)
}

@Composable
fun DashboardScreen(
    viewModel: DashboardViewModel = hiltViewModel(),
    permissionsGranted: Boolean = false,
    onSettingsClick: () -> Unit = {}
) {
    val patientName = remember { viewModel.patientName }
    val patientId = remember { viewModel.patientId }
    val prefs = remember { viewModel.prefs }
    val context = LocalContext.current

    var isRunning by remember { mutableStateOf(false) }
    var bleState by remember { mutableStateOf(BleState.IDLE) }
    var oxiState by remember { mutableStateOf(OxiDisplayState()) }

    val powerManager = context.getSystemService(Context.POWER_SERVICE) as PowerManager
    var isBatteryOptimized by remember {
        mutableStateOf(!powerManager.isIgnoringBatteryOptimizations(context.packageName))
    }

    // Register broadcast receiver for readings
    DisposableEffect(Unit) {
        val receiver = object : BroadcastReceiver() {
            override fun onReceive(ctx: Context, intent: Intent) {
                if (intent.action == BleService.ACTION_READING) {
                    oxiState = OxiDisplayState(
                        spo2 = intent.getIntExtra(BleService.EXTRA_SPO2, 0),
                        heartRate = intent.getIntExtra(BleService.EXTRA_HEART_RATE, 0),
                        batteryLevel = intent.getIntExtra(BleService.EXTRA_BATTERY_LEVEL, 0),
                        movement = intent.getIntExtra(BleService.EXTRA_MOVEMENT, 0),
                        uploadOk = intent.getBooleanExtra(BleService.EXTRA_UPLOAD_OK, false),
                        queueCount = intent.getIntExtra(BleService.EXTRA_QUEUE_COUNT, 0)
                    )
                    bleState = BleState.READING
                }
            }
        }
        val filter = IntentFilter(BleService.ACTION_READING)
        LocalBroadcastManager.getInstance(context).registerReceiver(receiver, filter)
        onDispose {
            LocalBroadcastManager.getInstance(context).unregisterReceiver(receiver)
        }
    }

    Surface(
        modifier = Modifier.fillMaxSize(),
        color = MaterialTheme.colorScheme.background
    ) {
        Column(
            modifier = Modifier
                .fillMaxSize()
                .verticalScroll(rememberScrollState())
                .padding(horizontal = 24.dp)
                .padding(top = 48.dp, bottom = 24.dp),
            verticalArrangement = Arrangement.Top,
            horizontalAlignment = Alignment.CenterHorizontally
        ) {
            Box(modifier = Modifier.fillMaxWidth()) {
                Text(
                    text = patientName,
                    style = MaterialTheme.typography.titleLarge,
                    color = MaterialTheme.colorScheme.onBackground,
                    modifier = Modifier.align(Alignment.Center)
                )
                IconButton(
                    onClick = onSettingsClick,
                    modifier = Modifier.align(Alignment.CenterEnd)
                ) {
                    Icon(
                        imageVector = Icons.Filled.Settings,
                        contentDescription = "Settings",
                        tint = MaterialTheme.colorScheme.onBackground
                    )
                }
            }

            Spacer(modifier = Modifier.height(8.dp))

            // BLE state indicator
            val stateLabel = when (bleState) {
                BleState.IDLE -> "Idle"
                BleState.SCANNING -> "Scanning…"
                BleState.CONNECTING -> "Connecting…"
                BleState.READING -> "Connected"
                BleState.RECONNECTING -> "Reconnecting…"
            }
            Text(
                text = stateLabel,
                style = MaterialTheme.typography.bodyMedium,
                color = if (bleState == BleState.READING)
                    Color(0xFF4CAF50)
                else
                    MaterialTheme.colorScheme.onBackground.copy(alpha = 0.6f)
            )

            // Upload status
            val uploadStatus = oxiState.uploadOk
            if (uploadStatus != null) {
                Spacer(modifier = Modifier.height(4.dp))
                val (uploadLabel, uploadColor) = if (uploadStatus) {
                    "Uploading" to Color(0xFF4CAF50)
                } else {
                    "Offline (${oxiState.queueCount} queued)" to Color(0xFFFF9800)
                }
                Text(
                    text = uploadLabel,
                    style = MaterialTheme.typography.bodySmall,
                    color = uploadColor
                )
            }

            Spacer(modifier = Modifier.height(32.dp))

            // SpO2 display
            val spo2 = oxiState.spo2
            Card(
                modifier = Modifier.fillMaxWidth(),
                colors = CardDefaults.cardColors(
                    containerColor = MaterialTheme.colorScheme.surface
                )
            ) {
                Column(
                    modifier = Modifier.padding(24.dp),
                    horizontalAlignment = Alignment.CenterHorizontally
                ) {
                    Text(
                        text = "SpO2",
                        style = MaterialTheme.typography.labelLarge,
                        color = MaterialTheme.colorScheme.onSurface.copy(alpha = 0.6f)
                    )
                    Text(
                        text = if (spo2 != null) "${spo2}%" else "--",
                        fontSize = 72.sp,
                        fontWeight = FontWeight.Bold,
                        color = if (spo2 != null) spo2Color(spo2) else MaterialTheme.colorScheme.onSurface
                    )
                }
            }

            Spacer(modifier = Modifier.height(16.dp))

            // Heart rate and battery row
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.spacedBy(16.dp)
            ) {
                Card(
                    modifier = Modifier.weight(1f),
                    colors = CardDefaults.cardColors(
                        containerColor = MaterialTheme.colorScheme.surface
                    )
                ) {
                    Column(
                        modifier = Modifier.padding(16.dp),
                        horizontalAlignment = Alignment.CenterHorizontally
                    ) {
                        Text(
                            text = "Heart Rate",
                            style = MaterialTheme.typography.labelMedium,
                            color = MaterialTheme.colorScheme.onSurface.copy(alpha = 0.6f)
                        )
                        Text(
                            text = oxiState.heartRate?.let { "$it bpm" } ?: "--",
                            fontSize = 28.sp,
                            fontWeight = FontWeight.Bold,
                            color = MaterialTheme.colorScheme.onSurface
                        )
                    }
                }

                Card(
                    modifier = Modifier.weight(1f),
                    colors = CardDefaults.cardColors(
                        containerColor = MaterialTheme.colorScheme.surface
                    )
                ) {
                    Column(
                        modifier = Modifier.padding(16.dp),
                        horizontalAlignment = Alignment.CenterHorizontally
                    ) {
                        Text(
                            text = "Battery",
                            style = MaterialTheme.typography.labelMedium,
                            color = MaterialTheme.colorScheme.onSurface.copy(alpha = 0.6f)
                        )
                        Text(
                            text = oxiState.batteryLevel?.let { "$it%" } ?: "--",
                            fontSize = 28.sp,
                            fontWeight = FontWeight.Bold,
                            color = MaterialTheme.colorScheme.onSurface
                        )
                    }
                }
            }

            Spacer(modifier = Modifier.height(24.dp))

            // SpO2 + HR history chart
            if (patientId.isNotBlank()) {
                Text(
                    text = "History",
                    style = MaterialTheme.typography.labelLarge,
                    color = MaterialTheme.colorScheme.onBackground.copy(alpha = 0.7f),
                    modifier = Modifier.align(Alignment.Start)
                )
                Spacer(modifier = Modifier.height(8.dp))
                VitalsChart(
                    patientId = patientId,
                    prefs = prefs,
                    httpClient = viewModel.httpClient,
                    modifier = Modifier.fillMaxWidth()
                )
                Spacer(modifier = Modifier.height(24.dp))
            } else {
                Spacer(modifier = Modifier.height(32.dp))
            }

            // Start / Stop button
            Button(
                enabled = permissionsGranted || isRunning,
                onClick = {
                    if (isRunning) {
                        val stopIntent = Intent(context, BleService::class.java).apply {
                            action = BleService.ACTION_STOP
                        }
                        context.startService(stopIntent)
                        isRunning = false
                        bleState = BleState.IDLE
                        oxiState = OxiDisplayState()
                    } else {
                        val startIntent = Intent(context, BleService::class.java)
                        context.startForegroundService(startIntent)
                        isRunning = true
                        bleState = BleState.SCANNING
                    }
                },
                colors = ButtonDefaults.buttonColors(
                    containerColor = if (isRunning) MaterialTheme.colorScheme.error
                    else MaterialTheme.colorScheme.primary
                ),
                modifier = Modifier.fillMaxWidth()
            ) {
                Text(
                    text = when {
                        !permissionsGranted && !isRunning -> "Permissions required"
                        isRunning -> "Stop Monitoring"
                        else -> "Start Monitoring"
                    },
                    style = MaterialTheme.typography.labelLarge
                )
            }

            if (isBatteryOptimized) {
                Spacer(modifier = Modifier.height(12.dp))
                Button(
                    onClick = {
                        val intent = Intent(
                            Settings.ACTION_REQUEST_IGNORE_BATTERY_OPTIMIZATIONS,
                            Uri.parse("package:${context.packageName}")
                        )
                        context.startActivity(intent)
                        isBatteryOptimized = !powerManager.isIgnoringBatteryOptimizations(context.packageName)
                    },
                    colors = ButtonDefaults.buttonColors(
                        containerColor = MaterialTheme.colorScheme.secondary
                    ),
                    modifier = Modifier.fillMaxWidth()
                ) {
                    Text(
                        text = "Disable Battery Optimization",
                        style = MaterialTheme.typography.labelLarge
                    )
                }
            }
        }
    }
}
