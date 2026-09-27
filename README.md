# 💸 bot-gastos

Un bot de Telegram que anota tus gastos y te dice cuánto te queda en cada categoría del mes.

- Le escribís **`45 pizza`** y lo anota en «Comida», con la barrita de cuánto llevás.
- **Opcional:** lee solo los correos de compra de tu banco (BAC viene listo; otros bancos se agregan con ayuda de una IA).
- **Opcional:** le mandás la captura de una compra, la lee con IA y te pregunta antes de anotarla.
- Cada noche te manda un resumen. Comandos: `/hoy`, `/mes`, `/deshacer`, `/categorias`.

Tus datos se quedan en tu compu (en la carpeta `datos/`). Es Python puro: no hay que instalar nada más.

```
✅ $12 · Comida fuera · pizza
Comida fuera este mes: $142 / $150  █████████░ 👀 vas en 95%
Total del mes: $227 / $1,000  ██░░░░░░░░
```

## Instalarlo con ayuda de una IA (recomendado)

Abrí **[INSTALAR-CON-IA.md](INSTALAR-CON-IA.md)**, copiá el mensaje que está ahí y pegalo en la IA que uses (ChatGPT, Gemini, Claude, Copilot; la versión gratis sirve). Te hace unas preguntas y te guía paso a paso, a tu ritmo.

## Instalarlo a mano

> En Windows, donde dice `python3` escribí `py`.

1. **Creá tu bot en Telegram:** buscá **@BotFather**, mandale `/newbot`, poné un nombre y un usuario que termine en `bot`. Te da un **token**: guardalo, no se lo pases a nadie.
2. **Python 3.9 o más nuevo:** en la terminal, `python3 --version`. Si no lo tenés: Mac (te ofrece instalarlo solo al escribir `python3`, o python.org), Windows (python.org, marcá **«Add python.exe to PATH»**), Linux (`sudo apt install python3`).
3. **Bajá esta carpeta:** botón verde **Code → Download ZIP**, descomprimila, renombrala a `bot-gastos` y ponela en tu carpeta personal (en Mac, **no** en Escritorio, Documentos ni Descargas). O con git: `git clone https://github.com/REEMPLAZAR/bot-gastos ~/bot-gastos`.
4. **Probalo sin Telegram:** en la terminal, `cd ~/bot-gastos` y `python3 bot.py --simular`. Escribí `45 pizza`, `/mes`, `salir`.
5. **Configuralo sin tocar archivos:** `python3 configurar.py` (token, moneda, categorías y, si querés, correo y fotos).
6. **Prendelo:** `python3 bot.py`. Te muestra un **código de 6 números**: mandáselo a tu bot en Telegram. Desde ahí el bot solo te hace caso a vos.
7. **Dejalo prendido siempre** (cerrá antes la ventana del paso 6 con Ctrl+C):
   - Mac: `bash servicio/mac/instalar.sh`
   - Windows: `powershell -ExecutionPolicy Bypass -File servicio\windows\instalar.ps1`
   - Linux: `bash servicio/linux/instalar.sh`

Si algo no anda: `python3 revisar.py` (no muestra tus claves, se lo podés pegar a tu IA).

## ¿Es gratis?

| Parte | Costo |
|---|---|
| El bot, Telegram, Python | Gratis |
| Leer el correo del banco (Gmail) | Gratis |
| Leer capturas con **Gemini** | Gratis dentro de los límites diarios de la capa gratis. **Ojo:** en la capa gratis Google puede usar lo que le mandás para mejorar sus productos. |
| Leer capturas con OpenAI o Anthropic | Pagás por uso (centavos por captura) |

**La compu tiene que estar prendida y con internet.** Si se apaga o se duerme, el bot se pausa; al volver se pone al día solo (Telegram guarda tus mensajes 24 horas y los correos no se pierden). Para que funcione 24/7 sin tu compu necesitarías un servidor, y eso no entra en esta guía.

## Tu banco no es BAC

Mirá [bancos/COMO-AGREGAR-TU-BANCO.md](bancos/COMO-AGREGAR-TU-BANCO.md): bajás un correo de compra, tu IA arma el patrón y lo probás con `python3 probar_correo.py tu-correo.eml` antes de usarlo. El correo es opcional: sin él, el bot funciona igual con texto y capturas.

**Outlook / Hotmail:** Microsoft ya no deja que programas como este entren con contraseña. Creá una regla que reenvíe los correos del banco a un Gmail.

## Privacidad y seguridad

- El bot **nunca** necesita la contraseña de tu banco, tu PIN ni el número de tu tarjeta. Si alguien (o una IA) te los pide, no los des.
- El token, la contraseña de aplicación de Gmail y las llaves de IA viven solo en el archivo `.env` de tu compu. No se suben a internet (`.gitignore`) ni se pegan en chats.
- El bot entra a tu correo en **solo lectura**: no borra ni marca nada, y la primera vez no lee tu historial.
- Tus gastos quedan en `datos/gastos.json`. Para respaldarlos, copiá esa carpeta.

## Problemas comunes

- **«Hay OTRA copia del bot prendida»**: lo tenés corriendo dos veces (una ventana y el servicio). Dejá una.
- **El bot no contesta:** ¿está prendida la compu? Corré `python3 revisar.py --en-linea`.
- **Una compra cayó en la categoría equivocada:** tocá **✏️ Cambiar categoría** en el mensaje. El bot aprende y la próxima vez lo pone ahí solo.
- **Quiero cambiar categorías o topes:** `python3 configurar.py categorias` (y reiniciá el bot).
- **Llegó un correo del banco que no supo leer:** te avisa por Telegram y lo guarda en `datos/correos-sin-entender/`. Usá ese texto para ajustar el patrón.

## Para curiosos

- `bot.py` arranca el bot · `configurar.py` asistente · `probar_correo.py` prueba patrones · `revisar.py` diagnóstico.
- `gastos/` es el código (solo biblioteca estándar de Python). Tests: `python3 -m unittest discover -s tests`.
- Licencia MIT.
