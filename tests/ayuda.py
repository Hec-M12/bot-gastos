"""Cosas compartidas por los tests: config de prueba, Telegram falso, buzón IMAP falso.

Todos los datos son INVENTADOS. Ningún test usa internet.
"""
from __future__ import annotations

import imaplib
import json
import sys
from datetime import datetime
from email.message import EmailMessage
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

from gastos.config import Config  # noqa: E402
from gastos.correo import validar_banco  # noqa: E402

AHORA = datetime(2026, 9, 26, 10, 0, 0)


def config_prueba(**cambios) -> Config:
    datos = {
        "moneda": "HNL", "simbolo": "L", "separador_decimal": ".",
        "tipos_de_cambio": {"USD": 25.0},
        "resumen_diario_hora": 20,
        "categorias": [
            {"id": "comida", "nombre": "Comida", "tope": 3000, "palabras": ["pizza", "pizzeria", "cafe", "uber eats"]},
            {"id": "super", "nombre": "Súper", "tope": 5000, "palabras": ["super", "despensa"]},
            {"id": "transporte", "nombre": "Transporte", "tope": 2000, "palabras": ["gasolina", "uber", "taxi"]},
            {"id": "otros", "nombre": "Otros", "tope": 1000, "palabras": []},
        ],
        "categoria_por_defecto": "otros",
        "correo": {"servidor_imap": "imap.ejemplo.invalid", "bancos": []},
    }
    datos.update(cambios)
    return Config(datos)


def banco_bac():
    return validar_banco(json.loads((RAIZ / "bancos" / "bac.json").read_text(encoding="utf-8")), "bac.json")


def banco_inventado_etiquetas():
    return validar_banco({
        "nombre": "Banco Luna",
        "remitentes": ["bancoluna"],
        "asuntos_a_ignorar": ["promoción"],
        "formatos": [{
            "nombre": "Compra",
            "asunto_contiene": ["compra aprobada"],
            "tipo": "gasto",
            "moneda_por_defecto": "HNL",
            "etiquetas": {"monto": "Valor:", "comercio": "Establecimiento:"},
        }],
    }, "luna.json")


def banco_inventado_patron():
    return validar_banco({
        "nombre": "Banco Sol",
        "remitentes": ["avisos@bancosol.invalid"],
        "formatos": [{
            "nombre": "Pago",
            "tipo": "gasto",
            "patron": r"pagaste (?P<moneda>Q|USD)\s?(?P<monto>[\d,.]+) en (?P<comercio>[^.\n]+)",
        }],
    }, "sol.json")


def correo_crudo(remitente: str, asunto: str, cuerpo: str, html: bool = False, fecha: str = "Sat, 26 Sep 2026 09:30:00 -0600") -> bytes:
    m = EmailMessage()
    m["From"] = remitente
    m["To"] = "persona@ejemplo.invalid"
    m["Subject"] = asunto
    m["Date"] = fecha
    if html:
        m.set_content("version texto")
        m.add_alternative(cuerpo, subtype="html")
    else:
        m.set_content(cuerpo)
    return m.as_bytes()


def html_bac(comercio: str, monto: str, estado: str = "Aprobada") -> str:
    return (f"<html><body><p>BAC Credomatic le informa la transacción con su tarjeta VISA ****1111 ({estado})</p>"
            f"<table><tr><td>Comercio</td><td>Monto</td></tr><tr><td>{comercio}</td><td>{monto}</td></tr>"
            f"<tr><td>Estado</td><td>{estado}</td></tr></table></body></html>")


class TransporteFalso:
    """Reemplaza la red de Telegram: guarda cada llamada y contesta lo que le digas."""

    def __init__(self):
        self.llamadas: list[tuple[str, dict]] = []
        self.updates: list[list[dict]] = []
        self.respuestas: dict[str, list[dict]] = {}

    def __call__(self, metodo: str, payload: dict, timeout: float) -> dict:
        self.llamadas.append((metodo, payload))
        if metodo in self.respuestas and self.respuestas[metodo]:
            return self.respuestas[metodo].pop(0)
        if metodo == "getUpdates":
            return {"ok": True, "result": self.updates.pop(0) if self.updates else []}
        if metodo == "getMe":
            return {"ok": True, "result": {"id": 1, "username": "mis_gastos_prueba_bot"}}
        if metodo == "sendMessage":
            return {"ok": True, "result": {"message_id": len(self.llamadas)}}
        return {"ok": True, "result": True}

    def enviados(self, metodo: str = "sendMessage") -> list[dict]:
        return [p for m, p in self.llamadas if m == metodo]

    def ultimo_texto(self) -> str:
        textos = [p["text"] for m, p in self.llamadas if m in ("sendMessage", "editMessageText")]
        return textos[-1] if textos else ""


class BuzonFalso:
    """Imita imaplib.IMAP4_SSL con correos en memoria."""

    def __init__(self, mensajes: dict[int, bytes], uidvalidity: str = "7", login_ok: bool = True):
        self.mensajes = mensajes
        self.uidvalidity = uidvalidity
        self.login_ok = login_ok
        self.seleccionada = None
        self.readonly = None
        self.fetches: list[tuple[str, str]] = []

    def __call__(self, host):  # se usa como fábrica: conectar(host)
        self.host = host
        return self

    def login(self, usuario, clave):
        if not self.login_ok:
            raise imaplib.IMAP4.error("[AUTHENTICATIONFAILED] Invalid credentials (Failure)")
        self.clave_usada = clave
        return "OK", [b"Logged in"]

    def select(self, carpeta, readonly=False):
        self.seleccionada, self.readonly = carpeta, readonly
        return "OK", [str(len(self.mensajes)).encode()]

    def response(self, codigo):
        return codigo, [self.uidvalidity.encode()]

    def uid(self, comando, *args):
        uids = sorted(self.mensajes)
        if comando == "search":
            criterio = args[-1]
            if criterio == "ALL":
                elegidos = uids
            else:
                desde = int(criterio.split()[1].split(":")[0])
                elegidos = [u for u in uids if u >= desde] or uids[-1:]  # quirk real de IMAP
            return "OK", [" ".join(str(u) for u in elegidos).encode()]
        if comando == "fetch":
            uid, spec = int(args[0]), args[1]
            self.fetches.append((str(uid), spec))
            crudo = self.mensajes[uid]
            if "HEADER.FIELDS" in spec:
                crudo = crudo.split(b"\n\n", 1)[0] + b"\n\n"
            return "OK", [(f"{uid} (UID {uid} BODY[] {{{len(crudo)}}}".encode(), crudo), b")"]
        raise AssertionError(comando)

    def logout(self):
        return "BYE", []
