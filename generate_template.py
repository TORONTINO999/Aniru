#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Генератор Android-шаблона для AnimeVost APK
Создаёт все необходимые файлы и папки для сборки
"""

import os
from pathlib import Path

# ==================== КОНФИГУРАЦИЯ ====================
TEMPLATE_DIR = Path("android_template")

# ==================== ВСЕ ФАЙЛЫ ====================
FILES = {
    # Корневые файлы
    "build.gradle": """buildscript {
    repositories {
        google()
        mavenCentral()
    }
    dependencies {
        classpath 'com.android.tools.build:gradle:8.2.0'
    }
}
""",
    "settings.gradle": """pluginManagement {
    repositories {
        google()
        mavenCentral()
        gradlePluginPortal()
    }
}
dependencyResolutionManagement {
    repositories {
        google()
        mavenCentral()
    }
}
rootProject.name = "AnimeVost"
include ':app'
""",

    # app/build.gradle
    "app/build.gradle": """plugins {
    id 'com.android.application'
}

android {
    namespace 'com.example.animevost'
    compileSdk 34

    defaultConfig {
        applicationId "com.example.animevost"
        minSdk 21
        targetSdk 34
        versionCode 1
        versionName "1.0"
    }

    buildTypes {
        release {
            minifyEnabled false
        }
    }

    compileOptions {
        sourceCompatibility JavaVersion.VERSION_1_8
        targetCompatibility JavaVersion.VERSION_1_8
    }
}

dependencies {
    implementation 'androidx.appcompat:appcompat:1.6.1'
    implementation 'com.google.android.material:material:1.11.0'
    implementation 'androidx.recyclerview:recyclerview:1.3.2'
    implementation 'com.google.code.gson:gson:2.10.1'
}
""",

    # AndroidManifest.xml
    "app/src/main/AndroidManifest.xml": """<?xml version="1.0" encoding="utf-8"?>
<manifest xmlns:android="http://schemas.android.com/apk/res/android">
    <uses-permission android:name="android.permission.INTERNET" />
    
    <application
        android:allowBackup="true"
        android:label="AnimeVost"
        android:theme="@style/Theme.AppCompat.DayNight.NoActionBar"
        android:usesCleartextTraffic="true">
        
        <activity
            android:name=".MainActivity"
            android:exported="true">
            <intent-filter>
                <action android:name="android.intent.action.MAIN" />
                <category android:name="android.intent.category.LAUNCHER" />
            </intent-filter>
        </activity>
    </application>
</manifest>
""",

    # MainActivity.kt
    "app/src/main/java/com/example/animevost/MainActivity.kt": """package com.example.animevost

import android.os.Bundle
import android.view.View
import android.webkit.JavascriptInterface
import android.webkit.WebView
import android.webkit.WebViewClient
import android.widget.*
import androidx.appcompat.app.AppCompatActivity
import androidx.recyclerview.widget.LinearLayoutManager
import androidx.recyclerview.widget.RecyclerView
import com.google.gson.Gson
import com.google.gson.reflect.TypeToken
import java.io.InputStreamReader
import java.text.SimpleDateFormat
import java.util.*

data class Film(
    val id: String?,
    val title: String,
    val year: String,
    val poster: String,
    val url: String,
    val category: String
)

