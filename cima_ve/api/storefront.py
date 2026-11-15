from __future__ import annotations

import json

from cima_ve.api._compat import whitelist
from cima_ve.services.storefront_service import (
    DEFAULT_PRODUCT_IMAGE,
    build_payment_methods_catalog,
    calculate_storefront_totals,
    normalize_rif_or_cedula,
    validate_registration_payload,
)


def _get_storefront_config() -> dict:
    import frappe

    settings = frappe.get_single("Cima VE Settings")
    warehouses = frappe.get_all(
        "Warehouse",
        filters={"is_group": 0, "disabled": 0},
        pluck="name",
        order_by="creation asc",
    )
    default_wh = settings.get("storefront_warehouse") or ""
    if not default_wh:
        preferred = next(
            (w for w in warehouses if "white point" in w.lower() or "principal" in w.lower()),
            warehouses[0] if warehouses else "",
        )
        default_wh = preferred

    webshop_pl = ""
    if frappe.db.exists("DocType", "Webshop Settings"):
        webshop_pl = frappe.db.get_single_value("Webshop Settings", "price_list") or ""

    price_list = webshop_pl or "Detal USD"
    if not frappe.db.exists("Price List", price_list):
        pl_list = frappe.get_all("Price List", filters={"selling": 1, "enabled": 1}, pluck="name", limit=1)
        price_list = pl_list[0] if pl_list else "Standard Selling"

    companies = frappe.get_all("Company", pluck="name", order_by="creation asc", limit=1)
    company = companies[0] if companies else ""

    return {
        "company": company,
        "warehouse": default_wh,
        "price_list": price_list,
        "simulation_mode": bool(settings.simulation_mode),
        "cashea_enabled": bool(settings.cashea_enabled),
        "iva_rate": float(settings.iva_rate or 16.0),
        "igtf_rate": float(settings.igtf_rate or 3.0),
        "google_pay_merchant_id": settings.get("google_pay_merchant_id") or "",
        "google_pay_merchant_name": settings.get("google_pay_merchant_name") or "CIMA ELECTRONIC VE",
        "pago_movil_info": settings.get("pago_movil_info") or "",
        "zelle_info": settings.get("zelle_info") or "",
        "binance_pay_info": settings.get("binance_pay_info") or "",
        "bank_transfer_info": settings.get("bank_transfer_info") or "",
    }


def _get_google_auth_info() -> dict:
    import frappe

    if not frappe.db.exists("DocType", "Social Login Key"):
        return {"google_enabled": False, "google_auth_url": ""}

    keys = frappe.get_all(
        "Social Login Key",
        filters={"enable_social_login": 1},
        fields=["name", "provider_name", "client_id"],
    )
    google_key = next(
        (k for k in keys if "google" in (k.get("provider_name") or k.get("name") or "").lower() and k.get("client_id")),
        None,
    )
    if not google_key:
        return {"google_enabled": False, "google_auth_url": ""}

    try:
        from frappe.utils.oauth import get_oauth2_authorize_url

        auth_url = get_oauth2_authorize_url(google_key["name"], "/tienda")
        return {"google_enabled": bool(auth_url), "google_auth_url": auth_url or ""}
    except Exception:
        return {"google_enabled": False, "google_auth_url": ""}


def _find_customer_for_user(user_email: str) -> str | None:
    import frappe

    if not user_email or user_email == "Guest":
        return None

    contacts = frappe.get_all("Contact", filters={"email_id": user_email}, pluck="name", limit=5)
    for contact_name in contacts:
        links = frappe.get_all(
            "Dynamic Link",
            filters={"parent": contact_name, "parenttype": "Contact", "link_doctype": "Customer"},
            pluck="link_name",
            limit=1,
        )
        if links:
            return links[0]

    customer_by_email = frappe.db.get_value("Customer", {"email_id": user_email}, "name")
    if customer_by_email:
        return customer_by_email

    return None


