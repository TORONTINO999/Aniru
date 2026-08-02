#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Единый скрипт: парсинг сайта + сборка APK
Запуск: python main.py
Результат: animevost_app.apk
"""

import re
import json
import time
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin
from pathlib import Path
from datetime import datetime
import shutil
import subprocess
import os
import sys

# ==================== КОНФИГУРАЦИЯ ====================
BASE_URL = "https://v13.vost.pw"
CATEGORY_URL = "/tip/polnometrazhnyy-film/"
OUTPUT_DIR = "site_dump"
REQUEST_DELAY = 0.5
MAX_PAGES = 50
JSON_FILE = "films.json"          # Имя внутри assets
TEMPLATE_DIR = "android_template"
OUTPUT_APK = "animevost_app.apk"

# ==================== ПАРСИНГ ====================
class FilmParser:
    def __init__(self):
        self.output_dir = Path(OUTPUT_DIR)
        self.output_dir.mkdir(exist_ok=True)
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        })
        self.films = []

    def fetch_page(self, url):
        try:
            resp = self.session.get(url, timeout=10)
            resp.raise_for_status()
            return resp.text
        except Exception as e:
            print(f"  ❌ Ошибка: {e}")
            return None

    def parse_films_from_page(self, html, page_num):
        soup = BeautifulSoup(html, "lxml")
        articles = soup.select("article.post")
        if not articles:
            print(f"  ⚠️ На странице {page_num} нет фильмов.")
            return []

        page_films = []
        for article in articles:
            a = article.select_one("span a")
            if not a:
                continue
            href = a.get("href")
            if not href:
                continue
            film_url = urljoin(BASE_URL, href)

            title_elem = article.select_one("h2")
            title = title_elem.text.strip() if title_elem else "Без названия"

            year_elem = article.select_one("a[href*='/god/']")
            year = year_elem.text.strip() if year_elem else "неизвестно"

            style = article.get("style", "")
            poster_match = re.search(r"url\(['\"]?(.*?)['\"]?\)", style)
            poster = poster_match.group(1) if poster_match else ""
            if poster and not poster.startswith("http"):
                poster = urljoin(BASE_URL, poster)

            id_match = re.search(r"/(\d+)-", href)
            film_id = id_match.group(1) if id_match else None

            film_data = {
                "id": film_id,
                "title": title,
                "year": year,
                "poster": poster,
                "url": film_url,
                "category": "polnometrazhnyy-film"
            }

            if not any(f["url"] == film_url for f in self.films):
                page_films.append(film_data)

        return page_films

    def run(self):
        print("🚀 Запуск парсинга (полнометражные фильмы, до 50 страниц)")
        print("═" * 50)

        for page in range(1, MAX_PAGES + 1):
            print(f"\n📄 Страница {page}...")

            if page == 1:
                url = urljoin(BASE_URL, CATEGORY_URL)
            else:
                url = urljoin(BASE_URL, f"{CATEGORY_URL}page/{page}/")

            html = self.fetch_page(url)
            if not html:
                print(f"  ⏹ Достигнут конец или ошибка. Останавливаемся на странице {page}.")
                break

            films = self.parse_films_from_page(html, page)
            if not films:
                print(f"  ℹ️ На странице {page} нет фильмов. Возможно, это конец.")
                break

            self.films.extend(films)
            print(f"  ✅ Найдено {len(films)} фильмов (всего {len(self.films)})")

            # Проверяем наличие следующей страницы
            if page == 1:
                soup = BeautifulSoup(html, "lxml")
                pager = soup.select_one(".pager")
                if not pager or not pager.find("a", href=re.compile(r"/page/2/")):
                    print("  ℹ️ Только одна страница.")
                    break
            else:
                soup = BeautifulSoup(html, "lxml")
                if not soup.select_one(f"a[href*='{CATEGORY_URL}page/{page+1}/']"):
                    print(f"  🏁 Достигнут конец пагинации на странице {page}.")
                    break

            time.sleep(REQUEST_DELAY)

        # Сохраняем результат
        result = {
            "timestamp": datetime.now().isoformat(),
            "total": len(self.films),
            "films": self.films
        }
        films_file = self.output_dir / JSON_FILE
        with open(films_file, "w", encoding="utf-8") as f:
            json.dump(result, f, indent=2, ensure_ascii=False)

        print("\n" + "═" * 50)
        print(f"✅ Парсинг завершён. Собрано {len(self.films)} фильмов.")
        print(f"💾 Файл сохранён: {films_file}")
        return films_file

# ==================== СБОРКА APK ====================
def create_template():
    """Создаёт минимальный Android-проект"""
    print("📱 Создание шаблона Android-приложения...")
    project_dir = Path(TEMPLATE_DIR)
    if project_dir.exists():
        shutil.rmtree(project_dir)
    project_dir.mkdir(parents=True)

    # build.gradle (проектный)
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

    # settings.gradle
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

    # app/build.gradle
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

    # AndroidManifest.xml
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

    # Kotlin исходники
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

    # Ресурсы (layout)
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

    # drawable
    drawable_dir = res_dir / "drawable"
    drawable_dir.mkdir()
    (drawable_dir / "search_bg.xml").write_text("""<?xml version="1.0" encoding="utf-8"?>