class MainActivity : AppCompatActivity() {
    private lateinit var recyclerView: RecyclerView
    private lateinit var searchEdit: EditText
    private lateinit var btnExtract: Button
    private lateinit var btnM3U: Button
    private lateinit var progressBar: ProgressBar
    private lateinit var statusText: TextView
    private lateinit var webView: WebView
    private var allFilms = listOf<Film>()
    private var selectedFilms = mutableListOf<Film>()
    private val gson = Gson()

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_main)
        
        recyclerView = findViewById(R.id.recyclerView)
        searchEdit = findViewById(R.id.searchEdit)
        btnExtract = findViewById(R.id.btnExtract)
        btnM3U = findViewById(R.id.btnM3U)
        progressBar = findViewById(R.id.progressBar)
        statusText = findViewById(R.id.statusText)
        webView = findViewById(R.id.webView)
        
        loadFilms()
        setupWebView()
        setupSearch()
        setupButtons()
    }

    private fun loadFilms() {
        try {
            val inputStream = assets.open("films.json")
            val reader = InputStreamReader(inputStream)
            val type = object : TypeToken<Map<String, Any>>() {}.type
            val response: Map<String, Any> = gson.fromJson(reader, type)
            @Suppress("UNCHECKED_CAST")
            val filmsList = response["films"] as List<Map<String, String>>
            allFilms = filmsList.map { 
                Film(
                    it["id"], 
                    it["title"]!!, 
                    it["year"]!!, 
                    it["poster"]!!, 
                    it["url"]!!, 
                    it["category"]!!
                ) 
            }
            statusText.text = "Загружено ${allFilms.size} фильмов"
            setupRecyclerView(allFilms)
        } catch (e: Exception) {
            Toast.makeText(this, "Ошибка: ${e.message}", Toast.LENGTH_LONG).show()
        }
    }

    private fun setupRecyclerView(films: List<Film>) {
        val adapter = object : RecyclerView.Adapter<RecyclerView.ViewHolder>() {
            override fun onCreateViewHolder(parent: ViewGroup, viewType: Int): RecyclerView.ViewHolder {
                val view = layoutInflater.inflate(R.layout.item_film, parent, false)
                return object : RecyclerView.ViewHolder(view) {}
            }
            
            override fun onBindViewHolder(holder: RecyclerView.ViewHolder, position: Int) {
                val film = films[position]
                holder.itemView.findViewById<TextView>(R.id.tvTitle).text = film.title
                holder.itemView.findViewById<TextView>(R.id.tvYear).text = film.year
                holder.itemView.setOnClickListener {
                    if (!selectedFilms.contains(film)) {
                        selectedFilms.add(film)
                        Toast.makeText(
                            this@MainActivity, 
                            "Добавлен: ${film.title}", 
                            Toast.LENGTH_SHORT
                        ).show()
                    }
                }
            }
            
            override fun getItemCount(): Int = films.size
        }
        
        recyclerView.layoutManager = LinearLayoutManager(this)
        recyclerView.adapter = adapter
    }

    private fun setupWebView() {
        webView.settings.javaScriptEnabled = true
        webView.webViewClient = object : WebViewClient() {
            override fun onPageFinished(view: WebView?, url: String?) {
                view?.evaluateJavascript(JS_EXTRACTOR, null)
            }
        }
        webView.addJavascriptInterface(object {
            @JavascriptInterface
            fun onVideoUrl(url: String?) {
                runOnUiThread {
                    if (url != null) {
                        Toast.makeText(
                            this@MainActivity, 
                            "Ссылка найдена!", 
                            Toast.LENGTH_SHORT
                        ).show()
                    }
                }
            }
        }, "Android")
    }

    private fun setupSearch() {
        searchEdit.addTextChangedListener(object : android.text.TextWatcher {
            override fun beforeTextChanged(s: CharSequence?, start: Int, count: Int, after: Int) {}
            override fun onTextChanged(s: CharSequence?, start: Int, before: Int, count: Int) {}
            override fun afterTextChanged(s: android.text.Editable?) {
                val query = s.toString()
                val filtered = if (query.isEmpty()) {
                    allFilms
                } else {
                    allFilms.filter { it.title.contains(query, ignoreCase = true) }
                }
                setupRecyclerView(filtered)
            }
        })
    }

    private fun setupButtons() {
        btnExtract.setOnClickListener {
            if (selectedFilms.isEmpty()) {
                Toast.makeText(this, "Выберите фильмы из списка", Toast.LENGTH_SHORT).show()
                return@setOnClickListener
            }
            
            progressBar.visibility = View.VISIBLE
            progressBar.max = selectedFilms.size
            
            Thread {
                for ((index, film) in selectedFilms.withIndex()) {
                    runOnUiThread {
                        statusText.text = "${index+1}/${selectedFilms.size}: ${film.title}"
                        progressBar.progress = index + 1
                    }
                    runOnUiThread { webView.loadUrl(film.url) }
                    Thread.sleep(3000)
                }
                runOnUiThread {
                    progressBar.visibility = View.GONE
                    statusText.text = "Готово! Ссылки извлечены через WebView."
                }
            }.start()
        }

        btnM3U.setOnClickListener {
            if (selectedFilms.isEmpty()) {
                Toast.makeText(this, "Нет выбранных фильмов", Toast.LENGTH_SHORT).show()
                return@setOnClickListener
            }
            
            val sb = StringBuilder("#EXTM3U\\n#EXTM3U url-tvg=\"\"\\n\\n")
            for (f in selectedFilms.sortedBy { it.year.toIntOrNull() ?: 9999 }) {
                val group = if (f.year != "неизвестно") "Фильмы ${f.year}" else "Фильмы"
                val title = f.title.replace("\"", "").replace(",", ";")
                sb.append("#EXTINF:-1 group-title=\"$group\" tvg-logo=\"${f.poster}\", $title\\n")
                sb.append("${f.url}\\n\\n")
            }
            
            val filename = "animevost_${SimpleDateFormat("yyyy-MM-dd", Locale.getDefault()).format(Date())}.m3u"
            val file = java.io.File(cacheDir, filename)
            file.writeText(sb.toString())
            
            val intent = android.content.Intent(android.content.Intent.ACTION_SEND).apply {
                type = "text/plain"
                putExtra(android.content.Intent.EXTRA_STREAM, android.net.Uri.fromFile(file))
                addFlags(android.content.Intent.FLAG_GRANT_READ_URI_PERMISSION)
            }
            startActivity(android.content.Intent.createChooser(intent, "Сохранить M3U"))
        }
    }

    companion object {
        private const val JS_EXTRACTOR = "(function() { setTimeout(function() { var video = document.querySelector('video'); if (video && video.src) { Android.onVideoUrl(video.src); return; } var iframe = document.querySelector('iframe'); if (iframe && iframe.src) { Android.onVideoUrl(iframe.src); return; } Android.onVideoUrl(null); }, 2000); })();"
    }
}
""",

    # activity_main.xml
    "app/src/main/res/layout/activity_main.xml": """<?xml version="1.0" encoding="utf-8"?>