def _ensure_customer_for_user(
    user_email: str,
    full_name: str = "",
    ve_rif_cedula: str = "",
    ve_taxpayer_type: str = "No Contribuyente",
    phone: str = "",
    address: str = "",
) -> str:
    import frappe

    existing = _find_customer_for_user(user_email)
    user_full_name = full_name or frappe.db.get_value("User", user_email, "full_name") or user_email.split("@")[0]

    if existing:
        if ve_rif_cedula:
            norm_rif = normalize_rif_or_cedula(ve_rif_cedula)
            frappe.db.set_value(
                "Customer",
                existing,
                {
                    "ve_rif_cedula": norm_rif,
                    "tax_id": norm_rif,
                    "ve_taxpayer_type": ve_taxpayer_type or "No Contribuyente",
                },
            )
        if phone:
            frappe.db.set_value("Customer", existing, "mobile_no", phone)
        return existing

    norm_rif = normalize_rif_or_cedula(ve_rif_cedula)
    customer_group = "Individual"
    if frappe.db.exists("DocType", "Webshop Settings"):
        customer_group = frappe.db.get_single_value("Webshop Settings", "default_customer_group") or "Individual"
    if not frappe.db.exists("Customer Group", customer_group):
        groups = frappe.get_all("Customer Group", filters={"is_group": 0}, pluck="name", limit=1)
        customer_group = groups[0] if groups else "All Customer Groups"

    territories = frappe.get_all("Territory", filters={"is_group": 0}, pluck="name", limit=1)
    territory = territories[0] if territories else "All Territories"

    cust_doc = frappe.get_doc(
        {
            "doctype": "Customer",
            "customer_name": user_full_name,
            "customer_type": "Company" if norm_rif.startswith(("J-", "G-")) else "Individual",
            "customer_group": customer_group,
            "territory": territory,
            "email_id": user_email,
            "mobile_no": phone or "",
            "tax_id": norm_rif,
            "ve_rif_cedula": norm_rif,
            "ve_taxpayer_type": ve_taxpayer_type or "No Contribuyente",
        }
    )
    cust_doc.insert(ignore_permissions=True)

    contact = frappe.get_doc(
        {
            "doctype": "Contact",
            "first_name": user_full_name,
            "email_id": user_email,
            "mobile_no": phone or "",
            "user": user_email if frappe.db.exists("User", user_email) else None,
            "email_ids": [{"email_id": user_email, "is_primary": 1}],
            "links": [{"link_doctype": "Customer", "link_name": cust_doc.name}],
        }
    )
    contact.insert(ignore_permissions=True)

    if address:
        _upsert_customer_address(cust_doc.name, user_full_name, address, phone, user_email)

    frappe.db.commit()
    return cust_doc.name


def _upsert_customer_address(
    customer_name: str,
    title: str,
    address_line: str,
    phone: str = "",
    email: str = "",
) -> str | None:
    import frappe

    if not (address_line or "").strip():
        return None

    links = frappe.get_all(
        "Dynamic Link",
        filters={"link_doctype": "Customer", "link_name": customer_name, "parenttype": "Address"},
        pluck="parent",
        limit=1,
    )
    if links:
        addr = frappe.get_doc("Address", links[0])
        addr.address_line1 = address_line.strip()
        if phone:
            addr.phone = phone.strip()
        addr.save(ignore_permissions=True)
        return addr.name

    country = "Venezuela" if frappe.db.exists("Country", "Venezuela") else frappe.db.get_default("country") or "Venezuela"
    addr = frappe.get_doc(
        {
            "doctype": "Address",
            "address_title": title or customer_name,
            "address_type": "Billing",
            "address_line1": address_line.strip(),
            "city": "Venezuela",
            "country": country,
            "phone": phone or "",
            "email_id": email or "",
            "is_primary_address": 1,
            "is_shipping_address": 1,
            "links": [{"link_doctype": "Customer", "link_name": customer_name}],
        }
    )
    addr.insert(ignore_permissions=True)
    return addr.name


def _get_customer_profile_dict(user_email: str) -> dict:
    import frappe

    if not user_email or user_email == "Guest":
        return {
            "is_guest": True,
            "email": "",
            "full_name": "Invitado",
            "customer_name": "",
            "ve_rif_cedula": "",
            "ve_taxpayer_type": "No Contribuyente",
            "phone": "",
            "address": "",
        }

    user_doc = frappe.db.get_value("User", user_email, ["full_name", "user_image"], as_dict=True) or {}
    customer_name = _ensure_customer_for_user(user_email, full_name=user_doc.get("full_name") or "")
    cust = frappe.db.get_value(
        "Customer",
        customer_name,
        ["customer_name", "ve_rif_cedula", "ve_taxpayer_type", "mobile_no"],
        as_dict=True,
    ) or {}

    address_text = ""
    addr_links = frappe.get_all(
        "Dynamic Link",
        filters={"link_doctype": "Customer", "link_name": customer_name, "parenttype": "Address"},
        pluck="parent",
        limit=1,
    )
    if addr_links:
        address_text = frappe.db.get_value("Address", addr_links[0], "address_line1") or ""

    return {
        "is_guest": False,
        "email": user_email,
        "full_name": cust.get("customer_name") or user_doc.get("full_name") or user_email,
        "user_image": user_doc.get("user_image") or "",
        "customer_name": customer_name,
        "ve_rif_cedula": cust.get("ve_rif_cedula") or "",
        "ve_taxpayer_type": cust.get("ve_taxpayer_type") or "No Contribuyente",
        "phone": cust.get("mobile_no") or "",
        "address": address_text,
    }


