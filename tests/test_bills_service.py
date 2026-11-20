import unittest

from cima_ve.services.bills_service import (
    summarize_bills,
    validate_bill_category_input,
    validate_bill_input,
)


class BillsServiceTests(unittest.TestCase):
    def test_validate_bill_category_and_fallback_group(self) -> None:
        cat = validate_bill_category_input("Alquiler Local", "Operativos", "Renta mensual")
        self.assertEqual(cat.category_name, "Alquiler Local")
        self.assertEqual(cat.parent_group, "Operativos")

        cat_other = validate_bill_category_input("Varios", "Grupo Inexistente")
        self.assertEqual(cat_other.parent_group, "Otros")

        with self.assertRaises(ValueError):
            validate_bill_category_input("")

    def test_validate_bill_input_rejects_invalid(self) -> None:
        with self.assertRaises(ValueError):
            validate_bill_input("", "Alquiler", "2026-11-20", 100)
        with self.assertRaises(ValueError):
            validate_bill_input("Pago Luz", "", "2026-11-20", 100)
        with self.assertRaises(ValueError):
            validate_bill_input("Pago Luz", "Servicios", "2026-11-20", 0)
        with self.assertRaises(ValueError):
            validate_bill_input("Pago Luz", "Servicios", "2026-11-20", 50, status="Desconocido")

    def test_summarize_bills_groups_and_ignores_cancelled(self) -> None:
        bills = [
            {
                "bill_title": "Renta Nov",
                "bill_category": "Alquiler",
                "bill_group": "Operativos",
                "amount": 500.0,
                "payment_method": "Contado USD",
                "status": "Pagada",
            },
            {
                "bill_title": "Campaña IG",
                "bill_category": "Meta Ads",
                "bill_group": "Marketing y Meta Ads",
                "amount": 150.0,
                "payment_method": "Zelle",
                "status": "Pendiente",
            },
            {
                "bill_title": "Factura Anulada",
                "bill_category": "Alquiler",
                "bill_group": "Operativos",
                "amount": 999.0,
                "payment_method": "Contado USD",
                "status": "Anulada",
            },
        ]
        summary = summarize_bills(bills)
        self.assertEqual(summary["total_count"], 2)
        self.assertEqual(summary["total_paid"], 500.0)
        self.assertEqual(summary["total_pending"], 150.0)
        self.assertEqual(summary["total_spent"], 650.0)
        self.assertEqual(summary["by_group"][0]["group"], "Operativos")


if __name__ == "__main__":
    unittest.main()
