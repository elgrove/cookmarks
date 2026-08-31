package com.cookmarks.app.ui

import android.net.Uri
import androidx.compose.animation.core.tween
import androidx.compose.animation.fadeIn
import androidx.compose.animation.fadeOut
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Snackbar
import androidx.compose.material3.SnackbarHost
import androidx.compose.material3.SnackbarHostState
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.remember
import androidx.compose.ui.Modifier
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.semantics.selected
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.navigation.NavGraph.Companion.findStartDestination
import androidx.navigation.compose.NavHost
import androidx.navigation.compose.composable
import androidx.navigation.compose.currentBackStackEntryAsState
import androidx.navigation.compose.rememberNavController
import com.cookmarks.app.ui.admin.AdminScreen
import com.cookmarks.app.ui.books.BookDetailScreen
import com.cookmarks.app.ui.books.BooksScreen
import com.cookmarks.app.ui.discover.DiscoverScreen
import com.cookmarks.app.ui.discover.GameScreen
import com.cookmarks.app.ui.discover.GameSource
import com.cookmarks.app.ui.lists.ListDetailScreen
import com.cookmarks.app.ui.lists.ListsScreen
import com.cookmarks.app.ui.lists.ReadingQueueScreen
import com.cookmarks.app.ui.reader.PagerSource
import com.cookmarks.app.ui.reader.RecipePagerScreen
import com.cookmarks.app.ui.recipes.RecipeDetailScreen
import com.cookmarks.app.ui.recipes.RecipesScreen
import com.cookmarks.app.ui.theme.CmTheme

private data class Tab(val route: String, val label: String)

private val Tabs = listOf(
    Tab("books", "Books"),
    Tab("recipes", "Search"),
    Tab("lists", "Lists"),
    Tab("discover", "Discover"),
)

private fun gameRoute(source: GameSource): String = when (source) {
    GameSource.All -> "discover/play?mode=all"
    is GameSource.Search ->
        "discover/play?mode=search&q=${Uri.encode(source.q)}&keywords=${Uri.encode(source.keywords.joinToString("|"))}"
    is GameSource.Semantic -> "discover/play?mode=semantic&q=${Uri.encode(source.q)}"
    is GameSource.Book -> "discover/play?mode=book&book=${source.bookId}&title=${Uri.encode(source.title)}"
}

