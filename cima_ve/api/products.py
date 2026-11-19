from __future__ import annotations

import base64
import json
import os

from cima_ve.api._compat import whitelist
from cima_ve.services.product_service import (
    validate_new_product_input,
    validate_stock_batch_input,
)

ALLOWED_PRODUCT_ROLES = ("System Manager", "Stock Manager", "Stock User", "Sales Manager")
ALLOWED_IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".gif"}


def _require_product_manager() -> None:
    import frappe

    current_user = frappe.session.user
    if not current_user or current_user == "Guest":
        frappe.throw("Debes iniciar sesión para gestionar productos e inventario.", frappe.PermissionError)
    frappe.only_for(ALLOWED_PRODUCT_ROLES)


def _resolve_price_lists() -> tuple[str, str]:
    import frappe

    price_lists = frappe.get_all(
        "Price List",
        filters={"selling": 1, "enabled": 1},
        pluck="name",
        order_by="name asc",
        limit_page_length=50,
    )
    detal_pl = next((pl for pl in price_lists if "detal" in pl.lower()), price_lists[0] if price_lists else "")
    mayor_pl = next((pl for pl in price_lists if "mayor" in pl.lower()), "")
    return detal_pl, mayor_pl


def _upsert_item_price(item_code: str, price_list: str, rate: float, currency: str = "USD") -> None:
    import frappe

    if not price_list or rate <= 0:
        return
    existing = frappe.db.get_value(
        "Item Price",
        {"item_code": item_code, "price_list": price_list, "selling": 1},
        "name",
    )
    if existing:
        frappe.db.set_value("Item Price", existing, "price_list_rate", round(float(rate), 2))
        return

    ip = frappe.get_doc(
        {
            "doctype": "Item Price",
            "item_code": item_code,
            "price_list": price_list,
            "selling": 1,
            "currency": currency or "USD",
            "price_list_rate": round(float(rate), 2),
        }
    )
    ip.flags.ignore_permissions = True
    ip.insert(ignore_permissions=True)


def _save_public_item_image(item_code: str, file_name: str, file_data_base64: str) -> str:
    import frappe

    clean_name = os.path.basename((file_name or "producto.png").strip()) or "producto.png"
    ext = os.path.splitext(clean_name)[1].lower()
    if ext not in ALLOWED_IMAGE_EXTS:
        frappe.throw("Formato de imagen no soportado. Usa PNG, JPG, WEBP o GIF.")

    raw_b64 = (file_data_base64 or "").strip()
    if "," in raw_b64 and raw_b64.startswith("data:"):
        raw_b64 = raw_b64.split(",", 1)[1]
    if not raw_b64:
        return ""

    try:
        content = base64.b64decode(raw_b64)
    except Exception:
        frappe.throw("No se pudo decodificar la imagen del producto.")

    if len(content) > 5 * 1024 * 1024:
        frappe.throw("La imagen supera el tamaño máximo permitido de 5 MB.")

    file_doc = frappe.get_doc(
        {
            "doctype": "File",
            "file_name": clean_name,
            "attached_to_doctype": "Item",
            "attached_to_name": item_code,
            "is_private": 0,
            "content": content,
        }
    )
    file_doc.flags.ignore_permissions = True
    file_doc.insert(ignore_permissions=True)

    item_meta = frappe.get_meta("Item")
    if item_meta.has_field("website_image"):
        frappe.db.set_value("Item", item_code, "website_image", file_doc.file_url)
    if item_meta.has_field("image"):
        frappe.db.set_value("Item", item_code, "image", file_doc.file_url)
    if frappe.db.table_exists("Website Item"):
        wi_name = frappe.db.get_value("Website Item", {"item_code": item_code}, "name")
        if wi_name:
            frappe.db.set_value("Website Item", wi_name, "website_image", file_doc.file_url)
    return file_doc.file_url


