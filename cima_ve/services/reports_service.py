from __future__ import annotations

from collections import defaultdict


def classify_sales_channel(invoice: dict) -> str:
    """Clasifica una venta en Detal, Mayor, Meta Ads u Otros."""
    explicit = str(invoice.get("ve_sales_channel") or "").strip().lower()
    price_list = str(invoice.get("selling_price_list") or "").strip().lower()
    customer_group = str(invoice.get("customer_group") or "").strip().lower()
    remarks = str(invoice.get("remarks") or "").strip().lower()
    combined = f"{explicit} {price_list} {customer_group} {remarks}"

    if "meta" in combined or "instagram" in combined or "facebook" in combined or "ads" in combined:
        return "Meta Ads"
    if "mayor" in combined or "wholesale" in combined:
        return "Mayor"
    if "detal" in combined or "tienda" in combined or "retail" in combined or explicit == "":
        return "Detal"
    return "Otros"


def extract_payment_method(invoice: dict) -> str:
    """Extrae el método de pago normalizado de una factura."""
    if invoice.get("cashea_order_id") or "cashea" in str(invoice.get("ve_payment_method") or "").lower():
        return "Cashea"
    pm = str(invoice.get("ve_payment_method") or "").strip()
    if pm:
        return pm

    remarks = str(invoice.get("remarks") or "")
    for marker in ("Método:", "Metodo:"):
        if marker in remarks:
            part = remarks.split(marker, 1)[1].strip()
            if part:
                return part.split("|")[0].strip()

    if invoice.get("mode_of_payment"):
        return str(invoice["mode_of_payment"]).strip()
    return "Contado USD"


