#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Парсер для v13.vost.pw (работает с DLE-шаблоном)
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

        # Ищем все блоки shortstory (это карточки фильмов)
        shortstory_pattern = r'<div class="shortstory">(.*?)</div>\s*</div>\s*</div>'
        shortstories = re.findall(shortstory_pattern, html, re.DOTALL)
        
        if not shortstories:
            # Альтернативный поиск (если структура другая)
            shortstories = re.findall(r'<div class="shortstory">(.*?)<div class="clr">', html, re.DOTALL)

        if not shortstories:
            print(f"  ⚠️ На странице {page_num} нет фильмов.")
            return []

        page_films = []
        for story in shortstories:
            # 1. Ссылка на фильм
            href_match = re.search(r'<a href="([^"]+)"', story)
            if not href_match:
                continue
            href = href_match.group(1)
            film_url = urljoin(BASE_URL, href)
            
            # 2. Название (из h2)
            title_match = re.search(r'<h2>.*?<a[^>]*>(.*?)</a>', story, re.DOTALL)
            if not title_match:
                title_match = re.search(r'<h2>(.*?)</h2>', story, re.DOTALL)
            title = title_match.group(1).strip() if title_match else "Без названия"
            title = re.sub(r'<[^>]+>', '', title).strip()
            
            # 3. ID фильма из URL
            id_match = re.search(r"/(\d+)-", href)
            film_id = id_match.group(1) if id_match else "0"
            
            # 4. Год (из категорий)
            year_match = re.search(r'/god/(\d{4})/', story)
            year = year_match.group(1) if year_match else "неизвестно"
            
            # 5. Постер (из img)
            img_match = re.search(r'<img[^>]+src="([^"]+)"', story)
            poster = img_match.group(1) if img_match else ""
            if poster and not poster.startswith("http"):
                poster = urljoin(BASE_URL, poster)
            
            # 6. Категория (из ссылок)
            category = "polnometrazhnyy-film"
            
            # Проверка на дубликаты
            if not any(f["url"] == film_url for f in self.films):
                page_films.append({
                    "id": film_id,
                    "title": title,
                    "year": year,
                    "poster": poster,
                    "url": film_url,
                    "category": category
                })

        return page_films

    def run(self):
        print("🚀 Запуск парсера (полнометражные фильмы)")
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

            # Проверка следующей страницы
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

        films_file = self.output_dir / "films.json"
        with open(films_file, "w", encoding="utf-8") as f:
            json.dump(result, f, indent=2, ensure_ascii=False)

        print("\n" + "═" * 60)
        print(f"✅ Готово! Собрано {len(self.films)} фильмов.")
        print(f"💾 Файл сохранён: {films_file}")
        return len(self.films) > 0

if __name__ == "__main__":
    parser = FilmParser()
    parser.run()
