#!/usr/bin/env python3
"""Asistente para configurar el bot SIN editar archivos a mano.

    python3 configurar.py              → todo, paso a paso
    python3 configurar.py telegram     → solo el token de Telegram
    python3 configurar.py categorias   → moneda, categorías y topes
    python3 configurar.py correo       → correo del banco (opcional)
    python3 configurar.py fotos        → llave de IA para leer capturas (opcional)
    python3 configurar.py banco        → pegar el patrón de tu banco que te armó la IA

Las claves se escriben a ciegas (no se ven al pegarlas: es normal) y van directo
al archivo .env de tu compu. Nunca las pegues en un chat.
"""
from __future__ import annotations

import argparse
import getpass
import imaplib
import json
import re
import shutil
import sys
import urllib.error
import urllib.request
from pathlib import Path

if sys.version_info < (3, 9):
    sys.exit("Necesitás Python 3.9 o más nuevo.")

from gastos import vision  # noqa: E402
from gastos.config import (BANCOS_DIR, CONFIG_EJEMPLO, CONFIG_FILE, ENV_FILE, RAIZ, ErrorDeConfig, cargar_json,  # noqa: E402
                           normalizar)
from gastos.correo import cargar_banco, validar_banco  # noqa: E402

PROBAR = True


# ---------------------------------------------------------------------------
# utilidades
# ---------------------------------------------------------------------------
def decir(t: str = "") -> None:
    try:
        print(t, flush=True)
    except UnicodeEncodeError:
        print(t.encode("ascii", "replace").decode(), flush=True)


def pedir(texto: str, defecto: str | None = None) -> str:
    sufijo = f" [{defecto}]" if defecto not in (None, "") else ""
    try:
        r = input(f"{texto}{sufijo}: ").strip()
    except EOFError:
        r = ""
    return r or (defecto or "")


def pedir_si(texto: str, defecto: bool = False) -> bool:
    r = normalizar(pedir(f"{texto} (s/n)", "s" if defecto else "n"))
    return r.startswith(("s", "y"))


def pedir_secreto(texto: str) -> str:
    """No muestra lo que pegás. Si la entrada no es una terminal (pruebas), lee normal."""
    if not sys.stdin.isatty():
        try:
            return input(f"{texto}: ").strip()
        except EOFError:
            return ""
    decir("   (al pegar no se ve nada: es normal, por seguridad. Pegalo y apretá Enter)")
    return getpass.getpass(f"{texto}: ").strip()


def escribir_env(cambios: dict, ruta: Path = ENV_FILE) -> None:
    """Actualiza CLAVE=valor en .env sin tocar el resto (lo crea desde .env.example si no existe)."""
    if not ruta.exists():
        ejemplo = RAIZ / ".env.example"
        if ejemplo.exists():
            shutil.copyfile(ejemplo, ruta)
        else:
            ruta.write_text("", encoding="utf-8")
    lineas = ruta.read_text(encoding="utf-8-sig").splitlines()
    pendientes = dict(cambios)
    for i, ln in enumerate(lineas):
        clave = ln.split("=", 1)[0].strip()
        if not ln.lstrip().startswith("#") and "=" in ln and clave in pendientes:
            lineas[i] = f"{clave}={pendientes.pop(clave)}"
    lineas += [f"{k}={v}" for k, v in pendientes.items()]
    ruta.write_text("\n".join(lineas) + "\n", encoding="utf-8")
    try:
        ruta.chmod(0o600)  # solo vos podés leerlo
    except OSError:
        pass


def arreglar_comillas(texto: str) -> str:
    """Los editores y chats cambian " por “ ” y rompen el JSON."""
    return texto.replace("“", '"').replace("”", '"').replace("‘", "'").replace("’", "'").replace(" ", " ")


def leer_bloque(mensaje: str) -> str:
    decir(mensaje)
    decir("   Cuando termines, escribí FIN solo en una línea y apretá Enter.")
    lineas = []
    while True:
        try:
            ln = input()
        except EOFError:
            break
        if ln.strip().upper() == "FIN":
            break
        lineas.append(ln)
    return "\n".join(lineas)


