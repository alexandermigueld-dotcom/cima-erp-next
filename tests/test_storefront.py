import json
import pathlib
import unittest

from cima_ve.services.storefront_service import (
    DEFAULT_PRODUCT_IMAGE,
    build_payment_methods_catalog,
    calculate_storefront_totals,
    format_cashea_installments,
    normalize_rif_or_cedula,
    validate_registration_payload,
)


class StorefrontServiceTests(unittest.TestCase):
    def test_normalize_rif_or_cedula(self) -> None:
        self.assertEqual(normalize_rif_or_cedula(""), "")
        self.assertEqual(normalize_rif_or_cedula("v12345678"), "V-12345678")
        self.assertEqual(normalize_rif_or_cedula("j123456789"), "J-12345678-9")
        self.assertEqual(normalize_rif_or_cedula("19876543"), "V-19876543")

    def test_validate_registration_payload_optional_rif(self) -> None:
        ok = validate_registration_payload(
            email="Cliente@Ejemplo.com ",
            full_name="María Pérez",
            password="password123",
        )
        self.assertEqual(ok["email"], "cliente@ejemplo.com")
        self.assertEqual(ok["ve_rif_cedula"], "")
        self.assertEqual(ok["ve_taxpayer_type"], "No Contribuyente")

        with_rif = validate_registration_payload(
            email="empresa@cima.ve",
            full_name="Inversiones Cima",
            password="password123",
            ve_rif_cedula="j312345678",
            ve_taxpayer_type="Ordinario",
        )
        self.assertEqual(with_rif["ve_rif_cedula"], "J-31234567-8")
        self.assertEqual(with_rif["ve_taxpayer_type"], "Ordinario")

        with self.assertRaises(ValueError):
            validate_registration_payload("invalido", "Ana", "password123")
        with self.assertRaises(ValueError):
            validate_registration_payload("ana@cima.ve", "Ana", "123")

    def test_build_payment_methods_catalog_includes_all_methods(self) -> None:
        methods = build_payment_methods_catalog({"cashea_enabled": 1, "simulation_mode": 1})
        ids = [m["id"] for m in methods]
        self.assertEqual(
            ids,
            ["cashea", "google_pay", "pago_movil", "zelle", "binance_pay", "transferencia"],
        )

    def test_calculate_storefront_totals_igtf_and_cashea(self) -> None:
        items = [{"item_code": "AUD-A88", "item_name": "Audífonos", "qty": 2, "rate": 50.0}]

        cashea_totals = calculate_storefront_totals(items, payment_method="cashea")
        self.assertEqual(cashea_totals["taxable_base"], 100.0)
        self.assertEqual(cashea_totals["iva_amount"], 16.0)
        self.assertEqual(cashea_totals["igtf_amount"], 0.0)
        self.assertEqual(cashea_totals["grand_total"], 116.0)
        self.assertEqual(cashea_totals["cashea"]["down_payment_usd"], 46.4)
        self.assertEqual(cashea_totals["cashea"]["installment_usd"], 23.2)

        zelle_totals = calculate_storefront_totals(items, payment_method="zelle")
        self.assertTrue(zelle_totals["apply_igtf"])
        self.assertEqual(zelle_totals["igtf_amount"], 3.48)
        self.assertEqual(zelle_totals["grand_total"], 119.48)

    def test_format_cashea_installments(self) -> None:
        c = format_cashea_installments(100.0)
        self.assertEqual(c["down_payment_usd"], 40.0)
        self.assertEqual(c["installment_usd"], 20.0)
        self.assertEqual(c["installments"], 3)

    def test_storefront_files_and_placeholder_exist(self) -> None:
        root = pathlib.Path(__file__).resolve().parent.parent
        svg = root / "cima_ve" / "public" / "images" / "pending-product.svg"
        html = root / "cima_ve" / "www" / "tienda.html"
        py = root / "cima_ve" / "www" / "tienda.py"
        css = root / "cima_ve" / "public" / "css" / "tienda.css"
        js = root / "cima_ve" / "public" / "js" / "tienda.js"
        settings_json = root / "cima_ve" / "cima_ve" / "doctype" / "cima_ve_settings" / "cima_ve_settings.json"

        for p in (svg, html, py, css, js, settings_json):
            self.assertTrue(p.exists(), f"Missing expected storefront file: {p}")

        self.assertIn("Imagen pendiente por subir", svg.read_text(encoding="utf-8"))
        self.assertIn(DEFAULT_PRODUCT_IMAGE, js.read_text(encoding="utf-8"))
        self.assertIn("pay.google.com/gp/p/js/pay.js", html.read_text(encoding="utf-8"))

        settings = json.loads(settings_json.read_text(encoding="utf-8"))
        fieldnames = {f["fieldname"] for f in settings["fields"]}
        self.assertIn("storefront_warehouse", fieldnames)
        self.assertIn("google_pay_merchant_id", fieldnames)
        self.assertIn("pago_movil_info", fieldnames)


if __name__ == "__main__":
    unittest.main()
