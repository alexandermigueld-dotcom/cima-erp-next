# Cima VE (`cima-erp-next`)

Aplicación personalizada de Frappe/ERPNext v16 para **CIMA Electronic VE**, desplegada en Frappe Cloud (`https://cimaelectronicve.v.frappe.cloud`), orientada a:
- **Facturación Rápida (`venta-rapida`)**: POS simplificado para vendedores con emisión de **Notas de Entrega**, precios personalizados por ítem, descuentos automáticos/manuales, comisiones por margen y totales en USD y Bolívares (`Bs.`).
- **Notas de Entrega (`notas-entrega`)**: Flujo de pago diferido con abonos parciales, comprobantes/referencias, congelamiento histórico en Bs, reversión exclusiva para administradores (anula pagos/factura y restaura inventario, conservando la nota como `Cancelada`) y cálculo de comisiones por vendedor.
- **Tienda Web (`/tienda`)**: Catálogo público con stock real, proveedores de envío, login con email/Google y creación de Notas de Entrega con comprobante de pago.
- **Tasas de Cambio y Brecha**: Sincronización horaria de BCV, Monitor y Binance P2P (`USDT/VES`) con cálculo de brecha.
- **Métricas y Clientes (`metricas-ventas`, `clientes-consumo`)**: Reportes exclusivos para administradores (`System Manager`).
- **Cashea & Facturación Fiscal Digital SENIAT**: Clientes HTTP y modo simulación local.

> **Documentación técnica completa para agentes y desarrolladores:** consulta [`AGENTS.md`](AGENTS.md) y [`CONTEXT.md`](CONTEXT.md).

---

## 1. Cómo probar el simulador ahora mismo (sin plan de $25 USD)

Todo el núcleo de Cashea y la Imprenta Fiscal Digital incluye un **Modo Simulación** en Python estándar que funciona localmente:

```powershell
# Ejecutar demostración completa (Cashea + Webhook + Imprenta Fiscal Digital)
.\.venv\Scripts\python.exe demo_simulador.py

# Ejecutar pruebas automatizadas
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

---

## 2. Scripts de diagnóstico incluidos

- `diagnostico_erpnext.py`: Verifica conexión REST, versiones, almacenes, listas de precios, impuestos y conteo de documentos en ERPNext.
- `diagnostico_frappe_cloud.py`: Verifica estado de cuenta, sitio, plan y apps disponibles en Frappe Cloud.

---

## 3. Cómo instalar en Frappe Cloud cuando actives `Private Bench` ($25 USD)

1. Sube este repositorio a `https://github.com/josephnowak/cima-erp-next`.
2. En **Frappe Cloud** (`frappecloud.com`), vincula tu repositorio en tu **Private Bench** e instala la app `cima_ve` en tu sitio.
3. En ERPNext, entra a **Cima VE Settings**:
   - Deja activo **Modo Simulación** mientras no tengas las credenciales reales.
   - Cuando recibas tus llaves de **Cashea** y de tu **Imprenta Digital SENIAT**, cárgalas en **Cima VE Settings** y desmarca **Modo Simulación**.
