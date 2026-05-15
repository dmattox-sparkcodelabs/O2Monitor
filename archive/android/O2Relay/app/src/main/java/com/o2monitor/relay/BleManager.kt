package com.o2monitor.relay

import android.annotation.SuppressLint
import android.bluetooth.*
import android.bluetooth.le.*
import android.content.Context
import android.os.Build
import android.os.Handler
import android.os.Looper
import android.util.Log
import java.util.UUID

/**
 * Manages BLE connection to the Checkme O2 Max oximeter.
 *
 * Handles scanning, connection, GATT operations, and data parsing.
 * Uses OximeterProtocol for packet parsing and CRC verification.
 */
class BleManager(private val context: Context) {

    companion object {
        private const val TAG = "BleManager"

        // Default target device (can be overridden via constructor or settings)
        const val DEFAULT_TARGET_MAC = "C8:F1:6B:56:7B:F1"
        const val DEVICE_NAME_PREFIX = "O2M"

        // BLE UUIDs from OximeterProtocol
        val SERVICE_UUID: UUID = UUID.fromString(OximeterProtocol.SERVICE_UUID)
        val TX_CHAR_UUID: UUID = UUID.fromString(OximeterProtocol.TX_CHAR_UUID)
        val RX_CHAR_UUID: UUID = UUID.fromString(OximeterProtocol.RX_CHAR_UUID)

        // Client Characteristic Configuration Descriptor UUID (standard)
        val CCCD_UUID: UUID = UUID.fromString("00002902-0000-1000-8000-00805f9b34fb")

        // Timeouts
        const val DEFAULT_SCAN_TIMEOUT_MS = 30_000L
        const val CONNECTION_TIMEOUT_MS = 10_000L
        const val GATT_OPERATION_TIMEOUT_MS = 5_000L
    }

    /**
     * Callback interface for BLE events.
     */
    interface Callback {
        fun onConnected()
        fun onDisconnected()
        fun onReading(reading: OxiReading)
        fun onError(message: String)
        fun onScanResult(device: BluetoothDevice)
        fun onScanFailed(errorCode: Int)
    }

    // State
    enum class State {
        IDLE,
        SCANNING,
        CONNECTING,
        DISCOVERING_SERVICES,
        ENABLING_NOTIFICATIONS,
        CONNECTED,
        DISCONNECTING
    }

    var state: State = State.IDLE
        private set

    var targetMac: String = DEFAULT_TARGET_MAC
    var callback: Callback? = null

    private val handler = Handler(Looper.getMainLooper())
    private val bluetoothAdapter: BluetoothAdapter? by lazy {
        val manager = context.getSystemService(Context.BLUETOOTH_SERVICE) as BluetoothManager
        manager.adapter
    }

    private var bluetoothLeScanner: BluetoothLeScanner? = null
    private var bluetoothGatt: BluetoothGatt? = null
    private var txCharacteristic: BluetoothGattCharacteristic? = null
    private var rxCharacteristic: BluetoothGattCharacteristic? = null

    // Buffer for incoming BLE data (packets may be fragmented)
    private var receiveBuffer = ByteArray(0)

    // Timeout runnables
    private var scanTimeoutRunnable: Runnable? = null
    private var connectionTimeoutRunnable: Runnable? = null

    /**
     * Check if Bluetooth is available and enabled.
     */
    fun isBluetoothEnabled(): Boolean {
        return bluetoothAdapter?.isEnabled == true
    }

