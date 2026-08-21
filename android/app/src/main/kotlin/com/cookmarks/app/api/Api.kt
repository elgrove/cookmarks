package com.cookmarks.app.api

import android.content.Context
import android.content.SharedPreferences
import com.cookmarks.app.BuildConfig
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.serialization.json.Json
import okhttp3.Cookie
import okhttp3.CookieJar
import okhttp3.HttpUrl
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import retrofit2.Retrofit
import retrofit2.converter.kotlinx.serialization.asConverterFactory

const val SESSION_COOKIE = "cm_session"

class SessionCookieJar(private val prefs: SharedPreferences) : CookieJar {
    override fun saveFromResponse(url: HttpUrl, cookies: List<Cookie>) {
        cookies.firstOrNull { it.name == SESSION_COOKIE }?.let {
            prefs.edit()
                .putString("value", it.value)
                .putLong("expires", it.expiresAt)
                .apply()
        }
    }

    override fun loadForRequest(url: HttpUrl): List<Cookie> {
        val value = prefs.getString("value", null) ?: return emptyList()
        if (prefs.getLong("expires", 0) < System.currentTimeMillis()) return emptyList()
        return listOf(
            Cookie.Builder().name(SESSION_COOKIE).value(value).domain(url.host).build()
        )
    }

    fun hasSession(): Boolean =
        prefs.getString("value", null) != null &&
            prefs.getLong("expires", 0) >= System.currentTimeMillis()

    fun clear() = prefs.edit().clear().apply()
}

object Api {
    val json = Json {
        ignoreUnknownKeys = true
        encodeDefaults = true
    }

    val loggedIn = MutableStateFlow(false)

    lateinit var cookieJar: SessionCookieJar
        private set

    lateinit var client: OkHttpClient
        private set

    lateinit var service: CookmarksService
        private set

    fun init(context: Context) {
        cookieJar = SessionCookieJar(context.getSharedPreferences("session", Context.MODE_PRIVATE))
        client = OkHttpClient.Builder()
            .cookieJar(cookieJar)
            .addInterceptor { chain ->
                val response = chain.proceed(chain.request())
                val isLogin = chain.request().url.encodedPath.endsWith("/auth/login")
                if (response.code == 401 && !isLogin) {
                    cookieJar.clear()
                    loggedIn.value = false
                }
                response
            }
            .build()
        service = Retrofit.Builder()
            .baseUrl(BuildConfig.BASE_URL + "/")
            .client(client)
            .addConverterFactory(json.asConverterFactory("application/json".toMediaType()))
            .build()
            .create(CookmarksService::class.java)
        loggedIn.value = cookieJar.hasSession()
    }

    fun bookCoverUrl(bookId: String): String = "${BuildConfig.BASE_URL}/api/books/$bookId/cover"

    fun recipeImageUrl(recipeId: String): String = "${BuildConfig.BASE_URL}/api/recipes/$recipeId/image"
}
