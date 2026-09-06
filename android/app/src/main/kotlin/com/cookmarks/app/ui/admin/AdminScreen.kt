package com.cookmarks.app.ui.admin

import android.text.format.DateUtils
import android.util.Log
import androidx.compose.foundation.clickable
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.selection.toggleable
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.Checkbox
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.OutlinedTextFieldDefaults
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.semantics.selected
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.font.FontStyle
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.unit.dp
import com.cookmarks.app.api.Api
import com.cookmarks.app.api.AuthMe
import com.cookmarks.app.api.BookKeywordTaskRequest
import com.cookmarks.app.api.ConfigRead
import com.cookmarks.app.api.ConfigUpdate
import com.cookmarks.app.api.PasswordChange
import com.cookmarks.app.api.PasswordReset
import com.cookmarks.app.api.TaskRun
import com.cookmarks.app.api.TaskRunAck
import com.cookmarks.app.api.UserCreate
import com.cookmarks.app.api.UserRead
import com.cookmarks.app.ui.Feedback
import com.cookmarks.app.ui.components.Loaded
import com.cookmarks.app.ui.components.MonoLabel
import com.cookmarks.app.ui.components.rememberLoad
import com.cookmarks.app.ui.theme.CmTheme
import com.cookmarks.app.ui.theme.ThemeMode
import com.cookmarks.app.ui.theme.ThemePref
import java.time.Instant
import kotlin.coroutines.cancellation.CancellationException
import kotlinx.coroutines.launch
import kotlinx.serialization.json.JsonNull
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import retrofit2.HttpException

private const val MIN_PASSWORD_LENGTH = 8

private enum class AdminSection(val label: String) {
    Account("Account"), Settings("Settings"), Tasks("Tasks"), Users("Users"), Runs("Runs")
}

private fun words(value: String) = value.replace('_', ' ')

private fun whenLabel(iso: String): String = runCatching {
    DateUtils.getRelativeTimeSpanString(Instant.parse(iso).toEpochMilli()).toString()
}.getOrDefault(iso)

private fun detailLine(run: TaskRun): String = run.detail.entries
    .filter { (_, value) -> value !is JsonNull && value is JsonPrimitive }
    .joinToString("  ·  ") { (key, value) -> "${words(key)} ${(value as JsonPrimitive).content}" }

private fun errorMessage(error: Exception): String = when (error) {
    is HttpException -> runCatching {
        val body = error.response()?.errorBody()?.string().orEmpty()
        Api.json.parseToJsonElement(body).jsonObject["detail"]?.jsonPrimitive?.content
    }.getOrNull() ?: "Server error (${error.code()})"
    else -> error.message ?: "Could not reach the server"
}

@Composable
fun AdminScreen(onBack: () -> Unit) {
    val colors = CmTheme.colors
    var refresh by remember { mutableIntStateOf(0) }
    var section by remember { mutableStateOf(AdminSection.Account) }
    val state by rememberLoad(refresh) { Api.service.me() }

    androidx.compose.foundation.lazy.LazyColumn(
        modifier = Modifier.fillMaxSize(),
        contentPadding = PaddingValues(bottom = 40.dp),
    ) {
        item {
            IconButton(onClick = onBack) {
                Icon(Icons.AutoMirrored.Filled.ArrowBack, contentDescription = "Back", tint = colors.muted)
            }
        }
        item {
            Text(
                "Settings",
                style = MaterialTheme.typography.displaySmall,
                color = colors.ink,
                modifier = Modifier.padding(horizontal = 20.dp, vertical = 4.dp),
            )
        }
        item {
            Loaded(state, onRetry = { refresh++ }) { me ->
                val sections = if (me.is_admin) AdminSection.entries else listOf(AdminSection.Account)
                AdminTabs(sections, section) { section = it }
                HorizontalDivider(color = colors.lineStrong)
                when (section) {
                    AdminSection.Account -> AccountSection(me)
                    AdminSection.Settings -> SettingsTab()
                    AdminSection.Tasks -> TasksSection()
                    AdminSection.Users -> UsersTab(me)
                    AdminSection.Runs -> RunsTab()
                }
            }
        }
    }
}

