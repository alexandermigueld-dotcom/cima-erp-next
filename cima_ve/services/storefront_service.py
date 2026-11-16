from __future__ import annotations

import json
import re
from urllib.parse import quote

from cima_ve.services.fiscal_printer import FiscalInvoiceItem, calculate_venezuela_taxes

DEFAULT_PRODUCT_IMAGE = "/assets/cima_ve/images/pending-product.svg"
VALID_TAXPAYER_TYPES = ("No Contribuyente", "Ordinario", "Especial", "Formal")

DEFAULT_DELIVERY_PROVIDERS = [
    {
        "id": "pickup",
        "label": "Retiro en Tienda (Pickup)",
        "cost": 0.0,
        "description": "Retira tu pedido directamente en tienda sin costo adicional.",
        "requires_address": False,
    },
    {
        "id": "mrw",
        "label": "MRW (Envío Nacional)",
        "cost": 5.0,
        "description": "Envío a agencia o dirección a nivel nacional vía MRW.",
        "requires_address": True,
    },
    {
        "id": "zoom",
        "label": "Zoom (Envío Nacional)",
        "cost": 6.0,
        "description": "Envío asegurado a agencia o domicilio vía Zoom.",
        "requires_address": True,
    },
    {
        "id": "tealca",
        "label": "Tealca (Envío Nacional)",
        "cost": 5.5,
        "description": "Envío nacional con seguimiento vía Tealca.",
        "requires_address": True,
    },
    {
        "id": "delivery_local",
        "label": "Delivery Express (Motorizado)",
        "cost": 3.0,
        "description": "Entrega rápida en la ciudad con mensajero.",
        "requires_address": True,
    },
]


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


def parse_delivery_providers(raw: str | list | None = None) -> list[dict]:
    """Parsea la lista de proveedores de envío desde Cima VE Settings o usa los predeterminados."""
    parsed = None
    if isinstance(raw, list):
        parsed = raw
    elif isinstance(raw, str) and raw.strip():
        text = raw.strip()
        try:
            candidate = json.loads(text)
            if isinstance(candidate, list):
                parsed = candidate
        except Exception:
            # Fallback: líneas tipo "MRW | 5.00 | Envío nacional"
            lines = []
            for idx, line in enumerate(text.splitlines()):
                parts = [p.strip() for p in line.split("|")]
                if not parts or not parts[0]:
                    continue
                label = parts[0]
                cost = 0.0
                if len(parts) > 1:
                    try:
                        cost = float(parts[1])
                    except ValueError:
                        cost = 0.0
                desc = parts[2] if len(parts) > 2 else ""
                pid = re.sub(r"[^a-z0-9]+", "_", label.lower()).strip("_") or f"provider_{idx}"
                lines.append(
                    {
                        "id": pid,
                        "label": label,
                        "cost": max(cost, 0.0),
                        "description": desc,
                        "requires_address": "retiro" not in label.lower() and "pickup" not in label.lower(),
                    }
                )
            if lines:
                parsed = lines

    if not parsed:
        return [dict(item) for item in DEFAULT_DELIVERY_PROVIDERS]

    normalized: list[dict] = []
    for idx, row in enumerate(parsed):
        if not isinstance(row, dict):
            continue
        label = str(row.get("label") or row.get("name") or "").strip()
        if not label:
            continue
        pid = str(row.get("id") or re.sub(r"[^a-z0-9]+", "_", label.lower()).strip("_") or f"envio_{idx}")
        try:
            cost = max(float(row.get("cost") or 0.0), 0.0)
        except (TypeError, ValueError):
            cost = 0.0
        normalized.append(
            {
                "id": pid,
                "label": label,
                "cost": round(cost, 2),
                "description": str(row.get("description") or "").strip(),
                "requires_address": bool(row.get("requires_address", "pickup" not in pid and "retiro" not in label.lower())),
            }
        )
    return normalized or [dict(item) for item in DEFAULT_DELIVERY_PROVIDERS]


def resolve_delivery_provider(provider_id: str | None, providers: list[dict] | None = None) -> dict:
    """Devuelve el proveedor de envío seleccionado o el primero disponible."""
    catalog = providers or [dict(item) for item in DEFAULT_DELIVERY_PROVIDERS]
    target = (provider_id or "").strip().lower()
    for p in catalog:
        if p["id"].lower() == target or p["label"].lower() == target:
            return p
    return catalog[0]


