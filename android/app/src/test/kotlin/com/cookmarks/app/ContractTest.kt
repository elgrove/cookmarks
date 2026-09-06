package com.cookmarks.app

import com.cookmarks.app.api.Api
import com.cookmarks.app.api.AuthMe
import com.cookmarks.app.api.BookDetail
import com.cookmarks.app.api.BookReadState
import com.cookmarks.app.api.BookSummary
import com.cookmarks.app.api.DismissState
import com.cookmarks.app.api.GameRecipeIds
import com.cookmarks.app.api.KeywordSummary
import com.cookmarks.app.api.ListDetail
import com.cookmarks.app.api.ListMembership
import com.cookmarks.app.api.ListSummary
import com.cookmarks.app.api.ReadingState
import com.cookmarks.app.api.RecipeDetail
import com.cookmarks.app.api.RecipeIndexEntry
import com.cookmarks.app.api.RecipeSearchResults
import com.cookmarks.app.api.SemanticSearchResults
import com.cookmarks.app.api.SimilarRecipes
import com.cookmarks.app.api.TaskRun
import java.io.File
import kotlinx.serialization.json.decodeFromJsonElement
import kotlinx.serialization.json.jsonObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class ContractTest {
    private val contract = File("../../contract")

    private inline fun <reified T> pin(name: String): T =
        Api.json.decodeFromString<T>(File(contract, "$name.example.json").readText())

    @Test
    fun contract_directory_exists() {
        assertTrue(contract.isDirectory)
    }

    @Test
    fun authme() {
        assertEquals("aaron", pin<AuthMe>("authme").username)
    }

    @Test
    fun book_summary() {
        val book = pin<BookSummary>("books")
        assertEquals("Salt, Fat, Acid, Heat", book.title)
        assertEquals(100, book.recipe_count)
    }

    @Test
    fun book_detail() {
        val detail = pin<BookDetail>("bookdetail")
        assertEquals("recipes", detail.reading!!.mode)
        assertEquals(detail.resume_recipe!!.id, detail.reading!!.anchor!!.id)
    }

    @Test
    fun recipe_index_entry() {
        assertTrue(pin<RecipeIndexEntry>("recipeindex").epub_cfi!!.startsWith("epubcfi("))
    }

    @Test
    fun recipe_search_results() {
        val results = pin<RecipeSearchResults>("recipes")
        assertEquals(1, results.items.size)
        assertEquals(2, results.facets.size)
    }

    @Test
    fun semantic_search_results() {
        val results = pin<SemanticSearchResults>("semanticsearch")
        assertTrue(results.available)
        assertEquals(2, results.items.size)
    }

    @Test
    fun recipe_detail() {
        val recipe = pin<RecipeDetail>("recipe")
        assertEquals(3, recipe.ingredients_verbatim.size)
        assertEquals(0, recipe.canonical_ingredients.size)
        assertEquals("book", recipe.context)
    }

    @Test
    fun similar_recipes() {
        assertEquals("vector", pin<SimilarRecipes>("similar").basis)
    }

    @Test
    fun keyword_summary() {
        assertEquals(42, pin<KeywordSummary>("keywords").recipe_count)
    }

    @Test
    fun list_summary() {
        assertEquals(12, pin<ListSummary>("listsummary").recipe_count)
    }

    @Test
    fun list_detail() {
        assertEquals(1, pin<ListDetail>("listdetail").recipes.size)
    }

    @Test
    fun list_membership() {
        assertTrue(pin<ListMembership>("listmembership").contains)
    }

    @Test
    fun reading_state() {
        val state = pin<BookReadState>("bookreadstate")
        assertEquals(100, state.recipe_count)
        val reading = state.reading!!
        assertTrue(reading.finished)
        assertEquals("Buttermilk-Marinated Roast Chicken", reading.anchor!!.name)
    }

    @Test
    fun game_recipe_ids() {
        assertEquals(1, pin<GameRecipeIds>("gameeligible").recipe_ids.size)
    }

    @Test
    fun dismiss_state() {
        assertTrue(pin<DismissState>("dismissstate").dismissed)
    }

    @Test
    fun task_run() {
        val run = pin<TaskRun>("taskrun")
        assertEquals("extraction", run.task_type)
        assertEquals("The Flavour Thesaurus", run.book_title)
    }
}
