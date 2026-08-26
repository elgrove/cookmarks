package com.cookmarks.app

import android.app.Application
import coil.Coil
import coil.ImageLoader
import com.cookmarks.app.api.Api
import com.cookmarks.app.ui.theme.ThemePref

class CookmarksApplication : Application() {
    override fun onCreate() {
        super.onCreate()
        Api.init(this)
        ThemePref.init(this)
        Coil.setImageLoader(
            ImageLoader.Builder(this).okHttpClient(Api.client).build()
        )
    }
}
