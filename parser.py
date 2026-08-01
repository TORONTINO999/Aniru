import os
import re
import time
import json
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
from PIL import Image
import pytesseract
from io import BytesIO

# ==========================================================
# НАСТРОЙКИ
# ==========================================================
BASE_URL = "https://mp4anime.com"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7",
    "Referer": BASE_URL
}

session = requests.Session()
session.headers.update(HEADERS)

POSTERS_DIR = "posters_movies"
os.makedirs(POSTERS_DIR, exist_ok=True)

OUTPUT_M3U = "anime_movies.m3u"
PROGRESS_FILE = "progress_movies.json"

# ==========================================================
# РАСПОЗНАВАНИЕ КАПЧИ
# ==========================================================
def solve_captcha(img_url):
    """Загружает капчу, распознаёт 3‑значный цифровой код."""
    try:
        resp = session.get(img_url, timeout=10)
        if resp.status_code != 200:
            return None
        img = Image.open(BytesIO(resp.content))
        img = img.convert('L')
        img = img.point(lambda x: 0 if x < 128 else 255, '1')
        code = pytesseract.image_to_string(img, config='--psm 8 -c tessedit_char_whitelist=0123456789')
        code = re.sub(r'\D', '', code).strip()
        return code if len(code) == 3 else None
    except Exception as e:
        print(f"   ❌ Ошибка распознавания капчи: {e}")
        return None

# ==========================================================
# ПОЛУЧЕНИЕ ПРЯМОЙ ССЫЛКИ
# ==========================================================
def get_direct_link(download_url, retries=3):
    """Проходит капчу и возвращает прямую ссылку на MP4."""
    for attempt in range(retries):
        try:
            resp = session.get(download_url, timeout=15)
            if resp.status_code != 200:
                continue

            soup = BeautifulSoup(resp.text, 'html.parser')
            form = soup.find('form')
            if not form:
                continue

            hidden_inputs = form.find_all('input', type='hidden')
            form_data = {inp.get('name'): inp.get('value') for inp in hidden_inputs if inp.get('name')}

            cap_img = soup.find('img', class_='img_caps')
            if not cap_img:
                continue

            cap_url = urljoin(BASE_URL, cap_img.get('src'))
            code = solve_captcha(cap_url)
            if not code:
                continue

            form_data['com_cod'] = code
            action_url = urljoin(BASE_URL, form.get('action', download_url))

            post_resp = session.post(action_url, data=form_data, timeout=15)

            # Ищем ссылку на скачивание
            soup_result = BeautifulSoup(post_resp.text, 'html.parser')
            download_link = soup_result.find('a', href=re.compile(r'\.mp4$|dl\.php\?file='))
            if download_link:
                return urljoin(BASE_URL, download_link.get('href'))

            # Если не нашли, ищем в тексте
            mp4_links = re.findall(r'href=[\'"]?([^\'" >]+\.mp4[^\'" >]*)', post_resp.text)
            if mp4_links:
                return urljoin(BASE_URL, mp4_links[0])

        except Exception as e:
            print(f"   ❌ Ошибка: {e}")

        time.sleep(2)
    return None

# ==========================================================
# СКАЧИВАНИЕ ПОСТЕРА
# ==========================================================
def download_poster(poster_url, anime_id):
    if not poster_url:
        return None
    try:
        resp = session.get(poster_url, timeout=10)
        if resp.status_code == 200:
            ext = os.path.splitext(urlparse(poster_url).path)[1] or '.jpg'
            filename = f"{anime_id}{ext}"
            filepath = os.path.join(POSTERS_DIR, filename)
            with open(filepath, 'wb') as f:
                f.write(resp.content)
            return filepath
    except Exception:
        pass
    return None

