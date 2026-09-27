"""Lee los correos de notificación de tu banco y saca monto, moneda y comercio.

Cada banco se describe en un archivo de bancos/ (ver bancos/COMO-AGREGAR-TU-BANCO.md).
El correo es opcional: sin CORREO_USUARIO / CORREO_CLAVE_APP el bot funciona igual.
"""
from __future__ import annotations

import email
import email.header
import email.utils
import html
import imaplib
import logging
import re
from datetime import datetime
from pathlib import Path

from .config import BANCOS_DIR, Config, ErrorDeConfig, cargar_json, codigo_moneda, normalizar
from .texto import a_numero, buscar_monto

logger = logging.getLogger("bot-gastos")

TIPOS = ("gasto", "movimiento", "ingreso")
MAX_POR_VUELTA = 200


# ---------------------------------------------------------------------------
# De correo crudo a texto plano
# ---------------------------------------------------------------------------
def decodificar_encabezado(v: str | None) -> str:
    try:
        return str(email.header.make_header(email.header.decode_header(v or "")))
    except Exception:  # noqa: BLE001 - encabezados rotos existen
        return v or ""


def html_a_texto(h: str) -> str:
    h = re.sub(r"(?is)<(style|script|head)\b.*?</\1>", " ", h)
    h = re.sub(r"(?i)<br\s*/?>|</p>|</tr>|</div>|</td>|</th>|</li>|</h\d>|</table>", "\n", h)
    h = re.sub(r"<[^>]+>", " ", h)
    return html.unescape(h)


def limpiar(texto: str) -> str:
    """Una línea por dato, sin espacios de más ni líneas vacías."""
    lineas = [re.sub(r"[ \t ​]+", " ", ln).strip() for ln in texto.replace("\r", "\n").split("\n")]
    return "\n".join(ln for ln in lineas if ln)


def texto_del_correo(msg: email.message.Message) -> str:
    """El texto del correo tal como lo ve el bot (el HTML se convierte a líneas)."""
    plano, formato_html = [], []
    for parte in (msg.walk() if msg.is_multipart() else [msg]):
        tipo = parte.get_content_type()
        if tipo not in ("text/plain", "text/html") or parte.get_filename():
            continue
        try:
            carga = parte.get_payload(decode=True) or b""
            contenido = carga.decode(parte.get_content_charset() or "utf-8", "replace")
        except (LookupError, AttributeError):
            continue
        (formato_html if tipo == "text/html" else plano).append(contenido)
    if formato_html:
        return limpiar(html_a_texto("\n".join(formato_html)))
    return limpiar("\n".join(plano))


def leer_eml(ruta: Path) -> tuple[str, str, str, datetime | None]:
    """(remitente, asunto, texto, fecha) de un archivo .eml."""
    msg = email.message_from_bytes(Path(ruta).read_bytes())
    return (decodificar_encabezado(msg.get("From")), decodificar_encabezado(msg.get("Subject")),
            texto_del_correo(msg), fecha_del_correo(msg.get("Date")))


def fecha_del_correo(valor: str | None) -> datetime | None:
    if not valor:
        return None
    try:
        dt = email.utils.parsedate_to_datetime(valor)
    except (TypeError, ValueError, IndexError):
        return None
    if dt is None:
        return None
    return dt.astimezone().replace(tzinfo=None) if dt.tzinfo else dt


# ---------------------------------------------------------------------------
# Definiciones de bancos
# ---------------------------------------------------------------------------
def _lista(v) -> list[str]:
    if v is None:
        return []
    if isinstance(v, str):
        return [v]
    return [str(x) for x in v]


def _normalizadas(v) -> list[str]:
    return list(dict.fromkeys(normalizar(x) for x in _lista(v) if str(x).strip()))


