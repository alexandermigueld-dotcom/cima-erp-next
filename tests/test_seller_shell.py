from __future__ import annotations

import json
import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parent.parent / "cima_ve"


class SellerShellTests(unittest.TestCase):
    def test_hooks_register_shell_and_role_home(self) -> None:
        hooks = (ROOT / "hooks.py").read_text(encoding="utf-8")
        self.assertIn("seller_shell.js", hooks)
        self.assertIn("seller_shell.css", hooks)
        self.assertIn('"Sales User": "vendedor"', hooks)

    def test_manifest_and_icons(self) -> None:
        manifest = json.loads((ROOT / "public" / "manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest["start_url"], "/vendedor")
        self.assertEqual(manifest["display"], "standalone")
        for icon in manifest["icons"]:
            name = icon["src"].rsplit("/", 1)[-1]
            self.assertTrue((ROOT / "public" / "images" / name).exists(), name)

    def test_shell_js_limits_non_admin_routes_and_avoids_floating_overlay(self) -> None:
        js = (ROOT / "public" / "js" / "seller_shell.js").read_text(encoding="utf-8")
        css = (ROOT / "public" / "css" / "seller_shell.css").read_text(encoding="utf-8")
        self.assertIn('"venta-rapida", "notas-entrega"', js)
        self.assertIn("System Manager", js)
        self.assertIn("cima-seller-mode", js)
        self.assertIn("cima-seller-tabs", js)
        self.assertIn("cima-seller-user-btn", js)
        self.assertIn("cima-seller-user-menu", js)
        self.assertIn("openSellerProfileDialog", js)
        self.assertIn("logoutSeller", js)
        self.assertIn("cima-admin-pos-btn", js)
        self.assertIn("cima-home-shortcuts", js)
        self.assertIn("cima-page-pos-btn", js)
        self.assertIn("#page-desktop", js)
        self.assertIn("frappe-mobile-nav", css)
        self.assertNotIn("position: fixed", css)

    def test_vendedor_page_redirects(self) -> None:
        py = (ROOT / "www" / "vendedor.py").read_text(encoding="utf-8")
        self.assertIn("/app/venta-rapida", py)
        self.assertIn("/login?redirect-to=/vendedor", py)


if __name__ == "__main__":
    unittest.main()
