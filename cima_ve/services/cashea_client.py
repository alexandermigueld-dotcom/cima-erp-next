from __future__ import annotations

import hashlib
import hmac
import json
import urllib.error
import urllib.request
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone


@dataclass(slots=True)
class CasheaOrderResult:
    order_id: str
    reference_id: str
    status: str
    amount_usd: float
    down_payment_usd: float
    financed_amount_usd: float
    installments_count: int
    installment_amount_usd: float
    checkout_url: str
    is_simulated: bool
    created_at: str
    raw_response: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(slots=True)
class CasheaWebhookEvent:
    event: str
    order_id: str
    reference_id: str
    status: str
    amount_usd: float
    down_payment_usd: float
    timestamp: str
    is_simulated: bool
    raw_payload: dict = field(default_factory=dict)


class CasheaClient:
    """Cliente de integración con Cashea.

    Soporta `simulation_mode=True` para desarrollar y probar el flujo completo
    sin credenciales reales de comercio aliado.
    """

    def __init__(
        self,
        api_url: str = "",
        api_key: str = "",
        webhook_secret: str = "sim-cashea-secret",
        simulation_mode: bool = True,
        down_payment_ratio: float = 0.40,
        installments_count: int = 3,
    ) -> None:
        self.api_url = api_url.rstrip("/")
        self.api_key = api_key
        self.webhook_secret = webhook_secret or "sim-cashea-secret"
        self.simulation_mode = simulation_mode or not (self.api_url and self.api_key)
        self.down_payment_ratio = down_payment_ratio
        self.installments_count = installments_count

    def create_order(
        self,
        reference_id: str,
        amount_usd: float,
        customer_name: str,
        customer_id_number: str,
        callback_url: str = "",
        items: list[dict] | None = None,
    ) -> CasheaOrderResult:
        if amount_usd <= 0:
            raise ValueError("El monto de la orden en Cashea debe ser mayor a 0.")
        if not reference_id.strip():
            raise ValueError("reference_id es obligatorio.")

        down_payment = round(amount_usd * self.down_payment_ratio, 2)
        financed = round(amount_usd - down_payment, 2)
        installment_amount = round(financed / max(self.installments_count, 1), 2)
        now_iso = datetime.now(timezone.utc).isoformat()

        if self.simulation_mode:
            order_id = f"CSH-SIM-{uuid.uuid4().hex[:10].upper()}"
            checkout_url = f"https://simulador.cashea.local/checkout/{order_id}?ref={reference_id}"
            raw = {
                "simulated": True,
                "order_id": order_id,
                "reference_id": reference_id,
                "customer_name": customer_name,
                "customer_id_number": customer_id_number,
                "items": items or [],
                "callback_url": callback_url,
            }
            return CasheaOrderResult(
                order_id=order_id,
                reference_id=reference_id,
                status="Pendiente",
                amount_usd=round(amount_usd, 2),
                down_payment_usd=down_payment,
                financed_amount_usd=financed,
                installments_count=self.installments_count,
                installment_amount_usd=installment_amount,
                checkout_url=checkout_url,
                is_simulated=True,
                created_at=now_iso,
                raw_response=raw,
            )

        payload = {
            "reference_id": reference_id,
            "amount": round(amount_usd, 2),
            "currency": "USD",
            "customer": {
                "name": customer_name,
                "id_number": customer_id_number,
            },
            "callback_url": callback_url,
            "items": items or [],
        }
        req = urllib.request.Request(
            f"{self.api_url}/orders",
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=20) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"Error HTTP Cashea ({exc.code}): {detail}") from exc

        return CasheaOrderResult(
            order_id=str(data.get("order_id") or data.get("id")),
            reference_id=reference_id,
            status=str(data.get("status", "Pendiente")),
            amount_usd=round(float(data.get("amount", amount_usd)), 2),
            down_payment_usd=round(float(data.get("down_payment", down_payment)), 2),
            financed_amount_usd=round(float(data.get("financed_amount", financed)), 2),
            installments_count=int(data.get("installments_count", self.installments_count)),
            installment_amount_usd=round(
                float(data.get("installment_amount", installment_amount)), 2
            ),
            checkout_url=str(data.get("checkout_url", "")),
            is_simulated=False,
            created_at=str(data.get("created_at", now_iso)),
            raw_response=data,
        )

    def sign_payload(self, payload_bytes: bytes) -> str:
        return hmac.new(
            self.webhook_secret.encode("utf-8"),
            payload_bytes,
            hashlib.sha256,
        ).hexdigest()

    def verify_webhook_signature(self, payload_bytes: bytes, signature_header: str) -> bool:
        if not signature_header:
            return False
        expected = self.sign_payload(payload_bytes)
        clean_sig = signature_header.replace("sha256=", "").strip()
        return hmac.compare_digest(expected, clean_sig)

    def build_simulated_webhook(
        self,
        order_id: str,
        reference_id: str,
        amount_usd: float,
        down_payment_usd: float | None = None,
        status: str = "Inicial Pagada",
    ) -> tuple[bytes, str]:
        if down_payment_usd is None:
            down_payment_usd = round(amount_usd * self.down_payment_ratio, 2)
        body = {
            "event": "order.approved",
            "order_id": order_id,
            "reference_id": reference_id,
            "status": status,
            "amount_usd": round(amount_usd, 2),
            "down_payment_usd": round(down_payment_usd, 2),
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "simulated": True,
        }
        raw_bytes = json.dumps(body, separators=(",", ":"), sort_keys=True).encode("utf-8")
        signature = self.sign_payload(raw_bytes)
        return raw_bytes, f"sha256={signature}"

    def parse_webhook(self, payload_bytes: bytes, signature_header: str) -> CasheaWebhookEvent:
        if not self.verify_webhook_signature(payload_bytes, signature_header):
            raise PermissionError("Firma de webhook de Cashea inválida.")
        data = json.loads(payload_bytes.decode("utf-8"))
        return CasheaWebhookEvent(
            event=str(data.get("event", "order.approved")),
            order_id=str(data["order_id"]),
            reference_id=str(data.get("reference_id", "")),
            status=str(data.get("status", "Aprobada")),
            amount_usd=round(float(data.get("amount_usd", 0.0)), 2),
            down_payment_usd=round(float(data.get("down_payment_usd", 0.0)), 2),
            timestamp=str(data.get("timestamp", datetime.now(timezone.utc).isoformat())),
            is_simulated=bool(data.get("simulated", self.simulation_mode)),
            raw_payload=data,
        )
