package com.o2monitor.app.ui.settings

import android.annotation.SuppressLint
import android.bluetooth.BluetoothManager
import android.bluetooth.le.ScanCallback
import android.bluetooth.le.ScanResult
import android.bluetooth.le.ScanSettings
import android.content.Context
import android.content.SharedPreferences
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.material3.TopAppBar
import androidx.compose.material3.TopAppBarDefaults
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.setValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.unit.dp
import androidx.hilt.navigation.compose.hiltViewModel
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.o2monitor.app.BuildConfig
import com.o2monitor.app.network.ApiClient
import com.o2monitor.app.network.PatientSummary
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import javax.inject.Inject

private data class ScannedDevice(
    val name: String,
    val address: String,
    val rssi: Int?,
    val isCurrent: Boolean = false
)

@HiltViewModel
class SettingsViewModel @Inject constructor(
    private val prefs: SharedPreferences,
    private val httpClient: okhttp3.OkHttpClient
) : ViewModel() {

    // Server config
    var serverUrl by mutableStateOf(prefs.getString("server_url", "") ?: "")
    var apiKey by mutableStateOf(prefs.getString("api_key", "") ?: "")

    // Device pairing
    var currentDeviceMac by mutableStateOf(prefs.getString("device_mac", null))
        private set

    // Patient selection
    var currentPatientName by mutableStateOf(prefs.getString("patient_name", null))
        private set

    var patients by mutableStateOf<List<PatientSummary>>(emptyList())
        private set
    var isLoadingPatients by mutableStateOf(false)
        private set
    var patientLoadError by mutableStateOf<String?>(null)
        private set

    fun saveServerConfig() {
        prefs.edit()
            .putString("server_url", serverUrl.trim().trimEnd('/'))
            .putString("api_key", apiKey.trim())
            .apply()
    }

    fun saveDeviceMac(mac: String) {
        prefs.edit().putString("device_mac", mac).apply()
        currentDeviceMac = mac
    }

    fun selectPatient(patient: PatientSummary) {
        prefs.edit()
            .putString("patient_id", patient.id)
            .putString("patient_name", patient.name)
            .apply()
        currentPatientName = patient.name
        patients = emptyList()
    }

    fun loadPatients() {
        viewModelScope.launch {
            isLoadingPatients = true
            patientLoadError = null
            val url = prefs.getString("server_url", "") ?: ""
            val key = prefs.getString("api_key", "") ?: ""
            val client = ApiClient(httpClient, url, key)
            val result = client.getPatients()
            isLoadingPatients = false
            if (result.isSuccess) {
                patients = result.getOrDefault(emptyList())
            } else {
                patientLoadError = result.exceptionOrNull()?.message ?: "Failed to load patients"
            }
        }
    }

    fun clearPatientList() {
        patients = emptyList()
        patientLoadError = null
    }

    fun clearAllSettings(onDone: () -> Unit) {
        prefs.edit().clear().apply()
        onDone()
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun SettingsScreen(
    onBack: () -> Unit,
    viewModel: SettingsViewModel = hiltViewModel()
) {
    val context = LocalContext.current
    val scope = rememberCoroutineScope()

    // BLE scan state — managed in the composable since it needs Context
    var isScanning by remember { mutableStateOf(false) }
    var scannedDevices by remember { mutableStateOf<List<ScannedDevice>>(emptyList()) }
    var scanError by remember { mutableStateOf<String?>(null) }

    val bluetoothManager = remember {
        context.getSystemService(Context.BLUETOOTH_SERVICE) as BluetoothManager
    }
    val bluetoothAdapter = remember { bluetoothManager.adapter }

    // BLE scan callback — kept stable via remember so DisposableEffect cleanup works correctly
    var activeScanCallback by remember { mutableStateOf<ScanCallback?>(null) }

    fun stopScan() {
        activeScanCallback?.let { cb ->
            @SuppressLint("MissingPermission")
            val scanner = bluetoothAdapter?.bluetoothLeScanner
            scanner?.stopScan(cb)
        }
        activeScanCallback = null
        isScanning = false
    }

    @SuppressLint("MissingPermission")
    fun startScan() {
        val scanner = bluetoothAdapter?.bluetoothLeScanner
        if (scanner == null) {
            scanError = "Bluetooth not available"
            return
        }
        val savedMac = viewModel.currentDeviceMac?.trim()
        scannedDevices = savedMac
            ?.takeIf { it.isNotBlank() }
            ?.let {
                listOf(
                    ScannedDevice(
                        name = "Current device",
                        address = it,
                        rssi = null,
                        isCurrent = true
                    )
                )
            }
            ?: emptyList()
        scanError = null
        isScanning = true

        val cb = object : ScanCallback() {
            override fun onScanResult(callbackType: Int, result: ScanResult) {
                val address = result.device.address ?: return
                val advertisedName = result.device.name ?: result.scanRecord?.deviceName
                val currentMac = viewModel.currentDeviceMac?.trim()
                val isCurrent = !currentMac.isNullOrBlank() &&
                    address.equals(currentMac, ignoreCase = true)
                val nameMatches = advertisedName?.let { name ->
                    name.startsWith("O2") ||
                        name.startsWith("Checkme") ||
                        name.startsWith("Viatom") ||
                        name.startsWith("Wellue")
                } == true

                if (!isCurrent && !nameMatches) return

                val name = advertisedName
                    ?.takeIf { it.isNotBlank() }
                    ?: if (isCurrent) "Current device" else return
                val rssi = result.rssi
                // Deduplicate by address, update RSSI
                scannedDevices = scannedDevices
                    .filter { it.address != address }
                    .plus(ScannedDevice(name, address, rssi, isCurrent))
                    .sortedWith(
                        compareByDescending<ScannedDevice> { it.isCurrent }
                            .thenByDescending { it.rssi ?: Int.MIN_VALUE }
                    )
            }

            override fun onScanFailed(errorCode: Int) {
                scanError = "Scan failed (error $errorCode)"
                isScanning = false
                activeScanCallback = null
            }
        }

        activeScanCallback = cb
        val settings = ScanSettings.Builder()
            .setScanMode(ScanSettings.SCAN_MODE_LOW_LATENCY)
            .build()
        scanner.startScan(null, settings, cb)

        // Auto-stop after 10 seconds
        scope.launch {
            delay(10_000L)
            stopScan()
        }
    }

    // Clean up any active scan when the composable leaves
    DisposableEffect(Unit) {
        onDispose { stopScan() }
    }

    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text("Settings") },
                navigationIcon = {
                    IconButton(onClick = onBack) {
                        Icon(
                            imageVector = Icons.AutoMirrored.Filled.ArrowBack,
                            contentDescription = "Back"
                        )
                    }
                },
                colors = TopAppBarDefaults.topAppBarColors(
                    containerColor = MaterialTheme.colorScheme.surface,
                    titleContentColor = MaterialTheme.colorScheme.onSurface
                )
            )
        },
        containerColor = MaterialTheme.colorScheme.background
    ) { innerPadding ->
        Column(
            modifier = Modifier
                .fillMaxSize()
                .padding(innerPadding)
                .verticalScroll(rememberScrollState())
                .padding(16.dp),
            verticalArrangement = Arrangement.spacedBy(24.dp)
        ) {
            // ---- Server Configuration ----
            SectionCard(title = "Server Configuration") {
                OutlinedTextField(
                    value = viewModel.serverUrl,
                    onValueChange = { viewModel.serverUrl = it },
                    label = { Text("Server URL") },
                    placeholder = { Text("https://your-api.azurewebsites.net") },
                    modifier = Modifier.fillMaxWidth(),
                    singleLine = true,
                    keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Uri)
                )
                Spacer(modifier = Modifier.height(12.dp))
                OutlinedTextField(
                    value = viewModel.apiKey,
                    onValueChange = { viewModel.apiKey = it },
                    label = { Text("API Key") },
                    modifier = Modifier.fillMaxWidth(),
                    singleLine = true,
                    visualTransformation = PasswordVisualTransformation(),
                    keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Password)
                )
                Spacer(modifier = Modifier.height(12.dp))
                Button(
                    onClick = { viewModel.saveServerConfig() },
                    modifier = Modifier.fillMaxWidth()
                ) {
                    Text("Save Server Settings")
                }
            }

            // ---- Device Pairing ----
            SectionCard(title = "Device Pairing") {
                val savedMac = viewModel.currentDeviceMac
                Text(
                    text = "Current Device: ${savedMac ?: "None"}",
                    style = MaterialTheme.typography.bodyMedium,
                    color = MaterialTheme.colorScheme.onSurface
                )
                Spacer(modifier = Modifier.height(12.dp))

                if (scanError != null) {
                    Text(
                        text = scanError!!,
                        color = MaterialTheme.colorScheme.error,
                        style = MaterialTheme.typography.bodySmall
                    )
                    Spacer(modifier = Modifier.height(8.dp))
                }

                Button(
                    onClick = {
                        if (isScanning) {
                            stopScan()
                        } else {
                            startScan()
                        }
                    },
                    modifier = Modifier.fillMaxWidth(),
                    colors = ButtonDefaults.buttonColors(
                        containerColor = if (isScanning)
                            MaterialTheme.colorScheme.error
                        else
                            MaterialTheme.colorScheme.primary
                    )
                ) {
                    if (isScanning) {
                        Row(
                            verticalAlignment = Alignment.CenterVertically,
                            horizontalArrangement = Arrangement.spacedBy(8.dp)
                        ) {
                            CircularProgressIndicator(
                                modifier = Modifier.size(16.dp),
                                color = MaterialTheme.colorScheme.onError,
                                strokeWidth = 2.dp
                            )
                            Text("Stop Scanning")
                        }
                    } else {
                        Text("Scan for Devices")
                    }
                }

                if (scannedDevices.isNotEmpty()) {
                    Spacer(modifier = Modifier.height(8.dp))
                    Text(
                        text = "Tap a device to pair:",
                        style = MaterialTheme.typography.labelMedium,
                        color = MaterialTheme.colorScheme.onSurface.copy(alpha = 0.7f)
                    )
                    Spacer(modifier = Modifier.height(4.dp))
                    Column {
                        scannedDevices.forEachIndexed { index, device ->
                            if (index > 0) HorizontalDivider(color = MaterialTheme.colorScheme.outline.copy(alpha = 0.3f))
                            DeviceRow(
                                device = device,
                                onClick = {
                                    viewModel.saveDeviceMac(device.address)
                                    stopScan()
                                    scannedDevices = emptyList()
                                }
                            )
                        }
                    }
                } else if (isScanning) {
                    Spacer(modifier = Modifier.height(8.dp))
                    Text(
                        text = "Scanning for O2M devices…",
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onSurface.copy(alpha = 0.6f)
                    )
                }
            }

            // ---- Patient Selection ----
            SectionCard(title = "Patient Selection") {
                val patientName = viewModel.currentPatientName
                Text(
                    text = "Current Patient: ${patientName ?: "None"}",
                    style = MaterialTheme.typography.bodyMedium,
                    color = MaterialTheme.colorScheme.onSurface
                )
                Spacer(modifier = Modifier.height(12.dp))

                if (viewModel.patientLoadError != null) {
                    Text(
                        text = viewModel.patientLoadError!!,
                        color = MaterialTheme.colorScheme.error,
                        style = MaterialTheme.typography.bodySmall
                    )
                    Spacer(modifier = Modifier.height(8.dp))
                }

                Button(
                    onClick = {
                        if (viewModel.patients.isNotEmpty()) {
                            viewModel.clearPatientList()
                        } else {
                            viewModel.loadPatients()
                        }
                    },
                    modifier = Modifier.fillMaxWidth(),
                    enabled = !viewModel.isLoadingPatients
                ) {
                    if (viewModel.isLoadingPatients) {
                        CircularProgressIndicator(
                            modifier = Modifier.size(16.dp),
                            color = MaterialTheme.colorScheme.onPrimary,
                            strokeWidth = 2.dp
                        )
                    } else {
                        Text(
                            text = if (viewModel.patients.isNotEmpty()) "Cancel" else "Change Patient"
                        )
                    }
                }

                if (viewModel.patients.isNotEmpty()) {
                    Spacer(modifier = Modifier.height(8.dp))
                    Text(
                        text = "Tap to select:",
                        style = MaterialTheme.typography.labelMedium,
                        color = MaterialTheme.colorScheme.onSurface.copy(alpha = 0.7f)
                    )
                    Spacer(modifier = Modifier.height(4.dp))
                    Column {
                        viewModel.patients.forEachIndexed { index, patient ->
                            if (index > 0) HorizontalDivider(color = MaterialTheme.colorScheme.outline.copy(alpha = 0.3f))
                            PatientRow(
                                patient = patient,
                                onClick = { viewModel.selectPatient(patient) }
                            )
                        }
                    }
                }
            }

            // ---- Monitoring Control ----
            SectionCard(title = "Monitoring") {
                val context = androidx.compose.ui.platform.LocalContext.current
                var isMonitoring by remember { mutableStateOf(true) }

                // Listen for state broadcasts to track service status
                DisposableEffect(Unit) {
                    val receiver = object : android.content.BroadcastReceiver() {
                        override fun onReceive(ctx: android.content.Context, intent: android.content.Intent) {
                            val nextState = intent.getStringExtra(com.o2monitor.app.ble.BleService.EXTRA_STATE)
                                ?.let { runCatching { com.o2monitor.app.ble.BleState.valueOf(it) }.getOrNull() }
                                ?: return
                            isMonitoring = nextState != com.o2monitor.app.ble.BleState.IDLE
                        }
                    }
                    val filter = android.content.IntentFilter(com.o2monitor.app.ble.BleService.ACTION_STATE)
                    androidx.localbroadcastmanager.content.LocalBroadcastManager.getInstance(context)
                        .registerReceiver(receiver, filter)
                    onDispose {
                        androidx.localbroadcastmanager.content.LocalBroadcastManager.getInstance(context)
                            .unregisterReceiver(receiver)
                    }
                }

                if (isMonitoring) {
                    Button(
                        onClick = {
                            val stopIntent = android.content.Intent(context, com.o2monitor.app.ble.BleService::class.java).apply {
                                action = com.o2monitor.app.ble.BleService.ACTION_STOP
                            }
                            context.startService(stopIntent)
                            isMonitoring = false
                        },
                        modifier = Modifier.fillMaxWidth(),
                        colors = ButtonDefaults.buttonColors(
                            containerColor = MaterialTheme.colorScheme.error
                        )
                    ) {
                        Text("Stop Monitoring")
                    }
                } else {
                    Button(
                        onClick = {
                            val startIntent = android.content.Intent(context, com.o2monitor.app.ble.BleService::class.java)
                            context.startForegroundService(startIntent)
                            isMonitoring = true
                        },
                        modifier = Modifier.fillMaxWidth(),
                        colors = ButtonDefaults.buttonColors(
                            containerColor = MaterialTheme.colorScheme.primary
                        )
                    ) {
                        Text("Start Monitoring")
                    }
                }
            }

            Spacer(modifier = Modifier.height(16.dp))

            // ---- App Info ----
            SectionCard(title = "App Info") {
                Text(
                    text = "Version ${BuildConfig.VERSION_NAME} (${BuildConfig.VERSION_CODE})",
                    style = MaterialTheme.typography.bodyMedium,
                    color = MaterialTheme.colorScheme.onSurface
                )
                Spacer(modifier = Modifier.height(16.dp))
                Button(
                    onClick = { viewModel.clearAllSettings(onBack) },
                    modifier = Modifier.fillMaxWidth(),
                    colors = ButtonDefaults.buttonColors(
                        containerColor = MaterialTheme.colorScheme.error
                    )
                ) {
                    Text("Clear All Settings")
                }
            }

            Spacer(modifier = Modifier.height(16.dp))
        }
    }
}

