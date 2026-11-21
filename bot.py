import asyncio
import aiohttp
from aiohttp_socks import ProxyConnector
import logging
import random
import sys

# Настройка логирования
logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger('TwitchBot')

CHANNEL_NAME = "denmiten36"
GQL_URL = "https://gql.twitch.tv/gql"
CLIENT_ID = "kimne78kx3ncx6brgo4mv6wki5h1ko"  # Публичный Web Client-ID Twitch

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64; rv:123.0) Gecko/20100101 Firefox/123.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2.1 Safari/605.1.15",
]

async def get_stream_tokens(session):
    """Получает токен и подпись для доступа к стриму через GQL API Twitch"""
    payload = [{
        "operationName": "PlaybackAccessToken_Anonymous",
        "extensions": {
            "persistedQuery": {
                "version": 1,
                "sha256Hash": "0828119ded1c13477966434e15800ff571fc133fb81a1bde72f89bab6649d80f"
            }
        },
        "variables": {
            "isLive": True,
            "login": CHANNEL_NAME,
            "vodID": "",
            "playerType": "embed"
        }
    }]
    headers = {
        "Client-ID": CLIENT_ID,
        "User-Agent": random.choice(USER_AGENTS)
    }
    
    try:
        async with session.post(GQL_URL, json=payload, headers=headers, timeout=10) as resp:
            if resp.status == 200:
                data = await resp.json()
                stream_data = data[0]['data']['streamPlaybackAccessToken']
                return stream_data['value'], stream_data['signature']
    except Exception as e:
        logger.error(f"Ошибка получения GQL токена: {e}")
    return None, None

async def get_master_playlist(session, token, signature):
    """Запрашивает мастер-плейлист HLS (.m3u8)"""
    usher_url = f"https://usher.ttvnw.net/api/channel/hls/{CHANNEL_NAME}.m3u8"
    params = {
        "sig": signature,
        "token": token,
        "player_backend": "mediaplayer",
        "supported_codecs": "avc1",
        "time": random.randint(100000, 999999)
    }
    try:
        async with session.get(usher_url, params=params, timeout=10) as resp:
            if resp.status == 200:
                return await resp.text()
    except Exception as e:
        logger.error(f"Ошибка получения плейлиста: {e}")
    return None

async def worker(proxy_url):
    """Воркер одного зрителя: держит соединение и запрашивает чанки"""
    # Создаем коннектор с поддержкой прокси (socks5:// или http://)
    try:
        connector = ProxyConnector.from_url(proxy_url)
    except Exception as e:
        logger.error(f"Неверный формат прокси {proxy_url}: {e}")
        return

    headers = {"User-Agent": random.choice(USER_AGENTS)}

    async with aiohttp.ClientSession(connector=connector, headers=headers) as session:
        logger.info(f"[{proxy_url}] Подключение к каналу {CHANNEL_NAME}...")
        
        while True:
            token, signature = await get_stream_tokens(session)
            if not token or not signature:
                logger.warning(f"[{proxy_url}] Не удалось получить токены, повтор через 10 сек...")
                await asyncio.sleep(10)
                continue
                
            playlist = await get_master_playlist(session, token, signature)
            if not playlist:
                logger.warning(f"[{proxy_url}] Не удалось получить мастер-плейлист, повтор...")
                await asyncio.sleep(10)
                continue
                
            # Ищем в плейлисте строчку с минимальным качеством (audio_only или 160p) для экономии трафика
            lines = playlist.splitlines()
            media_url = None
            for i, line in enumerate(lines):
                if "AUDIO" in line or "160p" in line or "chunked" in line:
                    if i + 1 < len(lines):
                        media_url = lines[i + 1]
                        break
            
            if not media_url and len(lines) > 0:
                # Берем первую попавшуюся ссылку на медиа-плейлист
                for line in lines:
                    if line.startswith("http"):
                        media_url = line
                        break

            if media_url:
                try:
                    # Запрашиваем медиа-плейлист (имитируем загрузку сегментов)
                    async with session.get(media_url, timeout=10) as media_resp:
                        if media_resp.status == 200:
                            logger.info(f"[{proxy_url}] Пакет данных успешно запрошен, просмотр идет.")
                except Exception as e:
                    logger.debug(f"[{proxy_url}] Ошибка запроса чанка: {e}")

            # Twitch обновляет чанки примерно каждые 2-4 секунды
            await asyncio.sleep(3.5)

async def main():
    # Загружаем прокси из файла proxies.txt (по одному на строку, например: socks5://123.45.67.89:1080)
    try:
        with open("proxies.txt", "r") as f:
            proxies = [line.strip() for line in f if line.strip() and not line.startswith("#")]
    except FileNotFoundError:
        logger.error("Файл proxies.txt не найден! Создай его и добавь прокси в формате socks5://ip:port")
        return

    if not proxies:
        logger.error("Список прокси пуст!")
        return

    logger.info(f"Загружено прокси: {len(proxies)}. Запуск симуляции зрителей...")
    
    tasks = [asyncio.create_task(worker(proxy)) for proxy in proxies]
    await asyncio.gather(*tasks)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Скрипт остановлен пользователем.")