def validar_banco(datos: dict, origen: str = "banco") -> dict:
    """Valida y compila una definición de banco. Tira ErrorDeConfig con explicación."""
    errs = []
    nombre = datos.get("nombre") or origen
    remitentes = _normalizadas(datos.get("remitentes"))
    if not remitentes:
        errs.append('falta "remitentes": una parte del correo de quien manda las notificaciones (ej. "notificaciones@tubanco.example" o solo "tubanco").')
    formatos = []
    for i, f in enumerate(datos.get("formatos") or [], 1):
        fn = f.get("nombre") or f"formato {i}"
        tipo = f.get("tipo", "gasto")
        if tipo not in TIPOS:
            errs.append(f'formato "{fn}": "tipo" tiene que ser uno de {", ".join(TIPOS)}.')
        patron = f.get("patron")
        etiquetas = f.get("etiquetas") or {}
        compilado = None
        if patron:
            try:
                compilado = re.compile(patron, re.I)
            except re.error as exc:
                errs.append(f'formato "{fn}": el "patron" no es una expresión regular válida ({exc}).')
            else:
                if "monto" not in compilado.groupindex:
                    errs.append(f'formato "{fn}": el "patron" necesita un grupo (?P<monto>...) que capture el monto.')
        elif etiquetas:
            if not etiquetas.get("monto"):
                errs.append(f'formato "{fn}": en "etiquetas" falta "monto" (el texto que va antes del monto, ej. "Monto:").')
        else:
            errs.append(f'formato "{fn}": necesita "etiquetas" o "patron" para saber dónde está el monto.')
        patron_cuenta = None
        if f.get("patron_cuenta"):
            try:
                patron_cuenta = re.compile(f["patron_cuenta"], re.I)
            except re.error as exc:
                errs.append(f'formato "{fn}": "patron_cuenta" no es válido ({exc}).')
        formatos.append({
            "nombre": fn, "tipo": tipo, "patron": compilado, "etiquetas": etiquetas,
            "asunto_contiene": _normalizadas(f.get("asunto_contiene")),
            "ignorar_si_contiene": _normalizadas(f.get("ignorar_si_contiene")),
            "es_ingreso_si_contiene": _normalizadas(f.get("es_ingreso_si_contiene")),
            "moneda_por_defecto": f.get("moneda_por_defecto"),
            "patron_cuenta": patron_cuenta,
        })
    if not formatos:
        errs.append('falta "formatos": al menos uno (ver bancos/COMO-AGREGAR-TU-BANCO.md).')
    if errs:
        raise ErrorDeConfig(f"{origen}: " + " / ".join(errs))
    return {"nombre": nombre, "remitentes": remitentes, "formatos": formatos,
            "asuntos_a_ignorar": _normalizadas(datos.get("asuntos_a_ignorar"))}


def cargar_banco(ruta: Path) -> dict:
    return validar_banco(cargar_json(ruta), Path(ruta).name)


def cargar_bancos(nombres: list[str], carpeta: Path = BANCOS_DIR) -> list[dict]:
    bancos = []
    for n in nombres:
        ruta = Path(n)
        if not ruta.suffix:
            ruta = carpeta / f"{n}.json"
        elif not ruta.is_absolute() and not ruta.exists():
            ruta = carpeta / ruta.name
        if not ruta.exists():
            raise ErrorDeConfig(f'En config.json pusiste el banco "{n}" pero no existe {ruta}.')
        bancos.append(cargar_banco(ruta))
    return bancos


# ---------------------------------------------------------------------------
# Interpretar un correo
# ---------------------------------------------------------------------------
def valor_de_etiqueta(texto: str, etiqueta: str) -> str | None:
    """Lo que viene después de 'Monto:' en la misma línea, o en la línea siguiente."""
    et = normalizar(etiqueta).strip()
    if not et:
        return None
    lineas = texto.split("\n")
    for i, ln in enumerate(lineas):
        pos = normalizar(ln).find(et)
        if pos < 0:
            continue
        resto = ln[pos + len(et):].strip(" :\t-–|")
        if resto:
            return resto
        for sig in lineas[i + 1:]:
            if sig.strip():
                return sig.strip()
    return None


def _contiene(texto_norm: str, frases: list[str]) -> bool:
    return any(f and f in texto_norm for f in frases)


def banco_del_remitente(remitente: str, bancos: list[dict]) -> dict | None:
    r = normalizar(remitente)
    for b in bancos:
        if any(x in r for x in b["remitentes"]):
            return b
    return None