@Composable
private fun AdminTabs(sections: List<AdminSection>, current: AdminSection, onSelect: (AdminSection) -> Unit) {
    val colors = CmTheme.colors
    Row(
        horizontalArrangement = Arrangement.spacedBy(22.dp),
        modifier = Modifier
            .fillMaxWidth()
            .horizontalScroll(rememberScrollState())
            .padding(horizontal = 20.dp, vertical = 16.dp),
    ) {
        sections.forEach { section ->
            val active = section == current
            MonoLabel(
                section.label,
                colour = if (active) colors.clay else colors.faint,
                modifier = Modifier
                    .clickable(role = Role.Tab, onClickLabel = "Open ${section.label}") { onSelect(section) }
                    .semantics { selected = active }
                    .padding(vertical = 8.dp),
            )
        }
    }
}

@Composable
private fun AccountSection(me: AuthMe) {
    val colors = CmTheme.colors
    val mode by ThemePref.mode.collectAsState()
    val scope = rememberCoroutineScope()
    var currentPassword by remember { mutableStateOf("") }
    var newPassword by remember { mutableStateOf("") }
    var busy by remember { mutableStateOf(false) }
    var error by remember { mutableStateOf<String?>(null) }

    fun signOut() {
        scope.launch {
            try {
                Api.service.logout()
            } catch (e: CancellationException) {
                throw e
            } catch (e: Exception) {
                Log.w("Admin", "logout request failed", e)
            }
            Api.cookieJar.clear()
            Api.loggedIn.value = false
        }
    }

    Section("Signed in") {
        Text(me.username, style = MaterialTheme.typography.headlineSmall, color = colors.ink)
        MonoLabel(
            listOf(if (me.is_admin) "Administrator" else "Member", words(me.auth_mode)).joinToString("  ·  "),
            colour = colors.faint,
            modifier = Modifier.padding(top = 4.dp),
        )
        OutlinedButton(
            onClick = { signOut() },
            shape = MaterialTheme.shapes.extraSmall,
            modifier = Modifier.padding(top = 18.dp),
        ) { Text("Sign out") }
    }

    Section("Appearance") {
        Row(horizontalArrangement = Arrangement.spacedBy(24.dp)) {
            ThemeMode.entries.forEach { option ->
                val active = option == mode
                MonoLabel(
                    option.label,
                    colour = if (active) colors.clay else colors.faint,
                    modifier = Modifier
                        .clickable(
                            role = Role.RadioButton,
                            onClickLabel = "Select ${option.label} theme",
                        ) { ThemePref.set(option) }
                        .semantics { selected = active }
                        .padding(vertical = 10.dp),
                )
            }
        }
    }

    if (me.auth_mode == "session") {
        Section("Password") {
            Text(
                "Changing your password signs you out on every device.",
                style = MaterialTheme.typography.bodyMedium.copy(fontStyle = FontStyle.Italic),
                color = colors.muted,
            )
            PasswordField(
                currentPassword,
                { currentPassword = it },
                "Current password",
                Modifier.padding(top = 12.dp),
                showMinimum = false,
            )
            PasswordField(newPassword, { newPassword = it }, "New password", Modifier.padding(top = 12.dp))
            PrimaryButton(
                if (busy) "Changing…" else "Change password",
                !busy && currentPassword.isNotEmpty() && newPassword.length >= MIN_PASSWORD_LENGTH,
                Modifier.padding(top = 12.dp),
            ) {
                busy = true
                error = null
                scope.launch {
                    try {
                        Api.service.changePassword(PasswordChange(currentPassword, newPassword))
                        Api.cookieJar.clear()
                        Api.loggedIn.value = false
                    } catch (e: CancellationException) {
                        throw e
                    } catch (e: Exception) {
                        error = errorMessage(e)
                        busy = false
                    }
                }
            }
            error?.let { InlineError(it) }
        }
    }
}

