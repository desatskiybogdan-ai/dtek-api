import time
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from playwright.sync_api import sync_playwright

app = FastAPI()

# Разрешаем запросы с вашего сайта на Netlify (обход блокировки CORS)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Кэш, чтобы не нагружать сайт ДТЕК при частых обновлениях страницы (5 минут)
CACHE = {"data": None, "timestamp": 0}
CACHE_TTL = 300


def parse_dtek():
    with sync_playwright() as p:
        # Запускаем скрытый браузер Chromium
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        page = context.new_page()

        try:
            page.goto("https://www.dtek-oem.com.ua/ua/shutdowns", timeout=60000)
            page.wait_for_timeout(3000)

            # Закрываем всплывающее окно, если оно появилось
            close_btn = page.locator(".modal__close, .btn-close").first
            if close_btn.is_visible():
                close_btn.click()

            # 1. Вводим населенный пункт: м. Подільськ
            city_input = page.locator("#city")
            city_input.fill("м. Подільськ")
            page.wait_for_timeout(1500)
            page.locator("#cityautocomplete-list div").first.click()

            # 2. Вводим улицу: вул. Петра Дорошенка
            street_input = page.locator("#street")
            street_input.fill("вул. Петра Дорошенка")
            page.wait_for_timeout(1500)
            page.locator("#streetautocomplete-list div").first.click()

            # 3. Вводим номер дома: 18
            house_input = page.locator("#house_num")
            house_input.fill("18")
            page.wait_for_timeout(1500)
            page.locator("#house_numautocomplete-list div").first.click()

            # Ждем подгрузки результата с сайта ДТЕК
            page.wait_for_timeout(3000)

            # Считываем блок с информацией об отключении
            result_block = page.locator("#showCurOutage")
            raw_text = result_block.inner_text().strip() if result_block.is_visible() else ""

            # Определяем статус для вашего HTML-приложения
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

        except Exception as e:
            return {
                "status": "warn",
                "title": "Помилка отримання даних",
                "description": f"Не вдалося оновити дані з сайту ДТЕК: {str(e)}",
                "group": ""
            }
        finally:
            browser.close()


@app.get("/api/dtek-podilsk")
def get_schedule():
    now = time.time()
    if CACHE["data"] and (now - CACHE["timestamp"] < CACHE_TTL):
        return CACHE["data"]

    fresh_data = parse_dtek()
    CACHE["data"] = fresh_data
    CACHE["timestamp"] = now
    return fresh_data
