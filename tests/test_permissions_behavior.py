from __future__ import annotations

import sys
import types
import unittest
from contextlib import contextmanager


class FakePermissionError(Exception):
    pass


def make_fake_frappe(roles: list[str], user: str = "seller@x.com", allow_doc: bool = True):
    fk = types.ModuleType("frappe")
    fk.PermissionError = FakePermissionError
    fk.session = types.SimpleNamespace(user=user)
    fk.calls = []

    def only_for(role):
        allowed = [role] if isinstance(role, str) else list(role)
        if not set(allowed) & set(roles):
            raise FakePermissionError("not permitted")

    def has_permission(doctype, ptype=None, doc=None, throw=False, **kw):
        fk.calls.append(("has_permission", doctype, ptype))
        if not allow_doc:
            if throw:
                raise FakePermissionError("no doc permission")
            return False
        return True

    def throw(msg, exc=None):
        raise (exc or Exception)(msg)

    class FakeDoc:
        customer = "C"
        customer_name = "C"
        items: list = []
        grand_total = 1

        def db_set(self, *a, **k):
            fk.calls.append(("db_set", a))

    fk.only_for = only_for
    fk.has_permission = has_permission
    fk.throw = throw
    fk.get_doc = lambda *a, **k: FakeDoc()
    fk.whitelist = lambda *a, **k: (lambda fn: fn)
    fk.__path__ = []
    utils = types.ModuleType("frappe.utils")
    utils.now_datetime = lambda: "now"
    utils.flt = float
    utils.cint = int
    utils.nowdate = lambda: "today"
    utils.today = lambda: "today"
    utils.getdate = lambda *a, **k: None
    fk.utils = utils
    return fk


@contextmanager
def patched_frappe(fake):
    previous = {k: sys.modules.get(k) for k in ("frappe", "frappe.utils")}
    sys.modules["frappe"] = fake
    sys.modules["frappe.utils"] = fake.utils
    try:
        yield
    finally:
        for k, v in previous.items():
            if v is None:
                sys.modules.pop(k, None)
            else:
                sys.modules[k] = v


class AdminOnlyEndpointTests(unittest.TestCase):
    def test_seller_cannot_cancel_or_settle_or_calculate_commissions(self) -> None:
        from cima_ve.api import delivery_notes as dn

        with patched_frappe(make_fake_frappe(["Sales User"])):
            with self.assertRaises(FakePermissionError):
                dn.cancel_delivery_note("MAT-DN-1")
            with self.assertRaises(FakePermissionError):
                dn.mark_delivery_note_paid("MAT-DN-1", "Efectivo")
            with self.assertRaises(FakePermissionError):
                dn.calculate_seller_commissions()

    def test_seller_cannot_read_admin_reports(self) -> None:
        from cima_ve.api import client_consumption, sales_metrics

        with patched_frappe(make_fake_frappe(["Sales User"])):
            with self.assertRaises(FakePermissionError):
                sales_metrics.get_sales_metrics()
            with self.assertRaises(FakePermissionError):
                client_consumption.get_client_consumption()


class CasheaAndFiscalPermissionTests(unittest.TestCase):
    def test_create_cashea_checkout_requires_doc_permission(self) -> None:
        from cima_ve.api import cashea

        with patched_frappe(make_fake_frappe(["Sales User"], allow_doc=False)):
            with self.assertRaises(FakePermissionError):
                cashea.create_cashea_checkout("SINV-1")

    def test_stamp_sales_invoice_requires_doc_permission(self) -> None:
        from cima_ve.api import fiscal

        with patched_frappe(make_fake_frappe(["Sales User"], allow_doc=False)):
            with self.assertRaises(FakePermissionError):
                fiscal.stamp_sales_invoice("SINV-1")

    def test_webhook_rejects_when_secret_missing_and_not_simulation(self) -> None:
        from cima_ve.api import cashea

        fk = make_fake_frappe([])

        class Settings:
            simulation_mode = 0
            cashea_api_url = ""
            cashea_api_key = ""
            cashea_webhook_secret = ""

        fk.get_single = lambda name: Settings()
        with patched_frappe(fk):
            with self.assertRaises(FakePermissionError):
                cashea.webhook()

    def test_client_without_secret_never_verifies_signature(self) -> None:
        from cima_ve.services.cashea_client import CasheaClient

        client = CasheaClient(webhook_secret="")
        self.assertFalse(client.verify_webhook_signature(b"{}", "sha256=abc"))
        sim = CasheaClient()
        body, sig = b"{}", None
        sig = "sha256=" + sim.sign_payload(body)
        self.assertTrue(sim.verify_webhook_signature(body, sig))


if __name__ == "__main__":
    unittest.main()
