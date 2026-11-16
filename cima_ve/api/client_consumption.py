from __future__ import annotations

from cima_ve.api._compat import whitelist
from cima_ve.services.client_consumption_service import compute_client_consumption


@whitelist()
def get_client_consumption(
    from_date: str = "",
    to_date: str = "",
    seller: str = "",
    search: str = "",
) -> dict:
    """Devuelve el consumo por cliente y cuánto ha comprado cada cliente a cada vendedor."""
    import frappe

    frappe.only_for("System Manager")

    si_meta = frappe.get_meta("Sales Invoice")
    has_si_user = si_meta.has_field("ve_vendedor_usuario")
    has_si_name = si_meta.has_field("ve_vendedor_nombre")

    si_conditions = ["si.docstatus = 1", "si.is_return = 0"]
    params: dict = {}

    if from_date:
        si_conditions.append("si.posting_date >= %(from_date)s")
        params["from_date"] = from_date
    if to_date:
        si_conditions.append("si.posting_date <= %(to_date)s")
        params["to_date"] = to_date
    if seller:
        if has_si_user:
            si_conditions.append("COALESCE(NULLIF(si.ve_vendedor_usuario, ''), si.owner) = %(seller)s")
        else:
            si_conditions.append("si.owner = %(seller)s")
        params["seller"] = seller
    if search:
        si_conditions.append("(si.customer LIKE %(q)s OR si.customer_name LIKE %(q)s)")
        params["q"] = f"%{search.strip()}%"

    invoices = frappe.db.sql(
        f"""
        SELECT
            si.name, si.posting_date, si.owner, si.customer, si.customer_name,
            si.currency, si.grand_total, si.paid_amount, si.outstanding_amount, si.total_qty,
            {"COALESCE(NULLIF(si.ve_vendedor_usuario, ''), si.owner)" if has_si_user else "si.owner"} AS seller_user,
            {"si.ve_vendedor_nombre" if has_si_name else "''"} AS seller_name
        FROM `tabSales Invoice` si
        WHERE {" AND ".join(si_conditions)}
        """,
        params,
        as_dict=True,
    )

    dn_meta = frappe.get_meta("Delivery Note")
    has_dn_user = dn_meta.has_field("ve_vendedor_usuario")
    has_dn_name = dn_meta.has_field("ve_vendedor_nombre")
    has_dn_estado = dn_meta.has_field("ve_ne_estado")

    dn_conditions = ["dn.docstatus = 1"]
    if has_dn_estado:
        dn_conditions.append("COALESCE(NULLIF(dn.ve_ne_estado, ''), 'Pendiente') = 'Pendiente'")
    if from_date:
        dn_conditions.append("dn.posting_date >= %(from_date)s")
    if to_date:
        dn_conditions.append("dn.posting_date <= %(to_date)s")
    if seller:
        if has_dn_user:
            dn_conditions.append("COALESCE(NULLIF(dn.ve_vendedor_usuario, ''), dn.owner) = %(seller)s")
        else:
            dn_conditions.append("dn.owner = %(seller)s")
    if search:
        dn_conditions.append("(dn.customer LIKE %(q)s OR dn.customer_name LIKE %(q)s)")

    delivery_notes = frappe.db.sql(
        f"""
        SELECT
            dn.name, dn.posting_date, dn.owner, dn.customer, dn.customer_name,
            dn.currency, dn.net_total, dn.grand_total,
            {"COALESCE(NULLIF(dn.ve_vendedor_usuario, ''), dn.owner)" if has_dn_user else "dn.owner"} AS seller_user,
            {"dn.ve_vendedor_nombre" if has_dn_name else "''"} AS seller_name
        FROM `tabDelivery Note` dn
        WHERE {" AND ".join(dn_conditions)}
        """,
        params,
        as_dict=True,
    )

    all_user_ids = {
        row.get("seller_user")
        for row in (invoices + delivery_notes)
        if row.get("seller_user")
    }
    fullname_map: dict[str, str] = {}
    if all_user_ids:
        for u in frappe.get_all("User", filters={"name": ["in", list(all_user_ids)]}, fields=["name", "full_name"]):
            fullname_map[u["name"]] = u.get("full_name") or u["name"]

    for row in invoices + delivery_notes:
        if not row.get("seller_name") and row.get("seller_user"):
            row["seller_name"] = fullname_map.get(row["seller_user"], row["seller_user"])

    cust_ids = sorted({row.get("customer") for row in (invoices + delivery_notes) if row.get("customer")})
    customer_meta: dict[str, dict] = {}
    if cust_ids:
        cust_fields = ["name", "customer_name", "tax_id"]
        if frappe.get_meta("Customer").has_field("ve_rif_cedula"):
            cust_fields.append("ve_rif_cedula")
        for c in frappe.get_all("Customer", filters={"name": ["in", cust_ids]}, fields=cust_fields):
            customer_meta[c["name"]] = c

    companies = frappe.get_all("Company", fields=["default_currency"], order_by="creation asc", limit=1)
    default_currency = companies[0]["default_currency"] if companies and companies[0].get("default_currency") else "USD"

    result = compute_client_consumption(
        invoices=invoices,
        delivery_notes=delivery_notes,
        customer_meta=customer_meta,
        default_currency=default_currency,
    )
    result["filter_options"] = {
        "sellers": [
            {"user": uid, "fullname": fullname_map.get(uid, uid)}
            for uid in sorted(all_user_ids)
        ]
    }
    return result
