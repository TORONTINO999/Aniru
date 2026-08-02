#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
ПОЛНЫЙ АНАЛИЗАТОР САЙТА ANIMEVOST
Скачивает ВСЁ: HTML, CSS, JavaScript, изображения
Анализирует JS-код на наличие API, ключей, методов
Сохраняет полную структуру в JSON для использования в приложении

Запуск: python analyze_animevost.py
Результат: site_dump/ (папка со всеми данными)
"""

import os
import re
import json
import time
import hashlib
import requests
from urllib.parse import urljoin, urlparse
from datetime import datetime
from bs4 import BeautifulSoup
from pathlib import Path
from typing import Dict, List, Set, Optional, Any

# ==================== КОНФИГУРАЦИЯ ====================
BASE_URL = "https://v13.vost.pw"
OUTPUT_DIR = "site_dump"  # Папка для всех данных
MAX_PAGES = 2000
REQUEST_DELAY = 0.5
MAX_DEPTH = 3

# ==================== КЛАСС АНАЛИЗАТОРА ====================
class AnimeVostAnalyzer:
    def __init__(self):
        self.base_url = BASE_URL
        self.output_dir = Path(OUTPUT_DIR)
        self.output_dir.mkdir(exist_ok=True)
        
        # Основные структуры данных
        self.films = []           # Все фильмы
        self.categories = {}      # Категории с фильмами
        self.pages = {}           # Все страницы
        self.scripts = {}         # JS-файлы
        self.styles = {}          # CSS-файлы
        self.api_endpoints = {}   # API-эндпоинты
        self.js_methods = {}      # JS-методы
        self.patterns = {}        # Найденные паттерны
        
        self.visited_urls = set()
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
            "Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7",
            "Accept-Encoding": "gzip, deflate, br",
            "Connection": "keep-alive"
        })

    def fetch_url(self, url: str, binary: bool = False) -> Optional[Any]:
        """Загружает URL с обработкой ошибок"""
        if url in self.visited_urls:
            return None
        
        try:
            response = self.session.get(url, timeout=30)
            response.raise_for_status()
            self.visited_urls.add(url)
            return response.content if binary else response.text
        except Exception as e:
            print(f"  ❌ {e}")
            return None

    def get_absolute_url(self, url: str) -> str:
        """Преобразует в абсолютный URL"""
        if not url:
            return ""
        if url.startswith("//"):
            return "https:" + url
        return urljoin(self.base_url, url)

    def is_internal(self, url: str) -> bool:
        """Проверяет, внутренняя ли ссылка"""
        parsed = urlparse(url)
        return (not parsed.netloc) or self.base_url in parsed.netloc

    # ==================== ПАРСИНГ КАТЕГОРИЙ ====================
    def parse_category(self, category_url: str) -> List[Dict]:
        """Парсит все страницы категории и собирает фильмы"""
        print(f"\n📂 Анализ категории: {category_url}")
        all_films = []
        page = 1
        
        while page <= 100:
            url = category_url if page == 1 else f"{category_url}page/{page}/"
            print(f"  📄 Страница {page}...")
            
            html = self.fetch_url(url)
            if not html:
                break
            
            soup = BeautifulSoup(html, "lxml")
            articles = soup.select("article.post")
            
            if not articles:
                print(f"  ℹ️ Страница {page} пуста – конец")
                break
            
            for article in articles:
                a = article.select_one("span a")
                if not a:
                    continue
                
                href = a.get("href")
                if not href:
                    continue
                
                film_url = self.get_absolute_url(href)
                title = article.select_one("h2").text.strip() if article.select_one("h2") else "Без названия"
                year_elem = article.select_one("a[href*='/god/']")
                year = year_elem.text.strip() if year_elem else "неизвестно"
                
                style = article.get("style", "")
                poster_match = re.search(r"url\(['\"]?(.*?)['\"]?\)", style)
                poster = poster_match.group(1) if poster_match else ""
                if poster and not poster.startswith("http"):
                    poster = self.get_absolute_url(poster)
                
                id_match = re.search(r"/(\d+)-", href)
                film_id = id_match.group(1) if id_match else None
                
                category = category_url.strip("/").split("/")[-1] if category_url else "unknown"
                
                film_data = {
                    "id": film_id,
                    "title": title,
                    "year": year,
                    "poster": poster,
                    "url": film_url,
                    "category": category
                }
                
                # Проверяем дубликаты
                if not any(f["url"] == film_url for f in all_films):
                    all_films.append(film_data)
            
            print(f"  ✅ Найдено {len(articles)} фильмов (всего в категории: {len(all_films)})")
            
            # Проверяем следующую страницу
            if page == 1:
                pager = soup.select_one(".pager")
                if not pager or not pager.find("a", href=re.compile(r"/page/2/")):
                    break
            else:
                if not soup.select_one(f"a[href*='{category_url}page/{page+1}/']"):
                    break
            
            page += 1
            time.sleep(REQUEST_DELAY)
        
        return all_films

    # ==================== АНАЛИЗ СТРАНИЦЫ ====================
    def analyze_page(self, url: str) -> Dict:
        """Анализирует отдельную HTML-страницу"""
        html = self.fetch_url(url)
        if not html:
            return {}
        
        soup = BeautifulSoup(html, "lxml")
        
        analysis = {
            "url": url,
            "title": soup.title.string.strip() if soup.title else "",
            "scripts": [],
            "styles": [],
            "images": [],
            "iframes": [],
            "links": []
        }
        
        # Собираем ресурсы
        for script in soup.find_all("script"):
            src = script.get("src")
            if src:
                analysis["scripts"].append(self.get_absolute_url(src))
        
        for link in soup.find_all("link", rel="stylesheet"):
            href = link.get("href")
            if href:
                analysis["styles"].append(self.get_absolute_url(href))
        
        for img in soup.find_all("img"):
            src = img.get("src")
            if src:
                analysis["images"].append(self.get_absolute_url(src))
        
        for iframe in soup.find_all("iframe"):
            src = iframe.get("src")
            if src:
                analysis["iframes"].append(self.get_absolute_url(src))
        
        for a in soup.find_all("a", href=True):
            href = a.get("href")
            if href and not href.startswith("#"):
                analysis["links"].append(self.get_absolute_url(href))
        
        return analysis

    # ==================== АНАЛИЗ JAVASCRIPT ====================
    def analyze_javascript(self, url: str) -> Dict:
        """Анализирует JavaScript-файл"""
        if url in self.scripts:
            return self.scripts[url]
        
        print(f"  📜 JS: {url}")
        content = self.fetch_url(url)
        if not content:
            return {}
        
        analysis = {
            "url": url,
            "size": len(content),
            "functions": [],
            "api_calls": [],
            "endpoints": [],
            "keys": [],
            "urls": []
        }
        
        # Паттерны для анализа
        patterns = {
            "function": re.compile(r'function\s+([a-zA-Z_$][a-zA-Z0-9_$]*)\s*\('),
            "api": re.compile(r'(/api/|/v1/|/v2/|/get_|/set_|/dl\.php|/video\.php)[^\s"\'<>]*'),
            "key": re.compile(r'["\'](api[_\s]*key|apikey|key|token|secret)["\']\s*[:=]\s*["\']([^"\']+)["\']', re.I),
            "url": re.compile(r'https?://[^\s"\'<>]+'),
            "fetch": re.compile(r'fetch\s*\(\s*["\']([^"\']+)["\']'),
            "ajax": re.compile(r'\$\.(?:ajax|get|post|getJSON)\s*\(\s*["\']([^"\']+)["\']'),
        }
        
        for name, pattern in patterns.items():
            matches = pattern.findall(content)
            if matches:
                if name == "function":
                    analysis["functions"].extend(matches)
                elif name == "api":
                    analysis["api_calls"].extend(matches)
                    analysis["endpoints"].extend(matches)
                elif name == "key":
                    analysis["keys"].extend(matches)
                elif name == "url":
                    analysis["urls"].extend(matches)
                elif name in ["fetch", "ajax"]:
                    analysis["api_calls"].extend(matches)
                    analysis["endpoints"].extend(matches)
        
        self.scripts[url] = analysis
        return analysis

    # ==================== ОСНОВНОЙ ЗАПУСК ====================
    def run(self):
        """Запускает полный анализ сайта"""
        print("🚀 ЗАПУСК ПОЛНОГО АНАЛИЗА САЙТА")
        print("═" * 60)
        
        # Категории для обхода
        categories = [
            "/tip/polnometrazhnyy-film/",
            "/tip/tv/",
            "/tip/ova/",
            "/tip/ona/",
            "/tip/tv-speshl/",
            "/tip/korotkometrazhnyy-film/",
            "/tip/dunkhua/"
        ]
        
        all_films = []
        
        for cat in categories:
            cat_url = self.get_absolute_url(cat)
            films = self.parse_category(cat_url)
            all_films.extend(films)
            
            category_name = cat.strip("/").split("/")[-1]
            self.categories[category_name] = {
                "url": cat_url,
                "count": len(films),
                "films": films
            }
            
            time.sleep(REQUEST_DELAY * 2)
        
        # Сохраняем фильмы
        self.films = all_films
        print(f"\n✅ Всего собрано фильмов: {len(self.films)}")
        
        # Анализируем JS-файлы (первые 10 с главной страницы)
        print("\n📜 Анализ JavaScript-файлов...")
        main_html = self.fetch_url(self.base_url)
        if main_html:
            soup = BeautifulSoup(main_html, "lxml")
            for script in soup.find_all("script"):
                src = script.get("src")
                if src:
                    js_url = self.get_absolute_url(src)
                    self.analyze_javascript(js_url)
                    time.sleep(REQUEST_DELAY)
        
        # Сохраняем всё
        self.save_data()
        print("\n✅ АНАЛИЗ ЗАВЕРШЁН")

    # ==================== СОХРАНЕНИЕ ДАННЫХ ====================
    def save_data(self):
        """Сохраняет все данные в JSON-файлы"""
        print("\n💾 Сохранение данных...")
        
        # 1. Основной JSON со всеми фильмами
        films_file = self.output_dir / "films.json"
        with open(films_file, "w", encoding="utf-8") as f:
            json.dump(self.films, f, indent=2, ensure_ascii=False)
        print(f"  ✅ films.json ({len(self.films)} фильмов)")
        
        # 2. Категории
        categories_file = self.output_dir / "categories.json"
        with open(categories_file, "w", encoding="utf-8") as f:
            json.dump(self.categories, f, indent=2, ensure_ascii=False)
        print(f"  ✅ categories.json ({len(self.categories)} категорий)")
        
        # 3. JavaScript-анализ
        js_file = self.output_dir / "scripts.json"
        with open(js_file, "w", encoding="utf-8") as f:
            json.dump(self.scripts, f, indent=2, ensure_ascii=False)
        print(f"  ✅ scripts.json ({len(self.scripts)} файлов)")
        
        # 4. Полная структура для приложения
        structure = {
            "timestamp": datetime.now().isoformat(),
            "base_url": self.base_url,
            "total_films": len(self.films),
            "total_categories": len(self.categories),
            "total_scripts": len(self.scripts),
            "films": self.films,
            "categories": self.categories,
            "scripts": self.scripts,
            "api_endpoints": self.api_endpoints,
            "js_methods": self.js_methods
        }
        
        structure_file = self.output_dir / "site_structure.json"
        with open(structure_file, "w", encoding="utf-8") as f:
            json.dump(structure, f, indent=2, ensure_ascii=False)
        print(f"  ✅ site_structure.json")
        
        # 5. Упрощённый JSON для Android
        app_data = {
            "films": self.films,
            "categories": list(self.categories.keys()),
            "script_methods": self.js_methods,
            "api_endpoints": self.api_endpoints
        }
        app_file = self.output_dir / "app_data.json"
        with open(app_file, "w", encoding="utf-8") as f:
            json.dump(app_data, f, indent=2, ensure_ascii=False)
        print(f"  ✅ app_data.json")
        
        print(f"\n📁 Все файлы сохранены в: {self.output_dir.absolute()}")
        print(f"   - films.json – все фильмы")
        print(f"   - categories.json – категории")
        print(f"   - scripts.json – JavaScript-анализ")
        print(f"   - site_structure.json – полная структура")
        print(f"   - app_data.json – данные для приложения")

# ==================== ЗАПУСК ====================
if __name__ == "__main__":
    analyzer = AnimeVostAnalyzer()
    analyzer.run()