# ==========================================================
# ПРОВЕРКА: ЭТО ФИЛЬМ ИЛИ СЕРИАЛ?
# ==========================================================
def is_movie(anime_id):
    """Заходит на страницу аниме и проверяет тип (Фильм / Movie)."""
    url = f"{BASE_URL}/anime.php?id={anime_id}"
    try:
        resp = session.get(url, timeout=15)
        if resp.status_code != 200:
            return False

        # Явно указываем кодировку windows-1251
        resp.encoding = 'windows-1251'
        soup = BeautifulSoup(resp.text, 'html.parser')

        # Ищем все строки с классом anime_review
        review_items = soup.find_all('p', class_='anime_review')
        for p in review_items:
            text = p.text.strip()
            if 'Тип:' in text:
                # Извлекаем значение после "Тип:"
                type_value = text.split('Тип:')[-1].strip()
                # Проверяем, что это фильм
                if re.search(r'^(Фильм|Movie)', type_value, re.IGNORECASE):
                    return True
                else:
                    return False
        return False
    except Exception as e:
        print(f"   ❌ Ошибка проверки типа для {anime_id}: {e}")
        return False

# ==========================================================
# СБОР СПИСКА АНИМЕ ЗА ГОД (ТОЛЬКО ФИЛЬМЫ)
# ==========================================================
def get_movies_list(year, page=1):
    """Возвращает список фильмов для указанного года и страницы."""
    url = f"{BASE_URL}/index.php?f={year}&s=2"
    if page > 1:
        url += f"&page={page}"
    try:
        resp = session.get(url, timeout=15)
        if resp.status_code != 200:
            return []

        # Указываем кодировку
        resp.encoding = 'windows-1251'
        soup = BeautifulSoup(resp.text, 'html.parser')

        cards = soup.find_all('div', class_='anime_card')
        if not cards:
            return []  # нет аниме на этой странице

        movies = []
        for card in cards:
            link = card.find('a', class_='card_link')
            if not link:
                continue
            href = link.get('href')
            if not href or 'anime.php?id=' not in href:
                continue
            anime_id = re.search(r'id=(\d+)', href).group(1)

            # Проверяем, что это фильм
            if not is_movie(anime_id):
                continue

            title_tag = link.find('h2')
            title = title_tag.text.strip() if title_tag else "Без названия"

            img_container = card.find('div', class_='img_container')
            poster_url = None
            if img_container:
                img = img_container.find('img')
                if img and img.get('src'):
                    poster_url = urljoin(BASE_URL, img.get('src'))

            movies.append({
                'id': anime_id,
                'title': title,
                'poster_url': poster_url,
                'year': year
            })
        return movies
    except Exception as e:
        print(f"   ❌ Ошибка загрузки {url}: {e}")
        return []

# ==========================================================
# ПОЛУЧЕНИЕ СПИСКА СЕРИЙ (ДЛЯ ФИЛЬМА ОБЫЧНО ТОЛЬКО 1)
# ==========================================================
def get_episodes(anime_id):
    url = f"{BASE_URL}/anime.php?id={anime_id}"
    try:
        resp = session.get(url, timeout=15)
        if resp.status_code != 200:
            return []

        resp.encoding = 'windows-1251'
        soup = BeautifulSoup(resp.text, 'html.parser')
        episode_block = soup.find('div', id='episode_list')
        if not episode_block:
            return []

        episodes = []
        for div in episode_block.find_all('div'):
            a_tag = div.find('a', href=True)
            if not a_tag:
                continue
            href = a_tag.get('href')
            if 'download.php?file=' not in href:
                continue

            text = a_tag.text.strip()
            # Для фильмов может быть просто "Скачать MP4" без номера серии
            match = re.search(r'(\d+)\s*серия', text, re.IGNORECASE)
            ep_num = int(match.group(1)) if match else 1  # по умолчанию 1

            episodes.append({
                'ep_num': ep_num,
                'download_url': urljoin(BASE_URL, href)
            })
        return episodes
    except Exception as e:
        print(f"   ❌ Ошибка загрузки серий для {anime_id}: {e}")
        return []

