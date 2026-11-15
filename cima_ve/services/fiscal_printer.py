from __future__ import annotations

import hashlib
import json
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone


@dataclass(slots=True)
class FiscalInvoiceItem:
    item_code: str
    description: str
    qty: float
    unit_price: float
    is_exempt: bool = False

    @property
    def subtotal(self) -> float:
        return round(self.qty * self.unit_price, 2)


@dataclass(slots=True)
class FiscalTaxBreakdown:
    taxable_base: float
    exempt_base: float
    iva_rate: float
    iva_amount: float
    igtf_rate: float
    igtf_amount: float
    total_before_igtf: float
    grand_total: float

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(slots=True)
class FiscalInvoicePayload:
    invoice_name: str
    customer_name: str
    customer_rif_cedula: str
    currency: str
    items: list[FiscalInvoiceItem]
    apply_igtf: bool = False
    iva_rate: float = 16.0
    igtf_rate: float = 3.0


@dataclass(slots=True)
class FiscalStampResult:
    invoice_name: str
    control_number: str
    fiscal_invoice_number: str
    status: str
    pdf_url: str
    qr_hash: str
    tax_breakdown: FiscalTaxBreakdown
    issued_at: str
    is_simulated: bool
    raw_response: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        data = asdict(self)
        data["tax_breakdown"] = self.tax_breakdown.to_dict()
        return data


def calculate_venezuela_taxes(
    items: list[FiscalInvoiceItem],
    apply_igtf: bool = False,
    iva_rate: float = 16.0,
    igtf_rate: float = 3.0,
) -> FiscalTaxBreakdown:
    if not items:
        raise ValueError("La factura fiscal debe contener al menos un ítem.")

    taxable_base = round(sum(i.subtotal for i in items if not i.is_exempt), 2)
    exempt_base = round(sum(i.subtotal for i in items if i.is_exempt), 2)
    iva_amount = round(taxable_base * (iva_rate / 100.0), 2)
    total_before_igtf = round(taxable_base + exempt_base + iva_amount, 2)
    igtf_amount = round(total_before_igtf * (igtf_rate / 100.0), 2) if apply_igtf else 0.0
    grand_total = round(total_before_igtf + igtf_amount, 2)

    return FiscalTaxBreakdown(
        taxable_base=taxable_base,
        exempt_base=exempt_base,
        iva_rate=iva_rate,
        iva_amount=iva_amount,
        igtf_rate=igtf_rate if apply_igtf else 0.0,
        igtf_amount=igtf_amount,
        total_before_igtf=total_before_igtf,
        grand_total=grand_total,
    )


class FiscalPrinterClient:
    """Cliente para Imprenta Digital autorizada por el SENIAT.

    En `simulation_mode=True` genera números de control, numeración fiscal,
    hash QR y URL de factura digital simulados pero consistentes con el
    formato fiscal venezolano.
    """

    def __init__(
        self,
        api_url: str = "",
        api_token: str = "",
        series_prefix: str = "00",
        simulation_mode: bool = True,
    ) -> None:
        self.api_url = api_url.rstrip("/")
        self.api_token = api_token
        self.series_prefix = series_prefix or "00"
        self.simulation_mode = simulation_mode or not (self.api_url and self.api_token)

    def issue_digital_invoice(
        self,
        payload: FiscalInvoicePayload,
        sequence_seed: int | None = None,
    ) -> FiscalStampResult:
        if not payload.customer_rif_cedula.strip():
            raise ValueError("El RIF o Cédula del cliente es obligatorio para facturar fiscalmente.")

        taxes = calculate_venezuela_taxes(
            items=payload.items,
            apply_igtf=payload.apply_igtf,
            iva_rate=payload.iva_rate,
            igtf_rate=payload.igtf_rate,
        )
        now_iso = datetime.now(timezone.utc).isoformat()

        if self.simulation_mode:
            digest = hashlib.sha256(
                f"{payload.invoice_name}|{payload.customer_rif_cedula}|{taxes.grand_total}".encode("utf-8")
            ).hexdigest()
            seq = sequence_seed if sequence_seed is not None else (int(digest[:6], 16) % 900000 + 100000)
            control_number = f"{self.series_prefix}-{seq:08d}"
            fiscal_number = f"FAC-SIM-{seq:08d}"
            pdf_url = f"https://simulador.imprenta-seniat.local/docs/{control_number}.pdf"
            qr_hash = f"SENIAT-SIM-{digest[:24].upper()}"
            raw = {
                "simulated": True,
                "control_number": control_number,
                "fiscal_invoice_number": fiscal_number,
                "customer_rif_cedula": payload.customer_rif_cedula,
                "taxes": taxes.to_dict(),
            }
            return FiscalStampResult(
                invoice_name=payload.invoice_name,
                control_number=control_number,
                fiscal_invoice_number=fiscal_number,
                status="Simulada",
                pdf_url=pdf_url,
                qr_hash=qr_hash,
                tax_breakdown=taxes,
                issued_at=now_iso,
                is_simulated=True,
                raw_response=raw,
            )

        request_body = {
            "invoice_reference": payload.invoice_name,
            "customer": {
                "name": payload.customer_name,
                "tax_id": payload.customer_rif_cedula,
            },
            "currency": payload.currency,
            "items": [
                {
                    "code": item.item_code,
                    "description": item.description,
                    "qty": item.qty,
                    "unit_price": item.unit_price,
                    "exempt": item.is_exempt,
                }
                for item in payload.items
            ],
            "taxes": taxes.to_dict(),
        }
        req = urllib.request.Request(
            f"{self.api_url}/invoices/stamp",
            data=json.dumps(request_body).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self.api_token}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=25) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"Error HTTP Imprenta Digital ({exc.code}): {detail}") from exc

        return FiscalStampResult(
            invoice_name=payload.invoice_name,
            control_number=str(data["control_number"]),
            fiscal_invoice_number=str(data.get("fiscal_invoice_number", "")),
            status="Timbrada",
            pdf_url=str(data.get("pdf_url", "")),
            qr_hash=str(data.get("qr_hash", "")),
            tax_breakdown=taxes,
            issued_at=str(data.get("issued_at", now_iso)),
            is_simulated=False,
            raw_response=data,
        )
