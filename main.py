import asyncio
import os
import re
import time
import httpx
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

CACHE = {"data": None, "timestamp": 0}
CACHE_TTL = 300
LAST_STATUS = None

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "").strip()


async def send_telegram(text: str):
    if not BOT_TOKEN or not CHAT_ID:
        return False
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    async with httpx.AsyncClient(timeout=15.0) as client:
        r = await client.post(url, json={"chat_id": CHAT_ID, "text": text})
        return r.status_code == 200


async def raw_dtek_request():
    base_url = "https://www.dtek-oem.com.ua/ua/shutdowns"
    ajax_url = "https://www.dtek-oem.com.ua/ua/ajax"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "uk-UA,uk;q=0.9",
    }
    async with httpx.AsyncClient(timeout=20.0, follow_redirects=True) as client:
        init_resp = await client.get(base_url, headers=headers)
        html = init_resp.text
        token_match = re.search(r'<meta\s+name="csrf-token"\s+content="([^"]+)"', html)
        csrf_token = token_match.group(1) if token_match else ""

        ajax_headers = {
            "User-Agent": headers["User-Agent"],
            "Accept": "application/json, text/javascript, */*; q=0.01",
            "X-Requested-With": "XMLHttpRequest",
            "Origin": "https://www.dtek-oem.com.ua",
            "Referer": base_url,
        }
        if csrf_token:
            ajax_headers["X-CSRF-Token"] = csrf_token

        payload = {
            "method": "getHomeNum",
            "data[0][name]": "city",
            "data[0][value]": "м. Подільськ",
            "data[1][name]": "street",
            "data[1][value]": "вул. Петра Дорошенка",
            "data[2][name]": "updateFact",
            "data[2][value]": time.strftime("%d.%m.%Y %H:%M"),
        }
        resp = await client.post(ajax_url, data=payload, headers=ajax_headers)
        return resp.status_code, resp.text, html


async def fetch_dtek():
    code, text, _ = await raw_dtek_request()
    if code != 200:
        return {
            "status": "warn",
            "title": "Сайт ДТЕК відхилив запит",
            "description": f"Код відповіді: {code}",
            "group": "м. Подільськ",
        }
    try:
        data = httpx.Response(200, text=text).json()
    except Exception:
        return {
            "status": "warn",
            "title": "Потрібна перевірка захисту ДТЕК",
            "description": "Сайт ДТЕК повернув сторінку перевірки замість JSON.",
            "group": "м. Подільськ",
        }

    houses = data.get("data", {})
    house_info = houses.get("18") if isinstance(houses, dict) else None
    if not house_info:
        return {
            "status": "on",
            "title": "Світло є",
            "description": "За адресою м. Подільськ, вул. Петра Дорошенка, 18 наразі відключень не зафіксовано.",
            "group": "м. Подільськ",
        }

    sub_type = str(house_info.get("sub_type", "")).strip()
    start_date = str(house_info.get("start_date", "")).strip()
    end_date = str(house_info.get("end_date", "")).strip()
    if sub_type:
        desc = f"Причина: {sub_type}."
        if start_date or end_date:
            desc += f" Час: {start_date} — {end_date}."
        return {
            "status": "off",
            "title": "Зафіксовано відключення",
            "description": desc,
            "group": "м. Подільськ",
        }

    return {
        "status": "on",
        "title": "Світло є",
        "description": "Активних відключень по будинку №18 не знайдено.",
        "group": "м. Подільськ",
    }


async def check_and_notify():
    global LAST_STATUS
    fresh = await fetch_dtek()
    CACHE["data"] = fresh
    CACHE["timestamp"] = time.time()

    current_status = fresh.get("status")
    if LAST_STATUS is not None and current_status != LAST_STATUS:
        emoji = "🟢" if current_status == "on" else ("🔴" if current_status == "off" else "🟡")
        await send_telegram(
            f"{emoji} {fresh.get('title')}\n"
            f"Адреса: м. Подільськ, вул. Петра Дорошенка, 18\n"
            f"{fresh.get('description')}"
        )
    LAST_STATUS = current_status
    return fresh


async def watcher_loop():
    await asyncio.sleep(5)
    while True:
        try:
            await check_and_notify()
        except Exception:
            pass
        await asyncio.sleep(300)


@app.on_event("startup")
async def on_startup():
    asyncio.create_task(watcher_loop())


@app.get("/api/debug-dtek")
async def debug_dtek():
    code, text, html = await raw_dtek_request()
    raw = httpx.Response(200, text=text).json()
    preset_match = re.search(r"DisconSchedule\.preset\s*=\s*(\{.*?\});", html, re.S)
    fact_match = re.search(r"DisconSchedule\.fact\s*=\s*(\{.*?\});", html, re.S)
    return {
        "house_18": raw.get("data", {}).get("18"),
        "raw_keys": list(raw.keys()),
        "has_preset": bool(preset_match),
        "has_fact": bool(fact_match),
        "fact_head": fact_match.group(1)[:600] if fact_match else None,
    }


@app.get("/api/dtek-podilsk")
async def get_schedule():
    now = time.time()
    if CACHE["data"] and (now - CACHE["timestamp"] < CACHE_TTL):
        return CACHE["data"]
    return await check_and_notify()


@app.get("/api/test-telegram")
async def test_telegram():
    ok = await send_telegram("✅ Тест повідомлення: бот Подільськ (вул. Петра Дорошенка, 18) підключено.")
    return {"sent": ok}


@app.get("/")
async def root():
    return await get_schedule()
