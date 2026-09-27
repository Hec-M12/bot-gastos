import email
import tempfile
import unittest
from pathlib import Path

from ayuda import (RAIZ, BuzonFalso, banco_bac, banco_inventado_etiquetas, banco_inventado_patron, config_prueba,
                   correo_crudo, html_bac)

from gastos.config import ErrorDeConfig
from gastos.correo import (cargar_bancos, interpretar_correo, leer_eml, revisar_buzon, texto_del_correo,
                           valor_de_etiqueta, validar_banco)

BAC = "BAC Credomatic <alertas@ejemplo.invalid>"


def texto(crudo: bytes) -> str:
    return texto_del_correo(email.message_from_bytes(crudo))


class ParserBAC(unittest.TestCase):
    def setUp(self):
        self.cfg = config_prueba()
        self.bancos = [banco_bac()]

    def interpretar(self, asunto, cuerpo, html=True, remitente=BAC):
        return interpretar_correo(remitente, asunto, texto(correo_crudo(remitente, asunto, cuerpo, html)), self.bancos, self.cfg)

    def test_compra_en_dolares(self):
        r = self.interpretar("BAC Credomatic Informa", html_bac("CAFETERIA LAS NUBES", "USD 8.75"))
        self.assertEqual(r["tipo"], "gasto")
        self.assertEqual((r["monto"], r["moneda"], r["comercio"]), (8.75, "USD", "CAFETERIA LAS NUBES"))
        self.assertEqual(r["cuenta"], "1111")

    def test_compra_en_lempiras_con_miles(self):
        r = self.interpretar("BAC Credomatic Informa", html_bac("FERRETERIA EL MARTILLO", "LPS 2,340.00"))
        self.assertEqual((r["monto"], r["moneda"]), (2340.0, "HNL"))

    def test_rechazada_se_ignora(self):
        r = self.interpretar("BAC Credomatic Informa", html_bac("TIENDA X", "USD 50.00", "Rechazada"))
        self.assertEqual(r["tipo"], "ignorar")

    def test_movimiento_debito(self):
        r = self.interpretar("Notificación Movimiento Monetario",
                             "Se realizó un débito a su cuenta número ****2222 por un monto de 850.00 LPS.", html=False)
        self.assertEqual(r["tipo"], "movimiento")
        self.assertEqual((r["monto"], r["moneda"]), (850.0, "HNL"))

    def test_movimiento_credito_es_ingreso(self):
        r = self.interpretar("Notificación Movimiento Monetario",
                             "Monto recibido: se acreditó a su cuenta ****2222 por un monto de 3,000.00 LPS.", html=False)
        self.assertEqual(r["tipo"], "ingreso")

    def test_ruido_del_banco(self):
        r = self.interpretar("Tu código de seguridad", "Tu código es 000000", html=False)
        self.assertEqual(r["tipo"], "ignorar")
        r = self.interpretar("¡Nueva promoción con tu tarjeta!", "Aprovechá", html=False)
        self.assertEqual(r["tipo"], "ignorar")

    def test_asunto_correcto_pero_formato_cambio(self):
        r = self.interpretar("BAC Credomatic Informa", "<p>Un formato nuevo que no conocemos: total 10</p>")
        self.assertEqual(r["tipo"], "no_entendido")

    def test_otro_remitente_no_es_del_banco(self):
        self.assertIsNone(self.interpretar("BAC Credomatic Informa", html_bac("X", "USD 1.00"), remitente="tienda@ejemplo.invalid"))

    def test_ejemplos_del_repo(self):
        rem, asunto, txt, fecha = leer_eml(RAIZ / "ejemplos" / "bac-compra.eml")
        r = interpretar_correo(rem, asunto, txt, self.bancos, self.cfg)
        self.assertEqual((r["tipo"], r["monto"], r["comercio"]), ("gasto", 12.5, "PIZZERIA LA FAMOSA"))
        self.assertEqual(fecha.year, 2026)
        rem, asunto, txt, _ = leer_eml(RAIZ / "ejemplos" / "bac-rechazada.eml")
        self.assertEqual(interpretar_correo(rem, asunto, txt, self.bancos, self.cfg)["tipo"], "ignorar")
        rem, asunto, txt, _ = leer_eml(RAIZ / "ejemplos" / "bac-movimiento.eml")
        self.assertEqual(asunto, "Notificación Movimiento Monetario")
        self.assertEqual(interpretar_correo(rem, asunto, txt, self.bancos, self.cfg)["tipo"], "movimiento")


