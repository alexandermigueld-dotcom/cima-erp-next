import unittest

from cima_ve.services.fiscal_printer import (
    FiscalInvoiceItem,
    FiscalInvoicePayload,
    FiscalPrinterClient,
    calculate_venezuela_taxes,
)


class TestFiscalSimulator(unittest.TestCase):
    def setUp(self) -> None:
        self.client = FiscalPrinterClient(series_prefix="00", simulation_mode=True)

    def test_calculate_iva_and_igtf_with_exempt_item(self) -> None:
        items = [
            FiscalInvoiceItem("A", "Producto Gravado", qty=1, unit_price=100.0, is_exempt=False),
            FiscalInvoiceItem("B", "Producto Exento", qty=1, unit_price=50.0, is_exempt=True),
        ]
        taxes = calculate_venezuela_taxes(items, apply_igtf=True, iva_rate=16.0, igtf_rate=3.0)
        self.assertEqual(taxes.taxable_base, 100.0)
        self.assertEqual(taxes.exempt_base, 50.0)
        self.assertEqual(taxes.iva_amount, 16.0)
        self.assertEqual(taxes.total_before_igtf, 166.0)
        self.assertEqual(taxes.igtf_amount, 4.98)
        self.assertEqual(taxes.grand_total, 170.98)

    def test_issue_simulated_digital_invoice(self) -> None:
        payload = FiscalInvoicePayload(
            invoice_name="SINV-2026-0001",
            customer_name="Comercial Cima",
            customer_rif_cedula="J-12345678-9",
            currency="USD",
            items=[FiscalInvoiceItem("P1", "Inversor", qty=2, unit_price=50.0)],
            apply_igtf=False,
            seller_user="vendedor1@cima.ve",
            seller_name="María Pérez",
        )
        result = self.client.issue_digital_invoice(payload, sequence_seed=42)
        self.assertTrue(result.is_simulated)
        self.assertEqual(result.status, "Simulada")
        self.assertEqual(result.control_number, "00-00000042")
        self.assertEqual(result.fiscal_invoice_number, "FAC-SIM-00000042")
        self.assertEqual(result.tax_breakdown.iva_amount, 16.0)
        self.assertEqual(result.tax_breakdown.grand_total, 116.0)
        self.assertTrue(result.qr_hash.startswith("SENIAT-SIM-"))
        self.assertEqual(result.raw_response["seller"]["user"], "vendedor1@cima.ve")
        self.assertEqual(result.raw_response["seller"]["name"], "María Pérez")

    def test_missing_rif_raises_value_error(self) -> None:
        payload = FiscalInvoicePayload(
            invoice_name="SINV-2026-0002",
            customer_name="Sin RIF",
            customer_rif_cedula="   ",
            currency="USD",
            items=[FiscalInvoiceItem("P1", "Cable", qty=1, unit_price=10.0)],
        )
        with self.assertRaises(ValueError):
            self.client.issue_digital_invoice(payload)


if __name__ == "__main__":
    unittest.main()