@Composable
private fun SettingsTab() {
    var refresh by remember { mutableIntStateOf(0) }
    val state by rememberLoad(refresh) { Api.service.config() }
    Loaded(state, onRetry = { refresh++ }) { config ->
        SettingsSection(config) { refresh++ }
    }
}

@Composable
private fun SettingsSection(config: ConfigRead, onSaved: () -> Unit) {
    val colors = CmTheme.colors
    val scope = rememberCoroutineScope()
    var extractionProvider by remember(config) { mutableStateOf(config.ai_provider) }
    var assistantProvider by remember(config) { mutableStateOf(config.assistant_provider) }
    var extractionKey by remember(config) { mutableStateOf("") }
    var assistantKey by remember(config) { mutableStateOf("") }
    var clearExtractionKey by remember(config) { mutableStateOf(false) }
    var clearAssistantKey by remember(config) { mutableStateOf(false) }
    var rateLimit by remember(config) { mutableStateOf(config.extraction_rate_limit_per_minute.toString()) }
    var busy by remember { mutableStateOf(false) }
    var error by remember { mutableStateOf<String?>(null) }

    Section("Recipe extraction") {
        ProviderPicker(config, extractionProvider) { extractionProvider = it }
        KeyEditor(config.api_key_set, extractionKey, clearExtractionKey, {
            extractionKey = it
            clearExtractionKey = false
        }) { clearExtractionKey = !clearExtractionKey }
        NumberField(
            rateLimit,
            { rateLimit = it.filter(Char::isDigit) },
            "Requests per minute",
            Modifier.padding(top = 12.dp),
        )
    }

    Section("Assistant") {
        ProviderPicker(config, assistantProvider) { assistantProvider = it }
        KeyEditor(config.assistant_api_key_set, assistantKey, clearAssistantKey, {
            assistantKey = it
            clearAssistantKey = false
        }) { clearAssistantKey = !clearAssistantKey }
    }

    val parsedRate = rateLimit.toIntOrNull()
    Column(modifier = Modifier.padding(horizontal = 20.dp)) {
        PrimaryButton("Save settings", !busy && parsedRate != null && parsedRate >= 1) {
            busy = true
            error = null
            scope.launch {
                try {
                    Api.service.updateConfig(
                        ConfigUpdate(
                            ai_provider = extractionProvider?.let(::JsonPrimitive) ?: JsonNull,
                            api_key = if (clearExtractionKey) {
                                JsonPrimitive("")
                            } else {
                                extractionKey.takeIf(String::isNotEmpty)?.let(::JsonPrimitive)
                            },
                            assistant_provider = assistantProvider?.let(::JsonPrimitive) ?: JsonNull,
                            assistant_api_key = if (clearAssistantKey) {
                                JsonPrimitive("")
                            } else {
                                assistantKey.takeIf(String::isNotEmpty)?.let(::JsonPrimitive)
                            },
                            extraction_rate_limit_per_minute = parsedRate,
                        )
                    )
                    Feedback.show("Settings saved")
                    onSaved()
                } catch (e: CancellationException) {
                    throw e
                } catch (e: Exception) {
                    error = errorMessage(e)
                    busy = false
                }
            }
        }
        error?.let { InlineError(it) }
        Text(
            "API keys are write-only. Saved keys are never shown here.",
            style = MaterialTheme.typography.bodySmall.copy(fontStyle = FontStyle.Italic),
            color = colors.faint,
            modifier = Modifier.padding(top = 10.dp),
        )
    }
}

