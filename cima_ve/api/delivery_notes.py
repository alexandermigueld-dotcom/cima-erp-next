from __future__ import annotations

import json

from cima_ve.api._compat import whitelist
from cima_ve.services.delivery_note_service import (
    compute_delivery_note_settlement_totals,
    summarize_delivery_notes,
)
from cima_ve.services.seller_pos_service import validate_quick_invoice_input


def _get_tax_rates() -> tuple[float, float]:
    import frappe

    settings = frappe.get_single("Cima VE Settings")
    return float(settings.iva_rate or 16.0), float(settings.igtf_rate or 3.0)


def _resolve_tax_account(company: str, keyword: str = "") -> str:
    import frappe

    filters = {"company": company, "is_group": 0, "account_type": "Tax"}
    accounts = frappe.get_all("Account", filters=filters, pluck="name", limit=20)
    if keyword and accounts:
        match = next((a for a in accounts if keyword.lower() in a.lower()), "")
        if match:
            return match
    if accounts:
        return accounts[0]

    liab = frappe.get_all(
        "Account",
        filters={"company": company, "is_group": 0, "root_type": "Liability"},
        pluck="name",
        limit=1,
    )
    if liab:
        return liab[0]
    any_acc = frappe.get_all("Account", filters={"company": company, "is_group": 0}, pluck="name", limit=1)
    return any_acc[0] if any_acc else ""


@whitelist()
def create_quick_delivery_note(
    customer: str,
    items: str | list[dict],
    price_list: str = "",
    warehouse: str = "",
    sales_channel: str = "Detal",
    sales_person: str = "",
    notes: str = "",
) -> dict:
    """Crea y confirma una Nota de Entrega (Delivery Note): descuenta inventario sin cobrar dinero aún."""
    import frappe
    from cima_ve.api.seller_pos import _apply_required_sales_metadata, _resolve_company_and_currency

    parsed_items = json.loads(items) if isinstance(items, str) else items
    validated = validate_quick_invoice_input(customer, parsed_items)
    company, currency = _resolve_company_and_currency(price_list)

    dn_items = []
    for row in validated:
        item_dict = {
            "item_code": row.item_code,
            "qty": row.qty,
        }
        if warehouse:
            item_dict["warehouse"] = warehouse
        dn_items.append(item_dict)

    seller_user = frappe.session.user
    seller_name = frappe.utils.get_fullname(seller_user) or seller_user

    doc = frappe.get_doc(
        {
            "doctype": "Delivery Note",
            "company": company,
            "customer": customer,
            "currency": currency,
            "selling_price_list": price_list or None,
            "set_warehouse": warehouse or None,
            "ignore_pricing_rule": 0,
            "ve_vendedor_usuario": seller_user,
            "ve_vendedor_nombre": seller_name,
            "ve_ne_estado": "Pendiente",
            "remarks": (notes or f"Nota de Entrega ({seller_name}) — Pendiente por cobrar").strip(),
            "items": dn_items,
        }
    )
    _apply_required_sales_metadata(doc, sales_channel=sales_channel, sales_person=sales_person)
    doc.insert()
    doc.submit()
    doc.reload()

    return {
        "delivery_note": doc.name,
        "status": doc.status,
        "ve_ne_estado": getattr(doc, "ve_ne_estado", None) or "Pendiente",
        "currency": doc.currency,
        "net_total": float(doc.net_total or 0),
        "grand_total": float(doc.grand_total or 0),
        "seller": {
            "user": getattr(doc, "ve_vendedor_usuario", None) or seller_user,
            "fullname": getattr(doc, "ve_vendedor_nombre", None) or seller_name,
        },
    }


