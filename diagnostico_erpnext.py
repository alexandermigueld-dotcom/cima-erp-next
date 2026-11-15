import json
import os
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path


def load_dotenv(env_path: Path) -> None:
    if not env_path.exists():
        return
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


class ERPNextClient:
    def __init__(self, base_url: str, api_key: str, api_secret: str) -> None:
        self.base_url = base_url.rstrip("/")
        self.auth_header = f"token {api_key}:{api_secret}"

    def get(self, path: str, params: dict | None = None) -> tuple[int, dict | list | str]:
        url = f"{self.base_url}{path}"
        if params:
            url = f"{url}?{urllib.parse.urlencode(params)}"
        req = urllib.request.Request(
            url,
            headers={
                "Authorization": self.auth_header,
                "Accept": "application/json",
            },
            method="GET",
        )
        try:
            with urllib.request.urlopen(req, timeout=20) as resp:
                body = resp.read().decode("utf-8", errors="replace")
                try:
                    return resp.status, json.loads(body)
                except json.JSONDecodeError:
                    return resp.status, body
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            try:
                return exc.code, json.loads(body)
            except json.JSONDecodeError:
                return exc.code, body


def get_count(client: ERPNextClient, doctype: str) -> int | str:
    status, data = client.get(
        "/api/method/frappe.client.get_count",
        {"doctype": doctype},
    )
    if status == 200 and isinstance(data, dict) and "message" in data:
        return data["message"]
    return f"error ({status})"


def get_list(
    client: ERPNextClient,
    doctype: str,
    fields: list[str] | None = None,
    limit: int = 20,
) -> list | str:
    params: dict[str, str | int] = {"limit_page_length": limit}
    if fields:
        params["fields"] = json.dumps(fields)
    status, data = client.get(f"/api/resource/{urllib.parse.quote(doctype)}", params)
    if status == 200 and isinstance(data, dict) and "data" in data:
        return data["data"]
    return f"error ({status})"


def main() -> int:
    load_dotenv(Path(__file__).resolve().parent / ".env")

    base_url = os.environ.get("ERPNEXT_URL", "").strip()
    api_key = os.environ.get("API_KEY", "").strip()
    api_secret = (
        os.environ.get("SECRET_API", "").strip()
        or os.environ.get("API_SECRET", "").strip()
    )

    if not base_url:
        print("ERROR: Falta ERPNEXT_URL en .env o en las variables de entorno.")
        return 1
    if not api_key or not api_secret:
        print("ERROR: Faltan API_KEY o SECRET_API en .env.")
        return 1

    client = ERPNextClient(base_url, api_key, api_secret)

    print("=== 1. CONEXIÓN Y USUARIO ===")
    status, user_resp = client.get("/api/method/frappe.auth.get_logged_user")
    if status != 200:
        print(f"Fallo de autenticación o conexión (HTTP {status}): {user_resp}")
        return 1
    print("Usuario autenticado:", user_resp.get("message") if isinstance(user_resp, dict) else user_resp)
    print("URL:", base_url)

    print("\n=== 2. VERSIONES Y APPS INSTALADAS ===")
    status, versions = client.get("/api/method/frappe.utils.change_log.get_versions")
    if status == 200 and isinstance(versions, dict):
        print(json.dumps(versions.get("message", versions), indent=2, ensure_ascii=False))
    else:
        print(f"No se pudo obtener get_versions (HTTP {status}): {versions}")

    apps = get_list(client, "Installed Application", ["app_name", "app_version", "git_branch"], limit=50)
    print("Installed Application:", json.dumps(apps, indent=2, ensure_ascii=False) if isinstance(apps, list) else apps)

    print("\n=== 3. EMPRESAS Y CONFIGURACIÓN FISCAL BASE ===")
    companies = get_list(client, "Company", ["name", "country", "default_currency", "tax_id"], limit=20)
    print("Empresas:", json.dumps(companies, indent=2, ensure_ascii=False) if isinstance(companies, list) else companies)

    taxes = get_list(client, "Sales Taxes and Charges Template", ["name", "company", "is_default", "disabled"], limit=20)
    print("Plantillas de impuestos de venta:", json.dumps(taxes, indent=2, ensure_ascii=False) if isinstance(taxes, list) else taxes)

    price_lists = get_list(client, "Price List", ["name", "currency", "selling", "buying", "enabled"], limit=20)
    print("Listas de precios:", json.dumps(price_lists, indent=2, ensure_ascii=False) if isinstance(price_lists, list) else price_lists)

    warehouses = get_list(client, "Warehouse", ["name", "company", "is_group", "disabled"], limit=30)
    print("Almacenes:", json.dumps(warehouses, indent=2, ensure_ascii=False) if isinstance(warehouses, list) else warehouses)

    print("\n=== 4. VOLUMEN ACTUAL DE DATOS ===")
    for doctype in ("Item", "Customer", "Sales Order", "Sales Invoice", "Payment Entry"):
        print(f"- {doctype}: {get_count(client, doctype)}")

    print("\n=== 5. CAPACIDAD DE PERSONALIZACIÓN ===")
    for doctype in ("Custom Field", "Webhook", "Server Script", "Client Script"):
        print(f"- {doctype}: {get_count(client, doctype)}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
