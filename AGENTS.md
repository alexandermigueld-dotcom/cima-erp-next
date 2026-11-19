# AI Agent & Developer Guide — `cima_ve` (`cima-erp-next`)

This document is the canonical technical reference for AI agents and developers working on **`cima_ve`**, the custom Frappe/ERPNext v16 application for **CIMA Electronic VE**.

---

## 1. Environment, Secrets & Local Testing

### Local Python & Virtual Environment
- **OS:** Windows (PowerShell). Always use `\` in Windows paths and PowerShell syntax (`;` instead of `&&`).
- **Python / `uv` venv:** `.venv` at repo root.
- **Run all unit tests (no live Frappe bench required):**
  ```powershell
  .\.venv\Scripts\python.exe -m unittest discover -s tests -v
  ```
- **Run local Cashea + Fiscal simulator demo:**
  ```powershell
  .\.venv\Scripts\python.exe demo_simulador.py
  ```
- **Run live diagnostics:**
  ```powershell
  .\.venv\Scripts\python.exe diagnostico_erpnext.py
  .\.venv\Scripts\python.exe diagnostico_frappe_cloud.py
  ```

### Secrets (`.env`, gitignored — NEVER commit)
Expected keys in `.env`:
- `ERPNEXT_URL=https://cimaelectronicve.v.frappe.cloud`
- `API_KEY` and `SECRET_API` (ERPNext REST token for `cimaelectronic@gmail.com`)
- `FRAPPE_API_ACCESS_KEY` and `FRAPPE_API_SECRET` (Frappe Cloud `https://cloud.frappe.io` Press API token)

---

## 2. Architecture & Code Organization

### Key Design Pattern: Pure-Python `services/` + Frappe `api/`
To keep business logic fast to test locally without a running Frappe/MariaDB bench:
1. **`cima_ve/services/*.py`**: Pure Python functions (calculations, formatting, validation, state transitions, HTTP clients using stdlib `urllib`). **Do not import `frappe` at module top level** in `services/` so `tests/*.py` can import and test them directly.
2. **`cima_ve/api/*.py`**: Frappe `@whitelist()` endpoints that handle `frappe.db`, `frappe.get_doc`, `frappe.only_for(...)`, permissions, and call into `services/`.
   - Use `from cima_ve.api._compat import whitelist` so API modules can still be imported in local unit tests when `frappe` is not installed.

### Repository Map
- **`cima_ve/hooks.py`**: App metadata, `fixtures` (`Custom Field`, `Workspace`), `doc_events` (`Sales Invoice` `validate` / `on_submit`), and `scheduler_events` (`hourly`: `cima_ve.api.exchange_rates.scheduled_sync_exchange_rates`).
- **`cima_ve/cima_ve/doctype/cima_ve_settings/`**: Single Settings DocType (`System Manager` only) storing:
  - `simulation_mode`, Cashea API/webhook secrets (`Password` fieldtype), Imprenta Digital fiscal API/token (`Password`).
  - Storefront warehouse (`Almacén Principal White Point - CEV`), Google Pay merchant ID, payment method details (`pago_movil_info`, `zelle_info`, `binance_pay_info`, `bank_transfer_info`), and `delivery_providers` JSON.
  - Notifications: `notify_order_email` (comma-separated emails), `notify_whatsapp_number`, `whatsapp_webhook_url`, `whatsapp_api_token`.
  - Discounts & Commissions: `auto_discount_enabled`, `auto_discount_tiers` (JSON), `commission_enabled`, `commission_rules` (JSON).
  - Exchange Rates & Brecha: `bcv_rate`, `monitor_rate`, `binance_usdt_rate`, `brecha_source`, `brecha_factor_pct`, `manual_brecha_pct`, `applied_brecha_pct`, `adjusted_rate`, `sync_currency_exchange`.
- **`cima_ve/cima_ve/page/`**:
  - `venta_rapida/` (`/app/venta-rapida`): Simplified seller POS for creating **Notas de Entrega** and checking inventory/prices.
  - `notas_entrega/` (`/app/notas-entrega`): Nota de Entrega management (Admin sees all + `Pagar`/`Revertir`/`Calcular Comisiones`; `Sales User` sees only their own notes and can register payment on their own notes, but cannot revert or calculate commissions).
  - `metricas_ventas/` (`/app/metricas-ventas`): Sales KPIs and per-user breakdown (**System Manager only**).
  - `clientes_consumo/` (`/app/clientes-consumo`): Client consumption and per-seller breakdown (**System Manager only**).
