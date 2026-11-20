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
