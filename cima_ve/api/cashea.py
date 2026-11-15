from __future__ import annotations

from cima_ve.api._compat import whitelist
from cima_ve.services.cashea_client import CasheaClient


def _get_cashea_client() -> CasheaClient:
    import frappe

    settings = frappe.get_single("Cima VE Settings")
    return CasheaClient(
        api_url=settings.cashea_api_url or "",
        api_key=settings.get_password("cashea_api_key") if settings.cashea_api_key else "",
        webhook_secret=(
            settings.get_password("cashea_webhook_secret")
            if settings.cashea_webhook_secret
            else "sim-cashea-secret"
        ),
        simulation_mode=bool(settings.simulation_mode),
    )


@whitelist()
def create_cashea_checkout(sales_invoice_name: str) -> dict:
    """Genera una orden de pago Cashea (real o simulada) para una Sales Invoice."""
    import frappe

    doc = frappe.get_doc("Sales Invoice", sales_invoice_name)
    customer_rif = frappe.db.get_value("Customer", doc.customer, "ve_rif_cedula") or doc.customer

    client = _get_cashea_client()
    items = [
        {"code": row.item_code, "name": row.item_name, "qty": row.qty, "rate": row.rate}
        for row in doc.items
    ]
    callback_url = frappe.utils.get_url("/api/method/cima_ve.api.cashea.webhook")
    order = client.create_order(
        reference_id=doc.name,
        amount_usd=float(doc.grand_total),
        customer_name=doc.customer_name or doc.customer,
        customer_id_number=str(customer_rif),
        callback_url=callback_url,
        items=items,
    )

    doc.db_set("cashea_order_id", order.order_id)
    doc.db_set("cashea_status", "Simulada" if order.is_simulated else order.status)
    doc.db_set("cashea_down_payment", order.down_payment_usd)
    return order.to_dict()


@whitelist(allow_guest=True)
def webhook() -> dict:
    """Endpoint receptor de webhooks de Cashea."""
    import frappe

    client = _get_cashea_client()
    raw_body = frappe.request.get_data() or b"{}"
    signature = frappe.get_request_header("X-Cashea-Signature") or ""
    event = client.parse_webhook(raw_body, signature)

    if event.reference_id and frappe.db.exists("Sales Invoice", event.reference_id):
        frappe.db.set_value(
            "Sales Invoice",
            event.reference_id,
            {
                "cashea_order_id": event.order_id,
                "cashea_status": event.status,
                "cashea_down_payment": event.down_payment_usd,
            },
        )
    return {"ok": True, "order_id": event.order_id, "status": event.status}
