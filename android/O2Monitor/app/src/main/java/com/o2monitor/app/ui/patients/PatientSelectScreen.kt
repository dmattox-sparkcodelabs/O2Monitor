package com.o2monitor.app.ui.patients

import android.content.SharedPreferences
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import androidx.hilt.navigation.compose.hiltViewModel
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.o2monitor.app.network.ApiClient
import com.o2monitor.app.network.PatientSummary
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.launch
import javax.inject.Inject

@HiltViewModel
class PatientSelectViewModel @Inject constructor(
    private val prefs: SharedPreferences,
    private val httpClient: okhttp3.OkHttpClient
) : ViewModel() {

    private val serverUrl get() = prefs.getString("server_url", "") ?: ""
    private val apiKey get() = prefs.getString("api_key", "") ?: ""

    var patients by mutableStateOf<List<PatientSummary>>(emptyList())
        private set
    var isLoading by mutableStateOf(false)
        private set
    var errorMessage by mutableStateOf<String?>(null)
        private set

    fun loadPatients() {
        viewModelScope.launch {
            isLoading = true
            errorMessage = null
            val client = ApiClient(httpClient, serverUrl, apiKey)
            val result = client.getPatients()
            isLoading = false
            if (result.isSuccess) {
                patients = result.getOrDefault(emptyList())
            } else {
                errorMessage = result.exceptionOrNull()?.message ?: "Failed to load patients"
            }
        }
    }

    fun selectPatient(patient: PatientSummary) {
        prefs.edit()
            .putString("patient_id", patient.id)
            .putString("patient_name", patient.name)
            .apply()
    }
}

@Composable
fun PatientSelectScreen(
    onPatientSelected: () -> Unit,
    viewModel: PatientSelectViewModel = hiltViewModel()
) {
    LaunchedEffect(Unit) { viewModel.loadPatients() }

    Surface(
        modifier = Modifier.fillMaxSize(),
        color = MaterialTheme.colorScheme.background
    ) {
        Column(modifier = Modifier.fillMaxSize()) {
            Text(
                text = "Select Patient",
                style = MaterialTheme.typography.headlineMedium,
                color = MaterialTheme.colorScheme.onBackground,
                modifier = Modifier.padding(24.dp)
            )

            when {
                viewModel.isLoading -> {
                    Box(modifier = Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
                        CircularProgressIndicator()
                    }
                }
                viewModel.errorMessage != null -> {
                    Box(modifier = Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
                        Text(
                            text = viewModel.errorMessage ?: "Unknown error",
                            color = MaterialTheme.colorScheme.error,
                            modifier = Modifier.padding(24.dp)
                        )
                    }
                }
                viewModel.patients.isEmpty() -> {
                    Box(modifier = Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
                        Text(
                            text = "No patients found.\nCreate one via the web dashboard.",
                            color = MaterialTheme.colorScheme.onBackground,
                            modifier = Modifier.padding(24.dp)
                        )
                    }
                }
                else -> {
                    LazyColumn {
                        items(viewModel.patients) { patient ->
                            PatientRow(
                                patient = patient,
                                onClick = {
                                    viewModel.selectPatient(patient)
                                    onPatientSelected()
                                }
                            )
                            HorizontalDivider()
                        }
                    }
                }
            }
        }
    }
}

@Composable
private fun PatientRow(patient: PatientSummary, onClick: () -> Unit) {
    Card(
        modifier = Modifier
            .fillMaxWidth()
            .clickable(onClick = onClick)
            .padding(horizontal = 16.dp, vertical = 4.dp),
        colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surface)
    ) {
        Column(modifier = Modifier.padding(16.dp)) {
            Text(
                text = patient.name,
                style = MaterialTheme.typography.titleMedium,
                color = MaterialTheme.colorScheme.onSurface
            )
            Text(
                text = patient.deviceMac,
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurface.copy(alpha = 0.6f)
            )
        }
    }
}
