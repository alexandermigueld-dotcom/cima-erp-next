from frappe.model.document import Document

from cima_ve.services.exchange_rate_service import (
    BRECHA_SOURCE_BINANCE,
    calculate_brecha_and_adjusted_rate,
)


class CimaVESettings(Document):
    def validate(self):
        if self.meta.has_field("fx_bcv_rate"):
            calc = calculate_brecha_and_adjusted_rate(
                bcv_rate=float(self.get("fx_bcv_rate") or 0.0),
                monitor_rate=float(self.get("fx_monitor_rate") or 0.0),
                binance_rate=float(self.get("fx_binance_usdt_rate") or 0.0),
                brecha_source=(self.get("fx_brecha_source") or BRECHA_SOURCE_BINANCE).strip(),
                brecha_factor_pct=float(
                    self.get("fx_brecha_factor_pct")
                    if self.get("fx_brecha_factor_pct") is not None
                    else 100.0
                ),
                manual_brecha_pct=float(self.get("fx_manual_brecha_pct") or 0.0),
            )
            if self.meta.has_field("fx_brecha_pct"):
                self.fx_brecha_pct = calc["applied_brecha_pct"]
            if self.meta.has_field("fx_adjusted_rate"):
                self.fx_adjusted_rate = calc["adjusted_rate"]
