from __future__ import annotations

from datetime import date, timedelta

from cima_ve.api._compat import whitelist
from cima_ve.services.reports_service import build_executive_report


def _fetch_report_data(date_from: str = "", date_to: str = "") -> dict:
    import frappe

    today = date.today()
    if not date_to:
        date_to = today.isoformat()
    if not date_from:
        date_from = (today - timedelta(days=30)).isoformat()

    invoices = frappe.db.sql(
        """
        SELECT
            si.name,
            si.customer,
            si.customer_name,
            si.posting_date,
            si.grand_total,
            si.outstanding_amount,
            si.total_taxes_and_charges,
            si.status,
            si.docstatus,
            si.selling_price_list,
            si.remarks,
            si.owner,
            COALESCE(u.full_name, si.owner) AS seller_name,
            COALESCE(c.customer_group, '') AS customer_group,
            COALESCE(si.ve_sales_channel, '') AS ve_sales_channel,
            COALESCE(si.ve_payment_method, '') AS ve_payment_method,
            COALESCE(si.ve_igtf_amount, 0) AS ve_igtf_amount,
            COALESCE(si.cashea_order_id, '') AS cashea_order_id
        FROM `tabSales Invoice` si
        LEFT JOIN `tabUser` u ON u.name = si.owner
        LEFT JOIN `tabCustomer` c ON c.name = si.customer
        WHERE si.docstatus = 1
          AND si.posting_date BETWEEN %(date_from)s AND %(date_to)s
        ORDER BY si.posting_date ASC
        """,
        {"date_from": date_from, "date_to": date_to},
        as_dict=True,
    )

    invoice_items = frappe.db.sql(
        """
        SELECT
            sii.item_code,
            sii.item_name,
            sii.qty,
            sii.amount
        FROM `tabSales Invoice Item` sii
        INNER JOIN `tabSales Invoice` si ON si.name = sii.parent
        WHERE si.docstatus = 1
          AND si.posting_date BETWEEN %(date_from)s AND %(date_to)s
        """,
        {"date_from": date_from, "date_to": date_to},
        as_dict=True,
    )

    bills = []
    if frappe.db.exists("DocType", "Cima Bill"):
        bills = frappe.get_all(
            "Cima Bill",
            filters={"bill_date": ["between", [date_from, date_to]]},
            fields=["name", "bill_title", "bill_category", "bill_group", "bill_date", "amount", "status"],
            limit_page_length=2000,
        )

    delivery_notes = frappe.db.sql(
        """
        SELECT
            name,
            customer,
            customer_name,
            posting_date,
            grand_total,
            per_billed,
            status,
            docstatus
        FROM `tabDelivery Note`
        WHERE docstatus = 1
          AND per_billed < 100
          AND posting_date BETWEEN %(date_from)s AND %(date_to)s
        ORDER BY posting_date ASC
        """,
        {"date_from": date_from, "date_to": date_to},
        as_dict=True,
    )

    return build_executive_report(
        invoices=invoices,
        bills=bills,
        delivery_notes=delivery_notes,
        invoice_items=invoice_items,
        date_from=date_from,
        date_to=date_to,
    )


@whitelist()
def get_executive_report(date_from: str = "", date_to: str = "") -> dict:
    """Devuelve el reporte ejecutivo completo para el período indicado."""
    return _fetch_report_data(date_from=date_from, date_to=date_to)


