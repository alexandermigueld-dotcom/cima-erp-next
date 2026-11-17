from __future__ import annotations

import json
import statistics
import urllib.request
from typing import Any


DEFAULT_DOLARAPI_URL = "https://ve.dolarapi.com/v1/dolares"
DEFAULT_BINANCE_P2P_URL = "https://p2p.binance.com/bapi/c2c/v2/friendly/c2c/adv/search"

BRECHA_SOURCE_BINANCE = "Binance USDT"
BRECHA_SOURCE_MONITOR = "Monitor / Paralelo"
BRECHA_SOURCE_MANUAL = "Manual"


def fetch_dolarapi_rates(timeout: int = 8, url: str = DEFAULT_DOLARAPI_URL) -> dict[str, Any]:
    """Obtiene tasas oficial (BCV) y paralelo (Monitor) desde ve.dolarapi.com."""
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "CimaVE-ERPNext/1.0",
            "Accept": "application/json",
        },
        method="GET",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        raw = resp.read().decode("utf-8")
    data = json.loads(raw)
    if not isinstance(data, list):
        raise ValueError("Respuesta inesperada de DolarAPI.")

    bcv_rate = 0.0
    monitor_rate = 0.0
    updated_at = ""
    for item in data:
        if not isinstance(item, dict):
            continue
        fuente = str(item.get("fuente") or item.get("nombre") or "").strip().lower()
        promedio = float(item.get("promedio") or item.get("venta") or item.get("compra") or 0.0)
        if promedio <= 0:
            continue
        if "oficial" in fuente or "bcv" in fuente:
            bcv_rate = round(promedio, 4)
            updated_at = str(item.get("fechaActualizacion") or updated_at)
        elif "paralelo" in fuente or "monitor" in fuente:
            monitor_rate = round(promedio, 4)
            if not updated_at:
                updated_at = str(item.get("fechaActualizacion") or "")

    return {
        "bcv_rate": bcv_rate,
        "monitor_rate": monitor_rate,
        "updated_at": updated_at,
    }


def parse_binance_p2p_ads(payload: dict[str, Any]) -> float:
    """Calcula la mediana de los anuncios P2P USDT/VES devueltos por Binance."""
    ads = payload.get("data") if isinstance(payload, dict) else None
    if not isinstance(ads, list) or not ads:
        return 0.0

    prices: list[float] = []
    for entry in ads:
        if not isinstance(entry, dict):
            continue
        adv = entry.get("adv") or {}
        try:
            price = float(adv.get("price") or 0.0)
        except (TypeError, ValueError):
            price = 0.0
        if price > 0:
            prices.append(price)

    if not prices:
        return 0.0
    if len(prices) >= 5:
        prices.sort()
        trimmed = prices[1:-1]
        return round(float(statistics.median(trimmed)), 4)
    return round(float(statistics.median(prices)), 4)


def fetch_binance_p2p_usdt_ves(
    timeout: int = 8,
    rows: int = 10,
    url: str = DEFAULT_BINANCE_P2P_URL,
) -> float:
    """Consulta el libro de órdenes público de Binance P2P para USDT/VES."""
    body = json.dumps(
        {
            "fiat": "VES",
            "page": 1,
            "rows": rows,
            "tradeType": "BUY",
            "asset": "USDT",
            "countries": [],
            "proMerchantAds": False,
            "shieldMerchantAds": False,
            "publisherType": None,
            "payTypes": [],
        }
    ).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=body,
        headers={
            "Content-Type": "application/json",
            "User-Agent": "Mozilla/5.0",
            "Accept": "application/json",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        raw = resp.read().decode("utf-8")
    payload = json.loads(raw)
    return parse_binance_p2p_ads(payload)


def calculate_brecha_and_adjusted_rate(
    bcv_rate: float,
    monitor_rate: float = 0.0,
    binance_rate: float = 0.0,
    brecha_source: str = BRECHA_SOURCE_BINANCE,
    brecha_factor_pct: float = 100.0,
    manual_brecha_pct: float = 0.0,
) -> dict[str, Any]:
    """Calcula la brecha (%) respecto al BCV y la tasa ajustada en Bs/USD."""
    bcv = max(float(bcv_rate or 0.0), 0.0)
    monitor = max(float(monitor_rate or 0.0), 0.0)
    binance = max(float(binance_rate or 0.0), 0.0)
    factor = max(float(brecha_factor_pct if brecha_factor_pct is not None else 100.0), 0.0)
    source = (brecha_source or BRECHA_SOURCE_BINANCE).strip()

    if bcv <= 0:
        return {
            "bcv_rate": 0.0,
            "monitor_rate": round(monitor, 4),
            "binance_usdt_rate": round(binance, 4),
            "brecha_source": source,
            "brecha_factor_pct": round(factor, 2),
            "raw_brecha_pct": 0.0,
            "applied_brecha_pct": 0.0,
            "adjusted_rate": 0.0,
            "market_reference_rate": 0.0,
        }

    market_ref = 0.0
    if source == BRECHA_SOURCE_MANUAL:
        raw_brecha_pct = float(manual_brecha_pct or 0.0)
        applied_brecha_pct = raw_brecha_pct
        market_ref = round(bcv * (1.0 + applied_brecha_pct / 100.0), 4)
    else:
        if source == BRECHA_SOURCE_MONITOR:
            market_ref = monitor or binance
        else:
            market_ref = binance or monitor

        if market_ref > 0:
            raw_brecha_pct = ((market_ref / bcv) - 1.0) * 100.0
        else:
            raw_brecha_pct = 0.0
        applied_brecha_pct = raw_brecha_pct * (factor / 100.0)

    adjusted_rate = round(max(bcv * (1.0 + applied_brecha_pct / 100.0), 0.0), 4)
    return {
        "bcv_rate": round(bcv, 4),
        "monitor_rate": round(monitor, 4),
        "binance_usdt_rate": round(binance, 4),
        "brecha_source": source,
        "brecha_factor_pct": round(factor, 2),
        "raw_brecha_pct": round(raw_brecha_pct, 2),
        "applied_brecha_pct": round(applied_brecha_pct, 2),
        "adjusted_rate": adjusted_rate,
        "market_reference_rate": round(market_ref, 4),
    }


def convert_usd_to_bs(amount_usd: float, rate_bs_per_usd: float) -> float:
    """Convierte un monto en USD a Bs usando la tasa suministrada."""
    usd = float(amount_usd or 0.0)
    rate = max(float(rate_bs_per_usd or 0.0), 0.0)
    if rate <= 0:
        return 0.0
    return round(usd * rate, 2)
