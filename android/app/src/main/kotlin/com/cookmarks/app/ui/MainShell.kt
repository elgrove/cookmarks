package com.cookmarks.app.ui

import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontStyle
import androidx.compose.ui.unit.dp
import androidx.navigation.NavGraph.Companion.findStartDestination
import androidx.navigation.compose.NavHost
import androidx.navigation.compose.composable
import androidx.navigation.compose.currentBackStackEntryAsState
import androidx.navigation.compose.rememberNavController
import com.cookmarks.app.ui.books.BookDetailScreen
import com.cookmarks.app.ui.books.BooksScreen
import com.cookmarks.app.ui.components.CentredState
import com.cookmarks.app.ui.components.MonoLabel
import com.cookmarks.app.ui.reader.PagerSource
import com.cookmarks.app.ui.reader.RecipePagerScreen
import com.cookmarks.app.ui.theme.CmTheme

private data class Tab(val route: String, val label: String)

private val Tabs = listOf(
    Tab("books", "Books"),
    Tab("recipes", "Recipes"),
    Tab("lists", "Lists"),
)

@Composable
fun MainShell() {
    val colors = CmTheme.colors
    val navController = rememberNavController()
    val backStackEntry by navController.currentBackStackEntryAsState()
    val route = backStackEntry?.destination?.route ?: "books"
    val immersive = route.startsWith("read/")

    Scaffold(
        containerColor = colors.bg,
        bottomBar = {
            if (!immersive) {
                Column {
                    HorizontalDivider(color = colors.lineStrong)
                    Row(
                        horizontalArrangement = Arrangement.SpaceEvenly,
                        modifier = Modifier
                            .fillMaxWidth()
                            .background(colors.bg)
                            .padding(vertical = 4.dp)
                            .padding(bottom = 8.dp),
                    ) {
                        Tabs.forEach { tab ->
                            val active = route == tab.route || (tab.route == "books" && route.startsWith("books/"))
                            MonoLabel(
                                text = tab.label,
                                colour = if (active) colors.clay else colors.muted,
                                modifier = Modifier
                                    .clickable {
                                        navController.navigate(tab.route) {
                                            popUpTo(navController.graph.findStartDestination().id) { saveState = true }
                                            launchSingleTop = true
                                            restoreState = true
                                        }
                                    }
                                    .padding(horizontal = 20.dp, vertical = 14.dp),
                            )
                        }
                    }
                }
            }
        },
    ) { padding ->
        Box(modifier = Modifier.fillMaxSize().padding(padding)) {
            NavHost(navController = navController, startDestination = "books") {
                composable("books") {
                    BooksScreen(onOpenBook = { navController.navigate("books/$it") })
                }
                composable("books/{bookId}") { entry ->
                    val bookId = entry.arguments?.getString("bookId") ?: return@composable
                    BookDetailScreen(
                        bookId = bookId,
                        onBack = { navController.popBackStack() },
                        onReadFrom = { start ->
                            navController.navigate("read/$bookId?start=${start ?: ""}")
                        },
                    )
                }
                composable("read/{bookId}?start={start}") { entry ->
                    val bookId = entry.arguments?.getString("bookId") ?: return@composable
                    val start = entry.arguments?.getString("start")?.takeIf { it.isNotEmpty() }
                    RecipePagerScreen(
                        source = PagerSource.Book(bookId),
                        startRecipeId = start,
                        onBack = { navController.popBackStack() },
                    )
                }
                composable("recipes") { PlaceholderScreen("Recipes") }
                composable("lists") { PlaceholderScreen("Lists") }
            }
        }
    }
}

@Composable
private fun PlaceholderScreen(name: String) {
    val colors = CmTheme.colors
    CentredState {
        Column(horizontalAlignment = androidx.compose.ui.Alignment.CenterHorizontally) {
            MonoLabel("Under construction", colour = colors.faint)
            Text(
                text = "The $name tab arrives with the next slice.",
                style = MaterialTheme.typography.bodyLarge.copy(fontStyle = FontStyle.Italic),
                color = colors.muted,
                modifier = Modifier.padding(top = 8.dp),
            )
        }
    }
}
