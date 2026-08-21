package com.cookmarks.app.ui.components

import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.runtime.Composable
import androidx.compose.runtime.State
import androidx.compose.runtime.produceState
import com.cookmarks.app.ui.theme.CmTheme

@Composable
fun <T> rememberLoad(vararg keys: Any?, block: suspend () -> T): State<Result<T>?> =
    produceState<Result<T>?>(initialValue = null, keys = keys) {
        value = null
        value = runCatching { block() }
    }

@Composable
fun <T> Loaded(state: Result<T>?, content: @Composable (T) -> Unit) {
    when {
        state == null -> CentredState { CircularProgressIndicator(color = CmTheme.colors.clay) }
        state.isFailure -> ErrorState(state.exceptionOrNull()?.message ?: "Unknown error")
        else -> content(state.getOrThrow())
    }
}
