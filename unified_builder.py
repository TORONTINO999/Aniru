#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
ЕДИНЫЙ СКРИПТ: Парсинг AnimeVost + Сборка Android APK
Адаптированная логика из UserScript
"""

import os
import sys
import re
import json
import time
import shutil
import subprocess
import requests
from pathlib import Path
from datetime import datetime
from urllib.parse import urljoin, urlparse

# ==================== КОНФИГУРАЦИЯ ====================
BASE_URL = "https://v13.vost.pw"
CATEGORY_URL = "/tip/polnometrazhnyy-film/"
OUTPUT_DIR = Path("site_dump")
JSON_FILE = OUTPUT_DIR / "films.json"
TEMPLATE_DIR = Path("android_template")
OUTPUT_APK = "animevost_app.apk"
MAX_PAGES = 50
REQUEST_DELAY = 0.5

# ==================== ЧАСТЬ 1: ПАРСИНГ ====================
class FilmParser:
    def __init__(self):
        self.output_dir = OUTPUT_DIR
        self.output_dir.mkdir(exist_ok=True)
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
            "Accept-Language": "ru-RU,ru;q=0.9,en;q=0.8"
        })
        self.films = []

    def fetch_page(self, url):
        try:
            resp = self.session.get(url, timeout=15)
            resp.raise_for_status()
            return resp.text
        except Exception as e:
            print(f"  ❌ Ошибка: {e}")
            return None

    def parse_films_from_page(self, html, page_num):
        """Парсит карточки фильмов на странице (как в UserScript)"""
        if not html:
            return []
        
        # Ищем article.post (как в скрипте)
        articles = re.findall(r'<article\s+class="post"[^>]*>(.*?)</article>', html, re.DOTALL)
        
        if not articles:
            print(f"  ⚠️ На странице {page_num} нет фильмов.")
            return []

        page_films = []
        for article_html in articles:
            # 1. Ссылка на фильм (как в скрипте: span a)
            href_match = re.search(r'<span[^>]*>.*?<a\s+href="([^"]+)"', article_html, re.DOTALL)
            if not href_match:
                # Альтернативный поиск
                href_match = re.search(r'<a\s+href="([^"]*' + CATEGORY_URL + r'[^"]+\.html)"', article_html)
                if not href_match:
                    continue
            href = href_match.group(1)
            film_url = urljoin(BASE_URL, href)
            
            # 2. ID фильма
            id_match = re.search(r"/(\d+)-", href)
            film_id = id_match.group(1) if id_match else "0"
            
            # 3. Название (из h2)
            title_match = re.search(r'<h2>(.*?)</h2>', article_html, re.DOTALL)
            title = title_match.group(1).strip() if title_match else "Без названия"
            title = re.sub(r'<[^>]+>', '', title)
            # Очистка от лишних пробелов
            title = re.sub(r'\s+', ' ', title).strip()
            
            # 4. Год (из тега a с /god/)
            year_match = re.search(r'<a\s+href="[^"]*/god/(\d{4})/[^"]*">', article_html)
            year = year_match.group(1) if year_match else "неизвестно"
            
            # 5. Постер (из style)
            style_match = re.search(r'style="[^"]*background-image:\s*url\([\'"]?([^\'"\)]+)[\'"]?\)', article_html, re.IGNORECASE)
            poster = style_match.group(1) if style_match else ""
            if poster and not poster.startswith("http"):
                poster = urljoin(BASE_URL, poster)
            
            if not any(f["url"] == film_url for f in self.films):
                page_films.append({
                    "id": film_id,
                    "title": title,
                    "year": year,
                    "poster": poster,
                    "url": film_url,
                    "category": "polnometrazhnyy-film"
                })

        return page_films

    def run(self):
        print("🚀 ЭТАП 1: Парсинг сайта")
        print("═" * 60)

        for page in range(1, MAX_PAGES + 1):
            print(f"📄 Страница {page}...", end=" ")

            if page == 1:
                url = urljoin(BASE_URL, CATEGORY_URL)
            else:
                url = urljoin(BASE_URL, f"{CATEGORY_URL}page/{page}/")

            html = self.fetch_page(url)
            if not html:
                print("⏹ Ошибка.")
                break

            films = self.parse_films_from_page(html, page)
            if not films:
                print("ℹ️ Нет фильмов. Конец.")
                break

            self.films.extend(films)
            print(f"✅ +{len(films)} (Всего: {len(self.films)})")

            # Проверка следующей страницы (как в скрипте)
            if not re.search(rf'href="[^"]*{CATEGORY_URL}page/{page+1}/', html):
                print("🏁 Достигнут конец пагинации.")
                break

            time.sleep(REQUEST_DELAY)

        # Сохраняем результат
        result = {
            "timestamp": datetime.now().isoformat(),
            "total": len(self.films),
            "films": self.films
        }

        with open(JSON_FILE, "w", encoding="utf-8") as f:
            json.dump(result, f, indent=2, ensure_ascii=False)

        print(f"\n💾 Сохранено: {JSON_FILE} ({len(self.films)} фильмов)")
        return len(self.films) > 0

# ==================== ЧАСТЬ 2: ГЕНЕРАЦИЯ ШАБЛОНА ====================
class TemplateGenerator:
    def __init__(self):
        self.project_dir = TEMPLATE_DIR

    def create_template(self):
        print("\n📱 ЭТАП 2: Генерация Android-шаблона...")
        if self.project_dir.exists():
            shutil.rmtree(self.project_dir)
        
        app_dir = self.project_dir / "app" / "src" / "main"
        (app_dir / "java" / "com" / "example" / "animevost").mkdir(parents=True)
        (app_dir / "res" / "layout").mkdir(parents=True)
        (app_dir / "res" / "drawable").mkdir(parents=True)
        (app_dir / "res" / "values").mkdir(parents=True)
        (app_dir / "assets").mkdir(parents=True)

        # build.gradle (Project)
        (self.project_dir / "build.gradle").write_text("""buildscript {
    repositories { google(); mavenCentral() }
    dependencies { classpath 'com.android.tools.build:gradle:8.2.0' }
}
""")
        # settings.gradle
        (self.project_dir / "settings.gradle").write_text("""pluginManagement { repositories { google(); mavenCentral(); gradlePluginPortal() } }
