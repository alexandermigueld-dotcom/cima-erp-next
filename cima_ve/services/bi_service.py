from __future__ import annotations

import math
from datetime import date, timedelta


def analyze_inventory_intelligence(
    items: list[dict],
    sales_rows: list[dict],
    china_lead_time_days: int = 45,
    safety_stock_days: int = 15,
    analysis_window_days: int = 90,
    reorder_cycle_days: int = 30,
    today: date | None = None,
) -> dict:
    """
    Analiza demanda, velocidad de venta, fecha estimada de agotamiento,
    clasificación ABC y cantidad sugerida de compra para importación desde China.
    """
    ref_date = today or date.today()
    lead_days = max(1, int(china_lead_time_days or 45))
    safety_days = max(0, int(safety_stock_days or 15))
    window_days = max(1, int(analysis_window_days or 90))
    cycle_days = max(1, int(reorder_cycle_days or 30))

    sales_by_item: dict[str, dict] = {}
    for row in sales_rows:
        code = str(row.get("item_code") or "").strip()
        if not code:
            continue
        entry = sales_by_item.setdefault(code, {"units_sold": 0.0, "revenue": 0.0})
        entry["units_sold"] += float(row.get("qty") or 0.0)
        entry["revenue"] += float(row.get("amount") or 0.0)

    analyzed: list[dict] = []
    total_revenue_all = 0.0
    total_inventory_value = 0.0
    total_recommended_investment = 0.0

    for item in items:
        code = str(item.get("item_code") or "").strip()
        if not code:
            continue
        name = str(item.get("item_name") or code)
        group = str(item.get("item_group") or "General")
        stock = max(0.0, float(item.get("stock_qty") or 0.0))
        incoming = max(0.0, float(item.get("incoming_qty") or 0.0))
        cost = max(0.0, float(item.get("valuation_rate") or item.get("cost") or 0.0))
        price = max(0.0, float(item.get("price") or item.get("standard_rate") or 0.0))

        s_info = sales_by_item.get(code, {"units_sold": 0.0, "revenue": 0.0})
        units_sold = round(float(s_info["units_sold"]), 2)
        revenue = round(float(s_info["revenue"]), 2)
        total_revenue_all += revenue
        total_inventory_value += stock * cost

        daily_velocity = round(units_sold / window_days, 4) if units_sold > 0 else 0.0

        if daily_velocity > 0:
            days_until_stockout = round(stock / daily_velocity, 1)
            est_stockout_date = (ref_date + timedelta(days=int(round(days_until_stockout)))).isoformat()
        else:
            days_until_stockout = None
            est_stockout_date = None

        target_coverage_days = lead_days + safety_days + cycle_days
        target_stock = daily_velocity * target_coverage_days
        effective_stock = stock + incoming
        raw_reorder = max(0.0, target_stock - effective_stock)
        recommended_order_qty = int(math.ceil(raw_reorder)) if raw_reorder > 0 else 0
        est_order_cost = round(recommended_order_qty * cost, 2)
        total_recommended_investment += est_order_cost

        if daily_velocity == 0:
            alert_level = "SIN MOVIMIENTO" if stock > 0 else "INACTIVO"
        elif days_until_stockout is not None and days_until_stockout <= lead_days:
            alert_level = "CRÍTICO"
        elif days_until_stockout is not None and days_until_stockout <= (lead_days + safety_days):
            alert_level = "ALERTA"
        else:
            alert_level = "SALUDABLE"

        analyzed.append(
            {
                "item_code": code,
                "item_name": name,
                "item_group": group,
                "current_stock": round(stock, 2),
                "incoming_qty": round(incoming, 2),
                "units_sold_window": units_sold,
                "revenue_window": revenue,
                "daily_velocity": daily_velocity,
                "monthly_velocity": round(daily_velocity * 30.0, 1),
                "days_until_stockout": days_until_stockout,
                "est_stockout_date": est_stockout_date,
                "alert_level": alert_level,
                "will_stockout_before_china": bool(
                    days_until_stockout is not None and days_until_stockout < lead_days
                ),
                "recommended_order_qty": recommended_order_qty,
                "unit_cost": round(cost, 2),
                "unit_price": round(price, 2),
                "est_order_cost": est_order_cost,
                "stock_value": round(stock * cost, 2),
                "abc_class": "C",
            }
        )

    # ABC classification by revenue
    analyzed_by_rev = sorted(analyzed, key=lambda x: x["revenue_window"], reverse=True)
    cum_rev = 0.0
    for row in analyzed_by_rev:
        if total_revenue_all <= 0 or row["revenue_window"] <= 0:
            row["abc_class"] = "C"
            continue
        cum_rev += row["revenue_window"]
        pct = (cum_rev / total_revenue_all) * 100.0
        if pct <= 80.0:
            row["abc_class"] = "A"
        elif pct <= 95.0:
            row["abc_class"] = "B"
        else:
            row["abc_class"] = "C"

    critical_items = sorted(
        [x for x in analyzed if x["will_stockout_before_china"]],
        key=lambda x: (x["days_until_stockout"] if x["days_until_stockout"] is not None else 99999),
    )
    warning_items = [x for x in analyzed if x["alert_level"] == "ALERTA"]
    top_revenue_items = analyzed_by_rev[:10]
    fastest_selling_items = sorted(
        [x for x in analyzed if x["daily_velocity"] > 0],
        key=lambda x: x["daily_velocity"],
        reverse=True,
    )[:10]
    slow_dead_stock = sorted(
        [x for x in analyzed if x["alert_level"] == "SIN MOVIMIENTO"],
        key=lambda x: x["stock_value"],
        reverse=True,
    )[:10]
    purchase_plan = sorted(
        [x for x in analyzed if x["recommended_order_qty"] > 0],
        key=lambda x: (0 if x["will_stockout_before_china"] else 1, -x["revenue_window"]),
    )

    return {
        "config": {
            "china_lead_time_days": lead_days,
            "safety_stock_days": safety_days,
            "analysis_window_days": window_days,
            "reorder_cycle_days": cycle_days,
        },
        "kpis": {
            "total_items_analyzed": len(analyzed),
            "critical_count": len(critical_items),
            "warning_count": len(warning_items),
            "dead_stock_count": len([x for x in analyzed if x["alert_level"] == "SIN MOVIMIENTO"]),
            "total_revenue_window": round(total_revenue_all, 2),
            "total_inventory_value": round(total_inventory_value, 2),
            "total_recommended_investment": round(total_recommended_investment, 2),
        },
        "critical_items": critical_items,
        "top_revenue_items": top_revenue_items,
        "fastest_selling_items": fastest_selling_items,
        "slow_dead_stock": slow_dead_stock,
        "purchase_plan": purchase_plan,
        "all_items": analyzed_by_rev,
    }