@whitelist(allow_guest=True)
def get_storefront_bootstrap() -> dict:
    """Devuelve configuración inicial, categorías, métodos de pago y usuario actual."""
    import frappe

    cfg = _get_storefront_config()
    auth = _get_google_auth_info()
    user_profile = _get_customer_profile_dict(frappe.session.user)

    categories = frappe.db.sql(
        """
        SELECT i.item_group AS name, COUNT(*) AS item_count
        FROM `tabItem` i
        WHERE i.disabled = 0 AND i.is_sales_item = 1 AND COALESCE(i.item_group, '') != ''
        GROUP BY i.item_group
        ORDER BY item_count DESC, i.item_group ASC
        """,
        as_dict=True,
    )

    return {
        "user": user_profile,
        "auth": auth,
        "categories": categories,
        "payment_methods": build_payment_methods_catalog(cfg),
        "settings": {
            "company": cfg["company"],
            "warehouse": cfg["warehouse"],
            "price_list": cfg["price_list"],
            "currency": "USD",
            "iva_rate": cfg["iva_rate"],
            "igtf_rate": cfg["igtf_rate"],
            "simulation_mode": cfg["simulation_mode"],
            "default_image": DEFAULT_PRODUCT_IMAGE,
        },
    }


@whitelist(allow_guest=True)
def get_catalog(
    query: str = "",
    item_group: str = "",
    only_in_stock: int = 0,
    sort: str = "stock_desc",
    page: int = 1,
    page_size: int = 24,
) -> dict:
    """Lista productos con stock real en almacén, precios Detal USD e imagen fallback."""
    import frappe

    cfg = _get_storefront_config()
    page = max(int(page or 1), 1)
    page_size = min(max(int(page_size or 24), 1), 60)
    offset = (page - 1) * page_size

    conditions = ["i.disabled = 0", "i.is_sales_item = 1"]
    params: dict = {
        "warehouse": cfg["warehouse"],
        "price_list": cfg["price_list"],
        "limit": page_size,
        "offset": offset,
    }

    q = (query or "").strip()
    if q:
        conditions.append("(i.item_code LIKE %(q)s OR i.item_name LIKE %(q)s OR i.item_group LIKE %(q)s)")
        params["q"] = f"%{q}%"

    grp = (item_group or "").strip()
    if grp:
        conditions.append("i.item_group = %(item_group)s")
        params["item_group"] = grp

    having_clause = "HAVING stock_qty > 0" if int(only_in_stock or 0) == 1 else ""
    order_map = {
        "stock_desc": "stock_qty DESC, i.item_name ASC",
        "price_asc": "price ASC, stock_qty DESC",
        "price_desc": "price DESC, stock_qty DESC",
        "name_asc": "i.item_name ASC",
    }
    order_by = order_map.get(sort, "stock_qty DESC, i.item_name ASC")
    where_sql = " AND ".join(conditions)
    wh_filter = "AND b.warehouse = %(warehouse)s" if cfg["warehouse"] else ""

    rows = frappe.db.sql(
        f"""
        SELECT
            i.item_code,
            i.item_name,
            i.item_group,
            COALESCE(wi.web_long_description, i.description, '') AS description,
            COALESCE(NULLIF(wi.website_image, ''), NULLIF(i.image, ''), '') AS raw_image,
            COALESCE(SUM(b.actual_qty), 0) AS stock_qty,
            COALESCE(MAX(ip.price_list_rate), i.standard_rate, 0) AS price,
            COALESCE(MAX(ip.currency), 'USD') AS currency
        FROM `tabItem` i
        LEFT JOIN `tabWebsite Item` wi
            ON wi.item_code = i.item_code AND wi.published = 1
        LEFT JOIN `tabBin` b
            ON b.item_code = i.item_code {wh_filter}
        LEFT JOIN `tabItem Price` ip
            ON ip.item_code = i.item_code
            AND ip.selling = 1
            AND ip.price_list = %(price_list)s
        WHERE {where_sql}
        GROUP BY i.item_code, i.item_name, i.item_group, wi.web_long_description, i.description, wi.website_image, i.image, i.standard_rate
        {having_clause}
        ORDER BY {order_by}
        LIMIT %(limit)s OFFSET %(offset)s
        """,
        params,
        as_dict=True,
    )

    count_rows = frappe.db.sql(
        f"""
        SELECT COUNT(*) AS total FROM (
            SELECT i.item_code, COALESCE(SUM(b.actual_qty), 0) AS stock_qty
            FROM `tabItem` i
            LEFT JOIN `tabBin` b ON b.item_code = i.item_code {wh_filter}
            WHERE {where_sql}
            GROUP BY i.item_code
            {having_clause}
        ) sub
        """,
        params,
        as_dict=True,
    )
    total = int(count_rows[0]["total"]) if count_rows else 0

    pricing_rules = frappe.get_all(
        "Pricing Rule",
        filters={"selling": 1, "disable": 0},
        fields=["name", "title", "apply_on", "min_qty", "discount_percentage", "rate"],
        order_by="min_qty asc",
        limit=50,
    )

    for row in rows:
        row["image"] = row.pop("raw_image") or DEFAULT_PRODUCT_IMAGE
        row["stock_qty"] = float(row.get("stock_qty") or 0)
        row["price"] = float(row.get("price") or 0)
        row["has_volume_discount"] = bool(pricing_rules)

    return {
        "items": rows,
        "total": total,
        "page": page,
        "page_size": page_size,
        "default_image": DEFAULT_PRODUCT_IMAGE,
    }


