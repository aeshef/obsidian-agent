import httpx
from typing import Dict, List
from .fx import get_usd_rub

# Minimal mapping; extend as needed
SYMBOL_TO_CGID = {
    "BTC": "bitcoin",
    "ETH": "ethereum",
    "USDT": "tether",
    "WBTC": "wrapped-bitcoin",
}


async def fetch_prices_usd(symbols: List[str]) -> Dict[str, float]:
    ids = [SYMBOL_TO_CGID[s] for s in symbols if s in SYMBOL_TO_CGID]
    if not ids:
        return {}
    url = "https://api.coingecko.com/api/v3/simple/price"
    params = {"ids": ",".join(ids), "vs_currencies": "usd"}
    async with httpx.AsyncClient(timeout=10.0) as client:
        r = await client.get(url, params=params)
        r.raise_for_status()
        data = r.json()
    out: Dict[str, float] = {}
    for sym, cg in SYMBOL_TO_CGID.items():
        if cg in data and "usd" in data[cg]:
            out[sym] = float(data[cg]["usd"])
    return out


async def fetch_prices_rub(symbols: List[str]) -> Dict[str, float]:
    usd_prices = await fetch_prices_usd(symbols)
    usd_rub = await get_usd_rub()
    return {s: p * usd_rub for s, p in usd_prices.items()}