def build_weekly_stockout_email_html(analysis: dict) -> str:
    """Genera el HTML del correo semanal de alerta de reposición para importación desde China."""
    lead_days = analysis["config"]["china_lead_time_days"]
    critical = analysis["critical_items"]

    rows_html = ""
    for item in critical:
        days_left = item["days_until_stockout"]
        rows_html += f"""
        <tr>
            <td style="padding:8px 10px;border-bottom:1px solid #e2e8f0;"><code>{item['item_code']}</code></td>
            <td style="padding:8px 10px;border-bottom:1px solid #e2e8f0;"><strong>{item['item_name']}</strong></td>
            <td style="padding:8px 10px;border-bottom:1px solid #e2e8f0;text-align:right;">{item['current_stock']}</td>
            <td style="padding:8px 10px;border-bottom:1px solid #e2e8f0;text-align:right;">{item['daily_velocity']:.2f}/día</td>
            <td style="padding:8px 10px;border-bottom:1px solid #e2e8f0;text-align:right;color:#b91c1c;font-weight:700;">{days_left} días</td>
            <td style="padding:8px 10px;border-bottom:1px solid #e2e8f0;">{item['est_stockout_date'] or '-'}</td>
            <td style="padding:8px 10px;border-bottom:1px solid #e2e8f0;text-align:right;font-weight:700;color:#0b6e68;">{item['recommended_order_qty']} uds</td>
        </tr>
        """

    return f"""
    <div style="font-family:Segoe UI,Arial,sans-serif;max-width:780px;margin:0 auto;color:#1c2532;">
      <div style="background:#1c2532;color:#ffffff;padding:20px 24px;border-radius:12px 12px 0 0;border-bottom:4px solid #06c686;">
        <h2 style="margin:0 0 6px;font-size:20px;">Alerta Semanal de Inventario — CIMA Electronic VE</h2>
        <p style="margin:0;color:#cbd5e1;font-size:13px;">
          Productos que se agotarán en menos de <strong>{lead_days} días</strong> (tiempo configurado de llegada desde China).
        </p>
      </div>
      <div style="padding:20px 24px;border:1px solid #d9e6e5;border-top:none;border-radius:0 0 12px 12px;background:#ffffff;">
        <p style="margin-top:0;">Se detectaron <strong>{len(critical)}</strong> productos en estado crítico de reposición:</p>
        <table style="width:100%;border-collapse:collapse;font-size:13px;">
          <thead>
            <tr style="background:#f4f8f8;text-align:left;">
              <th style="padding:8px 10px;">Código</th>
              <th style="padding:8px 10px;">Producto</th>
              <th style="padding:8px 10px;text-align:right;">Stock Actual</th>
              <th style="padding:8px 10px;text-align:right;">Rotación</th>
              <th style="padding:8px 10px;text-align:right;">Días Restantes</th>
              <th style="padding:8px 10px;">Agotamiento Est.</th>
              <th style="padding:8px 10px;text-align:right;">Pedido Sugerido</th>
            </tr>
          </thead>
          <tbody>{rows_html}</tbody>
        </table>
      </div>
    </div>
    """