def _create_material_receipt(
    company: str,
    warehouse: str,
    rows: list[dict],
    remarks: str = "",
    posting_date: str = "",
) -> str:
    import frappe
    from frappe.utils import today

    se_items = []
    for r in rows:
        rate = float(r.get("incoming_rate") or 0.0)
        row_dict: dict = {
            "item_code": r["item_code"],
            "qty": float(r["qty"]),
            "t_warehouse": warehouse,
            "basic_rate": rate,
            "allow_zero_valuation_rate": 1 if rate <= 0 else 0,
        }
        if r.get("batch_no"):
            has_batch = frappe.db.get_value("Item", r["item_code"], "has_batch_no")
            if has_batch:
                batch_name = r["batch_no"]
                if not frappe.db.exists("Batch", batch_name):
                    batch_doc = frappe.get_doc(
                        {
                            "doctype": "Batch",
                            "batch_id": batch_name,
                            "item": r["item_code"],
                            "expiry_date": r.get("expiry_date") or None,
                        }
                    )
                    batch_doc.flags.ignore_permissions = True
                    batch_doc.insert(ignore_permissions=True)
                    batch_name = batch_doc.name
                row_dict["batch_no"] = batch_name
        se_items.append(row_dict)

    se = frappe.get_doc(
        {
            "doctype": "Stock Entry",
            "stock_entry_type": "Material Receipt",
            "purpose": "Material Receipt",
            "company": company,
            "posting_date": posting_date or today(),
            "to_warehouse": warehouse,
            "remarks": remarks or "Carga rápida desde Carga de Productos y Lotes",
            "items": se_items,
        }
    )
    se.flags.ignore_permissions = True
    se.insert(ignore_permissions=True)
    se.submit()
    return se.name


@whitelist()
def get_product_loader_bootstrap() -> dict:
    """Devuelve almacenes, categorías, unidades y listas de precios para Carga de Productos."""
    import frappe

    _require_product_manager()

    companies = frappe.get_all("Company", pluck="name", order_by="creation asc", limit_page_length=5)
    default_company = companies[0] if companies else ""

    warehouses = frappe.get_all(
        "Warehouse",
        filters={"is_group": 0, "disabled": 0},
        fields=["name", "warehouse_name", "company"],
        order_by="name asc",
        limit_page_length=50,
    )

    preferred_wh = ""
    try:
        settings = frappe.get_single("Cima VE Settings")
        if settings.meta.has_field("storefront_warehouse") and settings.storefront_warehouse:
            preferred_wh = settings.storefront_warehouse
    except Exception:
        pass
    if not preferred_wh and warehouses:
        preferred_wh = next(
            (w["name"] for w in warehouses if "white point" in w["name"].lower()),
            warehouses[0]["name"],
        )

    item_groups = frappe.get_all(
        "Item Group",
        filters={"is_group": 0},
        pluck="name",
        order_by="name asc",
        limit_page_length=100,
    )
    if not item_groups:
        item_groups = frappe.get_all("Item Group", pluck="name", order_by="name asc", limit_page_length=100)

    uoms = frappe.get_all(
        "UOM",
        filters={"enabled": 1},
        pluck="name",
        order_by="name asc",
        limit_page_length=50,
    ) or ["Nos", "Unit"]

    detal_pl, mayor_pl = _resolve_price_lists()
    exchange_rate = {"bcv_rate": 0.0, "adjusted_rate": 0.0}
    try:
        from cima_ve.api.exchange_rates import get_current_exchange_rates

        exchange_rate = get_current_exchange_rates()
    except Exception:
        pass

    return {
        "company": default_company,
        "warehouses": warehouses,
        "default_warehouse": preferred_wh,
        "item_groups": item_groups,
        "default_item_group": next((g for g in item_groups if "product" in g.lower()), item_groups[0] if item_groups else "Products"),
        "uoms": uoms,
        "default_uom": next((u for u in uoms if u in ("Nos", "Unidad", "Unit")), uoms[0]),
        "detal_price_list": detal_pl,
        "mayor_price_list": mayor_pl,
        "exchange_rate": exchange_rate,
    }


