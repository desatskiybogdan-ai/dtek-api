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


async def fetch_dtek():
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

        # Ищем CSRF-токен в мета-тегах страницы ДТЕК
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

        if resp.status_code != 200:
            return {
                "status": "warn",
                "title": "Сайт ДТЕК відхилив запит",
                "description": f"Код відповіді: {resp.status_code} (CSRF знайдено: {bool(csrf_token)})",
                "group": "м. Подільськ",
            }

        try:
            data = resp.json()
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


@app.get("/api/dtek-podilsk")
async def get_schedule():
    now = time.time()
    if CACHE["data"] and (now - CACHE["timestamp"] < CACHE_TTL):
        return CACHE["data"]

    try:
        fresh_data = await fetch_dtek()
        CACHE["data"] = fresh_data
        CACHE["timestamp"] = now
        return fresh_data
    except Exception as e:
        return {
            "status": "warn",
            "title": "Помилка з'єднання з ДТЕК",
            "description": str(e),
            "group": "м. Подільськ",
        }


@app.get("/")
async def root():
    return await get_schedule()
            