<shape xmlns:android="http://schemas.android.com/apk/res/android">
    <solid android:color="#2a2a3e"/>
    <corners android:radius="8dp"/>
    <stroke android:width="1dp" android:color="#444"/>
</shape>
""")

    # mipmap
    for d in ["mipmap-mdpi", "mipmap-hdpi", "mipmap-xhdpi", "mipmap-xxhdpi", "mipmap-xxxhdpi"]:
        (res_dir / d).mkdir()
        (res_dir / d / "ic_launcher.xml").write_text("""<?xml version="1.0" encoding="utf-8"?>
<adaptive-icon xmlns:android="http://schemas.android.com/apk/res/android">
    <background android:drawable="@color/black"/>
    <foreground android:drawable="@drawable/ic_launcher_foreground"/>
</adaptive-icon>
""")

    # values
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

    # assets (позже скопируем JSON)
    assets_dir = app_dir / "src" / "main" / "assets"
    assets_dir.mkdir(parents=True)

    print("✅ Шаблон создан")


def build_apk(json_path):
    """Собирает APK, используя JSON из json_path"""
    print("🔧 Сборка APK...")

    if not os.path.exists(json_path):
        print(f"❌ Файл {json_path} не найден!")
        return False

    # Создаём шаблон
    create_template()

    # Копируем JSON в assets
    shutil.copy(json_path, f"{TEMPLATE_DIR}/app/src/main/assets/{JSON_FILE}")

    # Создаём gradlew
    gradlew_path = f"{TEMPLATE_DIR}/gradlew"
    if not os.path.exists(gradlew_path):
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

    apk_path = f"{TEMPLATE_DIR}/app/build/outputs/apk/debug/app-debug.apk"
    if os.path.exists(apk_path):
        shutil.copy(apk_path, OUTPUT_APK)
        print(f"✅ APK создан: {OUTPUT_APK}")
        return True
    else:
        print("❌ APK не найден после сборки")
        return False


# ==================== ГЛАВНАЯ ФУНКЦИЯ ====================
def main():
    print("🚀 ЗАПУСК ЕДИНОГО СКРИПТА")
    print("═" * 60)

    # 1. Парсинг
    parser = FilmParser()
    json_path = parser.run()

    if not json_path or not os.path.exists(json_path):
        print("❌ Парсинг не дал результата. Сборка отменена.")
        sys.exit(1)

    # 2. Сборка APK
    success = build_apk(json_path)
    if success:
        print("\n✅ ГОТОВО!")
        print(f"📱 APK файл: {OUTPUT_APK}")
        print("📦 Размер: {:.2f} MB".format(os.path.getsize(OUTPUT_APK) / (1024 * 1024)))
    else:
        print("\n❌ СБОРКА НЕ УДАЛАСЬ")
        sys.exit(1)


if __name__ == "__main__":
    main()
