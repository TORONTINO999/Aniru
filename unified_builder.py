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

# ==================== КОНФИГУРАЦИЯ ====================
BASE_URL = "https://v13.vost.pw"
CATEGORY_URL = "/tip/polnometrazhnyy-film/"
OUTPUT_DIR = Path("site_dump")
JSON_FILE = OUTPUT_DIR / "films.json"
TEMPLATE_DIR = Path("android_template")
OUTPUT_APK = "animevost_app.apk"
MAX_PAGES = 50
REQUEST_DELAY = 0.3

# ==================== ЧАСТЬ 1: ПАРСИНГ ====================
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

# ==================== ЧАСТЬ 2: СБОРКА APK ====================
class APKBuilder:
    def __init__(self):
        self.project_dir = TEMPLATE_DIR

    def build(self):
        print("\n📱 ЭТАП 2: Копирование Android-шаблона...")
        
        # Проверяем, существует ли шаблон
        if not self.project_dir.exists():
            print("❌ ОШИБКА: Папка android_template не найдена!")
            print("   Запустите сначала generate_template.py")
            return False
        
        # Копируем шаблон во временную папку для сборки
        build_dir = Path("android_build")
        if build_dir.exists():
            shutil.rmtree(build_dir)
        shutil.copytree(self.project_dir, build_dir)
        
        # Кладём JSON в assets
        assets_dir = build_dir / "app" / "src" / "main" / "assets"
        assets_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy(JSON_FILE, assets_dir / "films.json")
        
        print("📦 Настройка Gradle Wrapper...")
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
        
        # Создаём gradle-wrapper.properties
        (wrapper_dir / "gradle-wrapper.properties").write_text("""
distributionBase=GRADLE_USER_HOME
distributionPath=wrapper/dists
distributionUrl=https\\://services.gradle.org/distributions/gradle-8.4-bin.zip
zipStoreBase=GRADLE_USER_HOME
zipStorePath=wrapper/dists
""")
        
        # Создаём gradlew
        gradlew_path = build_dir / "gradlew"
        gradlew_path.write_text("""#!/bin/sh
APP_HOME=$(cd "$(dirname "$0")" && pwd)
exec java -classpath "$APP_HOME/gradle/wrapper/gradle-wrapper.jar" org.gradle.wrapper.GradleWrapperMain "$@"
""")
        os.chmod(gradlew_path, 0o755)
        
        # Сборка
        print("🏗️ ЭТАП 3: Компиляция APK (может занять 3-5 минут)...")
        os.chdir(build_dir)
        try:
            result = subprocess.run(
                ["./gradlew", "assembleDebug"],
                capture_output=True,
                text=True,
                check=True
            )
        except subprocess.CalledProcessError as e:
            print("❌ Ошибка сборки Gradle:")
            print(e.stderr)
            os.chdir("..")
            return False
        finally:
            os.chdir("..")
        
        apk_path = build_dir / "app" / "build" / "outputs" / "apk" / "debug" / "app-debug.apk"
        if apk_path.exists():
            shutil.copy(apk_path, OUTPUT_APK)
            size_mb = os.path.getsize(OUTPUT_APK) / (1024 * 1024)
            print(f"✅ APK успешно создан: {OUTPUT_APK} ({size_mb:.2f} MB)")
            return True
        return False

# ==================== ГЛАВНЫЙ ЗАПУСК ====================
def main():
    print("=" * 60)
    print(" 🎬 UNIFIED ANIMEVOST PARSER & APK BUILDER v3.0")
    print("=" * 60)
    
    # Проверка Java
    try:
        subprocess.run(["java", "-version"], capture_output=True, check=True)
    except (FileNotFoundError, subprocess.CalledProcessError):
        print("❌ ОШИБКА: Java не найдена в системе! Установите JDK 17+ для сборки APK.")
        sys.exit(1)
    
    # Шаг 1: Парсинг
    parser = FilmParser()
    if not parser.run():
        print("❌ Не удалось собрать данные. Завершение.")
        sys.exit(1)
    
    # Шаг 2: Сборка
    builder = APKBuilder()
    if builder.build():
        print("\n🎉 ВСЁ ГОТОВО! Установите animevost_app.apk на Android-устройство.")
    else:
        print("\n❌ Сборка APK не удалась. Проверьте логи выше.")
        sys.exit(1)

if __name__ == "__main__":
    main()
