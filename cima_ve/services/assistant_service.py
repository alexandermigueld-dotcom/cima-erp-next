from __future__ import annotations

import base64
import csv
import io
import json
import posixpath
import re
import unicodedata
import urllib.error
import urllib.request
import zipfile
from typing import Callable
from urllib.parse import urlparse
from xml.etree import ElementTree

MAX_UPLOAD_BYTES = 4 * 1024 * 1024
MAX_IMPORT_ROWS = 250
MAX_WORKBOOK_UNCOMPRESSED_BYTES = 12 * 1024 * 1024
MAX_REPOSITORY_FILE_CHARS = 6000

DEFAULT_MODELS = {
    "openai": "gpt-4o-mini",
    "anthropic": "claude-3-5-haiku-latest",
    "gemini": "gemini-2.0-flash",
}

_PROVIDER_URLS = {
    "openai": "https://api.openai.com/v1/chat/completions",
    "anthropic": "https://api.anthropic.com/v1/messages",
    "gemini": "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
}
_REPOSITORY_BASE_URL = "https://raw.githubusercontent.com/josephnowak/cima-erp-next/main"
_REPOSITORY_FILES = ("README.md", "CONTEXT.md", "AGENTS.md")
_HEADER_ALIASES = {
    "item_name": {"item_name", "product_name", "name", "nombre", "producto", "nombre_producto"},
    "item_code": {"item_code", "sku", "code", "codigo", "codigo_producto"},
    "item_group": {"item_group", "category", "categoria", "grupo", "grupo_articulo"},
    "stock_uom": {"stock_uom", "uom", "unit", "unidad", "unidad_medida"},
    "cost_rate": {"cost_rate", "cost", "costo", "costo_unitario"},
    "detal_price": {"detal_price", "retail_price", "price_retail", "precio_detal", "precio"},
    "mayor_price": {"mayor_price", "wholesale_price", "precio_mayor"},
    "initial_qty": {"initial_qty", "qty", "quantity", "stock", "cantidad", "cantidad_inicial"},
    "warehouse": {"warehouse", "almacen", "almacen_inicial"},
    "description": {"description", "descripcion"},
    "show_in_website": {"show_in_website", "published", "publicar", "visible_web"},
}


def _normalize_header(value: object) -> str:
    text = unicodedata.normalize("NFKD", str(value or "")).encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")


def _canonicalize_row(row: dict) -> dict:
    aliases = {alias: key for key, values in _HEADER_ALIASES.items() for alias in values}
    cleaned = {}
    for key, value in row.items():
        canonical = aliases.get(_normalize_header(key))
        if canonical:
            cleaned[canonical] = str(value or "").strip()
    return cleaned


def _column_index(cell_reference: str) -> int:
    letters = re.match(r"[A-Z]+", cell_reference.upper())
    if not letters:
        return 0
    result = 0
    for char in letters.group(0):
        result = result * 26 + ord(char) - ord("A") + 1
    return result - 1