@Composable
private fun ProviderPicker(config: ConfigRead, selectedProvider: String?, onSelect: (String?) -> Unit) {
    val colors = CmTheme.colors
    Column(verticalArrangement = Arrangement.spacedBy(2.dp)) {
        (listOf<String?>(null) + config.providers.map { it.name }).forEach { provider ->
            val active = provider == selectedProvider
            val label = provider?.lowercase()?.replaceFirstChar(Char::uppercase) ?: "None"
            Row(
                verticalAlignment = Alignment.CenterVertically,
                modifier = Modifier
                    .fillMaxWidth()
                    .clickable(role = Role.RadioButton, onClickLabel = "Select $label") {
                        onSelect(provider)
                    }
                    .semantics { selected = active }
                    .padding(vertical = 9.dp),
            ) {
                Text(
                    label,
                    style = MaterialTheme.typography.bodyLarge,
                    color = if (active) colors.clay else colors.ink,
                    modifier = Modifier.weight(1f),
                )
                if (active) MonoLabel("Selected", colour = colors.faint)
            }
        }
    }
}

@Composable
private fun KeyEditor(
    keySet: Boolean,
    value: String,
    clearing: Boolean,
    onValueChange: (String) -> Unit,
    onClear: () -> Unit,
) {
    val colors = CmTheme.colors
    PasswordField(
        value,
        onValueChange,
        if (keySet) "Replace API key" else "API key",
        Modifier.padding(top = 8.dp),
        showMinimum = false,
    )
    if (keySet) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            MonoLabel(
                if (clearing) "Key will be cleared" else "A key is saved",
                colour = if (clearing) colors.clayDeep else colors.faint,
                modifier = Modifier.weight(1f),
            )
            TextButton(onClick = onClear) {
                Text(if (clearing) "Keep key" else "Clear key", color = colors.clay)
            }
        }
    }
}

@Composable
private fun TasksSection() {
    val colors = CmTheme.colors
    val scope = rememberCoroutineScope()
    var busy by remember { mutableStateOf<String?>(null) }
    var regenerate by remember { mutableStateOf(false) }
    var error by remember { mutableStateOf<String?>(null) }

    fun queue(name: String, action: suspend () -> TaskRunAck) {
        if (busy != null) return
        busy = name
        error = null
        scope.launch {
            try {
                val ack = action()
                Feedback.show("${words(ack.task).replaceFirstChar(Char::uppercase)} queued (${ack.queued})")
                busy = null
            } catch (e: CancellationException) {
                throw e
            } catch (e: Exception) {
                error = errorMessage(e)
                busy = null
            }
        }
    }

    Section("Book keywords") {
        Text(
            "Generate missing book keywords with the configured AI provider.",
            style = MaterialTheme.typography.bodyMedium,
            color = colors.muted,
        )
        Row(
            verticalAlignment = Alignment.CenterVertically,
            modifier = Modifier
                .fillMaxWidth()
                .toggleable(
                    value = regenerate,
                    role = Role.Checkbox,
                    onValueChange = { regenerate = it },
                )
                .padding(top = 8.dp),
        ) {
            Checkbox(checked = regenerate, onCheckedChange = null)
            Text("Regenerate existing keywords", color = colors.ink)
        }
        ActionButton("book keywords", busy) {
            queue("book keywords") { Api.service.triggerBookKeywords(BookKeywordTaskRequest(regenerate)) }
        }
    }
    Section("Keyword deduplication") {
        Text(
            "Find and merge near-duplicate keywords across the library.",
            style = MaterialTheme.typography.bodyMedium,
            color = colors.muted,
        )
        ActionButton("keyword deduplication", busy) {
            queue("keyword deduplication") { Api.service.triggerKeywordDedup() }
        }
    }
    Section("Calibre sync") {
        Text(
            "Reconcile Cookmarks with the Calibre library.",
            style = MaterialTheme.typography.bodyMedium,
            color = colors.muted,
        )
        ActionButton("Calibre sync", busy) {
            queue("Calibre sync") { Api.service.triggerCalibreSync() }
        }
        error?.let { InlineError(it) }
    }
}

