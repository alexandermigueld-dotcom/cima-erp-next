from __future__ import annotations

from cima_ve.api._compat import whitelist
from cima_ve.services.bills_service import (
    VALID_BILL_GROUPS,
    summarize_bills,
    validate_bill_category_input,
    validate_bill_input,
)


@whitelist()
def get_bill_categories() -> dict:
    """Lista las categorías (tipos de gasto) y grupos disponibles."""
    import frappe

    categories = frappe.get_all(
        "Cima Bill Category",
        filters={"is_active": 1},
        fields=["name", "category_name", "parent_group", "default_account", "description"],
        order_by="parent_group asc, category_name asc",
        limit_page_length=200,
    )
    return {
        "groups": list(VALID_BILL_GROUPS),
        "categories": categories,
    }


@whitelist()
def create_bill_category(
    category_name: str,
    parent_group: str = "Operativos",
    description: str = "",
    default_account: str = "",
) -> dict:
    """Crea un nuevo tipo de gasto (similar a crear un ítem de inventario)."""
    import frappe

    data = validate_bill_category_input(
        category_name=category_name,
        parent_group=parent_group,
        description=description,
        default_account=default_account,
    )
    if frappe.db.exists("Cima Bill Category", data.category_name):
        frappe.throw(f"El tipo de gasto '{data.category_name}' ya existe.")

    doc = frappe.get_doc(
        {
            "doctype": "Cima Bill Category",
            "category_name": data.category_name,
            "parent_group": data.parent_group,
            "description": data.description,
            "default_account": data.default_account or None,
            "is_active": 1,
        }
    )
    doc.insert()
    return {
        "name": doc.name,
        "category_name": doc.category_name,
        "parent_group": doc.parent_group,
        "description": doc.description,
    }


@whitelist()
def list_bills(
    date_from: str = "",
    date_to: str = "",
    category: str = "",
    group: str = "",
    status: str = "",
    limit: int = 200,
) -> dict:
    """Lista gastos filtrados junto con su resumen agrupado."""
    import frappe

    filters: dict = {}
    if date_from and date_to:
        filters["bill_date"] = ["between", [date_from, date_to]]
    elif date_from:
        filters["bill_date"] = [">=", date_from]
    elif date_to:
        filters["bill_date"] = ["<=", date_to]

    if category:
        filters["bill_category"] = category
    if group:
        filters["bill_group"] = group
    if status:
        filters["status"] = status

    rows = frappe.get_all(
        "Cima Bill",
        filters=filters,
        fields=[
            "name",
            "bill_title",
            "bill_category",
            "bill_group",
            "bill_date",
            "due_date",
            "amount",
            "currency",
            "payment_method",
            "status",
            "supplier_name",
            "reference_number",
            "notes",
        ],
        order_by="bill_date desc, creation desc",
        limit_page_length=min(max(int(limit or 200), 1), 1000),
    )
    return {
        "bills": rows,
        "summary": summarize_bills(rows),
    }


@whitelist()
def create_bill(
    bill_title: str,
    bill_category: str,
    bill_date: str,
    amount: float | str,
    currency: str = "USD",
    supplier_name: str = "",
    reference_number: str = "",
    payment_method: str = "Contado USD",
    status: str = "Pagada",
    due_date: str = "",
    notes: str = "",
) -> dict:
    """Registra una nueva factura de gasto en Cima Bill."""
    import frappe

    data = validate_bill_input(
        bill_title=bill_title,
        bill_category=bill_category,
        bill_date=bill_date,
        amount=float(amount),
        currency=currency,
        supplier_name=supplier_name,
        reference_number=reference_number,
        payment_method=payment_method,
        status=status,
        due_date=due_date,
        notes=notes,
    )
    doc = frappe.get_doc(
        {
            "doctype": "Cima Bill",
            "bill_title": data.bill_title,
            "bill_category": data.bill_category,
            "bill_date": data.bill_date,
            "due_date": data.due_date or None,
            "amount": data.amount,
            "currency": data.currency,
            "payment_method": data.payment_method,
            "status": data.status,
            "supplier_name": data.supplier_name,
            "reference_number": data.reference_number,
            "notes": data.notes,
        }
    )
    doc.insert()
    return {
        "name": doc.name,
        "bill_title": doc.bill_title,
        "bill_category": doc.bill_category,
        "bill_group": doc.bill_group,
        "amount": doc.amount,
        "currency": doc.currency,
        "status": doc.status,
    }


@whitelist()
def update_bill_status(bill_name: str, status: str) -> dict:
    """Actualiza el estado de un gasto (Pagada / Pendiente / Anulada)."""
    import frappe

    if status not in ("Pagada", "Pendiente", "Anulada"):
        frappe.throw("Estado inválido.")
    frappe.db.set_value("Cima Bill", bill_name, "status", status)
    return {"name": bill_name, "status": status}
