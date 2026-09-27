#!/usr/bin/env python3
"""Arranca el bot de gastos.

    python3 bot.py              → prende el bot (dejá la ventana abierta)
    python3 bot.py --simular    → probalo sin Telegram, escribiendo acá mismo
"""
from __future__ import annotations

import argparse
import logging
import logging.handlers
import shutil
import sys
import tempfile
from pathlib import Path

if sys.version_info < (3, 9):
    sys.exit("Necesitás Python 3.9 o más nuevo. Tenés " + sys.version.split()[0] + ". Mirá el README, paso de Python.")

from gastos.app import Bot, evento_desde_eml  # noqa: E402
from gastos.config import DATOS_DIR, ENV_FILE, RAIZ, ErrorDeConfig, cargar_config, leer_env  # noqa: E402
from gastos.correo import cargar_bancos  # noqa: E402
from gastos.telegram import ErrorDeTelegram, Telegram, TelegramSimulado  # noqa: E402

logger = logging.getLogger("bot-gastos")


def configurar_logs(datos_dir: Path, a_archivo: bool = True) -> None:
    logger.setLevel(logging.INFO)
    logger.handlers.clear()
    formato = logging.Formatter("%(asctime)s %(levelname)s %(message)s", "%Y-%m-%d %H:%M:%S")
    if sys.stderr is not None:  # con pythonw (Windows) no hay consola
        h = logging.StreamHandler(sys.stderr)
        h.setFormatter(formato)
        logger.addHandler(h)
    if a_archivo:
        datos_dir.mkdir(parents=True, exist_ok=True)
        f = logging.handlers.RotatingFileHandler(datos_dir / "bot.log", maxBytes=1_000_000, backupCount=2, encoding="utf-8")
        f.setFormatter(formato)
        logger.addHandler(f)


def decir(texto: str = "") -> None:
    if sys.stdout is not None:
        try:
            print(texto, flush=True)
        except UnicodeEncodeError:
            print(texto.encode("ascii", "replace").decode(), flush=True)


def preparar(simulando: bool = False):
    """Carga .env, config.json y bancos. Sale con un mensaje claro si algo falta."""
    ejemplo = RAIZ / ".env.example"
    if not ENV_FILE.exists() and ejemplo.exists() and not simulando:
        shutil.copyfile(ejemplo, ENV_FILE)
        decir("Creé el archivo .env (copia de .env.example). Abrilo y pegá tu TELEGRAM_TOKEN.")
    env = leer_env()
    creado = not (RAIZ / "config.json").exists()
    try:
        cfg = cargar_config()
    except ErrorDeConfig as exc:
        sys.exit(f"❌ {exc}")
    if creado:
        decir("Creé config.json con categorías de ejemplo. Editalo con tus categorías y topes cuando quieras.")
    bancos = []
    if cfg.correo_bancos and (simulando or (env.get("CORREO_USUARIO") and env.get("CORREO_CLAVE_APP"))):
        try:
            bancos = cargar_bancos(cfg.correo_bancos)
        except ErrorDeConfig as exc:
            sys.exit(f"❌ Problema con un banco: {exc}")
    return cfg, env, bancos