@Composable
private fun ActionButton(name: String, busy: String?, onClick: () -> Unit) {
    OutlinedButton(
        onClick = onClick,
        enabled = busy == null,
        shape = MaterialTheme.shapes.extraSmall,
        modifier = Modifier.padding(top = 12.dp),
    ) { Text(if (busy == name) "Queuing…" else "Run $name") }
}

@Composable
private fun UsersTab(me: AuthMe) {
    var refresh by remember { mutableIntStateOf(0) }
    val state by rememberLoad(refresh) { Api.service.users() }
    Loaded(state, onRetry = { refresh++ }) { users ->
        UsersSection(users, me) { refresh++ }
    }
}

@Composable
private fun UsersSection(users: List<UserRead>, me: AuthMe, onChanged: () -> Unit) {
    val colors = CmTheme.colors
    val scope = rememberCoroutineScope()
    var username by remember { mutableStateOf("") }
    var password by remember { mutableStateOf("") }
    var isAdmin by remember { mutableStateOf(false) }
    var busy by remember { mutableStateOf(false) }
    var error by remember { mutableStateOf<String?>(null) }
    var resetting by remember { mutableStateOf<UserRead?>(null) }
    var deleting by remember { mutableStateOf<UserRead?>(null) }
    var newPassword by remember { mutableStateOf("") }
    val adminCount = users.count(UserRead::is_admin)

    fun runAction(success: String, action: suspend () -> Unit) {
        if (busy) return
        busy = true
        error = null
        scope.launch {
            try {
                action()
                Feedback.show(success)
                onChanged()
            } catch (e: CancellationException) {
                throw e
            } catch (e: Exception) {
                error = errorMessage(e)
                busy = false
            }
        }
    }

    Column {
        if (users.isEmpty()) {
            Text(
                "No accounts yet.",
                style = MaterialTheme.typography.bodyMedium.copy(fontStyle = FontStyle.Italic),
                color = colors.muted,
                modifier = Modifier.padding(horizontal = 20.dp, vertical = 20.dp),
            )
        }
        users.forEachIndexed { index, user ->
            val deleteBlockedReason = when {
                user.id == me.id -> "You cannot delete your own account"
                user.is_admin && adminCount <= 1 -> "The last administrator cannot be deleted"
                else -> null
            }
            Column(modifier = Modifier.padding(horizontal = 20.dp, vertical = 14.dp)) {
                Text(user.username, style = MaterialTheme.typography.titleLarge, color = colors.ink)
                MonoLabel(
                    "${if (user.is_admin) "Administrator" else "Member"}  ·  ${whenLabel(user.created_at)}",
                    colour = colors.faint,
                    modifier = Modifier.padding(top = 2.dp),
                )
                Row(modifier = Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.End) {
                    TextButton(
                        onClick = {
                            error = null
                            resetting = user
                            newPassword = ""
                        },
                        enabled = !busy,
                    ) { Text("Reset password", color = colors.clay) }
                    TextButton(
                        onClick = {
                            error = null
                            deleting = user
                        },
                        enabled = !busy && deleteBlockedReason == null,
                    ) {
                        Text("Delete", color = if (deleteBlockedReason != null) colors.faint else colors.clayDeep)
                    }
                }
                deleteBlockedReason?.let {
                    Text(
                        it,
                        style = MaterialTheme.typography.bodySmall.copy(fontStyle = FontStyle.Italic),
                        color = colors.faint,
                        modifier = Modifier.fillMaxWidth(),
                    )
                }
            }
            if (index < users.lastIndex) {
                HorizontalDivider(color = colors.line, modifier = Modifier.padding(horizontal = 20.dp))
            }
        }
    }

    Section("Add an account") {
        StandardField(username, { username = it }, "Username")
        PasswordField(password, { password = it }, "Password", Modifier.padding(top = 12.dp))
        Row(
            verticalAlignment = Alignment.CenterVertically,
            modifier = Modifier
                .fillMaxWidth()
                .toggleable(
                    value = isAdmin,
                    role = Role.Checkbox,
                    onValueChange = { isAdmin = it },
                )
                .padding(top = 6.dp),
        ) {
            Checkbox(checked = isAdmin, onCheckedChange = null)
            Text("Administrator", color = colors.ink)
        }
        PrimaryButton(
            if (busy) "Working…" else "Create account",
            !busy && username.isNotBlank() && password.length >= MIN_PASSWORD_LENGTH,
        ) {
            val requestedUsername = username.trim()
            val requestedPassword = password
            runAction("Account created") {
                Api.service.createUser(UserCreate(requestedUsername, requestedPassword, isAdmin))
                username = ""
                password = ""
                isAdmin = false
            }
        }
        error?.let { InlineError(it) }
    }

    resetting?.let { user ->
        AlertDialog(
            onDismissRequest = { if (!busy) resetting = null },
            title = { Text("Reset ${user.username}'s password?") },
            text = {
                Column {
                    Text("This signs the account out on every device.")
                    PasswordField(newPassword, { newPassword = it }, "New password", Modifier.padding(top = 12.dp))
                    error?.let { InlineError(it) }
                }
            },
            confirmButton = {
                TextButton(
                    enabled = !busy && newPassword.length >= MIN_PASSWORD_LENGTH,
                    onClick = {
                        val requestedPassword = newPassword
                        runAction("Password reset") {
                            Api.service.resetPassword(user.id, PasswordReset(requestedPassword))
                            resetting = null
                            if (user.id == me.id) {
                                Api.cookieJar.clear()
                                Api.loggedIn.value = false
                            }
                        }
                    },
                ) { Text("Reset password") }
            },
            dismissButton = {
                TextButton(onClick = { resetting = null }, enabled = !busy) { Text("Cancel") }
            },
        )
    }

    deleting?.let { user ->
        AlertDialog(
            onDismissRequest = { if (!busy) deleting = null },
            title = { Text("Delete ${user.username}?") },
            text = {
                Column {
                    Text("This also deletes this account's private lists. This action cannot be undone.")
                    error?.let { InlineError(it) }
                }
            },
            confirmButton = {
                TextButton(
                    enabled = !busy,
                    onClick = {
                        runAction("Account deleted") {
                            Api.service.deleteUser(user.id)
                            deleting = null
                        }
                    },
                ) { Text("Delete", color = colors.clayDeep) }
            },
            dismissButton = {
                TextButton(onClick = { deleting = null }, enabled = !busy) { Text("Cancel") }
            },
        )
    }
}

