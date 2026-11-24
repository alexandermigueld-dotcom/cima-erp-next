from __future__ import annotations

from datetime import date, datetime
import html
import json


DEFAULT_AUTO_DISCOUNT_TIERS: list[dict] = [
    {"label": "Compra < $100", "min_amount": 0.0, "max_amount": 99.99, "discount_percentage": 0.0},
    {"label": "Compra $500 - $1,000", "min_amount": 500.0, "max_amount": 1000.0, "discount_percentage": 4.76},
    {"label": "Compra > $1,000", "min_amount": 1000.01, "max_amount": None, "discount_percentage": 9.09},
]


def _parse_iso_date(raw_date: object) -> date | None:
    """Convierte una fecha (date, datetime o string YYYY-MM-DD) a datetime.date."""
    if raw_date is None:
        return None
    if isinstance(raw_date, datetime):
        return raw_date.date()
    if isinstance(raw_date, date):
        return raw_date
    text = str(raw_date).strip()
    if not text:
        return None
    try:
        return date.fromisoformat(text[:10])
    except ValueError:
        return None


def validate_due_date(due_date: str | None) -> str:
    """Valida que la Fecha de Vencimiento obligatoria esté presente y tenga formato YYYY-MM-DD."""
    clean = str(due_date or "").strip()
    if not clean:
        raise ValueError("Debe indicar la Fecha de Vencimiento de la Nota de Entrega.")
    parsed = _parse_iso_date(clean)
    if parsed is None:
        raise ValueError("La Fecha de Vencimiento debe tener un formato válido (YYYY-MM-DD).")
    return parsed.isoformat()


def parse_auto_discount_tiers(raw_tiers: str | list | None) -> list[dict]:
    """Parsea las reglas configurables de descuento automático por monto desde Cima VE Settings."""
    parsed = None
    if isinstance(raw_tiers, list):
        parsed = raw_tiers
    elif isinstance(raw_tiers, str) and raw_tiers.strip():
        try:
            candidate = json.loads(raw_tiers)
            if isinstance(candidate, list):
                parsed = candidate
        except Exception:
            parsed = None

    if parsed is None:
        return [dict(t) for t in DEFAULT_AUTO_DISCOUNT_TIERS]

    tiers: list[dict] = []
    for row in parsed:
        if not isinstance(row, dict):
            continue
        if row.get("enabled") is False:
            continue
        try:
            min_amt = float(row.get("min_amount") if row.get("min_amount") is not None else 0.0)
        except (TypeError, ValueError):
            min_amt = 0.0
        raw_max = row.get("max_amount")
        if raw_max in (None, ""):
            max_amt = None
        else:
            try:
                max_amt = float(raw_max)
            except (TypeError, ValueError):
                max_amt = None
        try:
            pct = float(row.get("discount_percentage") or 0.0)
        except (TypeError, ValueError):
            pct = 0.0
        pct = round(min(max(pct, 0.0), 100.0), 4)
        label = str(row.get("label") or "").strip()
        if not label:
            label = f"Desde ${min_amt:g}" if max_amt is None else f"${min_amt:g} - ${max_amt:g}"
        tiers.append(
            {
                "label": label,
                "min_amount": min_amt,
                "max_amount": max_amt,
                "discount_percentage": pct,
                "discount_type": str(row.get("discount_type") or "amount_tier"),
            }
        )
    return tiers


def match_auto_discount_tier(subtotal: float, tiers: list[dict] | None) -> dict | None:
    """Devuelve la regla de descuento automático aplicable al subtotal dado."""
    amount = round(max(float(subtotal or 0.0), 0.0), 2)
    if amount <= 0:
        return None
    matches: list[dict] = []
    for tier in tiers or []:
        min_amt = float(tier.get("min_amount") or 0.0)
        max_amt = tier.get("max_amount")
        if amount + 1e-9 < min_amt:
            continue
        if max_amt is not None and amount - 1e-9 > float(max_amt):
            continue
        matches.append(tier)
    if not matches:
        return None
    matches.sort(key=lambda t: (float(t.get("discount_percentage") or 0.0), float(t.get("min_amount") or 0.0)), reverse=True)
    best = matches[0]
    if float(best.get("discount_percentage") or 0.0) <= 0:
        return None
    return best


def compute_delivery_note_discounts(
    subtotal: float,
    auto_discount_enabled: bool = True,
    tiers: list[dict] | None = None,
    manual_discount_enabled: bool = False,
    manual_discount_percentage: float = 0.0,
) -> dict:
    """Calcula el descuento automático por monto y el descuento manual opcional (%) de una Nota de Entrega."""
    base = round(max(float(subtotal or 0.0), 0.0), 2)

    auto_pct = 0.0
    auto_amount = 0.0
    auto_label = ""
    if auto_discount_enabled and base > 0:
        matched = match_auto_discount_tier(base, tiers if tiers is not None else DEFAULT_AUTO_DISCOUNT_TIERS)
        if matched:
            auto_pct = round(float(matched.get("discount_percentage") or 0.0), 2)
            auto_label = str(matched.get("label") or "")
            auto_amount = round(base * (auto_pct / 100.0), 2)

    after_auto = round(max(base - auto_amount, 0.0), 2)

    manual_pct = 0.0
    manual_amount = 0.0
    if manual_discount_enabled and after_auto > 0:
        try:
            manual_pct = float(manual_discount_percentage or 0.0)
        except (TypeError, ValueError):
            manual_pct = 0.0
        manual_pct = round(min(max(manual_pct, 0.0), 100.0), 2)
        if manual_pct > 0:
            manual_amount = round(after_auto * (manual_pct / 100.0), 2)

    total_discount = round(min(base, auto_amount + manual_amount), 2)
    final_total = round(max(base - total_discount, 0.0), 2)
    effective_pct = round((total_discount / base) * 100.0, 4) if base > 0 and total_discount > 0 else 0.0

    return {
        "subtotal": base,
        "auto_discount_enabled": bool(auto_discount_enabled),
        "auto_discount_pct": auto_pct,
        "auto_discount_amount": auto_amount,
        "auto_discount_label": auto_label,
        "manual_discount_enabled": bool(manual_discount_enabled and manual_pct > 0),
        "manual_discount_pct": manual_pct,
        "manual_discount_amount": manual_amount,
        "total_discount_amount": total_discount,
        "effective_discount_pct": effective_pct,
        "final_total": final_total,
        "has_global_discount": total_discount > 0,
    }


def is_cash_payment_method(payment_method: str | None) -> bool:
    """Identifica si el método de pago es en efectivo (no requiere captura ni referencia)."""
    import re

    clean = (payment_method or "").strip().lower()
    if "efectivo" in clean:
        return True
    return bool(re.search(r"\bcash\b", clean))


def get_payment_method_currency(payment_method: str | None) -> str:
    """Identifica si el método de pago es en Bs ('Bs') o en Dólares ('USD')."""
    clean = (payment_method or "").strip().lower()
    if not clean:
        return "USD"
    # Explicit USD / FX indicators take priority if someone names e.g. "Transferencia USD"
    if any(tok in clean for tok in ("usd", "dólar", "dolar", "$", "zelle", "binance", "cashea", "paypal", "divisa", "google pay")):
        return "USD"
    # Bolívares indicators
    if any(tok in clean for tok in ("bs", "bolivar", "bolívar", "pago movil", "pago móvil", "punto de venta", "biopago", "transferencia", "ves")):
        return "Bs"
    return "USD"


def compute_delivery_note_settlement_totals(
    net_total: float,
    apply_iva: bool = False,
    apply_igtf: bool = False,
    iva_rate: float = 16.0,
    igtf_rate: float = 3.0,
) -> dict:
    """Calcula base, IVA, IGTF y total al liquidar/pagar una Nota de Entrega."""
    base = round(max(float(net_total or 0.0), 0.0), 2)
    iva_amount = round(base * (float(iva_rate or 0.0) / 100.0), 2) if apply_iva else 0.0
    subtotal_with_iva = round(base + iva_amount, 2)
    igtf_amount = round(subtotal_with_iva * (float(igtf_rate or 0.0) / 100.0), 2) if apply_igtf else 0.0
    grand_total = round(subtotal_with_iva + igtf_amount, 2)
    return {
        "net_total": base,
        "iva_rate": float(iva_rate or 0.0) if apply_iva else 0.0,
        "iva_amount": iva_amount,
        "igtf_rate": float(igtf_rate or 0.0) if apply_igtf else 0.0,
        "igtf_amount": igtf_amount,
        "grand_total": grand_total,
    }


