from __future__ import annotations

from dataclasses import asdict, dataclass

from cima_ve.services.fiscal_printer import (
    FiscalInvoiceItem,
    FiscalTaxBreakdown,
    calculate_venezuela_taxes,
)


@dataclass(slots=True)
class SellerInventoryItem:
    item_code: str
    item_name: str
    item_group: str
    warehouse: str
    stock_qty: float
    price: float
    currency: str
    price_list: str

    def to_dict(self) -> dict:
        return asdict(self)


def filter_inventory_items(
    items: list[dict],
    query: str = "",
    item_group: str = "",
    only_in_stock: bool = False,
) -> list[dict]:
    """Filtra ítems de inventario por código, nombre o grupo."""
    q = (query or "").strip().lower()
    group_filter = (item_group or "").strip().lower()

    results: list[dict] = []
    for item in items:
        code = str(item.get("item_code", "")).lower()
        name = str(item.get("item_name", "")).lower()
        group = str(item.get("item_group", "")).lower()
        stock = float(item.get("stock_qty", 0) or 0)

        if only_in_stock and stock <= 0:
            continue
        if group_filter and group != group_filter:
            continue
        if q and (q not in code and q not in name and q not in group):
            continue
        results.append(item)

    return results


def validate_quick_invoice_input(customer: str, items: list[dict]) -> list[FiscalInvoiceItem]:
    """Valida cliente e ítems antes de crear una factura rápida."""
    if not (customer or "").strip():
        raise ValueError("Debe seleccionar un cliente para iniciar la facturación.")
    if not items:
        raise ValueError("Debe agregar al menos un producto a la factura.")

    parsed: list[FiscalInvoiceItem] = []
    for idx, row in enumerate(items, start=1):
        item_code = str(row.get("item_code") or "").strip()
        if not item_code:
            raise ValueError(f"La línea {idx} no tiene código de producto válido.")
        qty = float(row.get("qty") or 0)
        if qty <= 0:
            raise ValueError(f"La cantidad para '{item_code}' debe ser mayor a 0.")
        rate = float(row.get("rate") if row.get("rate") is not None else row.get("price") or 0)
        if rate < 0:
            raise ValueError(f"El precio para '{item_code}' no puede ser negativo.")

        parsed.append(
            FiscalInvoiceItem(
                item_code=item_code,
                description=str(row.get("item_name") or row.get("description") or item_code),
                qty=qty,
                unit_price=rate,
                is_exempt=bool(row.get("is_exempt", False)),
            )
        )
    return parsed


def compute_custom_price_breakdown(list_rate: float, custom_rate: float) -> dict:
    """Calcula descuento si el precio personalizado es menor al precio original de lista."""
    orig = round(max(float(list_rate or 0.0), 0.0), 4)
    rate = round(max(float(custom_rate or 0.0), 0.0), 4)
    if orig > 0 and rate < orig - 0.0001:
        disc_amt = round(orig - rate, 4)
        disc_pct = round((disc_amt / orig) * 100.0, 2)
        return {
            "price_list_rate": orig,
            "rate": rate,
            "discount_amount": disc_amt,
            "discount_percentage": disc_pct,
            "has_discount": True,
            "price_changed": True,
        }
    return {
        "price_list_rate": orig,
        "rate": rate,
        "discount_amount": 0.0,
        "discount_percentage": 0.0,
        "has_discount": False,
        "price_changed": orig > 0 and abs(rate - orig) > 0.0001,
    }


def build_seller_invoice_summary(
    items: list[dict],
    apply_igtf: bool = False,
    iva_rate: float = 16.0,
    igtf_rate: float = 3.0,
) -> FiscalTaxBreakdown:
    """Calcula el desglose fiscal (Base, IVA 16%, IGTF 3%, Total) para el vendedor."""
    fiscal_items = validate_quick_invoice_input("PREVIEW", items)
    return calculate_venezuela_taxes(
        items=fiscal_items,
        apply_igtf=apply_igtf,
        iva_rate=iva_rate,
        igtf_rate=igtf_rate,
    )