@Composable
private fun SectionCard(title: String, content: @Composable () -> Unit) {
    Card(
        modifier = Modifier.fillMaxWidth(),
        colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surface)
    ) {
        Column(modifier = Modifier.padding(16.dp)) {
            Text(
                text = title,
                style = MaterialTheme.typography.titleSmall,
                color = MaterialTheme.colorScheme.primary
            )
            Spacer(modifier = Modifier.height(12.dp))
            content()
        }
    }
}

@Composable
private fun DeviceRow(device: ScannedDevice, onClick: () -> Unit) {
    Row(
        modifier = Modifier
            .fillMaxWidth()
            .clickable(onClick = onClick)
            .padding(vertical = 12.dp, horizontal = 4.dp),
        horizontalArrangement = Arrangement.SpaceBetween,
        verticalAlignment = Alignment.CenterVertically
    ) {
        Column(modifier = Modifier.weight(1f)) {
            Text(
                text = device.name,
                style = MaterialTheme.typography.bodyMedium,
                color = MaterialTheme.colorScheme.onSurface
            )
            Text(
                text = device.address,
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurface.copy(alpha = 0.6f)
            )
            if (device.isCurrent) {
                Text(
                    text = "Current device",
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.primary
                )
            }
        }
        Text(
            text = device.rssi?.let { "$it dBm" } ?: "Saved",
            style = MaterialTheme.typography.bodySmall,
            color = MaterialTheme.colorScheme.onSurface.copy(alpha = 0.6f)
        )
    }
}

@Composable
private fun PatientRow(patient: PatientSummary, onClick: () -> Unit) {
    Column(
        modifier = Modifier
            .fillMaxWidth()
            .clickable(onClick = onClick)
            .padding(vertical = 12.dp, horizontal = 4.dp)
    ) {
        Text(
            text = patient.name,
            style = MaterialTheme.typography.bodyMedium,
            color = MaterialTheme.colorScheme.onSurface
        )
        Text(
            text = patient.deviceMac,
            style = MaterialTheme.typography.bodySmall,
            color = MaterialTheme.colorScheme.onSurface.copy(alpha = 0.6f)
        )
    }
}
