package com.cookmarks.app

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.material3.Surface
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.ui.Modifier
import com.cookmarks.app.api.Api
import com.cookmarks.app.ui.MainShell
import com.cookmarks.app.ui.login.LoginScreen
import com.cookmarks.app.ui.theme.CmTheme
import com.cookmarks.app.ui.theme.CookmarksTheme

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()
        setContent {
            CookmarksTheme {
                Surface(
                    modifier = Modifier.fillMaxSize().background(CmTheme.colors.bg),
                    color = CmTheme.colors.bg,
                ) {
                    Root()
                }
            }
        }
    }
}

@Composable
private fun Root() {
    val loggedIn by Api.loggedIn.collectAsState()
    if (loggedIn) MainShell() else LoginScreen()
}
