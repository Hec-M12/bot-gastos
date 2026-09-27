"""Visión con proveedores de mentira: se revisa el pedido que se armaría y cómo se lee la respuesta."""
from __future__ import annotations

import io
import json
import tempfile
import unittest
import urllib.error
from pathlib import Path

from gastos import vision


class RespuestaFalsa(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class HttpFalso:
    def __init__(self, respuesta: dict | None = None, error: int | None = None):
        self.respuesta, self.error = respuesta, error
        self.pedidos = []

    def __call__(self, req, timeout=None):
        self.pedidos.append(req)
        if self.error:
            raise urllib.error.HTTPError(req.full_url, self.error, "error", {}, io.BytesIO(b"{}"))
        return RespuestaFalsa(json.dumps(self.respuesta).encode())

    def cuerpo(self):
        return json.loads(self.pedidos[-1].data.decode())

    def header(self, nombre):
        return self.pedidos[-1].get_header(nombre.capitalize())


JSON_OK = '{"monto": 123.45, "moneda": "USD", "comercio": "TIENDA INVENTADA", "es_gasto": true}'


class Proveedores(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.img = Path(self.dir.name) / "captura.png"
        self.img.write_bytes(b"\x89PNG imagen falsa")

    def tearDown(self):
        self.dir.cleanup()

    def test_elegir_proveedor(self):
        self.assertIsNone(vision.proveedor({}))
        self.assertEqual(vision.proveedor({"OPENAI_API_KEY": "k1", "GEMINI_API_KEY": "k2"})[0], "gemini")
        self.assertEqual(vision.proveedor({"OPENAI_API_KEY": "k1", "GEMINI_API_KEY": "k2", "VISION_PROVEEDOR": "OpenAI"})[0], "openai")
        self.assertIsNone(vision.proveedor({"VISION_PROVEEDOR": "anthropic", "GEMINI_API_KEY": "k"}))
        self.assertEqual(vision.proveedor({"GEMINI_API_KEY": "k", "VISION_MODELO": "otro-modelo"})[2], "otro-modelo")

    def test_gemini(self):
        http = HttpFalso({"candidates": [{"content": {"parts": [{"text": JSON_OK}]}}]})
        r = vision.leer_imagen(self.img, {"GEMINI_API_KEY": "llave-g"}, http)
        self.assertEqual(r, {"monto": 123.45, "moneda": "USD", "comercio": "TIENDA INVENTADA", "es_gasto": True})
        req = http.pedidos[0]
        self.assertIn("/models/gemini-3.5-flash-lite:generateContent", req.full_url)
        self.assertNotIn("llave-g", req.full_url)  # la llave va en un header, no en la URL
        self.assertEqual(http.header("x-goog-api-key"), "llave-g")
        parte = http.cuerpo()["contents"][0]["parts"][1]["inline_data"]
        self.assertEqual(parte["mime_type"], "image/png")

    def test_openai(self):
        http = HttpFalso({"choices": [{"message": {"content": JSON_OK}}]})
        r = vision.leer_imagen(self.img, {"OPENAI_API_KEY": "llave-o"}, http)
        self.assertEqual(r["monto"], 123.45)
        c = http.cuerpo()
        self.assertEqual(c["model"], "gpt-6-luna")
        self.assertTrue(c["messages"][0]["content"][1]["image_url"]["url"].startswith("data:image/png;base64,"))
        self.assertEqual(http.header("Authorization"), "Bearer llave-o")

    def test_anthropic(self):
        http = HttpFalso({"content": [{"type": "text", "text": "Acá va:\n" + JSON_OK}]})
        r = vision.leer_imagen(self.img, {"ANTHROPIC_API_KEY": "llave-a"}, http)
        self.assertEqual(r["comercio"], "TIENDA INVENTADA")
        c = http.cuerpo()
        self.assertEqual(c["model"], "claude-haiku-4-5")
        self.assertEqual(c["messages"][0]["content"][0]["source"]["media_type"], "image/png")
        self.assertEqual(http.header("Anthropic-version"), "2023-06-01")

    def test_errores_explicados(self):
        env = {"GEMINI_API_KEY": "k"}
        for codigo, texto in ((429, "cuota"), (403, "llave"), (404, "modelo"), (500, "500")):
            with self.assertRaises(vision.ErrorDeVision) as c:
                vision.leer_imagen(self.img, env, HttpFalso(error=codigo))
            self.assertIn(texto, str(c.exception))
        with self.assertRaises(vision.ErrorDeVision):
            vision.leer_imagen(self.img, {}, HttpFalso({}))

    def test_interpretar_respuestas_raras(self):
        self.assertIsNone(vision.interpretar_respuesta("no sé"))
        self.assertIsNone(vision.interpretar_respuesta('{"monto": null}'))
        self.assertIsNone(vision.interpretar_respuesta('{"monto": 0}'))
        self.assertEqual(vision.interpretar_respuesta('```json\n{"monto": "1,200.50"}\n```')["monto"], 1200.5)
        self.assertFalse(vision.interpretar_respuesta('{"monto": 5, "es_gasto": false}')["es_gasto"])


if __name__ == "__main__":
    unittest.main()