@Composable
private fun RunsTab() {
    var refresh by remember { mutableIntStateOf(0) }
    val state by rememberLoad(refresh) { Api.service.taskRuns() }
    Loaded(state, onRetry = { refresh++ }) { runs -> RunsSection(runs) }
}

@Composable
private fun RunsSection(runs: List<TaskRun>) {
    val colors = CmTheme.colors
    if (runs.isEmpty()) {
        Text(
            "No task runs yet.",
            style = MaterialTheme.typography.bodyMedium.copy(fontStyle = FontStyle.Italic),
            color = colors.muted,
            modifier = Modifier.padding(horizontal = 20.dp, vertical = 20.dp),
        )
    }
    runs.forEachIndexed { index, run ->
        TaskRunRow(run)
        if (index < runs.lastIndex) {
            HorizontalDivider(color = colors.line, modifier = Modifier.padding(horizontal = 20.dp))
        }
    }
}

@Composable
private fun Section(title: String, content: @Composable () -> Unit) {
    val colors = CmTheme.colors
    Column(modifier = Modifier.fillMaxWidth().padding(horizontal = 20.dp, vertical = 22.dp)) {
        MonoLabel(title, colour = colors.muted, modifier = Modifier.padding(bottom = 10.dp))
        content()
    }
    HorizontalDivider(color = colors.line, modifier = Modifier.padding(horizontal = 20.dp))
}