def compute_partial_payment_state(
    total_to_pay: float,
    already_paid: float,
    payment_amount: float | None,
) -> dict:
    """Valida un abono o pago total y calcula el nuevo saldo y estado de la Nota de Entrega."""
    total = round(max(float(total_to_pay or 0.0), 0.0), 2)
    paid_before = round(max(float(already_paid or 0.0), 0.0), 2)
    remaining_before = round(max(total - paid_before, 0.0), 2)

    if remaining_before <= 0.01:
        raise ValueError("Esta Nota de Entrega ya no tiene saldo pendiente por cobrar.")

    if payment_amount is None:
        amt = remaining_before
    else:
        amt = round(float(payment_amount), 2)

    if amt <= 0:
        raise ValueError("El monto a pagar debe ser mayor que 0.")
    if amt > remaining_before + 0.01:
        raise ValueError(
            f"El monto (${amt:.2f}) excede el saldo pendiente (${remaining_before:.2f})."
        )

    if amt > remaining_before:
        amt = remaining_before

    new_paid = round(min(total, paid_before + amt), 2)
    new_remaining = round(max(total - new_paid, 0.0), 2)
    is_fully_paid = new_remaining <= 0.01
    if is_fully_paid:
        new_remaining = 0.0
        new_paid = total

    return {
        "total_to_pay": total,
        "paid_before": paid_before,
        "payment_amount": amt,
        "new_paid_total": new_paid,
        "new_remaining": new_remaining,
        "is_fully_paid": is_fully_paid,
        "estado": "Pagada" if is_fully_paid else "Pago Parcial",
    }


def parse_payment_history(raw_history: str | list | None) -> list[dict]:
    """Parsea el historial JSON de abonos/pagos de una Nota de Entrega."""
    if isinstance(raw_history, list):
        return [dict(x) for x in raw_history if isinstance(x, dict)]
    if not raw_history:
        return []
    try:
        parsed = json.loads(raw_history)
        if isinstance(parsed, list):
            return [dict(x) for x in parsed if isinstance(x, dict)]
    except Exception:
        pass
    return []


def append_payment_history(raw_history: str | list | None, entry: dict) -> tuple[list[dict], str]:
    """Agrega un nuevo pago al historial y devuelve (lista, json_str)."""
    history = parse_payment_history(raw_history)
    history.append(dict(entry))
    return history, json.dumps(history, ensure_ascii=False)


def compute_historical_bs_payment(
    total_to_pay_usd: float,
    paid_now_usd: float,
    current_bs_rate: float,
    existing_history: list[dict] | None = None,
    is_fully_paid: bool = False,
) -> dict:
    """Calcula el monto en Bs de este abono y el total histórico en Bs al quedar pagada."""
    rate = round(max(float(current_bs_rate or 0.0), 0.0), 4)
    paid_now_bs = round(max(float(paid_now_usd or 0.0), 0.0) * rate, 2) if rate > 0 else 0.0
    prior_bs = sum(float(h.get("amount_bs") or 0.0) for h in (existing_history or []))
    paid_total_bs = round(prior_bs + paid_now_bs, 2)
    if is_fully_paid:
        total_bs = paid_total_bs if paid_total_bs > 0 else (
            round(max(float(total_to_pay_usd or 0.0), 0.0) * rate, 2) if rate > 0 else 0.0
        )
    else:
        total_bs = 0.0
    return {
        "exchange_rate": rate,
        "paid_now_bs": paid_now_bs,
        "paid_total_bs": paid_total_bs,
        "total_bs": total_bs,
    }


DEFAULT_COMMISSION_RULES: list[dict] = [
    {"label": "Meta Ads 7%", "channel": "Meta Ads", "percentage": 7.0},
    {"label": "Detal 8%", "channel": "Detal", "percentage": 8.0},
    {"label": "Mayor 10%", "channel": "Mayor", "percentage": 10.0},
]

NON_COMMISSION_CHANNELS: set[str] = {"tienda web", "mercadolibre", "mercado libre"}


def is_non_commission_channel(
    origin: str | None = "",
    sales_channel: str | None = "",
    commission_option: str | None = "",
) -> bool:
    """Devuelve True si la nota corresponde a canales sin comisión de vendedor (Tienda Web o MercadoLibre)."""
    for raw in (origin, sales_channel, commission_option):
        norm = " ".join(str(raw or "").strip().lower().split())
        if not norm:
            continue
        if (
            norm in NON_COMMISSION_CHANNELS
            or norm.startswith("tienda web")
            or norm.startswith("mercadolibre")
            or norm.startswith("mercado libre")
        ):
            return True
    return False


def parse_commission_rules(raw_rules: str | list | None) -> list[dict]:
    """Parsea las reglas configurables de comisión por canal/modalidad desde Cima VE Settings."""
    parsed = None
    if isinstance(raw_rules, list):
        parsed = raw_rules
    elif isinstance(raw_rules, str) and raw_rules.strip():
        try:
            candidate = json.loads(raw_rules)
            if isinstance(candidate, list):
                parsed = candidate
        except Exception:
            parsed = None

    if parsed is None:
        return [dict(r) for r in DEFAULT_COMMISSION_RULES]

    rules: list[dict] = []
    for row in parsed:
        if not isinstance(row, dict):
            continue
        if row.get("enabled") is False:
            continue
        label = str(row.get("label") or row.get("name") or "").strip()
        channel = str(row.get("channel") or label).strip()
        if not label and not channel:
            continue
        if not label:
            label = channel
        try:
            pct = float(row.get("percentage") if row.get("percentage") is not None else 0.0)
        except (TypeError, ValueError):
            pct = 0.0
        pct = round(min(max(pct, 0.0), 100.0), 2)
        rules.append({"label": label, "channel": channel or label, "percentage": pct})
    return rules or [dict(r) for r in DEFAULT_COMMISSION_RULES]


def resolve_commission_rule(selected_option: str | None, rules: list[dict] | None = None) -> dict | None:
    """Busca la regla de comisión por etiqueta exacta o por canal de venta."""
    key = str(selected_option or "").strip().lower()
    if not key:
        return None
    active_rules = rules if rules is not None else DEFAULT_COMMISSION_RULES
    for r in active_rules:
        if str(r.get("label") or "").strip().lower() == key:
            return dict(r)
    for r in active_rules:
        if str(r.get("channel") or "").strip().lower() == key:
            return dict(r)
    return None


def compute_margin_commission(
    net_sale_amount: float,
    total_cost: float,
    commission_pct: float,
) -> dict:
    """Calcula la comisión del vendedor sobre el precio de venta neto (conservando costo y margen informativos)."""
    net_sale = round(max(float(net_sale_amount or 0.0), 0.0), 2)
    cost = round(max(float(total_cost or 0.0), 0.0), 2)
    margin = round(net_sale - cost, 2)
    pct = round(min(max(float(commission_pct or 0.0), 0.0), 100.0), 2)
    commission = round(net_sale * (pct / 100.0), 2)
    return {
        "net_sale_amount": net_sale,
        "total_cost": cost,
        "margin_amount": margin,
        "commission_pct": pct,
        "commission_amount": commission,
    }


