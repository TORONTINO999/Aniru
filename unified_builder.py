#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Парсер для сайта v13.vost.pw (без JavaScript)
Использует регулярные выражения для прямого парсинга HTML
"""

import re
import json
import time
import requests
from pathlib import Path
from datetime import datetime
from urllib.parse import urljoin

BASE_URL = "https://v13.vost.pw"
CATEGORY_URL = "/tip/polnometrazhnyy-film/"
OUTPUT_DIR = "site_dump"
REQUEST_DELAY = 0.5
MAX_PAGES = 50

class FilmParser:
    def __init__(self):
        self.output_dir = Path(OUTPUT_DIR)
        self.output_dir.mkdir(exist_ok=True)
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
            print(f"  ❌ Ошибка: {e}")
            return None

    def parse_films_from_page(self, html, page_num):
        if not html:
            return []
        
        # Ищем все article с классом post
        articles = re.findall(r'<article\s+class="post"[^>]*>(.*?)</article>', html, re.DOTALL)
        
        if not articles:
            print(f"  ⚠️ На странице {page_num} нет фильмов.")
            return []

        page_films = []
        for article_html in articles:
            # 1. Ссылка на фильм
            href_match = re.search(r'<a\s+href="([^"]+)"', article_html)
            if not href_match:
                continue
            href = href_match.group(1)
            film_url = urljoin(BASE_URL, href)
            
            # 2. ID фильма
            id_match = re.search(r"/(\d+)-", href)
            film_id = id_match.group(1) if id_match else "0"
            
            # 3. Название
            title_match = re.search(r'<h2>(.*?)</h2>', article_html, re.DOTALL)
            title = title_match.group(1).strip() if title_match else "Без названия"
            title = re.sub(r'<[^>]+>', '', title)
            
            # 4. Год
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
        print("🚀 Запуск парсера (регулярные выражения)")
        print("═" * 50)

        for page in range(1, MAX_PAGES + 1):
            print(f"\n📄 Страница {page}...")

            if page == 1:
                url = urljoin(BASE_URL, CATEGORY_URL)
            else:
                url = urljoin(BASE_URL, f"{CATEGORY_URL}page/{page}/")

            html = self.fetch_page(url)
            if not html:
                print(f"  ⏹ Ошибка загрузки. Останавливаемся на странице {page}.")
                break

            films = self.parse_films_from_page(html, page)
            if not films:
                print(f"  ℹ️ На странице {page} нет фильмов. Возможно, это конец.")
                break

            self.films.extend(films)
            print(f"  ✅ Найдено {len(films)} фильмов (всего {len(self.films)})")

            if not re.search(rf'href="[^"]*{CATEGORY_URL}page/{page+1}/', html):
                print(f"  🏁 Достигнут конец пагинации на странице {page}.")
                break

            time.sleep(REQUEST_DELAY)

        result = {
            "timestamp": datetime.now().isoformat(),
            "total": len(self.films),
            "films": self.films
        }

        films_file = self.output_dir / "films.json"
        with open(films_file, "w", encoding="utf-8") as f:
            json.dump(result, f, indent=2, ensure_ascii=False)

        print("\n" + "═" * 50)
        print(f"✅ Готово! Собрано {len(self.films)} фильмов.")
        print(f"💾 Файл сохранён: {films_file}")
        return len(self.films) > 0

if __name__ == "__main__":
    parser = FilmParser()
    parser.run()
