#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import sys
import json
import time
import shutil
import subprocess
import requests
import re
from pathlib import Path
from datetime import datetime
from urllib.parse import urljoin

try:
    from bs4 import BeautifulSoup
except ImportError:
    subprocess.check_call([sys.executable, "-m", "pip", "install", "-q", "beautifulsoup4", "lxml", "requests"])
    from bs4 import BeautifulSoup

BASE_URL = "https://v13.vost.pw"
CATEGORY_URL = "/tip/polnometrazhnyy-film/"
OUTPUT_DIR = Path("site_dump")
JSON_FILE = OUTPUT_DIR / "films.json"
TEMPLATE_DIR = Path("android_template")
OUTPUT_APK = "animevost_app.apk"
MAX_PAGES = 50
REQUEST_DELAY = 0.3

class FilmParser:
    def __init__(self):
        OUTPUT_DIR.mkdir(exist_ok=True)
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8"
        })
        self.films = []

    def fetch_page(self, url):
        try:
            resp = self.session.get(url, timeout=15)
            resp.raise_for_status()
            return resp.text
        except Exception as e:
            print(f"  ❌ Ошибка загрузки {url}: {e}")
            return None

    def parse_page(self, html, page_num):
        soup = BeautifulSoup(html, "lxml")
        articles = soup.find_all("article", class_="post")
        if not articles:
            return []

        page_films = []
        for article in articles:
            a_tag = article.find("a", href=re.compile(r"/\d+-.*\.html$"))
            if not a_tag or not a_tag.get("href"):
                continue
            film_url = urljoin(BASE_URL, a_tag["href"])
            id_match = re.search(r"/(\d+)-", a_tag["href"])
            film_id = id_match.group(1) if id_match else "0"
            h2 = article.find("h2")
            title = h2.text.strip() if h2 else "Без названия"
            year_tag = article.find("a", href=re.compile(r"/god/\d{4}/"))
            year = year_tag.text.strip() if year_tag else "неизвестно"
            style = article.get("style", "")
            poster_match = re.search(r"url\(['\"]?(.*?)['\"]?\)", style)
            poster = urljoin(BASE_URL, poster_match.group(1)) if poster_match else ""
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
        print("🚀 ЭТАП 1: Парсинг сайта (до 50 страниц)")
        print("═" * 60)
        for page in range(1, MAX_PAGES + 1):
            url = urljoin(BASE_URL, CATEGORY_URL) if page == 1 else urljoin(BASE_URL, f"{CATEGORY_URL}page/{page}/")
            print(f"📄 Страница {page}...", end=" ")
            html = self.fetch_page(url)
            if not html:
                print("⏹ Ошибка или конец.")
                break
            films = self.parse_page(html, page)
            if not films:
                print("ℹ️ Нет фильмов. Конец пагинации.")
                break
            self.films.extend(films)
            print(f"✅ +{len(films)} (Всего: {len(self.films)})")
            soup = BeautifulSoup(html, "lxml")
            next_page_pattern = f"{CATEGORY_URL}page/{page+1}/"
            if not soup.find("a", href=re.compile(re.escape(next_page_pattern))):
                print("🏁 Достигнут конец пагинации.")
                break
            time.sleep(REQUEST_DELAY)
        result = {
            "timestamp": datetime.now().isoformat(),
            "total": len(self.films),
            "films": self.films
        }
        with open(JSON_FILE, "w", encoding="utf-8") as f:
            json.dump(result, f, indent=2, ensure_ascii=False)
        print(f"\n💾 Данные сохранены: {JSON_FILE} ({len(self.films)} фильмов)")
        return len(self.films) > 0

