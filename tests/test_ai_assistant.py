from __future__ import annotations

import base64
import io
import json
import pathlib
import sys
import unittest
import zipfile
from unittest.mock import patch

from cima_ve.services.assistant_service import (
    build_provider_request,
    extract_provider_text,
    fetch_public_repository_context,
    parse_inventory_upload,
    prepare_inventory_import,
)


class AssistantServiceTests(unittest.TestCase):
    def test_only_structured_product_proposals_supply_safe_prefill_fields(self) -> None:
        from cima_ve.services.assistant_service import parse_assistant_response

        reply = json.dumps({"answer": "Revisa el borrador.", "product_draft": {
            "item_name": " Cargador USB-C ", "item_code": "C-65", "description": "65 W",
            "initial_qty": 100, "show_in_website": True, "detal_price": 50,
        }})
        self.assertEqual(parse_assistant_response(f"```json\n{reply}\n```"), {
            "answer": "Revisa el borrador.",
            "product_draft": {"item_name": "Cargador USB-C", "item_code": "C-65", "description": "65 W"},
        })
        self.assertEqual(parse_assistant_response("Hay 20 productos."), {"answer": "Hay 20 productos."})
        self.assertEqual(parse_assistant_response('{"answer":"Informe","product_draft":{"item_name":true}}'), {"answer": "Informe"})
        self.assertEqual(parse_assistant_response('{"answer":"Informe","product_draft":null}'), {"answer": "Informe"})

    def test_csv_import_maps_spanish_headers_and_defaults_to_no_stock_or_website(self) -> None:
        content = "Nombre,SKU,Cantidad inicial,Costo,Publicar\nCargador USB-C,chg-01,0,8,\n".encode("utf-8-sig")
        rows = parse_inventory_upload("productos.csv", base64.b64encode(content).decode("ascii"))
        self.assertEqual(rows[0]["item_name"], "Cargador USB-C")
        self.assertEqual(rows[0]["item_code"], "chg-01")

        preview = prepare_inventory_import(rows, "")
        self.assertFalse(preview["has_errors"])
        self.assertEqual(preview["products"][0]["item_code"], "CHG-01")
        self.assertEqual(preview["products"][0]["initial_qty"], 0)
        self.assertFalse(preview["products"][0]["show_in_website"])
        self.assertEqual(preview["products"][0]["cost_rate"], 8)
        self.assertEqual(preview["rows"][0]["description"], preview["products"][0]["description"])

        semicolon_csv = "Nombre;SKU;Cantidad\nAudífonos;aud-2;2\n".encode("utf-8")
        semicolon_rows = parse_inventory_upload("productos.csv", base64.b64encode(semicolon_csv).decode("ascii"))
        self.assertEqual(semicolon_rows[0]["item_code"], "aud-2")
        self.assertEqual(semicolon_rows[0]["initial_qty"], "2")

    def test_import_rejects_duplicate_skus_and_requires_warehouse_for_initial_quantity(self) -> None:
        duplicate_rows = [
            {"item_name": "Cable A", "item_code": "sku-1"},
            {"item_name": "Cable B", "item_code": "SKU-1"},
        ]
        duplicate_preview = prepare_inventory_import(duplicate_rows)
        self.assertTrue(duplicate_preview["has_errors"])
        self.assertEqual(duplicate_preview["products"], [])
        self.assertIn("repetido", duplicate_preview["rows"][1]["errors"][0])

        existing_preview = prepare_inventory_import([{"item_name": "Cable", "item_code": "sku-2"}], existing_item_codes={"SKU-2"})
        self.assertIn("ya existe", existing_preview["rows"][0]["errors"][0])

        stock_preview = prepare_inventory_import([{"item_name": "Cable", "initial_qty": "3"}])
        self.assertIn("almacén", stock_preview["rows"][0]["errors"][0])

    def test_xlsx_upload_reads_first_sheet_and_enforces_file_type_and_size(self) -> None:
        main_ns = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
        workbook = (
            '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
            'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
            '<sheets><sheet name="Products" sheetId="1" r:id="rId1"/></sheets></workbook>'
        )
        relationships = (
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" Target="worksheets/sheet1.xml" '
            'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet"/>'
            '</Relationships>'
        )
        sheet = (
            f'<worksheet xmlns="{main_ns}"><sheetData>'
            '<row r="1"><c r="A1" t="inlineStr"><is><t>Nombre</t></is></c>'
            '<c r="B1" t="inlineStr"><is><t>SKU</t></is></c>'
            '<c r="C1" t="inlineStr"><is><t>Cantidad</t></is></c></row>'
            '<row r="2"><c r="A2" t="inlineStr"><is><t>Audífonos</t></is></c>'
            '<c r="B2" t="inlineStr"><is><t>aud-1</t></is></c>'
            '<c r="C2"><v>12</v></c></row>'
            '</sheetData></worksheet>'
        )
        file_buffer = io.BytesIO()
        with zipfile.ZipFile(file_buffer, "w", zipfile.ZIP_DEFLATED) as workbook_zip:
            workbook_zip.writestr("[Content_Types].xml", "<Types/>")
            workbook_zip.writestr("xl/workbook.xml", workbook)
            workbook_zip.writestr("xl/_rels/workbook.xml.rels", relationships)
            workbook_zip.writestr("xl/worksheets/sheet1.xml", sheet)

        encoded = base64.b64encode(file_buffer.getvalue()).decode("ascii")
        rows = parse_inventory_upload("productos.xlsx", encoded)
        self.assertEqual(rows[0]["item_name"], "Audífonos")
        self.assertEqual(rows[0]["initial_qty"], "12")
        with self.assertRaises(ValueError):
            parse_inventory_upload("productos.xls", encoded)
        with self.assertRaises(ValueError):
            parse_inventory_upload("productos.csv", base64.b64encode(b"x" * (4 * 1024 * 1024 + 1)).decode("ascii"))

    def test_provider_requests_use_fixed_hosts_and_keep_keys_out_of_payload(self) -> None:
        endpoints = {
            "OpenAI": "api.openai.com",
            "Anthropic": "api.anthropic.com",
            "Gemini": "generativelanguage.googleapis.com",
        }
        for provider, hostname in endpoints.items():
            with self.subTest(provider=provider):
                url, headers, payload = build_provider_request(
                    provider,
                    "test-model",
                    "test-secret",
                    "private system prompt",
                    [{"role": "user", "content": "Hi"}],
                )
                self.assertIn(hostname, url)
                self.assertNotIn("test-secret", json.dumps(payload))
                self.assertTrue(any("test-secret" in value for value in headers.values()))

        with self.assertRaises(ValueError):
            build_provider_request("openai", "https://evil.test", "key", "system", [{"role": "user", "content": "x"}])
        self.assertEqual(
            extract_provider_text("gemini", {"candidates": [{"content": {"parts": [{"text": "Respuesta"}]}}]}),
            "Respuesta",
        )

    def test_repository_context_fetches_only_allowlisted_public_docs(self) -> None:
        urls = []

        def fake_fetch(url: str) -> str:
            urls.append(url)
            return f"contenido de {url.rsplit('/', 1)[-1]}"

        context = fetch_public_repository_context(fake_fetch)
        self.assertEqual(len(urls), 3)
        self.assertTrue(all(url.startswith("https://raw.githubusercontent.com/josephnowak/cima-erp-next/main/") for url in urls))
        self.assertEqual([url.rsplit("/", 1)[-1] for url in urls], ["README.md", "CONTEXT.md", "AGENTS.md"])
        self.assertIn("README.md", context)
        self.assertNotIn(".env", " ".join(urls))


