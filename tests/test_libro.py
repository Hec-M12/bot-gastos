import tempfile
import unittest
from datetime import date, datetime
from pathlib import Path

from ayuda import config_prueba

from gastos.libro import Libro, barra, mensaje_registro, resumen_hoy, resumen_mes


class Barras(unittest.TestCase):
    def test_barra(self):
        self.assertEqual(barra(0, 100), "░" * 10)
        self.assertEqual(barra(50, 100), "█" * 5 + "░" * 5)
        self.assertEqual(barra(250, 100), "█" * 10)  # nunca más de 10
        self.assertEqual(barra(10, 0), "·" * 10)  # sin tope


class LibroTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.ruta = Path(self.dir.name) / "gastos.json"
        self.cfg = config_prueba()
        self.libro = Libro(self.ruta)

    def tearDown(self):
        self.dir.cleanup()

    def anotar(self, monto, cat, desc="algo", ts="2026-09-26T09:00:00"):
        return self.libro.agregar({"monto": monto, "cat": cat, "desc": desc, "ts": ts})

    def test_guarda_y_recarga(self):
        self.anotar(100, "comida")
        self.libro.guardar()
        otro = Libro(self.ruta)
        self.assertEqual(len(otro.gastos), 1)
        self.assertEqual(otro.gastos[0]["id"], 1)

    def test_archivo_danado_no_rompe(self):
        self.ruta.write_text("{esto no es json", encoding="utf-8")
        libro = Libro(self.ruta)
        self.assertEqual(libro.gastos, [])
        self.assertTrue(any(p.name.startswith("gastos.roto-") for p in Path(self.dir.name).iterdir()))

    def test_deshacer(self):
        self.anotar(1, "comida")
        self.anotar(2, "super")
        self.assertEqual(self.libro.deshacer()["monto"], 2)
        self.assertEqual(len(self.libro.gastos), 1)
        self.libro.deshacer()
        self.assertIsNone(self.libro.deshacer())

    def test_mensaje_registro_con_tope(self):
        self.anotar(2000, "comida", ts="2026-09-02T09:00:00")
        g = self.anotar(700, "comida", "pizza")
        m = mensaje_registro(self.libro, self.cfg, g)
        self.assertIn("L700", m)
        self.assertIn("Comida este mes: L2,700 / L3,000", m)
        self.assertIn("vas en 90%", m)
        self.assertIn("Total del mes: L2,700 / L11,000", m)

    def test_mensaje_registro_pasado_del_tope(self):
        g = self.anotar(3500, "comida")
        self.assertIn("te pasaste por L500", mensaje_registro(self.libro, self.cfg, g))

    def test_mes_anterior_no_cuenta(self):
        self.anotar(999, "comida", ts="2026-08-31T23:00:00")
        g = self.anotar(10, "comida")
        self.assertIn("Comida este mes: L10 /", mensaje_registro(self.libro, self.cfg, g))

    def test_resumen_mes(self):
        self.anotar(1500, "comida")
        self.anotar(6000, "super")
        r = resumen_mes(self.libro, self.cfg, date(2026, 9, 26))
        self.assertIn("Septiembre 2026 · día 26", r)
        self.assertIn("Total: <b>L7,500</b> de L11,000", r)
        self.assertIn("█████░░░░░ Comida L1,500/L3,000", r)
        self.assertIn("Súper L6,000/L5,000 ⚠️", r)
        self.assertIn("Te quedan L3,500 para 5 días ≈ L700 por día.", r)

    def test_resumen_mes_pasado_del_total(self):
        self.anotar(20000, "otros")
        self.assertIn("Te pasaste del total por L9,000", resumen_mes(self.libro, self.cfg, date(2026, 9, 26)))

    def test_resumen_hoy(self):
        self.assertIn("nada anotado", resumen_hoy(self.libro, self.cfg, date(2026, 9, 26)))
        self.anotar(45, "comida", "café <con> leche")
        self.anotar(55, "super", "pan", ts="2026-09-25T10:00:00")
        r = resumen_hoy(self.libro, self.cfg, date(2026, 9, 26))
        self.assertIn("café &lt;con&gt; leche", r)  # escapa HTML
        self.assertNotIn("pan", r)
        self.assertIn("Total: <b>L45</b>", r)

    def test_pendientes_se_recortan(self):
        for i in range(60):
            self.libro.guardar_pendiente("gasto", {"i": i})
        self.assertEqual(len(self.libro.datos["pendientes"]), 50)

    def test_agregar_usa_hora_dada(self):
        g = self.libro.agregar({"monto": 1, "cat": "otros", "desc": "x"}, datetime(2026, 1, 2, 3, 4, 5))
        self.assertEqual(g["ts"], "2026-01-02T03:04:05")


if __name__ == "__main__":
    unittest.main()
