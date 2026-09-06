package com.cookmarks.app.ui.login

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.imePadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.OutlinedTextFieldDefaults
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.unit.dp
import com.cookmarks.app.api.Api
import com.cookmarks.app.api.LoginRequest
import com.cookmarks.app.ui.components.MonoLabel
import com.cookmarks.app.ui.theme.CmTheme
import kotlinx.coroutines.launch
import retrofit2.HttpException

@Composable
fun LoginScreen() {
    val colors = CmTheme.colors
    var username by remember { mutableStateOf("") }
    var password by remember { mutableStateOf("") }
    var error by remember { mutableStateOf<String?>(null) }
    var busy by remember { mutableStateOf(false) }
    val scope = rememberCoroutineScope()

    fun submit() {
        if (busy || username.isBlank() || password.isBlank()) return
        busy = true
        error = null
        scope.launch {
            try {
                Api.service.login(LoginRequest(username.trim(), password))
                Api.loggedIn.value = true
            } catch (e: HttpException) {
                error = if (e.code() == 401) "Wrong username or password" else "Server error (${e.code()})"
            } catch (e: Exception) {
                error = e.message ?: "Could not reach the server"
            } finally {
                busy = false
            }
        }
    }

    val fieldColours = OutlinedTextFieldDefaults.colors(
        focusedBorderColor = colors.clay,
        unfocusedBorderColor = colors.lineStrong,
        cursorColor = colors.clay,
    )

    Column(
        modifier = Modifier
            .fillMaxSize()
            .background(colors.bg)
            .imePadding()
            .padding(horizontal = 36.dp),
        verticalArrangement = Arrangement.Center,
        horizontalAlignment = Alignment.CenterHorizontally,
    ) {
        MonoLabel("The cookbook archive", colour = colors.faint)
        Text(
            text = "Cookmarks",
            style = MaterialTheme.typography.displayMedium,
            color = colors.ink,
            modifier = Modifier.padding(top = 8.dp, bottom = 40.dp),
        )
        OutlinedTextField(
            value = username,
            onValueChange = { username = it },
            label = { Text("Username") },
            singleLine = true,
            colors = fieldColours,
            modifier = Modifier.fillMaxWidth(),
        )
        OutlinedTextField(
            value = password,
            onValueChange = { password = it },
            label = { Text("Password") },
            singleLine = true,
            visualTransformation = PasswordVisualTransformation(),
            keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Password),
            colors = fieldColours,
            modifier = Modifier
                .fillMaxWidth()
                .padding(top = 12.dp),
        )
        if (error != null) {
            Text(
                text = error!!,
                style = MaterialTheme.typography.bodyMedium,
                color = colors.clayDeep,
                modifier = Modifier.padding(top = 16.dp),
            )
        }
        Button(
            onClick = { submit() },
            enabled = !busy,
            shape = MaterialTheme.shapes.extraSmall,
            colors = ButtonDefaults.buttonColors(containerColor = colors.clay),
            modifier = Modifier
                .fillMaxWidth()
                .padding(top = 24.dp),
        ) {
            Text(if (busy) "Signing in…" else "Sign in", style = MaterialTheme.typography.labelLarge)
        }
    }
}
