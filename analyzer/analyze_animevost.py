#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
ПОЛНЫЙ АНАЛИЗАТОР САЙТА ANIMEVOST
Скачивает ВСЁ: HTML, CSS, JavaScript, изображения, шрифты
Анализирует JS-код на наличие API, ключей, методов
Сохраняет полную структуру в JSON для использования в приложении

Запуск: python full_site_analyzer.py
Результат: site_structure.json (полная структура сайта)
"""

import os
import re
import json
import time
import zlib
import hashlib
import requests
from urllib.parse import urljoin, urlparse
from datetime import datetime
from bs4 import BeautifulSoup
from pathlib import Path
from typing import Dict, List, Set, Optional, Any

# ==================== КОНФИГУРАЦИЯ ====================
BASE_URL = "https://v13.vost.pw"
OUTPUT_DIR = "site_structure"
MAX_PAGES = 2000  # Максимум страниц для сканирования
REQUEST_DELAY = 0.5
MAX_DEPTH = 5

# ==================== КЛАСС АНАЛИЗАТОРА ====================
class FullSiteAnalyzer:
    def __init__(self):
        self.base_url = BASE_URL
        self.output_dir = Path(OUTPUT_DIR)
        self.output_dir.mkdir(exist_ok=True)
        
        # Структуры для сбора данных
        self.pages: Dict[str, Dict] = {}  # Все страницы
        self.scripts: Dict[str, Dict] = {}  # Все JS-файлы
        self.styles: Dict[str, Dict] = {}  # Все CSS-файлы
        self.images: Dict[str, Dict] = {}  # Все изображения
        self.api_endpoints: Dict[str, List] = {}  # API-эндпоинты
        self.js_methods: Dict[str, List] = {}  # JS-методы
        self.video_links: List[str] = []  # Видео-ссылки
        self.iframe_links: List[str] = []  # Iframe-ссылки
        
        self.visited_urls: Set[str] = set()
        self.film_data: List[Dict] = []  # Все фильмы
        self.category_structure: Dict = {}  # Структура категорий
        
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
            "Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7",
            "Accept-Encoding": "gzip, deflate, br",
            "Connection": "keep-alive",
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "none",
            "Cache-Control": "max-age=0"
        })

    # ==================== ЗАГРУЗКА РЕСУРСОВ ====================
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
            print(f"  ❌ Ошибка: {url} - {e}")
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

    # ==================== АНАЛИЗ HTML ====================
    def analyze_html(self, html: str, url: str) -> Dict:
        """Полный анализ HTML-страницы"""
        soup = BeautifulSoup(html, "lxml")
        
        analysis = {
            "url": url,
            "title": soup.title.string.strip() if soup.title else "",
            "meta": {},
            "links": {"internal": [], "external": []},
            "scripts": [],
            "styles": [],
            "images": [],
            "iframes": [],
            "forms": [],
            "video": [],
            "audio": [],
            "comments": [],
            "dom_structure": self._analyze_dom(soup),
            "keywords": [],
            "description": ""
        }
        
        # Meta-теги
        for meta in soup.find_all("meta"):
            name = meta.get("name") or meta.get("property") or ""
            content = meta.get("content", "")
            if name and content:
                analysis["meta"][name] = content
                if name == "keywords":
                    analysis["keywords"] = [k.strip() for k in content.split(",")]
                if name == "description":
                    analysis["description"] = content
        
        # Ссылки
        for a in soup.find_all("a", href=True):
            href = a.get("href")
            if href and not href.startswith("#") and not href.startswith("javascript:"):
                full_url = self.get_absolute_url(href)
                if self.is_internal(full_url):
                    analysis["links"]["internal"].append(full_url)
                else:
                    analysis["links"]["external"].append(full_url)
        
        # Скрипты
        for script in soup.find_all("script"):
            src = script.get("src")
            if src:
                analysis["scripts"].append(self.get_absolute_url(src))
            elif script.string:
                analysis["comments"].append({
                    "type": "inline_script",
                    "content": script.string[:500]
                })
        
        # Стили
        for link in soup.find_all("link", rel="stylesheet"):
            href = link.get("href")
            if href:
                analysis["styles"].append(self.get_absolute_url(href))
        
        # Изображения
        for img in soup.find_all("img"):
            src = img.get("src")
            if src:
                analysis["images"].append(self.get_absolute_url(src))
        
        # Iframe
        for iframe in soup.find_all("iframe"):
            src = iframe.get("src")
            if src:
                analysis["iframes"].append(self.get_absolute_url(src))
        
        # Видео
        for video in soup.find_all("video"):
            src = video.get("src")
            if src:
                analysis["video"].append(self.get_absolute_url(src))
            for source in video.find_all("source"):
                src = source.get("src")
                if src:
                    analysis["video"].append(self.get_absolute_url(src))
        
        # Формы
        for form in soup.find_all("form"):
            form_data = {
                "action": form.get("action", ""),
                "method": form.get("method", "get"),
                "inputs": []
            }
            for input_tag in form.find_all("input"):
                form_data["inputs"].append({
                    "name": input_tag.get("name", ""),
                    "type": input_tag.get("type", "text"),
                    "value": input_tag.get("value", "")
                })
            analysis["forms"].append(form_data)
        
        return analysis

    def _analyze_dom(self, soup) -> Dict:
        """Анализирует структуру DOM"""
        dom = {
            "tags": {},
            "classes": {},
            "ids": {},
            "data_attrs": {},
            "max_depth": 0
        }
        
        def traverse(element, depth=0):
            if depth > dom["max_depth"]:
                dom["max_depth"] = depth
            
            tag = element.name
            if tag:
                dom["tags"][tag] = dom["tags"].get(tag, 0) + 1
            
            if element.get("class"):
                for cls in element.get("class"):
                    dom["classes"][cls] = dom["classes"].get(cls, 0) + 1
            
            if element.get("id"):
                dom["ids"][element.get("id")] = True
            
            for attr in element.attrs:
                if attr.startswith("data-"):
                    dom["data_attrs"][attr] = dom["data_attrs"].get(attr, 0) + 1
            
            for child in element.children:
                if hasattr(child, "name") and child.name:
                    traverse(child, depth + 1)
        
        for child in soup.children:
            if hasattr(child, "name") and child.name:
                traverse(child)
        
        return dom

    # ==================== АНАЛИЗ JAVASCRIPT ====================
    def analyze_javascript(self, content: str, url: str) -> Dict:
        """Глубокий анализ JavaScript-кода"""
        analysis = {
            "url": url,
            "size": len(content),
            "variables": [],
            "functions": [],
            "api_calls": [],
            "endpoints": [],
            "urls": [],
            "keys": [],
            "tokens": [],
            "imports": [],
            "exports": [],
            "event_listeners": [],
            "ajax_calls": [],
            "fetch_calls": [],
            "eval_calls": [],
            "regex_patterns": [],
            "strings": []
        }
        
        # Паттерны для анализа
        patterns = {
            "url": re.compile(r'https?://[^\s"\'<>]+'),
            "api": re.compile(r'(/api/|/v1/|/v2/|/get_|/set_|/dl\.php|/video\.php)[^\s"\'<>]*'),
            "key": re.compile(r'["\'](api[_\s]*key|apikey|key|token|secret|password)["\']\s*[:=]\s*["\']([^"\']+)["\']', re.I),
            "function": re.compile(r'function\s+([a-zA-Z_$][a-zA-Z0-9_$]*)\s*\('),
            "fetch": re.compile(r'fetch\s*\(\s*["\']([^"\']+)["\']'),
            "ajax": re.compile(r'\$\.(?:ajax|get|post|getJSON)\s*\(\s*["\']([^"\']+)["\']'),
            "import": re.compile(r'import\s+.*?from\s+["\']([^"\']+)["\']'),
            "export": re.compile(r'export\s+(?:default\s+)?(?:function|class|const|let|var)\s+([a-zA-Z_$][a-zA-Z0-9_$]*)'),
            "eval": re.compile(r'eval\s*\(["\']([^"\']+)["\']'),
            "event": re.compile(r'\.(?:addEventListener|on)\s*\(\s*["\']([^"\']+)["\']'),
        }
        
        # Анализ по паттернам
        for name, pattern in patterns.items():
            matches = pattern.findall(content)
            if matches:
                if name == "key":
                    analysis["keys"].extend(matches)
                elif name == "function":
                    analysis["functions"].extend(matches)
                elif name == "fetch":
                    analysis["fetch_calls"].extend(matches)
                elif name == "ajax":
                    analysis["ajax_calls"].extend(matches)
                elif name == "import":
                    analysis["imports"].extend(matches)
                elif name == "export":
                    analysis["exports"].extend(matches)
                elif name == "eval":
                    analysis["eval_calls"].extend(matches)
                elif name == "event":
                    analysis["event_listeners"].extend(matches)
                elif name == "url":
                    analysis["urls"].extend(matches)
                elif name == "api":
                    analysis["api_calls"].extend(matches)
                    analysis["endpoints"].extend(matches)
        
        # Ищем строки (для анализа данных)
        string_pattern = re.compile(r'["\']([^"\']{10,})["\']')
        analysis["strings"] = string_pattern.findall(content)
        
        # Ищем переменные
        var_pattern = re.compile(r'(?:var|let|const)\s+([a-zA-Z_$][a-zA-Z0-9_$]*)\s*[=;]')
        analysis["variables"] = var_pattern.findall(content)
        
        # Ищем токены (длинные строки)
        for s in analysis["strings"]:
            if len(s) > 20 and any(c.isalnum() for c in s):
                analysis["tokens"].append(s)
        
        return analysis

    # ==================== АНАЛИЗ CSS ====================
    def analyze_css(self, content: str, url: str) -> Dict:
        """Анализирует CSS-файл"""
        analysis = {
            "url": url,
            "size": len(content),
            "selectors": [],
            "properties": [],
            "media_queries": [],
            "keyframes": [],
            "imports": [],
            "colors": [],
            "fonts": [],
            "urls": []
        }
        
        # Селекторы
        selector_pattern = re.compile(r'([.#]?[a-zA-Z_][a-zA-Z0-9_-]*)\s*{')
        analysis["selectors"] = list(set(selector_pattern.findall(content)))
        
        # Свойства
        prop_pattern = re.compile(r'([a-zA-Z-]+)\s*:\s*([^;{]+);')
        properties = prop_pattern.findall(content)
        for prop, value in properties:
            analysis["properties"].append(prop)
            if "url(" in value:
                analysis["urls"].extend(re.findall(r'url\(["\']?([^)"\']+)["\']?\)', value))
            if "#" in value and len(value) < 8:
                analysis["colors"].extend(re.findall(r'#[a-fA-F0-9]{3,6}', value))
        
        # Media Queries
        mq_pattern = re.compile(r'@media\s+[^{]+{')
        analysis["media_queries"] = mq_pattern.findall(content)
        
        # Keyframes
        kf_pattern = re.compile(r'@keyframes\s+([a-zA-Z_][a-zA-Z0-9_-]*)\s*{')
        analysis["keyframes"] = kf_pattern.findall(content)
        
        # Импорты
        import_pattern = re.compile(r'@import\s+["\']([^"\']+)["\']')
        analysis["imports"] = import_pattern.findall(content)
        
        # Шрифты
        font_pattern = re.compile(r'font-family\s*:\s*([^;]+);')
        analysis["fonts"] = list(set(font_pattern.findall(content)))
        
        return analysis

    # ==================== КРАУЛИНГ САЙТА ====================
    def crawl_site(self):
        """Запускает полный обход сайта"""
        print("🕷️ ЗАПУСК ПОЛНОГО КРАУЛИНГА САЙТА")
        print("═" * 60)
        
        # Стартовые URL
        start_urls = [
            self.base_url,
            f"{self.base_url}/tip/polnometrazhnyy-film/",
            f"{self.base_url}/tip/tv/",
            f"{self.base_url}/tip/ova/",
            f"{self.base_url}/tip/ona/",
            f"{self.base_url}/tip/tv-speshl/",
            f"{self.base_url}/tip/korotkometrazhnyy-film/",
            f"{self.base_url}/tip/dunkhua/"
        ]
        
        for start_url in start_urls:
            self._crawl_page(start_url, depth=0)
        
        self._save_structure()
        self._generate_json_for_app()

    def _crawl_page(self, url: str, depth: int):
        """Обходит одну страницу рекурсивно"""
        if depth > MAX_DEPTH or len(self.visited_urls) > MAX_PAGES:
            return
        
        print(f"📄 [{depth}] {url}")
        html = self.fetch_url(url)
        if not html:
            return
        
        # Анализируем HTML
        page_analysis = self.analyze_html(html, url)
        self.pages[url] = page_analysis
        
        # Определяем тип страницы
        if "/tip/" in url and "/page/" not in url:
            self._extract_films(html, url)
        elif "/page/" in url:
            self._extract_films(html, url)
        
        # Скачиваем и анализируем ресурсы
        for script_url in page_analysis["scripts"][:10]:  # Ограничиваем
            self._analyze_script(script_url)
            time.sleep(REQUEST_DELAY)
        
        for style_url in page_analysis["styles"][:5]:
            self._analyze_style(style_url)
            time.sleep(REQUEST_DELAY)
        
        # Обрабатываем внутренние ссылки
        for link in page_analysis["links"]["internal"][:10]:
            if link not in self.visited_urls:
                self._crawl_page(link, depth + 1)
                time.sleep(REQUEST_DELAY)

    def _analyze_script(self, url: str):
        """Анализирует JavaScript-файл"""
        if url in self.scripts:
            return
        
        print(f"  📜 JS: {url}")
        content = self.fetch_url(url)
        if not content:
            return
        
        analysis = self.analyze_javascript(content, url)
        self.scripts[url] = analysis
        
        # Сохраняем найденные API-эндпоинты
        for endpoint in analysis["endpoints"]:
            if endpoint not in self.api_endpoints:
                self.api_endpoints[endpoint] = []
            self.api_endpoints[endpoint].append(url)
        
        # Сохраняем методы
        for method in analysis["functions"]:
            if method not in self.js_methods:
                self.js_methods[method] = []
            self.js_methods[method].append(url)

    def _analyze_style(self, url: str):
        """Анализирует CSS-файл"""
        if url in self.styles:
            return
        
        print(f"  🎨 CSS: {url}")
        content = self.fetch_url(url)
        if not content:
            return
        
        self.styles[url] = self.analyze_css(content, url)

    def _extract_films(self, html: str, url: str):
        """Извлекает фильмы со страницы категории"""
        soup = BeautifulSoup(html, "lxml")
        
        for article in soup.select("article.post"):
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
            
            category_match = re.search(r"/tip/([^/]+)/", url)
            category = category_match.group(1) if category_match else "unknown"
            
            film_data = {
                "id": film_id,
                "title": title,
                "year": year,
                "poster": poster,
                "url": film_url,
                "category": category
            }
            
            # Проверяем, есть ли уже такой фильм
            if not any(f["url"] == film_url for f in self.film_data):
                self.film_data.append(film_data)

    # ==================== СОХРАНЕНИЕ СТРУКТУРЫ ====================
    def _save_structure(self):
        """Сохраняет полную структуру в JSON"""
        structure = {
            "timestamp": datetime.now().isoformat(),
            "base_url": self.base_url,
            "statistics": {
                "total_pages": len(self.pages),
                "total_scripts": len(self.scripts),
                "total_styles": len(self.styles),
                "total_films": len(self.film_data),
                "total_api_endpoints": len(self.api_endpoints),
                "total_js_methods": len(self.js_methods)
            },
            "pages": self.pages,
            "scripts": self.scripts,
            "styles": self.styles,
            "films": self.film_data,
            "api_endpoints": self.api_endpoints,
            "js_methods": self.js_methods,
            "video_links": list(set(self.video_links)),
            "iframe_links": list(set(self.iframe_links))
        }
        
        # Сохраняем полную структуру
        output_file = self.output_dir / "site_structure.json"
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(structure, f, indent=2, ensure_ascii=False)
        
        print(f"\n💾 Полная структура сохранена в {output_file}")
        print(f"   📄 Страниц: {structure['statistics']['total_pages']}")
        print(f"   📜 JS-файлов: {structure['statistics']['total_scripts']}")
        print(f"   🎨 CSS-файлов: {structure['statistics']['total_styles']}")
        print(f"   🎬 Фильмов: {structure['statistics']['total_films']}")
        print(f"   🔗 API-эндпоинтов: {structure['statistics']['total_api_endpoints']}")

    def _generate_json_for_app(self):
        """Генерирует JSON для Android-приложения"""
        app_data = {
            "version": "1.0",
            "timestamp": datetime.now().isoformat(),
            "films": self.film_data,
            "api_endpoints": self.api_endpoints,
            "js_methods": self.js_methods,
            "selectors": {
                "film_card": "article.post",
                "film_title": "h2",
                "film_year": "a[href*='/god/']",
                "film_poster": "span a",
                "video_player": "video",
                "iframe_player": "iframe"
            }
        }
        
        # Сохраняем для приложения
        app_file = self.output_dir / "app_data.json"
        with open(app_file, "w", encoding="utf-8") as f:
            json.dump(app_data, f, indent=2, ensure_ascii=False)
        
        print(f"📱 Данные для приложения: {app_file}")

# ==================== ЗАПУСК ====================
if __name__ == "__main__":
    analyzer = FullSiteAnalyzer()
    analyzer.crawl_site()