def compute_note_commission_currency_split(note: dict, fallback_bs_rate: float = 0.0) -> dict:
    """Divide la comisión de una Nota de Entrega entre USD ($) y Bs según los métodos de pago usados."""
    comm_total = round(float(note.get("commission_amount") or note.get("ve_ne_comision_monto") or 0.0), 2)
    estado = (note.get("ve_ne_estado") or "").strip()
    if comm_total <= 0 or estado == "Cancelada":
        return {
            "commission_usd": 0.0,
            "commission_bs_usd_equiv": 0.0,
            "commission_bs": 0.0,
            "commission_pending_usd": 0.0,
        }

    total_to_pay = round(float(note.get("total_to_pay") or note.get("ve_ne_monto_total") or note.get("grand_total") or note.get("amount") or 0.0), 2)
    history = parse_payment_history(note.get("payment_history") if note.get("payment_history") is not None else note.get("ve_ne_historial_pagos"))
    default_rate = float(note.get("ve_ne_tasa_cambio") or fallback_bs_rate or 0.0)

    if not history:
        # Fallback when a note was marked paid without structured history
        if estado == "Pagada":
            method = note.get("ve_ne_metodo_pago") or ""
            if get_payment_method_currency(method) == "Bs":
                rate = default_rate
                return {
                    "commission_usd": 0.0,
                    "commission_bs_usd_equiv": comm_total,
                    "commission_bs": round(comm_total * rate, 2) if rate > 0 else 0.0,
                    "commission_pending_usd": 0.0,
                }
            return {
                "commission_usd": comm_total,
                "commission_bs_usd_equiv": 0.0,
                "commission_bs": 0.0,
                "commission_pending_usd": 0.0,
            }
        return {
            "commission_usd": 0.0,
            "commission_bs_usd_equiv": 0.0,
            "commission_bs": 0.0,
            "commission_pending_usd": comm_total,
        }

    total_paid_hist = sum(max(float(h.get("amount") or 0.0), 0.0) for h in history)
    denom = total_paid_hist if (estado == "Pagada" and total_paid_hist > 0) else (total_to_pay if total_to_pay > 0 else total_paid_hist)
    if denom <= 0:
        return {
            "commission_usd": 0.0,
            "commission_bs_usd_equiv": 0.0,
            "commission_bs": 0.0,
            "commission_pending_usd": comm_total,
        }

    comm_usd_part = 0.0
    comm_bs_usd_equiv = 0.0
    comm_bs_amount = 0.0

    for h in history:
        amt = max(float(h.get("amount") or 0.0), 0.0)
        if amt <= 0:
            continue
        share = min(amt / denom, 1.0)
        comm_piece = comm_total * share
        method = h.get("method") or note.get("ve_ne_metodo_pago") or ""
        if get_payment_method_currency(method) == "Bs":
            rate = float(h.get("exchange_rate") or default_rate or 0.0)
            comm_bs_usd_equiv += comm_piece
            if rate > 0:
                comm_bs_amount += comm_piece * rate
        else:
            comm_usd_part += comm_piece

    if estado == "Pagada":
        # Normalize rounding drift so paid USD + Bs equiv == comm_total
        comm_bs_usd_equiv = round(min(comm_bs_usd_equiv, comm_total), 2)
        comm_usd_part = round(max(comm_total - comm_bs_usd_equiv, 0.0), 2)
        pending = 0.0
    else:
        comm_usd_part = round(comm_usd_part, 2)
        comm_bs_usd_equiv = round(comm_bs_usd_equiv, 2)
        pending = round(max(comm_total - comm_usd_part - comm_bs_usd_equiv, 0.0), 2)

    return {
        "commission_usd": comm_usd_part,
        "commission_bs_usd_equiv": comm_bs_usd_equiv,
        "commission_bs": round(comm_bs_amount, 2),
        "commission_pending_usd": pending,
    }


def summarize_seller_commissions(notes: list[dict], current_bs_rate: float = 0.0) -> list[dict]:
    """Agrupa las notas activas (no canceladas) por vendedor para calcular el pago de comisiones en $ y Bs."""
    buckets: dict[str, dict] = {}
    for n in notes or []:
        if (
            (n.get("ve_ne_estado") or "") == "Cancelada"
            or int(n.get("docstatus") or 0) == 2
            or n.get("commission_excluded")
            or is_non_commission_channel(
                n.get("ve_ne_origen"),
                n.get("canal_venta"),
                n.get("commission_option") or n.get("ve_ne_comision_opcion"),
            )
        ):
            continue
        seller_user = str(n.get("seller_user") or n.get("ve_vendedor_usuario") or n.get("owner") or "Sin vendedor").strip()
        seller_name = str(n.get("seller_name") or n.get("ve_vendedor_nombre") or seller_user).strip()
        b = buckets.setdefault(
            seller_user,
            {
                "seller_user": seller_user,
                "seller_name": seller_name,
                "notes_count": 0,
                "paid_notes_count": 0,
                "pending_notes_count": 0,
                "sales_total": 0.0,
                "cost_total": 0.0,
                "margin_total": 0.0,
                "commission_total": 0.0,
                "paid_commission": 0.0,
                "pending_commission": 0.0,
                "commission_usd": 0.0,
                "commission_bs_usd_equiv": 0.0,
                "commission_bs": 0.0,
            },
        )
        comm = round(float(n.get("commission_amount") or 0.0), 2)
        split = compute_note_commission_currency_split(n, fallback_bs_rate=current_bs_rate)
        b["notes_count"] += 1
        b["sales_total"] += float(n.get("net_total") or n.get("amount") or 0.0)
        b["cost_total"] += float(n.get("cost_total") or 0.0)
        b["margin_total"] += float(n.get("margin_amount") or 0.0)
        b["commission_total"] += comm
        b["commission_usd"] += split["commission_usd"]
        b["commission_bs_usd_equiv"] += split["commission_bs_usd_equiv"]
        b["commission_bs"] += split["commission_bs"]
        if n.get("ve_ne_estado") == "Pagada":
            b["paid_notes_count"] += 1
            b["paid_commission"] += comm
        else:
            b["pending_notes_count"] += 1
            b["pending_commission"] += split["commission_pending_usd"] if split["commission_pending_usd"] > 0 else comm

    result: list[dict] = []
    for b in buckets.values():
        b["sales_total"] = round(b["sales_total"], 2)
        b["cost_total"] = round(b["cost_total"], 2)
        b["margin_total"] = round(b["margin_total"], 2)
        b["commission_total"] = round(b["commission_total"], 2)
        b["paid_commission"] = round(b["paid_commission"], 2)
        b["pending_commission"] = round(b["pending_commission"], 2)
        b["commission_usd"] = round(b["commission_usd"], 2)
        b["commission_bs_usd_equiv"] = round(b["commission_bs_usd_equiv"], 2)
        b["commission_bs"] = round(b["commission_bs"], 2)
        result.append(b)
    result.sort(key=lambda r: (r["commission_total"], r["sales_total"]), reverse=True)
    return result


