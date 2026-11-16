from __future__ import annotations


def _to_float(val) -> float:
    try:
        return float(val or 0.0)
    except (TypeError, ValueError):
        return 0.0


def compute_client_consumption(
    invoices: list[dict],
    delivery_notes: list[dict] | None = None,
    customer_meta: dict[str, dict] | None = None,
    default_currency: str = "USD",
) -> dict:
    """Agrupa el consumo total por cliente y el desglose de cuánto ha comprado por cada vendedor."""
    meta_map = customer_meta or {}
    clients_map: dict[str, dict] = {}
    currency = default_currency or "USD"

    def _ensure_client(cust_id: str, cust_name: str) -> dict:
        if cust_id not in clients_map:
            m = meta_map.get(cust_id, {})
            clients_map[cust_id] = {
                "customer": cust_id,
                "customer_name": cust_name or m.get("customer_name") or cust_id,
                "rif_cedula": m.get("ve_rif_cedula") or m.get("tax_id") or "",
                "invoice_count": 0,
                "total_consumed": 0.0,
                "paid_amount": 0.0,
                "outstanding_amount": 0.0,
                "total_qty": 0.0,
                "pending_dn_count": 0,
                "pending_dn_amount": 0.0,
                "last_purchase_date": "",
                "sellers": {},
            }
        return clients_map[cust_id]

    for idx, inv in enumerate(invoices or []):
        if idx == 0 and inv.get("currency"):
            currency = str(inv["currency"])
        cust_id = str(inv.get("customer") or "").strip()
        if not cust_id:
            continue
        cust_name = str(inv.get("customer_name") or cust_id).strip()
        c = _ensure_client(cust_id, cust_name)

        grand = _to_float(inv.get("grand_total"))
        outstanding = _to_float(inv.get("outstanding_amount"))
        paid = _to_float(inv.get("paid_amount"))
        if paid == 0.0 and grand > 0.0 and outstanding < grand:
            paid = round(max(grand - outstanding, 0.0), 2)
        qty = _to_float(inv.get("total_qty"))
        posting_date = str(inv.get("posting_date") or "")[:10]

        seller_user = str(inv.get("seller_user") or inv.get("ve_vendedor_usuario") or inv.get("owner") or "Sin usuario").strip()
        seller_name = str(inv.get("seller_name") or inv.get("ve_vendedor_nombre") or seller_user).strip()

        c["invoice_count"] += 1
        c["total_consumed"] += grand
        c["paid_amount"] += paid
        c["outstanding_amount"] += outstanding
        c["total_qty"] += qty
        if posting_date and (not c["last_purchase_date"] or posting_date > c["last_purchase_date"]):
            c["last_purchase_date"] = posting_date

        if seller_user not in c["sellers"]:
            c["sellers"][seller_user] = {
                "seller_user": seller_user,
                "seller_name": seller_name,
                "invoice_count": 0,
                "total_amount": 0.0,
                "pending_dn_count": 0,
                "pending_dn_amount": 0.0,
            }
        sb = c["sellers"][seller_user]
        if seller_name and sb["seller_name"] == sb["seller_user"] and seller_name != seller_user:
            sb["seller_name"] = seller_name
        sb["invoice_count"] += 1
        sb["total_amount"] += grand

    for dn in delivery_notes or []:
        cust_id = str(dn.get("customer") or "").strip()
        if not cust_id:
            continue
        cust_name = str(dn.get("customer_name") or cust_id).strip()
        c = _ensure_client(cust_id, cust_name)
        amount = _to_float(dn.get("grand_total") or dn.get("net_total"))
        posting_date = str(dn.get("posting_date") or "")[:10]
        seller_user = str(dn.get("seller_user") or dn.get("ve_vendedor_usuario") or dn.get("owner") or "Sin usuario").strip()
        seller_name = str(dn.get("seller_name") or dn.get("ve_vendedor_nombre") or seller_user).strip()

        c["pending_dn_count"] += 1
        c["pending_dn_amount"] += amount
        if posting_date and (not c["last_purchase_date"] or posting_date > c["last_purchase_date"]):
            c["last_purchase_date"] = posting_date

        if seller_user not in c["sellers"]:
            c["sellers"][seller_user] = {
                "seller_user": seller_user,
                "seller_name": seller_name,
                "invoice_count": 0,
                "total_amount": 0.0,
                "pending_dn_count": 0,
                "pending_dn_amount": 0.0,
            }
        sb = c["sellers"][seller_user]
        sb["pending_dn_count"] += 1
        sb["pending_dn_amount"] += amount

    clients_list: list[dict] = []
    total_consumed_all = 0.0
    total_pending_dn_all = 0.0

    for c in clients_map.values():
        total_c = round(c["total_consumed"], 2)
        pending_c = round(c["pending_dn_amount"], 2)
        total_consumed_all += total_c
        total_pending_dn_all += pending_c

        by_seller = []
        for sb in c["sellers"].values():
            amt = round(sb["total_amount"], 2)
            share = round((amt / total_c) * 100.0, 1) if total_c > 0 else 0.0
            by_seller.append(
                {
                    "seller_user": sb["seller_user"],
                    "seller_name": sb["seller_name"],
                    "invoice_count": sb["invoice_count"],
                    "total_amount": amt,
                    "pending_dn_count": sb["pending_dn_count"],
                    "pending_dn_amount": round(sb["pending_dn_amount"], 2),
                    "share_pct": share,
                }
            )
        by_seller.sort(key=lambda r: (-r["total_amount"], -r["pending_dn_amount"], r["seller_name"]))

        clients_list.append(
            {
                "customer": c["customer"],
                "customer_name": c["customer_name"],
                "rif_cedula": c["rif_cedula"],
                "invoice_count": c["invoice_count"],
                "total_consumed": total_c,
                "paid_amount": round(c["paid_amount"], 2),
                "outstanding_amount": round(c["outstanding_amount"], 2),
                "total_qty": round(c["total_qty"], 2),
                "pending_dn_count": c["pending_dn_count"],
                "pending_dn_amount": pending_c,
                "last_purchase_date": c["last_purchase_date"],
                "by_seller": by_seller,
            }
        )

    clients_list.sort(key=lambda r: (-r["total_consumed"], -r["pending_dn_amount"], r["customer_name"]))
    total_customers = len(clients_list)
    top_customer = clients_list[0]["customer_name"] if clients_list else "-"

    return {
        "summary": {
            "currency": currency,
            "total_customers": total_customers,
            "total_consumed": round(total_consumed_all, 2),
            "total_pending_dn": round(total_pending_dn_all, 2),
            "avg_per_customer": round(total_consumed_all / total_customers, 2) if total_customers else 0.0,
            "top_customer": top_customer,
        },
        "clients": clients_list,
    }