@whitelist()
def get_delivery_notes(
    status: str = "",
    from_date: str = "",
    to_date: str = "",
    seller: str = "",
    search: str = "",
) -> dict:
    """Lista todas las Notas de Entrega con su estado (Pendiente/Pagada/Cancelada), cliente, vendedor e ítems."""
    import frappe

    frappe.only_for("System Manager")

    dn_meta = frappe.get_meta("Delivery Note")
    has_estado = dn_meta.has_field("ve_ne_estado")
    has_vendedor_user = dn_meta.has_field("ve_vendedor_usuario")
    has_vendedor_name = dn_meta.has_field("ve_vendedor_nombre")
    has_fecha_res = dn_meta.has_field("ve_ne_fecha_resolucion")
    has_user_res = dn_meta.has_field("ve_ne_usuario_resolucion")
    has_metodo = dn_meta.has_field("ve_ne_metodo_pago")
    has_iva = dn_meta.has_field("ve_ne_aplica_iva")
    has_igtf = dn_meta.has_field("ve_ne_aplica_igtf")
    has_factura = dn_meta.has_field("ve_ne_factura")
    has_motivo = dn_meta.has_field("ve_ne_motivo_cancelacion")

    conditions = ["dn.docstatus IN (1, 2)"]
    params: dict = {}

    if from_date:
        conditions.append("dn.posting_date >= %(from_date)s")
        params["from_date"] = from_date
    if to_date:
        conditions.append("dn.posting_date <= %(to_date)s")
        params["to_date"] = to_date
    if seller:
        if has_vendedor_user:
            conditions.append("COALESCE(NULLIF(dn.ve_vendedor_usuario, ''), dn.owner) = %(seller)s")
        else:
            conditions.append("dn.owner = %(seller)s")
        params["seller"] = seller
    if search:
        conditions.append("(dn.name LIKE %(q)s OR dn.customer LIKE %(q)s OR dn.customer_name LIKE %(q)s)")
        params["q"] = f"%{search.strip()}%"

    select_cols = [
        "dn.name",
        "dn.docstatus",
        "dn.posting_date",
        "dn.posting_time",
        "dn.creation",
        "dn.owner",
        "dn.customer",
        "dn.customer_name",
        "dn.currency",
        "dn.net_total",
        "dn.grand_total",
        "dn.total_qty",
        "dn.status",
        "COALESCE(NULLIF(dn.ve_vendedor_usuario, ''), dn.owner) AS seller_user" if has_vendedor_user else "dn.owner AS seller_user",
        "dn.ve_vendedor_nombre AS seller_name" if has_vendedor_name else "'' AS seller_name",
        "dn.ve_ne_estado AS ve_ne_estado" if has_estado else "'' AS ve_ne_estado",
        "dn.ve_ne_fecha_resolucion AS ve_ne_fecha_resolucion" if has_fecha_res else "NULL AS ve_ne_fecha_resolucion",
        "dn.ve_ne_usuario_resolucion AS ve_ne_usuario_resolucion" if has_user_res else "'' AS ve_ne_usuario_resolucion",
        "dn.ve_ne_metodo_pago AS ve_ne_metodo_pago" if has_metodo else "'' AS ve_ne_metodo_pago",
        "dn.ve_ne_aplica_iva AS ve_ne_aplica_iva" if has_iva else "0 AS ve_ne_aplica_iva",
        "dn.ve_ne_aplica_igtf AS ve_ne_aplica_igtf" if has_igtf else "0 AS ve_ne_aplica_igtf",
        "dn.ve_ne_factura AS ve_ne_factura" if has_factura else "'' AS ve_ne_factura",
        "dn.ve_ne_motivo_cancelacion AS ve_ne_motivo_cancelacion" if has_motivo else "'' AS ve_ne_motivo_cancelacion",
    ]

    rows = frappe.db.sql(
        f"""
        SELECT {", ".join(select_cols)}
        FROM `tabDelivery Note` dn
        WHERE {" AND ".join(conditions)}
        ORDER BY dn.creation DESC
        LIMIT 300
        """,
        params,
        as_dict=True,
    )

    dn_names = [r["name"] for r in rows]
    items_by_dn: dict[str, list[dict]] = {}
    if dn_names:
        dn_items = frappe.get_all(
            "Delivery Note Item",
            filters={"parent": ["in", dn_names]},
            fields=["parent", "item_code", "item_name", "qty", "rate", "amount"],
            limit_page_length=3000,
        )
        for it in dn_items:
            items_by_dn.setdefault(it["parent"], []).append(it)

    for r in rows:
        r["items"] = items_by_dn.get(r["name"], [])
        if not r.get("seller_name") and r.get("seller_user"):
            r["seller_name"] = frappe.utils.get_fullname(r["seller_user"]) or r["seller_user"]

    summarized = summarize_delivery_notes(rows)
    if status:
        summarized["notes"] = [n for n in summarized["notes"] if n["ve_ne_estado"] == status]

    iva_rate, igtf_rate = _get_tax_rates()
    modes = frappe.get_all("Mode of Payment", filters={"enabled": 1}, pluck="name", order_by="name asc")
    payment_options = modes or ["Contado USD", "Pago Móvil / Bs", "Cashea", "Punto de Venta", "Zelle", "Binance Pay", "Transferencia"]
    for default_m in ["Contado USD", "Pago Móvil / Bs", "Cashea", "Punto de Venta", "Zelle", "Binance Pay", "Transferencia Bancaria"]:
        if default_m not in payment_options:
            payment_options.append(default_m)

    sellers = sorted({n.get("seller_user") for n in rows if n.get("seller_user")})
    seller_options = [
        {"user": u, "fullname": frappe.utils.get_fullname(u) or u}
        for u in sellers
    ]

    summarized["config"] = {
        "iva_rate": iva_rate,
        "igtf_rate": igtf_rate,
        "payment_methods": payment_options,
        "sellers": seller_options,
    }
    return summarized


