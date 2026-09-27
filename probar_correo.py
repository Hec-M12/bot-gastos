#!/usr/bin/env python3
"""Prueba si el bot entiende un correo de tu banco, SIN conectarse a tu correo.

    python3 probar_correo.py ejemplos/bac-compra.eml          → ¿qué sacaría el bot de este correo?
    python3 probar_correo.py --ver-texto mi-correo.eml         → el texto tal como lo ve el bot (para armar el patrón)
    python3 probar_correo.py --banco bancos/mi_banco.json mi-correo.eml
    python3 probar_correo.py --pegar                           → pegás el correo acá mismo (sin archivo)

Cómo bajar un correo como .eml en Gmail (computadora): abrí el correo → los tres puntitos (⋮) → "Descargar mensaje".
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

if sys.version_info < (3, 9):
    sys.exit("Necesitás Python 3.9 o más nuevo.")

from gastos.config import ErrorDeConfig, cargar_config, dinero  # noqa: E402
from gastos.config import a_moneda_local  # noqa: E402
from gastos.correo import cargar_banco, cargar_bancos, interpretar_correo, leer_eml, limpiar  # noqa: E402
from gastos.texto import adivinar_categoria  # noqa: E402


def leer_pegado() -> tuple[str, str, str]:
    print("Pegá los datos del correo. Tip: primero corré --ver-texto con el .eml si lo tenés, es más exacto.")
    remitente = input("1) ¿Quién lo manda? (el correo del remitente, ej. alertas@tubanco.example): ").strip()
    asunto = input("2) ¿Cuál es el asunto?: ").strip()
    print("3) Pegá el texto del correo. Cuando termines, escribí FIN solo en una línea y dale Enter:")
    lineas = []
    while True:
        try:
            ln = input()
        except EOFError:
            break
        if ln.strip().upper() == "FIN":
            break
        lineas.append(ln)
    return remitente, asunto, limpiar("\n".join(lineas))


def main() -> int:
    p = argparse.ArgumentParser(description="Probá el patrón de tu banco contra un correo")
    p.add_argument("archivo", nargs="?", type=Path, help="correo guardado como .eml (o .txt con el texto)")
    p.add_argument("--banco", type=Path, help="archivo de banco a probar (por defecto: los de config.json)")
    p.add_argument("--ver-texto", action="store_true", help="solo mostrar el texto como lo ve el bot")
    p.add_argument("--pegar", action="store_true", help="pegar el correo acá en vez de usar un archivo")
    p.add_argument("--asunto", help="asunto (si usás un .txt)")
    p.add_argument("--remitente", help="remitente (si usás un .txt)")
    a = p.parse_args()

    try:
        cfg = cargar_config()
    except ErrorDeConfig as exc:
        print(f"❌ {exc}")
        return 2

    if a.pegar:
        remitente, asunto, texto = leer_pegado()
    elif a.archivo:
        if not a.archivo.exists():
            print(f"❌ No encuentro el archivo {a.archivo}. Fijate que esté en esta carpeta o poné la ruta completa.")
            return 2
        if a.archivo.suffix.lower() == ".eml":
            remitente, asunto, texto, _ = leer_eml(a.archivo)
        else:
            texto = limpiar(a.archivo.read_text(encoding="utf-8", errors="replace"))
            remitente, asunto = a.remitente or "", a.asunto or ""
        remitente = a.remitente or remitente
        asunto = a.asunto or asunto
    else:
        p.print_help()
        return 2

    if a.ver_texto:
        print("=" * 60)
        print(f"DE: {remitente}\nASUNTO: {asunto}\n" + "-" * 60)
        print(texto)
        print("=" * 60)
        print("⚠️ Antes de pegarle esto a una IA, tachá tu nombre, números de tarjeta/cuenta y lo que no quieras compartir.")
        return 0

    try:
        bancos = [cargar_banco(a.banco)] if a.banco else cargar_bancos(cfg.correo_bancos)
    except ErrorDeConfig as exc:
        print(f"❌ {exc}")
        return 2
    if not bancos:
        print('❌ No hay bancos: agregá uno en config.json ("correo" → "bancos") o usá --banco.')
        return 2

    print(f"Correo de: {remitente or '(sin remitente)'}\nAsunto:    {asunto or '(sin asunto)'}\n")
    res = interpretar_correo(remitente, asunto, texto, bancos, cfg)
    if res is None:
        todos = "; ".join(f"{b['nombre']}: {b['remitentes']}" for b in bancos)
        print(f"❌ El remitente no coincide con ningún banco ({todos}).")
        print('   Arreglo: poné en "remitentes" una parte del correo de quien manda (ej. "tubanco" o "alertas@tubanco.example").')
        return 1
    for d in res["diagnostico"]:
        print(f"  • {d}")
    print()
    if res["tipo"] in ("gasto", "movimiento", "ingreso"):
        local, aviso = a_moneda_local(res["monto"], res.get("moneda"), cfg)
        print("✅ El bot entendió este correo:")
        print(f"   tipo:      {res['tipo']}")
        print(f"   monto:     {res['monto']:,.2f}")
        print(f"   moneda:    {res.get('moneda')}")
        print(f"   comercio:  {res.get('comercio') or '(no dice)'}")
        if res.get("cuenta"):
            print(f"   cuenta:    …{str(res['cuenta'])[-4:]}")
        if res["tipo"] == "gasto":
            cat = adivinar_categoria(res.get("comercio") or "", cfg)
            print(f"   → lo anotaría como {dinero(local, cfg)} en «{cfg.nombre(cat)}»")
        elif res["tipo"] == "movimiento":
            print(f"   → te preguntaría en qué categoría va ({dinero(local, cfg)})")
        else:
            print("   → te avisaría que te entró plata (no cuenta como gasto)")
        if aviso:
            print(f"   ⚠️ {aviso}")
        return 0
    if res["tipo"] == "ignorar":
        print("ℹ️ El bot IGNORA este correo (está bien si no es una compra).")
        return 1
    print("❌ El asunto coincide pero no encontré el monto. Corré con --ver-texto y ajustá el patrón o las etiquetas.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
