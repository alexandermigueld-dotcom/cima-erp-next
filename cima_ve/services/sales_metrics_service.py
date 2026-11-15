from __future__ import annotations

from collections import defaultdict


def _to_float(val) -> float:
    try:
        return float(val or 0.0)
    except (TypeError, ValueError):
        return 0.0


def compute_sales_metrics(
    invoices: list[dict],
    invoice_items: list[dict] | None = None,
    default_currency: str = "USD",
) -> dict:
    """Calcula métricas globales y desglose por usuario vendedor a partir de facturas."""
    total_sales = 0.0
    net_sales = 0.0
    tax_total = 0.0
    igtf_total = 0.0
    paid_amount = 0.0
    outstanding_amount = 0.0
    total_qty = 0.0
    invoice_count = 0
    return_count = 0
    fiscal_stamped_count = 0
    cashea_count = 0
    cashea_total = 0.0
    all_customers: set[str] = set()
    currency = default_currency or "USD"

    user_buckets: dict[str, dict] = {}
    channel_buckets: dict[str, dict] = defaultdict(
        lambda: {"channel": "", "invoice_count": 0, "total_sales": 0.0}
    )
    daily_buckets: dict[str, dict] = defaultdict(
        lambda: {"date": "", "invoice_count": 0, "total_sales": 0.0}
    )
    customer_buckets: dict[str, dict] = {}
    recent_invoices: list[dict] = []

    for idx, inv in enumerate(invoices or []):
        if idx == 0 and inv.get("currency"):
            currency = str(inv["currency"])

        is_return = bool(inv.get("is_return"))
        grand = _to_float(inv.get("grand_total"))
        net = _to_float(inv.get("net_total"))
        tax = _to_float(inv.get("total_taxes_and_charges"))
        igtf = _to_float(inv.get("ve_igtf_amount"))
        outstanding = _to_float(inv.get("outstanding_amount"))
        paid = _to_float(inv.get("paid_amount"))
        if paid == 0.0 and grand > 0.0 and outstanding < grand:
            paid = round(max(grand - outstanding, 0.0), 2)
        qty = _to_float(inv.get("total_qty"))

        seller_user = str(inv.get("seller_user") or inv.get("ve_vendedor_usuario") or inv.get("owner") or "Sin usuario").strip()
        seller_name = str(inv.get("seller_name") or inv.get("ve_vendedor_nombre") or seller_user).strip()
        channel = str(inv.get("canal_venta") or "Sin canal").strip() or "Sin canal"
        customer = str(inv.get("customer") or "").strip()
        customer_name = str(inv.get("customer_name") or customer or "Cliente").strip()
        posting_date = str(inv.get("posting_date") or "")[:10]
        fiscal_status = str(inv.get("ve_fiscal_status") or "").strip()
        is_fiscal_stamped = bool(inv.get("ve_numero_control")) or fiscal_status in ("Timbrada", "Simulada")
        is_cashea = bool(inv.get("cashea_order_id")) or bool(inv.get("cashea_status"))

        total_sales += grand
        net_sales += net
        tax_total += tax
        igtf_total += igtf
        paid_amount += paid
        outstanding_amount += outstanding
        total_qty += qty
        if is_return:
            return_count += 1
        else:
            invoice_count += 1
        if is_fiscal_stamped:
            fiscal_stamped_count += 1
        if is_cashea:
            cashea_count += 1
            cashea_total += grand
        if customer:
            all_customers.add(customer)

        if seller_user not in user_buckets:
            user_buckets[seller_user] = {
                "user": seller_user,
                "fullname": seller_name,
                "invoice_count": 0,
                "return_count": 0,
                "total_sales": 0.0,
                "net_sales": 0.0,
                "tax_total": 0.0,
                "igtf_total": 0.0,
                "paid_amount": 0.0,
                "outstanding_amount": 0.0,
                "total_qty": 0.0,
                "fiscal_stamped_count": 0,
                "cashea_count": 0,
                "cashea_total": 0.0,
                "customers": set(),
                "last_sale_date": posting_date,
            }
        ub = user_buckets[seller_user]
        if seller_name and ub["fullname"] == ub["user"] and seller_name != seller_user:
            ub["fullname"] = seller_name
        if is_return:
            ub["return_count"] += 1
        else:
            ub["invoice_count"] += 1
        ub["total_sales"] += grand
        ub["net_sales"] += net
        ub["tax_total"] += tax
        ub["igtf_total"] += igtf
        ub["paid_amount"] += paid
        ub["outstanding_amount"] += outstanding
        ub["total_qty"] += qty
        if is_fiscal_stamped:
            ub["fiscal_stamped_count"] += 1
        if is_cashea:
            ub["cashea_count"] += 1
            ub["cashea_total"] += grand
        if customer:
            ub["customers"].add(customer)
        if posting_date and (not ub["last_sale_date"] or posting_date > ub["last_sale_date"]):
            ub["last_sale_date"] = posting_date

        cb = channel_buckets[channel]
        cb["channel"] = channel
        if not is_return:
            cb["invoice_count"] += 1
        cb["total_sales"] += grand

        if posting_date:
            db = daily_buckets[posting_date]
            db["date"] = posting_date
            if not is_return:
                db["invoice_count"] += 1
            db["total_sales"] += grand

        if customer:
            if customer not in customer_buckets:
                customer_buckets[customer] = {
                    "customer": customer,
                    "customer_name": customer_name,
                    "invoice_count": 0,
                    "total_sales": 0.0,
                }
            if not is_return:
                customer_buckets[customer]["invoice_count"] += 1
            customer_buckets[customer]["total_sales"] += grand

        recent_invoices.append(
            {
                "name": inv.get("name") or "",
                "posting_date": posting_date,
                "seller_user": seller_user,
                "seller_name": seller_name,
                "customer": customer,
                "customer_name": customer_name,
                "canal_venta": channel,
                "grand_total": round(grand, 2),
                "paid_amount": round(paid, 2),
                "outstanding_amount": round(outstanding, 2),
                "ve_fiscal_status": fiscal_status or ("Timbrada" if is_fiscal_stamped else "Pendiente"),
                "ve_numero_control": inv.get("ve_numero_control") or "",
                "cashea_order_id": inv.get("cashea_order_id") or "",
                "cashea_status": inv.get("cashea_status") or "",
                "currency": inv.get("currency") or currency,
                "is_return": is_return,
            }
        )

    by_user = []
    for ub in user_buckets.values():
        cnt = ub["invoice_count"] or ub["return_count"] or 1
        share_pct = round((ub["total_sales"] / total_sales) * 100.0, 1) if total_sales > 0 else 0.0
        by_user.append(
            {
                "user": ub["user"],
                "fullname": ub["fullname"],
                "invoice_count": ub["invoice_count"],
                "return_count": ub["return_count"],
                "share_pct": share_pct,
                "total_sales": round(ub["total_sales"], 2),
                "net_sales": round(ub["net_sales"], 2),
                "tax_total": round(ub["tax_total"], 2),
                "igtf_total": round(ub["igtf_total"], 2),
                "paid_amount": round(ub["paid_amount"], 2),
                "outstanding_amount": round(ub["outstanding_amount"], 2),
                "avg_ticket": round(ub["total_sales"] / cnt, 2) if ub["invoice_count"] > 0 else 0.0,
                "total_qty": round(ub["total_qty"], 2),
                "unique_customers": len(ub["customers"]),
                "fiscal_stamped_count": ub["fiscal_stamped_count"],
                "cashea_count": ub["cashea_count"],
                "cashea_total": round(ub["cashea_total"], 2),
                "last_sale_date": ub["last_sale_date"],
            }
        )
    by_user.sort(key=lambda r: (-r["total_sales"], -r["invoice_count"], r["fullname"]))

    by_channel = []
    for cb in channel_buckets.values():
        share_pct = round((cb["total_sales"] / total_sales) * 100.0, 1) if total_sales > 0 else 0.0
        by_channel.append(
            {
                "channel": cb["channel"],
                "invoice_count": cb["invoice_count"],
                "total_sales": round(cb["total_sales"], 2),
                "share_pct": share_pct,
            }
        )
    by_channel.sort(key=lambda r: (-r["total_sales"], r["channel"]))

    daily_trend = [
        {
            "date": db["date"],
            "invoice_count": db["invoice_count"],
            "total_sales": round(db["total_sales"], 2),
        }
        for db in sorted(daily_buckets.values(), key=lambda x: x["date"])
    ]

    item_buckets: dict[str, dict] = {}
    for row in invoice_items or []:
        code = str(row.get("item_code") or "").strip()
        if not code:
            continue
        if code not in item_buckets:
            item_buckets[code] = {
                "item_code": code,
                "item_name": str(row.get("item_name") or code),
                "qty": 0.0,
                "amount": 0.0,
                "parents": set(),
            }
        ib = item_buckets[code]
        ib["qty"] += _to_float(row.get("qty"))
        ib["amount"] += _to_float(row.get("amount"))
        if row.get("parent"):
            ib["parents"].add(str(row["parent"]))

    top_items = sorted(
        [
            {
                "item_code": ib["item_code"],
                "item_name": ib["item_name"],
                "qty": round(ib["qty"], 2),
                "amount": round(ib["amount"], 2),
                "invoice_count": len(ib["parents"]),
            }
            for ib in item_buckets.values()
        ],
        key=lambda r: (-r["amount"], -r["qty"]),
    )[:10]

    top_customers = sorted(
        [
            {
                "customer": cb["customer"],
                "customer_name": cb["customer_name"],
                "invoice_count": cb["invoice_count"],
                "total_sales": round(cb["total_sales"], 2),
            }
            for cb in customer_buckets.values()
        ],
        key=lambda r: (-r["total_sales"], -r["invoice_count"]),
    )[:10]

    recent_invoices.sort(key=lambda r: (r["posting_date"], r["name"]), reverse=True)

    summary = {
        "currency": currency,
        "total_sales": round(total_sales, 2),
        "net_sales": round(net_sales, 2),
        "tax_total": round(tax_total, 2),
        "igtf_total": round(igtf_total, 2),
        "paid_amount": round(paid_amount, 2),
        "outstanding_amount": round(outstanding_amount, 2),
        "invoice_count": invoice_count,
        "return_count": return_count,
        "avg_ticket": round(total_sales / invoice_count, 2) if invoice_count > 0 else 0.0,
        "total_qty": round(total_qty, 2),
        "unique_customers": len(all_customers),
        "unique_sellers": len(by_user),
        "fiscal_stamped_count": fiscal_stamped_count,
        "cashea_count": cashea_count,
        "cashea_total": round(cashea_total, 2),
    }

    return {
        "summary": summary,
        "by_user": by_user,
        "by_channel": by_channel,
        "daily_trend": daily_trend,
        "top_items": top_items,
        "top_customers": top_customers,
        "invoices": recent_invoices[:100],
    }
