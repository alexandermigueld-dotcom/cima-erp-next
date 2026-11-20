from __future__ import annotations


def send_weekly_bi_stockout_alert() -> dict:
    """Tarea programada semanal: envía alertas de productos con stock menor al lead time de China."""
    import frappe
    from cima_ve.api.bi import compute_bi_snapshot
    from cima_ve.services.bi_service import build_weekly_stockout_email_html

    settings = frappe.get_single("Cima VE Settings")
    if not getattr(settings, "bi_weekly_alerts_enabled", 1):
        return {"sent": False, "reason": "disabled"}

    raw_emails = str(getattr(settings, "bi_alert_emails", "") or "").strip()
    recipients = [e.strip() for e in raw_emails.split(",") if e.strip()]
    if not recipients:
        return {"sent": False, "reason": "no_recipients"}

    analysis = compute_bi_snapshot()
    critical = analysis["critical_items"]
    if not critical:
        return {"sent": False, "reason": "no_critical_items"}

    html = build_weekly_stockout_email_html(analysis)
    frappe.sendmail(
        recipients=recipients,
        subject=f"[CIMA BI] Alerta Semanal: {len(critical)} productos críticos (China {analysis['config']['china_lead_time_days']}d)",
        message=html,
    )
    return {"sent": True, "critical_count": len(critical), "recipients": recipients}


def send_monday_overdue_delivery_notes_alert(force: bool = False) -> dict:
    """Tarea programada (Lunes): envía reporte por correo de Notas de Entrega vencidas sin pago completo."""
    import frappe
    from frappe.utils import today
    from cima_ve.services.delivery_note_service import (
        DEFAULT_NOTIFICATION_EMAILS,
        build_overdue_delivery_notes_email_html,
        filter_overdue_delivery_notes,
        parse_notification_emails,
    )

    settings = frappe.get_single("Cima VE Settings")
    if not force and settings.meta.has_field("overdue_dn_weekly_alerts_enabled"):
        if not int(getattr(settings, "overdue_dn_weekly_alerts_enabled", 1) or 0):
            return {"sent": False, "reason": "disabled"}

    raw_emails = ""
    if settings.meta.has_field("overdue_dn_alert_emails"):
        raw_emails = str(getattr(settings, "overdue_dn_alert_emails", "") or "").strip()
    if not raw_emails and settings.meta.has_field("notify_order_email"):
        raw_emails = str(getattr(settings, "notify_order_email", "") or "").strip()
    recipients = parse_notification_emails(raw_emails or ", ".join(DEFAULT_NOTIFICATION_EMAILS))

    dn_meta = frappe.get_meta("Delivery Note")
    if not dn_meta.has_field("ve_ne_fecha_vencimiento"):
        return {"sent": False, "reason": "missing_due_date_field"}

    ref_date = str(today())
    rows = frappe.db.sql(
        """
        SELECT
            dn.name,
            dn.docstatus,
            dn.posting_date,
            dn.customer,
            dn.customer_name,
            dn.grand_total,
            dn.net_total,
            dn.owner,
            COALESCE(NULLIF(dn.ve_vendedor_usuario, ''), dn.owner) AS seller_user,
            dn.ve_vendedor_nombre AS seller_name,
            dn.ve_ne_estado,
            dn.ve_ne_fecha_vencimiento,
            dn.ve_ne_factura,
            dn.ve_ne_monto_total,
            dn.ve_ne_monto_pagado,
            dn.ve_ne_saldo_pendiente,
            dn.ve_ne_historial_pagos
        FROM `tabDelivery Note` dn
        WHERE dn.docstatus = 1
          AND COALESCE(dn.ve_ne_estado, 'Pendiente') IN ('Pendiente', 'Pago Parcial')
          AND dn.ve_ne_fecha_vencimiento IS NOT NULL
          AND dn.ve_ne_fecha_vencimiento < %(ref_date)s
        ORDER BY dn.ve_ne_fecha_vencimiento ASC, dn.creation ASC
        """,
        {"ref_date": ref_date},
        as_dict=True,
    )

    for r in rows:
        if not r.get("seller_name") and r.get("seller_user"):
            r["seller_name"] = frappe.utils.get_fullname(r["seller_user"]) or r["seller_user"]

    overdue = filter_overdue_delivery_notes(rows, reference_date=ref_date)
    if not overdue:
        return {"sent": False, "reason": "no_overdue_notes"}

    total_pending = round(sum(float(n.get("remaining_amount") or 0.0) for n in overdue), 2)
    html_body = build_overdue_delivery_notes_email_html(overdue, reference_date=ref_date)
    frappe.sendmail(
        recipients=recipients,
        subject=f"[CIMA VE] Reporte Lunes: {len(overdue)} Notas de Entrega vencidas (${total_pending:,.2f} pendiente)",
        message=html_body,
        now=True,
    )
    return {
        "sent": True,
        "overdue_count": len(overdue),
        "total_pending": total_pending,
        "recipients": recipients,
    }
