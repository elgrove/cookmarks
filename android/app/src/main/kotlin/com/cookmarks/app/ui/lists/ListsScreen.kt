package com.cookmarks.app.ui.lists

import android.util.Log
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.itemsIndexed
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.OutlinedTextFieldDefaults
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import com.cookmarks.app.api.Api
import com.cookmarks.app.api.ListCreate
import com.cookmarks.app.ui.components.Loaded
import com.cookmarks.app.ui.components.MonoLabel
import com.cookmarks.app.ui.components.rememberLoad
import com.cookmarks.app.ui.theme.CmTheme
import kotlin.coroutines.cancellation.CancellationException
import kotlinx.coroutines.launch

@Composable
fun ListsScreen(onOpenList: (String) -> Unit) {
    val colors = CmTheme.colors
    val scope = rememberCoroutineScope()
    var tick by remember { mutableIntStateOf(0) }
    val state by rememberLoad(tick) { Api.service.lists() }
    var newName by rememberSaveable { mutableStateOf("") }

    fun create() {
        val name = newName.trim()
        if (name.isEmpty()) return
        scope.launch {
            try {
                Api.service.createList(ListCreate(name))
                newName = ""
                tick++
            } catch (e: CancellationException) {
                throw e
            } catch (e: Exception) {
                Log.w("Lists", "create list failed", e)
            }
        }
    }

    Loaded(state, onRetry = { tick++ }) { lists ->
        LazyColumn(
            modifier = Modifier.fillMaxSize(),
            contentPadding = PaddingValues(vertical = 16.dp),
        ) {
            item {
                Column(modifier = Modifier.padding(horizontal = 20.dp)) {
                    Text(
                        text = "Lists",
                        style = MaterialTheme.typography.displaySmall,
                        color = colors.ink,
                        modifier = Modifier.padding(bottom = 12.dp),
                    )
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        OutlinedTextField(
                            value = newName,
                            onValueChange = { newName = it },
                            placeholder = { Text("New list") },
                            singleLine = true,
                            colors = OutlinedTextFieldDefaults.colors(
                                focusedBorderColor = colors.clay,
                                unfocusedBorderColor = colors.lineStrong,
                                cursorColor = colors.clay,
                            ),
                            modifier = Modifier.weight(1f),
                        )
                        MonoLabel(
                            "Create",
                            colour = if (newName.isBlank()) colors.faint else colors.clay,
                            modifier = Modifier.clickable { create() }.padding(12.dp),
                        )
                    }
                }
            }
            itemsIndexed(lists, key = { _, l -> l.id }) { i, list ->
                Row(
                    verticalAlignment = Alignment.CenterVertically,
                    modifier = Modifier
                        .fillMaxWidth()
                        .clickable { onOpenList(list.id) }
                        .padding(horizontal = 20.dp, vertical = 16.dp),
                ) {
                    Column(modifier = Modifier.weight(1f)) {
                        Text(
                            text = list.name,
                            style = MaterialTheme.typography.titleLarge,
                            color = colors.ink,
                            maxLines = 1,
                            overflow = TextOverflow.Ellipsis,
                        )
                        MonoLabel(
                            listOfNotNull(
                                "${list.recipe_count} recipes",
                                "Default".takeIf { list.is_default },
                            ).joinToString("  ·  "),
                            colour = colors.faint,
                            modifier = Modifier.padding(top = 2.dp),
                        )
                    }
                    if (list.is_default) {
                        Text("★", color = colors.clay)
                    }
                }
                if (i < lists.lastIndex) {
                    HorizontalDivider(color = colors.line, modifier = Modifier.padding(horizontal = 20.dp))
                }
            }
            item {
                MonoLabel(
                    "Sign out",
                    colour = colors.faint,
                    modifier = Modifier
                        .clickable {
                            scope.launch {
                                try {
                                    Api.service.logout()
                                } catch (e: CancellationException) {
                                    throw e
                                } catch (e: Exception) {
                                    Log.w("Lists", "logout request failed", e)
                                }
                                Api.cookieJar.clear()
                                Api.loggedIn.value = false
                            }
                        }
                        .padding(horizontal = 20.dp, vertical = 28.dp),
                )
            }
        }
    }
}