@Composable
fun MainShell() {
    val colors = CmTheme.colors
    val navController = rememberNavController()
    val backStackEntry by navController.currentBackStackEntryAsState()
    val route = backStackEntry?.destination?.route ?: "books"
    val immersive = route.startsWith("read/") || route.startsWith("read-list/") ||
        route.startsWith("discover/play")
    val snackbarHostState = remember { SnackbarHostState() }

    LaunchedEffect(Unit) {
        Feedback.messages.collect { message ->
            snackbarHostState.showSnackbar(message)
        }
    }

    Scaffold(
        containerColor = colors.bg,
        snackbarHost = {
            SnackbarHost(
                hostState = snackbarHostState,
                snackbar = { data ->
                    Snackbar(
                        snackbarData = data,
                        containerColor = colors.bgWarm,
                        contentColor = colors.ink,
                        shape = MaterialTheme.shapes.extraSmall,
                    )
                },
            )
        },
        bottomBar = {
            if (!immersive) {
                Column {
                    HorizontalDivider(color = colors.lineStrong)
                    Row(
                        modifier = Modifier
                            .fillMaxWidth()
                            .background(colors.bg)
                            .padding(horizontal = 8.dp, vertical = 4.dp),
                    ) {
                        Tabs.forEach { tab ->
                            val active = route == tab.route || route.startsWith("${tab.route}/") ||
                                (tab.route == "recipes" && route.startsWith("recipe/")) ||
                                (tab.route == "books" && route.startsWith("read/"))
                            Text(
                                text = tab.label.uppercase(),
                                style = MaterialTheme.typography.labelSmall.copy(fontSize = 13.sp, lineHeight = 18.sp),
                                color = if (active) colors.clay else colors.muted,
                                maxLines = 1,
                                modifier = Modifier
                                    .weight(1f)
                                    .clickable(
                                        role = Role.Tab,
                                        onClickLabel = "Switch to ${tab.label}",
                                    ) {
                                        if (active) {
                                            navController.popBackStack(tab.route, inclusive = false)
                                        } else {
                                            navController.navigate(tab.route) {
                                                popUpTo(navController.graph.findStartDestination().id) { saveState = true }
                                                launchSingleTop = true
                                                restoreState = true
                                            }
                                        }
                                    }
                                    .semantics {
                                        selected = active
                                    }
                                    .padding(horizontal = 4.dp, vertical = 16.dp),
                            )
                        }
                    }
                }
            }
        },
    ) { padding ->
        Box(modifier = Modifier.fillMaxSize().padding(padding)) {
            NavHost(
                navController = navController,
                startDestination = "books",
                enterTransition = { fadeIn(tween(90)) },
                exitTransition = { fadeOut(tween(90)) },
                popEnterTransition = { fadeIn(tween(90)) },
                popExitTransition = { fadeOut(tween(90)) },
            ) {
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
                        onDiscover = { title -> navController.navigate(gameRoute(GameSource.Book(bookId, title))) },
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
                composable("recipes") {
                    RecipesScreen(
                        onOpenRecipe = { id, ids ->
                            navController.navigate("recipe/$id?ctx=${RecipeContexts.put(ids)}")
                        },
                        onPlay = { source -> navController.navigate(gameRoute(source)) },
                    )
                }
                composable("recipe/{recipeId}?ctx={ctx}") { entry ->
                    val recipeId = entry.arguments?.getString("recipeId") ?: return@composable
                    RecipeDetailScreen(
                        recipeId = recipeId,
                        onBack = { navController.popBackStack() },
                        onOpenRecipe = { id, ids ->
                            navController.navigate("recipe/$id?ctx=${RecipeContexts.put(ids)}")
                        },
                        contextIds = RecipeContexts.get(entry.arguments?.getString("ctx")),
                    )
                }
                composable("lists") {
                    ListsScreen(
                        onOpenList = { navController.navigate("lists/$it") },
                        onOpenQueue = { navController.navigate("lists/reading-queue") },
                        onOpenAdmin = { navController.navigate("admin") { launchSingleTop = true } },
                    )
                }
                composable("lists/reading-queue") {
                    ReadingQueueScreen(
                        onBack = { navController.popBackStack() },
                        onOpenBook = { navController.navigate("lists/book/$it") },
                    )
                }
                composable("lists/book/{bookId}") { entry ->
                    val bookId = entry.arguments?.getString("bookId") ?: return@composable
                    BookDetailScreen(
                        bookId = bookId,
                        onBack = { navController.popBackStack() },
                        onReadFrom = { start ->
                            navController.navigate("read/$bookId?start=${start ?: ""}")
                        },
                        onDiscover = { title -> navController.navigate(gameRoute(GameSource.Book(bookId, title))) },
                    )
                }
                composable("lists/{listId}") { entry ->
                    val listId = entry.arguments?.getString("listId") ?: return@composable
                    ListDetailScreen(
                        listId = listId,
                        onBack = { navController.popBackStack() },
                        onOpenRecipe = { id, ids ->
                            navController.navigate("lists/recipe/$id?ctx=${RecipeContexts.put(ids)}")
                        },
                        onReadThrough = { navController.navigate("read-list/$listId") },
                    )
                }
                composable("lists/recipe/{recipeId}?ctx={ctx}") { entry ->
                    val recipeId = entry.arguments?.getString("recipeId") ?: return@composable
                    RecipeDetailScreen(
                        recipeId = recipeId,
                        onBack = { navController.popBackStack() },
                        onOpenRecipe = { id, ids ->
                            navController.navigate("lists/recipe/$id?ctx=${RecipeContexts.put(ids)}")
                        },
                        contextIds = RecipeContexts.get(entry.arguments?.getString("ctx")),
                    )
                }
                composable("admin") {
                    AdminScreen(onBack = { navController.popBackStack() })
                }
                composable("discover") {
                    DiscoverScreen(onPlay = { source -> navController.navigate(gameRoute(source)) })
                }
                composable("discover/play?mode={mode}&q={q}&keywords={keywords}&book={book}&title={title}") { entry ->
                    val mode = entry.arguments?.getString("mode") ?: "all"
                    val q = entry.arguments?.getString("q").orEmpty()
                    val keywords =
                        entry.arguments?.getString("keywords").orEmpty().split("|").filter { it.isNotEmpty() }
                    val source = when (mode) {
                        "search" -> GameSource.Search(q, keywords)
                        "semantic" -> GameSource.Semantic(q)
                        "book" -> {
                            val bookId = entry.arguments?.getString("book") ?: return@composable
                            GameSource.Book(bookId, entry.arguments?.getString("title").orEmpty())
                        }
                        else -> GameSource.All
                    }
                    GameScreen(source = source, onBack = { navController.popBackStack() })
                }
                composable("read-list/{listId}") { entry ->
                    val listId = entry.arguments?.getString("listId") ?: return@composable
                    RecipePagerScreen(
                        source = PagerSource.RecipeList(listId),
                        startRecipeId = null,
                        onBack = { navController.popBackStack() },
                    )
                }
            }
        }
    }
}
