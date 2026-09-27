"""El libro de gastos: un JSON en datos/gastos.json que solo vive en tu compu.

También arma los mensajes de acumulado, /mes y /hoy.
"""
from __future__ import annotations

import calendar
import html
import json
import logging
from datetime import date, datetime
from pathlib import Path

from .config import Config, dinero

logger = logging.getLogger("bot-gastos")

MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio",
         "agosto", "septiembre", "octubre", "noviembre", "diciembre"]
MAX_PENDIENTES = 50


def _base() -> dict:
    return {"version": 1, "gastos": [], "pendientes": {}, "aprendido": {}, "resumenes": {},
            "secuencia": 0, "correo": {"ultimo_uid": 0, "uidvalidity": None, "anclado": False}}


class Libro:
    def __init__(self, ruta: Path):
        self.ruta = Path(ruta)
        self.datos = self._cargar()

    def _cargar(self) -> dict:
        base = _base()
        if not self.ruta.exists():
            return base
        try:
            datos = json.loads(self.ruta.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            respaldo = self.ruta.with_name(f"{self.ruta.stem}.roto-{datetime.now():%Y%m%d-%H%M%S}.json")
            try:
                self.ruta.replace(respaldo)
            except OSError:
                pass
            logger.warning(f"{self.ruta.name} estaba dañado ({exc}); lo guardé como {respaldo.name} y arranco vacío")
            return base
        for k, v in base.items():
            datos.setdefault(k, v)
        return datos

    def guardar(self) -> None:
        self.ruta.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.ruta.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.datos, ensure_ascii=False, indent=1), encoding="utf-8")
        tmp.replace(self.ruta)

    # --- ids ---------------------------------------------------------------
    def nuevo_id(self) -> int:
        self.datos["secuencia"] = int(self.datos.get("secuencia", 0)) + 1
        return self.datos["secuencia"]

    # --- gastos ------------------------------------------------------------
    @property
    def gastos(self) -> list[dict]:
        return self.datos["gastos"]

    def agregar(self, gasto: dict, ahora: datetime | None = None) -> dict:
        g = dict(gasto)
        g.setdefault("ts", (ahora or datetime.now()).isoformat(timespec="seconds"))
        g["id"] = self.nuevo_id()
        self.gastos.append(g)
        return g

    def deshacer(self) -> dict | None:
        return self.gastos.pop() if self.gastos else None

    def del_mes(self, ym: str) -> list[dict]:
        return [g for g in self.gastos if g["ts"][:7] == ym]

    def del_dia(self, dia: str) -> list[dict]:
        return [g for g in self.gastos if g["ts"][:10] == dia]

    # --- pendientes (esperan un botón) -------------------------------------
    def guardar_pendiente(self, tipo: str, datos: dict) -> str:
        pid = str(self.nuevo_id())
        self.datos["pendientes"][pid] = {"tipo": tipo, "datos": datos}
        viejos = list(self.datos["pendientes"])[:-MAX_PENDIENTES]
        for k in viejos:
            self.datos["pendientes"].pop(k, None)
        return pid

    def aprender(self, clave: str, cat: str) -> None:
        if clave:
            self.datos["aprendido"][clave] = cat


# ---------------------------------------------------------------------------
# Mensajes
# ---------------------------------------------------------------------------
def barra(gastado: float, tope: float, ancho: int = 10) -> str:
    if tope <= 0:
        return "·" * ancho
    n = max(0, min(ancho, int(round(gastado / tope * ancho))))
    return "█" * n + "░" * (ancho - n)


def _estado(gastado: float, tope: float, cfg: Config) -> str:
    if tope <= 0:
        return ""
    if gastado > tope:
        return f" ⚠️ te pasaste por {dinero(gastado - tope, cfg)}"
    if gastado >= 0.8 * tope:
        return f" 👀 vas en {gastado / tope:.0%}"
    return ""


def e(s) -> str:
    return html.escape(str(s), quote=False)