dependencyResolutionManagement { repositories { google(); mavenCentral() } }
rootProject.name = "AnimeVost"
include ':app'
""")
        # app/build.gradle
        (app_dir.parent / "build.gradle").write_text("""plugins { id 'com.android.application' }
android {
    namespace 'com.example.animevost'
    compileSdk 34
    defaultConfig {
        applicationId "com.example.animevost"
        minSdk 21; targetSdk 34; versionCode 1; versionName "1.0"
    }
    buildTypes { release { minifyEnabled false } }
    compileOptions { sourceCompatibility JavaVersion.VERSION_1_8; targetCompatibility JavaVersion.VERSION_1_8 }
}
dependencies {
    implementation 'androidx.appcompat:appcompat:1.6.1'
    implementation 'com.google.android.material:material:1.11.0'
    implementation 'androidx.recyclerview:recyclerview:1.3.2'
    implementation 'com.google.code.gson:gson:2.10.1'
}
""")
        # AndroidManifest.xml
        (app_dir / "AndroidManifest.xml").write_text("""<?xml version="1.0" encoding="utf-8"?>
<manifest xmlns:android="http://schemas.android.com/apk/res/android">
    <uses-permission android:name="android.permission.INTERNET" />
    <application android:allowBackup="true" android:label="AnimeVost" 
        android:theme="@style/Theme.AppCompat.DayNight.NoActionBar" android:usesCleartextTraffic="true">
        <activity android:name=".MainActivity" android:exported="true">
            <intent-filter>
                <action android:name="android.intent.action.MAIN" />
                <category android:name="android.intent.category.LAUNCHER" />
            </intent-filter>
        </activity>
    </application>
</manifest>
""")
        # MainActivity.kt
        (app_dir / "java" / "com" / "example" / "animevost" / "MainActivity.kt").write_text("""package com.example.animevost
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

data class Film(val id: String?, val title: String, val year: String, val poster: String, val url: String, val category: String)

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
            allFilms = filmsList.map { Film(it["id"], it["title"]!!, it["year"]!!, it["poster"]!!, it["url"]!!, it["category"]!!) }
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
                        Toast.makeText(this@MainActivity, "Добавлен: ${film.title}", Toast.LENGTH_SHORT).show()
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
                        Toast.makeText(this@MainActivity, "Ссылка найдена!", Toast.LENGTH_SHORT).show()
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
""")
        # res/layout/activity_main.xml
        (app_dir / "res" / "layout" / "activity_main.xml").write_text("""<?xml version="1.0" encoding="utf-8"?>