def summarize_delivery_notes(notes: list[dict], reference_date: date | str | None = None) -> dict:
    """Genera KPIs y normaliza el listado de Notas de Entrega."""
    ref_date = _parse_iso_date(reference_date) or date.today()
    total_count = 0
    pending_count = 0
    partial_count = 0
    pending_total = 0.0
    overdue_count = 0
    overdue_total = 0.0
    paid_count = 0
    paid_total = 0.0
    cancelled_count = 0
    cancelled_total = 0.0
    total_cost = 0.0
    total_margin = 0.0
    total_commission = 0.0
    paid_commission = 0.0
    pending_commission = 0.0

    normalized: list[dict] = []
    for row in notes or []:
        docstatus = int(row.get("docstatus") or 0)
        estado = (row.get("ve_ne_estado") or "").strip()
        base_amount = round(float(row.get("grand_total") or row.get("net_total") or 0.0), 2)
        total_to_pay = round(float(row.get("ve_ne_monto_total") or 0.0), 2) or base_amount
        paid_amount = round(float(row.get("ve_ne_monto_pagado") or 0.0), 2)
        history = parse_payment_history(row.get("ve_ne_historial_pagos"))

        if docstatus == 2 or estado == "Cancelada":
            estado = "Cancelada"
            remaining_amount = 0.0
        elif estado == "Pago Parcial":
            estado = "Pago Parcial"
            remaining_amount = round(
                float(row.get("ve_ne_saldo_pendiente") if row.get("ve_ne_saldo_pendiente") is not None else max(total_to_pay - paid_amount, 0.0)),
                2,
            )
            if remaining_amount <= 0.01 and paid_amount >= total_to_pay - 0.01 and total_to_pay > 0:
                estado = "Pagada"
                remaining_amount = 0.0
        elif estado == "Pagada" or (row.get("ve_ne_factura") and paid_amount <= 0.0):
            estado = "Pagada"
            if paid_amount <= 0.0:
                paid_amount = total_to_pay
            remaining_amount = 0.0
        elif row.get("ve_ne_factura") and max(total_to_pay - paid_amount, 0.0) > 0.01:
            estado = "Pago Parcial"
            remaining_amount = round(max(total_to_pay - paid_amount, 0.0), 2)
        else:
            estado = "Pendiente"
            remaining_amount = total_to_pay

        due_date_obj = _parse_iso_date(row.get("ve_ne_fecha_vencimiento"))
        due_date_str = due_date_obj.isoformat() if due_date_obj else ""
        is_overdue = bool(
            estado in ("Pendiente", "Pago Parcial")
            and due_date_obj is not None
            and due_date_obj < ref_date
            and remaining_amount > 0.01
        )
        days_overdue = (ref_date - due_date_obj).days if is_overdue and due_date_obj is not None else 0

        total_count += 1
        if estado == "Pendiente":
            pending_count += 1
            pending_total += remaining_amount
        elif estado == "Pago Parcial":
            pending_count += 1
            partial_count += 1
            pending_total += remaining_amount
            paid_total += paid_amount
        elif estado == "Pagada":
            paid_count += 1
            paid_total += paid_amount or total_to_pay
        else:
            cancelled_count += 1
            cancelled_total += base_amount

        if is_overdue:
            overdue_count += 1
            overdue_total += remaining_amount

        item = dict(row)
        item["ve_ne_estado"] = estado
        item["ve_ne_fecha_vencimiento"] = due_date_str
        item["is_overdue"] = is_overdue
        item["days_overdue"] = days_overdue
        item["amount"] = base_amount
        item["total_to_pay"] = total_to_pay
        item["paid_amount"] = paid_amount
        item["remaining_amount"] = remaining_amount
        item["payment_history"] = history
        auto_disc_pct = round(float(row.get("ve_ne_descuento_auto_pct") or 0.0), 2)
        auto_disc_amt = round(float(row.get("ve_ne_descuento_auto_monto") or 0.0), 2)
        manual_disc_pct = round(float(row.get("ve_ne_descuento_manual_pct") or 0.0), 2)
        manual_disc_amt = round(float(row.get("ve_ne_descuento_manual_monto") or 0.0), 2)
        global_disc_amt = round(float(row.get("discount_amount") or (auto_disc_amt + manual_disc_amt) or 0.0), 2)
        subtotal_before = round(
            float(row.get("ve_ne_subtotal_sin_descuento") or row.get("total") or (base_amount + global_disc_amt) or base_amount),
            2,
        )
        item["auto_discount_pct"] = auto_disc_pct
        item["auto_discount_amount"] = auto_disc_amt
        item["auto_discount_label"] = str(row.get("ve_ne_descuento_auto_etiqueta") or "")
        item["manual_discount_pct"] = manual_disc_pct
        item["manual_discount_amount"] = manual_disc_amt
        item["global_discount_amount"] = global_disc_amt
        item["subtotal_before_discount"] = subtotal_before
        item["has_global_discount"] = bool(
            auto_disc_pct > 0 or manual_disc_pct > 0 or global_disc_amt > 0
        )
        item["has_discount"] = bool(row.get("has_discount") or item["has_global_discount"])

        comm_option = str(row.get("ve_ne_comision_opcion") or row.get("canal_venta") or "").strip()
        comm_pct = round(float(row.get("ve_ne_comision_pct") or 0.0), 2)
        cost_total = round(float(row.get("ve_ne_costo_total") or 0.0), 2)
        margin_amount = round(float(row.get("ve_ne_margen_ganancia") or 0.0), 2)
        comm_amount = round(float(row.get("ve_ne_comision_monto") or 0.0), 2)
        excluded_by_channel = is_non_commission_channel(
            row.get("ve_ne_origen"),
            row.get("canal_venta"),
            row.get("ve_ne_comision_opcion"),
        )
        if estado == "Cancelada" or excluded_by_channel:
            comm_pct = 0.0
            comm_amount = 0.0
        else:
            total_cost += cost_total
            total_margin += margin_amount
            total_commission += comm_amount
            if estado == "Pagada":
                paid_commission += comm_amount
            else:
                pending_commission += comm_amount

        item["commission_excluded"] = excluded_by_channel
        item["commission_option"] = comm_option
        item["commission_pct"] = comm_pct
        item["cost_total"] = cost_total
        item["margin_amount"] = margin_amount
        item["commission_amount"] = comm_amount

        exchange_rate_used = round(float(row.get("ve_ne_tasa_cambio") or 0.0), 4)
        paid_bs = round(float(row.get("ve_ne_monto_pagado_bs") or 0.0), 2)
        if paid_bs <= 0 and history:
            paid_bs = round(sum(float(h.get("amount_bs") or 0.0) for h in history), 2)
        total_bs = round(float(row.get("ve_ne_monto_bs") or 0.0), 2)
        if estado == "Pagada" and total_bs <= 0 and paid_bs > 0:
            total_bs = paid_bs
        item["exchange_rate_used"] = exchange_rate_used
        item["paid_bs"] = paid_bs
        item["total_bs"] = total_bs
        item["is_bs_frozen"] = bool(estado == "Pagada" or total_bs > 0)
        normalized.append(item)

    return {
        "summary": {
            "total_count": total_count,
            "pending_count": pending_count,
            "partial_count": partial_count,
            "pending_total": round(pending_total, 2),
            "overdue_count": overdue_count,
            "overdue_total": round(overdue_total, 2),
            "paid_count": paid_count,
            "paid_total": round(paid_total, 2),
            "cancelled_count": cancelled_count,
            "cancelled_total": round(cancelled_total, 2),
            "total_cost": round(total_cost, 2),
            "total_margin": round(total_margin, 2),
            "total_commission": round(total_commission, 2),
            "paid_commission": round(paid_commission, 2),
            "pending_commission": round(pending_commission, 2),
        },
        "notes": normalized,
    }


def filter_overdue_delivery_notes(
    notes: list[dict],
    reference_date: date | str | None = None,
) -> list[dict]:
    """Filtra Notas de Entrega activas cuyo pago no está completo después de su Fecha de Vencimiento."""
    summarized = summarize_delivery_notes(notes, reference_date=reference_date)
    overdue = [n for n in summarized["notes"] if n.get("is_overdue")]
    overdue.sort(
        key=lambda n: (int(n.get("days_overdue") or 0), float(n.get("remaining_amount") or 0.0)),
        reverse=True,
    )
    return overdue


def build_overdue_delivery_notes_email_html(
    overdue_notes: list[dict],
    reference_date: date | str | None = None,
) -> str:
    """Genera el HTML del correo semanal (Lunes) de Notas de Entrega vencidas sin pago completo."""
    ref_date = _parse_iso_date(reference_date) or date.today()
    total_pending = round(sum(float(n.get("remaining_amount") or 0.0) for n in overdue_notes), 2)

    rows_html = ""
    for n in overdue_notes:
        dn_name = html.escape(str(n.get("name") or ""))
        customer = html.escape(str(n.get("customer_name") or n.get("customer") or ""))
        seller = html.escape(str(n.get("seller_name") or n.get("seller_user") or "-"))
        posting_date = html.escape(str(n.get("posting_date") or ""))
        due_date = html.escape(str(n.get("ve_ne_fecha_vencimiento") or ""))
        days_over = int(n.get("days_overdue") or 0)
        estado = html.escape(str(n.get("ve_ne_estado") or "Pendiente"))
        total_amt = float(n.get("total_to_pay") or n.get("amount") or 0.0)
        paid_amt = float(n.get("paid_amount") or 0.0)
        rem_amt = float(n.get("remaining_amount") or 0.0)
        rows_html += f"""
        <tr>
            <td style="padding:8px 10px;border-bottom:1px solid #e2e8f0;"><strong>{dn_name}</strong></td>
            <td style="padding:8px 10px;border-bottom:1px solid #e2e8f0;">{customer}</td>
            <td style="padding:8px 10px;border-bottom:1px solid #e2e8f0;">{seller}</td>
            <td style="padding:8px 10px;border-bottom:1px solid #e2e8f0;">{posting_date}</td>
            <td style="padding:8px 10px;border-bottom:1px solid #e2e8f0;">{due_date}</td>
            <td style="padding:8px 10px;border-bottom:1px solid #e2e8f0;text-align:right;color:#b91c1c;font-weight:700;">{days_over} días</td>
            <td style="padding:8px 10px;border-bottom:1px solid #e2e8f0;">{estado}</td>
            <td style="padding:8px 10px;border-bottom:1px solid #e2e8f0;text-align:right;">${total_amt:,.2f}</td>
            <td style="padding:8px 10px;border-bottom:1px solid #e2e8f0;text-align:right;">${paid_amt:,.2f}</td>
            <td style="padding:8px 10px;border-bottom:1px solid #e2e8f0;text-align:right;color:#b91c1c;font-weight:700;">${rem_amt:,.2f}</td>
        </tr>
        """

    return f"""
    <div style="font-family:Segoe UI,Arial,sans-serif;max-width:900px;margin:0 auto;color:#1c2532;">
      <div style="background:#1c2532;color:#ffffff;padding:20px 24px;border-radius:12px 12px 0 0;border-bottom:4px solid #dc2626;">
        <h2 style="margin:0 0 6px;font-size:20px;">Reporte Semanal (Lunes) — Notas de Entrega Vencidas</h2>
        <p style="margin:0;color:#cbd5e1;font-size:13px;">
          Corte al <strong>{ref_date.isoformat()}</strong> · Notas de Entrega con fecha de vencimiento superada sin pago completo.
        </p>
      </div>
      <div style="padding:20px 24px;border:1px solid #d9e6e5;border-top:none;border-radius:0 0 12px 12px;background:#ffffff;">
        <p style="margin-top:0;">
          Se encontraron <strong>{len(overdue_notes)}</strong> Notas de Entrega vencidas con un saldo pendiente total de
          <strong style="color:#b91c1c;">${total_pending:,.2f}</strong>:
        </p>
        <div style="overflow-x:auto;">
          <table style="width:100%;border-collapse:collapse;font-size:13px;">
            <thead>
              <tr style="background:#f4f8f8;text-align:left;">
                <th style="padding:8px 10px;">Nota de Entrega</th>
                <th style="padding:8px 10px;">Cliente</th>
                <th style="padding:8px 10px;">Vendedor</th>
                <th style="padding:8px 10px;">Emisión</th>
                <th style="padding:8px 10px;">Vencimiento</th>
                <th style="padding:8px 10px;text-align:right;">Atraso</th>
                <th style="padding:8px 10px;">Estado</th>
                <th style="padding:8px 10px;text-align:right;">Total</th>
                <th style="padding:8px 10px;text-align:right;">Pagado</th>
                <th style="padding:8px 10px;text-align:right;">Saldo Pendiente</th>
              </tr>
            </thead>
            <tbody>{rows_html}</tbody>
          </table>
        </div>
      </div>
    </div>
    """


