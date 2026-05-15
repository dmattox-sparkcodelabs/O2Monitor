# Android O2 Relay App - Design Draft

## Purpose
Android app that runs on dad's phone to relay O2 readings from his Checkme O2 Max oximeter to the Raspberry Pi over WiFi. Solves Bluetooth range limitation - phone stays near dad, Pi can be anywhere on network.

## Architecture
```
[Checkme O2 Max] --BLE--> [Android Phone] --WiFi/HTTP--> [Raspberry Pi]
```

## Key Requirements
1. **Foreground Service** - Must run reliably in background with persistent notification
2. **BLE Connection** - Connect to Checkme O2 Max (MAC: C8:F1:6B:56:7B:F1)
3. **HTTP POST** - Send readings to Pi's API every 5 seconds
4. **Auto-Update** - Check for new APK versions and prompt to install
5. **Sideload** - No Play Store, APK installed manually (initial install requires physical access)

## BLE Protocol
- Device name: "O2M 2781" or similar
- See `src/ble_reader.py` for characteristic UUIDs and data parsing
- Readings include: SpO2 %, Heart Rate, Battery %

## Pi API Endpoint (to be created)
```
POST /api/readings/relay
{
  "spo2": 97,
  "heart_rate": 72,
  "battery": 85,
  "source": "android_relay",
  "device_id": "phone_identifier"
}
```

## Android Specifics
- Min SDK: 26 (Android 8.0) for BLE reliability
- Permissions: BLUETOOTH, BLUETOOTH_ADMIN, BLUETOOTH_CONNECT, BLUETOOTH_SCAN, FOREGROUND_SERVICE, INTERNET
- Language: Kotlin
- Location in repo: `android/`

## Auto-Update Mechanism
- App checks Pi endpoint or GitHub releases for version
- Downloads APK, prompts user to install
- Requires "Install from unknown sources" enabled once

## UI (Minimal)
- Connection status (BLE + WiFi)
- Last reading display
- Start/Stop button
- Pi server URL config
- Version info

## Open Questions
1. What happens when phone loses WiFi? Queue readings?
2. Should Pi fall back to direct BLE if relay fails?
3. Battery optimization - how aggressive to keep alive?

## Files to Reference
- `src/ble_reader.py` - BLE protocol implementation
- `src/web/api.py` - API patterns
- `config.yaml` - Device MAC address
