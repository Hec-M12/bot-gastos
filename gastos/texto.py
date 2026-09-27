"""Entiende lo que escribís ("45 pizza", "L1500 gasolina #carro") y adivina la categoría."""
from __future__ import annotations

import re

from .config import Config, a_moneda_local, codigo_moneda, normalizar

NUM = r"\d{1,3}(?:[.,]\d{3})+(?:[.,]\d{1,2})?|\d+(?:[.,]\d{1,2})?"
_TEXTO_RE = re.compile(
    rf"^\s*(?P<pre>[^\d\s#]{{1,4}})?\s*(?P<num>{NUM})(?![\d.,])\s*(?P<resto>.*)$", re.S)
_ETIQUETA_RE = re.compile(r"#([\wñÑáéíóúÁÉÍÓÚ]+)")


def a_numero(crudo: str) -> float:
    """'1,500.50' / '1.500,50' / '45' / '45,5' -> float.

    Regla: el último separador es decimal si le siguen 1 o 2 dígitos; si le siguen 3, es de miles.
    """
    s = re.sub(r"[^\d.,]", "", crudo or "")
    if not s:
        raise ValueError("sin número")
    ultimo = max(s.rfind("."), s.rfind(","))
    if ultimo == -1:
        return float(s)
    decimales = s[ultimo + 1:]
    if len(decimales) in (1, 2):
        entero = re.sub(r"[.,]", "", s[:ultimo])
        return float(f"{entero or '0'}.{decimales}")
    return float(re.sub(r"[.,]", "", s))


def buscar_monto(texto: str, cfg: Config) -> tuple[float, str | None] | None:
    """Busca 'USD 12.50', '$12.50', 'L 1,500.00', '12.50 USD' dentro de un texto."""
    m = re.search(rf"(?P<pre>[A-Za-z$€₡/.]{{1,4}})?\s*(?P<num>{NUM})\s*(?P<post>[A-Za-z$€₡]{{1,4}})?", texto or "")
    if not m:
        return None
    moneda = None
    for tok in (m.group("pre"), m.group("post")):
        if tok:
            moneda = codigo_moneda(tok.strip(" ."), cfg) or codigo_moneda(tok.strip(), cfg) or moneda
            if moneda:
                break
    return a_numero(m.group("num")), moneda


def clave_comercio(desc: str) -> str:
    """'UBER *TRIP 8812' -> 'uber trip' (para recordar categorías que corregiste)."""
    s = normalizar(desc)
    s = re.sub(r"[^a-zñ ]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()[:40]


def adivinar_categoria(desc: str, cfg: Config, aprendido: dict | None = None) -> str:
    clave = clave_comercio(desc)
    if aprendido and clave and aprendido.get(clave) in cfg.por_id:
        return aprendido[clave]
    n = normalizar(desc)
    for c in cfg.categorias:
        for p in c["palabras"]:
            if re.search(r"(?<![a-z0-9])" + re.escape(p), n):
                return c["id"]
    return cfg.categoria_por_defecto


def interpretar_gasto(texto: str, cfg: Config, aprendido: dict | None = None) -> dict:
    """Convierte '45 pizza #comida' en un gasto.

    Devuelve {"ok": True, "gasto": {...}, "aviso": str|None} o {"ok": False, "error": str}.
    """
    m = _TEXTO_RE.match(texto or "")
    if not m:
        return {"ok": False, "error": "no_entendi"}
    moneda = None
    if m.group("pre"):
        moneda = codigo_moneda(m.group("pre"), cfg)
        if not moneda:
            return {"ok": False, "error": "no_entendi"}
    resto = m.group("resto").strip()
    # moneda después del número: "20 usd amazon"
    post = re.match(r"^([A-Za-z$€₡/.]{1,4})(?=\s|$)", resto)
    if post and not moneda:
        mon = codigo_moneda(post.group(1), cfg)
        if mon:
            moneda = mon
            resto = resto[post.end():].strip()
    try:
        monto = a_numero(m.group("num"))
    except ValueError:
        return {"ok": False, "error": "no_entendi"}
    if monto <= 0:
        return {"ok": False, "error": "monto_cero"}
    etiquetas = [normalizar(e) for e in _ETIQUETA_RE.findall(resto)]
    desc = re.sub(r"\s+", " ", _ETIQUETA_RE.sub("", resto)).strip() or "sin nota"
    cat = None
    for e in etiquetas:
        if e in cfg.por_id:
            cat = e
            break
    if etiquetas and cat is None:
        return {"ok": False, "error": "categoria_desconocida", "etiqueta": etiquetas[0]}
    local, aviso = a_moneda_local(monto, moneda, cfg)
    gasto = {"monto": local, "desc": desc[:80], "cat": cat or adivinar_categoria(desc, cfg, aprendido), "origen": "texto"}
    if moneda and moneda != cfg.moneda:
        gasto["original"] = {"monto": monto, "moneda": moneda}
    return {"ok": True, "gasto": gasto, "aviso": aviso}
