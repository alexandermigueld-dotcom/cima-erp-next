from __future__ import annotations

from cima_ve.services.fiscal_printer import FiscalInvoiceItem, calculate_venezuela_taxes


def validate_venezuela_fiscal(doc, method=None) -> None:
    """Asigna el vendedor responsable y calcula el monto referencial de IGTF (3%)."""
    try:
        import frappe

        seller_user = getattr(doc, "ve_vendedor_usuario", None) or getattr(doc, "owner", None) or frappe.session.user
        if seller_user and not getattr(doc, "ve_vendedor_usuario", None):
            doc.ve_vendedor_usuario = seller_user
        if seller_user and not getattr(doc, "ve_vendedor_nombre", None):
            doc.ve_vendedor_nombre = frappe.utils.get_fullname(seller_user) or seller_user
    except Exception:
        pass

    if not getattr(doc, "ve_igtf_aplicado", 0) or not getattr(doc, "items", None):
        doc.ve_igtf_amount = 0.0
        return

    items = [
        FiscalInvoiceItem(
            item_code=row.item_code or "ITEM",
            description=row.item_name or "Item",
            qty=float(row.qty or 0),
            unit_price=float(row.rate or 0),
            is_exempt=False,
        )
        for row in doc.items
    ]
    breakdown = calculate_venezuela_taxes(items, apply_igtf=True)
    doc.ve_igtf_amount = breakdown.igtf_amount


def on_submit_fiscal_stamp(doc, method=None) -> None:
    """Al confirmar la Sales Invoice, solicita el timbrado digital (real o simulado)."""
    import frappe
    from cima_ve.api.fiscal import stamp_sales_invoice

    settings = frappe.get_single("Cima VE Settings")
    if not settings.fiscal_enabled:
        return
    if getattr(doc, "ve_numero_control", None):
        return

    stamp_sales_invoice(doc.name)
