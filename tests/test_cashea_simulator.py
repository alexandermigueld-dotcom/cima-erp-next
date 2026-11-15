import unittest

from cima_ve.services.cashea_client import CasheaClient


class TestCasheaSimulator(unittest.TestCase):
    def setUp(self) -> None:
        self.client = CasheaClient(simulation_mode=True, webhook_secret="test-secret")

    def test_create_simulated_order_splits_down_payment_and_installments(self) -> None:
        order = self.client.create_order(
            reference_id="SINV-001",
            amount_usd=200.0,
            customer_name="Cliente Prueba",
            customer_id_number="V-12345678",
        )
        self.assertTrue(order.is_simulated)
        self.assertTrue(order.order_id.startswith("CSH-SIM-"))
        self.assertEqual(order.down_payment_usd, 80.0)
        self.assertEqual(order.financed_amount_usd, 120.0)
        self.assertEqual(order.installments_count, 3)
        self.assertEqual(order.installment_amount_usd, 40.0)

    def test_simulated_webhook_signature_roundtrip(self) -> None:
        raw_body, sig = self.client.build_simulated_webhook(
            order_id="CSH-SIM-ABC123",
            reference_id="SINV-001",
            amount_usd=100.0,
        )
        event = self.client.parse_webhook(raw_body, sig)
        self.assertEqual(event.order_id, "CSH-SIM-ABC123")
        self.assertEqual(event.reference_id, "SINV-001")
        self.assertEqual(event.down_payment_usd, 40.0)

    def test_invalid_webhook_signature_raises_permission_error(self) -> None:
        raw_body, _ = self.client.build_simulated_webhook(
            order_id="CSH-SIM-ABC123",
            reference_id="SINV-001",
            amount_usd=100.0,
        )
        with self.assertRaises(PermissionError):
            self.client.parse_webhook(raw_body, "sha256=firma-falsa")

    def test_invalid_amount_raises_value_error(self) -> None:
        with self.assertRaises(ValueError):
            self.client.create_order(
                reference_id="SINV-001",
                amount_usd=0.0,
                customer_name="Cliente",
                customer_id_number="V-123",
            )


if __name__ == "__main__":
    unittest.main()
