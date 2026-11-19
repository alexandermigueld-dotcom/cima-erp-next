from __future__ import annotations

import json
import pathlib
import sys
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from cima_ve.services.product_service import (
    normalize_item_code,
    validate_new_product_input,
    validate_stock_batch_input,
)


class ProductServiceTests(unittest.TestCase):
    def test_normalize_item_code(self) -> None:
        self.assertEqual(normalize_item_code(" carg usb 20w ", "Ignored"), "CARG-USB-20W")
        self.assertEqual(normalize_item_code("", "Cargador Rápido Tipo-C 20W"), "CARGADOR-RAPIDO-TIPO-C-20W")
        self.assertEqual(normalize_item_code("", ""), "")

    def test_validate_new_product_input(self) -> None:
        cleaned = validate_new_product_input(
            {
                "item_name": "Audífonos Bluetooth Pro",
                "item_code": "",
                "item_group": "Accesorios",
                "stock_uom": "Nos",
                "cost_rate": "8.5",
                "detal_price": "15",
                "mayor_price": "12",
                "initial_qty": "25",
                "warehouse": "Almacén Principal White Point - CEV",
                "show_in_website": 1,
            }
        )
        self.assertEqual(cleaned["item_code"], "AUDIFONOS-BLUETOOTH-PRO")
        self.assertEqual(cleaned["cost_rate"], 8.5)
        self.assertEqual(cleaned["detal_price"], 15.0)
        self.assertEqual(cleaned["mayor_price"], 12.0)
        self.assertEqual(cleaned["initial_qty"], 25.0)
        self.assertTrue(cleaned["show_in_website"])

        with self.assertRaises(ValueError):
            validate_new_product_input({"item_name": ""})
        with self.assertRaises(ValueError):
            validate_new_product_input({"item_name": "Cable", "initial_qty": 5, "warehouse": ""})
        with self.assertRaises(ValueError):
            validate_new_product_input({"item_name": "Cable", "detal_price": -1})

    def test_validate_stock_batch_input(self) -> None:
        rows = validate_stock_batch_input(
            [
                {"item_code": "SKU-1", "qty": "10", "incoming_rate": "4.5", "detal_price": "9.0"},
                {"item_code": "SKU-2", "qty": 5, "incoming_rate": 0},
            ],
            "Almacén Principal White Point - CEV",
        )
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["qty"], 10.0)
        self.assertEqual(rows[0]["incoming_rate"], 4.5)
        self.assertEqual(rows[0]["detal_price"], 9.0)
        self.assertIsNone(rows[1]["mayor_price"])

        with self.assertRaises(ValueError):
            validate_stock_batch_input(rows, "")
        with self.assertRaises(ValueError):
            validate_stock_batch_input([], "Almacén Principal White Point - CEV")
        with self.assertRaises(ValueError):
            validate_stock_batch_input([{"item_code": "SKU-1", "qty": 0}], "Almacén Principal White Point - CEV")