<LinearLayout xmlns:android="http://schemas.android.com/apk/res/android"
    android:layout_width="match_parent" android:layout_height="match_parent"
    android:orientation="vertical" android:padding="16dp" android:background="#0b0b1a">
    <EditText android:id="@+id/searchEdit" android:layout_width="match_parent" android:layout_height="wrap_content"
        android:hint="Поиск фильма..." android:padding="12dp" android:textColor="#ffffff" android:textColorHint="#888888"
        android:background="@drawable/search_bg"/>
    <androidx.recyclerview.widget.RecyclerView android:id="@+id/recyclerView"
        android:layout_width="match_parent" android:layout_height="0dp" android:layout_weight="1" android:layout_marginTop="8dp"/>
    <LinearLayout android:layout_width="match_parent" android:layout_height="wrap_content" android:orientation="horizontal" android:layout_marginTop="8dp">
        <Button android:id="@+id/btnExtract" android:layout_width="0dp" android:layout_height="wrap_content"
            android:layout_weight="1" android:text="Извлечь ссылки" android:backgroundTint="#00d4ff" android:textColor="#000000"/>
        <Button android:id="@+id/btnM3U" android:layout_width="0dp" android:layout_height="wrap_content"
            android:layout_weight="1" android:text="Создать M3U" android:backgroundTint="#44ff88" android:textColor="#000000"/>
    </LinearLayout>
    <ProgressBar android:id="@+id/progressBar" style="?android:attr/progressBarStyleHorizontal"
        android:layout_width="match_parent" android:layout_height="wrap_content" android:layout_marginTop="8dp" android:visibility="gone"/>
    <TextView android:id="@+id/statusText" android:layout_width="match_parent" android:layout_height="wrap_content"
        android:text="Готов к работе" android:textColor="#00ff88" android:textSize="12sp" android:layout_marginTop="4dp"/>
    <WebView android:id="@+id/webView" android:layout_width="1dp" android:layout_height="1dp" android:visibility="gone"/>
</LinearLayout>
""")
        # res/layout/item_film.xml
        (app_dir / "res" / "layout" / "item_film.xml").write_text("""<?xml version="1.0" encoding="utf-8"?>
<LinearLayout xmlns:android="http://schemas.android.com/apk/res/android"
    android:layout_width="match_parent" android:layout_height="wrap_content"
    android:orientation="horizontal" android:padding="12dp" android:background="#1a1a2e"
    android:layout_marginBottom="4dp" android:clickable="true">
    <TextView android:id="@+id/tvTitle" android:layout_width="0dp" android:layout_height="wrap_content"
        android:layout_weight="1" android:textColor="#ffffff" android:textSize="16sp" android:textStyle="bold"/>
    <TextView android:id="@+id/tvYear" android:layout_width="wrap_content" android:layout_height="wrap_content"
        android:textColor="#888888" android:textSize="14sp" android:layout_marginStart="8dp"/>
</LinearLayout>
""")
        # res/drawable/search_bg.xml
        (app_dir / "res" / "drawable" / "search_bg.xml").write_text("""<?xml version="1.0" encoding="utf-8"?>
<shape xmlns:android="http://schemas.android.com/apk/res/android">
    <solid android:color="#2a2a3e"/><corners android:radius="8dp"/><stroke android:width="1dp" android:color="#444"/>
</shape>
""")
        # res/values/colors.xml
        (app_dir / "res" / "values" / "colors.xml").write_text("""<?xml version="1.0" encoding="utf-8"?><resources><color name="black">#0b0b1a</color></resources>""")
        # res/values/themes.xml
        (app_dir / "res" / "values" / "themes.xml").write_text("""<?xml version="1.0" encoding="utf-8"?>
<resources><style name="Theme.AppCompat.DayNight.NoActionBar" parent="Theme.AppCompat.DayNight">
    <item name="windowActionBar">false</item><item name="windowNoTitle">true</item>
    <item name="android:windowBackground">@color/black</item>
</style></resources>
""")
        print("✅ Шаблон создан")
        return True

