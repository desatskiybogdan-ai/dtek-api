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
    url = "https://www.dtek-oem.com.ua/ua/ajax"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "X-Requested-With": "XMLHttpRequest",
        "Referer": "https://www.dtek-oem.com.ua/ua/shutdowns",
    }
    payload = {
        "method": "getHomeNum",
        "data[0][name]": "city",
        "data[0][value]": "м. Подільськ",
        "data[1][name]": "street",
        "data[1][value]": "вул. Петра Дорошенка",
        "data[2][name]": "updateFact",
        "data[2][value]": time.strftime("%d.%m.%Y %H:%M"),
    }

    async with httpx.AsyncClient(timeout=20.0, follow_redirects=True) as client:
        await client.get("https://www.dtek-oem.com.ua/ua/shutdowns", headers=headers)
        resp = await client.post(url, data=payload, headers=headers)

        if resp.status_code != 200:
            return {
                "status": "warn",
                "title": "Сайт ДТЕК тимчасово недоступний",
                "description": f"Код відповіді сервера ДТЕК: {resp.status_code}",
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
            
