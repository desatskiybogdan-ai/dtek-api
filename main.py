@app.get("/api/debug-dtek")
async def debug_dtek():
    base_url = "https://www.dtek-oem.com.ua/ua/shutdowns"
    ajax_url = "https://www.dtek-oem.com.ua/ua/ajax"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "uk-UA,uk;q=0.9",
    }
    async with httpx.AsyncClient(timeout=20.0, follow_redirects=True) as client:
        init_resp = await client.get(base_url, headers=headers)
        token_match = re.search(r'<meta\s+name="csrf-token"\s+content="([^"]+)"', init_resp.text)
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
        raw = resp.json()
        return {
            "house_18": raw.get("data", {}).get("18"),
            "keys": list(raw.keys()),
            "preset_sample": str(raw.get("preset", ""))[:1000],
            "fact_sample": str(raw.get("fact", ""))[:1000],
        }
