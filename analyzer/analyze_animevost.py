#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import json
import time
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin
from datetime import datetime
from pathlib import Path

# ==================== КОНФИГУРАЦИЯ ====================
BASE_URL = "https://v13.vost.pw"
SITE_DUMP_DIR = "site_dump"  # Папка для полной структуры
# ВАЖНО: Этот путь будет использоваться в GitHub Actions
FILMS_JSON = f"{SITE_DUMP_DIR}/films.json"
STRUCTURE_JSON = f"{SITE_DUMP_DIR}/site_structure.json"

# Категории для обхода
CATEGORIES = [
    "/tip/polnometrazhnyy-film/",
    "/tip/tv/",
    "/tip/ova/",
    "/tip/ona/",
    "/tip/tv-speshl/",
    "/tip/korotkometrazhnyy-film/",
    "/tip/dunkhua/"
]

def fetch_html(url):
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
    try:
        resp = requests.get(url, headers=headers, timeout=15)
        resp.raise_for_status()
        return resp.text
    except Exception as e:
        print(f"❌ {e}")
        return None

def parse_category_page(html, category_url):
    soup = BeautifulSoup(html, "lxml")
    films = []
    for article in soup.select("article.post"):
        a = article.select_one("span a")
        if not a:
            continue
        href = a.get("href")
        if not href:
            continue
        film_url = urljoin(BASE_URL, href)
        title = article.select_one("h2").text.strip() if article.select_one("h2") else "Без названия"
        year_elem = article.select_one("a[href*='/god/']")
        year = year_elem.text.strip() if year_elem else "неизвестно"
        style = article.get("style", "")
        poster_match = re.search(r"url\(['\"]?(.*?)['\"]?\)", style)
        poster = poster_match.group(1) if poster_match else ""
        if poster and not poster.startswith("http"):
            poster = urljoin(BASE_URL, poster)
        id_match = re.search(r"/(\d+)-", href)
        film_id = id_match.group(1) if id_match else None
        category = category_url.strip("/").split("/")[-1] if category_url else "unknown"
        films.append({
            "id": film_id,
            "title": title,
            "year": year,
            "poster": poster,
            "url": film_url,
            "category": category
        })
    return films

def analyze_category(category_url):
    all_films = []
    page = 1
    while page <= 100:
        url = category_url if page == 1 else f"{category_url}page/{page}/"
        html = fetch_html(url)
        if not html:
            break
        films = parse_category_page(html, category_url)
        if not films:
            break
        all_films.extend(films)
        if page == 1:
            soup = BeautifulSoup(html, "lxml")
            if not soup.select_one(f"a[href*='{category_url}page/2/']"):
                break
        else:
            soup = BeautifulSoup(html, "lxml")
            if not soup.select_one(f"a[href*='{category_url}page/{page+1}/']"):
                break
        page += 1
        time.sleep(1)
    return all_films

def main():
    print("🚀 ЗАПУСК ПОЛНОГО АНАЛИЗА САЙТА")
    print("═" * 50)
    
    # Создаём папку
    Path(SITE_DUMP_DIR).mkdir(exist_ok=True)
    
    all_films = []
    categories_data = {}
    
    for cat in CATEGORIES:
        cat_url = urljoin(BASE_URL, cat)
        print(f"\n📂 Анализ категории: {cat}")
        films = analyze_category(cat_url)
        all_films.extend(films)
        categories_data[cat.strip("/").split("/")[-1]] = {
            "url": cat_url,
            "count": len(films),
            "films": films
        }
        print(f"   ✅ Найдено {len(films)} фильмов")
    
    # Сохраняем все фильмы
    all_films_sorted = sorted(all_films, key=lambda x: (int(x["year"]) if x["year"].isdigit() else 9999, x["title"]))
    output = {
        "timestamp": datetime.now().isoformat(),
        "total": len(all_films_sorted),
        "categories": categories_data,
        "films": all_films_sorted
    }
    
    # Сохраняем в папку site_dump
    with open(FILMS_JSON, "w", encoding="utf-8") as f:
        json.dump(all_films_sorted, f, indent=2, ensure_ascii=False)
    
    with open(STRUCTURE_JSON, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)
    
    # Дополнительно сохраняем отдельные файлы для удобства
    with open(f"{SITE_DUMP_DIR}/categories.json", "w", encoding="utf-8") as f:
        json.dump(categories_data, f, indent=2, ensure_ascii=False)
    
    print("\n" + "═" * 50)
    print(f"✅ АНАЛИЗ ЗАВЕРШЁН")
    print(f"📊 Всего фильмов: {len(all_films_sorted)}")
    print(f"📁 Данные сохранены в папке: {SITE_DUMP_DIR}/")
    print(f"   - films.json (все фильмы)")
    print(f"   - site_structure.json (полная структура)")
    print(f"   - categories.json (категории)")

if __name__ == "__main__":
    main()