    /**
     * Start scanning for the oximeter device.
     *
     * @param timeout Scan timeout in milliseconds (default 30 seconds)
     */
    @SuppressLint("MissingPermission")
    fun startScan(timeout: Long = DEFAULT_SCAN_TIMEOUT_MS) {
        if (state != State.IDLE) {
            Log.w(TAG, "Cannot start scan in state: $state")
            callback?.onError("Cannot start scan: already $state")
            return
        }

        val adapter = bluetoothAdapter
        if (adapter == null || !adapter.isEnabled) {
            Log.e(TAG, "Bluetooth not available or not enabled")
            callback?.onError("Bluetooth not available or not enabled")
            return
        }

        bluetoothLeScanner = adapter.bluetoothLeScanner
        if (bluetoothLeScanner == null) {
            Log.e(TAG, "BLE scanner not available")
            callback?.onError("BLE scanner not available")
            return
        }

        state = State.SCANNING
        receiveBuffer = ByteArray(0)

        // Build scan filters - try to filter by MAC address if possible
        val filters = mutableListOf<ScanFilter>()

        // Filter by MAC address (primary method)
        if (targetMac.isNotEmpty()) {
            try {
                filters.add(
                    ScanFilter.Builder()
                        .setDeviceAddress(targetMac)
                        .build()
                )
                Log.d(TAG, "Scanning for device MAC: $targetMac")
            } catch (e: IllegalArgumentException) {
                Log.w(TAG, "Invalid MAC address format: $targetMac, scanning by name prefix")
            }
        }

        // Scan settings - balanced mode for reasonable battery/latency tradeoff
        val settings = ScanSettings.Builder()
            .setScanMode(ScanSettings.SCAN_MODE_BALANCED)
            .setReportDelay(0) // Report results immediately
            .build()

        // Set scan timeout
        scanTimeoutRunnable = Runnable {
            Log.w(TAG, "Scan timeout after ${timeout}ms")
            stopScan()
            callback?.onError("Scan timeout - device not found")
        }
        handler.postDelayed(scanTimeoutRunnable!!, timeout)

        try {
            if (filters.isNotEmpty()) {
                bluetoothLeScanner?.startScan(filters, settings, scanCallback)
            } else {
                // No filter - scan all devices and filter in callback
                bluetoothLeScanner?.startScan(null, settings, scanCallback)
            }
            Log.i(TAG, "BLE scan started")
        } catch (e: Exception) {
            Log.e(TAG, "Failed to start scan", e)
            state = State.IDLE
            cancelScanTimeout()
            callback?.onError("Failed to start scan: ${e.message}")
        }
    }

    /**
     * Stop scanning.
     */
    @SuppressLint("MissingPermission")
    fun stopScan() {
        if (state != State.SCANNING) {
            return
        }

        cancelScanTimeout()

        try {
            bluetoothLeScanner?.stopScan(scanCallback)
            Log.i(TAG, "BLE scan stopped")
        } catch (e: Exception) {
            Log.w(TAG, "Error stopping scan", e)
        }

        state = State.IDLE
    }

