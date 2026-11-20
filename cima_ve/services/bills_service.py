from __future__ import annotations

from collections import defaultdict
from dataclasses import asdict, dataclass

VALID_BILL_GROUPS = (
    "Operativos",
    "Logística e Importación",
    "Marketing y Meta Ads",
    "Nómina y Personal",
    "Impuestos y Legales",
    "Servicios Públicos",
    "Otros",
)

VALID_BILL_STATUSES = ("Pagada", "Pendiente", "Anulada")


@dataclass(slots=True)
class BillCategoryInput:
    category_name: str
    parent_group: str = "Operativos"
    description: str = ""
    default_account: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(slots=True)
class BillInput:
    bill_title: str
    bill_category: str
    bill_date: str
    amount: float
    currency: str = "USD"
    supplier_name: str = ""
    reference_number: str = ""
    payment_method: str = "Contado USD"
    status: str = "Pagada"
    due_date: str = ""
    notes: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


def validate_bill_category_input(
    category_name: str,
    parent_group: str = "Operativos",
    description: str = "",
    default_account: str = "",
) -> BillCategoryInput:
    clean_name = (category_name or "").strip()
    if not clean_name:
        raise ValueError("El nombre del tipo de gasto es obligatorio.")
    group_clean = (parent_group or "Operativos").strip()
    if group_clean not in VALID_BILL_GROUPS:
        group_clean = "Otros"
    return BillCategoryInput(
        category_name=clean_name,
        parent_group=group_clean,
        description=(description or "").strip(),
        default_account=(default_account or "").strip(),
    )


def validate_bill_input(
    bill_title: str,
    bill_category: str,
    bill_date: str,
    amount: float,
    currency: str = "USD",
    supplier_name: str = "",
    reference_number: str = "",
    payment_method: str = "Contado USD",
    status: str = "Pagada",
    due_date: str = "",
    notes: str = "",
) -> BillInput:
    title_clean = (bill_title or "").strip()
    cat_clean = (bill_category or "").strip()
    date_clean = (bill_date or "").strip()
    if not title_clean:
        raise ValueError("El concepto o descripción del gasto es obligatorio.")
    if not cat_clean:
        raise ValueError("Debe seleccionar un tipo de gasto (categoría).")
    if not date_clean:
        raise ValueError("La fecha del gasto es obligatoria.")

    amt = float(amount or 0)
    if amt <= 0:
        raise ValueError("El monto del gasto debe ser mayor a 0.")

    curr_clean = (currency or "USD").strip().upper()
    if curr_clean not in ("USD", "VES"):
        curr_clean = "USD"

    status_clean = (status or "Pagada").strip()
    if status_clean not in VALID_BILL_STATUSES:
        raise ValueError(f"Estado inválido: {status_clean}")

    return BillInput(
        bill_title=title_clean,
        bill_category=cat_clean,
        bill_date=date_clean,
        amount=round(amt, 2),
        currency=curr_clean,
        supplier_name=(supplier_name or "").strip(),
        reference_number=(reference_number or "").strip(),
        payment_method=(payment_method or "Contado USD").strip(),
        status=status_clean,
        due_date=(due_date or "").strip(),
        notes=(notes or "").strip(),
    )


def summarize_bills(bills: list[dict]) -> dict:
    """Agrupa gastos por grupo, categoría, estado y método de pago (excluye anuladas)."""
    total_paid = 0.0
    total_pending = 0.0
    total_count = 0
    by_group: dict[str, dict] = defaultdict(lambda: {"group": "", "count": 0, "total": 0.0})
    by_category: dict[str, dict] = defaultdict(
        lambda: {"category": "", "group": "", "count": 0, "total": 0.0}
    )
    by_payment_method: dict[str, dict] = defaultdict(
        lambda: {"payment_method": "", "count": 0, "total": 0.0}
    )

    for row in bills:
        status = str(row.get("status") or "Pagada").strip()
        if status == "Anulada":
            continue
        amt = float(row.get("amount") or 0.0)
        group = str(row.get("bill_group") or "Otros").strip() or "Otros"
        cat = str(row.get("bill_category") or "Sin Categoría").strip() or "Sin Categoría"
        pm = str(row.get("payment_method") or "Otro").strip() or "Otro"

        total_count += 1
        if status == "Pendiente":
            total_pending += amt
        else:
            total_paid += amt

        by_group[group]["group"] = group
        by_group[group]["count"] += 1
        by_group[group]["total"] = round(by_group[group]["total"] + amt, 2)

        by_category[cat]["category"] = cat
        by_category[cat]["group"] = group
        by_category[cat]["count"] += 1
        by_category[cat]["total"] = round(by_category[cat]["total"] + amt, 2)

        by_payment_method[pm]["payment_method"] = pm
        by_payment_method[pm]["count"] += 1
        by_payment_method[pm]["total"] = round(by_payment_method[pm]["total"] + amt, 2)

    total_spent = round(total_paid + total_pending, 2)
    return {
        "total_count": total_count,
        "total_paid": round(total_paid, 2),
        "total_pending": round(total_pending, 2),
        "total_spent": total_spent,
        "by_group": sorted(by_group.values(), key=lambda x: x["total"], reverse=True),
        "by_category": sorted(by_category.values(), key=lambda x: x["total"], reverse=True),
        "by_payment_method": sorted(by_payment_method.values(), key=lambda x: x["total"], reverse=True),
    }