@whitelist()
def cancel_delivery_note(delivery_note: str, reason: str = "") -> dict:
    """Cancela una Nota de Entrega pendiente, devolviendo el inventario automáticamente y registrando fecha/usuario."""
    import frappe
    from frappe.utils import now_datetime

    frappe.only_for("System Manager")

    dn = frappe.get_doc("Delivery Note", delivery_note)
    if dn.docstatus == 2 or getattr(dn, "ve_ne_estado", "") == "Cancelada":
        frappe.throw("Esta Nota de Entrega ya está cancelada.")
    if dn.docstatus != 1:
        frappe.throw("Solo se pueden cancelar Notas de Entrega confirmadas.")
    if getattr(dn, "ve_ne_estado", "") == "Pagada" or getattr(dn, "ve_ne_factura", ""):
        frappe.throw("Esta Nota de Entrega ya fue pagada y facturada.")

    resolved_at = str(now_datetime())
    resolved_by = frappe.session.user
    clean_reason = (reason or "").strip() or "Cancelada desde Notas de Entrega"

    dn.cancel()
    dn.db_set("ve_ne_estado", "Cancelada")
    dn.db_set("ve_ne_fecha_resolucion", resolved_at)
    dn.db_set("ve_ne_usuario_resolucion", resolved_by)
    dn.db_set("ve_ne_motivo_cancelacion", clean_reason)
    dn.add_comment("Comment", f"Nota de Entrega CANCELADA por {resolved_by} el {resolved_at}. Motivo: {clean_reason}. Inventario restaurado.")

    return {
        "ok": True,
        "delivery_note": dn.name,
        "ve_ne_estado": "Cancelada",
        "fecha_resolucion": resolved_at,
        "usuario_resolucion": resolved_by,
    }