DEFAULT_NOTIFICATION_EMAILS = ["cimaelectronic@gmail.com", "alexandermigueld@gmail.com"]
DEFAULT_NOTIFICATION_WHATSAPP = "+584243472198"
DEFAULT_WHATSAPP_ORDERS_CHAT_ID = "120363407788420645@g.us"
DEFAULT_WHATSAPP_PAYMENTS_CHAT_ID = "120363402853406963@g.us"


def parse_notification_emails(raw_emails: str | None) -> list[str]:
    """Parsea una lista de correos separados por coma/punto y coma, con fallback a los correos por defecto."""
    if not raw_emails or not str(raw_emails).strip():
        return list(DEFAULT_NOTIFICATION_EMAILS)

    seen: set[str] = set()
    emails: list[str] = []
    for part in str(raw_emails).replace(";", ",").split(","):
        addr = part.strip()
        if addr and "@" in addr and addr.lower() not in seen:
            seen.add(addr.lower())
            emails.append(addr)
    return emails or list(DEFAULT_NOTIFICATION_EMAILS)


def build_delivery_note_notification_payload(
    *,
    delivery_note: str,
    customer_name: str,
    seller_name: str = "",
    origin: str = "Facturación Rápida",
    items: list[dict] | None = None,
    grand_total: float = 0.0,
    bs_rate: float = 0.0,
    discount_total: float = 0.0,
    delivery_provider: str = "",
    delivery_cost: float = 0.0,
    delivery_address: str = "",
    customer_email: str = "",
    customer_phone: str = "",
    payment_method: str = "",
    payment_reference: str = "",
    payment_bank: str = "",
    screenshot_url: str = "",
    whatsapp_number: str | None = None,
    email_recipients_raw: str | None = None,
    due_date: str = "",
    posting_date: str = "",
) -> dict:
    """Construye el asunto, HTML, texto WhatsApp y enlace wa.me al crear cualquier Nota de Entrega."""
    from cima_ve.services.storefront_service import build_whatsapp_link

    total_usd = round(float(grand_total or 0.0), 2)
    total_bs = round(total_usd * float(bs_rate or 0.0), 2) if float(bs_rate or 0.0) > 0 else 0.0
    target_wa = (whatsapp_number or "").strip() or DEFAULT_NOTIFICATION_WHATSAPP
    recipients = parse_notification_emails(email_recipients_raw)

    item_lines_txt: list[str] = []
    item_rows_html: list[str] = []
    for row in items or []:
        name = str(row.get("item_name") or row.get("item_code") or "Producto")
        qty = float(row.get("qty") or 0)
        rate = float(row.get("rate") or 0)
        amt = round(float(row.get("amount") if row.get("amount") is not None else qty * rate), 2)
        item_lines_txt.append(f"• {name} x{qty:g} (${amt:.2f})")
        item_rows_html.append(
            f"<li><strong>{name}</strong> — Cant: {qty:g} × ${rate:.2f} = <strong>${amt:.2f}</strong></li>"
        )

    subject = f"Nota de Entrega creada: {delivery_note} — {customer_name} (${total_usd:.2f})"

    text_lines = [
        f"Nueva Nota de Entrega creada: {delivery_note}",
        f"Origen: {origin}",
        f"Cliente: {customer_name}",
    ]
    if posting_date:
        text_lines.append(f"Fecha: {posting_date}")
    if seller_name:
        text_lines.append(f"Vendedor: {seller_name}")
    if due_date:
        text_lines.append(f"Fecha de vencimiento: {due_date}")
    if customer_email:
        text_lines.append(f"Correo cliente: {customer_email}")
    if customer_phone:
        text_lines.append(f"Teléfono cliente: {customer_phone}")
    if delivery_provider:
        ship_txt = f"{delivery_provider} (${float(delivery_cost or 0.0):.2f})" if float(delivery_cost or 0.0) > 0 else delivery_provider
        text_lines.append(f"Envío: {ship_txt}")
    if delivery_address:
        text_lines.append(f"Dirección: {delivery_address}")
    if payment_method:
        pay_txt = payment_method
        if payment_reference:
            pay_txt += f" | Ref: {payment_reference}"
        if payment_bank:
            pay_txt += f" | Banco: {payment_bank}"
        text_lines.append(f"Pago reportado: {pay_txt}")
    if discount_total > 0:
        text_lines.append(f"Descuento aplicado: -${float(discount_total):.2f}")
    text_lines.append("Resumen:")
    text_lines.extend(item_lines_txt or ["• Sin ítems detallados"])
    if total_bs > 0:
        text_lines.append(f"TOTAL: ${total_usd:.2f} (Bs. {total_bs:,.2f})")
    else:
        text_lines.append(f"TOTAL: ${total_usd:.2f}")

    text_msg = "\n".join(text_lines)

    bs_html = f" <span style='color:#475569;font-size:14px;'>(Bs. {total_bs:,.2f})</span>" if total_bs > 0 else ""
    extra_html_rows = ""
    if posting_date:
        extra_html_rows += f"<p><strong>Fecha de emisión:</strong> {html.escape(str(posting_date))}</p>"
    if seller_name:
        extra_html_rows += f"<p><strong>Vendedor:</strong> {seller_name}</p>"
    if due_date:
        extra_html_rows += f"<p><strong>Fecha de vencimiento:</strong> {html.escape(str(due_date))}</p>"
    if customer_email or customer_phone:
        extra_html_rows += f"<p><strong>Contacto cliente:</strong> {customer_email or '-'} | {customer_phone or '-'}</p>"
    if delivery_provider:
        extra_html_rows += f"<p><strong>Envío:</strong> {delivery_provider} (${float(delivery_cost or 0.0):.2f}) {f'— {delivery_address}' if delivery_address else ''}</p>"
    if payment_method:
        extra_html_rows += f"<p><strong>Pago reportado:</strong> {payment_method} {f'| Ref: <strong>{payment_reference}</strong>' if payment_reference else ''} {f'| Banco: {payment_bank}' if payment_bank else ''}</p>"
    if screenshot_url:
        extra_html_rows += f"<p><strong>Comprobante adjunto:</strong> {screenshot_url}</p>"
    if discount_total > 0:
        extra_html_rows += f"<p><strong>Descuento aplicado:</strong> -${float(discount_total):.2f}</p>"

    html_msg = (
        f"<h3>Nueva Nota de Entrega: {delivery_note}</h3>"
        f"<p><strong>Origen:</strong> {origin} &nbsp;|&nbsp; <strong>Cliente:</strong> {customer_name}</p>"
        f"{extra_html_rows}"
        f"<ul>{''.join(item_rows_html)}</ul>"
        f"<p style='font-size:16px;'><strong>Total Nota de Entrega: ${total_usd:.2f}</strong>{bs_html}</p>"
    )

    return {
        "subject": subject,
        "text": text_msg,
        "html": html_msg,
        "email_recipients": recipients,
        "whatsapp_number": target_wa,
        "whatsapp_url": build_whatsapp_link(target_wa, text_msg),
    }