def _render_report_pdf_html(report: dict) -> str:
    kpis = report["kpis"]
    period = report["period"]

    channel_rows = "".join(
        f"<tr><td>{c['channel']}</td><td style='text-align:right'>{c['count']}</td><td style='text-align:right'><strong>${c['total']:,.2f}</strong></td></tr>"
        for c in report["sales_by_channel"]
    )
    pm_rows = "".join(
        f"<tr><td>{p['payment_method']}</td><td style='text-align:right'>{p['count']}</td><td style='text-align:right'><strong>${p['total']:,.2f}</strong></td></tr>"
        for p in report["sales_by_payment_method"]
    )
    seller_rows = "".join(
        f"""<tr>
            <td><strong>{s['seller']}</strong></td>
            <td style='text-align:right'>{s['invoice_count']}</td>
            <td style='text-align:right'>${s['detal_sales']:,.2f}</td>
            <td style='text-align:right'>${s['mayor_sales']:,.2f}</td>
            <td style='text-align:right'>${s['meta_ads_sales']:,.2f}</td>
            <td style='text-align:right'>${s['avg_ticket']:,.2f}</td>
            <td style='text-align:right'><strong>${s['total_sales']:,.2f}</strong> ({s['share_pct']}%)</td>
        </tr>"""
        for s in report["sellers_summary"]
    )
    pending_rows = "".join(
        f"""<tr>
            <td>{n['doctype']}</td>
            <td>{n['name']}</td>
            <td>{n['customer']}</td>
            <td>{n['date']}</td>
            <td style='text-align:right'>${n['grand_total']:,.2f}</td>
            <td style='text-align:right;color:#b91c1c;'><strong>${n['pending_amount']:,.2f}</strong></td>
        </tr>"""
        for n in report["pending_delivery_notes"][:40]
    )
    expense_rows = "".join(
        f"<tr><td>{e['group']}</td><td style='text-align:right'>{e['count']}</td><td style='text-align:right'><strong>${e['total']:,.2f}</strong></td></tr>"
        for e in report["expenses_by_group"]
    )

    return f"""
    <!DOCTYPE html>
    <html>
    <head>
      <meta charset="utf-8">
      <style>
        body {{ font-family: Helvetica, Arial, sans-serif; color: #1c2532; font-size: 11px; margin: 20px; }}
        .header {{ background: #1c2532; color: #ffffff; padding: 16px 20px; border-radius: 8px; border-bottom: 4px solid #06c686; margin-bottom: 16px; }}
        .header h1 {{ margin: 0 0 4px; font-size: 18px; }}
        .header p {{ margin: 0; color: #cbd5e1; font-size: 11px; }}
        .kpi-table {{ width: 100%; border-collapse: separate; border-spacing: 8px; margin-bottom: 14px; }}
        .kpi-box {{ background: #f4f8f8; border: 1px solid #d9e6e5; border-left: 4px solid #00ada4; padding: 10px; border-radius: 6px; width: 25%; }}
        .kpi-lbl {{ font-size: 9px; text-transform: uppercase; color: #5c6b73; }}
        .kpi-val {{ font-size: 16px; font-weight: bold; margin-top: 4px; }}
        h3 {{ font-size: 13px; color: #119689; border-bottom: 1px solid #d9e6e5; padding-bottom: 4px; margin: 16px 0 8px; }}
        table.data {{ width: 100%; border-collapse: collapse; margin-bottom: 12px; }}
        table.data th {{ background: #1c2532; color: #ffffff; text-align: left; padding: 6px 8px; font-size: 10px; }}
        table.data td {{ border-bottom: 1px solid #e2e8f0; padding: 6px 8px; font-size: 10px; }}
      </style>
    </head>
    <body>
      <div class="header">
        <h1>CIMA Electronic VE — Reporte Ejecutivo Gerencial</h1>
        <p>Período: {period['date_from']} al {period['date_to']} | Generado automáticamente por Cima VE ERP</p>
      </div>

      <table class="kpi-table">
        <tr>
          <td class="kpi-box"><div class="kpi-lbl">Ingresos (Ventas)</div><div class="kpi-val">${kpis['total_revenue']:,.2f}</div></td>
          <td class="kpi-box"><div class="kpi-lbl">Gastos Totales</div><div class="kpi-val">${kpis['total_expenses']:,.2f}</div></td>
          <td class="kpi-box"><div class="kpi-lbl">Ganancia Neta</div><div class="kpi-val">${kpis['net_profit']:,.2f} ({kpis['profit_margin_pct']}%)</div></td>
          <td class="kpi-box"><div class="kpi-lbl">Notas / Fact. Pendientes</div><div class="kpi-val">${kpis['pending_notes_total']:,.2f} ({kpis['pending_notes_count']})</div></td>
        </tr>
      </table>

      <h3>1. Ventas por Canal (Detal / Mayor / Meta Ads)</h3>
      <table class="data">
        <thead><tr><th>Canal</th><th style="text-align:right">Facturas</th><th style="text-align:right">Total</th></tr></thead>
        <tbody>{channel_rows or '<tr><td colspan="3">Sin datos</td></tr>'}</tbody>
      </table>

      <h3>2. Ventas por Método de Pago</h3>
      <table class="data">
        <thead><tr><th>Método de Pago</th><th style="text-align:right">Operaciones</th><th style="text-align:right">Total</th></tr></thead>
        <tbody>{pm_rows or '<tr><td colspan="3">Sin datos</td></tr>'}</tbody>
      </table>

      <h3>3. Resumen por Vendedor</h3>
      <table class="data">
        <thead><tr><th>Vendedor</th><th style="text-align:right">Fact.</th><th style="text-align:right">Detal</th><th style="text-align:right">Mayor</th><th style="text-align:right">Meta Ads</th><th style="text-align:right">Ticket Prom.</th><th style="text-align:right">Total</th></tr></thead>
        <tbody>{seller_rows or '<tr><td colspan="7">Sin datos</td></tr>'}</tbody>
      </table>

      <h3>4. Notas de Entrega y Cuentas Pendientes por Pagar</h3>
      <table class="data">
        <thead><tr><th>Tipo</th><th>Documento</th><th>Cliente</th><th>Fecha</th><th style="text-align:right">Total</th><th style="text-align:right">Pendiente</th></tr></thead>
        <tbody>{pending_rows or '<tr><td colspan="6">Sin documentos pendientes</td></tr>'}</tbody>
      </table>

      <h3>5. Desglose de Gastos por Grupo</h3>
      <table class="data">
        <thead><tr><th>Grupo de Gasto</th><th style="text-align:right">Registros</th><th style="text-align:right">Total</th></tr></thead>
        <tbody>{expense_rows or '<tr><td colspan="3">Sin gastos registrados</td></tr>'}</tbody>
      </table>
    </body>
    </html>
    """


@whitelist()
def download_executive_report_pdf(date_from: str = "", date_to: str = "") -> None:
    """Genera y descarga el PDF del reporte ejecutivo."""
    import frappe
    from frappe.utils.pdf import get_pdf

    report = _fetch_report_data(date_from=date_from, date_to=date_to)
    html = _render_report_pdf_html(report)
    pdf_bytes = get_pdf(html)

    frappe.local.response.filename = f"Reporte_Ejecutivo_CIMA_{report['period']['date_from']}_{report['period']['date_to']}.pdf"
    frappe.local.response.filecontent = pdf_bytes
    frappe.local.response.type = "pdf"
