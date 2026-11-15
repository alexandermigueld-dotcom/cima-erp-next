import json

from cima_ve.services.cashea_client import CasheaClient
from cima_ve.services.fiscal_printer import (
    FiscalInvoiceItem,
    FiscalInvoicePayload,
    FiscalPrinterClient,
)


def main() -> int:
    print("=== 1. SIMULACIÓN DE CHECKOUT CON CASHEA ===")
    cashea = CasheaClient(simulation_mode=True)
    order = cashea.create_order(
        reference_id="SINV-SIM-0001",
        amount_usd=150.00,
        customer_name="María Pérez",
        customer_id_number="V-18456789",
        items=[
            {"code": "PROD-001", "name": "Regulador de Voltaje", "qty": 1, "rate": 100.0},
            {"code": "PROD-002", "name": "Cable HDMI 4K", "qty": 2, "rate": 25.0},
        ],
    )
    print(json.dumps(order.to_dict(), indent=2, ensure_ascii=False))

    print("\n=== 2. SIMULACIÓN DE WEBHOOK DE APROBACIÓN CASHEA ===")
    raw_webhook, signature = cashea.build_simulated_webhook(
        order_id=order.order_id,
        reference_id=order.reference_id,
        amount_usd=order.amount_usd,
        down_payment_usd=order.down_payment_usd,
    )
    event = cashea.parse_webhook(raw_webhook, signature)
    print(
        f"Webhook verificado -> Orden: {event.order_id} | Estado: {event.status} "
        f"| Inicial pagada: ${event.down_payment_usd:.2f}"
    )

    print("\n=== 3. SIMULACIÓN DE IMPRENTA FISCAL DIGITAL (SENIAT) ===")
    fiscal = FiscalPrinterClient(series_prefix="00", simulation_mode=True)
    payload = FiscalInvoicePayload(
        invoice_name="SINV-SIM-0001",
        customer_name="María Pérez",
        customer_rif_cedula="V-18456789",
        currency="USD",
        items=[
            FiscalInvoiceItem("PROD-001", "Regulador de Voltaje", qty=1, unit_price=100.0, is_exempt=False),
            FiscalInvoiceItem("PROD-002", "Cable HDMI 4K", qty=2, unit_price=25.0, is_exempt=False),
        ],
        apply_igtf=True,
    )
    stamp = fiscal.issue_digital_invoice(payload, sequence_seed=14582)
    print(json.dumps(stamp.to_dict(), indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