def summarize_client_delivery_notes(notes: list[dict], reference_date: date | str | None = None) -> list[dict]:
    """Agrupa Notas de Entrega por cliente, ordenando sus notas de más antigua a más nueva (FIFO)."""
    ref_date = _parse_iso_date(reference_date) or date.today()
    groups: dict[str, dict] = {}
    for n in notes or []:
        cust = str(n.get("customer") or "").strip() or "Sin Cliente"
        cust_name = str(n.get("customer_name") or cust).strip()
        g = groups.setdefault(
            cust,
            {
                "customer": cust,
                "customer_name": cust_name,
                "customer_email": str(n.get("ve_ne_cliente_email") or "").strip(),
                "customer_phone": str(n.get("ve_ne_cliente_telefono") or "").strip(),
                "notes": [],
                "total_notes_count": 0,
                "pending_notes_count": 0,
                "partial_notes_count": 0,
                "paid_notes_count": 0,
                "cancelled_notes_count": 0,
                "overdue_count": 0,
                "overdue_total": 0.0,
                "total_amount": 0.0,
                "paid_amount": 0.0,
                "pending_amount": 0.0,
                "oldest_due_date": "",
                "sellers": [],
            },
        )
        if not g["customer_email"] and n.get("ve_ne_cliente_email"):
            g["customer_email"] = str(n.get("ve_ne_cliente_email") or "").strip()
        if not g["customer_phone"] and n.get("ve_ne_cliente_telefono"):
            g["customer_phone"] = str(n.get("ve_ne_cliente_telefono") or "").strip()

        g["notes"].append(n)
        g["total_notes_count"] += 1
        estado = (n.get("ve_ne_estado") or "Pendiente").strip()
        seller = str(n.get("seller_name") or n.get("seller_user") or "").strip()
        if seller and seller not in g["sellers"]:
            g["sellers"].append(seller)

        if estado == "Cancelada":
            g["cancelled_notes_count"] += 1
            continue

        g["total_amount"] += float(n.get("total_to_pay") or n.get("amount") or 0.0)
        g["paid_amount"] += float(n.get("paid_amount") or 0.0)
        rem = float(n.get("remaining_amount") or 0.0)
        if estado in ("Pendiente", "Pago Parcial"):
            g["pending_notes_count"] += 1
            if estado == "Pago Parcial":
                g["partial_notes_count"] += 1
            g["pending_amount"] += rem
            due = str(n.get("ve_ne_fecha_vencimiento") or "").strip()
            if due and (not g["oldest_due_date"] or due < g["oldest_due_date"]):
                g["oldest_due_date"] = due
            due_obj = _parse_iso_date(due)
            if n.get("is_overdue") or (due_obj is not None and due_obj < ref_date and rem > 0.01):
                g["overdue_count"] += 1
                g["overdue_total"] += rem
        elif estado == "Pagada":
            g["paid_notes_count"] += 1

    result: list[dict] = []
    for g in groups.values():
        g["notes"].sort(
            key=lambda row: (
                str(row.get("posting_date") or ""),
                str(row.get("creation") or ""),
                str(row.get("name") or ""),
            )
        )
        g["total_amount"] = round(g["total_amount"], 2)
        g["paid_amount"] = round(g["paid_amount"], 2)
        g["pending_amount"] = round(g["pending_amount"], 2)
        g["overdue_total"] = round(g["overdue_total"], 2)
        result.append(g)

    result.sort(
        key=lambda c: (
            1 if c["overdue_count"] > 0 else 0,
            c["pending_amount"],
            c["total_amount"],
        ),
        reverse=True,
    )
    return result


def allocate_client_payment_fifo(notes: list[dict], payment_amount: float) -> dict:
    """Distribuye un pago de cliente entre sus Notas de Entrega pendientes más antiguas (FIFO)."""
    amt = round(float(payment_amount or 0.0), 2)
    if amt <= 0:
        raise ValueError("El monto del pago debe ser mayor que 0.")

    eligible = [
        dict(n)
        for n in (notes or [])
        if int(n.get("docstatus") or 1) == 1
        and (n.get("ve_ne_estado") or "Pendiente") in ("Pendiente", "Pago Parcial")
        and round(float(n.get("remaining_amount") or 0.0), 2) > 0.01
    ]
    if not eligible:
        raise ValueError("Este cliente no tiene Notas de Entrega pendientes por cobrar.")

    eligible.sort(
        key=lambda row: (
            str(row.get("posting_date") or ""),
            str(row.get("creation") or ""),
            str(row.get("name") or ""),
        )
    )

    total_pending = round(sum(float(n["remaining_amount"]) for n in eligible), 2)
    if amt > total_pending + 0.01:
        raise ValueError(
            f"El monto del pago (${amt:.2f}) excede el saldo pendiente total del cliente (${total_pending:.2f})."
        )
    if amt > total_pending:
        amt = total_pending

    remaining_payment = amt
    allocations: list[dict] = []
    for n in eligible:
        if remaining_payment <= 0.01:
            break
        note_rem = round(float(n["remaining_amount"]), 2)
        alloc = round(min(remaining_payment, note_rem), 2)
        if alloc <= 0:
            continue
        new_rem = round(max(note_rem - alloc, 0.0), 2)
        will_complete = new_rem <= 0.01
        if will_complete:
            alloc = note_rem
            new_rem = 0.0
        allocations.append(
            {
                "delivery_note": n["name"],
                "posting_date": str(n.get("posting_date") or ""),
                "due_date": str(n.get("ve_ne_fecha_vencimiento") or ""),
                "remaining_before": note_rem,
                "allocated_amount": alloc,
                "remaining_after": new_rem,
                "new_estado": "Pagada" if will_complete else "Pago Parcial",
            }
        )
        remaining_payment = round(max(remaining_payment - alloc, 0.0), 2)

    return {
        "payment_amount": amt,
        "total_pending_before": total_pending,
        "total_pending_after": round(max(total_pending - amt, 0.0), 2),
        "allocations": allocations,
    }


