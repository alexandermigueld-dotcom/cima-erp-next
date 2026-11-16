from __future__ import annotations


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


def summarize_delivery_notes(notes: list[dict]) -> dict:
    """Genera KPIs y normaliza el listado de Notas de Entrega."""
    total_count = 0
    pending_count = 0
    pending_total = 0.0
    paid_count = 0
    paid_total = 0.0
    cancelled_count = 0
    cancelled_total = 0.0

    normalized: list[dict] = []
    for row in notes or []:
        docstatus = int(row.get("docstatus") or 0)
        estado = (row.get("ve_ne_estado") or "").strip()
        if docstatus == 2 or estado == "Cancelada":
            estado = "Cancelada"
        elif estado == "Pagada" or row.get("ve_ne_factura"):
            estado = "Pagada"
        else:
            estado = "Pendiente"

        amount = round(float(row.get("grand_total") or row.get("net_total") or 0.0), 2)
        total_count += 1
        if estado == "Pendiente":
            pending_count += 1
            pending_total += amount
        elif estado == "Pagada":
            paid_count += 1
            paid_total += amount
        else:
            cancelled_count += 1
            cancelled_total += amount

        item = dict(row)
        item["ve_ne_estado"] = estado
        item["amount"] = amount
        normalized.append(item)

    return {
        "summary": {
            "total_count": total_count,
            "pending_count": pending_count,
            "pending_total": round(pending_total, 2),
            "paid_count": paid_count,
            "paid_total": round(paid_total, 2),
            "cancelled_count": cancelled_count,
            "cancelled_total": round(cancelled_total, 2),
        },
        "notes": normalized,
    }