def _extraer(fmt: dict, texto: str, cfg: Config) -> dict | None:
    datos: dict = {}
    if fmt["patron"] is not None:
        m = fmt["patron"].search(texto)
        if not m:
            return None
        g = {k: (v.strip() if isinstance(v, str) else v) for k, v in m.groupdict().items()}
        try:
            datos["monto"] = a_numero(g.get("monto") or "")
        except ValueError:
            return None
        datos["moneda"] = codigo_moneda(g.get("moneda"), cfg, estricto=False)
        datos["comercio"] = g.get("comercio")
        datos["cuenta"] = g.get("cuenta")
    else:
        et = fmt["etiquetas"]
        valor = valor_de_etiqueta(texto, et["monto"])
        encontrado = buscar_monto(valor, cfg) if valor else None
        if not encontrado:
            return None
        datos["monto"], datos["moneda"] = encontrado
        if et.get("moneda"):
            datos["moneda"] = codigo_moneda(valor_de_etiqueta(texto, et["moneda"]), cfg, estricto=False) or datos["moneda"]
        datos["comercio"] = valor_de_etiqueta(texto, et["comercio"]) if et.get("comercio") else None
        datos["cuenta"] = valor_de_etiqueta(texto, et["cuenta"]) if et.get("cuenta") else None
    if fmt["patron_cuenta"] is not None and not datos.get("cuenta"):
        mc = fmt["patron_cuenta"].search(texto)
        if mc:
            datos["cuenta"] = (mc.group(1) if mc.groups() else mc.group(0)).strip()
    if not datos.get("moneda"):
        datos["moneda"] = codigo_moneda(fmt.get("moneda_por_defecto"), cfg, estricto=False) or cfg.moneda
    if datos["monto"] <= 0:
        return None
    if datos.get("comercio"):
        datos["comercio"] = re.sub(r"\s+", " ", datos["comercio"])[:60]
    return datos


def interpretar_correo(remitente: str, asunto: str, texto: str, bancos: list[dict], cfg: Config) -> dict | None:
    """Devuelve None si el correo no es de ningún banco configurado. Si es, devuelve un dict con
    "tipo" (gasto / movimiento / ingreso / ignorar / no_entendido) y "diagnostico" (para probar_correo)."""
    banco = banco_del_remitente(remitente, bancos)
    if banco is None:
        return None
    diag = [f"Remitente coincide con el banco {banco['nombre']}."]
    asunto_n, texto_n = normalizar(asunto), normalizar(texto)
    if _contiene(asunto_n, banco["asuntos_a_ignorar"]):
        diag.append("El asunto está en \"asuntos_a_ignorar\": no es una compra.")
        return {"tipo": "ignorar", "banco": banco["nombre"], "diagnostico": diag}
    alguno_por_asunto = None
    for fmt in banco["formatos"]:
        if fmt["asunto_contiene"] and not _contiene(asunto_n, fmt["asunto_contiene"]):
            diag.append(f"Formato \"{fmt['nombre']}\": el asunto no contiene {fmt['asunto_contiene']}.")
            continue
        if fmt["asunto_contiene"]:
            alguno_por_asunto = fmt
        if _contiene(texto_n, fmt["ignorar_si_contiene"]):
            diag.append(f"Formato \"{fmt['nombre']}\": el texto dice algo de {fmt['ignorar_si_contiene']}, se ignora (ej. compra rechazada).")
            return {"tipo": "ignorar", "banco": banco["nombre"], "formato": fmt["nombre"], "diagnostico": diag}
        datos = _extraer(fmt, texto, cfg)
        if datos is None:
            diag.append(f"Formato \"{fmt['nombre']}\": {'el patrón' if fmt['patron'] is not None else 'las etiquetas'} "
                        "no encontraron el monto en el texto.")
            continue
        tipo = "ingreso" if _contiene(texto_n, fmt["es_ingreso_si_contiene"]) else fmt["tipo"]
        diag.append(f"Formato \"{fmt['nombre']}\" funcionó.")
        return {"tipo": tipo, "banco": banco["nombre"], "formato": fmt["nombre"], "diagnostico": diag, **datos}
    if alguno_por_asunto is not None:
        return {"tipo": "no_entendido", "banco": banco["nombre"], "formato": alguno_por_asunto["nombre"], "diagnostico": diag}
    diag.append("Ningún formato aplica a este correo (probablemente es publicidad o un aviso que no es compra).")
    return {"tipo": "ignorar", "banco": banco["nombre"], "diagnostico": diag}


# ---------------------------------------------------------------------------
# Buzón (IMAP)
# ---------------------------------------------------------------------------
def _carpeta(nombre: str) -> str:
    return f'"{nombre}"' if " " in nombre and not nombre.startswith('"') else nombre


def _bytes_del_fetch(respuesta) -> bytes | None:
    for item in respuesta or []:
        if isinstance(item, tuple) and len(item) > 1 and isinstance(item[1], (bytes, bytearray)):
            return bytes(item[1])
    return None


