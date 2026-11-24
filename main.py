import time
import traceback
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from playwright.async_api import async_playwright

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

CACHE = {"data": None, "timestamp": 0}
CACHE_TTL = 300


async def parse_dtek():
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu", "--single-process"]
        )
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        page = await context.new_page()

        try:
            await page.goto("https://www.dtek-oem.com.ua/ua/shutdowns", timeout=60000)
            await page.wait_for_timeout(3000)

            close_btn = page.locator(".modal__close, .btn-close").first
            if await close_btn.is_visible():
                await close_btn.click()

            city_input = page.locator("#city")
            await city_input.fill("м. Подільськ")
            await page.wait_for_timeout(1500)
            await page.locator("#cityautocomplete-list div").first.click()

            street_input = page.locator("#street")
            await street_input.fill("вул. Петра Дорошенка")
            await page.wait_for_timeout(1500)
            await page.locator("#streetautocomplete-list div").first.click()

            house_input = page.locator("#house_num")
            await house_input.fill("18")
            await page.wait_for_timeout(1500)
            await page.locator("#house_numautocomplete-list div").first.click()

            await page.wait_for_timeout(3000)

            result_block = page.locator("#showCurOutage")
            raw_text = (await result_block.inner_text()).strip() if await result_block.is_visible() else ""

            lower_text = raw_text.lower()
            if not raw_text or "відключень не зафіксовано" in lower_text:
                status = "on"
                title = "Світло є"
                description = raw_text or "За вказаною адресою наразі відключень не зафіксовано."
            elif "стабілізаційне" in lower_text or "аварійне" in lower_text or "екстрене" in lower_text:
                status = "off"
                title = "Зафіксовано відключення"
                description = raw_text
            else:
                status = "warn"
                title = "Увага / Можливі зміни"
                description = raw_text

            return {
                "status": status,
                "title": title,
                "description": description,
                "group": "м. Подільськ"
            }
        finally:
            await browser.close()


@app.get("/api/dtek-podilsk")
async def get_schedule():
    now = time.time()
    if CACHE["data"] and (now - CACHE["timestamp"] < CACHE_TTL):
        return CACHE["data"]

    try:
        fresh_data = await parse_dtek()
        CACHE["data"] = fresh_data
        CACHE["timestamp"] = now
        return fresh_data
    except Exception as e:
        return {
            "status": "warn",
            "title": "Помилка парсингу",
            "description": str(e),
            "trace": traceback.format_exc().splitlines()[-3:],
            "group": ""
        }
