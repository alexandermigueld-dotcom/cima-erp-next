from __future__ import annotations

from cima_ve.api._compat import whitelist
from cima_ve.services.exchange_rate_service import (
    BRECHA_SOURCE_BINANCE,
    calculate_brecha_and_adjusted_rate,
    fetch_binance_p2p_usdt_ves,
    fetch_dolarapi_rates,
)


def _upsert_currency_exchange(adjusted_rate: float) -> None:
    """Sincroniza la tasa USD -> VES en el DocType nativo Currency Exchange de ERPNext."""
    import frappe
    from frappe.utils import today

    if adjusted_rate <= 0:
        return
    if not frappe.db.exists("Currency", "VES") or not frappe.db.exists("Currency", "USD"):
        return

    current_date = today()
    existing = frappe.get_all(
        "Currency Exchange",
        filters={"from_currency": "USD", "to_currency": "VES", "date": current_date},
        pluck="name",
        limit=1,
    )
    if existing:
        frappe.db.set_value(
            "Currency Exchange",
            existing[0],
            {"exchange_rate": adjusted_rate, "for_buying": 1, "for_selling": 1},
        )
    else:
        doc = frappe.get_doc(
            {
                "doctype": "Currency Exchange",
                "date": current_date,
                "from_currency": "USD",
                "to_currency": "VES",
                "exchange_rate": adjusted_rate,
                "for_buying": 1,
                "for_selling": 1,
            }
        )
        doc.insert(ignore_permissions=True)


def sync_exchange_rates_job(force: bool = False) -> dict:
    """Tarea programada (y manual) para obtener BCV, Monitor y Binance USDT/VES y calcular la brecha."""
    import frappe
    from frappe.utils import now_datetime

    settings = frappe.get_single("Cima VE Settings")
    auto_sync = bool(int(settings.get("fx_auto_sync") or 0)) if settings.meta.has_field("fx_auto_sync") else True
    if not force and not auto_sync:
        return {"skipped": True, "reason": "fx_auto_sync disabled"}

    errors: list[str] = []
    bcv_rate = float(settings.get("fx_bcv_rate") or 0.0)
    monitor_rate = float(settings.get("fx_monitor_rate") or 0.0)
    binance_rate = float(settings.get("fx_binance_usdt_rate") or 0.0)

    try:
        dolar_data = fetch_dolarapi_rates(timeout=8)
        if dolar_data.get("bcv_rate", 0) > 0:
            bcv_rate = float(dolar_data["bcv_rate"])
        if dolar_data.get("monitor_rate", 0) > 0:
            monitor_rate = float(dolar_data["monitor_rate"])
    except Exception as exc:
        errors.append(f"DolarAPI: {exc}")

    try:
        p2p_rate = fetch_binance_p2p_usdt_ves(timeout=8)
        if p2p_rate > 0:
            binance_rate = float(p2p_rate)
    except Exception as exc:
        errors.append(f"Binance P2P: {exc}")

    brecha_source = (settings.get("fx_brecha_source") or BRECHA_SOURCE_BINANCE).strip()
    brecha_factor = float(settings.get("fx_brecha_factor_pct") if settings.get("fx_brecha_factor_pct") is not None else 100.0)
    manual_brecha = float(settings.get("fx_manual_brecha_pct") or 0.0)

    calc = calculate_brecha_and_adjusted_rate(
        bcv_rate=bcv_rate,
        monitor_rate=monitor_rate,
        binance_rate=binance_rate,
        brecha_source=brecha_source,
        brecha_factor_pct=brecha_factor,
        manual_brecha_pct=manual_brecha,
    )

    now_str = str(now_datetime())[:19]
    status_msg = "OK" if not errors else f"Parcial ({'; '.join(errors)[:120]})"

    updates = {
        "fx_bcv_rate": calc["bcv_rate"],
        "fx_monitor_rate": calc["monitor_rate"],
        "fx_binance_usdt_rate": calc["binance_usdt_rate"],
        "fx_brecha_pct": calc["applied_brecha_pct"],
        "fx_adjusted_rate": calc["adjusted_rate"],
        "fx_last_updated": now_str,
        "fx_sync_status": status_msg,
    }
    for fieldname, value in updates.items():
        if settings.meta.has_field(fieldname):
            settings.set(fieldname, value)
    settings.save(ignore_permissions=True)

    try:
        _upsert_currency_exchange(calc["adjusted_rate"] or calc["bcv_rate"])
    except Exception:
        frappe.log_error(frappe.get_traceback(), "Cima VE Currency Exchange Sync Error")

    frappe.db.commit()
    return {
        **calc,
        "last_updated": now_str,
        "sync_status": status_msg,
        "errors": errors,
    }


@whitelist()
def sync_exchange_rates_now() -> dict:
    """Sincroniza manualmente las tasas BCV, Monitor y Binance USDT (solo System Manager)."""
    import frappe

    frappe.only_for("System Manager")
    return sync_exchange_rates_job(force=True)


@whitelist(allow_guest=True)
def get_current_exchange_rates() -> dict:
    """Devuelve las tasas actuales almacenadas en Cima VE Settings para UI y /tienda."""
    import frappe

    settings = frappe.get_single("Cima VE Settings")
    bcv = float(settings.get("fx_bcv_rate") or 0.0)
    monitor = float(settings.get("fx_monitor_rate") or 0.0)
    binance = float(settings.get("fx_binance_usdt_rate") or 0.0)
    brecha_source = (settings.get("fx_brecha_source") or BRECHA_SOURCE_BINANCE).strip()
    brecha_factor = float(settings.get("fx_brecha_factor_pct") if settings.get("fx_brecha_factor_pct") is not None else 100.0)
    manual_brecha = float(settings.get("fx_manual_brecha_pct") or 0.0)

    calc = calculate_brecha_and_adjusted_rate(
        bcv_rate=bcv,
        monitor_rate=monitor,
        binance_rate=binance,
        brecha_source=brecha_source,
        brecha_factor_pct=brecha_factor,
        manual_brecha_pct=manual_brecha,
    )
    return {
        **calc,
        "last_updated": str(settings.get("fx_last_updated") or ""),
        "sync_status": str(settings.get("fx_sync_status") or ""),
    }
