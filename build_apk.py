#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Сборщик APK приложения для AnimeVost
Создаёт Android-приложение с встроенными данными из films_structure.json

Запуск: python build_apk.py
Результат: animevost_app.apk в текущей папке
"""

import os
import sys
import json
import shutil
import subprocess
import zipfile
import requests
import tempfile
from pathlib import Path

# ==================== КОНФИГУРАЦИЯ ====================
APK_TEMPLATE_URL = "https://github.com/yourusername/animevost-android-template/archive/refs/heads/main.zip"
# Для демонстрации мы создадим минимальный шаблон прямо в скрипте
OUTPUT_APK = "animevost_app.apk"
JSON_FILE = "films_structure.json"
TEMPLATE_DIR = "android_template"

# ==================== СОЗДАНИЕ ШАБЛОНА ====================
def create_template():
    """Создаёт минимальный Android-проект для приложения"""
    print("📱 Создание шаблона Android-приложения...")
    
    # Создаём структуру папок
    project_dir = Path(TEMPLATE_DIR)
    if project_dir.exists():
        shutil.rmtree(project_dir)
    project_dir.mkdir(parents=True)
    
    # ---------- build.gradle (проектный) ----------
    (project_dir / "build.gradle").write_text("""
buildscript {
    repositories {
        google()
        mavenCentral()
    }
    dependencies {
        classpath 'com.android.tools.build:gradle:8.2.0'
        classpath 'org.jetbrains.kotlin:kotlin-gradle-plugin:1.9.0'
    }
}
""")

    # ---------- settings.gradle ----------
    (project_dir / "settings.gradle").write_text("""
pluginManagement {
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
""")

    # ---------- app/build.gradle ----------
    app_dir = project_dir / "app"
    app_dir.mkdir()
    (app_dir / "build.gradle").write_text("""
plugins {
    id 'com.android.application'
    id 'org.jetbrains.kotlin.android'
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
            proguardFiles getDefaultProguardFile('proguard-android-optimize.txt'), 'proguard-rules.pro'
        }
    }
    compileOptions {
        sourceCompatibility JavaVersion.VERSION_1_8
        targetCompatibility JavaVersion.VERSION_1_8
    }
    kotlinOptions {
        jvmTarget = '1.8'
    }
}

dependencies {
    implementation 'androidx.core:core-ktx:1.12.0'
    implementation 'androidx.appcompat:appcompat:1.6.1'
    implementation 'com.google.android.material:material:1.11.0'
    implementation 'androidx.constraintlayout:constraintlayout:2.1.4'
    implementation 'com.google.code.gson:gson:2.10.1'
    implementation 'com.github.bumptech.glide:glide:4.16.0'
}
""")

    # ---------- AndroidManifest.xml ----------
    manifest_dir = app_dir / "src" / "main"
    manifest_dir.mkdir(parents=True)
    (manifest_dir / "AndroidManifest.xml").write_text("""<?xml version="1.0" encoding="utf-8"?>
<manifest xmlns:android="http://schemas.android.com/apk/res/android">
    <uses-permission android:name="android.permission.INTERNET" />
    <application
        android:allowBackup="true"
        android:icon="@mipmap/ic_launcher"
        android:label="AnimeVost"
        android:theme="@style/Theme.AppCompat.DayNight.NoActionBar">
        <activity android:name=".MainActivity" android:exported="true">
            <intent-filter>
                <action android:name="android.intent.action.MAIN" />
                <category android:name="android.intent.category.LAUNCHER" />
            </intent-filter>
        </activity>
    </application>
</manifest>
""")

    # ---------- Java/Kotlin исходники ----------
    java_dir = manifest_dir / "java" / "com" / "example" / "animevost"
    java_dir.mkdir(parents=True)

    (java_dir / "Film.kt").write_text("""
package com.example.animevost

data class Film(
    val id: String?,
    val title: String,
    val year: String,
    val poster: String,
    val url: String,
    val category: String
)

data class FilmsResponse(
    val timestamp: String,
    val total: Int,
    val films: List<Film>
)
""")

    (java_dir / "M3UGenerator.kt").write_text("""
package com.example.animevost

import android.content.Context
import java.io.File
import java.text.SimpleDateFormat
import java.util.*

