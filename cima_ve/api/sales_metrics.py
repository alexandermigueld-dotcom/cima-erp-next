from __future__ import annotations

from cima_ve.api._compat import whitelist
from cima_ve.services.sales_metrics_service import compute_sales_metrics


@whitelist()
def get_sales_metrics(
    from_date: str = "",
    to_date: str = "",
    user: str = "",
    sales_channel: str = "",
    company: str = "",
    include_returns: int | bool = 0,
) -> dict:
    """Devuelve métricas globales de ventas y desglose completo por usuario vendedor."""
    import frappe

    frappe.only_for("System Manager")

    si_meta = frappe.get_meta("Sales Invoice")
    has_vendedor_user = si_meta.has_field("ve_vendedor_usuario")
    has_vendedor_name = si_meta.has_field("ve_vendedor_nombre")
    has_canal = si_meta.has_field("canal_venta")
    has_igtf = si_meta.has_field("ve_igtf_amount")
    has_fiscal_status = si_meta.has_field("ve_fiscal_status")
    has_control = si_meta.has_field("ve_numero_control")
    has_cashea_id = si_meta.has_field("cashea_order_id")
    has_cashea_status = si_meta.has_field("cashea_status")

    conditions = ["si.docstatus = 1"]
    params: dict = {}

    include_ret_flag = bool(int(include_returns)) if isinstance(include_returns, (int, str)) else bool(include_returns)
    if not include_ret_flag:
        conditions.append("si.is_return = 0")

    if from_date:
        conditions.append("si.posting_date >= %(from_date)s")
        params["from_date"] = from_date
    if to_date:
        conditions.append("si.posting_date <= %(to_date)s")
        params["to_date"] = to_date
    if company:
        conditions.append("si.company = %(company)s")
        params["company"] = company
    if sales_channel and has_canal:
        conditions.append("si.canal_venta = %(sales_channel)s")
        params["sales_channel"] = sales_channel
    if user:
        if has_vendedor_user:
            conditions.append("COALESCE(NULLIF(si.ve_vendedor_usuario, ''), si.owner) = %(user)s")
        else:
            conditions.append("si.owner = %(user)s")
        params["user"] = user

    select_cols = [
        "si.name",
        "si.posting_date",
        "si.owner",
        "si.customer",
        "si.customer_name",
        "si.currency",
        "si.grand_total",
        "si.net_total",
        "si.total_taxes_and_charges",
        "si.paid_amount",
        "si.outstanding_amount",
        "si.total_qty",
        "si.is_return",
        "COALESCE(NULLIF(si.ve_vendedor_usuario, ''), si.owner) AS seller_user" if has_vendedor_user else "si.owner AS seller_user",
        "si.ve_vendedor_nombre AS seller_name" if has_vendedor_name else "'' AS seller_name",
        "si.canal_venta AS canal_venta" if has_canal else "'' AS canal_venta",
        "si.ve_igtf_amount AS ve_igtf_amount" if has_igtf else "0 AS ve_igtf_amount",
        "si.ve_fiscal_status AS ve_fiscal_status" if has_fiscal_status else "'' AS ve_fiscal_status",
        "si.ve_numero_control AS ve_numero_control" if has_control else "'' AS ve_numero_control",
        "si.cashea_order_id AS cashea_order_id" if has_cashea_id else "'' AS cashea_order_id",
        "si.cashea_status AS cashea_status" if has_cashea_status else "'' AS cashea_status",
    ]

    where_sql = " AND ".join(conditions)
    invoices = frappe.db.sql(
        f"""
        SELECT {", ".join(select_cols)}
        FROM `tabSales Invoice` si
        WHERE {where_sql}
        ORDER BY si.posting_date DESC, si.creation DESC
        """,
        params,
        as_dict=True,
    )

    # Resolve full names for seller_user values
    user_ids = {row.get("seller_user") for row in invoices if row.get("seller_user")}
    fullname_map: dict[str, str] = {}
    if user_ids:
        user_rows = frappe.get_all(
            "User",
            filters={"name": ["in", list(user_ids)]},
            fields=["name", "full_name"],
        )
        for u in user_rows:
            fullname_map[u["name"]] = u.get("full_name") or u["name"]

    for row in invoices:
        su = row.get("seller_user") or row.get("owner") or ""
        if not row.get("seller_name"):
            row["seller_name"] = fullname_map.get(su, su)

    invoice_items: list[dict] = []
    if invoices:
        inv_names = [row["name"] for row in invoices]
        invoice_items = frappe.get_all(
            "Sales Invoice Item",
            filters={"parent": ["in", inv_names]},
            fields=["parent", "item_code", "item_name", "qty", "amount"],
            limit_page_length=5000,
        )

    companies = frappe.get_all(
        "Company",
        fields=["name", "default_currency"],
        order_by="creation asc",
        limit_page_length=20,
    )
    default_currency = companies[0]["default_currency"] if companies and companies[0].get("default_currency") else "USD"

    metrics = compute_sales_metrics(
        invoices=invoices,
        invoice_items=invoice_items,
        default_currency=default_currency,
    )

    # Available filter options (all active sellers + channels + companies)
    all_sellers_sql = (
        "SELECT DISTINCT COALESCE(NULLIF(ve_vendedor_usuario, ''), owner) AS user_id FROM `tabSales Invoice` WHERE docstatus = 1"
        if has_vendedor_user
        else "SELECT DISTINCT owner AS user_id FROM `tabSales Invoice` WHERE docstatus = 1"
    )
    seller_rows = frappe.db.sql(all_sellers_sql, as_dict=True)
    all_user_ids = sorted({r["user_id"] for r in seller_rows if r.get("user_id")} | {frappe.session.user})
    seller_options = []
    if all_user_ids:
        u_docs = frappe.get_all(
            "User",
            filters={"name": ["in", all_user_ids]},
            fields=["name", "full_name"],
            order_by="full_name asc",
        )
        seller_options = [
            {"user": u["name"], "fullname": u.get("full_name") or u["name"]}
            for u in u_docs
        ]

    channels: list[str] = []
    if has_canal:
        raw_opts = si_meta.get_field("canal_venta").options or ""
        channels = [opt.strip() for opt in raw_opts.splitlines() if opt.strip()]

    metrics["filter_options"] = {
        "users": seller_options,
        "channels": channels,
        "companies": [c["name"] for c in companies],
        "current_user": frappe.session.user,
    }
    return metrics
