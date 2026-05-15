package com.o2monitor.app

import android.content.SharedPreferences
import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.navigation.compose.NavHost
import androidx.navigation.compose.composable
import androidx.navigation.compose.rememberNavController
import com.o2monitor.app.ui.dashboard.DashboardScreen
import com.o2monitor.app.ui.patients.PatientSelectScreen
import com.o2monitor.app.ui.setup.SetupScreen
import com.o2monitor.app.ui.theme.O2MonitorTheme
import dagger.hilt.android.AndroidEntryPoint
import javax.inject.Inject

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
                        DashboardScreen()
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