- **`cima_ve/www/tienda.html`, `tienda.py`, `cima_ve/public/js/tienda.js`, `css/tienda.css`, `images/pending-product.svg`**: Public Amazon-style storefront (`/tienda`).
- **`cima_ve/fixtures/custom_field.json`**: Custom fields on `Customer`, `Sales Invoice`, and `Delivery Note`.
- **`cima_ve/fixtures/workspace.json`**: `Facturación Cima` (labeled `Facturación Rápida` for sellers) and `Administración Cima` (`System Manager` only).
- **`cima_ve/overrides/sales_invoice.py`**: Validates Venezuelan seller/fiscal fields and triggers fiscal stamping on submit.

---

## 3. Core Functionalities & Workflows

### A. Nota de Entrega Lifecycle (Lazy Payment Workflow)
The company uses **Notas de Entrega** (`Delivery Note` in ERPNext) instead of immediate fiscal invoicing:

1. **Creation (2 sources):**
   - **Facturación Rápida (`/app/venta-rapida` → `cima_ve.api.delivery_notes.create_quick_delivery_note`):**
     - Validates authenticated user (`frappe.session.user != "Guest"`).
     - Inserts and submits `Delivery Note` using `ignore_permissions=True` (required because ERPNext `Custom DocPerm` restricts `Sales User` from direct Desk `Delivery Note` creation).
     - Automatically attributes the logged-in user (`ve_vendedor_usuario`, `ve_vendedor_nombre`, and `sales_team` resolved from `Employee.user_id` or fallback).
     - Deducts inventory immediately (`docstatus = 1`), sets `ve_ne_estado = "Pendiente"`, **does not** record money yet.
   - **Public Storefront (`/tienda` → `cima_ve.api.storefront.place_storefront_order`):**
     - Creates and submits a `Delivery Note` (`ve_ne_origen = "Tienda Web"`, `ve_ne_estado = "Pendiente"`).
     - Saves customer-reported payment method, reference, bank, notes, shipping provider/cost, and uploaded screenshot (`upload_storefront_payment_proof` → `ve_ne_comprobante_url`).

2. **Item-Level Custom Pricing & Global Discounts:**
   - **Custom Unit Price (`Precio` button in `venta-rapida`):** `compute_custom_price_breakdown` keeps original `price_list_rate` and sets `rate`, `discount_amount`, and `discount_percentage` when the custom price is lower than list price. Discounted items are flagged on the Nota de Entrega.
   - **Automatic Amount-Based Discounts (`auto_discount_tiers` in `Cima VE Settings`):** Default rules: `< $100 → 0%`, `$500–$1,000 → 4.76%`, `> $1,000 → 9.09%`.
   - **Optional Manual Percentage Discount:** Sellers can toggle `Habilitar descuento (%)` in `venta-rapida`. Both auto and manual discounts are persisted on `Delivery Note` custom fields and highlighted in `notas-entrega`.

3. **Margin-Based Seller Commissions:**
   - Configurable `commission_rules` in `Cima VE Settings` (default: `Meta Ads 7%`, `Detal 8%`, `Mayor 10%`).
   - Computed on **winning margin**: `max(net_total - total_cost, 0) * (pct / 100)`, using `Delivery Note Item.incoming_rate` (with `Bin`/`Item` `valuation_rate` fallback).
   - Stored in `ve_ne_comision_opcion`, `ve_ne_comision_pct`, `ve_ne_costo_total`, `ve_ne_margen_ganancia`, `ve_ne_comision_monto`.
   - Admin can run `calculate_seller_commissions` from `/app/notas-entrega` (**Calcular Comisiones**) to summarize paid vs. pending commissions per seller (excluding cancelled notes).