# ==========================================================
# ОСНОВНАЯ ЛОГИКА
# ==========================================================
def main():
    print("=" * 70)
    print("🎬 СБОР АНИМЕ-ФИЛЬМОВ С MP4ANIME.COM (1971–2026)")
    print("=" * 70)

    # Загружаем прогресс
    processed = set()
    if os.path.exists(PROGRESS_FILE):
        with open(PROGRESS_FILE, 'r') as f:
            processed = set(json.load(f))

    all_movies = []
    years = range(1971, 2027)

    for year in years:
        print(f"\n📅 Сбор фильмов за {year} год...")
        page = 1
        year_movies = []

        while True:
            print(f"   📄 Страница {page}...")
            movies = get_movies_list(year, page)
            if not movies:
                # Если на первой странице нет аниме, значит год пустой
                if page == 1:
                    print(f"      ℹ️ Нет аниме за {year} год")
                else:
                    print(f"      ℹ️ Больше страниц нет")
                break

            # Фильтруем уже обработанные
            new_items = [m for m in movies if m['id'] not in processed]
            year_movies.extend(new_items)
            print(f"      ✅ Найдено новых фильмов: {len(new_items)} из {len(movies)}")

            # Проверяем, есть ли следующая страница
            # Если на странице меньше 12 аниме, значит это последняя
            if len(movies) < 12:
                break
            page += 1
            time.sleep(1)

        all_movies.extend(year_movies)
        if year_movies:
            print(f"   📊 Всего за {year} год: {len(year_movies)} новых фильмов")
        time.sleep(1)

    print(f"\n📊 Всего новых фильмов: {len(all_movies)}")

    if not all_movies:
        print("Новых фильмов нет, завершаем.")
        return

    # ==========================================================
    # СОЗДАЁМ M3U
    # ==========================================================
    with open(OUTPUT_M3U, 'w', encoding='utf-8') as f:
        f.write('#EXTM3U\n\n')

        # Сортируем по году
        all_movies.sort(key=lambda x: int(x['year']))

        for idx, movie in enumerate(all_movies, 1):
            year = movie['year']
            title = movie['title']
            anime_id = movie['id']
            poster_url = movie['poster_url']

            print(f"\n[{idx}/{len(all_movies)}] {title} ({year})")

            # Постер
            poster_path = None
            if poster_url:
                poster_path = download_poster(poster_url, anime_id)
                if poster_path:
                    print(f"   🖼️ Постер сохранён")

            # Серии
            episodes = get_episodes(anime_id)
            if not episodes:
                print(f"   ⚠️ Серии не найдены")
                processed.add(anime_id)
                continue

            print(f"   📺 Найдено серий: {len(episodes)}")

            for ep in episodes:
                ep_num = ep['ep_num']
                download_url = ep['download_url']

                print(f"      Серия {ep_num}: получение ссылки...")
                direct_link = get_direct_link(download_url)

                if direct_link:
                    # Для фильмов обычно 1 серия, но если их несколько
                    ep_label = f"{ep_num} серия" if len(episodes) > 1 else "фильм"
                    display_name = f"{title} ({year}) - {ep_label}"
                    safe_title = display_name.replace('"', "'")
                    poster_ref = os.path.basename(poster_path) if poster_path else ""

                    # Группируем по году
                    f.write(f'#EXTINF:-1 group-title="Фильмы {year}" tvg-logo="{poster_ref}", {safe_title}\n')
                    f.write(f'{direct_link}\n\n')
                    print(f"         ✅ OK")
                else:
                    print(f"         ❌ Не удалось получить ссылку")

                time.sleep(1)

            processed.add(anime_id)

    # Сохраняем прогресс
    with open(PROGRESS_FILE, 'w') as f:
        json.dump(list(processed), f)

    print(f"\n🎉 Готово! Плейлист сохранён: {OUTPUT_M3U}")
    print(f"📁 Постеры сохранены в {POSTERS_DIR}")
    print(f"📊 Всего фильмов: {len(all_movies)}")

if __name__ == "__main__":
    main()
