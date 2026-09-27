#!/usr/bin/env python3
"""Revisa que todo esté bien configurado. NO muestra tus contraseñas ni tokens:
podés copiar lo que sale y pegárselo a tu IA sin miedo.

    python3 revisar.py              → revisa archivos (sin internet)
    python3 revisar.py --en-linea   → además prueba Telegram, tu correo y la llave de IA de verdad
"""
from __future__ import annotations

import argparse
import imaplib
import json
import re
import sys
import urllib.error
import urllib.request

OK, MAL, OJO, INFO = "✅", "❌", "⚠️ ", "ℹ️ "


def linea(simbolo: str, texto: str) -> None:
    try:
        print(f"{simbolo} {texto}")
    except UnicodeEncodeError:
        print(f"{simbolo} {texto}".encode("ascii", "replace").decode())


def main() -> int:
    p = argparse.ArgumentParser(description="Revisa la configuración del bot")
    p.add_argument("--en-linea", action="store_true", help="probar conexiones de verdad (Telegram, correo, IA)")
    a = p.parse_args()
    problemas = 0

    v = sys.version_info
    if v >= (3, 9):
        linea(OK, f"Python {v.major}.{v.minor}.{v.micro}")
    else:
        linea(MAL, f"Python {v.major}.{v.minor}: necesitás 3.9 o más nuevo.")
        return 1

    from gastos import vision
    from gastos.config import CONFIG_FILE, ENV_FILE, ErrorDeConfig, cargar_config, dinero, leer_env
    from gastos.correo import cargar_bancos

    # --- config.json ---------------------------------------------------------
    cfg = None
    existia = CONFIG_FILE.exists()
    try:
        cfg = cargar_config()
        if not existia:
            linea(INFO, "No había config.json: lo creé con categorías de ejemplo.")
        cats = ", ".join(f"{c['id']} ({dinero(c['tope'], cfg)})" for c in cfg.categorias)
        linea(OK, f"config.json: moneda {cfg.moneda} ({cfg.simbolo}), {len(cfg.categorias)} categorías, "
                  f"tope total {dinero(cfg.tope_total, cfg)} al mes")
        linea("  ", cats)
        if cfg.tipos_de_cambio:
            linea("  ", "Tipos de cambio: " + ", ".join(f"1 {k} = {v:g} {cfg.moneda}" for k, v in cfg.tipos_de_cambio.items()))
    except ErrorDeConfig as exc:
        linea(MAL, str(exc))
        problemas += 1

    # --- .env ----------------------------------------------------------------
    env = leer_env()
    if not ENV_FILE.exists():
        linea(MAL, "No existe el archivo .env. Copiá .env.example como .env (ojo: empieza con punto) y llenalo.")
        problemas += 1
    token = (env.get("TELEGRAM_TOKEN") or "").strip()
    if not token or token.startswith("pega"):
        linea(MAL, "TELEGRAM_TOKEN: falta. Te lo da @BotFather en Telegram (paso 1).")
        problemas += 1
    elif not re.fullmatch(r"\d{5,}:[A-Za-z0-9_-]{30,}", token):
        linea(MAL, f"TELEGRAM_TOKEN: no tiene la forma correcta (números, dos puntos, letras). Tiene {len(token)} caracteres; "
                   "fijate de copiarlo completo y sin espacios.")
        problemas += 1
    else:
        linea(OK, "TELEGRAM_TOKEN: tiene la forma correcta (no lo muestro).")

    # --- dueño ---------------------------------------------------------------
    from gastos.config import DATOS_DIR
    estado = {}
    try:
        estado = json.loads((DATOS_DIR / "estado.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        pass
    if env.get("TELEGRAM_CHAT_ID") or estado.get("chat_id"):
        linea(OK, "El bot ya tiene dueño (vos).")
    elif estado.get("codigo"):
        linea(INFO, f"El bot espera su dueño. Mandale este código a tu bot en Telegram: {estado['codigo']}")
    else:
        linea(INFO, "El bot todavía no tiene dueño: al prenderlo te muestra un código de 6 números para mandarle.")

    # --- correo ----------------------------------------------------------------
    usuario, clave = env.get("CORREO_USUARIO"), env.get("CORREO_CLAVE_APP")
    bancos = []
    if usuario and clave:
        limpia = clave.replace(" ", "")
        linea(OK, f"Correo: {usuario} (la clave no la muestro)")
        if cfg and "gmail" in cfg.correo_servidor and len(limpia) != 16:
            linea(OJO, f"CORREO_CLAVE_APP tiene {len(limpia)} letras; la contraseña de aplicación de Gmail tiene 16. "
                       "¿Pegaste tu contraseña normal?")
        if cfg:
            try:
                bancos = cargar_bancos(cfg.correo_bancos)
                linea(OK, "Bancos: " + (", ".join(b["nombre"] for b in bancos) or "ninguno"))
                if not bancos:
                    linea(OJO, 'No hay bancos en config.json ("correo" → "bancos"): el correo no va a leer nada.')
            except ErrorDeConfig as exc:
                linea(MAL, f"Banco: {exc}")
                problemas += 1
    elif usuario or clave:
        linea(MAL, "Correo: pusiste solo una de CORREO_USUARIO / CORREO_CLAVE_APP. Van las dos, o ninguna.")
        problemas += 1
    else:
        linea(INFO, "Correo: apagado (es opcional).")

    # --- visión ------------------------------------------------------------------
    prov = vision.proveedor(env)
    elegido = (env.get("VISION_PROVEEDOR") or "").strip().lower()
    if elegido and elegido not in vision.LLAVES:
        linea(MAL, f"VISION_PROVEEDOR={elegido!r}: tiene que ser gemini, openai o anthropic (o vacío).")
        problemas += 1
    elif prov:
        linea(OK, f"Fotos: {prov[0]} con el modelo {prov[2]} (la llave no la muestro)")
    elif elegido:
        linea(MAL, f"Fotos: elegiste {elegido} pero falta {vision.LLAVES[elegido]} en .env.")
        problemas += 1
    else:
        linea(INFO, "Fotos: apagado (es opcional; Gemini tiene capa gratis).")

    # --- pruebas en línea ------------------------------------------------------------
    if a.en_linea:
        print("\nProbando conexiones…")
        if token and not token.startswith("pega"):
            from gastos.telegram import ErrorDeTelegram, Telegram
            try:
                yo = Telegram(token, reintentos=1).quien_soy()
                linea(OK, f"Telegram: conectado como @{yo.get('username')}")
            except ErrorDeTelegram as exc:
                linea(MAL, "Telegram: el token no funciona." if exc.codigo in (401, 404) else f"Telegram: {exc.descripcion}")
                problemas += 1
        if usuario and clave and cfg:
            try:
                conn = imaplib.IMAP4_SSL(cfg.correo_servidor)
                conn.login(usuario, clave.replace(" ", ""))
                conn.logout()
                linea(OK, f"Correo: entré a {cfg.correo_servidor} sin problema.")
            except imaplib.IMAP4.error as exc:
                linea(MAL, f"Correo: no me deja entrar ({str(exc)[:100]}). ¿Usaste la contraseña de APLICACIÓN de 16 letras?")
                problemas += 1
            except OSError as exc:
                linea(MAL, f"Correo: no llego a {cfg.correo_servidor} ({exc}).")
                problemas += 1
        if prov:
            nombre, llave, _ = prov
            urls = {"gemini": ("https://generativelanguage.googleapis.com/v1beta/models", {"x-goog-api-key": llave}),
                    "openai": ("https://api.openai.com/v1/models", {"Authorization": f"Bearer {llave}"}),
                    "anthropic": ("https://api.anthropic.com/v1/models", {"x-api-key": llave, "anthropic-version": "2023-06-01"})}
            url, headers = urls[nombre]
            try:
                with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=20):
                    linea(OK, f"Fotos: la llave de {nombre} funciona.")
            except urllib.error.HTTPError as exc:
                linea(MAL, f"Fotos: la llave de {nombre} no funciona (error {exc.code}).")
                problemas += 1
            except OSError as exc:
                linea(MAL, f"Fotos: no llego a {nombre} ({exc}).")
                problemas += 1

    print()
    if problemas:
        linea(MAL, f"Hay {problemas} cosa(s) por arreglar arriba.")
        return 1
    linea(OK, "Todo listo. Prendé el bot con: python3 bot.py" + ("" if a.en_linea else "   (o probá conexiones con --en-linea)"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
