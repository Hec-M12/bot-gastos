"""Cliente mínimo de la API de Telegram (solo stdlib) + un Telegram de mentira para probar."""
from __future__ import annotations

import http.client
import json
import logging
import shutil
import time
import urllib.error
import urllib.request
from pathlib import Path

logger = logging.getLogger("bot-gastos")

LIMITE_TEXTO = 4096
ESPERA_LARGA = 25  # segundos que Telegram retiene getUpdates si no hay mensajes


class ErrorDeTelegram(Exception):
    def __init__(self, codigo: int, descripcion: str):
        super().__init__(f"{codigo}: {descripcion}")
        self.codigo = codigo
        self.descripcion = descripcion


def _cortar(texto: str) -> str:
    return texto if len(texto) <= LIMITE_TEXTO else texto[:LIMITE_TEXTO - 1] + "…"


class Telegram:
    """Habla con api.telegram.org. `transporte(metodo, payload, timeout) -> dict` se puede cambiar en tests."""

    def __init__(self, token: str, transporte=None, reintentos: int = 3):
        self.token = token
        self._transporte = transporte or self._http
        self.reintentos = reintentos

    def _http(self, metodo: str, payload: dict, timeout: float) -> dict:
        url = f"https://api.telegram.org/bot{self.token}/{metodo}"
        req = urllib.request.Request(url, data=json.dumps(payload).encode(), headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            try:
                return json.loads(exc.read().decode("utf-8"))
            except (json.JSONDecodeError, OSError):
                return {"ok": False, "error_code": exc.code, "description": str(exc.reason)}

    def llamar(self, metodo: str, payload: dict | None = None, timeout: float = 20) -> dict:
        """Devuelve result o tira ErrorDeTelegram. Reintenta cortes de red."""
        ultimo: Exception | None = None
        for intento in range(self.reintentos):
            try:
                r = self._transporte(metodo, payload or {}, timeout)
            except (OSError, http.client.HTTPException, json.JSONDecodeError) as exc:
                ultimo = exc
                time.sleep(min(2 ** intento, 8))
                continue
            if r.get("ok"):
                return r.get("result")
            codigo = int(r.get("error_code") or 0)
            if codigo == 429:
                espera = int((r.get("parameters") or {}).get("retry_after") or 3)
                time.sleep(min(espera, 30))
                continue
            raise ErrorDeTelegram(codigo, str(r.get("description") or "error"))
        raise ErrorDeTelegram(0, f"sin conexión con Telegram ({ultimo})")

    # --- atajos -------------------------------------------------------------
    def enviar(self, chat_id, texto: str, botones: list | None = None, silencioso: bool = False) -> dict | None:
        payload = {"chat_id": chat_id, "text": _cortar(texto), "parse_mode": "HTML",
                   "disable_notification": silencioso, "disable_web_page_preview": True}
        if botones:
            payload["reply_markup"] = {"inline_keyboard": botones}
        try:
            return self.llamar("sendMessage", payload)
        except ErrorDeTelegram as exc:
            if exc.codigo == 400 and "parse" in exc.descripcion.lower():
                payload.pop("parse_mode")
                return self.llamar("sendMessage", payload)
            raise

    def editar(self, chat_id, message_id: int, texto: str, botones: list | None = None) -> None:
        payload = {"chat_id": chat_id, "message_id": message_id, "text": _cortar(texto), "parse_mode": "HTML",
                   "reply_markup": {"inline_keyboard": botones or []}, "disable_web_page_preview": True}
        try:
            self.llamar("editMessageText", payload)
        except ErrorDeTelegram as exc:
            if "not modified" not in exc.descripcion.lower():
                raise

    def responder_boton(self, callback_id: str, texto: str | None = None) -> None:
        try:
            self.llamar("answerCallbackQuery", {"callback_query_id": callback_id, **({"text": texto} if texto else {})})
        except ErrorDeTelegram:
            pass  # si el botón es viejo Telegram dice que venció; no importa

    def actualizaciones(self, offset: int, espera: int = ESPERA_LARGA) -> list[dict]:
        return self.llamar("getUpdates", {"offset": offset, "timeout": espera,
                                          "allowed_updates": ["message", "callback_query"]}, timeout=espera + 15) or []

    def quien_soy(self) -> dict:
        return self.llamar("getMe")

    def bajar_archivo(self, file_id: str, carpeta: Path) -> Path | None:
        info = self.llamar("getFile", {"file_id": file_id})
        ruta_remota = info.get("file_path") if info else None
        if not ruta_remota:
            return None
        carpeta.mkdir(parents=True, exist_ok=True)
        destino = carpeta / f"{int(time.time())}-{Path(ruta_remota).name}"
        try:
            with urllib.request.urlopen(f"https://api.telegram.org/file/bot{self.token}/{ruta_remota}", timeout=60) as resp, \
                    open(destino, "wb") as fh:
                shutil.copyfileobj(resp, fh)
        except (urllib.error.URLError, OSError) as exc:
            logger.warning(f"no pude bajar la imagen: {type(exc).__name__}")
            return None
        return destino


class TelegramSimulado:
    """Imprime en pantalla lo que el bot mandaría. Sirve para probar sin Telegram (python3 bot.py --simular)."""

    def __init__(self, salida=print):
        self.salida = salida
        self.mensajes: list[dict] = []
        self._mid = 0
        self.ultimos_botones: list | None = None
        self.ultimo_mid: int | None = None

    def _mostrar(self, texto: str, botones: list | None, prefijo: str) -> None:
        import html
        import re
        limpio = html.unescape(re.sub(r"</?(b|i|pre|code)>", "", texto))
        self.salida(f"\n{prefijo}\n{limpio}")
        if botones:
            planos = [b for fila in botones for b in fila]
            self.salida("   " + "   ".join(f"[b{i}] {b['text']}" for i, b in enumerate(planos, 1)))

    def enviar(self, chat_id, texto: str, botones: list | None = None, silencioso: bool = False) -> dict:
        self._mid += 1
        self.mensajes.append({"chat_id": chat_id, "texto": texto, "botones": botones, "message_id": self._mid})
        self._mostrar(texto, botones, "🤖 bot:" + (" (sin sonido)" if silencioso else ""))
        if botones:
            self.ultimos_botones, self.ultimo_mid = botones, self._mid
        return {"message_id": self._mid}

    def editar(self, chat_id, message_id: int, texto: str, botones: list | None = None) -> None:
        self.mensajes.append({"chat_id": chat_id, "texto": texto, "botones": botones, "message_id": message_id, "editado": True})
        self._mostrar(texto, botones, "🤖 bot (cambia el mensaje anterior):")
        if botones:
            self.ultimos_botones, self.ultimo_mid = botones, message_id
        elif message_id == self.ultimo_mid:
            self.ultimos_botones = None

    def responder_boton(self, callback_id: str, texto: str | None = None) -> None:
        pass

    def bajar_archivo(self, file_id: str, carpeta: Path) -> Path | None:
        p = Path(file_id)  # en la simulación el "file_id" es la ruta local de la imagen
        return p if p.exists() else None