class ParserConfigurable(unittest.TestCase):
    def setUp(self):
        self.cfg = config_prueba()

    def test_banco_inventado_con_etiquetas(self):
        cuerpo = ("<table><tr><td>Establecimiento:</td><td>LIBRERIA EL SABER</td></tr>"
                  "<tr><td>Valor:</td><td>L 315.40</td></tr></table>")
        rem = "Banco Luna <no-responder@bancoluna.invalid>"
        r = interpretar_correo(rem, "Compra aprobada", texto(correo_crudo(rem, "Compra aprobada", cuerpo, html=True)),
                               [banco_inventado_etiquetas()], self.cfg)
        self.assertEqual((r["tipo"], r["monto"], r["moneda"], r["comercio"]), ("gasto", 315.4, "HNL", "LIBRERIA EL SABER"))

    def test_etiqueta_en_la_misma_linea_y_moneda_por_defecto(self):
        rem = "no-responder@bancoluna.invalid"
        cuerpo = "Establecimiento: PANADERIA TRIGO\nValor: 77.00\n"
        r = interpretar_correo(rem, "Compra aprobada", cuerpo, [banco_inventado_etiquetas()], self.cfg)
        self.assertEqual((r["monto"], r["moneda"], r["comercio"]), (77.0, "HNL", "PANADERIA TRIGO"))

    def test_banco_inventado_con_patron(self):
        rem = "Banco Sol <avisos@bancosol.invalid>"
        r = interpretar_correo(rem, "Aviso", "Hola, pagaste Q 1,250.50 en ZAPATERIA PASO FIRME. Gracias.",
                               [banco_inventado_patron()], self.cfg)
        self.assertEqual((r["monto"], r["moneda"], r["comercio"]), (1250.5, "GTQ", "ZAPATERIA PASO FIRME"))

    def test_varios_bancos_elige_por_remitente(self):
        bancos = [banco_bac(), banco_inventado_patron()]
        r = interpretar_correo("avisos@bancosol.invalid", "x", "pagaste USD 3 en KIOSCO", bancos, self.cfg)
        self.assertEqual(r["banco"], "Banco Sol")

    def test_valor_de_etiqueta(self):
        t = "Comercio:\nTIENDA UNO\nMonto: USD 5.00"
        self.assertEqual(valor_de_etiqueta(t, "Comercio:"), "TIENDA UNO")
        self.assertEqual(valor_de_etiqueta(t, "monto"), "USD 5.00")
        self.assertIsNone(valor_de_etiqueta(t, "Fecha"))

    def test_validacion_explica_errores(self):
        with self.assertRaises(ErrorDeConfig) as c:
            validar_banco({"nombre": "Malo", "formatos": [{"patron": "monto (\\d+"}]}, "malo.json")
        msg = str(c.exception)
        self.assertIn("remitentes", msg)
        self.assertIn("expresión regular", msg)
        with self.assertRaises(ErrorDeConfig) as c:
            validar_banco({"remitentes": ["x"], "formatos": [{"patron": "(\\d+)"}]}, "sin_grupo.json")
        self.assertIn("(?P<monto>", str(c.exception))
        with self.assertRaises(ErrorDeConfig):
            validar_banco({"remitentes": ["x"], "formatos": [{"tipo": "raro", "etiquetas": {"monto": "Monto"}}]})

    def test_cargar_bancos_del_repo_y_plantilla(self):
        bancos = cargar_bancos(["bac", "plantilla"])
        self.assertEqual([b["nombre"] for b in bancos], ["BAC", "Banco Ejemplo"])
        with self.assertRaises(ErrorDeConfig):
            cargar_bancos(["no_existe"])

    def test_html_a_texto(self):
        t = texto(correo_crudo("a@b.invalid", "x", "<style>.a{}</style><p>Hola&nbsp;&amp; chau</p><br><td>Uno</td>", html=True))
        self.assertEqual(t, "Hola & chau\nUno")


