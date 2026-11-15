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


class FrappeCloudClient:
    def __init__(self, auth_header: str, base_url: str = "https://cloud.frappe.io") -> None:
        self.base_url = base_url.rstrip("/")
        self.auth_header = auth_header

    def request(
        self,
        method: str,
        path: str,
        params: dict | None = None,
        payload: dict | None = None,
    ) -> tuple[int, dict | list | str]:
        url = f"{self.base_url}{path}"
        if params:
            url = f"{url}?{urllib.parse.urlencode(params)}"
        data = None
        headers = {
            "Authorization": self.auth_header,
            "Accept": "application/json",
            "User-Agent": "cima-erp-next/1.0",
        }
        if payload is not None:
            data = json.dumps(payload).encode("utf-8")
            headers["Content-Type"] = "application/json"

        req = urllib.request.Request(url, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=25) as resp:
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


def resolve_auth_header(raw_value: str) -> list[str]:
    val = raw_value.strip()
    lower = val.lower()
    if lower.startswith("token ") or lower.startswith("bearer "):
        return [val]
    if ":" in val:
        return [f"token {val}", f"Token {val}"]
    return [f"Bearer {val}", f"token {val}", f"Token {val}"]


def main() -> int:
    load_dotenv(Path(__file__).resolve().parent / ".env")
    fc_key = (
        os.environ.get("FRAPPE_API_ACCESS_KEY", "").strip()
        or os.environ.get("FC_API_KEY", "").strip()
    )
    fc_secret = (
        os.environ.get("FRAPPE_API_SECRET", "").strip()
        or os.environ.get("FC_API_SECRET", "").strip()
    )
    raw_access = os.environ.get("FRAPPE_API_ACCESS", "").strip()

    if fc_key and fc_secret:
        raw_access = f"{fc_key}:{fc_secret}"

    if not raw_access:
        print("ERROR: Falta FRAPPE_API_ACCESS (en formato api_key:api_secret) o FC_API_KEY + FC_API_SECRET en .env")
        return 1

    if ":" not in raw_access and not raw_access.lower().startswith("bearer "):
        print(
            "ERROR: FRAPPE_API_ACCESS contiene un solo valor de "
            f"{len(raw_access)} caracteres sin ':'.\n"
            "Frappe Cloud genera dos claves de 56 caracteres (API Key y API Secret).\n"
            "Coloca FRAPPE_API_ACCESS=<API_KEY>:<API_SECRET> (o usa FC_API_KEY y FC_API_SECRET) en .env."
        )
        return 1

    client: FrappeCloudClient | None = None
    user_info = None
    last_error = None

    attempts = []
    for header in resolve_auth_header(raw_access):
        scheme = header.split()[0]
        candidate = FrappeCloudClient(header)
        for method, test_path in (
            ("POST", "/api/method/press.api.site.all"),
            ("POST", "/api/method/press.api.account.get"),
            ("GET", "/api/method/frappe.auth.get_logged_user"),
        ):
            status, resp = candidate.request(
                method,
                test_path,
                payload={} if method == "POST" else None,
            )
            attempts.append((scheme, method, test_path, status, resp))
            if status == 200 and isinstance(resp, dict) and resp.get("message") not in (None, "Guest"):
                client = candidate
                user_info = resp.get("message") if "get_logged_user" in test_path else f"OK via {test_path}"
                break
        if client is not None:
            break

    if client is None:
        print("Fallo de autenticación contra frappecloud.com. Detalle de intentos:")
        for scheme, method, test_path, status, resp in attempts:
            print(f"- {scheme} {method} {test_path} -> HTTP {status}: {resp}")
        return 1

    print("=== 1. CONEXIÓN FRAPPE CLOUD ===")
    print("Usuario autenticado:", user_info)

    print("\n=== 2. CUENTA Y EQUIPO ===")
    for method_path in (
        "/api/method/press.api.account.get",
        "/api/method/press.api.team.get",
    ):
        status, data = client.request("GET", method_path)
        print(f"{method_path} -> HTTP {status}")
        if status == 200:
            print(json.dumps(data, indent=2, ensure_ascii=False)[:1500])

    print("\n=== 3. SITIOS EN LA CUENTA ===")
    status, sites = client.request("POST", "/api/method/press.api.site.all", payload={})
    if status != 200:
        status, sites = client.request("GET", "/api/method/press.api.site.all")
    print(f"press.api.site.all -> HTTP {status}")
    print(json.dumps(sites, indent=2, ensure_ascii=False))

    site_name = "cimaelectronicve.v.frappe.cloud"
    if isinstance(sites, dict) and isinstance(sites.get("message"), list) and sites["message"]:
        first_site = sites["message"][0]
        site_name = first_site.get("name") or site_name
        host_name = first_site.get("host_name") or site_name
        print(f"\n=== 4. DETALLE DEL SITIO ({site_name} / {host_name}) ===")
    else:
        print(f"\n=== 4. DETALLE DEL SITIO ({site_name}) ===")

    st_site, res_site = client.request("POST", "/api/method/press.api.site.get", payload={"name": site_name})
    print(f"\n/api/method/press.api.site.get -> HTTP {st_site}")
    if st_site == 200 and isinstance(res_site, dict) and isinstance(res_site.get("message"), dict):
        site_doc = res_site["message"]
        summary = {
            "name": site_doc.get("name"),
            "host_name": site_doc.get("host_name"),
            "status": site_doc.get("status"),
            "bench": site_doc.get("bench"),
            "version": site_doc.get("version"),
            "plan": site_doc.get("plan", {}).get("name") if isinstance(site_doc.get("plan"), dict) else site_doc.get("plan"),
            "private_benches": site_doc.get("plan", {}).get("private_benches") if isinstance(site_doc.get("plan"), dict) else None,
            "installed_apps": site_doc.get("apps") or site_doc.get("installed_apps"),
            "config": site_doc.get("config"),
        }
        print(json.dumps(summary, indent=2, ensure_ascii=False))
    else:
        print(json.dumps(res_site, indent=2, ensure_ascii=False)[:2000])

    st_apps, res_apps = client.request("POST", "/api/method/press.api.site.available_apps", payload={"name": site_name})
    print(f"\n/api/method/press.api.site.available_apps -> HTTP {st_apps}")
    if st_apps == 200 and isinstance(res_apps, dict) and isinstance(res_apps.get("message"), list):
        apps_list = res_apps["message"]
        print(f"Total apps disponibles en Marketplace/bench: {len(apps_list)}")
        filtered = [
            {
                "name": app.get("name"),
                "title": app.get("title"),
                "plans": [
                    {"name": p.get("name"), "price_usd": p.get("price_usd")}
                    for p in (app.get("plans") or [])
                ],
            }
            for app in apps_list
            if str(app.get("name", "")).lower() in ("webshop", "payments", "erpnext", "frappe")
            or "webshop" in str(app.get("name", "")).lower()
            or "payment" in str(app.get("name", "")).lower()
        ]
        print("Apps relevantes (webshop / payments):", json.dumps(filtered, indent=2, ensure_ascii=False))
    else:
        print(json.dumps(res_apps, indent=2, ensure_ascii=False)[:2000])

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
