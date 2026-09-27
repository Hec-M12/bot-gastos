"""Las herramientas de línea de comando, corridas en una copia limpia del repo (como la bajaría un novato)."""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from ayuda import RAIZ

TOKEN_FALSO = "123456789:AAAA-token-inventado-para-la-prueba-0000"
CLAVE_FALSA = "qwer tyui asdf ghjk"
LLAVE_FALSA = "llave-inventada-de-gemini-XYZ"


class CopiaLimpia(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = Path(self.tmp.name) / "bot-gastos"
        shutil.copytree(RAIZ, self.repo, ignore=shutil.ignore_patterns(
            ".git", "datos", "config.json", ".env", "__pycache__", ".pytest_cache"))
        self.env = {k: v for k, v in os.environ.items() if k not in (
            "TELEGRAM_TOKEN", "TELEGRAM_CHAT_ID", "CORREO_USUARIO", "CORREO_CLAVE_APP",
            "GEMINI_API_KEY", "OPENAI_API_KEY", "ANTHROPIC_API_KEY", "VISION_PROVEEDOR", "VISION_MODELO")}
        self.env["PYTHONIOENCODING"] = "utf-8"

    def tearDown(self):
        self.tmp.cleanup()

    def correr(self, *args, entrada: str | None = None, env: dict | None = None):
        return subprocess.run([sys.executable, *args], cwd=self.repo, capture_output=True, text=True, encoding="utf-8",
                              input=entrada, env={**self.env, **(env or {})}, timeout=60)

    def test_probar_correo_bac(self):
        r = self.correr("probar_correo.py", "ejemplos/bac-compra.eml")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("PIZZERIA LA FAMOSA", r.stdout)
        self.assertIn("Comida fuera", r.stdout)
        self.assertTrue((self.repo / "config.json").exists())  # se crea solo

    def test_probar_correo_rechazada_y_plantilla(self):
        self.assertEqual(self.correr("probar_correo.py", "ejemplos/bac-rechazada.eml").returncode, 1)
        r = self.correr("probar_correo.py", "--banco", "bancos/plantilla.json", "ejemplos/banco-ejemplo.eml")
        self.assertEqual(r.returncode, 0, r.stdout)
        self.assertIn("FARMACIA SAN ROQUE", r.stdout)

    def test_probar_correo_ver_texto_y_pegar(self):
        r = self.correr("probar_correo.py", "--ver-texto", "ejemplos/bac-compra.eml")
        self.assertIn("Comercio\nMonto\nPIZZERIA LA FAMOSA\nUSD 12.50", r.stdout)
        pegado = "avisos@banco-ejemplo.invalid\nCompra aprobada\nComercio: KIOSCO LA ESQUINA\nMonto: $ 3.25\nFIN\n"
        r = self.correr("probar_correo.py", "--banco", "bancos/plantilla.json", "--pegar", entrada=pegado)
        self.assertEqual(r.returncode, 0, r.stdout)
        self.assertIn("KIOSCO LA ESQUINA", r.stdout)

    def test_probar_correo_archivo_que_no_existe(self):
        r = self.correr("probar_correo.py", "no-existe.eml")
        self.assertEqual(r.returncode, 2)
        self.assertIn("No encuentro el archivo", r.stdout)

    def test_revisar_no_muestra_secretos(self):
        (self.repo / ".env").write_text(
            f"TELEGRAM_TOKEN={TOKEN_FALSO}\nCORREO_USUARIO=persona@ejemplo.invalid\nCORREO_CLAVE_APP={CLAVE_FALSA}\n"
            f"GEMINI_API_KEY={LLAVE_FALSA}\n", encoding="utf-8")
        r = self.correr("revisar.py")
        salida = r.stdout + r.stderr
        self.assertEqual(r.returncode, 0, salida)
        for secreto in (TOKEN_FALSO, TOKEN_FALSO.split(":")[1], CLAVE_FALSA, CLAVE_FALSA.replace(" ", ""), LLAVE_FALSA):
            self.assertNotIn(secreto, salida)
        self.assertIn("Todo listo", salida)
        self.assertIn("gemini", salida)

    def test_revisar_detecta_problemas(self):
        r = self.correr("revisar.py")
        self.assertEqual(r.returncode, 1)
        self.assertIn("No existe el archivo .env", r.stdout)
        (self.repo / ".env").write_text("TELEGRAM_TOKEN=esto-no-es-un-token\nCORREO_USUARIO=solo@usuario.invalid\n", encoding="utf-8")
        r = self.correr("revisar.py")
        self.assertIn("no tiene la forma correcta", r.stdout)
        self.assertIn("Van las dos", r.stdout)

    def test_config_rota_se_explica(self):
        (self.repo / "config.json").write_text('{\n "moneda": "USD",\n "categorias": [],\n}\n', encoding="utf-8")
        r = self.correr("revisar.py")
        self.assertRegex(r.stdout, r"línea [34]")  # según la versión de Python marca la línea de la coma o la siguiente
        self.assertIn("sobra una coma", r.stdout)

    def test_configurar_todo_sin_editar_archivos(self):
        respuestas = "\n".join([
            TOKEN_FALSO,                 # token
            "HNL", "", "25.5",           # moneda, símbolo (Enter = L), dólar
            "Comida fuera 3,000", "Súper 5000", "Gimnasio 800", "esto no tiene número", "",
            "s",                         # ¿correo? sí
            "persona@gmail.com", CLAVE_FALSA, "s",   # gmail, clave, ¿BAC? sí
            "s", "gemini", LLAVE_FALSA,  # ¿fotos? sí
        ]) + "\n"
        r = self.correr("configurar.py", "--sin-probar", entrada=respuestas)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        for secreto in (TOKEN_FALSO, CLAVE_FALSA, LLAVE_FALSA):
            self.assertNotIn(secreto, r.stdout)
        env = (self.repo / ".env").read_text(encoding="utf-8")
        self.assertIn(f"TELEGRAM_TOKEN={TOKEN_FALSO}", env)
        self.assertIn("CORREO_CLAVE_APP=qwertyuiasdfghjk", env)
        self.assertIn(f"GEMINI_API_KEY={LLAVE_FALSA}", env)
        self.assertIn("VISION_PROVEEDOR=gemini", env)
        self.assertEqual(env.count("TELEGRAM_TOKEN="), 1)
        import json
        cfg = json.loads((self.repo / "config.json").read_text(encoding="utf-8"))
        self.assertEqual((cfg["moneda"], cfg["simbolo"], cfg["tipos_de_cambio"]), ("HNL", "L", {"USD": 25.5}))
        self.assertEqual([c["id"] for c in cfg["categorias"]], ["comida", "super", "gimnasio", "otros"])
        self.assertEqual(cfg["categorias"][0]["tope"], 3000)
        self.assertIn("pizza", cfg["categorias"][0]["palabras"])  # reusó las palabras de ejemplo
        self.assertEqual(cfg["categorias"][2]["palabras"], ["gimnasio"])
        self.assertEqual(cfg["correo"]["bancos"], ["bac"])
        # y el bot lo acepta
        r = self.correr("revisar.py")
        self.assertEqual(r.returncode, 0, r.stdout)
        self.assertIn("moneda HNL (L), 4 categorías", r.stdout)

    def test_configurar_banco_pegado_con_comillas_de_chat(self):
        patron = ('{ “nombre”: “Banco Ejemplo”, “remitentes”: [“banco-ejemplo”], “formatos”: [ { “nombre”: “Compra”, '
                  '“asunto_contiene”: [“compra”], “etiquetas”: { “monto”: “Monto:”, “comercio”: “Comercio:” } } ] }')
        r = self.correr("configurar.py", "banco", entrada=f"{patron}\nFIN\n")
        self.assertEqual(r.returncode, 0, r.stdout)
        self.assertTrue((self.repo / "bancos" / "mi_banco_ejemplo.json").exists())
        r = self.correr("probar_correo.py", "ejemplos/banco-ejemplo.eml")
        self.assertEqual(r.returncode, 0, r.stdout)
        self.assertIn("FARMACIA SAN ROQUE", r.stdout)
        r = self.correr("configurar.py", "banco", entrada='{"nombre": "Roto", "formatos": []}\nFIN\n')
        self.assertEqual(r.returncode, 1)
        self.assertIn("Pegale este error a la IA", r.stdout)

    def test_configurar_token_malo(self):
        r = self.correr("configurar.py", "telegram", "--sin-probar", entrada="hola\n")
        self.assertEqual(r.returncode, 1)
        self.assertIn("no parece un token", r.stdout)

    def test_bot_sin_token_explica(self):
        r = self.correr("bot.py")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("Falta TELEGRAM_TOKEN", r.stderr + r.stdout)
        self.assertTrue((self.repo / ".env").exists())  # lo creó a partir de .env.example

    def test_simulacion_de_punta_a_punta(self):
        guion = "45 pizza\n/eml ejemplos/bac-compra.eml\n/eml ejemplos/bac-movimiento.eml\nb2\n/hoy\n/deshacer\nsalir\n"
        r = self.correr("bot.py", "--simular", "--datos", str(Path(self.tmp.name) / "sim"), entrada=guion)
        self.assertEqual(r.returncode, 0, r.stderr)
        out = r.stdout
        self.assertIn("$45 · Comida fuera · pizza", out)
        self.assertIn("$12.50 · Comida fuera · PIZZERIA LA FAMOSA · 📧", out)
        self.assertIn("no dice en qué", out)
        self.assertIn("Súper y casa · movimiento en tu cuenta", out)
        self.assertIn("Total: $1,558", out)  # ≥ 1,000 se muestra sin centavos
        self.assertIn("Borré: $1,500", out)


if __name__ == "__main__":
    unittest.main()
