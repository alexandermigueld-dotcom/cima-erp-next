from __future__ import annotations

from datetime import date, timedelta

from cima_ve.api._compat import whitelist
from cima_ve.services.bi_service import (
    analyze_inventory_intelligence,
    build_weekly_stockout_email_html,
)


def compute_bi_snapshot() -> dict:
    import frappe

    settings = frappe.get_single("Cima VE Settings")
    lead_days = int(getattr(settings, "china_lead_time_days", 45) or 45)
    safety_days = int(getattr(settings, "bi_safety_stock_days", 15) or 15)
    window_days = int(getattr(settings, "bi_analysis_window_days", 90) or 90)

    since_date = (date.today() - timedelta(days=window_days)).isoformat()

    items = frappe.db.sql(
        """
        SELECT
            i.item_code,
            i.item_name,
            i.item_group,
            i.valuation_rate,
            i.standard_rate AS price,
            COALESCE(SUM(b.actual_qty), 0) AS stock_qty,
            COALESCE(SUM(b.ordered_qty), 0) AS incoming_qty
        FROM `tabItem` i
        LEFT JOIN `tabBin` b ON b.item_code = i.item_code
        WHERE i.disabled = 0
          AND i.is_stock_item = 1
        GROUP BY i.item_code, i.item_name, i.item_group, i.valuation_rate, i.standard_rate
        """,
        as_dict=True,
    )

    sales_rows = frappe.db.sql(
        """
        SELECT
            sii.item_code,
            SUM(sii.qty) AS qty,
            SUM(sii.amount) AS amount
        FROM `tabSales Invoice Item` sii
        INNER JOIN `tabSales Invoice` si ON si.name = sii.parent
        WHERE si.docstatus = 1
          AND si.posting_date >= %(since_date)s
        GROUP BY sii.item_code
        """,
        {"since_date": since_date},
        as_dict=True,
    )

    return analyze_inventory_intelligence(
        items=items,
        sales_rows=sales_rows,
        china_lead_time_days=lead_days,
        safety_stock_days=safety_days,
        analysis_window_days=window_days,
    )


@whitelist()
def get_bi_dashboard() -> dict:
    """Devuelve el análisis completo de Business Intelligence e importación desde China."""
    return compute_bi_snapshot()


@whitelist()
def send_bi_stockout_alert_now() -> dict:
    """Envía manualmente el correo de alerta de agotamiento vs tiempo de llegada desde China."""
    import frappe

    settings = frappe.get_single("Cima VE Settings")
    raw_emails = str(getattr(settings, "bi_alert_emails", "") or "").strip()
    recipients = [e.strip() for e in raw_emails.split(",") if e.strip()]
    if not recipients:
        frappe.throw("Configure al menos un correo en 'Cima VE Settings -> Correos para Alertas Semanales BI'.")

    analysis = compute_bi_snapshot()
    critical = analysis["critical_items"]
    if not critical:
        return {"sent": False, "critical_count": 0, "message": "No hay productos en riesgo de agotamiento."}

    html = build_weekly_stockout_email_html(analysis)
    frappe.sendmail(
        recipients=recipients,
        subject=f"[CIMA BI] Alerta Semanal: {len(critical)} productos se agotarán antes de llegar de China",
        message=html,
    )
    return {"sent": True, "critical_count": len(critical), "recipients": recipients}
