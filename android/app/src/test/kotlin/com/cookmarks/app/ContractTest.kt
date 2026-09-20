package com.cookmarks.app

import com.cookmarks.app.api.Api
import com.cookmarks.app.api.AuthMe
import com.cookmarks.app.api.BookDetail
import com.cookmarks.app.api.BookReadState
import com.cookmarks.app.api.BookSummary
import com.cookmarks.app.api.ConfigRead
import com.cookmarks.app.api.ConfigUpdate
import com.cookmarks.app.api.DismissState
import com.cookmarks.app.api.GameRecipeIds
import com.cookmarks.app.api.KeywordSummary
import com.cookmarks.app.api.ListDetail
import com.cookmarks.app.api.ListMembership
import com.cookmarks.app.api.ListSummary
import com.cookmarks.app.api.ProviderConfigUpdate
import com.cookmarks.app.api.ReadingState
import com.cookmarks.app.api.RecipeDetail
import com.cookmarks.app.api.RecipeIndexEntry
import com.cookmarks.app.api.RecipeSearchResults
import com.cookmarks.app.api.SemanticSearchResults
import com.cookmarks.app.api.SimilarRecipes
import com.cookmarks.app.api.TaskRun
import com.cookmarks.app.api.TaskRunAck
import com.cookmarks.app.api.UserRead
import java.io.File
import kotlinx.serialization.Serializable
import kotlinx.serialization.encodeToString
import kotlinx.serialization.json.JsonNull
import kotlinx.serialization.json.decodeFromJsonElement
import kotlinx.serialization.json.jsonObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

@Serializable
private data class LegacyIngredientLine(
    val id: String,
    val position: Int,
    val kind: String?,
    val text: String,
)

@Serializable
private data class LegacyIngredientOccurrence(
    val id: String,
    val line_id: String,
    val position: Int,
    val ingredient_id: String,
    val ingredient_name: String,
    val quantity: String?,
    val unit: String?,
    val preparation: String?,
    val optional: Boolean,
    val alternative_group: Int?,
    val is_key: Boolean,
    val parse_method: String,
    val resolution_method: String,
)

@Serializable
private data class LegacyRecipeFact(
    val id: String,
    val name: String,
    val is_primary: Boolean,
    val source: String,
    val evidence: String?,
)

@Serializable
private data class LegacyRecipeCuisine(
    val id: String,
    val source: String,
    val evidence: String?,
)

@Serializable
private data class LegacyRecipeNeighbour(val id: String, val name: String)

@Serializable
private data class LegacyRecipeDetail(
    val id: String,
    val book_id: String,
    val book_title: String,
    val book_author: String,
    val book_has_cover: Boolean,
    val name: String,
    val description: String?,
    val ingredients_verbatim: List<LegacyIngredientLine>,
    val ingredients: List<LegacyIngredientOccurrence>,
    val enrichment_status: String,
    val cuisines: List<LegacyRecipeCuisine>,
    val methods: List<LegacyRecipeFact>,
    val courses: List<LegacyRecipeFact>,
    val instructions: List<String>,
    val yields: String?,
    val keywords: List<String>,
    val has_image: Boolean,
    val is_favourite: Boolean,
    val context: String,
    val in_book: Boolean?,
    val previous: LegacyRecipeNeighbour?,
    val next: LegacyRecipeNeighbour?,
)

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
        val me = pin<AuthMe>("authme")
        assertEquals("aaron", me.username)
        assertEquals("standard", me.book_grid_density)
    }

    @Test
    fun config() {
        val config = pin<ConfigRead>("config")
        assertEquals(3, config.providers.size)
        assertEquals("GEMINI", config.providers.minBy { it.display_order }.provider)
        assertEquals(256, config.extraction_rate_limit_per_minute)
    }

    @Test
    fun config_update_omits_unchanged_keys() {
        val encoded = Api.json.encodeToString(
            ConfigUpdate(
                extraction_rate_limit_per_minute = 120,
            )
        )
        assertTrue("api_key" !in encoded)
        assertTrue("provider_configs" !in encoded)
    }

    @Test
    fun config_update_can_clear_a_provider() {
        val encoded = Api.json.encodeToString(
            ConfigUpdate(
                provider_configs = listOf(
                    ProviderConfigUpdate(provider = "GEMINI", api_key = JsonNull)
                )
            )
        )
        assertTrue("\"api_key\":null" in encoded)
    }

    @Test
    fun user() {
        assertTrue(pin<UserRead>("user").is_admin)
    }

    @Test
    fun task_run_ack() {
        assertEquals("queued", pin<TaskRunAck>("taskrunack").status)
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
        assertTrue(recipe.ingredients_verbatim.all { it.kind == null })
        assertEquals(0, recipe.canonical_ingredients.size)
        assertEquals("book", recipe.context)
    }

    @Test
    fun released_recipe_detail_remains_compatible() {
        val recipe = pin<LegacyRecipeDetail>("recipe")
        assertTrue(recipe.ingredients_verbatim.all { it.kind == null })
        assertTrue(recipe.ingredients.isEmpty())
        assertEquals("inferred", recipe.methods.single().source)
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
