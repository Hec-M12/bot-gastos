"""El bot: recibe mensajes de Telegram, anota gastos, lee el correo y manda el resumen diario."""
from __future__ import annotations

import json
import logging
import secrets
import time
from datetime import datetime
from pathlib import Path

from . import vision
from .config import Config, a_moneda_local, codigo_moneda, dinero
from .correo import interpretar_correo, revisar_buzon
from .libro import Libro, e, mensaje_registro, resumen_hoy, resumen_mes
from .telegram import ErrorDeTelegram
from .texto import adivinar_categoria, clave_comercio, interpretar_gasto

logger = logging.getLogger("bot-gastos")

MAX_INTENTOS_CODIGO = 5
GENERICOS = ("sin nota", "compra", "movimiento en tu cuenta", None, "")


class Bot:
    def __init__(self, cfg: Config, env: dict, tg, datos_dir: Path, bancos: list[dict] | None = None,
                 leer_imagen=vision.leer_imagen, reloj=datetime.now, conectar_imap=None):
        self.cfg, self.env, self.tg = cfg, env, tg
        self.datos_dir = Path(datos_dir)
        self.bancos = bancos or []
        self.leer_imagen = leer_imagen
        self.reloj = reloj
        self.conectar_imap = conectar_imap
        self.libro = Libro(self.datos_dir / "gastos.json")
        self.estado_ruta = self.datos_dir / "estado.json"
        self.estado = self._cargar_estado()
        self.chat_id = str(env.get("TELEGRAM_CHAT_ID") or self.estado.get("chat_id") or "") or None
        if not self.chat_id and not self.estado.get("codigo"):
            self.estado["codigo"] = f"{secrets.randbelow(10 ** 6):06d}"
            self._guardar_estado()
        self._ultimo_correo = 0.0

    # --- estado (offset de Telegram, dueño del bot) -------------------------
    def _cargar_estado(self) -> dict:
        try:
            return json.loads(self.estado_ruta.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {"offset": 0}

    def _guardar_estado(self) -> None:
        self.datos_dir.mkdir(parents=True, exist_ok=True)
        tmp = self.estado_ruta.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.estado, ensure_ascii=False, indent=1), encoding="utf-8")
        tmp.replace(self.estado_ruta)

    @property
    def codigo(self) -> str | None:
        return None if self.chat_id else self.estado.get("codigo")

    # --- capacidades ----------------------------------------------------------
    @property
    def correo_activo(self) -> bool:
        return bool(self.env.get("CORREO_USUARIO") and self.env.get("CORREO_CLAVE_APP") and self.bancos)

    @property
    def fotos_activas(self) -> str | None:
        p = vision.proveedor(self.env)
        return p[0] if p else None

    # --- salida ---------------------------------------------------------------
    def enviar(self, texto: str, botones: list | None = None, silencioso: bool = False):
        if not self.chat_id or not texto:
            return None
        return self.tg.enviar(self.chat_id, texto, botones, silencioso)

    def ayuda(self) -> str:
        fotos = self.fotos_activas
        lineas = [
            "<b>Bot de gastos</b> 💸",
            "✍️ Escribí el monto y qué fue: <code>45 pizza</code> · <code>1,200 súper</code> · <code>20 uber #transporte</code>",
            ("📷 Mandame la captura de una compra y te pregunto antes de anotarla."
             if fotos else "📷 Fotos: apagado (falta una llave de IA en el archivo .env; Gemini tiene capa gratis)."),
            ("📧 Las compras que te lleguen al correo del banco se anotan solas."
             if self.correo_activo else "📧 Correo: apagado (opcional; se configura en el archivo .env)."),
            "",
            "/hoy · lo de hoy",
            "/mes · cómo vas en el mes",
            "/deshacer · borra el último gasto",
            "/categorias · tus categorías y topes",
            "/correo · estado del correo",
        ]
        return "\n".join(lineas)

    def texto_categorias(self) -> str:
        filas = [f"• <code>#{c['id']}</code> {e(c['nombre'])} · tope {dinero(c['tope'], self.cfg)}" for c in self.cfg.categorias]
        return ("<b>Tus categorías</b>\n" + "\n".join(filas) +
                f"\nTotal: {dinero(self.cfg.tope_total, self.cfg)} al mes."
                "\nPara forzar una: <code>45 algo #categoria</code>. Se cambian en config.json.")

    def teclado_categorias(self, prefijo: str, ref: str, cancelar: str | None = None) -> list:
        filas, fila = [], []
        for i, c in enumerate(self.cfg.categorias):
            fila.append({"text": c["nombre"][:24], "callback_data": f"{prefijo}:{ref}:{i}"})
            if len(fila) == 2:
                filas.append(fila)
                fila = []
        if fila:
            filas.append(fila)
        if cancelar:
            filas.append([{"text": cancelar, "callback_data": f"no:{ref}"}])
        return filas

    def boton_cambiar(self, gasto_id: int) -> list:
        return [[{"text": "✏️ Cambiar categoría", "callback_data": f"mv:{gasto_id}"}]]

    # --- registrar -------------------------------------------------------------
    def registrar(self, gasto: dict, aviso: str | None = None) -> tuple[str, list]:
        g = self.libro.agregar(gasto, self.reloj())
        self.libro.guardar()
        texto = mensaje_registro(self.libro, self.cfg, g)
        if aviso:
            texto += f"\n<i>{e(aviso)}</i>"
        return texto, self.boton_cambiar(g["id"])

    # --- entrada ---------------------------------------------------------------
    def procesar(self, update: dict) -> None:
        if "callback_query" in update:
            cb = update["callback_query"]
            chat = str(((cb.get("message") or {}).get("chat") or {}).get("id", ""))
            if self.chat_id and chat == self.chat_id:
                self.al_boton(cb)
            return
        msg = update.get("message") or {}
        chat = str((msg.get("chat") or {}).get("id", ""))
        if not chat:
            return
        if not self.chat_id:
            self.emparejar(chat, (msg.get("text") or "").strip())
            return
        if chat != self.chat_id:
            return  # bot privado: ignora a cualquier otra persona
        if msg.get("photo") or msg.get("document"):
            self.al_foto(msg)
        elif msg.get("text"):
            self.al_texto(msg["text"])

    def emparejar(self, chat: str, texto: str) -> None:
        intentos = self.estado.setdefault("intentos", {})
        if intentos.get(chat, 0) >= MAX_INTENTOS_CODIGO:
            return
        if texto.replace(" ", "") == self.estado.get("codigo"):
            self.chat_id = chat
            self.estado["chat_id"] = chat
            self.estado.pop("codigo", None)
            self.estado.pop("intentos", None)
            self._guardar_estado()
            logger.info("¡Listo! El bot ya tiene dueño (quedó guardado en datos/estado.json).")
            self.enviar("🎉 Listo, este bot ya es tuyo. Solo te hace caso a vos.\n\n" + self.ayuda())
            return
        if texto and not texto.startswith("/start"):
            intentos[chat] = intentos.get(chat, 0) + 1
            self._guardar_estado()
        self.tg.enviar(chat, "🔒 Este bot todavía no tiene dueño. Mandame el código de 6 números que aparece "
                             "en la ventana donde lo arrancaste (o corré <code>python3 revisar.py</code> para verlo).")

    def al_texto(self, texto: str) -> None:
        t = texto.strip()
        comando = t.split()[0].split("@")[0].lower() if t.startswith("/") else ""
        if comando in ("/start", "/ayuda", "/help"):
            self.enviar(self.ayuda())
        elif comando == "/mes":
            self.enviar(resumen_mes(self.libro, self.cfg, self.reloj().date()))
        elif comando == "/hoy":
            self.enviar(resumen_hoy(self.libro, self.cfg, self.reloj().date()))
        elif comando in ("/deshacer", "/undo"):
            g = self.libro.deshacer()
            if g is None:
                self.enviar("No hay nada que deshacer.")
            else:
                self.libro.guardar()
                self.enviar(f"🗑 Borré: {dinero(g['monto'], self.cfg)} · {e(self.cfg.nombre(g['cat']))} · {e(g['desc'])}")
        elif comando in ("/categorias", "/categorías"):
            self.enviar(self.texto_categorias())
        elif comando == "/correo":
            self.enviar(self.estado_correo())
        elif comando == "/resumen_diario":
            self.resumen_diario(forzar=True)
        elif comando:
            self.enviar("No conozco ese comando. /ayuda")
        else:
            self.anotar_texto(t)

    def anotar_texto(self, t: str) -> None:
        r = interpretar_gasto(t, self.cfg, self.libro.datos["aprendido"])
        if r["ok"]:
            self.enviar(*self.registrar(r["gasto"], r.get("aviso")))
            return
        if r["error"] == "categoria_desconocida":
            ids = " ".join(f"#{c['id']}" for c in self.cfg.categorias)
            self.enviar(f"No tengo la categoría <code>#{e(r['etiqueta'])}</code>. Las que hay: {e(ids)}")
        elif r["error"] == "monto_cero":
            self.enviar("El monto tiene que ser mayor que cero.")
        else:
            self.enviar("No entendí 🤔 Escribí primero el monto y después qué fue: <code>45 pizza</code>. /ayuda")

    # --- fotos -----------------------------------------------------------------
    def al_foto(self, msg: dict) -> None:
        fotos = msg.get("photo") or []
        doc = msg.get("document") or {}
        file_id = fotos[-1]["file_id"] if fotos else (doc.get("file_id") if str(doc.get("mime_type", "")).startswith("image/") else None)
        if not file_id:
            self.enviar("Solo leo imágenes (fotos o capturas).")
            return
        if not self.fotos_activas:
            self.enviar("📷 Para leer fotos necesito una llave de IA en el archivo .env (Gemini tiene capa gratis, "
                        "mirá el README). Mientras tanto mandámelo en texto: <code>45 súper</code>")
            return
        ruta = self.tg.bajar_archivo(file_id, self.datos_dir / "imagenes")
        if not ruta:
            self.enviar("No pude bajar la imagen. Mandala de nuevo.")
            return
        self.enviar("👀 Leyendo…", silencioso=True)
        try:
            v = self.leer_imagen(ruta, self.env)
        except vision.ErrorDeVision as exc:
            self.enviar(f"📷 {e(exc)}")
            return
        if not v:
            self.enviar("No encontré un monto en esa imagen. Mandámelo en texto: <code>45 súper</code>")
            return
        moneda = codigo_moneda(v.get("moneda"), self.cfg, estricto=False) if v.get("moneda") else None
        if not v.get("es_gasto", True):
            self.enviar(f"💵 Esa captura parece plata que te <b>entró</b> ({e(v.get('moneda') or '')} {v['monto']:,.2f}). "
                        "Este bot anota gastos; si igual es un gasto, mandámelo en texto.")
            return
        caption = (msg.get("caption") or "").strip()
        etiqueta = next((w[1:].lower() for w in caption.split() if w.startswith("#") and w[1:].lower() in self.cfg.por_id), None)
        desc = " ".join(w for w in caption.split() if not w.startswith("#")) or v.get("comercio") or "compra"
        local, aviso = a_moneda_local(v["monto"], moneda, self.cfg)
        gasto = {"monto": local, "desc": desc[:80], "origen": "foto",
                 "cat": etiqueta or adivinar_categoria(desc, self.cfg, self.libro.datos["aprendido"])}
        if moneda and moneda != self.cfg.moneda:
            gasto["original"] = {"monto": v["monto"], "moneda": moneda}
        pid = self.libro.guardar_pendiente("gasto", {"gasto": gasto, "aviso": aviso})
        self.libro.guardar()
        hoy = self.reloj().date().isoformat()
        repetido = any(abs(g["monto"] - local) < 0.01 for g in self.libro.del_dia(hoy))
        texto = (f"📷 Leí: <b>{dinero(local, self.cfg)}</b> · {e(desc)} · {e(self.cfg.nombre(gasto['cat']))}\n"
                 + ("⚠️ Ya tenés un gasto de ese mismo monto hoy (¿llegó por correo?). " if repetido else "")
                 + "¿Lo anoto?")
        botones = [[{"text": "✅ Anotar", "callback_data": f"ok:{pid}"},
                    {"text": "✏️ Categoría", "callback_data": f"cat:{pid}"},
                    {"text": "❌ No", "callback_data": f"no:{pid}"}]]
        self.enviar(texto, botones)

    # --- botones ---------------------------------------------------------------
    def al_boton(self, cb: dict) -> None:
        self.tg.responder_boton(cb.get("id", ""))
        mid = (cb.get("message") or {}).get("message_id")
        partes = str(cb.get("data", "")).split(":")
        accion, ref = partes[0], (partes[1] if len(partes) > 1 else "")
        extra = partes[2] if len(partes) > 2 else None

        if accion in ("mv", "mvc"):
            self._mover_gasto(mid, ref, extra)
            return

        pend = self.libro.datos["pendientes"].get(ref)
        if not pend:
            self.tg.editar(self.chat_id, mid, "Eso ya se resolvió o venció.")
            return
        d = pend["datos"]
        gasto = d["gasto"]
        if accion == "no":
            self.libro.datos["pendientes"].pop(ref, None)
            self.libro.guardar()
            self.tg.editar(self.chat_id, mid, "❌ Listo, no lo anoté.")
        elif accion == "cat":
            self.tg.editar(self.chat_id, mid, f"¿En qué categoría va {dinero(gasto['monto'], self.cfg)} · {e(gasto['desc'])}?",
                           self.teclado_categorias("set", ref, "❌ Cancelar"))
        elif accion in ("ok", "set"):
            if accion == "set" and extra is not None:
                cat = self._categoria_por_indice(extra)
                if cat is None:
                    return
                if gasto.get("desc") not in GENERICOS and cat != gasto.get("cat"):
                    self.libro.aprender(clave_comercio(gasto["desc"]), cat)
                gasto["cat"] = cat
            self.libro.datos["pendientes"].pop(ref, None)
            texto, botones = self.registrar(gasto, d.get("aviso"))
            self.tg.editar(self.chat_id, mid, texto, botones)

    def _categoria_por_indice(self, idx: str | None) -> str | None:
        try:
            return self.cfg.categorias[int(idx)]["id"]
        except (TypeError, ValueError, IndexError):
            return None

    def _mover_gasto(self, mid, ref: str, extra: str | None) -> None:
        g = next((x for x in self.libro.gastos if str(x.get("id")) == ref), None)
        if g is None:
            self.tg.editar(self.chat_id, mid, "Ese gasto ya no existe (¿lo borraste con /deshacer?).")
            return
        if extra is None:
            self.tg.editar(self.chat_id, mid, f"¿A qué categoría muevo {dinero(g['monto'], self.cfg)} · {e(g['desc'])}?",
                           self.teclado_categorias("mvc", ref))
            return
        cat = self._categoria_por_indice(extra)
        if cat is None:
            return
        g["cat"] = cat
        if g.get("desc") not in GENERICOS:
            self.libro.aprender(clave_comercio(g["desc"]), cat)
        self.libro.guardar()
        self.tg.editar(self.chat_id, mid, mensaje_registro(self.libro, self.cfg, g) + "\n<i>Listo, la próxima vez lo pongo ahí solo.</i>",
                       self.boton_cambiar(g["id"]))

    # --- correo ----------------------------------------------------------------
    def estado_correo(self) -> str:
        if not self.env.get("CORREO_USUARIO") or not self.env.get("CORREO_CLAVE_APP"):
            return "📧 El correo está apagado. Es opcional: se prende poniendo CORREO_USUARIO y CORREO_CLAVE_APP en el archivo .env."
        if not self.bancos:
            return '📧 Tenés el correo configurado pero ningún banco en config.json ("correo" → "bancos").'
        eventos = self.revisar_correo(forzar=True)
        est = self.libro.datos["correo"]
        if est.get("ultimo_error"):
            return f"📧 ⚠️ No puedo entrar a tu correo: {e(est['ultimo_error'])}"
        nombres = ", ".join(b["nombre"] for b in self.bancos)
        return (f"📧 Conectado a {e(self.env['CORREO_USUARIO'])}. Leo correos de {e(nombres)} cada "
                f"{self.cfg.correo_cada_min:g} min." + (f" Recién encontré {len(eventos)}." if eventos else ""))

    def revisar_correo(self, forzar: bool = False) -> list[dict]:
        if not self.correo_activo:
            return []
        if not forzar and time.time() - self._ultimo_correo < self.cfg.correo_cada_min * 60:
            return []
        self._ultimo_correo = time.time()
        eventos = revisar_buzon(self.cfg, self.env, self.libro.datos["correo"], self.bancos, self.conectar_imap,
                                self.datos_dir / "correos-sin-entender")
        self.libro.guardar()
        for ev in eventos:
            try:
                self.al_evento_correo(ev)
            except ErrorDeTelegram:
                raise
            except Exception:  # noqa: BLE001 - un correo raro no tumba el bot
                logger.exception("evento de correo")
        return eventos

    def al_evento_correo(self, ev: dict) -> None:
        tipo = ev["tipo"]
        if tipo == "anclado":
            nombres = ", ".join(b["nombre"] for b in self.bancos)
            self.enviar(f"📧 Conectado a tu correo. Desde ahora anoto solas las compras que te avise {e(nombres)}.", silencioso=True)
        elif tipo == "error":
            self.enviar(f"⚠️ {e(ev['mensaje'])}")
        elif tipo == "no_entendido":
            self.enviar(f"📧 Llegó un correo de {e(ev['banco'])} («{e(ev.get('asunto', ''))}») que no supe leer. "
                        "Lo guardé en la carpeta datos/correos-sin-entender para ajustar el patrón "
                        "(mirá bancos/COMO-AGREGAR-TU-BANCO.md).", silencioso=True)
        elif tipo == "ingreso":
            self.enviar(f"💵 Te entró {e(ev.get('moneda') or '')} {ev['monto']:,.2f} ({e(ev['banco'])}). No lo cuento como gasto.",
                        silencioso=True)
        elif tipo in ("gasto", "movimiento"):
            local, aviso = a_moneda_local(ev["monto"], ev.get("moneda"), self.cfg)
            desc = ev.get("comercio") or ("movimiento en tu cuenta" if tipo == "movimiento" else "compra")
            gasto = {"monto": local, "desc": desc, "origen": "correo", "ts": ev.get("ts"),
                     "cat": adivinar_categoria(desc, self.cfg, self.libro.datos["aprendido"])}
            if not gasto["ts"]:
                gasto.pop("ts")
            if ev.get("moneda") and ev["moneda"] != self.cfg.moneda:
                gasto["original"] = {"monto": ev["monto"], "moneda": ev["moneda"]}
            if ev.get("cuenta"):
                gasto["cuenta"] = str(ev["cuenta"])[-8:]
            if tipo == "gasto":
                self.enviar(*self.registrar(gasto, aviso))
                return
            pid = self.libro.guardar_pendiente("gasto", {"gasto": gasto, "aviso": aviso})
            self.libro.guardar()
            self.enviar(f"📧 Salieron <b>{dinero(local, self.cfg)}</b> de tu cuenta ({e(ev['banco'])}), "
                        "pero el correo no dice en qué. ¿En qué categoría lo anoto?",
                        self.teclado_categorias("set", pid, "No es un gasto"))

    # --- tareas programadas -------------------------------------------------------
    def resumen_diario(self, forzar: bool = False) -> bool:
        if not self.chat_id:
            return False
        ahora = self.reloj()
        hora = self.cfg.resumen_diario_hora
        clave = ahora.date().isoformat()
        hechos = self.libro.datos["resumenes"]
        if not forzar and (hora is None or ahora.hour < hora or hechos.get(clave)):
            return False
        hechos[clave] = True
        for k in sorted(hechos)[:-60]:
            hechos.pop(k, None)
        self.libro.guardar()
        self.enviar(resumen_hoy(self.libro, self.cfg, ahora.date(), "<b>Resumen del día</b>") + "\n\n"
                    + resumen_mes(self.libro, self.cfg, ahora.date(), "<b>Mes hasta hoy</b>"), silencioso=True)
        return True

    # --- vuelta principal -----------------------------------------------------------
    def una_vuelta(self) -> None:
        offset = int(self.estado.get("offset", 0))
        for u in self.tg.actualizaciones(offset):
            self.estado["offset"] = int(u.get("update_id", offset)) + 1
            self._guardar_estado()
            try:
                self.procesar(u)
            except ErrorDeTelegram:
                raise
            except Exception as exc:  # noqa: BLE001 - un mensaje raro no tumba el bot
                logger.exception("procesando mensaje")
                self.enviar(f"Se me rompió algo con ese mensaje ({e(type(exc).__name__)}). Probá de otra forma.")
        self.revisar_correo()
        self.resumen_diario()

    def correr(self, parar=lambda: False) -> None:
        espera = 2
        while not parar():
            try:
                self.una_vuelta()
                espera = 2
            except ErrorDeTelegram as exc:
                if exc.codigo == 409:
                    logger.error("Hay OTRA copia del bot prendida con el mismo token (¿en otra ventana o como servicio?). "
                                 "Dejá solo una.")
                    espera = 30
                elif exc.codigo in (401, 404):
                    logger.error("Telegram dice que el TELEGRAM_TOKEN no es válido. Revisalo en el archivo .env.")
                    espera = 60
                else:
                    logger.warning(f"Telegram: {exc}")
                    espera = min(espera * 2, 60)
                time.sleep(espera)
            except Exception:  # noqa: BLE001
                logger.exception("vuelta principal")
                espera = min(espera * 2, 60)
                time.sleep(espera)


def evento_desde_eml(ruta: Path, bot: Bot) -> dict | None:
    """Para la simulación: lee un .eml como si hubiera llegado al buzón."""
    from .correo import leer_eml
    remitente, asunto, texto, fecha = leer_eml(ruta)
    res = interpretar_correo(remitente, asunto, texto, bot.bancos, bot.cfg)
    if res is None:
        return None
    res["asunto"] = asunto
    res["ts"] = (fecha or datetime.now()).isoformat(timespec="seconds")
    return res