def build_client_delivery_note_email_html(
    *,
    delivery_note: str,
    customer_name: str,
    items: list[dict] | None = None,
    grand_total: float = 0.0,
    bs_rate: float = 0.0,
    due_date: str = "",
    seller_name: str = "",
    discount_total: float = 0.0,
    posting_date: str = "",
    customer_phone: str = "",
) -> dict:
    """Construye el correo y mensaje WhatsApp de confirmación para el cliente al crear una Nota de Entrega."""
    from cima_ve.services.storefront_service import build_whatsapp_link

    total_usd = round(float(grand_total or 0.0), 2)
    total_bs = round(total_usd * float(bs_rate or 0.0), 2) if float(bs_rate or 0.0) > 0 else 0.0
    effective_date = str(posting_date or date.today().isoformat()).strip()
    rows_html = []
    item_lines_txt = []
    for row in items or []:
        raw_name = str(row.get("item_name") or row.get("item_code") or "Producto")
        name = html.escape(raw_name)
        qty = float(row.get("qty") or 0)
        rate = float(row.get("rate") or 0)
        amt = round(float(row.get("amount") if row.get("amount") is not None else qty * rate), 2)
        item_lines_txt.append(f"• {raw_name} x{qty:g} (${amt:.2f})")
        rows_html.append(
            f"<tr>"
            f"<td style='padding:6px 8px;border-bottom:1px solid #e2e8f0;'>{name}</td>"
            f"<td style='padding:6px 8px;border-bottom:1px solid #e2e8f0;text-align:right;'>{qty:g}</td>"
            f"<td style='padding:6px 8px;border-bottom:1px solid #e2e8f0;text-align:right;'>${rate:.2f}</td>"
            f"<td style='padding:6px 8px;border-bottom:1px solid #e2e8f0;text-align:right;'><strong>${amt:.2f}</strong></td>"
            f"</tr>"
        )
    bs_line = f" <span style='color:#475569;font-size:13px;'>(Bs. {total_bs:,.2f})</span>" if total_bs > 0 else ""
    date_line = f"<p><strong>Fecha de emisión:</strong> {html.escape(effective_date)}</p>" if effective_date else ""
    due_line = f"<p><strong>Fecha de vencimiento:</strong> {html.escape(str(due_date))}</p>" if due_date else ""
    seller_line = f"<p><strong>Asesor / Vendedor:</strong> {html.escape(str(seller_name))}</p>" if seller_name else ""
    disc_line = f"<p><strong>Descuento aplicado:</strong> -${float(discount_total):.2f}</p>" if float(discount_total or 0) > 0 else ""

    subject = f"[CIMA Electronic VE] ¡Gracias por tu compra! Nota de Entrega {delivery_note} — ${total_usd:.2f}"
    body = f"""
    <div style="font-family:Arial,sans-serif;max-width:680px;margin:0 auto;color:#0f172a;">
      <div style="background:#0f172a;color:#fff;padding:16px 20px;border-radius:8px 8px 0 0;">
        <h2 style="margin:0;font-size:18px;">CIMA ELECTRONIC VE</h2>
        <p style="margin:4px 0 0;font-size:12px;color:#cbd5e1;">Comprobante de Nota de Entrega</p>
      </div>
      <div style="border:1px solid #cbd5e1;border-top:none;padding:18px 20px;border-radius:0 0 8px 8px;">
        <p>¡Hola <strong>{html.escape(customer_name)}</strong>!</p>
        <p>Muchas gracias por comprar con <strong>CIMA Electronic VE</strong>. Para nosotros es un gusto atenderte y acompañarte en cada proyecto.</p>
        <p>Hemos registrado tu Nota de Entrega <strong>{html.escape(delivery_note)}</strong> y adjuntamos el documento en formato <strong>PDF</strong> para tu respaldo.</p>
        {date_line}
        {due_line}
        {seller_line}
        {disc_line}
        <table style="width:100%;border-collapse:collapse;font-size:13px;margin:12px 0;">
          <thead>
            <tr style="background:#f8fafc;">
              <th style="padding:8px;text-align:left;border-bottom:1px solid #cbd5e1;">Producto</th>
              <th style="padding:8px;text-align:right;border-bottom:1px solid #cbd5e1;">Cant.</th>
              <th style="padding:8px;text-align:right;border-bottom:1px solid #cbd5e1;">Precio</th>
              <th style="padding:8px;text-align:right;border-bottom:1px solid #cbd5e1;">Subtotal</th>
            </tr>
          </thead>
          <tbody>{''.join(rows_html)}</tbody>
        </table>
        <p style="font-size:16px;margin-top:12px;"><strong>Total: ${total_usd:.2f}</strong>{bs_line}</p>
        <p style="font-size:13px;color:#334155;margin-top:16px;">¡Gracias por tu confianza! Si tienes alguna consulta sobre tu pedido, estamos siempre a tu disposición.</p>
      </div>
    </div>
    """

    wa_lines = [
        f"¡Hola {customer_name}! Gracias por comprar con *CIMA Electronic VE*.",
        "Para nosotros es un gusto atenderte. Te enviamos tu *Nota de Entrega* en PDF con todos los detalles de tu compra:",
        f"• *Nota de Entrega:* {delivery_note}",
        f"• *Fecha:* {effective_date}",
    ]
    if due_date:
        wa_lines.append(f"• *Vencimiento:* {due_date}")
    if seller_name:
        wa_lines.append(f"• *Asesor:* {seller_name}")
    if float(discount_total or 0) > 0:
        wa_lines.append(f"• *Descuento aplicado:* -${float(discount_total):.2f}")
    wa_lines.append("*Productos:*")
    wa_lines.extend(item_lines_txt or ["• Ver detalle en el PDF adjunto"])
    if total_bs > 0:
        wa_lines.append(f"*Total:* ${total_usd:.2f} (Bs. {total_bs:,.2f})")
    else:
        wa_lines.append(f"*Total:* ${total_usd:.2f}")
    wa_lines.append("¡Muchas gracias por confiar en CIMA Electronic VE! Estamos a tu orden para lo que necesites.")
    wa_text = "\n".join(wa_lines)

    return {
        "subject": subject,
        "html": body,
        "whatsapp_text": wa_text,
        "whatsapp_url": build_whatsapp_link(customer_phone, wa_text) if customer_phone else "",
    }


def build_delivery_note_document_html(
    *,
    customer_info: dict,
    notes: list[dict],
    bs_rate: float = 0.0,
    company_name: str = "CIMA ELECTRONIC VE",
    logo_url: str = "/assets/cima_ve/images/cima-logo-color.png",
    generated_at: str = "",
    pdf_download_url: str = "",
) -> str:
    """Genera un documento imprimible tipo factura para una Nota de Entrega individual o consolidado de un cliente."""
    cust_name = html.escape(str(customer_info.get("customer_name") or customer_info.get("customer") or "Cliente"))
    cust_rif = html.escape(str(customer_info.get("rif_cedula") or "N/A"))
    cust_email = html.escape(str(customer_info.get("email") or "N/A"))
    cust_phone = html.escape(str(customer_info.get("phone") or "N/A"))
    cust_addr = html.escape(str(customer_info.get("address") or ""))

    is_single = len(notes) == 1
    doc_title = f"NOTA DE ENTREGA {html.escape(str(notes[0].get('name') or ''))}" if is_single else f"ESTADO DE CUENTA / NOTAS DE ENTREGA ({len(notes)})"

    total_amount = 0.0
    total_paid = 0.0
    total_pending = 0.0
    total_discount = 0.0
    item_rows: list[str] = []

    for n in notes:
        estado = str(n.get("ve_ne_estado") or "Pendiente")
        if estado != "Cancelada":
            total_amount += float(n.get("total_to_pay") or n.get("grand_total") or n.get("amount") or 0.0)
            total_paid += float(n.get("paid_amount") or 0.0)
            total_pending += float(n.get("remaining_amount") or 0.0)
            total_discount += float(n.get("discount_amount") or 0.0)
        note_name = html.escape(str(n.get("name") or ""))
        note_date = html.escape(str(n.get("posting_date") or ""))
        due_date = html.escape(str(n.get("ve_ne_fecha_vencimiento") or "-"))
        for it in (n.get("items") or []):
            qty = float(it.get("qty") or 0)
            rate = float(it.get("rate") or 0)
            amt = round(float(it.get("amount") if it.get("amount") is not None else qty * rate), 2)
            item_rows.append(
                f"<tr>"
                f"<td>{note_name}<br><small style='color:#64748b;'>{note_date} · Vence: {due_date}</small></td>"
                f"<td>{html.escape(str(it.get('item_code') or ''))}</td>"
                f"<td>{html.escape(str(it.get('item_name') or it.get('item_code') or ''))}</td>"
                f"<td style='text-align:right;'>{qty:g}</td>"
                f"<td style='text-align:right;'>${rate:.2f}</td>"
                f"<td style='text-align:right;'><strong>${amt:.2f}</strong></td>"
                f"</tr>"
            )

    total_amount = round(total_amount, 2)
    total_paid = round(total_paid, 2)
    total_pending = round(total_pending, 2)
    rate_val = float(bs_rate or 0.0)
    pending_bs = round(total_pending * rate_val, 2) if rate_val > 0 else 0.0
    total_bs = round(total_amount * rate_val, 2) if rate_val > 0 else 0.0

    notes_summary_rows = "".join(
        f"<tr>"
        f"<td><strong>{html.escape(str(n.get('name') or ''))}</strong></td>"
        f"<td>{html.escape(str(n.get('posting_date') or ''))}</td>"
        f"<td>{html.escape(str(n.get('ve_ne_fecha_vencimiento') or '-'))}</td>"
        f"<td>{html.escape(str(n.get('ve_ne_estado') or 'Pendiente'))}</td>"
        f"<td style='text-align:right;'>${float(n.get('total_to_pay') or n.get('amount') or 0):.2f}</td>"
        f"<td style='text-align:right;'>${float(n.get('paid_amount') or 0):.2f}</td>"
        f"<td style='text-align:right;'><strong>${float(n.get('remaining_amount') or 0):.2f}</strong></td>"
        f"</tr>"
        for n in notes
    )

    download_btn_html = (
        f'<a class="btn-print btn-download" href="{html.escape(pdf_download_url)}" target="_blank" rel="noopener">Descargar PDF</a>'
        if pdf_download_url
        else ""
    )

    return f"""<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1.0" />
<title>{doc_title} - {cust_name}</title>
<style>
  body {{ font-family: 'Segoe UI', Arial, sans-serif; color: #0f172a; margin: 0; padding: 24px; background: #f8fafc; }}
  .doc-sheet {{ max-width: 900px; margin: 0 auto; background: #fff; border: 1px solid #cbd5e1; border-radius: 10px; padding: 28px; box-shadow: 0 4px 18px rgba(15,23,42,0.06); }}
  .doc-header {{ display: flex; justify-content: space-between; align-items: flex-start; border-bottom: 2px solid #0f172a; padding-bottom: 16px; margin-bottom: 18px; }}
  .doc-brand {{ display: flex; align-items: center; gap: 14px; }}
  .doc-brand img {{ height: 54px; width: auto; }}
  .doc-title-box {{ text-align: right; }}
  .doc-title-box h1 {{ margin: 0; font-size: 18px; color: #0f172a; }}
  .doc-title-box p {{ margin: 4px 0 0; font-size: 12px; color: #475569; }}
  .doc-client {{ background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 8px; padding: 12px 16px; margin-bottom: 18px; display: grid; grid-template-columns: 1fr 1fr; gap: 8px 18px; font-size: 13px; }}
  .table-wrap {{ width: 100%; overflow-x: auto; -webkit-overflow-scrolling: touch; margin-bottom: 18px; }}
  table {{ width: 100%; border-collapse: collapse; font-size: 12.5px; }}
  th {{ background: #0f172a; color: #fff; padding: 8px; text-align: left; }}
  td {{ padding: 7px 8px; border-bottom: 1px solid #e2e8f0; vertical-align: top; }}
  .doc-totals {{ margin-left: auto; width: 320px; max-width: 100%; background: #f8fafc; border: 1px solid #cbd5e1; border-radius: 8px; padding: 12px 14px; font-size: 13px; box-sizing: border-box; }}
  .doc-total-row {{ display: flex; justify-content: space-between; margin-bottom: 5px; }}
  .doc-total-grand {{ font-size: 15px; font-weight: 700; border-top: 1px solid #cbd5e1; padding-top: 6px; margin-top: 6px; }}
  .no-print {{ margin-bottom: 16px; display: flex; justify-content: flex-end; flex-wrap: wrap; gap: 8px; }}
  .btn-print {{ background: #0f172a; color: #fff; border: none; padding: 8px 16px; border-radius: 6px; cursor: pointer; font-weight: 600; text-decoration: none; display: inline-flex; align-items: center; font-size: 13px; }}
  .btn-download {{ background: #2563eb; }}
  @media (max-width: 768px) {{
    body {{ padding: 10px; }}
    .doc-sheet {{ padding: 14px; border-radius: 8px; }}
    .doc-header {{ flex-direction: column; gap: 12px; }}
    .doc-title-box {{ text-align: left; }}
    .doc-client {{ grid-template-columns: 1fr; }}
    .no-print {{ justify-content: stretch; }}
    .btn-print {{ flex: 1 1 auto; justify-content: center; padding: 10px 14px; }}
  }}
  @media print {{ body {{ background: #fff; padding: 0; }} .doc-sheet {{ border: none; box-shadow: none; padding: 0; }} .no-print {{ display: none; }} }}
</style>
</head>
<body>
  <div class="doc-sheet">
    <div class="no-print">
      <button class="btn-print" onclick="window.print()">Imprimir / Guardar PDF</button>
      {download_btn_html}
    </div>
    <div class="doc-header">
      <div class="doc-brand">
        <img src="{html.escape(logo_url)}" alt="CIMA" onerror="this.style.display='none'" />
        <div>
          <strong style="font-size:17px;">{html.escape(company_name)}</strong><br>
          <span style="font-size:12px;color:#475569;">Documento Administrativo de Entrega</span>
        </div>
      </div>
      <div class="doc-title-box">
        <h1>{doc_title}</h1>
        <p>Emitido: {html.escape(generated_at or date.today().isoformat())}</p>
        {f'<p>Tasa ref.: Bs. {rate_val:,.2f} / USD</p>' if rate_val > 0 else ''}
      </div>
    </div>

    <div class="doc-client">
      <div><strong>Cliente:</strong> {cust_name}</div>
      <div><strong>Cédula / RIF:</strong> {cust_rif}</div>
      <div><strong>Correo:</strong> {cust_email}</div>
      <div><strong>Teléfono:</strong> {cust_phone}</div>
      {f'<div style="grid-column:1 / -1;"><strong>Dirección:</strong> {cust_addr}</div>' if cust_addr else ''}
    </div>

    <h3 style="font-size:14px;margin:0 0 8px;">Resumen de Notas de Entrega</h3>
    <div class="table-wrap">
    <table>
      <thead>
        <tr>
          <th>Nota</th><th>Fecha</th><th>Vencimiento</th><th>Estado</th>
          <th style="text-align:right;">Total ($)</th><th style="text-align:right;">Pagado ($)</th><th style="text-align:right;">Pendiente ($)</th>
        </tr>
      </thead>
      <tbody>{notes_summary_rows}</tbody>
    </table>
    </div>

    <h3 style="font-size:14px;margin:0 0 8px;">Detalle de Productos</h3>
    <div class="table-wrap">
    <table>
      <thead>
        <tr>
          <th>Nota / Fecha</th><th>Código</th><th>Producto</th>
          <th style="text-align:right;">Cant.</th><th style="text-align:right;">Precio Unit.</th><th style="text-align:right;">Subtotal</th>
        </tr>
      </thead>
      <tbody>{''.join(item_rows) or '<tr><td colspan="6" style="text-align:center;">Sin ítems detallados</td></tr>'}</tbody>
    </table>
    </div>

    <div class="doc-totals">
      <div class="doc-total-row"><span>Total Notas:</span><strong>${total_amount:,.2f}{f' (Bs. {total_bs:,.2f})' if total_bs > 0 else ''}</strong></div>
      {f'<div class="doc-total-row"><span>Descuentos:</span><span>-${total_discount:,.2f}</span></div>' if total_discount > 0 else ''}
      <div class="doc-total-row"><span>Total Pagado:</span><span>${total_paid:,.2f}</span></div>
      <div class="doc-total-row doc-total-grand"><span>Saldo Pendiente:</span><span>${total_pending:,.2f}{f' (Bs. {pending_bs:,.2f})' if pending_bs > 0 else ''}</span></div>
    </div>
  </div>
</body>
</html>"""


