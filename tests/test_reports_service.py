import unittest

from cima_ve.services.reports_service import (
    build_executive_report,
    classify_sales_channel,
    extract_payment_method,
)


class ReportsServiceTests(unittest.TestCase):
    def test_classify_channels_and_payment_methods(self) -> None:
        self.assertEqual(classify_sales_channel({"ve_sales_channel": "Meta Ads"}), "Meta Ads")
        self.assertEqual(classify_sales_channel({"selling_price_list": "Mayor USD"}), "Mayor")
        self.assertEqual(classify_sales_channel({"selling_price_list": "Detal USD"}), "Detal")

        self.assertEqual(extract_payment_method({"cashea_order_id": "CSH-1"}), "Cashea")
        self.assertEqual(
            extract_payment_method({"remarks": "Factura rápida | Método: Pago Móvil / Bs"}),
            "Pago Móvil / Bs",
        )

    def test_build_executive_report_totals(self) -> None:
        invoices = [
            {
                "name": "SINV-001",
                "customer_name": "Juan",
                "posting_date": "2026-11-10",
                "grand_total": 200.0,
                "outstanding_amount": 0.0,
                "total_taxes_and_charges": 27.59,
                "ve_igtf_amount": 0.0,
                "ve_sales_channel": "Tienda / Detal",
                "ve_payment_method": "Cashea",
                "cashea_order_id": "CSH-10",
                "seller_name": "Carlos",
                "docstatus": 1,
            },
            {
                "name": "SINV-002",
                "customer_name": "Comercial XYZ",
                "posting_date": "2026-11-12",
                "grand_total": 500.0,
                "outstanding_amount": 100.0,
                "total_taxes_and_charges": 68.97,
                "ve_igtf_amount": 15.0,
                "ve_sales_channel": "Mayor",
                "ve_payment_method": "Contado USD",
                "seller_name": "Ana",
                "docstatus": 1,
            },
            {
                "name": "SINV-003",
                "customer_name": "Maria",
                "posting_date": "2026-11-12",
                "grand_total": 100.0,
                "outstanding_amount": 0.0,
                "ve_sales_channel": "Meta Ads",
                "ve_payment_method": "Pago Móvil / Bs",
                "seller_name": "Carlos",
                "docstatus": 1,
            },
        ]
        bills = [
            {"bill_group": "Operativos", "bill_date": "2026-11-11", "amount": 250.0, "status": "Pagada"},
        ]
        delivery_notes = [
            {
                "name": "DN-001",
                "customer_name": "Distribuidora Norte",
                "posting_date": "2026-11-14",
                "grand_total": 300.0,
                "per_billed": 0.0,
                "status": "To Bill",
                "docstatus": 1,
            }
        ]
        invoice_items = [
            {"item_code": "TV-55", "item_name": "TV 55", "qty": 2, "amount": 700.0},
        ]

        rep = build_executive_report(
            invoices=invoices,
            bills=bills,
            delivery_notes=delivery_notes,
            invoice_items=invoice_items,
            date_from="2026-11-01",
            date_to="2026-11-20",
        )
        self.assertEqual(rep["kpis"]["total_revenue"], 800.0)
        self.assertEqual(rep["kpis"]["total_expenses"], 250.0)
        self.assertEqual(rep["kpis"]["net_profit"], 550.0)
        self.assertEqual(rep["kpis"]["pending_notes_count"], 2)
        self.assertEqual(rep["kpis"]["pending_notes_total"], 400.0)
        self.assertEqual(len(rep["sellers_summary"]), 2)
        self.assertEqual(rep["top_products"][0]["item_code"], "TV-55")


if __name__ == "__main__":
    unittest.main()
