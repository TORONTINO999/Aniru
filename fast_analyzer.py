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
REQUEST_DELAY = 0.5  # Можно уменьшить до 0.2 для скорости
MAX_PAGES = 50  # Ограничиваем количество страниц

class FastFilmParser:
    def __init__(self):
        self.output_dir = Path(OUTPUT_DIR)
        self.output_dir.mkdir(exist_ok=True)
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        })
        self.films = []
        self.visited_urls = set()

    def fetch_page(self, url):
        """Загружает HTML страницы"""
        try:
            resp = self.session.get(url, timeout=10)
            resp.raise_for_status()
            return resp.text
        except Exception as e:
            print(f"  ❌ Ошибка: {e}")
            return None

    def parse_films_from_page(self, html, page_num):
        """Парсит карточки фильмов на странице"""
        soup = BeautifulSoup(html, "lxml")
        articles = soup.select("article.post")
        if not articles:
            print(f"  ⚠️ На странице {page_num} нет фильмов.")
            return []

        page_films = []
        for article in articles:
            # Ссылка на фильм
            a = article.select_one("span a")
            if not a:
                continue
            href = a.get("href")
            if not href:
                continue
            film_url = urljoin(BASE_URL, href)

            # Название
            title_elem = article.select_one("h2")
            title = title_elem.text.strip() if title_elem else "Без названия"

            # Год
            year_elem = article.select_one("a[href*='/god/']")
            year = year_elem.text.strip() if year_elem else "неизвестно"

            # Постер (из style)
            style = article.get("style", "")
            poster_match = re.search(r"url\(['\"]?(.*?)['\"]?\)", style)
            poster = poster_match.group(1) if poster_match else ""
            if poster and not poster.startswith("http"):
                poster = urljoin(BASE_URL, poster)

            # ID фильма (из URL)
            id_match = re.search(r"/(\d+)-", href)
            film_id = id_match.group(1) if id_match else None

            # Категория
            category = "polnometrazhnyy-film"

            film_data = {
                "id": film_id,
                "title": title,
                "year": year,
                "poster": poster,
                "url": film_url,
                "category": category
            }

            # Проверяем дубликаты
            if not any(f["url"] == film_url for f in self.films):
                page_films.append(film_data)

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

        films_file = self.output_dir / "films.json"
        with open(films_file, "w", encoding="utf-8") as f:
            json.dump(result, f, indent=2, ensure_ascii=False)

        print("\n" + "═" * 50)
        print(f"✅ Готово! Собрано {len(self.films)} фильмов.")
        print(f"💾 Файл сохранён: {films_file}")

if __name__ == "__main__":
    parser = FastFilmParser()
    parser.run()
