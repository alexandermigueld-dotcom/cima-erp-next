import json
import pathlib
import unittest

from cima_ve.services.client_consumption_service import compute_client_consumption
from cima_ve.services.delivery_note_service import (
    append_payment_history,
    compute_delivery_note_discounts,
    compute_delivery_note_settlement_totals,
    compute_partial_payment_state,
    is_cash_payment_method,
    parse_auto_discount_tiers,
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
        self.assertIn("ne-payment-screenshot", ne_js)
        self.assertIn("screenshot_url", ne_js)
        self.assertIn("cancel_delivery_note", ne_js)
        self.assertIn("get_client_consumption", cc_js)
        self.assertIn("create_quick_delivery_note", vr_js)
        self.assertIn("cima-enable-discount", vr_js)
        self.assertIn("cima-discount-pct", vr_js)
        self.assertIn("EMITIR NOTA DE ENTREGA", vr_js)

        seller_links = {s["link_to"] for s in ws[0]["shortcuts"]}
        admin_links = {s["link_to"] for s in ws[1]["shortcuts"]}
        self.assertEqual(seller_links, {"venta-rapida", "notas-entrega"})
        self.assertIn("notas-entrega", admin_links)
        self.assertIn("clientes-consumo", admin_links)
        self.assertIn("metricas-ventas", admin_links)

    def test_auto_and_manual_delivery_note_discounts(self) -> None:
        tiers = parse_auto_discount_tiers(None)
        self.assertEqual(len(tiers), 3)

        # Under $100 -> 0% auto, optional 10% manual on $40 -> $36.00
        d40 = compute_delivery_note_discounts(40.0, auto_discount_enabled=True, tiers=tiers)
        self.assertEqual(d40["auto_discount_pct"], 0.0)
        self.assertEqual(d40["final_total"], 40.0)
        self.assertFalse(d40["has_global_discount"])

        d40_manual = compute_delivery_note_discounts(
            40.0,
            auto_discount_enabled=True,
            tiers=tiers,
            manual_discount_enabled=True,
            manual_discount_percentage=10.0,
        )
        self.assertEqual(d40_manual["manual_discount_pct"], 10.0)
        self.assertEqual(d40_manual["manual_discount_amount"], 4.0)
        self.assertEqual(d40_manual["final_total"], 36.0)
        self.assertTrue(d40_manual["has_global_discount"])

        # Between $500 and $1,000 -> 4.76%
        d600 = compute_delivery_note_discounts(600.0, auto_discount_enabled=True, tiers=tiers)
        self.assertEqual(d600["auto_discount_pct"], 4.76)
        self.assertEqual(d600["auto_discount_amount"], 28.56)
        self.assertEqual(d600["final_total"], 571.44)

        # Over $1,000 -> 9.09%
        d1200 = compute_delivery_note_discounts(1200.0, auto_discount_enabled=True, tiers=tiers)
        self.assertEqual(d1200["auto_discount_pct"], 9.09)
        self.assertEqual(d1200["auto_discount_amount"], 109.08)
        self.assertEqual(d1200["final_total"], 1090.92)

        # Custom configurable tier added in settings
        custom_tiers = parse_auto_discount_tiers(
            json.dumps([{"label": "Mayorista > 2000", "min_amount": 2000, "max_amount": None, "discount_percentage": 15}])
        )
        d2500 = compute_delivery_note_discounts(2500.0, auto_discount_enabled=True, tiers=custom_tiers)
        self.assertEqual(d2500["auto_discount_pct"], 15.0)
        self.assertEqual(d2500["final_total"], 2125.0)

    def test_cash_payment_method_detection(self) -> None:
        self.assertTrue(is_cash_payment_method("Efectivo USD"))
        self.assertTrue(is_cash_payment_method("Efectivo Bs"))
        self.assertTrue(is_cash_payment_method("Cash"))
        self.assertFalse(is_cash_payment_method("Pago Móvil / Bs"))
        self.assertFalse(is_cash_payment_method("Zelle"))
        self.assertFalse(is_cash_payment_method("Cashea"))

    def test_non_admin_delivery_notes_access_and_scoping(self) -> None:
        root = pathlib.Path(__file__).resolve().parent.parent
        dn_api = (root / "cima_ve" / "api" / "delivery_notes.py").read_text(encoding="utf-8")
        ne_json = json.loads((root / "cima_ve" / "cima_ve" / "page" / "notas_entrega" / "notas_entrega.json").read_text(encoding="utf-8"))
        ne_js = (root / "cima_ve" / "cima_ve" / "page" / "notas_entrega" / "notas_entrega.js").read_text(encoding="utf-8")
        vr_js = (root / "cima_ve" / "cima_ve" / "page" / "venta_rapida" / "venta_rapida.js").read_text(encoding="utf-8")

        # create_quick_delivery_note bypasses Custom DocPerm restriction on Delivery Note for Sales User
        self.assertIn("doc.flags.ignore_permissions = True", dn_api)
        self.assertIn("doc.insert(ignore_permissions=True)", dn_api)

        # get_delivery_notes scopes non-admin users to their own records only
        self.assertIn('is_admin = "System Manager" in frappe.get_roles(current_user)', dn_api)
        self.assertIn("if not is_admin:", dn_api)
        self.assertIn('params["current_user"] = current_user', dn_api)

        # notas-entrega page allows Sales User and Sales Manager
        roles = {r["role"] for r in ne_json.get("roles", [])}
        self.assertTrue({"Sales User", "Sales Manager", "System Manager"}.issubset(roles))

        # notas_entrega.js hides admin controls for non-admins
        self.assertIn("applyRoleUi()", ne_js)
        self.assertIn("Mis Notas de Entrega", ne_js)
        self.assertIn("Solo lectura", ne_js)

        # venta_rapida.js exposes Notas de Entrega button to all sellers, keeping metrics/clients admin-only
        self.assertIn('data-action="open-delivery-notes">\n\t\t\t\t\t\t\tNotas de Entrega', vr_js)
        self.assertIn('data-action="open-client-consumption" data-admin-only="1"', vr_js)
        self.assertIn('data-action="open-metrics" data-admin-only="1"', vr_js)


if __name__ == "__main__":
    unittest.main()
