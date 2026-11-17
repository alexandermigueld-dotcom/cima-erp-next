import json
import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from cima_ve.services.exchange_rate_service import (
    BRECHA_SOURCE_BINANCE,
    BRECHA_SOURCE_MANUAL,
    BRECHA_SOURCE_MONITOR,
    calculate_brecha_and_adjusted_rate,
    convert_usd_to_bs,
    parse_binance_p2p_ads,
)


class ExchangeRateServiceTests(unittest.TestCase):
    def test_brecha_binance_full_and_partial_factor(self) -> None:
        res_full = calculate_brecha_and_adjusted_rate(
            bcv_rate=45.0,
            monitor_rate=52.0,
            binance_rate=54.0,
            brecha_source=BRECHA_SOURCE_BINANCE,
            brecha_factor_pct=100.0,
        )
        self.assertEqual(res_full["raw_brecha_pct"], 20.0)
        self.assertEqual(res_full["applied_brecha_pct"], 20.0)
        self.assertEqual(res_full["adjusted_rate"], 54.0)

        res_half = calculate_brecha_and_adjusted_rate(
            bcv_rate=45.0,
            monitor_rate=52.0,
            binance_rate=54.0,
            brecha_source=BRECHA_SOURCE_BINANCE,
            brecha_factor_pct=50.0,
        )
        self.assertEqual(res_half["raw_brecha_pct"], 20.0)
        self.assertEqual(res_half["applied_brecha_pct"], 10.0)
        self.assertEqual(res_half["adjusted_rate"], 49.5)

    def test_brecha_monitor_and_manual(self) -> None:
        res_mon = calculate_brecha_and_adjusted_rate(
            bcv_rate=40.0,
            monitor_rate=50.0,
            binance_rate=54.0,
            brecha_source=BRECHA_SOURCE_MONITOR,
            brecha_factor_pct=100.0,
        )
        self.assertEqual(res_mon["raw_brecha_pct"], 25.0)
        self.assertEqual(res_mon["adjusted_rate"], 50.0)

        res_man = calculate_brecha_and_adjusted_rate(
            bcv_rate=40.0,
            monitor_rate=50.0,
            binance_rate=54.0,
            brecha_source=BRECHA_SOURCE_MANUAL,
            manual_brecha_pct=15.0,
        )
        self.assertEqual(res_man["applied_brecha_pct"], 15.0)
        self.assertEqual(res_man["adjusted_rate"], 46.0)

    def test_parse_binance_p2p_ads_trimmed_median(self) -> None:
        payload = {
            "data": [
                {"adv": {"price": "40.0"}},
                {"adv": {"price": "53.8"}},
                {"adv": {"price": "54.0"}},
                {"adv": {"price": "54.2"}},
                {"adv": {"price": "70.0"}},
            ]
        }
        self.assertEqual(parse_binance_p2p_ads(payload), 54.0)
        self.assertEqual(convert_usd_to_bs(25.0, 54.0), 1350.0)

    def test_settings_and_hooks_wired(self) -> None:
        root = pathlib.Path(__file__).resolve().parent.parent
        hooks_py = (root / "cima_ve" / "hooks.py").read_text(encoding="utf-8")
        self.assertIn("cima_ve.api.exchange_rates.sync_exchange_rates_job", hooks_py)

        settings_json = json.loads(
            (root / "cima_ve" / "cima_ve" / "doctype" / "cima_ve_settings" / "cima_ve_settings.json").read_text(
                encoding="utf-8"
            )
        )
        fieldnames = {f["fieldname"] for f in settings_json["fields"]}
        for expected in (
            "fx_auto_sync",
            "fx_brecha_source",
            "fx_brecha_factor_pct",
            "fx_bcv_rate",
            "fx_monitor_rate",
            "fx_binance_usdt_rate",
            "fx_brecha_pct",
            "fx_adjusted_rate",
            "fx_sync_now",
        ):
            self.assertIn(expected, fieldnames)


if __name__ == "__main__":
    unittest.main()
