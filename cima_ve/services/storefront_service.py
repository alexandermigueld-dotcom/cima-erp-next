from __future__ import annotations

import re

from cima_ve.services.fiscal_printer import FiscalInvoiceItem, calculate_venezuela_taxes

DEFAULT_PRODUCT_IMAGE = "/assets/cima_ve/images/pending-product.svg"
VALID_TAXPAYER_TYPES = ("No Contribuyente", "Ordinario", "Especial", "Formal")


def normalize_rif_or_cedula(value: str | None) -> str:
    """Normaliza un RIF o Cédula venezolana (opcional)."""
    raw = (value or "").strip().upper()
    if not raw:
        return ""
    compact = re.sub(r"[^A-Z0-9]", "", raw)
    if not compact:
        return ""
    prefix = compact[0]
    digits = compact[1:]
    if prefix in {"V", "E", "J", "G", "P", "C"} and digits.isdigit():
        if prefix in {"J", "G"} and len(digits) == 9:
            return f"{prefix}-{digits[:8]}-{digits[8]}"
        return f"{prefix}-{digits}"
    if compact.isdigit():
        return f"V-{compact}"
    return raw


def validate_registration_payload(
    email: str,
    full_name: str,
    password: str,
    ve_rif_cedula: str = "",
    ve_taxpayer_type: str = "No Contribuyente",
) -> dict:
    """Valida datos de registro de cliente web (RIF/datos fiscales opcionales)."""
    clean_email = (email or "").strip().lower()
    if not clean_email or "@" not in clean_email or "." not in clean_email.split("@")[-1]:
        raise ValueError("Ingresa un correo electrónico válido.")

    clean_name = (full_name or "").strip()
    if len(clean_name) < 2:
        raise ValueError("Ingresa tu nombre completo.")

    clean_password = password or ""
    if len(clean_password) < 6:
        raise ValueError("La contraseña debe tener al menos 6 caracteres.")

    normalized_rif = normalize_rif_or_cedula(ve_rif_cedula)
    taxpayer = (ve_taxpayer_type or "No Contribuyente").strip()
    if taxpayer not in VALID_TAXPAYER_TYPES:
        taxpayer = "No Contribuyente"

    return {
        "email": clean_email,
        "full_name": clean_name,
        "password": clean_password,
        "ve_rif_cedula": normalized_rif,
        "ve_taxpayer_type": taxpayer,
    }


def format_cashea_installments(grand_total: float) -> dict:
    """Calcula la inicial (40%) y 3 cuotas (20% c/u) estimadas en Cashea."""
    total = max(float(grand_total or 0), 0.0)
    down_payment = round(total * 0.40, 2)
    remaining = round(total - down_payment, 2)
    installment = round(remaining / 3.0, 2) if total > 0 else 0.0
    return {
        "down_payment_usd": down_payment,
        "installment_usd": installment,
        "installments": 3,
    }


