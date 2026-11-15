from __future__ import annotations

from cima_ve.api._compat import whitelist
from cima_ve.services.fiscal_printer import (
    FiscalInvoiceItem,
    FiscalInvoicePayload,
    FiscalPrinterClient,
)


def _get_fiscal_client() -> tuple[FiscalPrinterClient, float, float]:
    import frappe

    settings = frappe.get_single("Cima VE Settings")
    client = FiscalPrinterClient(
        api_url=settings.fiscal_api_url or "",
        api_token=settings.get_password("fiscal_api_token") if settings.fiscal_api_token else "",
        series_prefix=settings.fiscal_series_prefix or "00",
        simulation_mode=bool(settings.simulation_mode),
    )
    iva_rate = float(settings.iva_rate or 16.0)
    igtf_rate = float(settings.igtf_rate or 3.0)
    return client, iva_rate, igtf_rate


@whitelist()
def stamp_sales_invoice(sales_invoice_name: str) -> dict:
    """Timbra una Sales Invoice en la Imprenta Digital (real o simulada)."""
    import frappe

    doc = frappe.get_doc("Sales Invoice", sales_invoice_name)
    customer_rif = (
        frappe.db.get_value("Customer", doc.customer, "ve_rif_cedula")
        or frappe.db.get_value("Customer", doc.customer, "tax_id")
        or "V-00000000"
    )
    client, iva_rate, igtf_rate = _get_fiscal_client()

    items = [
        FiscalInvoiceItem(
            item_code=row.item_code,
            description=row.item_name or row.description or row.item_code,
            qty=float(row.qty),
            unit_price=float(row.rate),
            is_exempt=bool(getattr(row, "is_free_item", False)),
        )
        for row in doc.items
    ]
    payload = FiscalInvoicePayload(
        invoice_name=doc.name,
        customer_name=doc.customer_name or doc.customer,
        customer_rif_cedula=str(customer_rif),
        currency=doc.currency or "USD",
        items=items,
        apply_igtf=bool(getattr(doc, "ve_igtf_aplicado", 0)),
        iva_rate=iva_rate,
        igtf_rate=igtf_rate,
    )
    result = client.issue_digital_invoice(payload)

    doc.db_set("ve_numero_control", result.control_number)
    doc.db_set("ve_numero_factura_fiscal", result.fiscal_invoice_number)
    doc.db_set("ve_fiscal_status", result.status)
    doc.db_set("ve_fiscal_pdf_url", result.pdf_url)
    doc.db_set("ve_fiscal_hash", result.qr_hash)
    doc.db_set("ve_igtf_amount", result.tax_breakdown.igtf_amount)
    return result.to_dict()
