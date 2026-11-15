from __future__ import annotations

import json

from cima_ve.api._compat import whitelist
from cima_ve.services.seller_pos_service import (
    build_seller_invoice_summary,
    validate_quick_invoice_input,
)


@whitelist()
def get_seller_bootstrap() -> dict:
    """Devuelve configuración inicial para la interfaz simplificada de vendedores."""
    import frappe

    companies = frappe.get_all(
        "Company",
        fields=["name", "default_currency"],
        order_by="creation asc",
        limit_page_length=5,
    )
    default_company = companies[0]["name"] if companies else ""

    price_lists = frappe.get_all(
        "Price List",
        filters={"selling": 1, "enabled": 1},
        fields=["name", "currency"],
        order_by="name asc",
        limit_page_length=50,
    )
    warehouses = frappe.get_all(
        "Warehouse",
        filters={"is_group": 0, "disabled": 0},
        fields=["name", "warehouse_name", "company"],
        order_by="name asc",
        limit_page_length=50,
    )

    preferred_pl = next(
        (pl["name"] for pl in price_lists if "detal usd" in pl["name"].lower()),
        price_lists[0]["name"] if price_lists else "Standard Selling",
    )

    return {
        "company": default_company,
        "default_price_list": preferred_pl,
        "price_lists": price_lists,
        "warehouses": warehouses,
        "default_warehouse": warehouses[0]["name"] if warehouses else "",
    }


@whitelist()
def search_inventory_and_prices(
    query: str = "",
    price_list: str = "",
    warehouse: str = "",
    limit: int = 60,
) -> list[dict]:
    """Busca productos con su stock disponible y precio según la lista seleccionada."""
    import frappe

    limit = min(max(int(limit or 60), 1), 200)
    search_like = f"%{(query or '').strip()}%"

    conditions = ["i.disabled = 0", "i.is_sales_item = 1"]
    params: dict = {
        "search": search_like,
        "price_list": price_list or "",
        "warehouse": warehouse or "",
        "limit": limit,
    }

    if (query or "").strip():
        conditions.append(
            "(i.item_code LIKE %(search)s OR i.item_name LIKE %(search)s OR i.item_group LIKE %(search)s)"
        )

    warehouse_filter = "AND b.warehouse = %(warehouse)s" if warehouse else ""
    where_clause = " AND ".join(conditions)

    rows = frappe.db.sql(
        f"""
        SELECT
            i.item_code,
            i.item_name,
            i.item_group,
            COALESCE(SUM(b.actual_qty), 0) AS stock_qty,
            COALESCE(MAX(ip.price_list_rate), i.standard_rate, 0) AS price,
            COALESCE(MAX(ip.currency), 'USD') AS currency,
            COALESCE(%(warehouse)s, '') AS warehouse,
            %(price_list)s AS price_list
        FROM `tabItem` i
        LEFT JOIN `tabBin` b
            ON b.item_code = i.item_code {warehouse_filter}
        LEFT JOIN `tabItem Price` ip
            ON ip.item_code = i.item_code
            AND ip.selling = 1
            AND (%(price_list)s = '' OR ip.price_list = %(price_list)s)
        WHERE {where_clause}
        GROUP BY i.item_code, i.item_name, i.item_group, i.standard_rate
        ORDER BY stock_qty DESC, i.item_name ASC
        LIMIT %(limit)s
        """,
        params,
        as_dict=True,
    )
    return rows


@whitelist()
def search_customers(query: str = "", limit: int = 20) -> list[dict]:
    """Busca clientes por nombre, código o RIF/Cédula."""
    import frappe

    q = (query or "").strip()
    limit = min(max(int(limit or 20), 1), 50)
    if not q:
        return frappe.get_all(
            "Customer",
            filters={"disabled": 0},
            fields=["name", "customer_name", "tax_id", "ve_rif_cedula"],
            order_by="modified desc",
            limit_page_length=limit,
        )

    like = f"%{q}%"
    return frappe.db.sql(
        """
        SELECT name, customer_name, tax_id, ve_rif_cedula
        FROM `tabCustomer`
        WHERE disabled = 0
          AND (
              name LIKE %(q)s
              OR customer_name LIKE %(q)s
              OR COALESCE(tax_id, '') LIKE %(q)s
              OR COALESCE(ve_rif_cedula, '') LIKE %(q)s
          )
        ORDER BY customer_name ASC
        LIMIT %(limit)s
        """,
        {"q": like, "limit": limit},
        as_dict=True,
    )


