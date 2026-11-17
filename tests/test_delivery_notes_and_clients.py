import json
import pathlib
import unittest

from cima_ve.services.client_consumption_service import compute_client_consumption
from cima_ve.services.delivery_note_service import (
    append_payment_history,
    compute_delivery_note_settlement_totals,
    compute_partial_payment_state,
    summarize_delivery_notes,
)


class DeliveryNotesAndClientConsumptionTests(unittest.TestCase):
    def test_delivery_note_settlement_totals_iva_and_igtf(self) -> None:
        no_tax = compute_delivery_note_settlement_totals(100.0, apply_iva=False, apply_igtf=False)
        self.assertEqual(no_tax["iva_amount"], 0.0)
        self.assertEqual(no_tax["igtf_amount"], 0.0)
        self.assertEqual(no_tax["grand_total"], 100.0)

        iva_only = compute_delivery_note_settlement_totals(100.0, apply_iva=True, apply_igtf=False)
        self.assertEqual(iva_only["iva_amount"], 16.0)
        self.assertEqual(iva_only["grand_total"], 116.0)

        iva_and_igtf = compute_delivery_note_settlement_totals(100.0, apply_iva=True, apply_igtf=True)
        self.assertEqual(iva_and_igtf["iva_amount"], 16.0)
        self.assertEqual(iva_and_igtf["igtf_amount"], 3.48)
        self.assertEqual(iva_and_igtf["grand_total"], 119.48)

    def test_summarize_delivery_notes(self) -> None:
        notes = [
            {"name": "DN-1", "docstatus": 1, "ve_ne_estado": "Pendiente", "grand_total": 50.0},
            {"name": "DN-2", "docstatus": 1, "ve_ne_estado": "Pagada", "ve_ne_factura": "SINV-1", "grand_total": 116.0},
            {"name": "DN-3", "docstatus": 2, "ve_ne_estado": "Cancelada", "grand_total": 30.0},
        ]
        res = summarize_delivery_notes(notes)
        self.assertEqual(res["summary"]["total_count"], 3)
        self.assertEqual(res["summary"]["pending_count"], 1)
        self.assertEqual(res["summary"]["pending_total"], 50.0)
        self.assertEqual(res["summary"]["paid_count"], 1)
        self.assertEqual(res["summary"]["paid_total"], 116.0)
        self.assertEqual(res["summary"]["cancelled_count"], 1)
        self.assertEqual(res["summary"]["cancelled_total"], 30.0)

    def test_partial_payment_state_and_history(self) -> None:
        first = compute_partial_payment_state(116.0, 0.0, 50.0)
        self.assertEqual(first["estado"], "Pago Parcial")
        self.assertEqual(first["payment_amount"], 50.0)
        self.assertEqual(first["new_paid_total"], 50.0)
        self.assertEqual(first["new_remaining"], 66.0)
        self.assertFalse(first["is_fully_paid"])

        second = compute_partial_payment_state(116.0, 50.0, 66.0)
        self.assertEqual(second["estado"], "Pagada")
        self.assertEqual(second["new_paid_total"], 116.0)
        self.assertEqual(second["new_remaining"], 0.0)
        self.assertTrue(second["is_fully_paid"])

        with self.assertRaises(ValueError):
            compute_partial_payment_state(116.0, 50.0, 0.0)
        with self.assertRaises(ValueError):
            compute_partial_payment_state(116.0, 50.0, 70.0)

        hist_list, hist_json = append_payment_history("", {"amount": 50.0, "method": "Zelle"})
        hist_list2, _ = append_payment_history(hist_json, {"amount": 66.0, "method": "Contado USD"})
        self.assertEqual(len(hist_list), 1)
        self.assertEqual(len(hist_list2), 2)

    def test_summarize_delivery_notes_with_partial_payments(self) -> None:
        notes = [
            {"name": "DN-1", "docstatus": 1, "ve_ne_estado": "Pendiente", "grand_total": 50.0},
            {
                "name": "DN-2",
                "docstatus": 1,
                "ve_ne_estado": "Pago Parcial",
                "ve_ne_factura": "SINV-2",
                "ve_ne_monto_total": 100.0,
                "ve_ne_monto_pagado": 40.0,
                "ve_ne_saldo_pendiente": 60.0,
                "grand_total": 100.0,
            },
        ]
        res = summarize_delivery_notes(notes)
        self.assertEqual(res["summary"]["pending_count"], 2)
        self.assertEqual(res["summary"]["partial_count"], 1)
        self.assertEqual(res["summary"]["pending_total"], 110.0)
        self.assertEqual(res["summary"]["paid_total"], 40.0)
        self.assertEqual(res["notes"][1]["remaining_amount"], 60.0)

    def test_compute_client_consumption_with_per_seller_split(self) -> None:
        invoices = [
            {
                "name": "SINV-1",
                "customer": "CUST-1",
                "customer_name": "Cliente Alfa",
                "posting_date": "2026-11-10",
                "grand_total": 100.0,
                "paid_amount": 100.0,
                "outstanding_amount": 0.0,
                "total_qty": 2,
                "seller_user": "vendedor1@cima.ve",
                "seller_name": "Juan Pérez",
            },
            {
                "name": "SINV-2",
                "customer": "CUST-1",
                "customer_name": "Cliente Alfa",
                "posting_date": "2026-11-12",
                "grand_total": 300.0,
                "paid_amount": 300.0,
                "outstanding_amount": 0.0,
                "total_qty": 5,
                "seller_user": "vendedor2@cima.ve",
                "seller_name": "María Gómez",
            },
        ]
        dns = [
            {
                "name": "DN-10",
                "customer": "CUST-1",
                "customer_name": "Cliente Alfa",
                "posting_date": "2026-11-15",
                "grand_total": 75.0,
                "seller_user": "vendedor1@cima.ve",
                "seller_name": "Juan Pérez",
            }
        ]
        meta = {"CUST-1": {"ve_rif_cedula": "J-12345678-9"}}
        res = compute_client_consumption(invoices, delivery_notes=dns, customer_meta=meta)
        self.assertEqual(res["summary"]["total_customers"], 1)
        self.assertEqual(res["summary"]["total_consumed"], 400.0)
        self.assertEqual(res["summary"]["total_pending_dn"], 75.0)

        client = res["clients"][0]
        self.assertEqual(client["rif_cedula"], "J-12345678-9")
        self.assertEqual(len(client["by_seller"]), 2)
        self.assertEqual(client["by_seller"][0]["seller_name"], "María Gómez")
        self.assertEqual(client["by_seller"][0]["total_amount"], 300.0)
        self.assertEqual(client["by_seller"][0]["share_pct"], 75.0)
        self.assertEqual(client["by_seller"][1]["seller_name"], "Juan Pérez")
        self.assertEqual(client["by_seller"][1]["total_amount"], 100.0)
        self.assertEqual(client["by_seller"][1]["pending_dn_amount"], 75.0)

    def test_pages_and_fixtures_markers_present(self) -> None:
        root = pathlib.Path(__file__).resolve().parent.parent
        ne_js = (root / "cima_ve" / "cima_ve" / "page" / "notas_entrega" / "notas_entrega.js").read_text(encoding="utf-8")
        cc_js = (root / "cima_ve" / "cima_ve" / "page" / "clientes_consumo" / "clientes_consumo.js").read_text(encoding="utf-8")
        vr_js = (root / "cima_ve" / "cima_ve" / "page" / "venta_rapida" / "venta_rapida.js").read_text(encoding="utf-8")
        ws = json.loads((root / "cima_ve" / "fixtures" / "workspace.json").read_text(encoding="utf-8"))

        self.assertIn("mark_delivery_note_paid", ne_js)
        self.assertIn("paid_amount", ne_js)
        self.assertIn("Pago Parcial", ne_js)
        self.assertIn("cancel_delivery_note", ne_js)
        self.assertIn("get_client_consumption", cc_js)
        self.assertIn("create_quick_delivery_note", vr_js)
        self.assertIn("EMITIR NOTA DE ENTREGA", vr_js)

        seller_links = {s["link_to"] for s in ws[0]["shortcuts"]}
        admin_links = {s["link_to"] for s in ws[1]["shortcuts"]}
        self.assertEqual(seller_links, {"venta-rapida"})
        self.assertIn("notas-entrega", admin_links)
        self.assertIn("clientes-consumo", admin_links)
        self.assertIn("metricas-ventas", admin_links)


if __name__ == "__main__":
    unittest.main()