class APKBuilder:
    def __init__(self):
        self.project_dir = TEMPLATE_DIR

    def create_template(self):
        print("📱 ЭТАП 2: Генерация Android-шаблона...")
        if self.project_dir.exists():
            shutil.rmtree(self.project_dir)
        app_dir = self.project_dir / "app" / "src" / "main"
        (app_dir / "java" / "com" / "example" / "animevost").mkdir(parents=True)
        (app_dir / "res" / "layout").mkdir(parents=True)
        (app_dir / "res" / "drawable").mkdir(parents=True)
        (app_dir / "res" / "values").mkdir(parents=True)
        (app_dir / "assets").mkdir(parents=True)

        (self.project_dir / "build.gradle").write_text("""
buildscript {
    repositories { google(); mavenCentral() }
    dependencies { classpath 'com.android.tools.build:gradle:8.2.0' }
}
""")
        (self.project_dir / "settings.gradle").write_text("""
pluginManagement { repositories { google(); mavenCentral(); gradlePluginPortal() } }
dependencyResolutionManagement { repositories { google(); mavenCentral() } }
rootProject.name = "AnimeVost"
include ':app'
""")
        (app_dir.parent / "build.gradle").write_text("""
plugins { id 'com.android.application' }
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
        # Исправленный блок MainActivity.kt с \x22\x22\x22 вместо """
        (app_dir / "java" / "com" / "example" / "animevost" / "MainActivity.kt").write_text("""
package com.example.animevost
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
        private const val JS_EXTRACTOR = \x22\x22\x22
            (function() {
                setTimeout(function() {
                    var video = document.querySelector('video');
                    if (video && video.src) { Android.onVideoUrl(video.src); return; }
                    var iframe = document.querySelector('iframe');
                    if (iframe && iframe.src) { Android.onVideoUrl(iframe.src); return; }
                    Android.onVideoUrl(null);
                }, 2000);
            })();
        \x22\x22\x22
    }
}
""")
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
        (app_dir / "res" / "drawable" / "search_bg.xml").write_text("""<?xml version="1.0" encoding="utf-8"?>
<shape xmlns:android="http://schemas.android.com/apk/res/android">
    <solid android:color="#2a2a3e"/><corners android:radius="8dp"/><stroke android:width="1dp" android:color="#444"/>
</shape>
""")
        (app_dir / "res" / "values" / "colors.xml").write_text("""<?xml version="1.0" encoding="utf-8"?><resources><color name="black">#0b0b1a</color></resources>""")
        (app_dir / "res" / "values" / "themes.xml").write_text("""<?xml version="1.0" encoding="utf-8"?>
<resources><style name="Theme.AppCompat.DayNight.NoActionBar" parent="Theme.AppCompat.DayNight">
    <item name="windowActionBar">false</item><item name="windowNoTitle">true</item>
    <item name="android:windowBackground">@color/black</item>
</style></resources>
""")
        print("✅ Шаблон создан")

    def setup_gradle(self):
        print("📦 Настройка Gradle Wrapper...")
        wrapper_dir = self.project_dir / "gradle" / "wrapper"
        wrapper_dir.mkdir(parents=True)
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
        (wrapper_dir / "gradle-wrapper.properties").write_text("""
distributionBase=GRADLE_USER_HOME
distributionPath=wrapper/dists
distributionUrl=https\\://services.gradle.org/distributions/gradle-8.4-bin.zip
zipStoreBase=GRADLE_USER_HOME
zipStorePath=wrapper/dists
""")
        gradlew_path = self.project_dir / "gradlew"
        gradlew_path.write_text("""#!/bin/sh
APP_HOME=$(cd "$(dirname "$0")" && pwd)
exec java -classpath "$APP_HOME/gradle/wrapper/gradle-wrapper.jar" org.gradle.wrapper.GradleWrapperMain "$@"
""")
        os.chmod(gradlew_path, 0o755)
        return True

    def build(self):
        print("🏗️ ЭТАП 3: Компиляция APK (может занять 3-5 минут)...")
        shutil.copy(JSON_FILE, self.project_dir / "app" / "src" / "main" / "assets" / "films.json")
        if not self.setup_gradle():
            return False
        os.chdir(self.project_dir)
        try:
            subprocess.run(["./gradlew", "assembleDebug"], capture_output=True, text=True, check=True)
        except subprocess.CalledProcessError as e:
            print("❌ Ошибка сборки Gradle:")
            print(e.stderr)
            os.chdir("..")
            return False
        finally:
            os.chdir("..")
        apk_path = self.project_dir / "app" / "build" / "outputs" / "apk" / "debug" / "app-debug.apk"
        if apk_path.exists():
            shutil.copy(apk_path, OUTPUT_APK)
            print(f"✅ APK успешно создан: {OUTPUT_APK}")
            print(f"📦 Размер: {os.path.getsize(OUTPUT_APK) / (1024*1024):.2f} MB")
            return True
        return False

def main():
    print("=" * 60)
    print(" 🎬 UNIFIED ANIMEVOST PARSER & APK BUILDER v2.0")
    print("=" * 60)
    try:
        subprocess.run(["java", "-version"], capture_output=True, check=True)
    except (FileNotFoundError, subprocess.CalledProcessError):
        print("❌ ОШИБКА: Java не найдена в системе! Установите JDK 17+ для сборки APK.")
        sys.exit(1)
    parser = FilmParser()
    if not parser.run():
        print("❌ Не удалось собрать данные. Завершение.")
        sys.exit(1)
    builder = APKBuilder()
    if builder.build():
        print("\n🎉 ВСЁ ГОТОВО! Установите animevost_app.apk на Android-устройство.")
    else:
        print("\n❌ Сборка APK не удалась. Проверьте логи выше.")

if __name__ == "__main__":
    main()