# ---------------------------------------------------------------------------
# pasos
# ---------------------------------------------------------------------------
def paso_telegram() -> bool:
    decir("\n── Telegram ──")
    decir("Pegá el token que te dio @BotFather (algo como 123456789:ABCdef...).")
    token = pedir_secreto("Token")
    token = token.replace(" ", "")
    if not re.fullmatch(r"\d{5,}:[A-Za-z0-9_-]{30,}", token):
        decir(f"❌ Eso no parece un token ({len(token)} caracteres). Copialo completo de BotFather y probá de nuevo:"
              " python3 configurar.py telegram")
        return False
    escribir_env({"TELEGRAM_TOKEN": token})
    decir("✅ Token guardado en .env")
    if PROBAR:
        from gastos.telegram import ErrorDeTelegram, Telegram
        try:
            yo = Telegram(token, reintentos=1).quien_soy()
            decir(f"✅ Telegram lo reconoce: tu bot es @{yo.get('username')}")
        except ErrorDeTelegram as exc:
            if exc.codigo in (401, 404):
                decir("❌ Telegram dice que ese token no es válido. Pedí uno nuevo en BotFather y repetí este paso.")
                return False
            decir(f"⚠️  No pude verificarlo ahora ({exc.descripcion}). Seguimos igual.")
    return True


def _categorias_ejemplo() -> dict:
    try:
        return {c["id"]: c for c in cargar_json(CONFIG_EJEMPLO).get("categorias", [])}
    except (OSError, ErrorDeConfig):
        return {}


