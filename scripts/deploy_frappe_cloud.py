"""Automated Frappe Cloud deployment script for cima_ve.

Triggers a cima_ve-only bench deploy on Frappe Cloud (Press API) and
optionally waits for completion and updates the target site.

Environment variables:
    FRAPPE_API_ACCESS_KEY: Frappe Cloud Press API key
    FRAPPE_API_SECRET: Frappe Cloud Press API secret
    FRAPPE_BENCH_NAME: Target bench (default: bench-52215)
    FRAPPE_SITE_NAME: Target site (default: erpnext-yfl-bqf.v.frappe.cloud)
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

PRESS_URL = "https://cloud.frappe.io"
DEFAULT_BENCH = "bench-52215"
DEFAULT_SITE = "erpnext-yfl-bqf.v.frappe.cloud"
APP_NAME = "cima_ve"


def load_dotenv(dotenv_path: Path) -> None:
    if not dotenv_path.exists():
        return
    for raw_line in dotenv_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, val = line.split("=", 1)
        key = key.strip()
        val = val.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = val


class PressClient:
    def __init__(self, access_key: str, api_secret: str, base_url: str = PRESS_URL) -> None:
        self.base_url = base_url.rstrip("/")
        self.auth_header = f"token {access_key}:{api_secret}"

    def post(self, method: str, payload: dict[str, Any]) -> tuple[int, dict[str, Any]]:
        url = f"{self.base_url}/api/method/{method}"
        body = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=body,
            method="POST",
            headers={
                "Authorization": self.auth_header,
                "Content-Type": "application/json",
                "Accept": "application/json",
                "User-Agent": "cima-ve-deploy/1.0",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                return resp.status, json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            raw = exc.read().decode("utf-8", errors="replace")
            try:
                return exc.code, json.loads(raw)
            except json.JSONDecodeError:
                return exc.code, {"error": raw}


def extract_cima_release(
    deploy_info: dict[str, Any], target_sha: str | None = None
) -> dict[str, str] | None:
    """Find the cima_ve release payload for press.api.bench.deploy."""
    apps = deploy_info.get("apps") or []
    cima = next((a for a in apps if a.get("name") == APP_NAME), None)
    if not cima:
        return None

    current_hash = cima.get("current_hash") or ""
    releases = cima.get("releases") or []
    if target_sha:
        for rel in releases:
            if (rel.get("hash") or "").startswith(target_sha):
                return {"name": APP_NAME, "release": rel["name"], "hash": rel["hash"]}

    if releases:
        latest = releases[0]
        if latest.get("hash") and latest.get("hash") != current_hash:
            return {"name": APP_NAME, "release": latest["name"], "hash": latest["hash"]}

    return None


def is_cima_up_to_date(deploy_info: dict[str, Any], target_sha: str | None = None) -> bool:
    apps = deploy_info.get("apps") or []
    cima = next((a for a in apps if a.get("name") == APP_NAME), None)
    if not cima:
        return False
    current_hash = cima.get("current_hash") or ""
    if target_sha:
        return current_hash.startswith(target_sha)
    return not bool(cima.get("update_available"))


def deploy(
    client: PressClient,
    bench: str,
    site: str,
    target_sha: str | None = None,
    wait_seconds: int = 0,
    poll_interval: int = 20,
) -> int:
    print(f"[1/4] Fetching latest {APP_NAME} update on {bench}...")
    st, res = client.post("press.api.bench.fetch_latest_app_update", {"name": bench, "app": APP_NAME})
    if st != 200:
        print(f"Warning: fetch_latest_app_update returned HTTP {st}: {res}")

    time.sleep(3)
    st, info_res = client.post("press.api.bench.deploy_information", {"name": bench})
    if st != 200:
        print(f"Error: deploy_information failed ({st}): {info_res}", file=sys.stderr)
        return 1

    info = info_res.get("message") or {}
    if is_cima_up_to_date(info, target_sha):
        print(f"{APP_NAME} is already up to date on {bench}.")
    elif info.get("deploy_in_progress"):
        last = info.get("last_deploy") or {}
        print(
            f"A bench deploy is already in progress ({last.get('name')} - {last.get('status')}). "
            "Skipping duplicate trigger; check Frappe Cloud Deploys tab."
        )
        if wait_seconds <= 0:
            return 0
    else:
        app_payload = extract_cima_release(info, target_sha)
        if not app_payload:
            print(f"No new {APP_NAME} release found to deploy on {bench}.")
        else:
            print(
                f"[2/4] Triggering cima_ve-only deploy: release={app_payload['release']} "
                f"hash={app_payload['hash'][:7]}..."
            )
            st_dep, res_dep = client.post(
                "press.api.bench.deploy",
                {"name": bench, "apps": [app_payload]},
            )
            if st_dep != 200:
                print(f"Error: bench.deploy failed ({st_dep}): {res_dep}", file=sys.stderr)
                return 1
            print(f"Deploy started: {res_dep.get('message')}")

    if wait_seconds > 0:
        print(f"[3/4] Waiting up to {wait_seconds}s for bench deploy to finish...")
        deadline = time.time() + wait_seconds
        while time.time() < deadline:
            st, info_res = client.post("press.api.bench.deploy_information", {"name": bench})
            info = info_res.get("message") or {}
            last = info.get("last_deploy") or {}
            if not info.get("deploy_in_progress"):
                print(f"Bench deploy finished with status: {last.get('status')}")
                break
            print(f"  Still {last.get('status')} ({last.get('name')})...")
            time.sleep(poll_interval)

    print(f"[4/4] Checking site updates for {site}...")
    st_chk, res_chk = client.post("press.api.site.check_for_updates", {"name": site})
    if st_chk == 200 and (res_chk.get("message") or {}).get("update_available"):
        st_upd, res_upd = client.post("press.api.site.update", {"name": site})
        print(f"Triggered site.update ({st_upd}): {res_upd}")
    else:
        print(f"Site update status ({st_chk}): {res_chk.get('message', res_chk)}")

    return 0


def main(argv: list[str] | None = None) -> int:
    load_dotenv(Path(".env"))
    parser = argparse.ArgumentParser(description="Deploy cima_ve on Frappe Cloud")
    parser.add_argument("--bench", default=os.environ.get("FRAPPE_BENCH_NAME", DEFAULT_BENCH))
    parser.add_argument("--site", default=os.environ.get("FRAPPE_SITE_NAME", DEFAULT_SITE))
    parser.add_argument("--sha", default=os.environ.get("GITHUB_SHA", "").strip() or None)
    parser.add_argument("--wait", type=int, default=0, help="Seconds to wait for bench build")
    args = parser.parse_args(argv)

    key = os.environ.get("FRAPPE_API_ACCESS_KEY", "").strip()
    secret = os.environ.get("FRAPPE_API_SECRET", "").strip()
    if not key or not secret:
        print(
            "FRAPPE_API_ACCESS_KEY / FRAPPE_API_SECRET not set; skipping Frappe Cloud deploy.",
            file=sys.stderr,
        )
        return 1

    client = PressClient(key, secret)
    return deploy(client, args.bench, args.site, target_sha=args.sha, wait_seconds=args.wait)


if __name__ == "__main__":
    raise SystemExit(main())