@whitelist(allow_guest=True)
def preview_storefront_cart(items: str | list[dict], payment_method: str = "cashea") -> dict:
    """Calcula precios reales (con Pricing Rules), IVA e IGTF para el carrito de tienda."""
    import frappe

    parsed_items = json.loads(items) if isinstance(items, str) else items
    if not parsed_items:
        return {
            "items": [],
            "totals": calculate_storefront_totals([], payment_method=payment_method),
        }

    cfg = _get_storefront_config()
    priced_items: list[dict] = []

    try:
        from erpnext.stock.get_item_details import get_item_details

        for row in parsed_items:
            item_code = row.get("item_code")
            qty = float(row.get("qty") or 1)
            if not item_code or qty <= 0:
                continue
            details = get_item_details(
                {
                    "item_code": item_code,
                    "company": cfg["company"],
                    "selling_price_list": cfg["price_list"],
                    "price_list": cfg["price_list"],
                    "currency": "USD",
                    "qty": qty,
                    "warehouse": cfg["warehouse"],
                    "doctype": "Sales Order",
                    "conversion_rate": 1.0,
                    "plc_conversion_rate": 1.0,
                }
            )
            base_rate = float(details.get("price_list_rate") or row.get("price") or 0)
            net_rate = float(details.get("rate") or base_rate)
            discount_pct = float(details.get("discount_percentage") or 0)
            priced_items.append(
                {
                    "item_code": item_code,
                    "item_name": row.get("item_name") or details.get("item_name") or item_code,
                    "qty": qty,
                    "price_list_rate": base_rate,
                    "rate": net_rate,
                    "discount_percentage": discount_pct,
                    "amount": round(net_rate * qty, 2),
                }
            )
    except Exception:
        for row in parsed_items:
            qty = float(row.get("qty") or 1)
            rate = float(row.get("price") or row.get("rate") or 0)
            priced_items.append(
                {
                    "item_code": row.get("item_code"),
                    "item_name": row.get("item_name") or row.get("item_code"),
                    "qty": qty,
                    "price_list_rate": rate,
                    "rate": rate,
                    "discount_percentage": 0.0,
                    "amount": round(rate * qty, 2),
                }
            )

    totals = calculate_storefront_totals(
        priced_items,
        payment_method=payment_method,
        iva_rate=cfg["iva_rate"],
        igtf_rate=cfg["igtf_rate"],
    )
    return {"items": priced_items, "totals": totals}