@whitelist()
def search_products_for_batch(query: str = "", warehouse: str = "", limit: int = 60) -> list[dict]:
    """Busca productos existentes con su stock, costo y precios Detal/Mayor."""
    import frappe

    _require_product_manager()

    limit = min(max(int(limit or 60), 1), 200)
    detal_pl, mayor_pl = _resolve_price_lists()
    search_like = f"%{(query or '').strip()}%"
    conditions = ["i.disabled = 0"]
    params: dict = {
        "search": search_like,
        "warehouse": warehouse or "",
        "detal_pl": detal_pl or "",
        "mayor_pl": mayor_pl or "",
        "limit": limit,
    }
    if (query or "").strip():
        conditions.append("(i.item_code LIKE %(search)s OR i.item_name LIKE %(search)s OR i.item_group LIKE %(search)s)")

    wh_filter = "AND b.warehouse = %(warehouse)s" if warehouse else ""
    where_clause = " AND ".join(conditions)

    has_website_item = bool(frappe.db.table_exists("Website Item"))
    item_meta = frappe.get_meta("Item")
    has_item_website_image = bool(item_meta.has_field("website_image"))

    if has_website_item:
        website_item_join = "LEFT JOIN `tabWebsite Item` wi ON wi.item_code = i.item_code"
        image_select = "COALESCE(NULLIF(MAX(wi.website_image), ''), NULLIF(i.image, ''), '') AS website_image"
        extra_group_by = ""
    elif has_item_website_image:
        website_item_join = ""
        image_select = "COALESCE(NULLIF(i.website_image, ''), NULLIF(i.image, ''), '') AS website_image"
        extra_group_by = ", i.website_image"
    else:
        website_item_join = ""
        image_select = "COALESCE(NULLIF(i.image, ''), '') AS website_image"
        extra_group_by = ""

    rows = frappe.db.sql(
        f"""
        SELECT
            i.item_code,
            i.item_name,
            i.item_group,
            i.stock_uom,
            COALESCE(i.valuation_rate, 0) AS valuation_rate,
            COALESCE(i.last_purchase_rate, 0) AS last_purchase_rate,
            COALESCE(i.standard_rate, 0) AS standard_rate,
            {image_select},
            COALESCE(i.has_batch_no, 0) AS has_batch_no,
            COALESCE(SUM(b.actual_qty), 0) AS stock_qty,
            COALESCE(MAX(ip_detal.price_list_rate), i.standard_rate, 0) AS detal_price,
            COALESCE(MAX(ip_mayor.price_list_rate), 0) AS mayor_price
        FROM `tabItem` i
        {website_item_join}
        LEFT JOIN `tabBin` b
            ON b.item_code = i.item_code {wh_filter}
        LEFT JOIN `tabItem Price` ip_detal
            ON ip_detal.item_code = i.item_code AND ip_detal.selling = 1 AND ip_detal.price_list = %(detal_pl)s
        LEFT JOIN `tabItem Price` ip_mayor
            ON ip_mayor.item_code = i.item_code AND ip_mayor.selling = 1 AND ip_mayor.price_list = %(mayor_pl)s
        WHERE {where_clause}
        GROUP BY
            i.item_code, i.item_name, i.item_group, i.stock_uom,
            i.valuation_rate, i.last_purchase_rate, i.standard_rate,
            i.image, i.has_batch_no{extra_group_by}
        ORDER BY i.modified DESC
        LIMIT %(limit)s
        """,
        params,
        as_dict=True,
    )
    return rows


def _validate_product_creation(payload: dict) -> dict:
    import frappe

    try:
        cleaned = validate_new_product_input(payload)
    except ValueError as exc:
        frappe.throw(str(exc))
    if frappe.db.exists("Item", cleaned["item_code"]):
        frappe.throw(
            f"El producto con código {cleaned['item_code']} ya existe. Usa la pestaña 'Agregar Lote' para sumarle inventario."
        )
    return cleaned


@whitelist(methods=["POST"])
def preview_quick_product(product: str) -> dict:
    """Devuelve los valores normalizados para revisión sin crear registros."""
    import frappe

    _require_product_manager()
    try:
        payload = json.loads(product)
    except (TypeError, ValueError):
        frappe.throw("Datos de producto inválidos.")
    return _validate_product_creation(payload)


@whitelist(methods=["POST"])
def create_quick_product(
    item_name: str,
    item_code: str = "",
    item_group: str = "Products",
    stock_uom: str = "Nos",
    cost_rate: float | str = 0.0,
    detal_price: float | str = 0.0,
    mayor_price: float | str = 0.0,
    initial_qty: float | str = 0.0,
    warehouse: str = "",
    description: str = "",
    show_in_website: int | bool = 1,
    image_file_name: str = "",
    image_data_base64: str = "",
) -> dict:
    """Crea un producto nuevo con precios Detal/Mayor, imagen opcional y entrada inicial de inventario."""
    import frappe

    _require_product_manager()

    cleaned = _validate_product_creation({
        "item_code": item_code,
        "item_name": item_name,
        "item_group": item_group,
        "stock_uom": stock_uom,
        "cost_rate": cost_rate,
        "detal_price": detal_price,
        "mayor_price": mayor_price,
        "initial_qty": initial_qty,
        "warehouse": warehouse,
        "description": description,
        "show_in_website": show_in_website,
    })

    item_dict: dict = {
        "doctype": "Item",
        "item_code": cleaned["item_code"],
        "item_name": cleaned["item_name"],
        "item_group": cleaned["item_group"],
        "stock_uom": cleaned["stock_uom"],
        "description": cleaned["description"],
        "is_stock_item": 1,
        "is_sales_item": 1,
        "valuation_rate": cleaned["cost_rate"],
        "standard_rate": cleaned["detal_price"] or cleaned["cost_rate"],
    }
    item_meta = frappe.get_meta("Item")
    if item_meta.has_field("show_in_website"):
        item_dict["show_in_website"] = 1 if cleaned["show_in_website"] else 0

    item_doc = frappe.get_doc(item_dict)
    item_doc.flags.ignore_permissions = True
    item_doc.insert(ignore_permissions=True)

    detal_pl, mayor_pl = _resolve_price_lists()
    if cleaned["detal_price"] > 0 and detal_pl:
        _upsert_item_price(item_doc.name, detal_pl, cleaned["detal_price"])
    if cleaned["mayor_price"] > 0 and mayor_pl:
        _upsert_item_price(item_doc.name, mayor_pl, cleaned["mayor_price"])

    image_url = ""
    if image_data_base64 and image_file_name:
        image_url = _save_public_item_image(item_doc.name, image_file_name, image_data_base64)

    stock_entry_name = ""
    if cleaned["initial_qty"] > 0 and cleaned["warehouse"]:
        company = frappe.db.get_value("Warehouse", cleaned["warehouse"], "company") or (
            frappe.get_all("Company", pluck="name", limit=1) or [""]
        )[0]
        stock_entry_name = _create_material_receipt(
            company=company,
            warehouse=cleaned["warehouse"],
            rows=[
                {
                    "item_code": item_doc.name,
                    "qty": cleaned["initial_qty"],
                    "incoming_rate": cleaned["cost_rate"],
                }
            ],
            remarks=f"Inventario inicial de {item_doc.item_name} ({item_doc.name})",
        )

    return {
        "ok": True,
        "item_code": item_doc.name,
        "item_name": item_doc.item_name,
        "stock_entry": stock_entry_name,
        "image_url": image_url,
    }