<LinearLayout xmlns:android="http://schemas.android.com/apk/res/android"
    android:layout_width="match_parent"
    android:layout_height="match_parent"
    android:orientation="vertical"
    android:padding="16dp"
    android:background="#0b0b1a">

    <EditText
        android:id="@+id/searchEdit"
        android:layout_width="match_parent"
        android:layout_height="wrap_content"
        android:hint="Поиск фильма..."
        android:padding="12dp"
        android:textColor="#ffffff"
        android:textColorHint="#888888"
        android:background="@drawable/search_bg" />

    <androidx.recyclerview.widget.RecyclerView
        android:id="@+id/recyclerView"
        android:layout_width="match_parent"
        android:layout_height="0dp"
        android:layout_weight="1"
        android:layout_marginTop="8dp" />

    <LinearLayout
        android:layout_width="match_parent"
        android:layout_height="wrap_content"
        android:orientation="horizontal"
        android:layout_marginTop="8dp">

        <Button
            android:id="@+id/btnExtract"
            android:layout_width="0dp"
            android:layout_height="wrap_content"
            android:layout_weight="1"
            android:text="Извлечь ссылки"
            android:backgroundTint="#00d4ff"
            android:textColor="#000000" />

        <Button
            android:id="@+id/btnM3U"
            android:layout_width="0dp"
            android:layout_height="wrap_content"
            android:layout_weight="1"
            android:text="Создать M3U"
            android:backgroundTint="#44ff88"
            android:textColor="#000000" />

    </LinearLayout>

    <ProgressBar
        android:id="@+id/progressBar"
        style="?android:attr/progressBarStyleHorizontal"
        android:layout_width="match_parent"
        android:layout_height="wrap_content"
        android:layout_marginTop="8dp"
        android:visibility="gone" />

    <TextView
        android:id="@+id/statusText"
        android:layout_width="match_parent"
        android:layout_height="wrap_content"
        android:text="Готов к работе"
        android:textColor="#00ff88"
        android:textSize="12sp"
        android:layout_marginTop="4dp" />

    <WebView
        android:id="@+id/webView"
        android:layout_width="1dp"
        android:layout_height="1dp"
        android:visibility="gone" />