    /**
     * Connect to a BLE device.
     */
    @SuppressLint("MissingPermission")
    fun connect(device: BluetoothDevice) {
        if (state != State.IDLE && state != State.SCANNING) {
            Log.w(TAG, "Cannot connect in state: $state")
            callback?.onError("Cannot connect: already $state")
            return
        }

        // Stop scanning if active
        if (state == State.SCANNING) {
            stopScan()
        }

        state = State.CONNECTING
        receiveBuffer = ByteArray(0)

        Log.i(TAG, "Connecting to device: ${device.address}")

        // Set connection timeout
        connectionTimeoutRunnable = Runnable {
            Log.w(TAG, "Connection timeout")
            disconnect()
            callback?.onError("Connection timeout")
        }
        handler.postDelayed(connectionTimeoutRunnable!!, CONNECTION_TIMEOUT_MS)

        try {
            // Use TRANSPORT_LE for BLE devices
            // autoConnect=false for faster initial connection
            bluetoothGatt = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.M) {
                device.connectGatt(context, false, gattCallback, BluetoothDevice.TRANSPORT_LE)
            } else {
                device.connectGatt(context, false, gattCallback)
            }
        } catch (e: Exception) {
            Log.e(TAG, "Failed to connect", e)
            state = State.IDLE
            cancelConnectionTimeout()
            callback?.onError("Failed to connect: ${e.message}")
        }
    }

    /**
     * Connect to the target device by MAC address.
     */
    @SuppressLint("MissingPermission")
    fun connectToTarget() {
        val adapter = bluetoothAdapter
        if (adapter == null || !adapter.isEnabled) {
            callback?.onError("Bluetooth not available")
            return
        }

        try {
            val device = adapter.getRemoteDevice(targetMac)
            connect(device)
        } catch (e: IllegalArgumentException) {
            callback?.onError("Invalid MAC address: $targetMac")
        }
    }

    /**
     * Disconnect from the device.
     */
    @SuppressLint("MissingPermission")
    fun disconnect() {
        cancelConnectionTimeout()

        val gatt = bluetoothGatt
        if (gatt == null) {
            state = State.IDLE
            return
        }

        state = State.DISCONNECTING
        Log.i(TAG, "Disconnecting")

        try {
            gatt.disconnect()
        } catch (e: Exception) {
            Log.w(TAG, "Error disconnecting", e)
        }

        // Close will be called in onConnectionStateChange callback
        // But also schedule a fallback cleanup
        handler.postDelayed({
            if (state == State.DISCONNECTING) {
                cleanup()
            }
        }, 2000)
    }

    /**
     * Request a reading from the oximeter (send 0x17 command).
     */
    @SuppressLint("MissingPermission")
    fun requestReading() {
        if (state != State.CONNECTED) {
            Log.w(TAG, "Cannot request reading in state: $state")
            return
        }

        val gatt = bluetoothGatt
        val txChar = txCharacteristic

        if (gatt == null || txChar == null) {
            Log.e(TAG, "GATT or TX characteristic not available")
            callback?.onError("Not connected properly")
            return
        }

        val command = OximeterProtocol.buildReadingCommand()
        Log.d(TAG, "Sending reading command: ${command.toHexString()}")

        try {
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
                val result = gatt.writeCharacteristic(
                    txChar,
                    command,
                    BluetoothGattCharacteristic.WRITE_TYPE_DEFAULT
                )
                if (result != BluetoothGatt.GATT_SUCCESS) {
                    Log.e(TAG, "Failed to write characteristic: $result")
                }
            } else {
                @Suppress("DEPRECATION")
                txChar.value = command
                @Suppress("DEPRECATION")
                val success = gatt.writeCharacteristic(txChar)
                if (!success) {
                    Log.e(TAG, "Failed to write characteristic")
                }
            }
        } catch (e: Exception) {
            Log.e(TAG, "Error sending command", e)
            callback?.onError("Failed to send command: ${e.message}")
        }
    }

    /**
     * Clean up all resources.
     */
    @SuppressLint("MissingPermission")
    fun cleanup() {
        cancelScanTimeout()
        cancelConnectionTimeout()

        try {
            bluetoothLeScanner?.stopScan(scanCallback)
        } catch (e: Exception) {
            // Ignore
        }

        try {
            bluetoothGatt?.close()
        } catch (e: Exception) {
            // Ignore
        }

        bluetoothGatt = null
        txCharacteristic = null
        rxCharacteristic = null
        receiveBuffer = ByteArray(0)
        state = State.IDLE

        Log.i(TAG, "BLE resources cleaned up")
    }

    // ==================== Private Methods ====================

    private fun cancelScanTimeout() {
        scanTimeoutRunnable?.let { handler.removeCallbacks(it) }
        scanTimeoutRunnable = null
    }

    private fun cancelConnectionTimeout() {
        connectionTimeoutRunnable?.let { handler.removeCallbacks(it) }
        connectionTimeoutRunnable = null
    }

    /**
     * Process received data - buffer and parse complete packets.
     */
    private fun processReceivedData(data: ByteArray) {
        // Append to buffer
        receiveBuffer += data
        Log.d(TAG, "Received ${data.size} bytes, buffer size: ${receiveBuffer.size}")

        // Try to find and parse complete packets
        while (true) {
            val result = OximeterProtocol.findPacket(receiveBuffer)
            if (result == null) {
                // No complete packet found
                break
            }

            val (packet, remaining) = result
            receiveBuffer = remaining

            Log.d(TAG, "Found packet: ${packet.toHexString()}")

            // Parse the packet
            when (val parseResult = OximeterProtocol.parsePacket(packet)) {
                is ParseResult.Success -> {
                    Log.i(TAG, "Reading: SpO2=${parseResult.reading.spo2}, HR=${parseResult.reading.heartRate}")
                    callback?.onReading(parseResult.reading)
                }
                is ParseResult.Error -> {
                    Log.w(TAG, "Parse error: ${parseResult.message}")
                    // Don't report as error to callback - just log it
                }
                is ParseResult.Incomplete -> {
                    // Shouldn't happen since findPacket ensures complete packets
                    Log.w(TAG, "Unexpected incomplete packet")
                }
            }
        }

        // Prevent buffer from growing too large (discard old data)
        if (receiveBuffer.size > 1024) {
            Log.w(TAG, "Receive buffer too large, discarding old data")
            receiveBuffer = receiveBuffer.takeLast(256).toByteArray()
        }
    }

    // ==================== Scan Callback ====================

    private val scanCallback = object : ScanCallback() {
        @SuppressLint("MissingPermission")
        override fun onScanResult(callbackType: Int, result: ScanResult) {
            val device = result.device
            val deviceName = device.name ?: ""
            val deviceAddress = device.address

            Log.d(TAG, "Scan result: $deviceName ($deviceAddress) RSSI: ${result.rssi}")

            // Check if this is our target device
            val isTarget = deviceAddress.equals(targetMac, ignoreCase = true) ||
                    (targetMac.isEmpty() && deviceName.startsWith(DEVICE_NAME_PREFIX))

            if (isTarget) {
                Log.i(TAG, "Found target device: $deviceName ($deviceAddress)")
                stopScan()
                callback?.onScanResult(device)

                // Auto-connect to the device
                connect(device)
            }
        }

        override fun onScanFailed(errorCode: Int) {
            Log.e(TAG, "Scan failed with error code: $errorCode")
            state = State.IDLE
            cancelScanTimeout()
            callback?.onScanFailed(errorCode)
        }

        override fun onBatchScanResults(results: MutableList<ScanResult>) {
            for (result in results) {
                onScanResult(ScanSettings.CALLBACK_TYPE_ALL_MATCHES, result)
            }
        }
    }

    // ==================== GATT Callback ====================

    private val gattCallback = object : BluetoothGattCallback() {
        @SuppressLint("MissingPermission")
        override fun onConnectionStateChange(gatt: BluetoothGatt, status: Int, newState: Int) {
            Log.d(TAG, "Connection state changed: status=$status, newState=$newState")

            when (newState) {
                BluetoothProfile.STATE_CONNECTED -> {
                    cancelConnectionTimeout()

                    if (status == BluetoothGatt.GATT_SUCCESS) {
                        Log.i(TAG, "Connected to GATT server")
                        state = State.DISCOVERING_SERVICES

                        // Discover services
                        handler.post {
                            try {
                                gatt.discoverServices()
                            } catch (e: Exception) {
                                Log.e(TAG, "Failed to discover services", e)
                                disconnect()
                                callback?.onError("Failed to discover services")
                            }
                        }
                    } else {
                        Log.e(TAG, "Connection failed with status: $status")
                        cleanup()
                        callback?.onError("Connection failed: status $status")
                    }
                }

                BluetoothProfile.STATE_DISCONNECTED -> {
                    Log.i(TAG, "Disconnected from GATT server")
                    val wasConnected = state == State.CONNECTED
                    cleanup()

                    if (wasConnected) {
                        callback?.onDisconnected()
                    } else if (status != BluetoothGatt.GATT_SUCCESS) {
                        // Connection attempt failed (e.g., GATT error 133)
                        callback?.onError("Disconnected: status $status")
                    }
                }
            }
        }

        @SuppressLint("MissingPermission")
        override fun onServicesDiscovered(gatt: BluetoothGatt, status: Int) {
            if (status != BluetoothGatt.GATT_SUCCESS) {
                Log.e(TAG, "Service discovery failed: $status")
                disconnect()
                callback?.onError("Service discovery failed")
                return
            }

            Log.i(TAG, "Services discovered")

            // Find our service
            val service = gatt.getService(SERVICE_UUID)
            if (service == null) {
                Log.e(TAG, "Oximeter service not found")
                disconnect()
                callback?.onError("Oximeter service not found")
                return
            }

            // Find TX characteristic (for sending commands)
            txCharacteristic = service.getCharacteristic(TX_CHAR_UUID)
            if (txCharacteristic == null) {
                Log.e(TAG, "TX characteristic not found")
                disconnect()
                callback?.onError("TX characteristic not found")
                return
            }

            // Find RX characteristic (for receiving notifications)
            rxCharacteristic = service.getCharacteristic(RX_CHAR_UUID)
            if (rxCharacteristic == null) {
                Log.e(TAG, "RX characteristic not found")
                disconnect()
                callback?.onError("RX characteristic not found")
                return
            }

            Log.d(TAG, "Found TX and RX characteristics")
            state = State.ENABLING_NOTIFICATIONS

            // Enable notifications on RX characteristic
            handler.post {
                enableNotifications(gatt)
            }
        }

        @SuppressLint("MissingPermission")
        private fun enableNotifications(gatt: BluetoothGatt) {
            val rxChar = rxCharacteristic ?: return

            // Enable local notifications
            val notifySet = gatt.setCharacteristicNotification(rxChar, true)
            if (!notifySet) {
                Log.e(TAG, "Failed to set characteristic notification")
                disconnect()
                callback?.onError("Failed to enable notifications")
                return
            }

            // Write to CCCD to enable remote notifications
            val descriptor = rxChar.getDescriptor(CCCD_UUID)
            if (descriptor == null) {
                Log.w(TAG, "CCCD descriptor not found, notifications may not work")
                // Continue anyway - some devices work without explicit CCCD write
                onNotificationsEnabled()
                return
            }

            try {
                if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
                    val result = gatt.writeDescriptor(
                        descriptor,
                        BluetoothGattDescriptor.ENABLE_NOTIFICATION_VALUE
                    )
                    if (result != BluetoothGatt.GATT_SUCCESS) {
                        Log.e(TAG, "Failed to write CCCD: $result")
                    }
                } else {
                    @Suppress("DEPRECATION")
                    descriptor.value = BluetoothGattDescriptor.ENABLE_NOTIFICATION_VALUE
                    @Suppress("DEPRECATION")
                    val success = gatt.writeDescriptor(descriptor)
                    if (!success) {
                        Log.e(TAG, "Failed to write CCCD")
                    }
                }
            } catch (e: Exception) {
                Log.e(TAG, "Error enabling notifications", e)
                disconnect()
                callback?.onError("Failed to enable notifications: ${e.message}")
            }
        }

        override fun onDescriptorWrite(
            gatt: BluetoothGatt,
            descriptor: BluetoothGattDescriptor,
            status: Int
        ) {
            if (descriptor.uuid == CCCD_UUID) {
                if (status == BluetoothGatt.GATT_SUCCESS) {
                    Log.i(TAG, "Notifications enabled")
                    onNotificationsEnabled()
                } else {
                    Log.e(TAG, "Failed to enable notifications: $status")
                    disconnect()
                    callback?.onError("Failed to enable notifications")
                }
            }
        }

        private fun onNotificationsEnabled() {
            state = State.CONNECTED
            Log.i(TAG, "BLE connection fully established")
            handler.post {
                callback?.onConnected()
            }
        }

        @Deprecated("Deprecated in API 33")
        override fun onCharacteristicChanged(
            gatt: BluetoothGatt,
            characteristic: BluetoothGattCharacteristic
        ) {
            if (characteristic.uuid == RX_CHAR_UUID) {
                @Suppress("DEPRECATION")
                val data = characteristic.value
                if (data != null) {
                    processReceivedData(data)
                }
            }
        }

        override fun onCharacteristicChanged(
            gatt: BluetoothGatt,
            characteristic: BluetoothGattCharacteristic,
            value: ByteArray
        ) {
            if (characteristic.uuid == RX_CHAR_UUID) {
                processReceivedData(value)
            }
        }

        override fun onCharacteristicWrite(
            gatt: BluetoothGatt,
            characteristic: BluetoothGattCharacteristic,
            status: Int
        ) {
            if (characteristic.uuid == TX_CHAR_UUID) {
                if (status == BluetoothGatt.GATT_SUCCESS) {
                    Log.d(TAG, "Command written successfully")
                } else {
                    Log.e(TAG, "Command write failed: $status")
                }
            }
        }
    }

    // ==================== Utility Extensions ====================

    private fun ByteArray.toHexString(): String =
        joinToString(" ") { String.format("%02X", it) }
}
