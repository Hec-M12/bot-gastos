"""Lee screenshots de compras con la IA que elijas (opcional).

Proveedores: gemini (tiene capa gratis), openai, anthropic. Se elige con
VISION_PROVEEDOR en .env; si no lo ponés, se usa la primera llave que encuentre.
Sin ninguna llave, el bot funciona igual con texto y correo.
"""
from __future__ import annotations

import base64
import json
import logging
import re
import urllib.error
import urllib.request
from pathlib import Path

logger = logging.getLogger("bot-gastos")

MODELOS = {
    "gemini": "gemini-3.5-flash-lite",
    "openai": "gpt-6-luna",
    "anthropic": "claude-haiku-4-5",
}
LLAVES = {"gemini": "GEMINI_API_KEY", "openai": "OPENAI_API_KEY", "anthropic": "ANTHROPIC_API_KEY"}
TIMEOUT = 60

PROMPT = (
    "La imagen es una captura de una compra: notificación del banco, recibo, comprobante de pago o "
    "transferencia, o la app de una tienda. Devolvé SOLO un objeto JSON, sin texto alrededor, con estas claves:\n"
    '{"monto": <número del TOTAL pagado, sin símbolo ni separador de miles, o null si no hay>, '
    '"moneda": "<código de 3 letras (USD, HNL, GTQ, MXN…) o el símbolo que se ve, o null>", '
    '"comercio": "<dónde se compró o a quién se le pagó, corto, o null>", '
    '"es_gasto": <true si la plata SALE de la persona, false si le ENTRA>}\n'
    "Si hay varios montos, usá el total. No inventes: si no se ve, poné null."
)


class ErrorDeVision(Exception):
    """Algo salió mal leyendo la imagen, explicado para humanos."""


def proveedor(env: dict) -> tuple[str, str, str] | None:
    """(nombre, llave, modelo) del proveedor configurado, o None si no hay llave."""
    elegido = (env.get("VISION_PROVEEDOR") or "").strip().lower()
    orden = [elegido] if elegido else ["gemini", "openai", "anthropic"]
    for nombre in orden:
        if nombre not in LLAVES:
            continue
        llave = (env.get(LLAVES[nombre]) or "").strip()
        if llave:
            return nombre, llave, (env.get("VISION_MODELO") or "").strip() or MODELOS[nombre]
    return None


def _mime(ruta: Path) -> str:
    return {".png": "image/png", ".webp": "image/webp", ".gif": "image/gif"}.get(ruta.suffix.lower(), "image/jpeg")


def _post(url: str, cuerpo: dict, headers: dict, http=None) -> dict:
    req = urllib.request.Request(url, data=json.dumps(cuerpo).encode(), headers={"Content-Type": "application/json", **headers})
    abrir = http or urllib.request.urlopen
    try:
        with abrir(req, timeout=TIMEOUT) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        if exc.code == 429:
            raise ErrorDeVision("Se acabó la cuota de la IA por ahora (demasiadas fotos o límite del plan gratis). "
                                "Probá más tarde o mandámelo en texto.") from None
        if exc.code in (401, 403):
            raise ErrorDeVision("La llave de la IA no funciona. Revisá la llave en el archivo .env.") from None
        if exc.code == 404:
            raise ErrorDeVision("La IA no reconoce el modelo. Revisá VISION_MODELO en .env (o borralo para usar el de siempre).") from None
        raise ErrorDeVision(f"La IA contestó con error {exc.code}. Probá de nuevo o mandámelo en texto.") from None
    except (urllib.error.URLError, OSError, json.JSONDecodeError) as exc:
        raise ErrorDeVision(f"No pude hablar con la IA ({exc}). ¿Hay internet?") from None


def _texto_gemini(r: dict) -> str:
    partes = ((r.get("candidates") or [{}])[0].get("content") or {}).get("parts") or []
    return "".join(p.get("text", "") for p in partes)


def _texto_openai(r: dict) -> str:
    return ((r.get("choices") or [{}])[0].get("message") or {}).get("content") or ""


def _texto_anthropic(r: dict) -> str:
    return "".join(b.get("text", "") for b in r.get("content") or [] if b.get("type") == "text")


def pedir(nombre: str, llave: str, modelo: str, imagen: bytes, mime: str, http=None) -> str:
    """Manda la imagen al proveedor y devuelve el texto que contestó."""
    b64 = base64.b64encode(imagen).decode()
    if nombre == "gemini":
        r = _post(f"https://generativelanguage.googleapis.com/v1beta/models/{modelo}:generateContent",
                  {"contents": [{"parts": [{"text": PROMPT}, {"inline_data": {"mime_type": mime, "data": b64}}]}],
                   "generationConfig": {"responseMimeType": "application/json"}},
                  {"x-goog-api-key": llave}, http)
        return _texto_gemini(r)
    if nombre == "openai":
        r = _post("https://api.openai.com/v1/chat/completions",
                  {"model": modelo, "response_format": {"type": "json_object"},
                   "messages": [{"role": "user", "content": [
                       {"type": "text", "text": PROMPT},
                       {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{b64}"}}]}]},
                  {"Authorization": f"Bearer {llave}"}, http)
        return _texto_openai(r)
    if nombre == "anthropic":
        r = _post("https://api.anthropic.com/v1/messages",
                  {"model": modelo, "max_tokens": 1024, "messages": [{"role": "user", "content": [
                      {"type": "image", "source": {"type": "base64", "media_type": mime, "data": b64}},
                      {"type": "text", "text": PROMPT}]}]},
                  {"x-api-key": llave, "anthropic-version": "2023-06-01"}, http)
        return _texto_anthropic(r)
    raise ErrorDeVision(f"No conozco el proveedor {nombre!r}. Usá gemini, openai o anthropic.")


def interpretar_respuesta(texto: str) -> dict | None:
    m = re.search(r"\{.*\}", texto or "", re.S)
    if not m:
        return None
    try:
        d = json.loads(m.group(0))
    except json.JSONDecodeError:
        return None
    try:
        monto = float(str(d.get("monto")).replace(",", "")) if d.get("monto") not in (None, "", "null") else None
    except ValueError:
        monto = None
    if not monto or monto <= 0:
        return None
    return {"monto": monto, "moneda": d.get("moneda") or None, "comercio": (d.get("comercio") or "").strip() or None,
            "es_gasto": d.get("es_gasto") is not False}


def leer_imagen(ruta: Path, env: dict, http=None) -> dict | None:
    """Devuelve {"monto", "moneda", "comercio", "es_gasto"} o None si no se ve un monto.

    Tira ErrorDeVision si no hay proveedor o si la IA falló.
    """
    p = proveedor(env)
    if p is None:
        raise ErrorDeVision("sin_proveedor")
    nombre, llave, modelo = p
    ruta = Path(ruta)
    texto = pedir(nombre, llave, modelo, ruta.read_bytes(), _mime(ruta), http)
    return interpretar_respuesta(texto)