@whitelist(allow_guest=True)
def register_customer(
    email: str,
    full_name: str,
    password: str,
    ve_rif_cedula: str = "",
    ve_taxpayer_type: str = "No Contribuyente",
    phone: str = "",
    address: str = "",
) -> dict:
    """Registra un nuevo usuario web + Customer (con RIF/datos fiscales opcionales) e inicia sesión."""
    import frappe

    data = validate_registration_payload(
        email=email,
        full_name=full_name,
        password=password,
        ve_rif_cedula=ve_rif_cedula,
        ve_taxpayer_type=ve_taxpayer_type,
    )

    if frappe.db.exists("User", data["email"]):
        frappe.throw("Ya existe una cuenta registrada con este correo. Inicia sesión o usa Google.")

    user = frappe.get_doc(
        {
            "doctype": "User",
            "email": data["email"],
            "first_name": data["full_name"],
            "enabled": 1,
            "user_type": "Website User",
            "send_welcome_email": 0,
            "new_password": data["password"],
        }
    )
    user.append("roles", {"role": "Customer"})
    user.insert(ignore_permissions=True)

    _ensure_customer_for_user(
        user_email=data["email"],
        full_name=data["full_name"],
        ve_rif_cedula=data["ve_rif_cedula"],
        ve_taxpayer_type=data["ve_taxpayer_type"],
        phone=phone,
        address=address,
    )

    frappe.local.login_manager.login_as(data["email"])
    return {"ok": True, "user": _get_customer_profile_dict(data["email"])}


@whitelist()
def get_my_profile_and_orders() -> dict:
    """Devuelve perfil fiscal y pedidos/facturas del cliente autenticado."""
    import frappe

    profile = _get_customer_profile_dict(frappe.session.user)
    customer_name = profile.get("customer_name")
    if not customer_name:
        return {"profile": profile, "orders": [], "invoices": []}

    orders = frappe.get_all(
        "Sales Order",
        filters={"customer": customer_name, "docstatus": ["<", 2]},
        fields=["name", "transaction_date", "grand_total", "currency", "status", "per_billed", "po_no"],
        order_by="creation desc",
        limit=25,
    )
    invoices = frappe.get_all(
        "Sales Invoice",
        filters={"customer": customer_name, "docstatus": 1},
        fields=[
            "name",
            "posting_date",
            "grand_total",
            "status",
            "ve_numero_control",
            "ve_numero_factura_fiscal",
            "ve_fiscal_status",
            "ve_fiscal_pdf_url",
            "cashea_status",
        ],
        order_by="creation desc",
        limit=25,
    )
    return {"profile": profile, "orders": orders, "invoices": invoices}


@whitelist()
def update_my_fiscal_profile(
    full_name: str = "",
    ve_rif_cedula: str = "",
    ve_taxpayer_type: str = "No Contribuyente",
    phone: str = "",
    address: str = "",
) -> dict:
    """Actualiza datos fiscales (RIF/Cédula opcional, contribuyente, teléfono, dirección)."""
    import frappe

    user_email = frappe.session.user
    if not user_email or user_email == "Guest":
        frappe.throw("Debes iniciar sesión para actualizar tu perfil.")

    customer_name = _ensure_customer_for_user(user_email, full_name=full_name)
    norm_rif = normalize_rif_or_cedula(ve_rif_cedula)

    updates: dict = {
        "ve_rif_cedula": norm_rif,
        "tax_id": norm_rif,
        "ve_taxpayer_type": ve_taxpayer_type or "No Contribuyente",
    }
    if full_name.strip():
        updates["customer_name"] = full_name.strip()
        frappe.db.set_value("User", user_email, "first_name", full_name.strip())
    if phone.strip():
        updates["mobile_no"] = phone.strip()

    frappe.db.set_value("Customer", customer_name, updates)
    if address.strip():
        _upsert_customer_address(customer_name, full_name or customer_name, address, phone, user_email)

    frappe.db.commit()
    return {"ok": True, "profile": _get_customer_profile_dict(user_email)}