def calculate_storefront_totals(
    items: list[dict],
    payment_method: str = "cashea",
    iva_rate: float = 16.0,
    igtf_rate: float = 3.0,
    shipping_cost: float = 0.0,
) -> dict:
    """Calcula subtotal, IVA, IGTF (si aplica), envío y total para el carrito web."""
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
    ship = round(max(float(shipping_cost or 0.0), 0.0), 2)
    grand_with_shipping = round(breakdown.grand_total + ship, 2)
    result = breakdown.to_dict()
    result["shipping_cost"] = ship
    result["grand_total"] = grand_with_shipping
    result["apply_igtf"] = apply_igtf
    result["cashea"] = format_cashea_installments(grand_with_shipping)
    return result


def build_whatsapp_link(phone: str | None, text: str = "") -> str:
    """Genera un enlace wa.me limpio para coordinar entrega por WhatsApp."""
    digits = re.sub(r"[^0-9]", "", phone or "")
    if not digits:
        return ""
    if len(digits) == 10 and digits.startswith("4"):
        digits = f"58{digits}"
    elif len(digits) == 11 and digits.startswith("04"):
        digits = f"58{digits[1:]}"
    base = f"https://wa.me/{digits}"
    if text:
        return f"{base}?text={quote(text)}"
    return base


def build_order_notification_payload(
    *,
    order_id: str,
    customer_name: str,
    customer_email: str,
    customer_phone: str = "",
    address: str = "",
    delivery_label: str = "",
    delivery_cost: float = 0.0,
    payment_method: str = "",
    payment_reference: str = "",
    items: list[dict] | None = None,
    grand_total: float = 0.0,
) -> dict:
    """Construye asunto, HTML de correo y texto de WhatsApp para notificar un pedido web."""
    lines = [
        f"Nuevo pedido en Tienda Web: {order_id}",
        f"Cliente: {customer_name}",
        f"Correo: {customer_email}",
    ]
    if customer_phone:
        lines.append(f"Teléfono/WhatsApp: {customer_phone}")
    if delivery_label:
        cost_txt = f"${delivery_cost:.2f}" if delivery_cost > 0 else "Gratis"
        lines.append(f"Envío: {delivery_label} ({cost_txt})")
    if address:
        lines.append(f"Dirección: {address}")
    lines.append(f"Método de pago: {payment_method}" + (f" (Ref: {payment_reference})" if payment_reference else ""))
    lines.append("")
    lines.append("Productos:")
    item_rows_html = []
    for row in items or []:
        qty = float(row.get("qty") or 0)
        name = row.get("item_name") or row.get("item_code") or ""
        rate = float(row.get("rate") or row.get("price") or 0)
        lines.append(f"- {qty:g} x {name} (${rate:.2f})")
        item_rows_html.append(
            f"<li><strong>{qty:g}x</strong> {name} — ${rate:.2f}</li>"
        )
    lines.append(f"\nTotal pedido: ${float(grand_total or 0):.2f}")

    customer_wa = build_whatsapp_link(
        customer_phone,
        f"Hola {customer_name}, te contactamos de CIMA ELECTRONIC VE por tu pedido {order_id}.",
    )
    if customer_wa:
        lines.append(f"Contactar cliente por WhatsApp: {customer_wa}")

    plain_text = "\n".join(lines)
    html_body = f"""
    <div style="font-family:Arial,sans-serif;max-width:600px;margin:0 auto;">
      <h2 style="color:#131921;margin-bottom:8px;">Nuevo Pedido Web: {order_id}</h2>
      <p><strong>Cliente:</strong> {customer_name}<br>
         <strong>Correo:</strong> {customer_email}<br>
         <strong>Teléfono / WhatsApp:</strong> {customer_phone or 'No suministrado'}<br>
         <strong>Envío:</strong> {delivery_label or 'No especificado'} (${delivery_cost:.2f})<br>
         <strong>Dirección:</strong> {address or 'Retiro en tienda / Sin dirección'}<br>
         <strong>Método de pago:</strong> {payment_method} {f'(Ref: {payment_reference})' if payment_reference else ''}
      </p>
      <h4>Productos</h4>
      <ul>{''.join(item_rows_html)}</ul>
      <p style="font-size:16px;"><strong>Total: ${float(grand_total or 0):.2f}</strong></p>
      {f'<p><a href="{customer_wa}" style="background:#16a34a;color:#fff;padding:10px 14px;border-radius:6px;text-decoration:none;display:inline-block;">Escribir al cliente por WhatsApp</a></p>' if customer_wa else ''}
    </div>
    """

    return {
        "subject": f"[CIMA Tienda] Nuevo Pedido {order_id} - {customer_name} (${float(grand_total or 0):.2f})",
        "text": plain_text,
        "html": html_body,
        "customer_whatsapp_url": customer_wa,
    }
