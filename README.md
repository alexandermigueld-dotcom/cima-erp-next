# Cima VE (`cima-erp-next`)

Aplicación personalizada de Frappe/ERPNext y entorno de simulación local para **CIMA Electronic VE**, orientada a:
- Pagos con **Cashea** (checkout + webhook firmado).
- **Facturación Fiscal Digital SENIAT** vía Imprenta Digital por API (IVA 16%, exentos e IGTF 3% en divisas).

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