def _parse_xlsx(content: bytes) -> list[dict]:
    main_ns = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
    office_rel_ns = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
    package_rel_ns = "http://schemas.openxmlformats.org/package/2006/relationships"
    try:
        archive = zipfile.ZipFile(io.BytesIO(content))
    except (zipfile.BadZipFile, OSError) as exc:
        raise ValueError("El archivo XLSX no es válido.") from exc

    with archive:
        entries = archive.infolist()
        if len(entries) > 500 or sum(entry.file_size for entry in entries) > MAX_WORKBOOK_UNCOMPRESSED_BYTES:
            raise ValueError("El archivo XLSX excede el límite permitido.")
        names = set(archive.namelist())
        if "xl/workbook.xml" not in names or "[Content_Types].xml" not in names:
            raise ValueError("El archivo no contiene un libro XLSX válido.")
        if "xl/vbaProject.bin" in names:
            raise ValueError("No se permiten libros con macros.")

        def read_xml(path: str):
            raw_xml = archive.read(path)
            if b"<!DOCTYPE" in raw_xml.upper() or b"<!ENTITY" in raw_xml.upper():
                raise ValueError("El archivo XLSX contiene declaraciones XML no permitidas.")
            return ElementTree.fromstring(raw_xml)

        workbook = read_xml("xl/workbook.xml")
        first_sheet = workbook.find(f".//{{{main_ns}}}sheet")
        if first_sheet is None:
            raise ValueError("El archivo XLSX no contiene hojas.")
        relationship_id = first_sheet.attrib.get(f"{{{office_rel_ns}}}id", "")

        relationship_path = "xl/_rels/workbook.xml.rels"
        if relationship_path not in names:
            raise ValueError("No se encontró la primera hoja del archivo XLSX.")
        relationships = read_xml(relationship_path)
        target = ""
        for relation in relationships.findall(f"{{{package_rel_ns}}}Relationship"):
            if relation.attrib.get("Id") == relationship_id:
                target = relation.attrib.get("Target", "")
                break
        if not target:
            raise ValueError("No se encontró la primera hoja del archivo XLSX.")
        sheet_path = target.lstrip("/") if target.startswith("/") else posixpath.normpath(posixpath.join("xl", target))
        if not sheet_path.startswith("xl/worksheets/") or sheet_path not in names:
            raise ValueError("La ruta de la hoja XLSX no es válida.")

        shared_strings = []
        if "xl/sharedStrings.xml" in names:
            shared_root = read_xml("xl/sharedStrings.xml")
            for entry in shared_root.findall(f"{{{main_ns}}}si"):
                shared_strings.append("".join(node.text or "" for node in entry.iter(f"{{{main_ns}}}t")))

        sheet = read_xml(sheet_path)
        sheet_data = sheet.find(f"{{{main_ns}}}sheetData")
        raw_rows = []
        if sheet_data is not None:
            for row_element in sheet_data.findall(f"{{{main_ns}}}row"):
                values = {}
                for cell in row_element.findall(f"{{{main_ns}}}c"):
                    column = _column_index(cell.attrib.get("r", ""))
                    value_element = cell.find(f"{{{main_ns}}}v")
                    cell_type = cell.attrib.get("t", "")
                    if cell_type == "inlineStr":
                        value = "".join(node.text or "" for node in cell.iter(f"{{{main_ns}}}t"))
                    elif value_element is None:
                        value = ""
                    elif cell_type == "s":
                        try:
                            value = shared_strings[int(value_element.text or "")]
                        except (ValueError, IndexError):
                            value = ""
                    else:
                        value = value_element.text or ""
                    values[column] = value
                raw_rows.append(values)

    if not raw_rows:
        raise ValueError("El archivo XLSX está vacío.")
    headers = raw_rows[0]
    records = []
    for row in raw_rows[1:]:
        record = {str(headers.get(column, "")): value for column, value in row.items()}
        if any(str(value).strip() for value in record.values()):
            records.append(_canonicalize_row(record))
            if len(records) > MAX_IMPORT_ROWS:
                raise ValueError(f"El archivo supera el máximo de {MAX_IMPORT_ROWS} productos por carga.")
    return records


