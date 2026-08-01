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
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
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
    """Загружает капчу и распознаёт 3‑значный цифровой код."""
    try:
        resp = session.get(img_url, timeout=10)
        if resp.status_code != 200:
            return None
        img = Image.open(BytesIO(resp.content)).convert('L')
        # Пороговая обработка для лучшего распознавания
        img = img.point(lambda x: 0 if x < 128 else 255, '1')
        code = pytesseract.image_to_string(img, config='--psm 8 -c tessedit_char_whitelist=0123456789')
        code = re.sub(r'\D', '', code).strip()
        return code if len(code) == 3 else None
    except Exception as e:
        print(f"   ❌ Ошибка капчи: {e}")
        return None

# ==========================================================
# ПОЛУЧЕНИЕ ПРЯМОЙ ССЫЛКИ НА MP4
# ==========================================================
def get_direct_link(download_url, retries=3):
    """Решает капчу и возвращает прямую ссылку на видео."""
    for attempt in range(retries):
        try:
            resp = session.get(download_url, timeout=15)
            if resp.status_code != 200:
                continue

            resp.encoding = 'windows-1251'
            soup = BeautifulSoup(resp.text, 'html.parser')

            form = soup.find('form')
            if not form:
                continue

            # Собираем все hidden-поля (включая caps и d)
            form_data = {}
            for inp in form.find_all('input', type='hidden'):
                name = inp.get('name')
                if name:
                    form_data[name] = inp.get('value', '')

            cap_img = soup.find('img', class_='img_caps')
            if not cap_img:
                continue

            cap_url = urljoin(BASE_URL, cap_img.get('src'))
            code = solve_captcha(cap_url)
            if not code:
                continue

            form_data['com_cod'] = code
            action_url = urljoin(download_url, form.get('action', ''))

            post_resp = session.post(action_url, data=form_data, timeout=15)
            post_resp.encoding = 'windows-1251'

            soup_result = BeautifulSoup(post_resp.text, 'html.parser')

            # Ищем ссылку на скачивание (dl.php или .mp4)
            dl_link = soup_result.find('a', href=re.compile(r'\.mp4$|dl\.php\?file='))
            if dl_link:
                return urljoin(BASE_URL, dl_link.get('href'))

            mp4_links = re.findall(r'href=[\'"]?([^\'" >]+\.mp4[^\'" >]*)', post_resp.text)
            if mp4_links:
                return urljoin(BASE_URL, mp4_links[0])

        except Exception as e:
            print(f"   ❌ Ошибка при получении ссылки: {e}")

        time.sleep(1)
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
# ПРОВЕРКА: ЭТО ФИЛЬМ?
# ==========================================================
def is_movie(anime_id):
    """Проверяет страницу аниме на предмет типа 'Фильм'."""
    url = f"{BASE_URL}/anime.php?id={anime_id}"
    try:
        resp = session.get(url, timeout=15)
        if resp.status_code != 200:
            return False

        resp.encoding = 'windows-1251'
        soup = BeautifulSoup(resp.text, 'html.parser')

        # Ищем блок с типом
        for p in soup.find_all('p', class_='anime_review'):
            text = p.text.strip()
            if 'Тип:' in text:
                type_val = text.replace('Тип:', '').strip()
                # Проверяем на наличие слова "Фильм" или "Movie"
                if re.search(r'фильм|movie|полнометраж', type_val, re.IGNORECASE):
                    return True
                return False
        return False
    except Exception as e:
        print(f"   ❌ Ошибка проверки типа для ID {anime_id}: {e}")
        return False

# ==========================================================
# СБОР СНИППЕТОВ ЗА ГОД
# ==========================================================
def get_movies_from_page(year, page):
    """Возвращает (список_фильмов, количество_карточек_на_странице)."""
    url = f"{BASE_URL}/index.php?f={year}&s=2&page={page}"
    try:
        resp = session.get(url, timeout=15)
        if resp.status_code != 200:
            return [], 0

        resp.encoding = 'windows-1251'
        soup = BeautifulSoup(resp.text, 'html.parser')

        cards = soup.find_all('td', class_='anime_card')
        if not cards:
            cards = soup.find_all('div', class_='anime_card')

        total_cards = len(cards)
        if total_cards == 0:
            return [], 0

        movies = []
        for card in cards:
            link = card.find('a', class_='card_link')
            if not link or not link.get('href'):
                continue

            href = link.get('href')
            match_id = re.search(r'id=(\d+)', href)
            if not match_id:
                continue

            anime_id = match_id.group(1)

            # Фильтруем: пропускаем, если это не фильм
            if not is_movie(anime_id):
                continue

            h2 = card.find('h2')
            title = h2.text.strip() if h2 else "Без названия"

            img = card.find('img', class_='poster')
            poster_url = urljoin(BASE_URL, img.get('src')) if img and img.get('src') else None

            movies.append({
                'id': anime_id,
                'title': title,
                'poster_url': poster_url,
                'year': year
            })

        return movies, total_cards

    except Exception as e:
        print(f"   ❌ Ошибка загрузки страницы {page} за {year} год: {e}")
        return [], 0