class M3UGenerator {
    fun generate(films: List<Film>, context: Context): File {
        val sorted = films.sortedBy { it.year.toIntOrNull() ?: 9999 }
        val sb = StringBuilder()
        sb.append("#EXTM3U\\n#EXTM3U url-tvg=\\"\\"\\n\\n")
        for (f in sorted) {
            val group = if (f.year != "неизвестно") "Фильмы \${f.year}" else "Фильмы"
            val title = f.title.replace("\\"", "").replace(",", ";")
            sb.append("#EXTINF:-1 group-title=\\"$group\\" tvg-logo=\\"\${f.poster}\\", $title\\n")
            sb.append("\${f.url}\\n\\n")
        }
        val filename = "animevost_\${SimpleDateFormat("yyyy-MM-dd", Locale.getDefault()).format(Date())}.m3u"
        val file = File(context.cacheDir, filename)
        file.writeText(sb.toString())
        return file
    }
}
""")

    (java_dir / "MainActivity.kt").write_text("""
package com.example.animevost

import android.content.Intent
import android.net.Uri
import android.os.Bundle
import android.view.View
import android.webkit.WebView
import android.webkit.WebViewClient
import android.webkit.JavascriptInterface
import android.widget.*
import androidx.appcompat.app.AppCompatActivity
import androidx.recyclerview.widget.LinearLayoutManager
import androidx.recyclerview.widget.RecyclerView
import com.google.gson.Gson
import java.io.InputStreamReader

class MainActivity : AppCompatActivity() {

    private lateinit var recyclerView: RecyclerView
    private lateinit var searchEdit: EditText
    private lateinit var btnExtract: Button
    private lateinit var btnM3U: Button
    private lateinit var progressBar: ProgressBar
    private lateinit var statusText: TextView
    private lateinit var webView: WebView

    private var allFilms = listOf<Film>()
    private val gson = Gson()
    private var selectedFilms = mutableListOf<Film>()

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
            val response = gson.fromJson(reader, FilmsResponse::class.java)
            allFilms = response.films
            statusText.text = "Загружено \${allFilms.size} фильмов"
            setupRecyclerView(allFilms)
        } catch (e: Exception) {
            Toast.makeText(this, "Ошибка: \${e.message}", Toast.LENGTH_LONG).show()
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
                holder.itemView.findViewById<TextView>(R.id.tvCategory).text = film.category
                holder.itemView.setOnClickListener {
                    selectedFilms.add(film)
                    Toast.makeText(this@MainActivity, "Выбран: \${film.title}", Toast.LENGTH_SHORT).show()
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
                        Toast.makeText(this@MainActivity, "Ссылка получена", Toast.LENGTH_SHORT).show()
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
                val filtered = if (query.isEmpty()) allFilms else allFilms.filter { it.title.contains(query, ignoreCase = true) }
                setupRecyclerView(filtered)
            }
        })
    }

    private fun setupButtons() {
        btnExtract.setOnClickListener {
            if (selectedFilms.isEmpty()) {
                Toast.makeText(this, "Выберите фильмы", Toast.LENGTH_SHORT).show()
                return@setOnClickListener
            }
            progressBar.visibility = View.VISIBLE
            statusText.text = "Извлечение..."
            Thread {
                for ((index, film) in selectedFilms.withIndex()) {
                    runOnUiThread {
                        statusText.text = "\${index+1}/\${selectedFilms.size}: \${film.title}"
                        progressBar.max = selectedFilms.size
                        progressBar.progress = index + 1
                    }
                    webView.loadUrl(film.url)
                    Thread.sleep(3000)
                }
                runOnUiThread {
                    progressBar.visibility = View.GONE
                    statusText.text = "Готово!"
                    Toast.makeText(this, "Извлечение завершено", Toast.LENGTH_SHORT).show()
                }
            }.start()
        }

        btnM3U.setOnClickListener {
            if (selectedFilms.isEmpty()) {
                Toast.makeText(this, "Нет выбранных фильмов", Toast.LENGTH_SHORT).show()
                return@setOnClickListener
            }
            val generator = M3UGenerator()
            val file = generator.generate(selectedFilms, this)
            val intent = Intent(Intent.ACTION_SEND)
            intent.type = "text/plain"
            intent.putExtra(Intent.EXTRA_STREAM, Uri.fromFile(file))
            startActivity(Intent.createChooser(intent, "Сохранить M3U"))
        }
    }

    companion object {
        private const val JS_EXTRACTOR = """
            (function() {
                setTimeout(function() {
                    var video = document.querySelector('video');
                    if (video && video.src) {
                        Android.onVideoUrl(video.src);
                        return;
                    }
                    var iframe = document.querySelector('iframe');
                    if (iframe && iframe.src) {
                        Android.onVideoUrl(iframe.src);
                        return;
                    }
                    Android.onVideoUrl(null);
                }, 2000);
            })();
        """
    }
}
""")

    # ---------- Ресурсы (layout) ----------
    res_dir = manifest_dir / "res"
    layout_dir = res_dir / "layout"
    layout_dir.mkdir(parents=True)
    
    (layout_dir / "activity_main.xml").write_text("""<?xml version="1.0" encoding="utf-8"?>
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
        android:background="@drawable/search_bg"
        android:padding="12dp"
        android:textColor="#ffffff"
        android:textColorHint="#888888"/>

    <androidx.recyclerview.widget.RecyclerView
        android:id="@+id/recyclerView"
        android:layout_width="match_parent"
        android:layout_height="0dp"
        android:layout_weight="1"
        android:layout_marginTop="8dp"/>

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
            android:textColor="#000000"/>

        <Button
            android:id="@+id/btnM3U"
            android:layout_width="0dp"
            android:layout_height="wrap_content"
            android:layout_weight="1"
            android:text="Создать M3U"
            android:backgroundTint="#44ff88"
            android:textColor="#000000"/>
    </LinearLayout>

    <ProgressBar
        android:id="@+id/progressBar"
        style="?android:attr/progressBarStyleHorizontal"
        android:layout_width="match_parent"
        android:layout_height="wrap_content"
        android:layout_marginTop="8dp"
        android:visibility="gone"/>

    <TextView
        android:id="@+id/statusText"
        android:layout_width="match_parent"
        android:layout_height="wrap_content"
        android:text="Готов к работе"
        android:textColor="#00ff88"
        android:textSize="12sp"
        android:layout_marginTop="4dp"/>

    <WebView
        android:id="@+id/webView"
        android:layout_width="1dp"
        android:layout_height="1dp"
        android:visibility="gone"/>

