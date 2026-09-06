package com.cookmarks.app.api

import kotlinx.serialization.EncodeDefault
import kotlinx.serialization.ExperimentalSerializationApi
import kotlinx.serialization.Serializable
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonObject

@Serializable
data class LoginRequest(val username: String, val password: String)

@Serializable
data class PasswordChange(val current_password: String, val new_password: String)

@Serializable
data class AuthMe(
    val id: String,
    val username: String,
    val is_admin: Boolean,
    val auth_mode: String,
    val user_instructions: String? = null,
    val book_grid_density: String = "standard",
)

@Serializable
data class ProviderInfo(val name: String, val requires_api_key: Boolean)

@Serializable
data class ConfigRead(
    val ai_provider: String?,
    val api_key_set: Boolean,
    val assistant_provider: String?,
    val assistant_api_key_set: Boolean,
    val extraction_rate_limit_per_minute: Int,
    val providers: List<ProviderInfo>,
)

@OptIn(ExperimentalSerializationApi::class)
@Serializable
data class ConfigUpdate(
    @EncodeDefault(EncodeDefault.Mode.NEVER)
    val ai_provider: JsonElement? = null,
    @EncodeDefault(EncodeDefault.Mode.NEVER)
    val api_key: JsonElement? = null,
    @EncodeDefault(EncodeDefault.Mode.NEVER)
    val assistant_provider: JsonElement? = null,
    @EncodeDefault(EncodeDefault.Mode.NEVER)
    val assistant_api_key: JsonElement? = null,
    @EncodeDefault(EncodeDefault.Mode.NEVER)
    val extraction_rate_limit_per_minute: Int? = null,
)

@Serializable
data class UserRead(
    val id: String,
    val username: String,
    val is_admin: Boolean,
    val created_at: String,
)

@Serializable
data class UserCreate(val username: String, val password: String, val is_admin: Boolean)

@Serializable
data class PasswordReset(val password: String)

@Serializable
data class BookKeywordTaskRequest(val regenerate: Boolean = false)

@Serializable
data class TaskRunAck(val task: String, val status: String, val queued: Int)

@Serializable
data class BookSummary(
    val id: String,
    val title: String,
    val author: String,
    val recipe_count: Int,
    val progress: Double?,
    val has_cover: Boolean,
    val pubdate: String?,
    val keywords: List<String>,
)

@Serializable
data class RecipeNeighbour(val id: String, val name: String)

@Serializable
data class IngredientLine(
    val id: String,
    val position: Int,
    val kind: String?,
    val text: String,
)

@Serializable
data class IngredientOccurrence(
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
data class ReadingState(
    val mode: String,
    val fraction: Double,
    val anchor: RecipeNeighbour?,
    val location: String?,
    val finished: Boolean,
)

@Serializable
data class RecipeRow(val id: String, val name: String, val keywords: List<String>)

@Serializable
data class BookDetail(
    val id: String,
    val title: String,
    val author: String,
    val isbn: String?,
    val pubdate: String?,
    val description: String,
    val recipe_count: Int,
    val has_cover: Boolean,
    val has_epub: Boolean,
    val added: String?,
    val keywords: List<String>,
    val recipes: List<RecipeRow>,
    val queued: Boolean,
    val reading: ReadingState?,
    val resume_recipe: RecipeNeighbour?,
)

@Serializable
data class ReadingUpdate(
    val mode: String,
    val recipe_id: String? = null,
    val location: String? = null,
)

@Serializable
data class BookReadState(
    val recipe_count: Int,
    val reading: ReadingState?,
)

@Serializable
data class RecipeIndexEntry(
    val id: String,
    val name: String,
    val is_favourite: Boolean,
    val epub_cfi: String?,
)

@Serializable
data class RecipeSummary(
    val id: String,
    val name: String,
    val book_id: String,
    val book_title: String,
    val book_author: String,
    val keywords: List<String>,
)

@Serializable
data class KeywordSummary(val name: String, val recipe_count: Int)

@Serializable
data class RecipeSearchResults(
    val total: Int,
    val items: List<RecipeSummary>,
    val facets: List<KeywordSummary> = emptyList(),
)

@Serializable
data class SemanticResult(
    val id: String,
    val name: String,
    val book_id: String,
    val book_title: String,
    val book_author: String,
    val keywords: List<String>,
    val distance: Double,
)

@Serializable
data class SemanticSearchResults(
    val available: Boolean,
    val query: String,
    val total: Int,
    val items: List<SemanticResult> = emptyList(),
)

@Serializable
data class RecipeDetail(
    val id: String,
    val book_id: String,
    val book_title: String,
    val book_author: String,
    val book_has_cover: Boolean,
    val name: String,
    val description: String?,
    val ingredients_verbatim: List<IngredientLine>,
    val ingredients: List<IngredientOccurrence>,
    val enrichment_status: String,
    val cuisines: List<RecipeCuisine>,
    val methods: List<RecipeFact>,
    val courses: List<RecipeFact>,
    val instructions: List<String>,
    val yields: String?,
    val keywords: List<String>,
    val has_image: Boolean,
    val is_favourite: Boolean,
    val context: String,
    val in_book: Boolean?,
    val previous: RecipeNeighbour?,
    val next: RecipeNeighbour?,
)

@Serializable
data class RecipeFact(
    val id: String,
    val name: String,
    val is_primary: Boolean,
    val source: String,
    val evidence: String?,
)

@Serializable
data class RecipeCuisine(val id: String, val source: String, val evidence: String?)

@Serializable
data class SimilarRecipes(val basis: String, val items: List<RecipeSummary>)

@Serializable
data class ListSummary(
    val id: String,
    val name: String,
    val is_default: Boolean,
    val recipe_count: Int,
)

@Serializable
data class ListDetail(
    val id: String,
    val name: String,
    val is_default: Boolean,
    val recipe_count: Int,
    val recipes: List<RecipeSummary>,
)

@Serializable
data class ListMembership(
    val id: String,
    val name: String,
    val is_default: Boolean,
    val contains: Boolean,
)

@Serializable
data class FavouriteState(val is_favourite: Boolean)

@Serializable
data class ListCreate(val name: String)

@Serializable
data class ListRecipeRef(val recipe_id: String)

@Serializable
data class QueuedBook(
    val id: String,
    val title: String,
    val author: String,
    val has_cover: Boolean,
    val recipe_count: Int,
)

@Serializable
data class QueueState(val queued: Boolean)

@Serializable
data class GameRecipeIds(val recipe_ids: List<String>)

@Serializable
data class DismissState(val dismissed: Boolean)

@Serializable
data class TaskRun(
    val id: String,
    val task_type: String,
    val status: String,
    val book_title: String?,
    val model_name: String?,
    val cost_usd: String?,
    val errors: List<String>,
    val detail: JsonObject,
    val created_at: String,
    val completed_at: String?,
)