4. **Settlement (`Pagar` → `cima_ve.api.delivery_notes.mark_delivery_note_paid`; admins can pay any note and Sales Users can pay their own):**
   - Opens dialog showing USD + live Bs equivalents (`Saldo pendiente`, `Este pago`, `Saldo restante`), previous installments, and any `/tienda` reported payment proof.
   - **Partial Payments:** Supports paying a partial amount (`paid_amount`). On the first payment, creates & submits a `Sales Invoice` (applying selected IVA/IGTF taxes) and a `Payment Entry` for `paid_amount`. Subsequent payments reuse `ve_ne_factura` and submit additional `Payment Entry` records.
   - While `remaining_amount > 0.01`, `ve_ne_estado` becomes `"Pago Parcial"` and the note **stays visible** under the `Pendiente` filter. Once fully paid, `ve_ne_estado` becomes `"Pagada"`.
   - **Non-Cash Payment Proof:** Reference number and screenshot upload are required/shown for non-cash methods and automatically hidden for cash (`Efectivo` / `Cash`).
   - **Historical Bs Freeze (`compute_historical_bs_payment`):** Each installment saves `amount_bs` and `exchange_rate` in `ve_ne_historial_pagos` JSON. `ve_ne_tasa_cambio` and `ve_ne_monto_pagado_bs` are updated, and once `Pagada`, `ve_ne_monto_bs` is frozen so future FX rate changes **never** alter the historical Bs amount of a paid Nota de Entrega.

5. **Reversion (`Revertir` → `cima_ve.api.delivery_notes.revert_delivery_note`, System Manager only):**
   - Cancels linked `Payment Entry` documents, then the `Sales Invoice`, then the `Delivery Note`. Cancelling the submitted Delivery Note restores inventory even when it was never paid.
   - Keeps the Delivery Note and its payment history for audit, sets `docstatus = 2` and `ve_ne_estado = "Cancelada"`, and logs `ve_ne_fecha_resolucion`, `ve_ne_usuario_resolucion`, and `ve_ne_motivo_cancelacion`.
   - A fiscal invoice with a control number must be handled with a credit note. Cancelling ERPNext payment records reverses the accounting entries; it does not initiate a bank transfer.

6. **Notifications on Creation:**
   - Every Nota de Entrega (from `venta-rapida` or `/tienda`) triggers `notify_delivery_note_created`:
     - Sends summary email via `frappe.sendmail` to `notify_order_email` (configured for `cimaelectronic@gmail.com, alexandermigueld@gmail.com`).
     - Sends WhatsApp notification via `whatsapp_webhook_url` (if configured) and generates a `wa.me` coordination link for `notify_whatsapp_number` (`+584243472198`).

### B. Exchange Rates & Brecha (`exchange_rate_service.py`, `exchange_rates.py`)
- Fetches **BCV (`oficial`)** and **Monitor (`paralelo`)** from DolarAPI (`https://ve.dolarapi.com/v1/dolares`) and **Binance P2P (`USDT/VES`)** from Binance's public P2P endpoint (`POST https://p2p.binance.com/bapi/c2c/v2/friendly/c2c/adv/search`).
- Computes `brecha_pct = ((Market_Rate / BCV_Rate) - 1) * 100` and `adjusted_rate = BCV_Rate * (1 + (applied_brecha_pct / 100))`.
- Runs hourly via `hooks.py` and on-demand via `sync_exchange_rates_now` in `Cima VE Settings`.

### C. Public Storefront (`/tienda`)
- Reads live `Bin` stock from `storefront_warehouse` (`Almacén Principal White Point - CEV`) and `Detal USD` prices; shows `"Imagen pendiente por subir"` (`pending-product.svg`) when `website_image` is empty.
- Mandatory email on login/registration/checkout (optional phone, optional RIF/taxpayer profile); supports Google OAuth user linking to `Customer`.
- Delivery providers (`Retiro en Tienda`, `MRW`, `Zoom`, `Tealca`, `Delivery Express`) with configurable costs.
- 6 payment methods: Cashea, Google Pay / Card Tokenization, Pago Móvil, Zelle, Binance Pay, Transferencia Bancaria.

### D. Role & Access Control Rules
- **Non-admin (`Sales User`):**
  - Can **only** access `/app/venta-rapida` (`Facturación Rápida` workspace) and **only their own** Notas de Entrega in `/app/notas-entrega`; can register payments on their own notes but cannot `Revertir`, `Calcular Comisiones`, or access `Sales Invoice` links.