def simular(entrada=None, datos: Path | None = None) -> None:
    cfg, env, bancos = preparar(simulando=True)
    datos = datos or Path(tempfile.mkdtemp(prefix="bot-gastos-simulacion-"))
    configurar_logs(datos, a_archivo=False)
    tg = TelegramSimulado(salida=decir)
    bot = Bot(cfg, env, tg, datos, bancos)
    bot.chat_id = "simulacion"
    decir("💸 MODO SIMULACIÓN: escribí como si fuera Telegram. Nada sale de tu compu.")
    decir(f"   (los datos de prueba van a {datos}, no a tu libro real)")
    decir("   Probá: 45 pizza · /mes · /hoy · /deshacer · b1 (toca el botón 1) · salir")
    decir("   Extra: /eml ejemplos/bac-compra.eml (simula un correo) · /foto ruta.jpg (lee una captura)")
    entrada = entrada or sys.stdin
    uid = 0
    while True:
        if entrada is sys.stdin and sys.stdin.isatty():
            try:
                linea = input("\n🧑 vos: ")
            except EOFError:
                break
        else:
            linea = entrada.readline()
            if not linea:
                break
            linea = linea.rstrip("\n")
            decir(f"\n🧑 vos: {linea}")
        linea = linea.strip()
        if not linea:
            continue
        if linea.lower() in ("salir", "exit", "quit"):
            break
        uid += 1
        if linea.lower().startswith("b") and linea[1:].isdigit():
            planos = [b for fila in (tg.ultimos_botones or []) for b in fila]
            n = int(linea[1:])
            if not 1 <= n <= len(planos):
                decir("   (no hay un botón con ese número)")
                continue
            bot.procesar({"update_id": uid, "callback_query": {"id": str(uid), "data": planos[n - 1]["callback_data"],
                                                                "message": {"message_id": tg.ultimo_mid, "chat": {"id": "simulacion"}}}})
        elif linea.startswith("/eml "):
            ruta = Path(linea[5:].strip())
            if not ruta.exists():
                decir(f"   (no existe {ruta})")
                continue
            ev = evento_desde_eml(ruta, bot)
            if ev is None:
                decir("   (ese correo no es de ningún banco de tu config.json)")
            elif ev["tipo"] == "ignorar":
                decir("   (el bot ignora ese correo: " + ev["diagnostico"][-1] + ")")
            else:
                bot.al_evento_correo(ev)
        elif linea.startswith("/foto "):
            bot.procesar({"update_id": uid, "message": {"chat": {"id": "simulacion"}, "photo": [{"file_id": linea[6:].strip()}]}})
        else:
            bot.procesar({"update_id": uid, "message": {"chat": {"id": "simulacion"}, "text": linea}})
    decir("\nFin de la simulación.")


def arrancar() -> None:
    cfg, env, bancos = preparar()
    configurar_logs(DATOS_DIR)
    token = (env.get("TELEGRAM_TOKEN") or "").strip()
    if not token or token.startswith("pega"):
        sys.exit("❌ Falta TELEGRAM_TOKEN en el archivo .env (te lo da BotFather en Telegram). Mirá el README.")
    tg = Telegram(token)
    try:
        yo = tg.quien_soy()
    except ErrorDeTelegram as exc:
        if exc.codigo in (401, 404):
            sys.exit("❌ Telegram dice que el TELEGRAM_TOKEN no es válido. Copialo de nuevo de BotFather, completo.")
        sys.exit(f"❌ No pude conectarme a Telegram: {exc}. ¿Hay internet?")
    bot = Bot(cfg, env, tg, DATOS_DIR, bancos)
    decir("💸 Bot de gastos prendido")
    decir(f"   Telegram: @{yo.get('username')} ✅")
    decir(f"   Correo:   {'prendido (' + ', '.join(b['nombre'] for b in bancos) + ')' if bot.correo_activo else 'apagado (opcional)'}")
    decir(f"   Fotos:    {bot.fotos_activas or 'apagado (opcional)'}")
    if bot.codigo:
        decir("")
        decir(f"   👉 Abrí Telegram, buscá @{yo.get('username')} y mandale este código: {bot.codigo}")
        logger.info(f"Esperando dueño. Código para mandarle al bot: {bot.codigo}")
    decir("   Dejá esta ventana abierta. Para apagarlo: Ctrl+C.")
    logger.info("bot prendido")
    try:
        bot.correr()
    except KeyboardInterrupt:
        decir("\nBot apagado. 👋")


def main() -> None:
    p = argparse.ArgumentParser(description="Bot de gastos por Telegram")
    p.add_argument("--simular", action="store_true", help="probar sin Telegram, escribiendo en esta ventana")
    p.add_argument("--datos", type=Path, help="carpeta de datos para la simulación")
    a = p.parse_args()
    if a.simular:
        simular(datos=a.datos)
    else:
        arrancar()


if __name__ == "__main__":
    main()
