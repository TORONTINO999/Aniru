#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Оптимизированный анализатор только для раздела полнометражных фильмов.
Собирает: ID, название, год, постер, ссылку, категорию.
Сохраняет в site_dump/films.json
"""

import re
import json
import time
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin
from pathlib import Path
from datetime import datetime

BASE_URL = "https://v13.vost.pw"
CATEGORY_URL = "/tip/polnometrazhnyy-film/"
OUTPUT_DIR = "site_dump"
REQUEST_DELAY = 0.5
MAX_PAGES = 50

class FastFilmParser:
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
        soup = BeautifulSoup(html, "lxml")
        
        # Ищем все article с классом post
        articles = soup.find_all("article", class_="post")
        if not articles:
            print(f"  ⚠️ На странице {page_num} нет фильмов.")
            return []

        page_films = []
        for article in articles:
            # 1. Ссылка на фильм (внутри span a)
            span = article.find("span")
            if not span:
                continue
            a_tag = span.find("a")
            if not a_tag or not a_tag.get("href"):
                continue
            
            href = a_tag.get("href")
            film_url = urljoin(BASE_URL, href)
            
            # 2. ID фильма из URL
            id_match = re.search(r"/(\d+)-", href)
            film_id = id_match.group(1) if id_match else "0"
            
            # 3. Название (из h2)
            h2 = article.find("h2")
            title = h2.text.strip() if h2 else "Без названия"
            
            # 4. Год (из тега a с href содержащим /god/)
            year_tag = article.find("a", href=re.compile(r"/god/\d{4}/"))
            year = year_tag.text.strip() if year_tag else "неизвестно"
            
            # 5. Постер (из style="background-image: url('...')")
            style = article.get("style", "")
            poster_match = re.search(r"url\(['\"]?(.*?)['\"]?\)", style)
            poster = poster_match.group(1) if poster_match else ""
            if poster and not poster.startswith("http"):
                poster = urljoin(BASE_URL, poster)
            
            # Проверка на дубликаты
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
        print("🚀 Запуск анализатора (только полнометражные фильмы)")
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
            soup = BeautifulSoup(html, "lxml")
            next_page_pattern = f"{CATEGORY_URL}page/{page+1}/"
            if not soup.find("a", href=re.compile(re.escape(next_page_pattern))):
                print(f"  🏁 Достигнут конец пагинации на странице {page}.")
                break

            time.sleep(REQUEST_DELAY)

        # Сохраняем результат
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
    parser = FastFilmParser()
    parser.run()