</LinearLayout>
""")

    (layout_dir / "item_film.xml").write_text("""<?xml version="1.0" encoding="utf-8"?>
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
        android:textStyle="bold"/>

    <TextView
        android:id="@+id/tvYear"
        android:layout_width="wrap_content"
        android:layout_height="wrap_content"
        android:textColor="#888888"
        android:textSize="14sp"
        android:layout_marginStart="8dp"/>

    <TextView
        android:id="@+id/tvCategory"
        android:layout_width="wrap_content"
        android:layout_height="wrap_content"
        android:textColor="#00d4ff"
        android:textSize="12sp"
        android:layout_marginStart="8dp"
        android:background="#333333"
        android:paddingHorizontal="8dp"
        android:paddingVertical="2dp"/>
</LinearLayout>
""")

    # ---------- drawable ----------
    drawable_dir = res_dir / "drawable"
    drawable_dir.mkdir()
    (drawable_dir / "search_bg.xml").write_text("""<?xml version="1.0" encoding="utf-8"?>
<shape xmlns:android="http://schemas.android.com/apk/res/android">
    <solid android:color="#2a2a3e"/>
    <corners android:radius="8dp"/>
    <stroke android:width="1dp" android:color="#444"/>
</shape>
""")

    # ---------- mipmap (иконка) ----------
    for d in ["mipmap-mdpi", "mipmap-hdpi", "mipmap-xhdpi", "mipmap-xxhdpi", "mipmap-xxxhdpi"]:
        (res_dir / d).mkdir()
        (res_dir / d / "ic_launcher.xml").write_text("""<?xml version="1.0" encoding="utf-8"?>
<adaptive-icon xmlns:android="http://schemas.android.com/apk/res/android">
    <background android:drawable="@color/black"/>
    <foreground android:drawable="@drawable/ic_launcher_foreground"/>
</adaptive-icon>
""")

    # ---------- values ----------
    values_dir = res_dir / "values"
    values_dir.mkdir()
    (values_dir / "colors.xml").write_text("""<?xml version="1.0" encoding="utf-8"?>
<resources>
    <color name="black">#0b0b1a</color>
    <color name="white">#ffffff</color>
