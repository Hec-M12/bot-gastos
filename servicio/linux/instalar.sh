#!/bin/bash
# Deja el bot prendido en Linux con systemd (se reinicia solo si se cae).
#
#   bash servicio/linux/instalar.sh           → instalar y prender
#   bash servicio/linux/instalar.sh --quitar  → apagar y desinstalar
#   bash servicio/linux/instalar.sh --solo-mostrar → mostrar el archivo sin instalar nada
#
# Si tu Linux no tiene systemd, usa cron (@reboot) como plan B.
# Ojo: la compu tiene que estar prendida para que el bot funcione.
set -euo pipefail

CARPETA="$(cd "$(dirname "$0")/../.." && pwd)"
SERVICIO="bot-gastos.service"
DESTINO="$HOME/.config/systemd/user/$SERVICIO"
PYTHON="$(command -v python3 || true)"

if [ "${1:-}" = "--quitar" ]; then
  if command -v systemctl >/dev/null 2>&1; then
    systemctl --user disable --now "$SERVICIO" 2>/dev/null || true
    rm -f "$DESTINO"
    systemctl --user daemon-reload 2>/dev/null || true
  fi
  (crontab -l 2>/dev/null | grep -v "bot-gastos-autostart") | crontab - 2>/dev/null || true
  echo "✅ Listo: el bot ya no arranca solo. (Tus datos siguen en $CARPETA/datos)"
  exit 0
fi

if [ -z "$PYTHON" ]; then
  echo "❌ No encuentro python3. Instalalo con el gestor de paquetes (ej. sudo apt install python3)."
  exit 1
fi
if ! grep -Eq '^TELEGRAM_TOKEN=["'"'"']?[0-9]+:' "$CARPETA/.env" 2>/dev/null; then
  echo "❌ No encuentro tu TELEGRAM_TOKEN en $CARPETA/.env. Primero corré: python3 configurar.py telegram"
  exit 1
fi

UNIDAD="[Unit]
Description=Bot de gastos (Telegram)
After=network-online.target
Wants=network-online.target

[Service]
WorkingDirectory=$CARPETA
ExecStart=\"$PYTHON\" \"$CARPETA/bot.py\"
Restart=always
RestartSec=30
Environment=PYTHONUNBUFFERED=1
Environment=PYTHONIOENCODING=utf-8

[Install]
WantedBy=default.target"

if [ "${1:-}" = "--solo-mostrar" ]; then
  echo "$UNIDAD"
  exit 0
fi

mkdir -p "$CARPETA/datos"
if command -v systemctl >/dev/null 2>&1 && systemctl --user show-environment >/dev/null 2>&1; then
  mkdir -p "$(dirname "$DESTINO")"
  echo "$UNIDAD" > "$DESTINO"
  systemctl --user daemon-reload
  systemctl --user enable --now "$SERVICIO"
  # Para que siga corriendo aunque cierres sesión:
  loginctl enable-linger "$USER" 2>/dev/null || echo "ℹ️  Para que corra aunque no hayas iniciado sesión: sudo loginctl enable-linger $USER"
  sleep 2
  systemctl --user --no-pager status "$SERVICIO" | head -5 || true
  echo "✅ Listo con systemd. Ver qué hace: journalctl --user -u $SERVICIO -f"
else
  LINEA="@reboot cd \"$CARPETA\" && $PYTHON bot.py >> datos/servicio.log 2>&1 # bot-gastos-autostart"
  (crontab -l 2>/dev/null | grep -v "bot-gastos-autostart"; echo "$LINEA") | crontab -
  (cd "$CARPETA" && nohup "$PYTHON" bot.py >> datos/servicio.log 2>&1 &)
  echo "✅ Listo con cron: arranca solo al prender la compu (y ya lo prendí ahora)."
fi
echo "   Importante: cerrá la otra ventana donde lo tenías prendido (si quedan dos, Telegram se queja)."
