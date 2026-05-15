package com.o2monitor.relay

import android.Manifest
import android.app.Activity
import android.content.Context
import android.content.pm.PackageManager
import android.os.Build
import androidx.core.app.ActivityCompat
import androidx.core.content.ContextCompat

/**
 * Helper for managing BLE-related permissions.
 *
 * BLE permissions vary by Android version:
 * - Android 12+ (API 31+): BLUETOOTH_SCAN, BLUETOOTH_CONNECT
 * - Android 6-11 (API 23-30): ACCESS_FINE_LOCATION (for BLE scanning)
 * - Android 5 and below: BLUETOOTH, BLUETOOTH_ADMIN (granted at install)
 */
object BlePermissions {

    const val REQUEST_CODE_BLE_PERMISSIONS = 1001

    /**
     * Get the list of permissions required for BLE operations on this device.
     */
    fun getRequiredPermissions(): Array<String> {
        return if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
            // Android 12+ (API 31+)
            arrayOf(
                Manifest.permission.BLUETOOTH_SCAN,
                Manifest.permission.BLUETOOTH_CONNECT
            )
        } else {
            // Android 6-11 (API 23-30)
            // Location permission required for BLE scanning
            arrayOf(
                Manifest.permission.ACCESS_FINE_LOCATION
            )
        }
    }

    /**
     * Check if all required BLE permissions are granted.
     */
    fun hasRequiredPermissions(context: Context): Boolean {
        return getRequiredPermissions().all { permission ->
            ContextCompat.checkSelfPermission(context, permission) == PackageManager.PERMISSION_GRANTED
        }
    }

    /**
     * Check which permissions are missing.
     */
    fun getMissingPermissions(context: Context): List<String> {
        return getRequiredPermissions().filter { permission ->
            ContextCompat.checkSelfPermission(context, permission) != PackageManager.PERMISSION_GRANTED
        }
    }

    /**
     * Request the required BLE permissions.
     */
    fun requestPermissions(activity: Activity) {
        val permissions = getRequiredPermissions()
        ActivityCompat.requestPermissions(activity, permissions, REQUEST_CODE_BLE_PERMISSIONS)
    }

    /**
     * Check if we should show rationale for any of the permissions.
     */
    fun shouldShowRationale(activity: Activity): Boolean {
        return getRequiredPermissions().any { permission ->
            ActivityCompat.shouldShowRequestPermissionRationale(activity, permission)
        }
    }

    /**
     * Process permission request result.
     *
     * @return true if all permissions were granted, false otherwise
     */
    fun onRequestPermissionsResult(
        requestCode: Int,
        permissions: Array<out String>,
        grantResults: IntArray
    ): Boolean {
        if (requestCode != REQUEST_CODE_BLE_PERMISSIONS) {
            return false
        }

        return grantResults.isNotEmpty() && grantResults.all { it == PackageManager.PERMISSION_GRANTED }
    }

    /**
     * Get a user-friendly description of what permissions are needed and why.
     */
    fun getPermissionRationale(): String {
        return if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
            "This app needs Bluetooth permissions to connect to your oximeter device."
        } else {
            "This app needs location permission to scan for Bluetooth devices. " +
                    "This is required by Android for Bluetooth Low Energy scanning. " +
                    "The app does not track or store your location."
        }
    }

    /**
     * Get a description of which specific permissions are missing.
     */
    fun getMissingPermissionsDescription(context: Context): String {
        val missing = getMissingPermissions(context)
        if (missing.isEmpty()) {
            return "All permissions granted"
        }

        val descriptions = missing.map { permission ->
            when (permission) {
                Manifest.permission.BLUETOOTH_SCAN -> "Bluetooth Scan"
                Manifest.permission.BLUETOOTH_CONNECT -> "Bluetooth Connect"
                Manifest.permission.ACCESS_FINE_LOCATION -> "Location"
                Manifest.permission.ACCESS_COARSE_LOCATION -> "Coarse Location"
                else -> permission.substringAfterLast('.')
            }
        }

        return "Missing permissions: ${descriptions.joinToString(", ")}"
    }
}