def build_payment_methods_catalog(settings: dict | None = None) -> list[dict]:
    """Construye el catálogo de métodos de pago disponibles en la tienda."""
    cfg = settings or {}
    cashea_enabled = bool(cfg.get("cashea_enabled", 1))
    simulation_mode = bool(cfg.get("simulation_mode", 1))

    methods: list[dict] = []
    if cashea_enabled:
        methods.append(
            {
                "id": "cashea",
                "label": "Cashea (Cuotas sin interés)",
                "short_label": "Cashea",
                "badge": "40% inicial + 3 cuotas",
                "description": "Compra ahora y paga en cuotas sin interés desde la app de Cashea.",
                "requires_reference": False,
                "applies_igtf": False,
                "mode_of_payment": "Cashea",
                "simulation_mode": simulation_mode,
            }
        )

    methods.extend(
        [
            {
                "id": "google_pay",
                "label": "Google Pay / Tarjeta (Sin guardar tarjeta)",
                "short_label": "Google Pay / Tarjeta",
                "badge": "Pago seguro navegador",
                "description": (
                    "Paga con tus tarjetas guardadas en Google Wallet / navegador "
                    "mediante tokenización segura, sin almacenar datos de tarjeta."
                ),
                "requires_reference": False,
                "applies_igtf": False,
                "mode_of_payment": "Credit Card",
                "merchant_id": (cfg.get("google_pay_merchant_id") or "").strip(),
                "merchant_name": (cfg.get("google_pay_merchant_name") or "CIMA ELECTRONIC VE").strip(),
                "simulation_mode": simulation_mode,
            },
            {
                "id": "pago_movil",
                "label": "Pago Móvil (Bs)",
                "short_label": "Pago Móvil",
                "badge": "Confirmación rápida",
                "description": "Transfiere en Bolívares al instante e ingresa el número de referencia.",
                "instructions": (cfg.get("pago_movil_info") or "").strip()
                or "Solicita o confirma los datos de Pago Móvil al finalizar el pedido.",
                "requires_reference": True,
                "applies_igtf": False,
                "mode_of_payment": "Pago Móvil",
            },
            {
                "id": "zelle",
                "label": "Zelle (USD)",
                "short_label": "Zelle",
                "badge": "Divisas (+3% IGTF)",
                "description": "Pago en dólares vía Zelle. Sujeto a 3% IGTF según normativa SENIAT.",
                "instructions": (cfg.get("zelle_info") or "").strip()
                or "Ingresa el titular/correo emisor y número de confirmación Zelle.",
                "requires_reference": True,
                "applies_igtf": True,
                "mode_of_payment": "Zelle",
            },
            {
                "id": "binance_pay",
                "label": "Binance Pay / USDT",
                "short_label": "Binance Pay",
                "badge": "Cripto USD (+3% IGTF)",
                "description": "Paga con USDT a través de Binance Pay e indica tu ID de transacción.",
                "instructions": (cfg.get("binance_pay_info") or "").strip()
                or "Envía USDT por Binance Pay y registra tu Order ID / TXID.",
                "requires_reference": True,
                "applies_igtf": True,
                "mode_of_payment": "USDT Binance",
            },
            {
                "id": "transferencia",
                "label": "Transferencia Bancaria",
                "short_label": "Transferencia",
                "badge": "Banco Nacional",
                "description": "Transferencia bancaria directa con comprobante de referencia.",
                "instructions": (cfg.get("bank_transfer_info") or "").strip()
                or "Realiza tu transferencia e ingresa el banco emisor y número de referencia.",
                "requires_reference": True,
                "applies_igtf": False,
                "mode_of_payment": "Transferencia Bs",
            },
        ]
    )
    return methods


def calculate_storefront_totals(
    items: list[dict],
    payment_method: str = "cashea",
    iva_rate: float = 16.0,
    igtf_rate: float = 3.0,
) -> dict:
    """Calcula subtotal, IVA, IGTF (si aplica) y total para el carrito web."""
    fiscal_items: list[FiscalInvoiceItem] = []
    for row in items or []:
        qty = float(row.get("qty") or 0)
        rate = float(row.get("rate") if row.get("rate") is not None else row.get("price") or 0)
        if qty <= 0:
            continue
        fiscal_items.append(
            FiscalInvoiceItem(
                item_code=str(row.get("item_code") or ""),
                description=str(row.get("item_name") or row.get("item_code") or ""),
                qty=qty,
                unit_price=max(rate, 0.0),
                is_exempt=bool(row.get("is_exempt", False)),
            )
        )

    apply_igtf = payment_method in {"zelle", "binance_pay"}
    breakdown = calculate_venezuela_taxes(
        items=fiscal_items,
        apply_igtf=apply_igtf,
        iva_rate=iva_rate,
        igtf_rate=igtf_rate,
    )
    result = breakdown.to_dict()
    result["apply_igtf"] = apply_igtf
    result["cashea"] = format_cashea_installments(breakdown.grand_total)
    return result