# ==================== ЧАСТЬ 3: СБОРКА APK ====================
class APKBuilder:
    def __init__(self):
        self.project_dir = TEMPLATE_DIR

    def build(self):
        print("\n📱 ЭТАП 3: Сборка APK")

        # Проверяем наличие шаблона
        if not self.project_dir.exists():
            print("❌ Шаблон не найден! Создаём...")
            gen = TemplateGenerator()
            if not gen.create_template():
                return False

        # Копируем шаблон в build_dir
        build_dir = Path("android_build")
        if build_dir.exists():
            shutil.rmtree(build_dir)
        shutil.copytree(self.project_dir, build_dir)

        # Кладём JSON в assets
        assets_dir = build_dir / "app" / "src" / "main" / "assets"
        assets_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy(JSON_FILE, assets_dir / "films.json")

        # Настройка Gradle Wrapper
        print("📦 Настройка Gradle...")
        wrapper_dir = build_dir / "gradle" / "wrapper"
        wrapper_dir.mkdir(parents=True, exist_ok=True)

        # Скачиваем gradle-wrapper.jar
        jar_url = "https://raw.githubusercontent.com/gradle/gradle/v8.4.0/gradle/wrapper/gradle-wrapper.jar"
        jar_path = wrapper_dir / "gradle-wrapper.jar"
        if not jar_path.exists():
            try:
                r = requests.get(jar_url, timeout=30)
                r.raise_for_status()
                with open(jar_path, "wb") as f:
                    f.write(r.content)
            except Exception as e:
                print(f"⚠️ Не удалось скачать wrapper.jar: {e}")
                return False

        # gradle-wrapper.properties
        (wrapper_dir / "gradle-wrapper.properties").write_text("""
distributionBase=GRADLE_USER_HOME
distributionPath=wrapper/dists
distributionUrl=https\\://services.gradle.org/distributions/gradle-8.4-bin.zip
zipStoreBase=GRADLE_USER_HOME
zipStorePath=wrapper/dists
""")

        # gradlew
        gradlew_path = build_dir / "gradlew"
        gradlew_path.write_text("""#!/bin/sh
APP_HOME=$(cd "$(dirname "$0")" && pwd)
exec java -classpath "$APP_HOME/gradle/wrapper/gradle-wrapper.jar" org.gradle.wrapper.GradleWrapperMain "$@"
""")
        os.chmod(gradlew_path, 0o755)

        # Сборка APK
        print("🏗️ Компиляция APK (3-5 минут)...")
        os.chdir(build_dir)
        try:
            result = subprocess.run(
                ["./gradlew", "assembleDebug", "--no-daemon"],
                capture_output=True,
                text=True,
                check=True
            )
        except subprocess.CalledProcessError as e:
            print("❌ Ошибка сборки:")
            print(e.stderr[-1000:] if e.stderr else "Нет вывода ошибок")
            os.chdir("..")
            return False
        finally:
            os.chdir("..")

        # Копируем готовый APK
        apk_path = build_dir / "app" / "build" / "outputs" / "apk" / "debug" / "app-debug.apk"
        if apk_path.exists():
            shutil.copy(apk_path, OUTPUT_APK)
            size = os.path.getsize(OUTPUT_APK) / (1024 * 1024)
            print(f"✅ APK создан: {OUTPUT_APK} ({size:.2f} MB)")
            return True
        
        # Если APK не найден, ищем его в других местах
        for apk in build_dir.glob("**/*.apk"):
            if "debug" in str(apk):
                shutil.copy(apk, OUTPUT_APK)
                size = os.path.getsize(OUTPUT_APK) / (1024 * 1024)
                print(f"✅ APK найден и скопирован: {OUTPUT_APK} ({size:.2f} MB)")
                return True
        
        print("❌ APK не найден после сборки")
        return False

# ==================== ГЛАВНАЯ ФУНКЦИЯ ====================
def main():
    print("=" * 60)
    print(" 🎬 ANIMEVOST PARSER & APK BUILDER v4.0")
    print("=" * 60)

    # Проверка Java
    try:
        subprocess.run(["java", "-version"], capture_output=True, check=True)
        print("✅ Java найдена")
    except:
        print("❌ Java не найдена!")
        sys.exit(1)

    # 1. Парсинг
    parser = FilmParser()
    if not parser.run():
        print("❌ Не удалось собрать данные.")
        sys.exit(1)

    # 2. Сборка
    builder = APKBuilder()
    if builder.build():
        print("\n🎉 ГОТОВО! Установите animevost_app.apk на Android-устройство.")
    else:
        print("\n❌ Сборка не удалась.")
        sys.exit(1)

if __name__ == "__main__":
    main()
