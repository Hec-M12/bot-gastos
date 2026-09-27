"""El bot completo con la API de Telegram de mentira (sin red)."""
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest import mock

from ayuda import AHORA, BuzonFalso, TransporteFalso, banco_bac, config_prueba, correo_crudo, html_bac

from gastos import vision
from gastos.app import Bot
from gastos.telegram import ErrorDeTelegram, Telegram

YO = 424242
EXTRANO = 999


def msg(texto, chat=YO, uid=1):
    return {"update_id": uid, "message": {"message_id": uid, "chat": {"id": chat}, "text": texto}}


def boton(data, chat=YO, mid=77, uid=1):
    return {"update_id": uid, "callback_query": {"id": f"cb{uid}", "data": data, "message": {"message_id": mid, "chat": {"id": chat}}}}


class Base(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.datos = Path(self.dir.name)
        self.red = TransporteFalso()
        self.tg = Telegram("123456:TOKEN-DE-PRUEBA-NO-ES-REAL-xxxxxxxxxx", transporte=self.red)
        self.cfg = config_prueba()
        self.reloj = mock.Mock(return_value=AHORA)
        self.lector = mock.Mock(return_value=None)
        self.env = {"TELEGRAM_CHAT_ID": str(YO)}

    def tearDown(self):
        self.dir.cleanup()

    def bot(self, env=None, **kw):
        opciones = dict(leer_imagen=self.lector, reloj=self.reloj)
        opciones.update(kw)
        return Bot(self.cfg, self.env if env is None else env, self.tg, self.datos, **opciones)

    def textos(self):
        return [p["text"] for m, p in self.red.llamadas if m in ("sendMessage", "editMessageText")]


class Emparejar(Base):
    def test_sin_dueno_pide_codigo_y_se_empareja(self):
        b = self.bot(env={})
        codigo = b.codigo
        self.assertRegex(codigo, r"^\d{6}$")
        b.procesar(msg("45 pizza", chat=YO))
        self.assertIn("no tiene dueño", self.red.ultimo_texto())
        self.assertEqual(b.libro.gastos, [])
        b.procesar(msg(codigo, chat=YO))
        self.assertEqual(b.chat_id, str(YO))
        self.assertIn("este bot ya es tuyo", self.red.ultimo_texto())
        # quedó guardado: otro arranque ya lo conoce
        b2 = self.bot(env={})
        self.assertEqual(b2.chat_id, str(YO))
        self.assertIsNone(b2.codigo)

    def test_el_codigo_sobrevive_reinicios(self):
        self.assertEqual(self.bot(env={}).codigo, self.bot(env={}).codigo)

    def test_demasiados_intentos_bloquean_ese_chat(self):
        b = self.bot(env={})
        for i in range(6):
            b.procesar(msg("000000" if b.codigo != "000000" else "111111", chat=EXTRANO, uid=i))
        antes = len(self.red.llamadas)
        b.procesar(msg(b.codigo, chat=EXTRANO, uid=99))
        self.assertIsNone(b.chat_id)
        self.assertEqual(len(self.red.llamadas), antes)

    def test_extrano_ignorado_cuando_ya_hay_dueno(self):
        b = self.bot()
        b.procesar(msg("45 pizza", chat=EXTRANO))
        b.procesar(boton("mv:1", chat=EXTRANO))
        self.assertEqual(self.red.llamadas, [])
        self.assertEqual(b.libro.gastos, [])


class Comandos(Base):
    def test_texto_suelto_anota(self):
        b = self.bot()
        b.procesar(msg("45 pizza"))
        envio = self.red.enviados()[-1]
        self.assertEqual(envio["chat_id"], str(YO))
        self.assertEqual(envio["parse_mode"], "HTML")
        self.assertIn("<b>L45</b> · Comida · pizza", envio["text"])
        self.assertEqual(envio["reply_markup"]["inline_keyboard"][0][0]["callback_data"], "mv:1")
        self.assertEqual(len(b.libro.gastos), 1)
        self.assertEqual(b.libro.gastos[0]["ts"], "2026-09-26T10:00:00")

    def test_ayuda_refleja_lo_que_esta_prendido(self):
        b = self.bot()
        b.procesar(msg("/ayuda"))
        t = self.red.ultimo_texto()
        self.assertIn("Fotos: apagado", t)
        self.assertIn("Correo: apagado", t)
        self.env["GEMINI_API_KEY"] = "llave-falsa"
        b = self.bot()
        b.procesar(msg("/start"))
        self.assertIn("Mandame la captura", self.red.ultimo_texto())

    def test_mes_hoy_deshacer_categorias(self):
        b = self.bot()
        b.procesar(msg("100 super"))
        b.procesar(msg("/hoy"))
        self.assertIn("L100 · Súper · super", self.red.ultimo_texto())
        b.procesar(msg("/mes"))
        self.assertIn("Septiembre 2026", self.red.ultimo_texto())
        b.procesar(msg("/deshacer"))
        self.assertIn("Borré: L100", self.red.ultimo_texto())
        b.procesar(msg("/deshacer"))
        self.assertIn("No hay nada que deshacer", self.red.ultimo_texto())
        b.procesar(msg("/categorias"))
        self.assertIn("#transporte", self.red.ultimo_texto())
        b.procesar(msg("/mes@mis_gastos_prueba_bot"))
        self.assertIn("Septiembre", self.red.ultimo_texto())

    def test_comando_desconocido_y_texto_raro(self):
        b = self.bot()
        b.procesar(msg("/inventado"))
        self.assertIn("No conozco ese comando", self.red.ultimo_texto())
        b.procesar(msg("hola bot"))
        self.assertIn("No entendí", self.red.ultimo_texto())
        b.procesar(msg("50 algo #inexistente"))
        self.assertIn("#inexistente", self.red.ultimo_texto())

    def test_cambiar_categoria_y_aprender(self):
        b = self.bot()
        b.procesar(msg("300 COMERCIO NUEVO"))
        self.assertEqual(b.libro.gastos[0]["cat"], "otros")
        b.procesar(boton("mv:1"))
        teclado = self.red.enviados("editMessageText")[-1]["reply_markup"]["inline_keyboard"]
        self.assertEqual(teclado[0][1]["callback_data"], "mvc:1:1")
        b.procesar(boton("mvc:1:1"))  # Súper
        self.assertEqual(b.libro.gastos[0]["cat"], "super")
        self.assertIn("la próxima vez", self.red.ultimo_texto())
        b.procesar(msg("80 comercio nuevo"))
        self.assertEqual(b.libro.gastos[1]["cat"], "super")  # aprendió
        b.procesar(msg("/deshacer"))
        b.procesar(msg("/deshacer"))
        b.procesar(boton("mv:1"))
        self.assertIn("ya no existe", self.red.ultimo_texto())

    def test_un_error_no_tumba_el_bot(self):
        b = self.bot()
        self.red.updates = [[msg("45 pizza", uid=10), msg("/hoy", uid=11)]]
        with mock.patch.object(b, "anotar_texto", side_effect=RuntimeError("boom")):
            b.una_vuelta()
        self.assertIn("Se me rompió algo", self.textos()[0])
        self.assertIn("Hoy", self.textos()[1])
        self.assertEqual(b.estado["offset"], 12)


class Fotos(Base):
    def foto(self, caption=None):
        m = {"update_id": 5, "message": {"message_id": 5, "chat": {"id": YO}, "photo": [{"file_id": "chica"}, {"file_id": "grande"}]}}
        if caption:
            m["message"]["caption"] = caption
        return m

    def preparar(self, lectura):
        self.env["GEMINI_API_KEY"] = "llave-falsa"
        self.lector.return_value = lectura
        b = self.bot()
        img = self.datos / "img.jpg"
        img.write_bytes(b"\xff\xd8 no es una foto real")
        b.tg.bajar_archivo = mock.Mock(return_value=img)
        return b

    def test_sin_llave_explica(self):
        b = self.bot()
        b.procesar(self.foto())
        self.assertIn("necesito una llave de IA", self.red.ultimo_texto())

    def test_foto_propone_y_anota_con_ok(self):
        b = self.preparar({"monto": 12.0, "moneda": "USD", "comercio": "CAFETERIA LUNA", "es_gasto": True})
        b.procesar(self.foto())
        b.tg.bajar_archivo.assert_called_once()
        self.assertEqual(b.tg.bajar_archivo.call_args[0][0], "grande")
        propuesta = self.red.enviados()[-1]
        self.assertIn("Leí: <b>L300</b> · CAFETERIA LUNA", propuesta["text"])
        pid = propuesta["reply_markup"]["inline_keyboard"][0][0]["callback_data"].split(":")[1]
        self.assertEqual(b.libro.gastos, [])  # todavía no
        b.procesar(boton(f"ok:{pid}"))
        self.assertEqual(b.libro.gastos[0]["monto"], 300)
        self.assertEqual(b.libro.gastos[0]["original"], {"monto": 12.0, "moneda": "USD"})
        self.assertEqual(b.libro.gastos[0]["origen"], "foto")
        b.procesar(boton(f"ok:{pid}"))
        self.assertIn("ya se resolvió", self.red.ultimo_texto())

    def test_foto_categoria_con_botones_y_no(self):
        b = self.preparar({"monto": 50.0, "moneda": None, "comercio": "LUGAR X", "es_gasto": True})
        b.procesar(self.foto())
        pid = self.red.enviados()[-1]["reply_markup"]["inline_keyboard"][0][1]["callback_data"].split(":")[1]
        b.procesar(boton(f"cat:{pid}"))
        self.assertIn("¿En qué categoría", self.red.ultimo_texto())
        b.procesar(boton(f"set:{pid}:2"))
        self.assertEqual(b.libro.gastos[0]["cat"], "transporte")
        b.procesar(self.foto())
        pid2 = self.red.enviados()[-1]["reply_markup"]["inline_keyboard"][0][2]["callback_data"].split(":")[1]
        b.procesar(boton(f"no:{pid2}"))
        self.assertEqual(len(b.libro.gastos), 1)
        self.assertIn("no lo anoté", self.red.ultimo_texto())

    def test_caption_manda(self):
        b = self.preparar({"monto": 80.0, "moneda": "HNL", "comercio": "ALGO", "es_gasto": True})
        b.procesar(self.foto("regalo #super"))
        self.assertIn("regalo · Súper", self.red.ultimo_texto())

    def test_ingreso_no_se_anota(self):
        b = self.preparar({"monto": 80.0, "moneda": "HNL", "comercio": "X", "es_gasto": False})
        b.procesar(self.foto())
        self.assertIn("te <b>entró</b>", self.red.ultimo_texto())

    def test_sin_monto_y_error_de_ia(self):
        b = self.preparar(None)
        b.procesar(self.foto())
        self.assertIn("No encontré un monto", self.red.ultimo_texto())
        self.lector.side_effect = vision.ErrorDeVision("Se acabó la cuota")
        b.procesar(self.foto())
        self.assertIn("Se acabó la cuota", self.red.ultimo_texto())

    def test_aviso_de_repetido(self):
        b = self.preparar({"monto": 45.0, "moneda": "HNL", "comercio": "PIZZERIA", "es_gasto": True})
        b.procesar(msg("45 pizza"))
        b.procesar(self.foto())
        self.assertIn("mismo monto hoy", self.red.ultimo_texto())


class Correo(Base):
    def setUp(self):
        super().setUp()
        self.env.update({"CORREO_USUARIO": "persona@ejemplo.invalid", "CORREO_CLAVE_APP": "abcdefghijklmnop"})
        self.bac = "BAC Credomatic <alertas@ejemplo.invalid>"

    def test_de_punta_a_punta(self):
        buzon = BuzonFalso({
            10: correo_crudo(self.bac, "BAC Credomatic Informa", html_bac("PIZZERIA ROMA", "USD 10.00"), True),
            11: correo_crudo(self.bac, "Notificación Movimiento Monetario", "débito por un monto de 400.00 LPS"),
        })
        b = self.bot(bancos=[banco_bac()], conectar_imap=buzon)
        self.assertEqual(b.revisar_correo(), [{"tipo": "anclado"}])
        self.assertIn("Conectado a tu correo", self.red.ultimo_texto())
        buzon.mensajes[12] = correo_crudo(self.bac, "BAC Credomatic Informa", html_bac("PIZZERIA NUEVA", "USD 4.00"), True)
        buzon.mensajes[13] = correo_crudo(self.bac, "Notificación Movimiento Monetario", "débito por un monto de 400.00 LPS")
        self.assertEqual(b.revisar_correo(), [])  # todavía no pasaron los 10 minutos
        eventos = b.revisar_correo(forzar=True)
        self.assertEqual([e["tipo"] for e in eventos], ["gasto", "movimiento"])
        g = b.libro.gastos[0]
        self.assertEqual((g["monto"], g["cat"], g["origen"], g["desc"]), (100.0, "comida", "correo", "PIZZERIA NUEVA"))
        self.assertTrue(g["ts"].startswith("2026-09-26T"))
        pregunta = self.red.enviados()[-1]
        self.assertIn("no dice en qué", pregunta["text"])
        ultima_fila = pregunta["reply_markup"]["inline_keyboard"][-1][0]
        self.assertEqual(ultima_fila["text"], "No es un gasto")
        pid = ultima_fila["callback_data"].split(":")[1]
        b.procesar(boton(f"set:{pid}:1"))
        self.assertEqual(b.libro.gastos[1]["cat"], "super")
        self.assertEqual(b.libro.gastos[1]["monto"], 400.0)
        self.assertEqual(b.libro.datos["aprendido"], {})  # "movimiento en tu cuenta" no se aprende

    def test_estado_correo(self):
        b = self.bot(bancos=[banco_bac()], conectar_imap=BuzonFalso({}, login_ok=False))
        b.procesar(msg("/correo"))
        self.assertIn("No puedo entrar", self.red.ultimo_texto())
        b = self.bot(env={"TELEGRAM_CHAT_ID": str(YO)})
        b.procesar(msg("/correo"))
        self.assertIn("apagado", self.red.ultimo_texto())


class ResumenDiario(Base):
    def test_a_la_hora_y_una_sola_vez(self):
        b = self.bot()
        b.procesar(msg("45 pizza"))
        self.reloj.return_value = datetime(2026, 9, 26, 19, 59)
        self.assertFalse(b.resumen_diario())
        self.reloj.return_value = datetime(2026, 9, 26, 20, 0)
        self.assertTrue(b.resumen_diario())
        enviado = self.red.enviados()[-1]
        self.assertTrue(enviado["disable_notification"])
        self.assertIn("Resumen del día", enviado["text"])
        self.assertIn("Mes hasta hoy", enviado["text"])
        self.assertFalse(b.resumen_diario())
        self.reloj.return_value = datetime(2026, 9, 27, 21, 0)
        self.assertTrue(b.resumen_diario())
        self.assertIn("nada anotado", self.red.enviados()[-1]["text"])

    def test_apagado(self):
        self.cfg = config_prueba(resumen_diario_hora=None)
        b = self.bot()
        self.reloj.return_value = datetime(2026, 9, 26, 23, 0)
        self.assertFalse(b.resumen_diario())


class Vuelta(Base):
    def test_offset_se_guarda(self):
        b = self.bot()
        self.red.updates = [[msg("10 cafe", uid=41), msg("20 cafe", uid=42)]]
        b.una_vuelta()
        self.assertEqual(len(b.libro.gastos), 2)
        self.assertEqual(self.bot().estado["offset"], 43)
        pedido = [p for m, p in self.red.llamadas if m == "getUpdates"][0]
        self.assertEqual(pedido["offset"], 0)
        self.assertEqual(pedido["timeout"], 25)

    def test_otra_copia_corriendo_409(self):
        b = self.bot()
        self.red.respuestas["getUpdates"] = [{"ok": False, "error_code": 409, "description": "Conflict: terminated by other getUpdates"}]
        vueltas = iter([False, True])
        with mock.patch("gastos.app.time.sleep") as dormir, self.assertLogs("bot-gastos", "ERROR") as logs:
            b.correr(parar=lambda: next(vueltas))
        self.assertIn("OTRA copia", logs.output[0])
        dormir.assert_called_with(30)

    def test_telegram_html_roto_reintenta_sin_formato(self):
        self.red.respuestas["sendMessage"] = [{"ok": False, "error_code": 400, "description": "Bad Request: can't parse entities"}]
        b = self.bot()
        b.enviar("<b>roto")
        envios = self.red.enviados()
        self.assertEqual(len(envios), 2)
        self.assertNotIn("parse_mode", envios[1])

    def test_errores_de_red_se_reintentan(self):
        llamadas = {"n": 0}

        def red_inestable(metodo, payload, timeout):
            llamadas["n"] += 1
            if llamadas["n"] < 3:
                raise OSError("red caída")
            return {"ok": True, "result": {"message_id": 1}}
        tg = Telegram("x", transporte=red_inestable)
        with mock.patch("gastos.telegram.time.sleep"):
            tg.enviar(1, "hola")
        self.assertEqual(llamadas["n"], 3)
        tg = Telegram("x", transporte=mock.Mock(side_effect=OSError("nada")))
        with mock.patch("gastos.telegram.time.sleep"), self.assertRaises(ErrorDeTelegram):
            tg.enviar(1, "hola")


if __name__ == "__main__":
    unittest.main()
