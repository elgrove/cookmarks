package com.cookmarks.app.ui

fun cleanTitle(title: String): String {
    val i = title.indexOf(':')
    return if (i == -1) title else title.substring(0, i).trim()
}

fun titleSubtitle(title: String): String {
    val i = title.indexOf(':')
    return if (i == -1) "" else title.substring(i + 1).replace(Regex("\\s*:\\s*"), " — ").trim()
}
