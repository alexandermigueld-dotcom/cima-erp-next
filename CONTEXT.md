# Project & Conversation Context — `cima-erp-next` (`cima_ve`)

**Last updated:** 2026-11-15  
**GitHub Repository:** `https://github.com/josephnowak/cima-erp-next`  
**Local Git Repo Path:** `C:\Users\usuario\PycharmProjects\cima-erp-next`  
**Previous Workspace (migrated from):** `C:\Users\usuario\PycharmProjects\PythonProject\cima-erp-next`

---

## 1. Business Goals & Requirements

- **Company:** `CIMA ELECTRONIC VE` (Venezuela).
- **Primary Objectives:**
  1. **E-commerce Webshop:** Publish existing ERPNext inventory online using native Frappe `Webshop` + `Payments`.
  2. **Cashea Integration:** Support Cashea installment checkout + signed webhook confirmation, creating/updating `Customer`, `Sales Invoice`, and `Payment Entry` in ERPNext. *(Currently in **Simulation Mode** until official Cashea merchant API credentials are obtained.)*
  3. **Venezuelan Fiscal Invoicing (SENIAT):** Digital fiscal printing (`Imprenta Digital` via REST API), supporting IVA 16%, exempt items, IGTF 3% (foreign currency payments), control numbers (`00-XXXXXXXX`), fiscal invoice numbers, QR hashes, and PDF URLs. *(Currently in **Simulation Mode** until a SENIAT-authorized Imprenta Digital provider is contracted.)*
  4. **Simplified Seller POS Interface (`venta-rapida`):** A clean, distraction-free ERPNext Page & Workspace (`Facturación Cima`) for sellers, featuring a prominent **+ INICIAR FACTURACIÓN** button and a searchable **Inventario y Precios** tab.
  5. **No External App Servers:** Run everything inside Frappe Cloud using `Private Bench` (`$25 USD/month` plan) + the `cima_ve` custom Frappe app.

---

## 2. Live Infrastructure & Environment State

### Frappe Cloud (`https://cloud.frappe.io`)
- **Site Domain:** `https://cimaelectronicve.v.frappe.cloud`
- **Internal Site ID:** `erpnext-yfl-bqf.v.frappe.cloud`
- **Plan:** `USD 25` (`price_usd: 25.0`, `private_benches: 1`, `cpu_time_per_day: 2.0h`, `max_storage_usage: 25 GB`, `max_database_usage: 1 GB`, `offsite_backups: 1`).
- **Region / Cluster:** `N. Virginia, USA` (`Virginia`).
- **Current Bench:** `bench-52215` (`bench-52215-000002-f94v`, **Private Bench**, `public: 0`, `Version 16`).
- **Installed Custom App:** `cima_ve` (`0.1.0`, connected to `https://github.com/josephnowak/cima-erp-next`, `main`).

### ERPNext Instance (`https://cimaelectronicve.v.frappe.cloud`)
- **Versions:** `Frappe 16.56.0`, `ERPNext 16.51.2`, `Cima VE 0.1.0`.
- **Installed Apps:** `frappe`, `erpnext`, `payments`, `webshop`, `email_delivery_service`, `cima_ve`.
- **Admin / API User:** `cimaelectronic@gmail.com` (has `System Manager` and `Script Manager` roles).
- **Company & Fiscal Setup:**
  - Company: `CIMA ELECTRONIC VE` (default currency `USD`; `tax_id`/RIF still needs to be filled in ERPNext).
  - Existing Tax Templates: `Factura Fiscal IVA 16% - CEV`, `Factura Fiscal IVA 16% + IGTF 3% (pago en divisas) - CEV`.
  - Price Lists: `Detal USD`, `Detal Bs BCV`, `Mayor Ruta USD`, `Mayor Tienda USD`, `Costo Importación`.
  - Warehouses: includes `Almacén Principal White Point - CEV`.
  - Data Counts (at last check): `377` `Item`s, `8` `Customer`s, `15` `Sales Invoice`s, `3` `Webhook`s, `8` `Client Script`s.
- **Custom Fields Already Synced to Live Site (14 fields):**
  - On `Customer`: `ve_rif_cedula`, `ve_taxpayer_type`
  - On `Sales Invoice`: `ve_numero_control`, `ve_numero_factura_fiscal`, `ve_fiscal_status`, `ve_fiscal_pdf_url`, `ve_fiscal_hash`, `ve_igtf_aplicado`, `ve_igtf_amount`, `cashea_order_id`, `cashea_status`, `cashea_down_payment` (plus section breaks).