class AssistantPermissionAndWiringTests(unittest.TestCase):
    def test_business_context_uses_bound_filters_and_never_selects_customer_details(self) -> None:
        from cima_ve.api import ai_assistant

        class FakeMeta:
            def __init__(self, fields):
                self.fields = set(fields)

            def has_field(self, fieldname):
                return fieldname in self.fields

        class FakeDB:
            def __init__(self):
                self.calls = []

            def sql(self, query, params, as_dict=False):
                self.calls.append((query, params))
                if "COUNT(DISTINCT b.item_code)" in query:
                    return [
                        {"stock_uom": "Nos", "items_with_bin": 3, "total_on_hand": 9},
                        {"stock_uom": "Unit", "items_with_bin": 1, "total_on_hand": 3},
                    ]
                if "SELECT i.item_code" in query:
                    return [{"item_code": "SKU-123", "item_name": "Producto", "actual_qty": 2}]
                if "INNER JOIN `tabPayment Entry Reference`" in query:
                    return [{"currency": "USD", "seller_user": "seller@example.test", "collected_amount": 10}]
                if "FROM `tabSales Invoice` si" in query:
                    return [{"currency": "USD", "seller_user": "seller@example.test", "billed_total": 20}]
                if "FROM `tabDelivery Note` dn" in query and "SELECT dn.name" in query:
                    return [{"name": "DN-0001", "seller_user": "seller@example.test", "status": "Pendiente"}]
                return [{"currency": "USD", "seller_user": "seller@example.test", "note_count": 1}]

        fake_db = FakeDB()

        class FakeFrappe:
            db = fake_db

            @staticmethod
            def get_meta(doctype):
                fields = {"ve_vendedor_usuario", "ve_ne_estado", "ve_ne_monto_total", "ve_ne_costo_total", "ve_ne_margen_ganancia", "ve_ne_comision_monto", "ve_ne_monto_pagado", "ve_ne_saldo_pendiente"}
                return FakeMeta(fields)

            @staticmethod
            def get_all(doctype, **kwargs):
                return [{"name": "seller@example.test", "full_name": "Seller"}]

        with patch.dict(sys.modules, {"frappe": FakeFrappe}):
            context = ai_assistant._build_business_context(
                "2026-01-01",
                "2026-01-31",
                "seller@example.test",
                "WH-1",
                "Company-1",
                "SKU-123'); DROP TABLE tabItem",
            )

        context_text = json.dumps(context)
        self.assertIn("collections_by_payment_entry_date", context_text)
        self.assertIn("delivery_notes_by_dispatch_date", context_text)
        self.assertIn("quantities_by_stock_uom", context_text)
        self.assertNotIn("total_on_hand", context["inventory"])
        self.assertIn("seller_name", context_text)
        self.assertNotIn("customer_name", context_text)
        self.assertNotIn("Payment proof", context_text)
        self.assertTrue(all("DROP TABLE" not in query for query, _ in fake_db.calls))
        self.assertTrue(any("2026-01-01" in params.values() for _, params in fake_db.calls))

    def test_every_assistant_endpoint_requires_system_manager(self) -> None:
        from cima_ve.api import ai_assistant

        class FakePermissionError(Exception):
            pass

        class FakeFrappe:
            PermissionError = FakePermissionError

            class session:
                user = "seller@example.test"

            @staticmethod
            def only_for(role):
                raise FakePermissionError(role)

            @staticmethod
            def throw(message, exc=Exception):
                raise exc(message)

        calls = [
            (ai_assistant.get_assistant_bootstrap, {}),
            (ai_assistant.ask_assistant, {"message": "consulta"}),
            (ai_assistant.test_assistant_connection, {}),
            (ai_assistant.preview_inventory_import, {"filename": "a.csv", "file_data_base64": "eA=="}),
            (ai_assistant.confirm_inventory_import, {"token": "a" * 40}),
        ]
        with patch.dict(sys.modules, {"frappe": FakeFrappe}):
            for endpoint, kwargs in calls:
                with self.subTest(endpoint=endpoint.__name__), self.assertRaises(FakePermissionError):
                    endpoint(**kwargs)

    def test_page_settings_and_workspace_are_admin_only_and_connected(self) -> None:
        root = pathlib.Path(__file__).resolve().parent.parent
        page_path = root / "cima_ve" / "cima_ve" / "page" / "asistente_cima"
        page = json.loads((page_path / "asistente_cima.json").read_text(encoding="utf-8"))
        self.assertEqual(page["name"], "asistente-cima")
        self.assertEqual({role["role"] for role in page["roles"]}, {"System Manager"})

        settings = json.loads((root / "cima_ve" / "cima_ve" / "doctype" / "cima_ve_settings" / "cima_ve_settings.json").read_text(encoding="utf-8"))
        fields = {field["fieldname"]: field for field in settings["fields"]}
        self.assertEqual(fields["assistant_openai_api_key"]["fieldtype"], "Password")
        self.assertEqual(fields["assistant_anthropic_api_key"]["fieldtype"], "Password")
        self.assertEqual(fields["assistant_gemini_api_key"]["fieldtype"], "Password")
        self.assertEqual(fields["assistant_enabled"]["default"], "0")

        workspace = json.loads((root / "cima_ve" / "fixtures" / "workspace.json").read_text(encoding="utf-8"))
        admin_workspace = next(row for row in workspace if row["name"] == "Administración Cima")
        self.assertIn("System Manager", {role["role"] for role in admin_workspace["roles"]})
        self.assertIn("asistente-cima", {shortcut["link_to"] for shortcut in admin_workspace["shortcuts"]})


if __name__ == "__main__":
    unittest.main()