def build_payment_registered_whatsapp_payload(
    *,
    customer_name: str,
    payment_amount: float,
    payment_method: str,
    reference: str = "",
    registered_by: str = "",
    allocations: list[dict] | None = None,
    total_pending_after: float = 0.0,
    bs_rate: float = 0.0,
    paid_now_bs: float = 0.0,
    screenshot_url: str = "",
    whatsapp_number: str | None = None,
    chat_id: str | None = None,
) -> dict:
    """Construye el payload JSON y comprobante WhatsApp al registrar un pago de cliente."""
    paid_usd = round(max(float(payment_amount or 0.0), 0.0), 2)
    rate_bs = max(float(bs_rate or 0.0), 0.0)
    paid_bs = round(float(paid_now_bs or 0.0), 2)
    if paid_bs <= 0.0 and rate_bs > 0.0:
        paid_bs = round(paid_usd * rate_bs, 2)
    pending_after = round(max(float(total_pending_after or 0.0), 0.0), 2)
    clean_customer = (customer_name or "").strip() or "Cliente"
    clean_method = (payment_method or "").strip() or "Pago"
    clean_ref = (reference or "").strip()
    clean_user = (registered_by or "").strip()
    clean_screenshot = (screenshot_url or "").strip()
    target_wa = (whatsapp_number or "").strip() or DEFAULT_NOTIFICATION_WHATSAPP
    target_chat_id = (chat_id or "").strip() or DEFAULT_WHATSAPP_PAYMENTS_CHAT_ID

    amount_line = f"Monto pagado: ${paid_usd:,.2f}"
    if paid_bs > 0:
        amount_line += f" (Bs. {paid_bs:,.2f})"

    lines = [
        "Pago registrado — CIMA Electronic VE",
        f"Cliente: {clean_customer}",
        amount_line,
        f"Método de pago: {clean_method}",
    ]
    if clean_ref:
        lines.append(f"Referencia: {clean_ref}")
    if clean_user:
        lines.append(f"Registrado por: {clean_user}")

    dn_names: list[str] = []
    alloc_rows = allocations or []
    if alloc_rows:
        lines.append("Notas aplicadas:")
        for row in alloc_rows:
            dn_name = str(row.get("delivery_note") or "").strip()
            if dn_name:
                dn_names.append(dn_name)
            alloc_amt = round(float(row.get("allocated_amount") or row.get("paid_amount") or 0.0), 2)
            estado = str(row.get("new_estado") or row.get("ve_ne_estado") or "").strip()
            estado_txt = f" ({estado})" if estado else ""
            lines.append(f"• {dn_name or 'Nota'}: ${alloc_amt:,.2f}{estado_txt}")

    lines.append(f"Saldo pendiente del cliente: ${pending_after:,.2f}")
    if clean_screenshot:
        lines.append(f"Comprobante adjunto: {clean_screenshot}")

    return {
        "event": "payment_registered",
        "recipient_type": "company_payments",
        "chat_id": target_chat_id,
        "to": target_wa,
        "delivery_note": dn_names[0] if dn_names else "",
        "delivery_notes": dn_names,
        "customer_name": clean_customer,
        "grand_total": paid_usd,
        "payment_amount": paid_usd,
        "payment_amount_bs": paid_bs,
        "payment_method": clean_method,
        "reference": clean_ref,
        "registered_by": clean_user,
        "total_pending_after": pending_after,
        "screenshot_url": clean_screenshot,
        "message": "\n".join(lines),
    }
