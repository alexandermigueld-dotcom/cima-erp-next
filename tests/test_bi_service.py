import unittest
from datetime import date

from cima_ve.services.bi_service import (
    analyze_inventory_intelligence,
    build_weekly_stockout_email_html,
)


class BiServiceTests(unittest.TestCase):
    def test_china_lead_time_stockout_and_reorder_calculation(self) -> None:
        items = [
            {
                "item_code": "ITEM-FAST",
                "item_name": "Cargador Rápido 65W",
                "item_group": "Accesorios",
                "stock_qty": 30,
                "incoming_qty": 0,
                "valuation_rate": 8.0,
                "standard_rate": 20.0,
            },
            {
                "item_code": "ITEM-SLOW",
                "item_name": "Cable VGA 5m",
                "item_group": "Cables",
                "stock_qty": 50,
                "incoming_qty": 0,
                "valuation_rate": 3.0,
                "standard_rate": 8.0,
            },
        ]
        sales_rows = [
            {"item_code": "ITEM-FAST", "qty": 90, "amount": 1800.0},  # 1/day over 90d -> 30d left < 45d China
        ]
        res = analyze_inventory_intelligence(
            items=items,
            sales_rows=sales_rows,
            china_lead_time_days=45,
            safety_stock_days=15,
            analysis_window_days=90,
            reorder_cycle_days=30,
            today=date(2026, 11, 20),
        )
        self.assertEqual(res["kpis"]["critical_count"], 1)
        self.assertEqual(res["kpis"]["dead_stock_count"], 1)
        crit = res["critical_items"][0]
        self.assertEqual(crit["item_code"], "ITEM-FAST")
        self.assertTrue(crit["will_stockout_before_china"])
        self.assertEqual(crit["days_until_stockout"], 30.0)
        # Target = 90 days * 1/day = 90; current stock = 30 -> order 60
        self.assertEqual(crit["recommended_order_qty"], 60)

        email_html = build_weekly_stockout_email_html(res)
        self.assertIn("Cargador Rápido 65W", email_html)
        self.assertIn("45 días", email_html)


if __name__ == "__main__":
    unittest.main()