@Composable
private fun StandardField(value: String, onValueChange: (String) -> Unit, label: String) {
    val colors = CmTheme.colors
    OutlinedTextField(
        value,
        onValueChange,
        label = { Text(label) },
        singleLine = true,
        colors = OutlinedTextFieldDefaults.colors(
            focusedBorderColor = colors.clay,
            unfocusedBorderColor = colors.lineStrong,
            cursorColor = colors.clay,
        ),
        modifier = Modifier.fillMaxWidth(),
    )
}

@Composable
private fun PasswordField(
    value: String,
    onValueChange: (String) -> Unit,
    label: String,
    modifier: Modifier = Modifier,
    showMinimum: Boolean = true,
) {
    val colors = CmTheme.colors
    OutlinedTextField(
        value,
        onValueChange,
        label = { Text(label) },
        singleLine = true,
        visualTransformation = PasswordVisualTransformation(),
        keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Password),
        supportingText = if (showMinimum) {
            { Text("At least $MIN_PASSWORD_LENGTH characters") }
        } else {
            null
        },
        colors = OutlinedTextFieldDefaults.colors(
            focusedBorderColor = colors.clay,
            unfocusedBorderColor = colors.lineStrong,
            cursorColor = colors.clay,
        ),
        modifier = modifier.fillMaxWidth(),
    )
}

@Composable
private fun NumberField(
    value: String,
    onValueChange: (String) -> Unit,
    label: String,
    modifier: Modifier = Modifier,
) {
    val colors = CmTheme.colors
    OutlinedTextField(
        value,
        onValueChange,
        label = { Text(label) },
        singleLine = true,
        keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Number),
        colors = OutlinedTextFieldDefaults.colors(
            focusedBorderColor = colors.clay,
            unfocusedBorderColor = colors.lineStrong,
            cursorColor = colors.clay,
        ),
        modifier = modifier.fillMaxWidth(),
    )
}

@Composable
private fun PrimaryButton(
    label: String,
    enabled: Boolean,
    modifier: Modifier = Modifier,
    onClick: () -> Unit,
) {
    val colors = CmTheme.colors
    Button(
        onClick,
        enabled = enabled,
        shape = MaterialTheme.shapes.extraSmall,
        colors = ButtonDefaults.buttonColors(containerColor = colors.clay),
        modifier = modifier.fillMaxWidth(),
    ) { Text(label) }
}

@Composable
private fun InlineError(message: String) {
    Text(
        message,
        style = MaterialTheme.typography.bodyMedium.copy(fontStyle = FontStyle.Italic),
        color = CmTheme.colors.clayDeep,
        modifier = Modifier.padding(top = 12.dp),
    )
}

@Composable
private fun TaskRunRow(run: TaskRun) {
    val colors = CmTheme.colors
    Column(modifier = Modifier.fillMaxWidth().padding(horizontal = 20.dp, vertical = 14.dp)) {
        Row(modifier = Modifier.fillMaxWidth()) {
            MonoLabel(
                words(run.status),
                colour = if (run.status == "failed") colors.clayDeep else colors.clay,
                modifier = Modifier.weight(1f),
            )
            MonoLabel(whenLabel(run.created_at), colour = colors.faint)
        }
        Text(
            run.book_title ?: words(run.task_type),
            style = MaterialTheme.typography.bodyLarge,
            color = colors.ink,
            modifier = Modifier.padding(top = 2.dp),
        )
        val meta = listOfNotNull(
            words(run.task_type).takeIf { run.book_title != null },
            run.model_name,
            run.cost_usd?.let { "\$$it" },
            detailLine(run).takeIf { it.isNotEmpty() },
        ).joinToString("  ·  ")
        if (meta.isNotEmpty()) MonoLabel(meta, colour = colors.faint, modifier = Modifier.padding(top = 4.dp))
        run.errors.forEach { error ->
            Text(
                error,
                style = MaterialTheme.typography.bodyMedium.copy(fontStyle = FontStyle.Italic),
                color = colors.clayDeep,
                modifier = Modifier.padding(top = 4.dp),
            )
        }
    }
}
