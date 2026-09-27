#!/bin/bash
# Deja el bot prendido en tu Mac: arranca solo cuando iniciás sesión y se reinicia si se cae.
#
#   bash servicio/mac/instalar.sh           → instalar y prender
#   bash servicio/mac/instalar.sh --quitar  → apagar y desinstalar
#   bash servicio/mac/instalar.sh --solo-mostrar → mostrar el archivo sin instalar nada
#
# Ojo: la Mac tiene que estar prendida y despierta. Si se duerme, el bot se pausa hasta que despierte.
set -euo pipefail

CARPETA="$(cd "$(dirname "$0")/../.." && pwd)"
ETIQUETA="com.botgastos"
PLIST="$HOME/Library/LaunchAgents/$ETIQUETA.plist"
DOMINIO="gui/$(id -u)"

if [ "${1:-}" = "--quitar" ]; then
  launchctl bootout "$DOMINIO/$ETIQUETA" 2>/dev/null || launchctl unload "$PLIST" 2>/dev/null || true
  rm -f "$PLIST"
  echo "✅ Listo: el bot ya no arranca solo. (Tus datos siguen en $CARPETA/datos)"
  exit 0
fi

PYTHON="$(command -v python3 || true)"
if [ -z "$PYTHON" ]; then
  echo "❌ No encuentro python3. Instalalo primero (mirá el README)."
  exit 1
fi

case "$CARPETA" in
  "$HOME/Desktop"*|"$HOME/Documents"*|"$HOME/Downloads"*|"$HOME/Library/Mobile Documents"*)
    echo "❌ La carpeta del bot está en Escritorio, Documentos, Descargas o iCloud: macOS no deja que un"
    echo "   servicio lea ahí y el bot fallaría en silencio. Mové la carpeta a $HOME/bot-gastos y corré esto de nuevo."
    exit 1;;
esac

if ! grep -Eq '^TELEGRAM_TOKEN=["'"'"']?[0-9]+:' "$CARPETA/.env" 2>/dev/null; then
  echo "❌ No encuentro tu TELEGRAM_TOKEN en $CARPETA/.env. Primero corré: python3 configurar.py telegram"
  exit 1
fi

CONTENIDO="$("$PYTHON" - "$ETIQUETA" "$PYTHON" "$CARPETA" <<'PY'
import plistlib, sys
etiqueta, python, carpeta = sys.argv[1:4]
print(plistlib.dumps({
    "Label": etiqueta,
    "ProgramArguments": [python, f"{carpeta}/bot.py"],
    "WorkingDirectory": carpeta,
    "RunAtLoad": True,
    "KeepAlive": True,
    "ThrottleInterval": 30,
    "StandardOutPath": f"{carpeta}/datos/servicio.log",
    "StandardErrorPath": f"{carpeta}/datos/servicio.log",
    "EnvironmentVariables": {"PYTHONUNBUFFERED": "1", "PYTHONIOENCODING": "utf-8"},
}).decode())
PY
)"

if [ "${1:-}" = "--solo-mostrar" ]; then
  echo "$CONTENIDO"
  exit 0
fi

mkdir -p "$CARPETA/datos" "$HOME/Library/LaunchAgents"
echo "$CONTENIDO" > "$PLIST"
launchctl bootout "$DOMINIO/$ETIQUETA" 2>/dev/null || true
launchctl bootstrap "$DOMINIO" "$PLIST" 2>/dev/null || launchctl load "$PLIST"
sleep 3
if launchctl print "$DOMINIO/$ETIQUETA" 2>/dev/null | grep -q "state = running"; then
  echo "✅ Listo: el bot quedó prendido y va a arrancar solo cada vez que prendas la Mac."
  echo "   Probalo: mandale /hoy en Telegram. Si algo falla, mirá $CARPETA/datos/servicio.log"
else
  echo "⚠️  Lo instalé pero todavía no lo veo corriendo. Mirá $CARPETA/datos/servicio.log"
fi
echo "   Importante: cerrá la otra ventana donde lo tenías prendido (si quedan dos, Telegram se queja)."
