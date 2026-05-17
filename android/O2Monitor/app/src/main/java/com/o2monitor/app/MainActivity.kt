package com.o2monitor.app

import android.Manifest
import android.content.SharedPreferences
import android.os.Build
import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.compose.setContent
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.navigation.compose.NavHost
import androidx.navigation.compose.composable
import androidx.navigation.compose.rememberNavController
import com.o2monitor.app.ui.dashboard.DashboardScreen
import com.o2monitor.app.ui.patients.PatientSelectScreen
import com.o2monitor.app.ui.settings.SettingsScreen
import com.o2monitor.app.ui.setup.SetupScreen
import com.o2monitor.app.ui.theme.O2MonitorTheme
import dagger.hilt.android.AndroidEntryPoint
import javax.inject.Inject

private val BLE_PERMISSIONS = arrayOf(
    Manifest.permission.BLUETOOTH_SCAN,
    Manifest.permission.BLUETOOTH_CONNECT,
    Manifest.permission.ACCESS_FINE_LOCATION
)

private val APP_PERMISSIONS: Array<String>
    get() = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
        BLE_PERMISSIONS + Manifest.permission.POST_NOTIFICATIONS
    } else {
        BLE_PERMISSIONS
    }

@AndroidEntryPoint
class MainActivity : ComponentActivity() {

    @Inject
    lateinit var prefs: SharedPreferences

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContent {
            O2MonitorTheme {
                val navController = rememberNavController()
                val startDestination = resolveStartDestination()

                var blePermissionsGranted by remember { mutableStateOf(false) }

                val permissionLauncher = rememberLauncherForActivityResult(
                    contract = ActivityResultContracts.RequestMultiplePermissions()
                ) { results ->
                    blePermissionsGranted = BLE_PERMISSIONS.all { results[it] == true }
                }

                LaunchedEffect(Unit) {
                    permissionLauncher.launch(APP_PERMISSIONS)
                }

                NavHost(navController = navController, startDestination = startDestination) {
                    composable("setup") {
                        SetupScreen(
                            onSetupComplete = {
                                navController.navigate("patients") {
                                    popUpTo("setup") { inclusive = true }
                                }
                            }
                        )
                    }
                    composable("patients") {
                        PatientSelectScreen(
                            onPatientSelected = {
                                navController.navigate("dashboard") {
                                    popUpTo("patients") { inclusive = true }
                                }
                            }
                        )
                    }
                    composable("dashboard") {
                        DashboardScreen(
                            permissionsGranted = blePermissionsGranted,
                            onSettingsClick = { navController.navigate("settings") }
                        )
                    }
                    composable("settings") {
                        SettingsScreen(onBack = { navController.popBackStack() })
                    }
                }
            }
        }
    }

    private fun resolveStartDestination(): String {
        val serverUrl = prefs.getString("server_url", null)
        val apiKey = prefs.getString("api_key", null)
        val patientId = prefs.getString("patient_id", null)
        return when {
            serverUrl.isNullOrBlank() || apiKey.isNullOrBlank() -> "setup"
            patientId.isNullOrBlank() -> "patients"
            else -> "dashboard"
        }
    }
}
