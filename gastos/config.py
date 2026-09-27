"""Lee config.json (tus categorías y topes) y .env (tus llaves secretas).

Todo lo que el usuario puede cambiar vive en esos dos archivos. Nada de acá
adentro tiene datos de nadie.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import unicodedata
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
CONFIG_FILE = RAIZ / "config.json"
CONFIG_EJEMPLO = RAIZ / "config.ejemplo.json"
ENV_FILE = RAIZ / ".env"
BANCOS_DIR = RAIZ / "bancos"
DATOS_DIR = RAIZ / "datos"

CLAVES_ENV = (
    "TELEGRAM_TOKEN", "TELEGRAM_CHAT_ID",
    "CORREO_USUARIO", "CORREO_CLAVE_APP",
    "VISION_PROVEEDOR", "VISION_MODELO",
    "GEMINI_API_KEY", "OPENAI_API_KEY", "ANTHROPIC_API_KEY",
)

# Cómo aparece cada moneda en correos, capturas y texto. La clave es el código ISO.
ALIAS_MONEDAS = {
    "USD": ["usd", "us$", "dolares", "dólares", "dolar", "dólar"],
    "HNL": ["hnl", "lps", "lps.", "l", "l.", "lempiras"],
    "GTQ": ["gtq", "q", "q.", "quetzales"],
    "CRC": ["crc", "₡", "colones"],
    "NIO": ["nio", "c$", "cordobas", "córdobas"],
    "PAB": ["pab", "b/.", "balboas"],
    "MXN": ["mxn", "mx$"],
    "COP": ["cop"],
    "DOP": ["dop", "rd$"],
    "PEN": ["pen", "s/", "s/.", "soles"],
    "ARS": ["ars"],
    "CLP": ["clp"],
    "EUR": ["eur", "€", "euros"],
}


class ErrorDeConfig(Exception):
    """Un problema en config.json explicado para humanos."""


def normalizar(s: str) -> str:
    """minúsculas y sin tildes: 'Súper Café' -> 'super cafe'."""
    s = unicodedata.normalize("NFKD", str(s or "").lower())
    return "".join(c for c in s if not unicodedata.combining(c))


def leer_env(ruta: Path = ENV_FILE) -> dict:
    """Lee un .env simple (CLAVE=valor). Las variables de entorno reales ganan."""
    out: dict = {}
    if ruta.exists():
        for linea in ruta.read_text(encoding="utf-8-sig").splitlines():
            linea = linea.strip()
            if not linea or linea.startswith("#") or "=" not in linea:
                continue
            k, v = linea.split("=", 1)
            v = v.strip()
            if len(v) >= 2 and v[0] == v[-1] and v[0] in "'\"":
                v = v[1:-1]
            out[k.strip()] = v
    for k in CLAVES_ENV:
        if os.environ.get(k):
            out[k] = os.environ[k]
    return out


def _explicar_json_roto(ruta: Path, exc: json.JSONDecodeError) -> str:
    lineas = ruta.read_text(encoding="utf-8-sig").splitlines()
    linea = lineas[exc.lineno - 1] if 0 < exc.lineno <= len(lineas) else ""
    pista = ""
    if "trailing comma" in exc.msg.lower():
        pista = " Te sobra una coma: lo último de una lista o de un bloque { } no lleva coma."
    elif "Expecting property name" in exc.msg or ("Expecting value" in exc.msg and linea.strip().startswith(("}", "]"))):
        pista = " Casi seguro te sobra una coma al final de la línea anterior."
    elif "Expecting ',' delimiter" in exc.msg:
        pista = " Casi seguro te falta una coma al final de la línea anterior (o unas comillas)."
    elif "Invalid \\escape" in exc.msg:
        pista = " En JSON cada \\ se escribe doble: \\\\d en vez de \\d."
    return (f"{ruta.name} tiene un error en la línea {exc.lineno}, columna {exc.colno}: {exc.msg}.{pista}\n"
            f"   → {linea.strip()[:120]}")


def cargar_json(ruta: Path) -> dict:
    try:
        return json.loads(ruta.read_text(encoding="utf-8-sig"))
    except json.JSONDecodeError as exc:
        raise ErrorDeConfig(_explicar_json_roto(ruta, exc)) from None


class Config:
    """config.json ya validado, con valores por defecto."""

    def __init__(self, datos: dict):
        self.crudo = datos
        self.moneda: str = str(datos.get("moneda", "USD")).upper()
        self.simbolo: str = str(datos.get("simbolo", "$"))
        self.separador_decimal: str = str(datos.get("separador_decimal", "."))
        self.tipos_de_cambio: dict = {str(k).upper(): float(v) for k, v in (datos.get("tipos_de_cambio") or {}).items()}
        hora = datos.get("resumen_diario_hora", 20)
        self.resumen_diario_hora = None if hora in (None, False, "") else int(hora)
        cats = datos.get("categorias") or []
        self.categorias: list[dict] = []
        for c in cats:
            if isinstance(c, dict) and not str(c.get("id", "")).startswith("_"):
                self.categorias.append({
                    "id": str(c["id"]).strip().lower(),
                    "nombre": str(c.get("nombre") or c["id"]),
                    "tope": float(c.get("tope") or 0),
                    "palabras": [normalizar(p) for p in (c.get("palabras") or []) if str(p).strip()],
                })
        self.por_id = {c["id"]: c for c in self.categorias}
        self.categoria_por_defecto: str = str(datos.get("categoria_por_defecto") or (self.categorias[-1]["id"] if self.categorias else "otros"))
        correo = datos.get("correo") or {}
        self.correo_servidor: str = str(correo.get("servidor_imap") or "imap.gmail.com")
        self.correo_carpeta: str = str(correo.get("carpeta") or "INBOX")
        self.correo_cada_min: float = float(correo.get("revisar_cada_minutos") or 10)
        self.correo_bancos: list[str] = [str(b) for b in (correo.get("bancos") or [])]

    @property
    def tope_total(self) -> float:
        return sum(c["tope"] for c in self.categorias)

    def nombre(self, cat_id: str) -> str:
        c = self.por_id.get(cat_id)
        return c["nombre"] if c else cat_id

    def errores(self) -> list[str]:
        errs = []
        if not re.fullmatch(r"[A-Z]{3}", self.moneda):
            errs.append(f'"moneda" tiene que ser un código de 3 letras (USD, HNL, GTQ, MXN…). Tiene: {self.moneda!r}')
        if self.separador_decimal not in (".", ","):
            errs.append('"separador_decimal" tiene que ser "." o ","')
        if not self.categorias:
            errs.append('"categorias" está vacío: necesitás al menos una.')
        ids = [c["id"] for c in self.categorias]
        for i in set(ids):
            if ids.count(i) > 1:
                errs.append(f'La categoría "{i}" está repetida.')
            if not re.fullmatch(r"[a-z0-9_ñ]+", i):
                errs.append(f'El id "{i}" solo puede tener minúsculas, números y _ (sin espacios ni tildes): lo vas a escribir como #{i}.')
        if self.categoria_por_defecto not in self.por_id:
            errs.append(f'"categoria_por_defecto" es "{self.categoria_por_defecto}" pero esa categoría no existe.')
        if self.resumen_diario_hora is not None and not 0 <= self.resumen_diario_hora <= 23:
            errs.append('"resumen_diario_hora" va de 0 a 23 (o null para apagarlo).')
        return errs


def cargar_config(ruta: Path = CONFIG_FILE, crear_si_falta: bool = True) -> Config:
    """Carga config.json. Si no existe, lo crea copiando config.ejemplo.json."""
    if not ruta.exists():
        if crear_si_falta and CONFIG_EJEMPLO.exists() and ruta == CONFIG_FILE:
            shutil.copyfile(CONFIG_EJEMPLO, ruta)
        else:
            raise ErrorDeConfig(f"No existe {ruta}. Copiá config.ejemplo.json como config.json.")
    cfg = Config(cargar_json(ruta))
    errs = cfg.errores()
    if errs:
        raise ErrorDeConfig("config.json tiene problemas:\n - " + "\n - ".join(errs))
    return cfg


def codigo_moneda(token: str | None, cfg: Config, estricto: bool = True) -> str | None:
    """'LPS' -> 'HNL', '$' -> USD (o la moneda local si tu símbolo es $).

    estricto=False acepta cualquier código de 3 letras (solo para correos de banco,
    donde el patrón ya dice dónde va la moneda). En texto libre "45 luz" no es una moneda.
    """
    if not token:
        return None
    t = normalizar(token).strip()
    if t in ("$",):
        return cfg.moneda if cfg.simbolo == "$" else "USD"
    if t == normalizar(cfg.simbolo) or t == cfg.moneda.lower():
        return cfg.moneda
    for codigo, alias in ALIAS_MONEDAS.items():
        if t == codigo.lower() or t in alias:
            return codigo
    if t.upper() in cfg.tipos_de_cambio:
        return t.upper()
    if not estricto and re.fullmatch(r"[a-z]{3}", t):
        return t.upper()
    return None


def a_moneda_local(monto: float, moneda: str | None, cfg: Config) -> tuple[float, str | None]:
    """Convierte a tu moneda. Devuelve (monto, aviso_o_None)."""
    if not moneda or moneda == cfg.moneda:
        return round(monto, 2), None
    tasa = cfg.tipos_de_cambio.get(moneda)
    if tasa:
        return round(monto * tasa, 2), None
    return round(monto, 2), (f"No tengo tipo de cambio para {moneda} en config.json "
                             f'("tipos_de_cambio"), así que lo anoté como si fuera {cfg.moneda}.')


def formato_numero(v: float, cfg: Config, decimales: bool | None = None) -> str:
    if decimales is None:
        decimales = abs(v) < 1000 and round(v, 2) != round(v)
    s = f"{v:,.2f}" if decimales else f"{v:,.0f}"
    if cfg.separador_decimal == ",":
        s = s.replace(",", "\0").replace(".", ",").replace("\0", ".")
    return s


def dinero(v: float, cfg: Config) -> str:
    signo = "-" if v < 0 else ""
    return f"{signo}{cfg.simbolo}{formato_numero(abs(v), cfg)}"