- **Webshop Status (LIVE & FIXED):**
  - `Webshop Settings` enabled (`enabled=1`, `show_price=1`, `show_stock_availability=1`, `price_list="Detal USD"`, `default_customer_group="Individual"`, `enable_checkout=1`).
  - All **321** active sales items (`disabled=0`, `is_sales_item=1`) are published as `Website Item` (`published=1`) and confirmed visible via guest `get_product_filter_data`.

---

## 3. Local Environment & Credentials (`.env`)

Secrets are stored **only** in the local `.env` file (gitignored, never committed). Expected keys:
- `ERPNEXT_URL=https://cimaelectronicve.v.frappe.cloud`
- `API_KEY` and `SECRET_API` (ERPNext REST API token for `cimaelectronic@gmail.com`)
- `FRAPPE_API_ACCESS_KEY` and `FRAPPE_API_SECRET` (Frappe Cloud `https://cloud.frappe.io` API token)

Local Python virtual environment (`.venv`, Python 3.14) is managed with `uv`:
```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe demo_simulador.py
.\.venv\Scripts\python.exe diagnostico_erpnext.py
.\.venv\Scripts\python.exe diagnostico_frappe_cloud.py
```

---

## 4. Implemented Codebase (`cima_ve` Custom App)

- **`cima_ve/hooks.py` & `cima_ve/modules.txt`**: App metadata, fixtures (`Custom Field`, `Workspace`), and `Sales Invoice` doc events (`validate`, `on_submit`).
- **`cima_ve/cima_ve/doctype/cima_ve_settings/`**: Settings DocType with `simulation_mode`, Cashea API config, and Fiscal Printer API config.
- **`cima_ve/services/cashea_client.py` & `cima_ve/api/cashea.py`**: Cashea checkout creation (40% down payment + installments) and HMAC-SHA256 webhook verification (simulation + real HTTP client).
- **`cima_ve/services/fiscal_printer.py` & `cima_ve/api/fiscal.py`**: Venezuelan tax breakdown (IVA 16%, exempt, IGTF 3%) and simulated/REST Imprenta Digital stamping (`on_submit` hook in `cima_ve/overrides/sales_invoice.py`).
- **`cima_ve/services/seller_pos_service.py` & `cima_ve/api/seller_pos.py`**: Backend endpoints for the simplified seller POS (`get_seller_bootstrap`, `search_inventory_and_prices`, `search_customers`, `quick_create_customer`, `create_quick_invoice`).
- **`cima_ve/cima_ve/page/venta_rapida/`**: Native Frappe Page (`venta-rapida.json`, `.js`, `.css`) with **+ INICIAR FACTURACIÓN** flow and searchable **Inventario y Precios** tab.
- **`cima_ve/fixtures/workspace.json`**: `Facturación Cima` workspace for sellers (`Sales User`).
- **`tests/`**: 11 unit tests (`test_cashea_simulator.py`, `test_fiscal_simulator.py`, `test_seller_pos.py`) — all passing.

---

## 5. Completed & Immediate Next Steps

1. **Completed:**
   - Committed and pushed `cima_ve` to `https://github.com/josephnowak/cima-erp-next` (`main`).
   - Migrated `cimaelectronicve.v.frappe.cloud` to Private Bench `bench-52215` (`bench-52215-000002-f94v`).
   - Deployed and installed `cima_ve` (`0.1.0`) on `cimaelectronicve.v.frappe.cloud`.
   - Verified `Cima VE Settings` (`simulation_mode=1`), `venta-rapida` page, `Facturación Cima` workspace, `get_seller_bootstrap`, and `search_inventory_and_prices` live.
2. **Remaining Configuration & Credentials:**
   - Verify `venta-rapida` page and `Facturación Cima` workspace visually in the ERPNext UI.
   - Set `CIMA ELECTRONIC VE` `tax_id` (RIF) in ERPNext.
   - Replace simulator endpoints/credentials in `Cima VE Settings`, `CasheaClient`, and `FiscalPrinterClient` once real Cashea and SENIAT Imprenta Digital API docs/credentials are available (keep Simulation Mode ON until then).