def mensaje_registro(libro: Libro, cfg: Config, g: dict) -> str:
    """Lo que el bot contesta al anotar un gasto: el gasto + cómo vas en esa categoría y en el mes."""
    ym = g["ts"][:7]
    filas = libro.del_mes(ym)
    cat = cfg.por_id.get(g["cat"], {"nombre": g["cat"], "tope": 0})
    en_cat = sum(x["monto"] for x in filas if x["cat"] == g["cat"])
    total = sum(x["monto"] for x in filas)
    original = ""
    if g.get("original"):
        o = g["original"]
        original = f" ({o['moneda']} {o['monto']:,.2f})"
    origen = {"correo": " · 📧", "foto": " · 📷"}.get(g.get("origen", ""), "")
    lineas = [f"✅ <b>{dinero(g['monto'], cfg)}</b>{e(original)} · {e(cat['nombre'])} · {e(g['desc'])}{origen}"]
    if cat["tope"] > 0:
        lineas.append(f"{e(cat['nombre'])} este mes: {dinero(en_cat, cfg)} / {dinero(cat['tope'], cfg)}  "
                      f"{barra(en_cat, cat['tope'])}{_estado(en_cat, cat['tope'], cfg)}")
    else:
        lineas.append(f"{e(cat['nombre'])} este mes: {dinero(en_cat, cfg)}")
    lineas.append(f"Total del mes: {dinero(total, cfg)} / {dinero(cfg.tope_total, cfg)}  {barra(total, cfg.tope_total)}")
    return "\n".join(lineas)


def resumen_mes(libro: Libro, cfg: Config, hoy: date | None = None, titulo: str | None = None) -> str:
    hoy = hoy or date.today()
    ym = hoy.strftime("%Y-%m")
    filas = libro.del_mes(ym)
    por_cat: dict = {c["id"]: 0.0 for c in cfg.categorias}
    for g in filas:
        por_cat[g["cat"]] = por_cat.get(g["cat"], 0.0) + g["monto"]
    total = sum(por_cat.values())
    tope = cfg.tope_total
    filas_txt = []
    for c in cfg.categorias:
        s = por_cat.get(c["id"], 0.0)
        aviso = " ⚠️" if c["tope"] and s > c["tope"] else ""
        filas_txt.append(f"{barra(s, c['tope'])} {e(c['nombre'])} {dinero(s, cfg)}/{dinero(c['tope'], cfg)}{aviso}")
    for k in [k for k in por_cat if k not in cfg.por_id and por_cat[k]]:  # categorías que ya no están en config.json
        filas_txt.append(f"{'·' * 10} {e(k)} {dinero(por_cat[k], cfg)}")
    lineas = [titulo or f"<b>{MESES[hoy.month - 1].capitalize()} {hoy.year} · día {hoy.day}</b>",
              f"Total: <b>{dinero(total, cfg)}</b> de {dinero(tope, cfg)}  {barra(total, tope)}", ""] + filas_txt + [""]
    dias_restantes = calendar.monthrange(hoy.year, hoy.month)[1] - hoy.day + 1
    resto = tope - total
    if tope > 0:
        if resto > 0:
            lineas.append(f"Te quedan {dinero(resto, cfg)} para {dias_restantes} "
                          f"{'día' if dias_restantes == 1 else 'días'} ≈ {dinero(resto / dias_restantes, cfg)} por día.")
        else:
            lineas.append(f"Te pasaste del total por {dinero(-resto, cfg)}.")
    return "\n".join(lineas)


def resumen_hoy(libro: Libro, cfg: Config, hoy: date | None = None, titulo: str = "<b>Hoy</b>") -> str:
    hoy = hoy or date.today()
    filas = libro.del_dia(hoy.isoformat())
    if not filas:
        return f"{titulo}: nada anotado. 👌"
    cuerpo = "\n".join(f"• {dinero(g['monto'], cfg)} · {e(cfg.nombre(g['cat']))} · {e(g['desc'])}" for g in filas)
    return f"{titulo}\n{cuerpo}\nTotal: <b>{dinero(sum(g['monto'] for g in filas), cfg)}</b>"
