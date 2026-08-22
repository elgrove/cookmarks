package com.cookmarks.app.ui

import androidx.compose.animation.core.tween
import androidx.compose.animation.fadeIn
import androidx.compose.animation.fadeOut
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
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.navigation.NavGraph.Companion.findStartDestination
import androidx.navigation.compose.NavHost
import androidx.navigation.compose.composable
import androidx.navigation.compose.currentBackStackEntryAsState
import androidx.navigation.compose.rememberNavController
import com.cookmarks.app.ui.books.BookDetailScreen
import com.cookmarks.app.ui.books.BooksScreen
import com.cookmarks.app.ui.lists.ListDetailScreen
import com.cookmarks.app.ui.lists.ListsScreen
import com.cookmarks.app.ui.reader.PagerSource
import com.cookmarks.app.ui.reader.RecipePagerScreen
import com.cookmarks.app.ui.recipes.RecipeDetailScreen
import com.cookmarks.app.ui.recipes.RecipesScreen
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
    val immersive = route.startsWith("read/") || route.startsWith("read-list/")

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
                            val active = route == tab.route || route.startsWith("${tab.route}/") ||
                                (tab.route == "recipes" && route.startsWith("recipe/")) ||
                                (tab.route == "books" && route.startsWith("read/")) ||
                                (tab.route == "lists" && route.startsWith("read-list/"))
                            Text(
                                text = tab.label.uppercase(),
                                style = MaterialTheme.typography.labelSmall.copy(fontSize = 13.sp, lineHeight = 18.sp),
                                color = if (active) colors.clay else colors.muted,
                                modifier = Modifier
                                    .clickable {
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
                                    .padding(horizontal = 20.dp, vertical = 20.dp),
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
                    RecipesScreen(onOpenRecipe = { id, ids ->
                        navController.navigate("recipe/$id?ctx=${RecipeContexts.put(ids)}")
                    })
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
                    ListsScreen(onOpenList = { navController.navigate("lists/$it") })
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
