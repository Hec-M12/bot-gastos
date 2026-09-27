import unittest

from ayuda import config_prueba

from gastos.config import a_moneda_local, codigo_moneda, dinero, formato_numero
from gastos.texto import a_numero, adivinar_categoria, buscar_monto, clave_comercio, interpretar_gasto


class Numeros(unittest.TestCase):
    def test_formatos(self):
        casos = {"45": 45, "45.5": 45.5, "45,50": 45.5, "1,500": 1500, "1.500": 1500, "1,500.75": 1500.75,
                 "1.500,75": 1500.75, "12,345,678.90": 12345678.90, "0.99": 0.99}
        for crudo, esperado in casos.items():
            self.assertAlmostEqual(a_numero(crudo), esperado, msg=crudo)

    def test_sin_numero(self):
        with self.assertRaises(ValueError):
            a_numero("abc")

    def test_buscar_monto_con_moneda(self):
        cfg = config_prueba()
        self.assertEqual(buscar_monto("USD 12.50", cfg), (12.5, "USD"))
        self.assertEqual(buscar_monto("$ 45.90", cfg), (45.9, "USD"))
        self.assertEqual(buscar_monto("L 1,500.00", cfg), (1500.0, "HNL"))
        self.assertEqual(buscar_monto("99.10 GTQ", cfg), (99.1, "GTQ"))
        self.assertIsNone(buscar_monto("sin plata", cfg))


class Monedas(unittest.TestCase):
    def test_alias(self):
        cfg = config_prueba()
        self.assertEqual(codigo_moneda("LPS", cfg), "HNL")
        self.assertEqual(codigo_moneda("L", cfg), "HNL")
        self.assertEqual(codigo_moneda("$", cfg), "USD")
        self.assertEqual(codigo_moneda("₡", cfg), "CRC")
        self.assertIsNone(codigo_moneda("luz", cfg))
        self.assertEqual(codigo_moneda("JPY", cfg, estricto=False), "JPY")

    def test_dolar_es_local_si_tu_simbolo_es_dolar(self):
        cfg = config_prueba(moneda="MXN", simbolo="$", tipos_de_cambio={})
        self.assertEqual(codigo_moneda("$", cfg), "MXN")

    def test_conversion(self):
        cfg = config_prueba()
        self.assertEqual(a_moneda_local(10, "USD", cfg), (250.0, None))
        self.assertEqual(a_moneda_local(10, "HNL", cfg), (10.0, None))
        monto, aviso = a_moneda_local(10, "EUR", cfg)
        self.assertEqual(monto, 10.0)
        self.assertIn("EUR", aviso)

    def test_formato(self):
        cfg = config_prueba()
        self.assertEqual(dinero(1500, cfg), "L1,500")
        self.assertEqual(dinero(12.5, cfg), "L12.50")
        self.assertEqual(dinero(-3, cfg), "-L3")
        coma = config_prueba(separador_decimal=",")
        self.assertEqual(formato_numero(1234.5, coma, decimales=True), "1.234,50")


class TextoLibre(unittest.TestCase):
    def setUp(self):
        self.cfg = config_prueba()

    def test_monto_y_descripcion(self):
        r = interpretar_gasto("45 pizza", self.cfg)
        self.assertTrue(r["ok"])
        self.assertEqual(r["gasto"]["monto"], 45)
        self.assertEqual(r["gasto"]["desc"], "pizza")
        self.assertEqual(r["gasto"]["cat"], "comida")

    def test_moneda_extranjera_se_convierte(self):
        r = interpretar_gasto("$20 uber", self.cfg)
        self.assertEqual(r["gasto"]["monto"], 500)
        self.assertEqual(r["gasto"]["original"], {"monto": 20, "moneda": "USD"})
        self.assertEqual(r["gasto"]["cat"], "transporte")
        r = interpretar_gasto("20 usd uber", self.cfg)
        self.assertEqual(r["gasto"]["monto"], 500)
        self.assertEqual(r["gasto"]["desc"], "uber")

    def test_moneda_local_con_simbolo(self):
        r = interpretar_gasto("L1,500 gasolina", self.cfg)
        self.assertEqual(r["gasto"]["monto"], 1500)
        self.assertNotIn("original", r["gasto"])

    def test_palabra_que_parece_moneda_no_lo_es(self):
        r = interpretar_gasto("45 luz", self.cfg)
        self.assertEqual(r["gasto"]["desc"], "luz")
        self.assertEqual(r["gasto"]["monto"], 45)

    def test_etiqueta_fuerza_categoria(self):
        r = interpretar_gasto("120 regalo #super", self.cfg)
        self.assertEqual(r["gasto"]["cat"], "super")
        self.assertEqual(r["gasto"]["desc"], "regalo")

    def test_etiqueta_desconocida(self):
        r = interpretar_gasto("120 regalo #casa", self.cfg)
        self.assertFalse(r["ok"])
        self.assertEqual(r["error"], "categoria_desconocida")

    def test_sin_monto_o_cero(self):
        self.assertFalse(interpretar_gasto("hola", self.cfg)["ok"])
        self.assertEqual(interpretar_gasto("0 nada", self.cfg)["error"], "monto_cero")
        self.assertFalse(interpretar_gasto("#comida 45", self.cfg)["ok"])

    def test_sin_nota(self):
        self.assertEqual(interpretar_gasto("45", self.cfg)["gasto"]["desc"], "sin nota")


class Categorias(unittest.TestCase):
    def setUp(self):
        self.cfg = config_prueba()

    def test_por_palabra_sin_tildes_ni_mayusculas(self):
        self.assertEqual(adivinar_categoria("CAFÉ DEL PARQUE", self.cfg), "comida")
        self.assertEqual(adivinar_categoria("Súper La Esquina", self.cfg), "super")

    def test_orden_importa(self):
        self.assertEqual(adivinar_categoria("UBER EATS pedido", self.cfg), "comida")
        self.assertEqual(adivinar_categoria("UBER *TRIP 4411", self.cfg), "transporte")

    def test_inicio_de_palabra(self):
        self.assertEqual(adivinar_categoria("supermercado", self.cfg), "super")
        self.assertEqual(adivinar_categoria("hipersuper", self.cfg), "otros")

    def test_por_defecto(self):
        self.assertEqual(adivinar_categoria("COMERCIO RARO", self.cfg), "otros")

    def test_aprendido_gana(self):
        aprendido = {clave_comercio("TIENDA RARA 123"): "super"}
        self.assertEqual(adivinar_categoria("TIENDA RARA 999", self.cfg, aprendido), "super")


if __name__ == "__main__":
    unittest.main()
