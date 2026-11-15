import json
import pathlib
import unittest

from cima_ve.services.sales_metrics_service import compute_sales_metrics


class SalesMetricsServiceTests(unittest.TestCase):
    def test_empty_invoices(self) -> None:
        res = compute_sales_metrics([])
        self.assertEqual(res["summary"]["total_sales"], 0.0)
        self.assertEqual(res["summary"]["invoice_count"], 0)
        self.assertEqual(res["summary"]["unique_sellers"], 0)
        self.assertEqual(res["by_user"], [])

    def test_compute_sales_metrics_splits_by_user_and_calculates_kpis(self) -> None:
        invoices = [
            {
                "name": "SINV-0001",
                "posting_date": "2026-11-14",
                "seller_user": "ana@cima.ve",
                "seller_name": "Ana Gómez",
                "customer": "CUST-1",
                "customer_name": "Cliente Uno",
                "canal_venta": "Detal",
                "grand_total": 300.0,
                "net_total": 250.0,
                "total_taxes_and_charges": 50.0,
                "ve_igtf_amount": 9.0,
                "paid_amount": 300.0,
                "outstanding_amount": 0.0,
                "ve_fiscal_status": "Timbrada",
                "ve_numero_control": "00-000001",
                "cashea_order_id": "CAS-1",
                "cashea_status": "Aprobada",
                "total_qty": 3,
                "currency": "USD",
            },
            {
                "name": "SINV-0002",
                "posting_date": "2026-11-15",
                "seller_user": "ana@cima.ve",
                "seller_name": "Ana Gómez",
                "customer": "CUST-2",
                "customer_name": "Cliente Dos",
                "canal_venta": "Mayor",
                "grand_total": 100.0,
                "net_total": 86.21,
                "total_taxes_and_charges": 13.79,
                "ve_igtf_amount": 0.0,
                "paid_amount": 50.0,
                "outstanding_amount": 50.0,
                "ve_fiscal_status": "Simulada",
                "ve_numero_control": "00-000002",
                "total_qty": 5,
                "currency": "USD",
            },
            {
                "name": "SINV-0003",
                "posting_date": "2026-11-15",
                "seller_user": "luis@cima.ve",
                "seller_name": "Luis Díaz",
                "customer": "CUST-1",
                "customer_name": "Cliente Uno",
                "canal_venta": "Detal",
                "grand_total": 100.0,
                "net_total": 86.21,
                "total_taxes_and_charges": 13.79,
                "ve_igtf_amount": 0.0,
                "paid_amount": 100.0,
                "outstanding_amount": 0.0,
                "ve_fiscal_status": "Pendiente",
                "total_qty": 2,
                "currency": "USD",
            },
        ]
        items = [
            {"parent": "SINV-0001", "item_code": "TV-55", "item_name": "TV 55", "qty": 2, "amount": 250.0},
            {"parent": "SINV-0002", "item_code": "TV-55", "item_name": "TV 55", "qty": 1, "amount": 86.21},
            {"parent": "SINV-0003", "item_code": "CABLE-1", "item_name": "Cable HDMI", "qty": 2, "amount": 86.21},
        ]

        res = compute_sales_metrics(invoices, items)
        summary = res["summary"]
        self.assertEqual(summary["total_sales"], 500.0)
        self.assertEqual(summary["invoice_count"], 3)
        self.assertEqual(summary["unique_sellers"], 2)
        self.assertEqual(summary["unique_customers"], 2)
        self.assertEqual(summary["total_qty"], 10.0)
        self.assertEqual(summary["paid_amount"], 450.0)
        self.assertEqual(summary["outstanding_amount"], 50.0)
        self.assertEqual(summary["fiscal_stamped_count"], 2)
        self.assertEqual(summary["cashea_count"], 1)
        self.assertEqual(summary["cashea_total"], 300.0)
        self.assertAlmostEqual(summary["avg_ticket"], 166.67, places=2)

        by_user = res["by_user"]
        self.assertEqual(len(by_user), 2)
        self.assertEqual(by_user[0]["user"], "ana@cima.ve")
        self.assertEqual(by_user[0]["total_sales"], 400.0)
        self.assertEqual(by_user[0]["share_pct"], 80.0)
        self.assertEqual(by_user[0]["invoice_count"], 2)
        self.assertEqual(by_user[0]["unique_customers"], 2)
        self.assertEqual(by_user[0]["avg_ticket"], 200.0)

        self.assertEqual(by_user[1]["user"], "luis@cima.ve")
        self.assertEqual(by_user[1]["total_sales"], 100.0)
        self.assertEqual(by_user[1]["share_pct"], 20.0)

        self.assertEqual(res["top_items"][0]["item_code"], "TV-55")
        self.assertEqual(res["top_items"][0]["invoice_count"], 2)
        self.assertEqual(res["top_customers"][0]["customer"], "CUST-1")
        self.assertEqual(res["top_customers"][0]["total_sales"], 400.0)

    def test_metricas_ventas_page_files_valid(self) -> None:
        root = pathlib.Path(__file__).resolve().parent.parent
        page_dir = root / "cima_ve" / "cima_ve" / "page" / "metricas_ventas"
        page_json = json.loads((page_dir / "metricas_ventas.json").read_text(encoding="utf-8"))
        self.assertEqual(page_json["page_name"], "metricas-ventas")
        self.assertEqual(page_json["module"], "Cima VE")
        js_text = (page_dir / "metricas_ventas.js").read_text(encoding="utf-8")
        self.assertIn("cima_ve.api.sales_metrics.get_sales_metrics", js_text)
        self.assertIn("cm-by-user-body", js_text)


if __name__ == "__main__":
    unittest.main()