@whitelist(allow_guest=True)
def place_storefront_order(
    items: str | list[dict],
    payment_method: str = "cashea",
    payment_details: str | dict | None = None,
    customer_info: str | dict | None = None,
) -> dict:
    """Crea el pedido (Sales Order) en ERPNext y procesa Cashea / Google Pay / métodos manuales."""
    import frappe
    from frappe.utils import add_days, today

    parsed_items = json.loads(items) if isinstance(items, str) else items
    if not parsed_items:
        frappe.throw("Tu carrito está vacío.")

    pay_details = json.loads(payment_details) if isinstance(payment_details, str) else (payment_details or {})
    cust_info = json.loads(customer_info) if isinstance(customer_info, str) else (customer_info or {})

    cfg = _get_storefront_config()
    user_email = frappe.session.user

    if user_email == "Guest":
        guest_email = (cust_info.get("email") or "").strip().lower()
        guest_name = (cust_info.get("full_name") or "").strip()
        if not guest_email or not guest_name:
            frappe.throw("Inicia sesión o ingresa tu nombre y correo para completar el pedido.")
        if cust_info.get("password"):
            register_customer(
                email=guest_email,
                full_name=guest_name,
                password=cust_info.get("password"),
                ve_rif_cedula=cust_info.get("ve_rif_cedula", ""),
                ve_taxpayer_type=cust_info.get("ve_taxpayer_type", "No Contribuyente"),
                phone=cust_info.get("phone", ""),
                address=cust_info.get("address", ""),
            )
            customer_name = _ensure_customer_for_user(guest_email)
        else:
            customer_name = _ensure_customer_for_user(
                user_email=guest_email,
                full_name=guest_name,
                ve_rif_cedula=cust_info.get("ve_rif_cedula", ""),
                ve_taxpayer_type=cust_info.get("ve_taxpayer_type", "No Contribuyente"),
                phone=cust_info.get("phone", ""),
                address=cust_info.get("address", ""),
            )
    else:
        customer_name = _ensure_customer_for_user(
            user_email=user_email,
            full_name=cust_info.get("full_name", ""),
            ve_rif_cedula=cust_info.get("ve_rif_cedula", ""),
            ve_taxpayer_type=cust_info.get("ve_taxpayer_type", "No Contribuyente"),
            phone=cust_info.get("phone", ""),
            address=cust_info.get("address", ""),
        )

    so = frappe.new_doc("Sales Order")
    so.customer = customer_name
    so.company = cfg["company"]
    so.order_type = "Shopping Cart"
    so.transaction_date = today()
    so.delivery_date = add_days(today(), 1)
    so.selling_price_list = cfg["price_list"]
    so.currency = "USD"
    if cfg["warehouse"]:
        so.set_warehouse = cfg["warehouse"]

    ref_code = (pay_details.get("reference") or "").strip()
    so.po_no = f"{payment_method.upper()}{': ' + ref_code if ref_code else ''}"[:140]

    for row in parsed_items:
        qty = float(row.get("qty") or 0)
        if qty <= 0:
            continue
        so.append(
            "items",
            {
                "item_code": row.get("item_code"),
                "qty": qty,
                "warehouse": cfg["warehouse"],
            },
        )

    if not so.items:
        frappe.throw("No hay productos válidos en el pedido.")

    so.insert(ignore_permissions=True)
    so.submit()

    note_parts = [f"Método de pago web: {payment_method}"]
    if ref_code:
        note_parts.append(f"Referencia: {ref_code}")
    if pay_details.get("bank"):
        note_parts.append(f"Banco/Emisor: {pay_details.get('bank')}")
    if pay_details.get("phone"):
        note_parts.append(f"Teléfono: {pay_details.get('phone')}")
    if pay_details.get("token_summary"):
        note_parts.append(f"Token navegador: {pay_details.get('token_summary')}")
    so.add_comment("Comment", " | ".join(note_parts))

    result: dict = {
        "ok": True,
        "sales_order": so.name,
        "grand_total": float(so.grand_total or 0),
        "payment_method": payment_method,
        "status": "Pedido registrado",
    }

    if payment_method in {"cashea", "google_pay"}:
        try:
            from erpnext.selling.doctype.sales_order.sales_order import make_sales_invoice

            si = make_sales_invoice(so.name, ignore_permissions=True)
            si.insert(ignore_permissions=True)
            si.submit()
            result["sales_invoice"] = si.name

            if payment_method == "cashea":
                from cima_ve.api.cashea import create_cashea_checkout

                cashea_resp = create_cashea_checkout(si.name)
                result["cashea"] = cashea_resp
                result["status"] = "Pendiente de pago en Cashea"
            elif payment_method == "google_pay":
                si.add_comment("Comment", f"Pago Google Pay / Tarjeta tokenizado: {pay_details.get('token_summary') or 'Simulación'}")
                result["status"] = "Pago autorizado (Google Pay)"
        except Exception as exc:
            result["invoice_warning"] = str(exc)

    frappe.db.commit()
    return result
