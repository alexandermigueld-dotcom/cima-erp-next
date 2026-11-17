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


DEFAULT_COMMISSION_RULES: list[dict] = [
    {"label": "Meta Ads 7%", "channel": "Meta Ads", "percentage": 7.0},
    {"label": "Detal 8%", "channel": "Detal", "percentage": 8.0},
    {"label": "Mayor 10%", "channel": "Mayor", "percentage": 10.0},
]


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
    """Calcula el margen de ganancia (venta neta - costo) y la comisión del vendedor sobre ese margen."""
    net_sale = round(max(float(net_sale_amount or 0.0), 0.0), 2)
    cost = round(max(float(total_cost or 0.0), 0.0), 2)
    margin = round(net_sale - cost, 2)
    positive_margin = max(margin, 0.0)
    pct = round(min(max(float(commission_pct or 0.0), 0.0), 100.0), 2)
    commission = round(positive_margin * (pct / 100.0), 2)
    return {
        "net_sale_amount": net_sale,
        "total_cost": cost,
        "margin_amount": margin,
        "commission_pct": pct,
        "commission_amount": commission,
    }


def summarize_seller_commissions(notes: list[dict]) -> list[dict]:
    """Agrupa las notas activas (no canceladas) por vendedor para calcular el pago de comisiones."""
    buckets: dict[str, dict] = {}
    for n in notes or []:
        if (n.get("ve_ne_estado") or "") == "Cancelada" or int(n.get("docstatus") or 0) == 2:
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
            },
        )
        comm = round(float(n.get("commission_amount") or 0.0), 2)
        b["notes_count"] += 1
        b["sales_total"] += float(n.get("net_total") or n.get("amount") or 0.0)
        b["cost_total"] += float(n.get("cost_total") or 0.0)
        b["margin_total"] += float(n.get("margin_amount") or 0.0)
        b["commission_total"] += comm
        if n.get("ve_ne_estado") == "Pagada":
            b["paid_notes_count"] += 1
            b["paid_commission"] += comm
        else:
            b["pending_notes_count"] += 1
            b["pending_commission"] += comm

    result: list[dict] = []
    for b in buckets.values():
        b["sales_total"] = round(b["sales_total"], 2)
        b["cost_total"] = round(b["cost_total"], 2)
        b["margin_total"] = round(b["margin_total"], 2)
        b["commission_total"] = round(b["commission_total"], 2)
        b["paid_commission"] = round(b["paid_commission"], 2)
        b["pending_commission"] = round(b["pending_commission"], 2)
        result.append(b)
    result.sort(key=lambda r: (r["commission_total"], r["sales_total"]), reverse=True)
    return result


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

        comm_option = str(row.get("ve_ne_comision_opcion") or row.get("canal_venta") or "").strip()
        comm_pct = round(float(row.get("ve_ne_comision_pct") or 0.0), 2)
        cost_total = round(float(row.get("ve_ne_costo_total") or 0.0), 2)
        margin_amount = round(float(row.get("ve_ne_margen_ganancia") or 0.0), 2)
        comm_amount = round(float(row.get("ve_ne_comision_monto") or 0.0), 2)
        if estado == "Cancelada":
            comm_amount = 0.0
        else:
            total_cost += cost_total
            total_margin += margin_amount
            total_commission += comm_amount
            if estado == "Pagada":
                paid_commission += comm_amount
            else:
                pending_commission += comm_amount

        item["commission_option"] = comm_option
        item["commission_pct"] = comm_pct
        item["cost_total"] = cost_total
        item["margin_amount"] = margin_amount
        item["commission_amount"] = comm_amount
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
            "total_cost": round(total_cost, 2),
            "total_margin": round(total_margin, 2),
            "total_commission": round(total_commission, 2),
            "paid_commission": round(paid_commission, 2),
            "pending_commission": round(pending_commission, 2),
        },
        "notes": normalized,
    }


DEFAULT_NOTIFICATION_EMAILS = ["cimaelectronic@gmail.com", "alexandermigueld@gmail.com"]
DEFAULT_NOTIFICATION_WHATSAPP = "+584243472198"


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
    if seller_name:
        text_lines.append(f"Vendedor: {seller_name}")
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
    if seller_name:
        extra_html_rows += f"<p><strong>Vendedor:</strong> {seller_name}</p>"
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
