#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Анализатор сайта AnimeVost (v13.vost.pw)
Собирает все фильмы со всех категорий и сохраняет в JSON.

Запуск: python analyze_animevost.py
Результат: films_structure.json
"""

import json
import re
import time
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin
from datetime import datetime

BASE_URL = "https://v13.vost.pw"
CATEGORIES = [
    "/tip/polnometrazhnyy-film/",
    "/tip/tv/",
    "/tip/ova/",
    "/tip/ona/",
    "/tip/tv-speshl/",
    "/tip/korotkometrazhnyy-film/",
    "/tip/dunkhua/"
]
REQUEST_DELAY = 1
MAX_PAGES = 100
OUTPUT_FILE = "films_structure.json"

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

def parse_category(category_url):
    print(f"\n📂 Анализ категории: {category_url}")
    all_films = []
    page = 1
    while page <= MAX_PAGES:
        url = category_url if page == 1 else f"{category_url}page/{page}/"
        print(f"  📄 Страница {page}...")
        html = fetch_html(url)
        if not html:
            break
        films = parse_category_page(html, category_url)
        if not films:
            print(f"  ℹ️ Страница {page} пуста – конец.")
            break
        all_films.extend(films)
        print(f"  ✅ Найдено {len(films)} (всего {len(all_films)})")
        if page == 1:
            soup = BeautifulSoup(html, "lxml")
            pager = soup.select_one(".pager")
            if not pager or not pager.find("a", href=re.compile(r"/page/2/")):
                break
        else:
            soup = BeautifulSoup(html, "lxml")
            if not soup.select_one(f"a[href*='{category_url}page/{page+1}/']"):
                print(f"  🏁 Достигнут конец пагинации.")
                break
        page += 1
        time.sleep(REQUEST_DELAY)
    return all_films

def main():
    print("🚀 ЗАПУСК ПОЛНОГО ПАРСИНГА САЙТА")
    print("═" * 50)
    all_films = []
    for cat in CATEGORIES:
        cat_url = urljoin(BASE_URL, cat)
        films = parse_category(cat_url)
        all_films.extend(films)
        print(f"✅ Категория {cat} завершена. Собрано {len(films)} фильмов.")
        time.sleep(REQUEST_DELAY * 2)
    
    all_films_sorted = sorted(all_films, key=lambda x: (int(x["year"]) if x["year"].isdigit() else 9999, x["title"]))
    output = {
        "timestamp": datetime.now().isoformat(),
        "total": len(all_films_sorted),
        "films": all_films_sorted
    }
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)
    
    print("\n" + "═" * 50)
    print(f"📊 ВСЕГО СОБРАНО ФИЛЬМОВ: {len(all_films_sorted)}")
    print(f"💾 Результат сохранён в {OUTPUT_FILE}")
    print("✅ АНАЛИЗ ЗАВЕРШЁН")

if __name__ == "__main__":
    main()
