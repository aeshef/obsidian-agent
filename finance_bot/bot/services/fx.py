import httpx
from datetime import datetime, timedelta

_cached = {"usd_rub": None, "ts": None}


async def get_usd_rub() -> float:
    global _cached
    now = datetime.utcnow()
    if _cached["usd_rub"] and _cached["ts"] and now - _cached["ts"] < timedelta(minutes=30):
        return _cached["usd_rub"]
    url = "https://www.cbr-xml-daily.ru/daily_json.js"
    async with httpx.AsyncClient(timeout=10.0) as client:
        r = await client.get(url)
        r.raise_for_status()
        data = r.json()
        usd = data.get("Valute", {}).get("USD", {}).get("Value")
        if not usd:
            raise RuntimeError("USD rate not found")
        _cached["usd_rub"] = float(usd)
        _cached["ts"] = now
        return _cached["usd_rub"]
