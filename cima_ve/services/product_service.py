from __future__ import annotations

import re
import unicodedata


def normalize_item_code(item_code: str | None, item_name: str | None) -> str:
    """Normaliza un código SKU o genera uno limpio a partir del nombre del producto."""
    raw_code = str(item_code or "").strip()
    if raw_code:
        cleaned = re.sub(r"\s+", "-", raw_code.upper())
        return cleaned[:60]

    raw_name = str(item_name or "").strip()
    if not raw_name:
        return ""
    ascii_name = (
        unicodedata.normalize("NFKD", raw_name)
        .encode("ascii", "ignore")
        .decode("ascii")
    )
    slug = re.sub(r"[^A-Za-z0-9]+", "-", ascii_name.upper()).strip("-")
    return slug[:40]


def _to_non_negative_float(value: object, field_label: str) -> float:
    if value in (None, ""):
        return 0.0
    try:
        num = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field_label} debe ser un número válido.") from exc
    if num < 0:
        raise ValueError(f"{field_label} no puede ser negativo.")
    return round(num, 4)


def validate_new_product_input(payload: dict) -> dict:
    """Valida y normaliza los datos para crear un producto nuevo de forma simplificada."""
    if not isinstance(payload, dict):
        raise ValueError("Datos de producto inválidos.")

    item_name = str(payload.get("item_name") or "").strip()
    if not item_name:
        raise ValueError("El nombre del producto es obligatorio.")

    item_code = normalize_item_code(payload.get("item_code"), item_name)
    if not item_code:
        raise ValueError("No se pudo determinar un código SKU válido para el producto.")

    item_group = str(payload.get("item_group") or "Products").strip() or "Products"
    stock_uom = str(payload.get("stock_uom") or "Nos").strip() or "Nos"
    description = str(payload.get("description") or "").strip() or item_name
    warehouse = str(payload.get("warehouse") or "").strip()

    cost_rate = _to_non_negative_float(payload.get("cost_rate"), "El costo unitario")
    detal_price = _to_non_negative_float(payload.get("detal_price"), "El precio Detal")
    mayor_price = _to_non_negative_float(payload.get("mayor_price"), "El precio Mayor")
    initial_qty = _to_non_negative_float(payload.get("initial_qty"), "La cantidad inicial")

    if initial_qty > 0 and not warehouse:
        raise ValueError("Selecciona un almacén para registrar la cantidad inicial.")

    show_in_website = payload.get("show_in_website")
    if isinstance(show_in_website, str):
        show_in_website_flag = show_in_website.strip().lower() in {"1", "true", "yes", "si", "sí"}
    elif show_in_website is None:
        show_in_website_flag = True
    else:
        show_in_website_flag = bool(int(show_in_website)) if isinstance(show_in_website, (int, float)) else bool(show_in_website)

    return {
        "item_code": item_code,
        "item_name": item_name,
        "item_group": item_group,
        "stock_uom": stock_uom,
        "description": description,
        "cost_rate": round(cost_rate, 2),
        "detal_price": round(detal_price, 2),
        "mayor_price": round(mayor_price, 2),
        "initial_qty": initial_qty,
        "warehouse": warehouse,
        "show_in_website": show_in_website_flag,
    }


def validate_stock_batch_input(items: list[dict] | None, warehouse: str | None) -> list[dict]:
    """Valida las filas de un lote de entrada de inventario para productos existentes."""
    clean_warehouse = str(warehouse or "").strip()
    if not clean_warehouse:
        raise ValueError("Debes seleccionar un almacén destino para el lote.")
    if not items or not isinstance(items, list):
        raise ValueError("Agrega al menos un producto al lote.")

    normalized: list[dict] = []
    for idx, row in enumerate(items, start=1):
        if not isinstance(row, dict):
            continue
        item_code = str(row.get("item_code") or "").strip()
        if not item_code:
            raise ValueError(f"Fila #{idx}: falta el código del producto.")
        qty = _to_non_negative_float(row.get("qty"), f"Cantidad en fila #{idx}")
        if qty <= 0:
            raise ValueError(f"Producto {item_code}: la cantidad debe ser mayor a 0.")
        incoming_rate = round(
            _to_non_negative_float(row.get("incoming_rate"), f"Costo unitario de {item_code}"),
            2,
        )
        detal_price = (
            round(_to_non_negative_float(row.get("detal_price"), f"Precio Detal de {item_code}"), 2)
            if row.get("detal_price") not in (None, "")
            else None
        )
        mayor_price = (
            round(_to_non_negative_float(row.get("mayor_price"), f"Precio Mayor de {item_code}"), 2)
            if row.get("mayor_price") not in (None, "")
            else None
        )
        batch_no = str(row.get("batch_no") or "").strip()
        expiry_date = str(row.get("expiry_date") or "").strip()

        normalized.append(
            {
                "item_code": item_code,
                "qty": qty,
                "incoming_rate": incoming_rate,
                "detal_price": detal_price,
                "mayor_price": mayor_price,
                "batch_no": batch_no,
                "expiry_date": expiry_date,
            }
        )

    if not normalized:
        raise ValueError("Agrega al menos un producto válido al lote.")
    return normalized