@whitelist()
def quick_create_customer(
    customer_name: str,
    rif_cedula: str,
    taxpayer_type: str = "No Contribuyente",
) -> dict:
    """Crea un cliente rápido desde la pantalla de facturación."""
    import frappe

    name_clean = (customer_name or "").strip()
    rif_clean = (rif_cedula or "").strip().upper()
    if not name_clean:
        frappe.throw("El nombre o razón social del cliente es obligatorio.")
    if not rif_clean:
        frappe.throw("La Cédula o RIF del cliente es obligatoria.")

    doc = frappe.get_doc(
        {
            "doctype": "Customer",
            "customer_name": name_clean,
            "customer_type": "Individual" if rif_clean.startswith(("V", "E")) else "Company",
            "tax_id": rif_clean,
            "ve_rif_cedula": rif_clean,
            "ve_taxpayer_type": taxpayer_type or "No Contribuyente",
        }
    )
    doc.insert()
    return {
        "name": doc.name,
        "customer_name": doc.customer_name,
        "ve_rif_cedula": doc.ve_rif_cedula,
    }


@whitelist()
def create_quick_invoice(
    customer: str,
    items: str | list[dict],
    price_list: str = "",
    warehouse: str = "",
    payment_method: str = "Contado USD",
    apply_igtf: int | bool = False,
    submit: int | bool = True,
) -> dict:
    """Crea y opcionalmente confirma una Sales Invoice desde la interfaz de vendedor."""
    import frappe
    from cima_ve.api.cashea import create_cashea_checkout

    parsed_items = json.loads(items) if isinstance(items, str) else items
    validated = validate_quick_invoice_input(customer, parsed_items)
    apply_igtf_flag = bool(int(apply_igtf)) if isinstance(apply_igtf, (int, str)) else bool(apply_igtf)
    submit_flag = bool(int(submit)) if isinstance(submit, (int, str)) else bool(submit)

    currency = "USD"
    if price_list:
        pl_currency = frappe.db.get_value("Price List", price_list, "currency")
        if pl_currency:
            currency = pl_currency

    invoice_items = []
    for row in validated:
        item_dict = {
            "item_code": row.item_code,
            "qty": row.qty,
            "rate": row.unit_price,
        }
        if warehouse:
            item_dict["warehouse"] = warehouse
        invoice_items.append(item_dict)

    doc = frappe.get_doc(
        {
            "doctype": "Sales Invoice",
            "customer": customer,
            "currency": currency,
            "selling_price_list": price_list or None,
            "update_stock": 1 if warehouse else 0,
            "ve_igtf_aplicado": 1 if apply_igtf_flag else 0,
            "remarks": f"Factura rápida vendedor | Método: {payment_method}",
            "items": invoice_items,
        }
    )
    doc.insert()
    if submit_flag:
        doc.submit()
        doc.reload()

    cashea_data = None
    if (payment_method or "").strip().lower() == "cashea":
        cashea_data = create_cashea_checkout(doc.name)
        doc.reload()

    summary = build_seller_invoice_summary(parsed_items, apply_igtf=apply_igtf_flag)
    return {
        "invoice_name": doc.name,
        "status": doc.status,
        "currency": doc.currency,
        "grand_total": float(doc.grand_total or summary.grand_total),
        "tax_summary": summary.to_dict(),
        "fiscal": {
            "control_number": getattr(doc, "ve_numero_control", None),
            "fiscal_invoice_number": getattr(doc, "ve_numero_factura_fiscal", None),
            "status": getattr(doc, "ve_fiscal_status", None),
            "pdf_url": getattr(doc, "ve_fiscal_pdf_url", None),
        },
        "cashea": cashea_data,
    }