# ==========================================================
# ПОЛУЧЕНИЕ ССЫЛОК СКАЧИВАНИЯ СО Страницы АНИМЕ
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
            if not a_tag or 'download.php?file=' not in a_tag['href']:
                continue

            text = a_tag.text.strip()
            match = re.search(r'(\d+)\s*серия', text, re.IGNORECASE)
            ep_num = int(match.group(1)) if match else 1

            episodes.append({
                'ep_num': ep_num,
                'download_url': urljoin(BASE_URL, a_tag['href'])
            })
        return episodes
    except Exception as e:
        print(f"   ❌ Ошибка серий для ID {anime_id}: {e}")
        return []

# ==========================================================
# MAIN
# ==========================================================
def main():
    print("=" * 70)
    print("🎬 СБОР АНИМЕ-ФИЛЬМОВ С MP4ANIME.COM (1971–2026)")
    print("=" * 70)

    processed = set()
    if os.path.exists(PROGRESS_FILE):
        with open(PROGRESS_FILE, 'r', encoding='utf-8') as f:
            processed = set(json.load(f))

    all_movies = []

    for year in range(1971, 2027):
        print(f"\n📅 Обход {year} года...")
        page = 1
        year_movies_count = 0

        while True:
            movies, total_cards = get_movies_from_page(year, page)

            if total_cards == 0:
                if page == 1:
                    print(f"   ℹ️ Нет аниме за {year} год")
                break

            new_items = [m for m in movies if m['id'] not in processed]
            all_movies.extend(new_items)
            year_movies_count += len(new_items)

            print(f"   📄 Стр. {page}: найдено фильмов {len(movies)} (из {total_cards} карточек)")

            # Прерываем цикл только если на ВСЕЙ странице было меньше 12 карточек
            if total_cards < 12:
                break

            page += 1
            time.sleep(0.5)

        if year_movies_count > 0:
            print(f"   📊 Всего новых фильмов за {year}: {year_movies_count}")

    print(f"\n📊 Итого новых фильмов для обработки: {len(all_movies)}")

    if not all_movies:
        print("Завершено. Новых фильмов не найдено.")
        return

    # Запись в M3U
    with open(OUTPUT_M3U, 'a', encoding='utf-8') as f:
        if os.path.getsize(OUTPUT_M3U) == 0 if os.path.exists(OUTPUT_M3U) else True:
            f.write('#EXTM3U\n\n')

        for idx, movie in enumerate(all_movies, 1):
            title = movie['title']
            year = movie['year']
            anime_id = movie['id']
            poster_url = movie['poster_url']

            print(f"\n[{idx}/{len(all_movies)}] {title} ({year})")

            poster_path = download_poster(poster_url, anime_id) if poster_url else None
            episodes = get_episodes(anime_id)

            if not episodes:
                print("   ⚠️ Ссылки на файлы не найдены")
                processed.add(anime_id)
                continue

            for ep in episodes:
                ep_label = f"{ep['ep_num']} серия" if len(episodes) > 1 else "фильм"
                print(f"   ⏳ Получение прямой ссылки ({ep_label})...")

                direct_link = get_direct_link(ep['download_url'])
                if direct_link:
                    display_name = f"{title} ({year}) - {ep_label}"
                    poster_ref = os.path.basename(poster_path) if poster_path else ""

                    f.write(f'#EXTINF:-1 group-title="Фильмы {year}" tvg-logo="{poster_ref}", {display_name}\n')
                    f.write(f'{direct_link}\n\n')
                    f.flush()
                    print(f"      ✅ Ссылка получена: {direct_link}")
                else:
                    print(f"      ❌ Не удалось обойти капчу")

                time.sleep(1)

            processed.add(anime_id)
            with open(PROGRESS_FILE, 'w', encoding='utf-8') as pf:
                json.dump(list(processed), pf)

    print(f"\n🎉 Обработка завершена! Файл сохранена в {OUTPUT_M3U}")

if __name__ == "__main__":
    main()
