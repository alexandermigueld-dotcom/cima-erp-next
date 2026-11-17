from __future__ import annotations

import json


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
