#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Анализатор сайта AnimeVost на основе sitemap.xml
Скачивает все страницы фильмов, извлекает данные и ресурсы.
"""

import re
import json
import time
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
from pathlib import Path
from datetime import datetime
import xml.etree.ElementTree as ET

# ================== КОНФИГ ==================
BASE_URL = "https://v13.vost.pw"
SITEMAP_URL = "https://v13.vost.pw/sitemap.xml"  # или локальный файл
OUTPUT_DIR = "site_dump"
REQUEST_DELAY = 0.5
MAX_JS_CSS = 5  # сколько JS/CSS файлов скачивать с каждой страницы

# ================== КЛАСС АНАЛИЗАТОРА ==================
class AnimeVostSitemapAnalyzer:
    def __init__(self):
        self.output_dir = Path(OUTPUT_DIR)
        self.output_dir.mkdir(exist_ok=True)
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        })
        self.films = []
        self.js_files = {}
        self.css_files = {}
        self.images = {}
        self.visited_urls = set()

    def fetch_sitemap(self):
        """Загружает sitemap.xml (локально или с сервера)"""
        if Path("sitemap.xml").exists():
            with open("sitemap.xml", "r", encoding="utf-8") as f:
                return f.read()
        resp = self.session.get(SITEMAP_URL, timeout=30)
        resp.raise_for_status()
        return resp.text

    def parse_sitemap(self, xml_content):
        """Извлекает все URL из sitemap"""
        root = ET.fromstring(xml_content)
        ns = {'ns': 'http://www.sitemaps.org/schemas/sitemap/0.9'}
        urls = []
        for loc in root.findall('.//ns:loc', ns):
            urls.append(loc.text)
        return urls

    def is_film_url(self, url):
        """Проверяет, является ли URL страницей фильма (содержит числовой ID)"""
        # Примеры: /tip/tv/3890-snowball-earth.html, /tip/polnometrazhnyy-film/2976-...
        pattern = r'/tip/[^/]+/\d+-[^/]+\.html$'
        return re.search(pattern, url) is not None

    def fetch_page(self, url):
        if url in self.visited_urls:
            return None
        try:
            resp = self.session.get(url, timeout=15)
            resp.raise_for_status()
            self.visited_urls.add(url)
            return resp.text
        except Exception as e:
            print(f"⚠️ Ошибка загрузки {url}: {e}")
            return None

    def extract_film_data(self, html, url):
        """Извлекает данные фильма из HTML"""
        soup = BeautifulSoup(html, "lxml")
        data = {
            "url": url,
            "title": "",
            "year": "неизвестно",
            "poster": "",
            "video_url": None,
            "iframe_url": None,
            "js_links": [],
            "css_links": [],
            "image_links": []
        }

        # Название
        title_elem = soup.select_one("h1, .post-title, .title")
        if title_elem:
            data["title"] = title_elem.text.strip()
        else:
            # fallback
            title_elem = soup.select_one("h2")
            if title_elem:
                data["title"] = title_elem.text.strip()

        # Год
        year_elem = soup.select_one("a[href*='/god/']")
        if year_elem:
            data["year"] = year_elem.text.strip()

        # Постер
        style_elem = soup.select_one("[style*='background-image']")
        if style_elem:
            style = style_elem.get("style", "")
            match = re.search(r"url\(['\"]?(.*?)['\"]?\)", style)
            if match:
                data["poster"] = urljoin(BASE_URL, match.group(1))

        # Видео (тег video)
        video = soup.find("video")
        if video:
            src = video.get("src")
            if src:
                data["video_url"] = urljoin(BASE_URL, src)
            else:
                source = video.find("source")
                if source and source.get("src"):
                    data["video_url"] = urljoin(BASE_URL, source.get("src"))

        # Iframe
        iframe = soup.find("iframe")
        if iframe and iframe.get("src"):
            data["iframe_url"] = urljoin(BASE_URL, iframe.get("src"))

        # Поиск видео в скриптах
        for script in soup.find_all("script"):
            if script.string:
                content = script.string
                # Ищем .mp4 или .m3u8
                match = re.search(r'(https?://[^\s"\'<>]+\.(?:mp4|m3u8)[^\s"\'<>]*)', content)
                if match:
                    data["video_url"] = match.group(1)
                # Ищем "file":"..."
                match = re.search(r'"file"\s*:\s*"([^"]+\.(?:mp4|m3u8)[^"]*)"', content)
                if match:
                    data["video_url"] = match.group(1)

        # Собираем ссылки на ресурсы
        for script in soup.find_all("script"):
            src = script.get("src")
            if src:
                data["js_links"].append(urljoin(BASE_URL, src))
        for link in soup.find_all("link", rel="stylesheet"):
            href = link.get("href")
            if href:
                data["css_links"].append(urljoin(BASE_URL, href))
        for img in soup.find_all("img"):
            src = img.get("src")
            if src:
                data["image_links"].append(urljoin(BASE_URL, src))

        # Ограничим количество, чтобы не перегружать
        data["js_links"] = data["js_links"][:MAX_JS_CSS]
        data["css_links"] = data["css_links"][:MAX_JS_CSS]
        data["image_links"] = data["image_links"][:5]

        return data

    def download_resource(self, url, resource_type):
        """Скачивает ресурс (JS, CSS, изображение) и сохраняет в папку"""
        try:
            resp = self.session.get(url, timeout=15)
            resp.raise_for_status()
            parsed = urlparse(url)
            # Создаём имя файла на основе URL
            filename = parsed.path.strip("/").replace("/", "_")
            if not filename:
                filename = hashlib.md5(url.encode()).hexdigest()
            if resource_type == "js" and not filename.endswith(".js"):
                filename += ".js"
            elif resource_type == "css" and not filename.endswith(".css"):
                filename += ".css"
            elif resource_type == "image":
                # Сохраняем с оригинальным расширением
                ext = parsed.path.split(".")[-1] if "." in parsed.path else "jpg"
                filename = f"{filename}.{ext}"
            # Определяем папку
            folder = self.output_dir / resource_type
            folder.mkdir(exist_ok=True)
            filepath = folder / filename
            with open(filepath, "wb") as f:
                f.write(resp.content)
            return str(filepath.relative_to(self.output_dir))
        except Exception as e:
            print(f"⚠️ Не удалось скачать {resource_type} {url}: {e}")
            return None

    def process_film_page(self, url):
        """Обрабатывает одну страницу фильма"""
        print(f"🎬 Обработка {url}")
        html = self.fetch_page(url)
        if not html:
            return None

        data = self.extract_film_data(html, url)
        # Скачиваем JS, CSS, изображения
        for js in data["js_links"]:
            self.download_resource(js, "js")
            time.sleep(0.2)
        for css in data["css_links"]:
            self.download_resource(css, "css")
            time.sleep(0.2)
        for img in data["image_links"]:
            self.download_resource(img, "image")
            time.sleep(0.2)

        # Сохраняем ссылки на локальные файлы (если нужно)
        return data

    def run(self):
        print("🚀 Запуск анализатора на основе sitemap")
        xml = self.fetch_sitemap()
        urls = self.parse_sitemap(xml)
        film_urls = [u for u in urls if self.is_film_url(u)]
        print(f"📊 Найдено страниц фильмов: {len(film_urls)}")

        for i, url in enumerate(film_urls, 1):
            print(f"  [{i}/{len(film_urls)}] ", end="")
            film_data = self.process_film_page(url)
            if film_data:
                self.films.append(film_data)
            time.sleep(REQUEST_DELAY)

        # Сохраняем результат
        result = {
            "timestamp": datetime.now().isoformat(),
            "total": len(self.films),
            "films": self.films
        }
        with open(self.output_dir / "films.json", "w", encoding="utf-8") as f:
            json.dump(result, f, indent=2, ensure_ascii=False)

        print(f"✅ Сохранено {len(self.films)} фильмов в {self.output_dir}/films.json")

if __name__ == "__main__":
    analyzer = AnimeVostSitemapAnalyzer()
    analyzer.run()