def parse_inventory_upload(filename: str, file_data_base64: str) -> list[dict]:
    """Decode a bounded CSV/XLSX upload into allowlisted product fields only."""
    extension = str(filename or "").rsplit(".", 1)[-1].lower()
    if extension not in {"csv", "xlsx"}:
        raise ValueError("Usa un archivo CSV o XLSX.")
    encoded = str(file_data_base64 or "").strip()
    if encoded.startswith("data:") and "," in encoded:
        encoded = encoded.split(",", 1)[1]
    if len(encoded) > ((MAX_UPLOAD_BYTES + 2) // 3) * 4 + 8:
        raise ValueError("El archivo supera el límite de 4 MB.")
    try:
        content = base64.b64decode(encoded, validate=True)
    except (ValueError, base64.binascii.Error) as exc:
        raise ValueError("No se pudo leer el archivo cargado.") from exc
    if not content:
        raise ValueError("El archivo está vacío.")
    if len(content) > MAX_UPLOAD_BYTES:
        raise ValueError("El archivo supera el límite de 4 MB.")

    if extension == "csv":
        try:
            text = content.decode("utf-8-sig")
        except UnicodeDecodeError as exc:
            raise ValueError("El CSV debe estar guardado en formato UTF-8.") from exc
        try:
            try:
                dialect = csv.Sniffer().sniff(text[:8192], delimiters=",;\t")
            except csv.Error:
                dialect = csv.excel
            reader = csv.DictReader(io.StringIO(text, newline=""), dialect=dialect)
            if not reader.fieldnames:
                raise ValueError("El CSV debe incluir encabezados en la primera fila.")
            rows = []
            for row in reader:
                if any(str(value or "").strip() for value in row.values()):
                    rows.append(_canonicalize_row(row))
                    if len(rows) > MAX_IMPORT_ROWS:
                        raise ValueError(f"El archivo supera el máximo de {MAX_IMPORT_ROWS} productos por carga.")
        except csv.Error as exc:
            raise ValueError("No se pudo interpretar el CSV.") from exc
    else:
        try:
            rows = _parse_xlsx(content)
        except (ElementTree.ParseError, KeyError, RuntimeError, zipfile.BadZipFile) as exc:
            raise ValueError("El archivo XLSX está dañado o no es válido.") from exc

    if not rows:
        raise ValueError("El archivo no contiene filas de productos.")
    if len(rows) > MAX_IMPORT_ROWS:
        raise ValueError(f"El archivo supera el máximo de {MAX_IMPORT_ROWS} productos por carga.")
    return rows


def prepare_inventory_import(rows: list[dict], warehouse: str = "", existing_item_codes: set[str] | None = None) -> dict:
    """Validate import rows and detect duplicates without performing writes."""
    from cima_ve.services.product_service import validate_new_product_input

    if not isinstance(rows, list) or not rows or len(rows) > MAX_IMPORT_ROWS:
        raise ValueError(f"La carga debe incluir entre 1 y {MAX_IMPORT_ROWS} productos.")

    existing = {str(code).strip().upper() for code in (existing_item_codes or set())}
    seen = set()
    products = []
    preview_rows = []
    has_errors = False
    for index, row in enumerate(rows, start=2):
        preset_errors = (row or {}).get("_import_errors", []) if isinstance(row, dict) else []
        errors = [str(error) for error in preset_errors if error]
        try:
            payload = dict(row or {})
            payload["warehouse"] = warehouse or payload.get("warehouse", "")
            if payload.get("show_in_website") in (None, ""):
                payload["show_in_website"] = 0
            cleaned = validate_new_product_input(payload)
            code_key = cleaned["item_code"].upper()
            if code_key in seen:
                errors.append("El código está repetido en el archivo.")
            elif code_key in existing:
                errors.append("El código del producto ya existe.")
            seen.add(code_key)
        except (TypeError, ValueError) as exc:
            cleaned = None
            errors.append(str(exc))

        if errors:
            has_errors = True
        else:
            products.append(cleaned)
        preview_rows.append(
            {
                "row": index,
                "item_code": cleaned.get("item_code", "") if cleaned else str((row or {}).get("item_code", "")),
                "item_name": cleaned.get("item_name", "") if cleaned else str((row or {}).get("item_name", "")),
                "description": cleaned["description"] if cleaned else str((row or {}).get("description", "")),
                "item_group": cleaned.get("item_group", "") if cleaned else str((row or {}).get("item_group", "")),
                "stock_uom": cleaned.get("stock_uom", "") if cleaned else str((row or {}).get("stock_uom", "")),
                "cost_rate": cleaned.get("cost_rate", 0) if cleaned else (row or {}).get("cost_rate", ""),
                "detal_price": cleaned.get("detal_price", 0) if cleaned else (row or {}).get("detal_price", ""),
                "mayor_price": cleaned.get("mayor_price", 0) if cleaned else (row or {}).get("mayor_price", ""),
                "initial_qty": cleaned.get("initial_qty", 0) if cleaned else (row or {}).get("initial_qty", ""),
                "warehouse": cleaned.get("warehouse", "") if cleaned else warehouse,
                "show_in_website": cleaned.get("show_in_website", False) if cleaned else False,
                "errors": errors,
            }
        )

    return {"rows": preview_rows, "products": products if not has_errors else [], "has_errors": has_errors}


def parse_assistant_response(text: str) -> dict:
    """Accept an optional product proposal but never pass through operational fields."""
    text = text.strip()
    fenced = re.fullmatch(r"```(?:json)?\s*(.*?)\s*```", text, re.IGNORECASE | re.DOTALL)
    try:
        response = json.loads(fenced[1] if fenced else text)
    except json.JSONDecodeError:
        return {"answer": text}
    if not isinstance(response, dict) or not isinstance(response.get("answer"), str) or not response["answer"].strip():
        return {"answer": text}

    result = {"answer": response["answer"].strip()}
    raw_draft = response.get("product_draft")
    if isinstance(raw_draft, dict):
        draft = {
            field: raw_draft[field].strip()[:limit]
            for field, limit in (("item_name", 140), ("item_code", 60), ("description", 1000))
            if isinstance(raw_draft.get(field), str) and raw_draft[field].strip()
        }
        if draft.get("item_name"):
            result["product_draft"] = draft
    return result


def normalize_chat_history(messages: object) -> list[dict[str, str]]:
    if not isinstance(messages, list):
        return []
    normalized = []
    for entry in messages[-8:]:
        if not isinstance(entry, dict) or entry.get("role") not in {"user", "assistant"}:
            continue
        content = str(entry.get("content") or "").strip()
        if content:
            normalized.append({"role": entry["role"], "content": content[:2000]})
    return normalized


def build_provider_request(provider: str, model: str, api_key: str, system_prompt: str, messages: list[dict]) -> tuple[str, dict, dict]:
    """Build a request for one of three fixed provider endpoints."""
    provider_key = str(provider or "").strip().lower()
    if provider_key not in _PROVIDER_URLS:
        raise ValueError("Selecciona un proveedor de IA compatible.")
    if not str(api_key or "").strip():
        raise ValueError("Configura la clave API del proveedor seleccionado.")
    model_name = str(model or DEFAULT_MODELS[provider_key]).strip()
    if not re.fullmatch(r"[A-Za-z0-9._-]{1,100}", model_name):
        raise ValueError("El identificador del modelo no es válido.")
    safe_messages = normalize_chat_history(messages)
    if not safe_messages:
        raise ValueError("Escribe una pregunta para el asistente.")

    if provider_key == "openai":
        url = _PROVIDER_URLS[provider_key]
        headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
        payload = {
            "model": model_name,
            "messages": [{"role": "system", "content": system_prompt}, *safe_messages],
            "temperature": 0.2,
            "max_tokens": 900,
        }
    elif provider_key == "anthropic":
        url = _PROVIDER_URLS[provider_key]
        headers = {"x-api-key": api_key, "anthropic-version": "2023-06-01", "Content-Type": "application/json"}
        payload = {
            "model": model_name,
            "max_tokens": 900,
            "system": system_prompt,
            "messages": safe_messages,
        }
    else:
        url = _PROVIDER_URLS[provider_key].format(model=model_name)
        headers = {"x-goog-api-key": api_key, "Content-Type": "application/json"}
        payload = {
            "systemInstruction": {"parts": [{"text": system_prompt}]},
            "contents": [
                {"role": "model" if message["role"] == "assistant" else "user", "parts": [{"text": message["content"]}]}
                for message in safe_messages
            ],
            "generationConfig": {"temperature": 0.2, "maxOutputTokens": 900},
        }
    return url, headers, payload


def extract_provider_text(provider: str, response: dict) -> str:
    provider_key = str(provider or "").strip().lower()
    if not isinstance(response, dict):
        raise ValueError("El proveedor devolvió una respuesta inválida.")
    try:
        if provider_key == "openai":
            text = response.get("choices", [{}])[0].get("message", {}).get("content", "")
        elif provider_key == "anthropic":
            text = "\n".join(block.get("text", "") for block in response.get("content", []) if block.get("type") == "text")
        elif provider_key == "gemini":
            parts = response.get("candidates", [{}])[0].get("content", {}).get("parts", [])
            text = "\n".join(part.get("text", "") for part in parts if isinstance(part, dict))
        else:
            raise ValueError("Proveedor de IA no compatible.")
    except (AttributeError, IndexError, TypeError) as exc:
        raise ValueError("El proveedor devolvió una respuesta inválida.") from exc
    cleaned = str(text or "").strip()
    if not cleaned:
        raise ValueError("El proveedor no devolvió una respuesta de texto.")
    return cleaned[:12000]


def call_ai_provider(provider: str, model: str, api_key: str, system_prompt: str, messages: list[dict]) -> str:
    url, headers, payload = build_provider_request(provider, model, api_key, system_prompt, messages)
    request = urllib.request.Request(
        url,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=25) as response:
            raw = response.read(1024 * 1024 + 1)
        if len(raw) > 1024 * 1024:
            raise ValueError("La respuesta del proveedor excede el tamaño permitido.")
        parsed = json.loads(raw.decode("utf-8"))
        if not isinstance(parsed, dict):
            raise ValueError("El proveedor devolvió una respuesta inválida.")
    except urllib.error.HTTPError as exc:
        details = exc.read(1000).decode("utf-8", errors="replace")
        raise ValueError(f"El proveedor de IA respondió HTTP {exc.code}: {details[:500]}") from exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise ValueError("No se pudo conectar con el proveedor de IA.") from exc
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("El proveedor devolvió una respuesta inválida.") from exc
    return extract_provider_text(provider, parsed)


def fetch_public_repository_context(fetcher: Callable[[str], str] | None = None) -> str:
    """Fetch only the repository's fixed public documentation allowlist."""
    def fetch(url: str) -> str:
        request = urllib.request.Request(url, headers={"User-Agent": "Cima-VE-Assistant/1.0"})
        with urllib.request.urlopen(request, timeout=5) as response:
            final_url = urlparse(response.geturl())
            if final_url.scheme != "https" or final_url.hostname != "raw.githubusercontent.com":
                raise ValueError("Repositorio respondió desde un host no permitido.")
            raw = response.read(MAX_REPOSITORY_FILE_CHARS * 4 + 1)
        return raw.decode("utf-8", errors="replace")[:MAX_REPOSITORY_FILE_CHARS]

    sections = []
    for path in _REPOSITORY_FILES:
        url = f"{_REPOSITORY_BASE_URL}/{path}"
        try:
            content = (fetcher or fetch)(url)
        except Exception:
            continue
        if content:
            sections.append(f"### {path}\n{str(content)[:MAX_REPOSITORY_FILE_CHARS]}")
    return "\n\n".join(sections)