class ProductLoaderWiringAndPermissionTests(unittest.TestCase):
    def test_sales_user_blocked_from_product_loader_api(self) -> None:
        from cima_ve.api import products as products_api

        class FakePermissionError(Exception):
            pass

        class FakeFrappe:
            PermissionError = FakePermissionError

            class session:
                user = "vendedor@cima.com"

            @staticmethod
            def throw(msg, exc=Exception):
                raise exc(msg)

            @staticmethod
            def only_for(roles):
                raise FakePermissionError("not allowed")

        sys.modules["frappe"] = FakeFrappe
        try:
            with self.assertRaises(FakePermissionError):
                products_api.get_product_loader_bootstrap()
            with self.assertRaises(FakePermissionError):
                products_api.preview_quick_product(product='{"item_name":"Test"}')
            with self.assertRaises(FakePermissionError):
                products_api.create_quick_product(item_name="Test")
            with self.assertRaises(FakePermissionError):
                products_api.add_stock_batch(items=[], warehouse="WH")
        finally:
            del sys.modules["frappe"]

    def test_product_preview_normalizes_sku_and_rejects_duplicates_without_writes(self) -> None:
        from cima_ve.api.products import preview_quick_product

        def throw(message):
            raise ValueError(message)

        exists = Mock(return_value=False)
        frappe = SimpleNamespace(
            session=SimpleNamespace(user="admin"), only_for=Mock(), throw=throw,
            db=SimpleNamespace(exists=exists), get_doc=Mock(),
        )
        product = '{"item_name":"Cable rápido","show_in_website":0}'
        with patch.dict(sys.modules, {"frappe": frappe}):
            result = preview_quick_product(product)
            self.assertEqual(result["item_code"], "CABLE-RAPIDO")
            self.assertFalse(result["show_in_website"])
            exists.assert_called_once_with("Item", "CABLE-RAPIDO")
            exists.return_value = True
            with self.assertRaisesRegex(ValueError, "ya existe"):
                preview_quick_product(product)
        frappe.get_doc.assert_not_called()

    def test_page_workspace_and_navigation_wiring(self) -> None:
        root = pathlib.Path(__file__).resolve().parent.parent
        page_dir = root / "cima_ve" / "cima_ve" / "page" / "carga_productos"
        page_json = json.loads((page_dir / "carga_productos.json").read_text(encoding="utf-8"))
        self.assertEqual(page_json["name"], "carga-productos")
        roles = {r["role"] for r in page_json["roles"]}
        self.assertIn("System Manager", roles)
        self.assertNotIn("Sales User", roles)

        js_text = (page_dir / "carga_productos.js").read_text(encoding="utf-8")
        self.assertIn("create_quick_product", js_text)
        self.assertIn("add_stock_batch", js_text)
        self.assertIn("update_product_quick_details", js_text)

        ws_text = (root / "cima_ve" / "fixtures" / "workspace.json").read_text(encoding="utf-8")
        self.assertIn("carga-productos", ws_text)
        self.assertIn("Carga de Productos y Lotes", ws_text)

        vr_js = (root / "cima_ve" / "cima_ve" / "page" / "venta_rapida" / "venta_rapida.js").read_text(encoding="utf-8")
        self.assertIn("open-product-loader", vr_js)
        self.assertIn('frappe.set_route("carga-productos")', vr_js)

    def test_search_products_for_batch_avoids_missing_item_website_image_column(self) -> None:
        from cima_ve.api import products as products_api

        captured_queries: list[str] = []

        class FakeMeta:
            def has_field(self, fieldname: str) -> bool:
                return fieldname != "website_image"

        class FakeDB:
            @staticmethod
            def table_exists(doctype: str) -> bool:
                return doctype == "Website Item"

            @staticmethod
            def sql(query: str, params: dict, as_dict: bool = True) -> list[dict]:
                captured_queries.append(query)
                return [{"item_code": "SKU-1", "item_name": "Test", "website_image": "/files/a.png"}]

        class FakeFrappe:
            PermissionError = Exception
            db = FakeDB()

            class session:
                user = "admin@cima.com"

            @staticmethod
            def only_for(roles):
                return None

            @staticmethod
            def get_all(*args, **kwargs):
                return ["Detal USD", "Mayor"]

            @staticmethod
            def get_meta(doctype: str):
                return FakeMeta()

        sys.modules["frappe"] = FakeFrappe
        try:
            rows = products_api.search_products_for_batch(query="Test", warehouse="WH-1")
            self.assertEqual(len(rows), 1)
            self.assertEqual(len(captured_queries), 1)
            self.assertNotRegex(captured_queries[0], r"\bi\.website_image\b")
            self.assertIn("LEFT JOIN `tabWebsite Item` wi", captured_queries[0])
            self.assertIn("MAX(wi.website_image)", captured_queries[0])
        finally:
            del sys.modules["frappe"]


if __name__ == "__main__":
    unittest.main()