def revisar_buzon(cfg: Config, env: dict, estado: dict, bancos: list[dict], conectar=None,
                  carpeta_sin_entender: Path | None = None) -> list[dict]:
    """Lee correos nuevos (solo lectura: no marca nada como leído) y devuelve eventos.

    `estado` es libro.datos["correo"]; se actualiza el último UID visto.
    La primera vez solo se ancla en el último correo: no procesa tu historial.
    """
    usuario, clave = env.get("CORREO_USUARIO"), env.get("CORREO_CLAVE_APP")
    if not usuario or not clave or not bancos:
        return []
    eventos: list[dict] = []
    conectar = conectar or imaplib.IMAP4_SSL
    try:
        conn = conectar(cfg.correo_servidor)
    except OSError as exc:
        logger.warning(f"correo: sin conexión a {cfg.correo_servidor}: {exc}")
        return []
    try:
        conn.login(usuario, clave.replace(" ", ""))
        typ, _ = conn.select(_carpeta(cfg.correo_carpeta), readonly=True)
        if typ != "OK":
            return [{"tipo": "error", "mensaje": f'No existe la carpeta "{cfg.correo_carpeta}" en tu correo.'}]
        uv = conn.response("UIDVALIDITY")[1]
        uidvalidity = (uv[0].decode() if uv and isinstance(uv[0], bytes) else str(uv[0])) if uv and uv[0] else None
        ultimo = int(estado.get("ultimo_uid") or 0)
        if not estado.get("anclado") or (estado.get("uidvalidity") and uidvalidity and estado["uidvalidity"] != uidvalidity):
            typ, data = conn.uid("search", None, "ALL")
            uids = data[0].split() if typ == "OK" and data and data[0] else []
            estado["ultimo_uid"] = int(uids[-1]) if uids else 0
            estado["uidvalidity"] = uidvalidity
            estado["anclado"] = True
            logger.info(f"correo: listo, empiezo a leer desde el correo #{estado['ultimo_uid']} (no leo tu historial)")
            return [{"tipo": "anclado"}]
        typ, data = conn.uid("search", None, f"UID {ultimo + 1}:*")
        uids = sorted(int(u) for u in (data[0].split() if typ == "OK" and data and data[0] else []) if int(u) > ultimo)
        for uid in uids[:MAX_POR_VUELTA]:
            estado["ultimo_uid"] = uid
            typ, cab = conn.uid("fetch", str(uid), "(BODY.PEEK[HEADER.FIELDS (FROM SUBJECT DATE)])")
            crudo = _bytes_del_fetch(cab) if typ == "OK" else None
            if not crudo:
                continue
            h = email.message_from_bytes(crudo)
            remitente = decodificar_encabezado(h.get("From"))
            if banco_del_remitente(remitente, bancos) is None:
                continue
            typ, completo = conn.uid("fetch", str(uid), "(BODY.PEEK[])")
            crudo = _bytes_del_fetch(completo) if typ == "OK" else None
            if not crudo:
                continue
            msg = email.message_from_bytes(crudo)
            asunto = decodificar_encabezado(msg.get("Subject"))
            texto = texto_del_correo(msg)
            res = interpretar_correo(remitente, asunto, texto, bancos, cfg)
            if res is None or res["tipo"] == "ignorar":
                continue
            res["ts"] = (fecha_del_correo(msg.get("Date")) or datetime.now()).isoformat(timespec="seconds")
            res["asunto"] = asunto
            if res["tipo"] == "no_entendido" and carpeta_sin_entender is not None:
                carpeta_sin_entender.mkdir(parents=True, exist_ok=True)
                archivo = carpeta_sin_entender / f"{uid}.txt"
                archivo.write_text(f"De: {remitente}\nAsunto: {asunto}\n\n{texto[:8000]}", encoding="utf-8")
                res["archivo"] = str(archivo)
            eventos.append(res)
        estado.pop("ultimo_error", None)
    except imaplib.IMAP4.error as exc:
        detalle = str(exc)[:160]
        if estado.get("ultimo_error") != detalle:
            estado["ultimo_error"] = detalle
            eventos.append({"tipo": "error", "mensaje": (
                f"No pude entrar a tu correo ({detalle}). Revisá CORREO_USUARIO y CORREO_CLAVE_APP en el archivo .env "
                "(la clave es la contraseña de aplicación de 16 letras, no tu contraseña normal).")})
        logger.warning(f"correo: {detalle}")
    except OSError as exc:
        logger.warning(f"correo: se cortó la conexión: {exc}")
    finally:
        try:
            conn.logout()
        except Exception:  # noqa: BLE001
            pass
    return eventos