</LinearLayout>
""",

    # item_film.xml
    "app/src/main/res/layout/item_film.xml": """<?xml version="1.0" encoding="utf-8"?>
<LinearLayout xmlns:android="http://schemas.android.com/apk/res/android"
    android:layout_width="match_parent"
    android:layout_height="wrap_content"
    android:orientation="horizontal"
    android:padding="12dp"
    android:background="#1a1a2e"
    android:layout_marginBottom="4dp"
    android:clickable="true">

    <TextView
        android:id="@+id/tvTitle"
        android:layout_width="0dp"
        android:layout_height="wrap_content"
        android:layout_weight="1"
        android:textColor="#ffffff"
        android:textSize="16sp"
        android:textStyle="bold" />

    <TextView
        android:id="@+id/tvYear"
        android:layout_width="wrap_content"
        android:layout_height="wrap_content"
        android:textColor="#888888"
        android:textSize="14sp"
        android:layout_marginStart="8dp" />

</LinearLayout>
""",

    # search_bg.xml
    "app/src/main/res/drawable/search_bg.xml": """<?xml version="1.0" encoding="utf-8"?>
<shape xmlns:android="http://schemas.android.com/apk/res/android">
    <solid android:color="#2a2a3e" />
    <corners android:radius="8dp" />
    <stroke android:width="1dp" android:color="#444" />
</shape>
""",

    # colors.xml
    "app/src/main/res/values/colors.xml": """<?xml version="1.0" encoding="utf-8"?>
<resources>
    <color name="black">#0b0b1a</color>
</resources>
""",

    # themes.xml
    "app/src/main/res/values/themes.xml": """<?xml version="1.0" encoding="utf-8"?>
<resources>
    <style name="Theme.AppCompat.DayNight.NoActionBar" parent="Theme.AppCompat.DayNight">
        <item name="windowActionBar">false</item>
        <item name="windowNoTitle">true</item>
        <item name="android:windowBackground">@color/black</item>
    </style>
</resources>
""",
}


# ==================== ФУНКЦИЯ ГЕНЕРАЦИИ ====================
def generate_template():
    """Создаёт все файлы и папки шаблона"""
    print("🚀 Генерация Android-шаблона...")
    print("═" * 60)
    
    # Удаляем старую папку, если есть
    if TEMPLATE_DIR.exists():
        import shutil
        shutil.rmtree(TEMPLATE_DIR)
        print(f"🗑️  Старая папка {TEMPLATE_DIR} удалена")
    
    # Создаём все файлы
    for file_path, content in FILES.items():
        full_path = TEMPLATE_DIR / file_path
        full_path.parent.mkdir(parents=True, exist_ok=True)
        full_path.write_text(content, encoding="utf-8")
        print(f"✅ Создан: {file_path}")
    
    print("═" * 60)
    print(f"🎉 Готово! Шаблон создан в папке {TEMPLATE_DIR}")
    print(f"📁 Всего файлов: {len(FILES)}")


# ==================== ЗАПУСК ====================
if __name__ == "__main__":
    generate_template()