def build_executive_report(
    invoices: list[dict],
    bills: list[dict],
    delivery_notes: list[dict] | None = None,
    invoice_items: list[dict] | None = None,
    date_from: str = "",
    date_to: str = "",
) -> dict:
    """Construye el reporte ejecutivo completo de CIMA Electronic VE."""
    delivery_notes = delivery_notes or []
    invoice_items = invoice_items or []

    total_revenue = 0.0
    total_iva = 0.0
    total_igtf = 0.0
    invoice_count = 0

    channel_totals: dict[str, dict] = {
        "Detal": {"channel": "Detal", "count": 0, "total": 0.0},
        "Mayor": {"channel": "Mayor", "count": 0, "total": 0.0},
        "Meta Ads": {"channel": "Meta Ads", "count": 0, "total": 0.0},
        "Otros": {"channel": "Otros", "count": 0, "total": 0.0},
    }
    payment_totals: dict[str, dict] = defaultdict(
        lambda: {"payment_method": "", "count": 0, "total": 0.0}
    )
    seller_totals: dict[str, dict] = defaultdict(
        lambda: {
            "seller": "",
            "invoice_count": 0,
            "total_sales": 0.0,
            "detal_sales": 0.0,
            "mayor_sales": 0.0,
            "meta_ads_sales": 0.0,
            "avg_ticket": 0.0,
            "share_pct": 0.0,
        }
    )
    daily_series: dict[str, dict] = defaultdict(
        lambda: {"date": "", "revenue": 0.0, "expenses": 0.0}
    )
    pending_invoices: list[dict] = []

    for inv in invoices:
        if int(inv.get("docstatus") if inv.get("docstatus") is not None else 1) == 2:
            continue

        grand_total = float(inv.get("grand_total") or 0.0)
        outstanding = float(inv.get("outstanding_amount") or 0.0)
        iva_amt = float(inv.get("total_taxes_and_charges") or 0.0)
        igtf_amt = float(inv.get("ve_igtf_amount") or 0.0)
        posting_date = str(inv.get("posting_date") or "")[:10]
        seller = str(inv.get("seller_name") or inv.get("owner") or "Sin Asignar").strip()

        total_revenue += grand_total
        total_iva += iva_amt
        total_igtf += igtf_amt
        invoice_count += 1

        channel = classify_sales_channel(inv)
        channel_totals[channel]["count"] += 1
        channel_totals[channel]["total"] = round(channel_totals[channel]["total"] + grand_total, 2)

        pm = extract_payment_method(inv)
        payment_totals[pm]["payment_method"] = pm
        payment_totals[pm]["count"] += 1
        payment_totals[pm]["total"] = round(payment_totals[pm]["total"] + grand_total, 2)

        s_entry = seller_totals[seller]
        s_entry["seller"] = seller
        s_entry["invoice_count"] += 1
        s_entry["total_sales"] = round(s_entry["total_sales"] + grand_total, 2)
        if channel == "Detal":
            s_entry["detal_sales"] = round(s_entry["detal_sales"] + grand_total, 2)
        elif channel == "Mayor":
            s_entry["mayor_sales"] = round(s_entry["mayor_sales"] + grand_total, 2)
        elif channel == "Meta Ads":
            s_entry["meta_ads_sales"] = round(s_entry["meta_ads_sales"] + grand_total, 2)

        if posting_date:
            daily_series[posting_date]["date"] = posting_date
            daily_series[posting_date]["revenue"] = round(
                daily_series[posting_date]["revenue"] + grand_total, 2
            )

        if outstanding > 0.01:
            pending_invoices.append(
                {
                    "doctype": "Sales Invoice",
                    "name": inv.get("name"),
                    "customer": inv.get("customer_name") or inv.get("customer"),
                    "date": posting_date,
                    "grand_total": round(grand_total, 2),
                    "pending_amount": round(outstanding, 2),
                    "status": inv.get("status") or "Unpaid",
                }
            )

    # Expenses from Cima Bill (and any Purchase Invoices passed in)
    total_expenses = 0.0
    expenses_pending = 0.0
    expense_by_group: dict[str, dict] = defaultdict(lambda: {"group": "", "count": 0, "total": 0.0})

    for bill in bills:
        status = str(bill.get("status") or "Pagada")
        if status == "Anulada":
            continue
        amt = float(bill.get("amount") or 0.0)
        total_expenses += amt
        if status == "Pendiente":
            expenses_pending += amt
        grp = str(bill.get("bill_group") or "Otros")
        expense_by_group[grp]["group"] = grp
        expense_by_group[grp]["count"] += 1
        expense_by_group[grp]["total"] = round(expense_by_group[grp]["total"] + amt, 2)

        b_date = str(bill.get("bill_date") or "")[:10]
        if b_date:
            daily_series[b_date]["date"] = b_date
            daily_series[b_date]["expenses"] = round(daily_series[b_date]["expenses"] + amt, 2)

    # Notas de Entrega pendientes por pagar / facturar
    pending_delivery_notes: list[dict] = []
    for dn in delivery_notes:
        if int(dn.get("docstatus") if dn.get("docstatus") is not None else 1) == 2:
            continue
        per_billed = float(dn.get("per_billed") or 0.0)
        grand_total = float(dn.get("grand_total") or 0.0)
        pending_amt = round(grand_total * max(0.0, (100.0 - per_billed) / 100.0), 2)
        if pending_amt > 0.01 or str(dn.get("status") or "") == "To Bill":
            pending_delivery_notes.append(
                {
                    "doctype": "Delivery Note",
                    "name": dn.get("name"),
                    "customer": dn.get("customer_name") or dn.get("customer"),
                    "date": str(dn.get("posting_date") or "")[:10],
                    "grand_total": round(grand_total, 2),
                    "pending_amount": pending_amt if pending_amt > 0 else round(grand_total, 2),
                    "status": dn.get("status") or "Por Facturar / Pagar",
                }
            )

    all_pending_notes = pending_delivery_notes + pending_invoices
    pending_notes_total = round(sum(x["pending_amount"] for x in all_pending_notes), 2)

    # Finalize seller metrics
    sellers_list = []
    for s in seller_totals.values():
        s["avg_ticket"] = round(s["total_sales"] / s["invoice_count"], 2) if s["invoice_count"] else 0.0
        s["share_pct"] = round((s["total_sales"] / total_revenue) * 100.0, 1) if total_revenue > 0 else 0.0
        sellers_list.append(s)
    sellers_list.sort(key=lambda x: x["total_sales"], reverse=True)

    # Top products
    product_totals: dict[str, dict] = defaultdict(
        lambda: {"item_code": "", "item_name": "", "qty": 0.0, "revenue": 0.0}
    )
    for row in invoice_items:
        code = str(row.get("item_code") or "")
        if not code:
            continue
        p = product_totals[code]
        p["item_code"] = code
        p["item_name"] = str(row.get("item_name") or code)
        p["qty"] = round(p["qty"] + float(row.get("qty") or 0.0), 2)
        p["revenue"] = round(p["revenue"] + float(row.get("amount") or 0.0), 2)

    top_products = sorted(product_totals.values(), key=lambda x: x["revenue"], reverse=True)[:10]

    net_profit = round(total_revenue - total_expenses, 2)
    profit_margin_pct = round((net_profit / total_revenue) * 100.0, 1) if total_revenue > 0 else 0.0
    avg_ticket = round(total_revenue / invoice_count, 2) if invoice_count > 0 else 0.0

    return {
        "period": {"date_from": date_from, "date_to": date_to},
        "kpis": {
            "total_revenue": round(total_revenue, 2),
            "total_expenses": round(total_expenses, 2),
            "expenses_pending": round(expenses_pending, 2),
            "net_profit": net_profit,
            "profit_margin_pct": profit_margin_pct,
            "invoice_count": invoice_count,
            "avg_ticket": avg_ticket,
            "pending_notes_count": len(all_pending_notes),
            "pending_notes_total": pending_notes_total,
            "total_iva": round(total_iva, 2),
            "total_igtf": round(total_igtf, 2),
        },
        "sales_by_channel": list(channel_totals.values()),
        "sales_by_payment_method": sorted(
            payment_totals.values(), key=lambda x: x["total"], reverse=True
        ),
        "sellers_summary": sellers_list,
        "pending_delivery_notes": sorted(
            all_pending_notes, key=lambda x: x["pending_amount"], reverse=True
        ),
        "expenses_by_group": sorted(
            expense_by_group.values(), key=lambda x: x["total"], reverse=True
        ),
        "top_products": top_products,
        "daily_series": sorted(daily_series.values(), key=lambda x: x["date"]),
    }