class Buzon(unittest.TestCase):
    def setUp(self):
        self.cfg = config_prueba()
        self.bancos = [banco_bac()]
        self.env = {"CORREO_USUARIO": "persona@ejemplo.invalid", "CORREO_CLAVE_APP": "abcd efgh ijkl mnop"}

    def test_sin_credenciales_no_hace_nada(self):
        estado = {}
        self.assertEqual(revisar_buzon(self.cfg, {}, estado, self.bancos, BuzonFalso({})), [])

    def test_primera_vez_se_ancla_sin_leer_historial(self):
        buzon = BuzonFalso({1: correo_crudo(BAC, "BAC Credomatic Informa", html_bac("VIEJO", "USD 1.00"), True)})
        estado = {}
        ev = revisar_buzon(self.cfg, self.env, estado, self.bancos, buzon)
        self.assertEqual(ev, [{"tipo": "anclado"}])
        self.assertEqual(estado["ultimo_uid"], 1)
        self.assertTrue(buzon.readonly)
        self.assertEqual(buzon.clave_usada, "abcdefghijklmnop")  # sin espacios
        self.assertEqual(buzon.fetches, [])

    def test_correos_nuevos(self):
        buzon = BuzonFalso({
            5: correo_crudo(BAC, "BAC Credomatic Informa", html_bac("VIEJO", "USD 1.00"), True),
            6: correo_crudo("amigo@ejemplo.invalid", "hola", "nada que ver"),
            7: correo_crudo(BAC, "BAC Credomatic Informa", html_bac("PIZZERIA NAPOLES", "USD 9.99"), True),
            8: correo_crudo(BAC, "BAC Credomatic Informa", html_bac("X", "USD 3.00", "Rechazada"), True),
            9: correo_crudo(BAC, "BAC Credomatic Informa", "<p>formato raro</p>", True),
        })
        estado = {"ultimo_uid": 5, "anclado": True, "uidvalidity": "7"}
        with tempfile.TemporaryDirectory() as d:
            ev = revisar_buzon(self.cfg, self.env, estado, self.bancos, buzon, Path(d))
            self.assertEqual([e["tipo"] for e in ev], ["gasto", "no_entendido"])
            self.assertEqual(ev[0]["comercio"], "PIZZERIA NAPOLES")
            self.assertTrue(ev[0]["ts"].startswith("2026-09-26"))
            self.assertTrue(Path(ev[1]["archivo"]).exists())
        self.assertEqual(estado["ultimo_uid"], 9)
        # el correo del amigo solo se miró por encabezado, nunca se bajó entero
        self.assertNotIn(("6", "(BODY.PEEK[])"), buzon.fetches)
        # segunda vuelta: nada nuevo (IMAP devuelve el último igual, hay que filtrarlo)
        self.assertEqual(revisar_buzon(self.cfg, self.env, estado, self.bancos, buzon), [])

    def test_clave_mala_avisa_una_sola_vez(self):
        estado = {"ultimo_uid": 1, "anclado": True}
        ev = revisar_buzon(self.cfg, self.env, estado, self.bancos, BuzonFalso({}, login_ok=False))
        self.assertEqual(ev[0]["tipo"], "error")
        self.assertIn("contraseña de aplicación", ev[0]["mensaje"])
        self.assertNotIn("abcd", ev[0]["mensaje"])
        self.assertEqual(revisar_buzon(self.cfg, self.env, estado, self.bancos, BuzonFalso({}, login_ok=False)), [])

    def test_uidvalidity_cambia_se_reancla(self):
        buzon = BuzonFalso({3: correo_crudo(BAC, "x", "y")}, uidvalidity="99")
        estado = {"ultimo_uid": 50, "anclado": True, "uidvalidity": "7"}
        self.assertEqual(revisar_buzon(self.cfg, self.env, estado, self.bancos, buzon), [{"tipo": "anclado"}])
        self.assertEqual(estado["ultimo_uid"], 3)


if __name__ == "__main__":
    unittest.main()
