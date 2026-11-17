from __future__ import annotations

import json


DEFAULT_AUTO_DISCOUNT_TIERS: list[dict] = [
    {"label": "Compra < $100", "min_amount": 0.0, "max_amount": 99.99, "discount_percentage": 0.0},
    {"label": "Compra $500 - $1,000", "min_amount": 500.0, "max_amount": 1000.0, "discount_percentage": 4.76},
    {"label": "Compra > $1,000", "min_amount": 1000.01, "max_amount": None, "discount_percentage": 9.09},
]


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


def summarize_delivery_notes(notes: list[dict]) -> dict:
    """Genera KPIs y normaliza el listado de Notas de Entrega."""
    total_count = 0
    pending_count = 0
    partial_count = 0
    pending_total = 0.0
    paid_count = 0
    paid_total = 0.0
    cancelled_count = 0
    cancelled_total = 0.0

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

        item = dict(row)
        item["ve_ne_estado"] = estado
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
        normalized.append(item)

    return {
        "summary": {
            "total_count": total_count,
            "pending_count": pending_count,
            "partial_count": partial_count,
            "pending_total": round(pending_total, 2),
            "paid_count": paid_count,
            "paid_total": round(paid_total, 2),
            "cancelled_count": cancelled_count,
            "cancelled_total": round(cancelled_total, 2),
        },
        "notes": normalized,
    }