@whitelist()
def add_stock_batch(
    items: str | list[dict],
    warehouse: str,
    reference: str = "",
    posting_date: str = "",
) -> dict:
    """Registra una entrada de inventario por lote (Stock Entry Material Receipt) y actualiza precios opcionales."""
    import frappe

    _require_product_manager()

    parsed = json.loads(items) if isinstance(items, str) else items
    try:
        rows = validate_stock_batch_input(parsed, warehouse)
    except ValueError as exc:
        frappe.throw(str(exc))

    company = frappe.db.get_value("Warehouse", warehouse, "company") or (
        frappe.get_all("Company", pluck="name", limit=1) or [""]
    )[0]
    remarks = (reference or "").strip() or f"Lote de entrada en {warehouse}"

    se_name = _create_material_receipt(
        company=company,
        warehouse=warehouse,
        rows=rows,
        remarks=remarks,
        posting_date=posting_date,
    )

    detal_pl, mayor_pl = _resolve_price_lists()
    for r in rows:
        if r.get("detal_price") is not None and r["detal_price"] > 0 and detal_pl:
            _upsert_item_price(r["item_code"], detal_pl, r["detal_price"])
            frappe.db.set_value("Item", r["item_code"], "standard_rate", r["detal_price"])
        if r.get("mayor_price") is not None and r["mayor_price"] > 0 and mayor_pl:
            _upsert_item_price(r["item_code"], mayor_pl, r["mayor_price"])

    total_qty = round(sum(float(r["qty"]) for r in rows), 2)
    total_cost = round(sum(float(r["qty"]) * float(r["incoming_rate"]) for r in rows), 2)
    return {
        "ok": True,
        "stock_entry": se_name,
        "items_count": len(rows),
        "total_qty": total_qty,
        "total_cost": total_cost,
    }


@whitelist()
def update_product_quick_details(
    item_code: str,
    detal_price: float | str | None = None,
    mayor_price: float | str | None = None,
    cost_rate: float | str | None = None,
    image_file_name: str = "",
    image_data_base64: str = "",
) -> dict:
    """Actualiza rápidamente precios, costo e imagen de un producto existente."""
    import frappe

    _require_product_manager()

    code = (item_code or "").strip()
    if not code or not frappe.db.exists("Item", code):
        frappe.throw("El producto indicado no existe.")

    detal_pl, mayor_pl = _resolve_price_lists()
    if detal_price not in (None, ""):
        val = max(float(detal_price), 0.0)
        if val > 0 and detal_pl:
            _upsert_item_price(code, detal_pl, val)
            frappe.db.set_value("Item", code, "standard_rate", round(val, 2))
    if mayor_price not in (None, ""):
        val = max(float(mayor_price), 0.0)
        if val > 0 and mayor_pl:
            _upsert_item_price(code, mayor_pl, val)
    if cost_rate not in (None, ""):
        val = max(float(cost_rate), 0.0)
        frappe.db.set_value("Item", code, "valuation_rate", round(val, 2))

    image_url = ""
    if image_data_base64 and image_file_name:
        image_url = _save_public_item_image(code, image_file_name, image_data_base64)

    return {"ok": True, "item_code": code, "image_url": image_url}