- **Admin (`System Manager`):**
  - Full access to `/app/notas-entrega`, `/app/metricas-ventas`, `/app/clientes-consumo`, `Cima VE Settings`, and `Administración Cima` workspace.
  - All admin APIs enforce `frappe.only_for("System Manager")`.

---

## 4. Frappe v16 & ERPNext Gotchas

1. **`Workspace` Fixture Requires `"type": "Workspace"`:** Frappe v16 will throw `MandatoryError: [Workspace, ...]: type` on `install_app` / `migrate` if `"type"` is missing from `cima_ve/fixtures/workspace.json`.
2. **`Page` JSON `modified` Timestamp Must Be Bumped:** When changing `roles` in `cima_ve/cima_ve/page/<page>/<page>.json`, Frappe's `bench migrate` only re-syncs the `Page` doc (and its `Has Role` child table) if the JSON `"modified"` timestamp is newer than the database `modified` timestamp!
3. **Mandatory `Property Setter` Fields on Sales Docs:** `cimaelectronicve.v.frappe.cloud` has `Property Setter` rules making `canal_venta` and `sales_team` mandatory on `Sales Invoice` and `Sales Order`. Always route creation through `_apply_required_sales_metadata` in `seller_pos.py` / `storefront.py`.
4. **`Custom DocPerm` Blocks `Sales User` on `Delivery Note`:** Do not rely on Desk permissions for `create_quick_delivery_note`; validate the authenticated user and call `insert(ignore_permissions=True)` + `submit()`.

---

## 5. Git & Frappe Cloud Deployment Playbook

### Infrastructure Identifiers
- **GitHub Repo:** `https://github.com/josephnowak/cima-erp-next` (branch `main`)
- **Live Site URL:** `https://cimaelectronicve.v.frappe.cloud`
- **Frappe Cloud Internal Site ID:** `erpnext-yfl-bqf.v.frappe.cloud`
- **Private Bench:** `bench-52215` (Frappe v16, N. Virginia)

### Step-by-Step Release Process

1. **Run Local Tests First:**
   ```powershell
   .\.venv\Scripts\python.exe -m unittest discover -s tests -v
   ```
2. **Commit & Push to `origin/main`:**
   *(Always include the Junie co-author trailer when committing as Junie; never stage `.env`.)*
   ```powershell
   git status --short
   git add cima_ve/ tests/
   git commit -m "Describe change" --trailer "Co-authored-by: Junie <junie@jetbrains.com>"
   git push origin main
   ```
3. **Deploy Bench on Frappe Cloud (`https://cloud.frappe.io` Press API):**
   Using `.env` credentials (`FRAPPE_API_ACCESS_KEY` + `FRAPPE_API_SECRET`) with `Authorization: token <key>:<secret>`:
   - **Important:** `press.api.bench.fetch_latest_app_update` may return `HTTP 403` depending on API token scope. Calling `press.api.bench.deploy` directly with `{"name": "bench-52215"}` automatically fetches the latest `main` commit and builds a new bench release!
   - Poll `press.api.bench.deploy_information` (`{"name": "bench-52215"}`) until `last_deploy.status == "Success"` (or `running_deploy` clears).
4. **Update Site onto the New Bench Release:**
   - Check `press.api.site.check_for_updates` (`{"name": "erpnext-yfl-bqf.v.frappe.cloud"}`) until `update_available == True`.
   - Call `press.api.site.update` (`{"name": "erpnext-yfl-bqf.v.frappe.cloud"}`) — this migrates the site (`bench migrate`, syncing `Custom Field`, `Workspace`, `Page` JSONs, and JS/CSS assets).
   - Poll `press.api.site.get` (`{"name": "erpnext-yfl-bqf.v.frappe.cloud"}`) until `status == "Active"` and `check_for_updates` returns `update_available: False`.
5. **Verify Live Endpoints (using `.env` `ERPNEXT_URL`, `API_KEY`, `SECRET_API`):**
   - `GET /api/method/cima_ve.api.seller_pos.get_seller_bootstrap`
   - `GET /api/method/cima_ve.api.delivery_notes.get_delivery_notes`
   - `GET /api/method/cima_ve.api.storefront.get_storefront_bootstrap`
   - `GET /api/method/frappe.desk.desk_page.getpage?name=venta-rapida`
   - `GET /api/method/frappe.desk.desk_page.getpage?name=notas-entrega`