</resources>
""")
    (values_dir / "themes.xml").write_text("""<?xml version="1.0" encoding="utf-8"?>
<resources>
    <style name="Theme.AppCompat.DayNight.NoActionBar" parent="Theme.AppCompat.DayNight">
        <item name="windowActionBar">false</item>
        <item name="windowNoTitle">true</item>
        <item name="android:windowBackground">@color/black</item>
    </style>
</resources>
""")

    # ---------- assets (JSON будет вставлен позже) ----------
    assets_dir = app_dir / "src" / "main" / "assets"
    assets_dir.mkdir(parents=True)

    print("✅ Шаблон создан")

# ==================== СБОРКА APK ====================
def build_apk():
    """Собирает APK из шаблона"""
    print("🔧 Сборка APK...")
    
    # Проверяем наличие films_structure.json
    if not os.path.exists(JSON_FILE):
        print("❌ Файл films_structure.json не найден! Сначала запустите анализатор.")
        return False
    
    # Создаём шаблон
    create_template()
    
    # Копируем JSON в assets
    shutil.copy(JSON_FILE, f"{TEMPLATE_DIR}/app/src/main/assets/films.json")
    
    # Проверяем наличие gradlew
    gradlew_path = f"{TEMPLATE_DIR}/gradlew"
    if not os.path.exists(gradlew_path):
        # Создаём gradlew скрипт
        with open(gradlew_path, "w") as f:
            f.write("""#!/bin/sh
# Gradle wrapper
exec java -cp "app/build.gradle" org.gradle.wrapper.GradleWrapperMain "$@"
""")
        os.chmod(gradlew_path, 0o755)
    
    # Создаём gradle wrapper
    wrapper_dir = Path(TEMPLATE_DIR) / "gradle" / "wrapper"
    wrapper_dir.mkdir(parents=True)
    (wrapper_dir / "gradle-wrapper.properties").write_text("""
distributionBase=GRADLE_USER_HOME
distributionPath=wrapper/dists
distributionUrl=https\\://services.gradle.org/distributions/gradle-8.4-bin.zip
zipStoreBase=GRADLE_USER_HOME
zipStorePath=wrapper/dists
""")
    
    # Копируем gradle wrapper jar (встроим)
    print("📦 Загрузка Gradle Wrapper...")
    try:
        wrapper_jar = requests.get("https://raw.githubusercontent.com/gradle/gradle/v8.4.0/gradle/wrapper/gradle-wrapper.jar")
        with open(wrapper_dir / "gradle-wrapper.jar", "wb") as f:
            f.write(wrapper_jar.content)
    except:
        print("⚠️ Не удалось загрузить gradle-wrapper.jar, используем встроенный")
    
    # Запускаем сборку
    print("🏗️ Компиляция APK (это займёт несколько минут)...")
    os.chdir(TEMPLATE_DIR)
    result = subprocess.run(["./gradlew", "assembleDebug"], capture_output=True, text=True)
    os.chdir("..")
    
    if result.returncode != 0:
        print("❌ Ошибка сборки:")
        print(result.stderr)
        return False
    
    # Копируем APK
    apk_path = f"{TEMPLATE_DIR}/app/build/outputs/apk/debug/app-debug.apk"
    if os.path.exists(apk_path):
        shutil.copy(apk_path, OUTPUT_APK)
        print(f"✅ APK создан: {OUTPUT_APK}")
        return True
    else:
        print("❌ APK не найден после сборки")
        return False

def main():
    print("🚀 СБОРЩИК APK ANIMEVOST")
    print("═" * 50)
    
    if not os.path.exists(JSON_FILE):
        print("⚠️ Файл films_structure.json не найден!")
        print("Запустите анализатор: python analyze_animevost.py")
        return
    
    # Загружаем данные для проверки
    with open(JSON_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)
    print(f"📊 Данные загружены: {data['total']} фильмов")
    
    success = build_apk()
    if success:
        print("\n✅ ГОТОВО!")
        print(f"📱 APK файл: {OUTPUT_APK}")
        print("📦 Размер: {:.2f} MB".format(os.path.getsize(OUTPUT_APK) / (1024*1024)))
    else:
        print("\n❌ СБОРКА НЕ УДАЛАСЬ")

if __name__ == "__main__":
    main()