def paso_categorias() -> bool:
    decir("\n── Moneda y categorías ──")
    datos = cargar_json(CONFIG_FILE) if CONFIG_FILE.exists() else cargar_json(CONFIG_EJEMPLO)
    moneda = pedir("¿En qué moneda gastás? Código de 3 letras (HNL, GTQ, CRC, NIO, PAB, MXN, COP, USD…)",
                   datos.get("moneda", "USD")).upper()
    if not re.fullmatch(r"[A-Z]{3}", moneda):
        decir("❌ Tiene que ser un código de 3 letras, ej. HNL. Probá de nuevo: python3 configurar.py categorias")
        return False
    simbolos = {"HNL": "L", "GTQ": "Q", "CRC": "₡", "NIO": "C$", "PAB": "B/.", "USD": "$", "MXN": "$", "COP": "$",
                "DOP": "RD$", "PEN": "S/", "EUR": "€", "ARS": "$", "CLP": "$"}
    simbolo = pedir("¿Qué símbolo querés ver?", simbolos.get(moneda, datos.get("simbolo", "$")))
    cambios = dict(datos.get("tipos_de_cambio") or {})
    if moneda != "USD":
        actual = cambios.get("USD")
        tc = pedir(f"¿Cuántos {moneda} vale 1 dólar? (para compras en USD; Enter si nunca comprás en dólares)",
                   str(actual) if actual else None)
        if tc:
            try:
                cambios["USD"] = float(tc.replace(",", "."))
            except ValueError:
                decir("   (no entendí el número, lo dejo sin tipo de cambio)")
    else:
        cambios.pop("USD", None)

    ejemplo = _categorias_ejemplo()
    decir("\nAhora tus categorías: una por línea, con el nombre y el tope al mes. Ejemplo:")
    decir("   Comida 3000\n   Súper 5000\n   Transporte 1500")
    decir("Cuando termines, dejá una línea vacía y apretá Enter.")
    decir("(Si apretás Enter de una, quedan las de ejemplo: " + ", ".join(c["nombre"] for c in ejemplo.values()) + ")")
    categorias, ids = [], set()
    while True:
        try:
            ln = input("> ").strip()
        except EOFError:
            break
        if not ln:
            break
        m = re.match(r"^(?P<nombre>.+?)\s+(?P<tope>[\d][\d.,]*)$", ln)
        if not m:
            decir("   Poné el nombre y después el número, ej: Comida 3000")
            continue
        nombre = m.group("nombre").strip()
        try:
            from gastos.texto import a_numero
            tope = a_numero(m.group("tope"))
        except ValueError:
            decir("   No entendí el número.")
            continue
        base = re.sub(r"[^a-z0-9_ñ]", "", normalizar(nombre).split()[0]) or "cat"
        cid, n = base, 2
        while cid in ids:
            cid, n = f"{base}{n}", n + 1
        ids.add(cid)
        palabras = ejemplo.get(cid, {}).get("palabras") or [normalizar(nombre).split()[0]]
        categorias.append({"id": cid, "nombre": nombre, "tope": tope, "palabras": palabras})
        decir(f"   ✓ {nombre}: tope {tope:,.0f} (para forzarla: #{cid})")
    if categorias:
        if "otros" not in ids:
            resto = round(sum(c["tope"] for c in categorias) * 0.1)
            categorias.append({"id": "otros", "nombre": "Otros", "tope": resto, "palabras": []})
            decir(f"   ✓ Agregué «Otros» (lo que no cae en ninguna) con tope {resto:,.0f}. Cambialo cuando quieras.")
        datos["categorias"] = categorias
        datos["categoria_por_defecto"] = "otros"
    datos.update({"moneda": moneda, "simbolo": simbolo, "tipos_de_cambio": cambios})
    CONFIG_FILE.write_text(json.dumps(datos, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    decir("✅ Guardado en config.json")
    return True


def _config() -> dict:
    return cargar_json(CONFIG_FILE) if CONFIG_FILE.exists() else cargar_json(CONFIG_EJEMPLO)


def _guardar_config(datos: dict) -> None:
    CONFIG_FILE.write_text(json.dumps(datos, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def paso_correo() -> bool:
    decir("\n── Correo del banco (opcional) ──")
    decir("Necesitás un Gmail PERSONAL (no de trabajo ni de la U) con verificación en 2 pasos,")
    decir("y una CONTRASEÑA DE APLICACIÓN de 16 letras: myaccount.google.com/apppasswords")
    decir("Nunca uses tu contraseña normal de Gmail, ni la de tu banco.")
    usuario = pedir("Tu Gmail (ej. tunombre@gmail.com)")
    if not usuario or "@" not in usuario:
        decir("Listo, dejo el correo apagado. Podés prenderlo después: python3 configurar.py correo")
        return True
    clave = pedir_secreto("Contraseña de aplicación (16 letras)").replace(" ", "")
    if len(clave) != 16 and "gmail" in usuario.lower():
        decir(f"⚠️  Tiene {len(clave)} letras; la de Gmail tiene 16. ¿Pegaste tu contraseña normal? La guardo igual.")
    escribir_env({"CORREO_USUARIO": usuario, "CORREO_CLAVE_APP": clave})
    decir("✅ Guardado en .env")
    datos = _config()
    servidor = (datos.get("correo") or {}).get("servidor_imap", "imap.gmail.com")
    if PROBAR:
        try:
            conn = imaplib.IMAP4_SSL(servidor)
            conn.login(usuario, clave)
            conn.logout()
            decir(f"✅ Entré a tu correo ({servidor}).")
        except imaplib.IMAP4.error:
            decir("❌ Gmail no me dejó entrar. Revisá que sea la contraseña de APLICACIÓN y repetí: python3 configurar.py correo")
            return False
        except OSError as exc:
            decir(f"⚠️  No pude probar la conexión ahora ({exc}). Seguimos igual.")
    bancos = datos.setdefault("correo", {}).setdefault("bancos", [])
    if pedir_si("¿Tu banco es BAC Credomatic?", "bac" in bancos):
        if "bac" not in bancos:
            bancos.append("bac")
        decir("✅ BAC queda activado (ya viene listo).")
    else:
        if "bac" in bancos:
            bancos.remove("bac")
        decir("Para tu banco hay que armar un patrón una sola vez: mirá bancos/COMO-AGREGAR-TU-BANCO.md "
              "y después corré python3 configurar.py banco")
    _guardar_config(datos)
    return True


def paso_fotos() -> bool:
    decir("\n── Leer capturas con IA (opcional) ──")
    decir("Gemini tiene capa gratis: sacá una llave en aistudio.google.com/apikey (botón «Create API key»).")
    decir("Ojo: en la capa gratis, Google puede usar lo que le mandás para mejorar sus productos.")
    prov = normalizar(pedir("¿Cuál vas a usar? gemini / openai / anthropic (Enter para saltar)", "")).strip()
    if not prov:
        decir("Listo, fotos apagadas. Podés prenderlas después: python3 configurar.py fotos")
        return True
    if prov not in vision.LLAVES:
        decir("❌ Tiene que ser gemini, openai o anthropic.")
        return False
    llave = pedir_secreto(f"Llave de {prov}")
    if not llave:
        decir("No pegaste nada; fotos apagadas.")
        return True
    escribir_env({vision.LLAVES[prov]: llave, "VISION_PROVEEDOR": prov})
    decir("✅ Guardado en .env")
    if PROBAR:
        urls = {"gemini": ("https://generativelanguage.googleapis.com/v1beta/models", {"x-goog-api-key": llave}),
                "openai": ("https://api.openai.com/v1/models", {"Authorization": f"Bearer {llave}"}),
                "anthropic": ("https://api.anthropic.com/v1/models", {"x-api-key": llave, "anthropic-version": "2023-06-01"})}
        url, headers = urls[prov]
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=20):
                decir(f"✅ La llave de {prov} funciona.")
        except urllib.error.HTTPError as exc:
            decir(f"❌ La llave no funciona (error {exc.code}). Copiala de nuevo y repetí: python3 configurar.py fotos")
            return False
        except OSError as exc:
            decir(f"⚠️  No pude probarla ahora ({exc}). Seguimos igual.")
    return True


def paso_banco() -> bool:
    decir("\n── Patrón de tu banco ──")
    texto = arreglar_comillas(leer_bloque("Pegá el bloque JSON que te armó la IA (empieza con { y termina con })."))
    ini, fin = texto.find("{"), texto.rfind("}")
    if ini < 0 or fin < 0:
        decir("❌ No encontré un bloque { ... }. Pedile a la IA el archivo completo.")
        return False
    try:
        datos = json.loads(texto[ini:fin + 1])
        validar_banco(datos, "patrón")
    except json.JSONDecodeError as exc:
        decir(f"❌ El JSON está roto (línea {exc.lineno}: {exc.msg}). Pegale este error a la IA para que lo corrija.")
        return False
    except ErrorDeConfig as exc:
        decir(f"❌ {exc}\n   Pegale este error a la IA para que lo corrija.")
        return False
    nombre = re.sub(r"[^a-z0-9_]", "_", normalizar(datos.get("nombre") or "banco")).strip("_") or "banco"
    archivo = f"mi_{nombre}"
    ruta = BANCOS_DIR / f"{archivo}.json"
    ruta.write_text(json.dumps(datos, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    cargar_banco(ruta)
    cfg = _config()
    bancos = cfg.setdefault("correo", {}).setdefault("bancos", [])
    if archivo not in bancos:
        bancos.append(archivo)
    _guardar_config(cfg)
    decir(f"✅ Guardado en bancos/{archivo}.json y agregado a config.json.")
    decir("   Probalo con un correo real: python3 probar_correo.py tu-correo.eml")
    return True


def main() -> int:
    global PROBAR
    p = argparse.ArgumentParser(description="Configurar el bot sin editar archivos")
    p.add_argument("que", nargs="?", choices=["telegram", "categorias", "correo", "fotos", "banco"], help="solo una parte")
    p.add_argument("--sin-probar", action="store_true", help="no probar conexiones")
    a = p.parse_args()
    PROBAR = not a.sin_probar
    pasos = {"telegram": paso_telegram, "categorias": paso_categorias, "correo": paso_correo,
             "fotos": paso_fotos, "banco": paso_banco}
    if a.que:
        return 0 if pasos[a.que]() else 1
    decir("Te voy a hacer unas preguntas. Enter acepta lo que está entre [corchetes].")
    if not paso_telegram():
        return 1
    if not paso_categorias():
        return 1
    if pedir_si("\n¿Querés que lea los correos de compra de tu banco? (lo podés hacer después)", False) and not paso_correo():
        return 1
    if pedir_si("\n¿Querés que lea capturas de compras con IA? (lo podés hacer después)", False) and not paso_fotos():
        return 1
    decir("\n🎉 Listo. Ahora prendé el bot con: python3 bot.py   (en Windows: py bot.py)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