@whitelist()
def mark_delivery_note_paid(
    delivery_note: str,
    payment_method: str,
    apply_iva: int | bool = 0,
    apply_igtf: int | bool = 0,
    reference: str = "",
) -> dict:
    """Marca una Nota de Entrega como Pagada: crea Sales Invoice (con IVA/IGTF elegidos) y Payment Entry."""
    import frappe
    from frappe.utils import now_datetime, today
    from cima_ve.api.seller_pos import _apply_required_sales_metadata

    frappe.only_for("System Manager")

    dn = frappe.get_doc("Delivery Note", delivery_note)
    if dn.docstatus != 1:
        frappe.throw("La Nota de Entrega no está activa (puede estar cancelada o en borrador).")
    if getattr(dn, "ve_ne_estado", "") == "Pagada" or getattr(dn, "ve_ne_factura", ""):
        frappe.throw(f"Esta Nota de Entrega ya fue pagada (Factura {getattr(dn, 've_ne_factura', '')}).")

    clean_method = (payment_method or "").strip()
    if not clean_method:
        frappe.throw("Selecciona un método de pago.")

    iva_flag = bool(int(apply_iva)) if isinstance(apply_iva, (int, str)) else bool(apply_iva)
    igtf_flag = bool(int(apply_igtf)) if isinstance(apply_igtf, (int, str)) else bool(apply_igtf)
    iva_rate, igtf_rate = _get_tax_rates()

    from erpnext.stock.doctype.delivery_note.delivery_note import make_sales_invoice

    si = make_sales_invoice(dn.name)
    si.update_stock = 0
    si.set("taxes", [])
    si.ve_igtf_aplicado = 1 if igtf_flag else 0

    seller_user = getattr(dn, "ve_vendedor_usuario", None) or dn.owner or frappe.session.user
    seller_name = getattr(dn, "ve_vendedor_nombre", None) or frappe.utils.get_fullname(seller_user) or seller_user
    si.ve_vendedor_usuario = seller_user
    si.ve_vendedor_nombre = seller_name

    totals = compute_delivery_note_settlement_totals(
        net_total=float(dn.net_total or dn.grand_total or 0.0),
        apply_iva=iva_flag,
        apply_igtf=igtf_flag,
        iva_rate=iva_rate,
        igtf_rate=igtf_rate,
    )

    if iva_flag and totals["iva_amount"] > 0:
        iva_acc = _resolve_tax_account(dn.company, "iva")
        if iva_acc:
            si.append(
                "taxes",
                {
                    "charge_type": "Actual",
                    "account_head": iva_acc,
                    "description": f"IVA ({iva_rate:g}%)",
                    "tax_amount": totals["iva_amount"],
                },
            )

    if igtf_flag and totals["igtf_amount"] > 0:
        igtf_acc = _resolve_tax_account(dn.company, "igtf")
        if igtf_acc:
            si.append(
                "taxes",
                {
                    "charge_type": "Actual",
                    "account_head": igtf_acc,
                    "description": f"IGTF Divisas ({igtf_rate:g}%)",
                    "tax_amount": totals["igtf_amount"],
                },
            )

    si.remarks = f"Liquidación Nota de Entrega {dn.name} | Método: {clean_method}" + (f" | Ref: {reference}" if reference else "")
    _apply_required_sales_metadata(si, sales_channel=getattr(dn, "canal_venta", "Detal") or "Detal")
    si.flags.ignore_fiscal_stamp = True
    si.insert(ignore_permissions=True)
    si.submit()

    payment_entry_name = ""
    try:
        from erpnext.accounts.doctype.payment_entry.payment_entry import get_payment_entry

        pe = get_payment_entry("Sales Invoice", si.name)
        if frappe.db.exists("Mode of Payment", clean_method):
            pe.mode_of_payment = clean_method
        pe.reference_no = (reference or dn.name)[:140]
        pe.reference_date = today()
        pe.remarks = f"Pago Nota de Entrega {dn.name} ({clean_method})"
        pe.insert(ignore_permissions=True)
        pe.submit()
        payment_entry_name = pe.name
    except Exception:
        frappe.log_error(frappe.get_traceback(), f"Payment Entry Error for {dn.name}")

    resolved_at = str(now_datetime())
    resolved_by = frappe.session.user

    dn.db_set("ve_ne_estado", "Pagada")
    dn.db_set("ve_ne_fecha_resolucion", resolved_at)
    dn.db_set("ve_ne_usuario_resolucion", resolved_by)
    dn.db_set("ve_ne_metodo_pago", clean_method)
    dn.db_set("ve_ne_aplica_iva", 1 if iva_flag else 0)
    dn.db_set("ve_ne_aplica_igtf", 1 if igtf_flag else 0)
    dn.db_set("ve_ne_factura", si.name)
    dn.add_comment(
        "Comment",
        f"Nota de Entrega PAGADA por {resolved_by} el {resolved_at}. Método: {clean_method} | IVA: {'Sí' if iva_flag else 'No'} | IGTF: {'Sí' if igtf_flag else 'No'} | Factura: {si.name}",
    )

    return {
        "ok": True,
        "delivery_note": dn.name,
        "sales_invoice": si.name,
        "payment_entry": payment_entry_name,
        "grand_total": float(si.grand_total or totals["grand_total"]),
        "ve_ne_estado": "Pagada",
        "fecha_resolucion": resolved_at,
        "usuario_resolucion": resolved_by,
        "metodo_pago": clean_method,
        "apply_iva": iva_flag,
        "apply_igtf": igtf_flag,
    }
