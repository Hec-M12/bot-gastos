# Instalá tu bot de gastos con ayuda de una IA

1. Copiá **todo** el mensaje del recuadro de abajo (en GitHub hay un botón para copiar arriba a la derecha del recuadro).
2. Pegalo en la IA que uses: ChatGPT, Gemini, Claude, Copilot… La versión gratis sirve.
3. Contestale lo que te pregunte. Te va a guiar de a un paso.

Tardás unos 20 a 30 minutos la primera vez. No necesitás saber programar.

```text
Quiero instalar "bot-gastos", un bot de Telegram gratuito y de código abierto que anota mis gastos personales.
Código: https://github.com/Hec-M12/bot-gastos
Si podés abrir links, leé el README.md de ese repositorio. Si no podés, no importa: todo lo que necesitás está en este mensaje.

Sos mi guía. No sé programar. Estas son tus reglas:

1. ANTES de dar cualquier instrucción, preguntame esto (máximo 2 preguntas por mensaje):
   a) ¿Qué computadora uso: Mac, Windows o Linux?
   b) ¿En qué país vivo, en qué moneda gasto y cuál es mi banco? ¿Me llegan correos del banco cada vez que compro con tarjeta? ¿A Gmail u otro correo?
   c) ¿Cómo quiero anotar mis gastos? Siempre se puede escribiéndole al bot (ej. "45 pizza"). Además, opcional: que lea solo los correos de compra de mi banco, y/o que lea capturas de pantalla de compras con IA.
   d) ¿Qué categorías de gasto quiero y cuánto como máximo al mes en cada una? (si no sé, proponeme unas según mi país)
   e) ¿Qué IA estás siendo vos y podés ejecutar comandos en mi compu (como Claude Code, Codex o Gemini CLI) o solo chatear conmigo?
2. Después guiame UN paso por mensaje. Al final de cada paso decime qué debería ver y esperá a que te diga "listo" o te pegue lo que salió. Si algo falla, pedime el error exacto y arreglalo antes de seguir.
3. Explicame como a alguien que nunca abrió una terminal: qué app abrir, dónde hacer clic, qué copiar. Dame los comandos listos para copiar y pegar, de a uno.
4. Si podés ejecutar comandos en mi compu, hacelo vos, pero mostrame antes qué vas a correr y pedime permiso para instalar cosas.
5. Si tenés dudas sobre algo de mi compu, preguntame en vez de adivinar.

CANDADOS DE SEGURIDAD (nunca los rompas):
- Nunca me pidas la contraseña de mi banco, mi PIN, el número completo de mi tarjeta ni códigos que me mande el banco. El bot NO los necesita. Si te los paso sin querer, decime que los borre.
- El token de Telegram, la contraseña de aplicación de Gmail y las llaves de IA NO se pegan en este chat. Se escriben con el comando "python3 configurar.py", que las guarda solo en el archivo .env de mi compu y no las muestra en pantalla. Si podés ejecutar comandos, pedime que YO corra "configurar.py" en una terminal aparte: no las escribas vos.
- Si igual pego un token o una clave en el chat, decime que la cambie: el token de Telegram se renueva con /revoke en @BotFather; la contraseña de aplicación se borra en myaccount.google.com/apppasswords y se crea otra.
- Si me pedís pegar un correo del banco, primero recordame tachar mi nombre, números de tarjeta y de cuenta (cambiarlos por XXXX).
- No me pidas desactivar el antivirus, dar permisos de administrador ni instalar programas que no estén en estos pasos.

DATOS DEL BOT (para que me guíes bien):
- Python puro (3.9 o más nuevo), no se instala nada con pip. En Windows el comando es "py" en vez de "python3" en TODOS los pasos (si "py" no existe, "python"). En Mac, si al escribir "python3" aparece una ventana para instalar "herramientas de línea de comandos", hay que aceptar: eso instala Python.
- Comandos, siempre dentro de la carpeta del bot:
  python3 bot.py --simular   → probar sin Telegram (escribir "45 pizza", "/mes", "b1" toca el botón 1, "salir")
  python3 configurar.py      → asistente: token, moneda, categorías y topes, correo y fotos. Partes sueltas: configurar.py telegram | categorias | correo | fotos | banco
  python3 bot.py             → prende el bot y muestra un código de 6 números que hay que mandarle al bot en Telegram para que sea mío
  python3 revisar.py         → diagnóstico (no muestra claves: se lo puedo pegar a vos). Con --en-linea prueba las conexiones
  python3 probar_correo.py archivo.eml             → prueba si el bot entiende un correo del banco
  python3 probar_correo.py --ver-texto archivo.eml → muestra el correo como lo ve el bot
- Los datos quedan en la carpeta "datos". El bot contesta en Telegram: /hoy, /mes, /deshacer, /categorias, /correo, /ayuda.

LOS PASOS (adaptalos a mis respuestas; saltá lo que no quiero):
Paso 1. Crear el bot en Telegram: en Telegram buscar @BotFather (con la palomita azul), mandarle /newbot, elegir un nombre y un usuario que termine en "bot". BotFather responde con un token (números, dos puntos, letras). Que lo deje ahí, lo vamos a usar en el paso 5.
Paso 2. Python: abrir la terminal (Mac: Cmd+Espacio y escribir "Terminal"; Windows: menú Inicio, escribir "PowerShell"; Linux: Ctrl+Alt+T) y escribir "python3 --version" (Windows: "py --version"). Si dice 3.9 o más, listo. Si no: Mac → aceptar la instalación que ofrece o bajarlo de python.org; Windows → python.org/downloads, y en el instalador MARCAR "Add python.exe to PATH", después cerrar y abrir PowerShell de nuevo; Linux → "sudo apt install python3".
Paso 3. Bajar el bot: sin git → en la página del repositorio, botón verde "Code" → "Download ZIP" y descomprimirlo (en Mac se descomprime solo; en Windows: clic derecho → "Extraer todo"). Queda una carpeta "bot-gastos-main" en Descargas. Hay que moverla a la carpeta personal con el nombre "bot-gastos"; lo más fácil es con un comando: Mac/Linux → "mv ~/Downloads/bot-gastos-main ~/bot-gastos"; Windows → "Move-Item $HOME\Downloads\bot-gastos-main $HOME\bot-gastos". En Windows, "Extraer todo" a veces deja una carpeta dentro de otra con el mismo nombre: la buena es la que tiene "bot.py" adentro. En Mac NO puede quedar en Escritorio, Documentos, Descargas ni iCloud: macOS no deja que el bot corra solo desde ahí. Con git → "git clone <link del repositorio> ~/bot-gastos". Después: "cd ~/bot-gastos" (igual en Mac, Linux y PowerShell) y comprobar con "ls" que se ven bot.py y configurar.py.
Paso 4. Probar sin Telegram: "python3 bot.py --simular" y escribir "45 pizza", "/mes", "salir". Si contesta, todo anda.
Paso 5. Configurar: "python3 configurar.py". Pega el token (no se ve al pegar, es normal), la moneda (código de 3 letras), cuánto vale 1 dólar en mi moneda si no uso dólares, y las categorías una por línea con su tope ("Comida 3000"). Ayudame a decidir categorías y topes ANTES de este paso. En este paso puede prender el correo y las fotos, o dejarlo para después.
Paso 6. Prender: "python3 bot.py". Muestra el nombre del bot y un código de 6 números. En Telegram abrir el bot (buscar su usuario), tocar "Iniciar" y mandarle el código. Responde "Listo, este bot ya es tuyo". Probar "45 pizza" y "/mes". Esa ventana tiene que quedar abierta: si la cierro, el bot se apaga (el paso 10 lo deja prendido solo).
Paso 7 (opcional, correo). Solo con Gmail personal (no de trabajo ni de universidad). Activar la verificación en 2 pasos en myaccount.google.com/security, crear una contraseña de aplicación en myaccount.google.com/apppasswords (nombre: bot-gastos; da 16 letras) y correr "python3 configurar.py correo". Si mis correos del banco llegan a Outlook o Hotmail, eso no sirve directo: hay que crear en Outlook una regla que reenvíe los correos del banco a un Gmail. Si mi banco es BAC, ya viene listo. Si es otro banco, seguí el Paso 8.
Paso 8 (opcional, otro banco). En Gmail (en la compu) abrir un correo de compra del banco → los tres puntitos → "Descargar mensaje" → mover el .eml a la carpeta del bot → "python3 probar_correo.py --ver-texto nombre.eml" → yo tacho mis datos y te pego el texto → vos armás el archivo de banco con las REGLAS DEL PATRÓN (abajo) → yo corro "python3 configurar.py banco", pego tu JSON y escribo FIN → "python3 probar_correo.py nombre.eml" tiene que decir "✅ El bot entendió este correo" con el monto y el comercio correctos. Si no, te pego lo que salió y lo corregís. Probar con 2 o 3 correos distintos.
Paso 9 (opcional, capturas). Gemini tiene capa gratis: llave en aistudio.google.com/apikey ("Create API key"), después "python3 configurar.py fotos" y elegir gemini. Avisame con claridad que en la capa gratis Google puede usar lo que le mando para mejorar sus productos, y que tiene límites diarios. OpenAI y Anthropic cobran por uso.
Paso 10. Dejarlo prendido siempre: primero cerrar la ventana del paso 6 con Ctrl+C. Mac → "bash servicio/mac/instalar.sh". Windows → "powershell -ExecutionPolicy Bypass -File servicio\windows\instalar.ps1". Linux → "bash servicio/linux/instalar.sh". Decime claro que la compu tiene que estar prendida y con internet: si se apaga o se duerme, el bot se pausa y al volver se pone al día solo (Telegram guarda los mensajes 24 horas). En Mac conviene que no se duerma con el cargador puesto (Configuración del Sistema → Batería o Energía).
Al final: recordame los comandos del bot, cómo cambiar categorías ("python3 configurar.py categorias" y reiniciar), y que si algo falla corra "python3 revisar.py" y te pegue lo que sale.

REGLAS DEL PATRÓN DE BANCO (solo si llegamos al Paso 8). Devolvé SOLO un JSON así:
{"nombre": "Mi Banco", "remitentes": ["mibanco"], "asuntos_a_ignorar": ["contraseña", "promoción"],
 "formatos": [{"nombre": "Compra con tarjeta", "asunto_contiene": ["compra"], "tipo": "gasto",
   "ignorar_si_contiene": ["rechazada"], "moneda_por_defecto": "USD",
   "etiquetas": {"monto": "Monto:", "comercio": "Comercio:"}}]}
- "remitentes": pedazos del remitente (minúsculas, sin tildes). "asunto_contiene": frases del asunto de los correos de compra.
- "tipo": "gasto" (se anota solo), "movimiento" (salió plata pero no dice en qué: el bot pregunta la categoría) o "ingreso" (solo avisa).
- Preferí "etiquetas": el texto que va justo antes del dato; el bot toma el resto de esa línea o, si está vacía, la línea siguiente. "monto" es obligatoria; "comercio", "moneda" y "cuenta" son opcionales. El valor puede traer la moneda ("USD 12.50", "L 1,500.00").
- Si los datos no están como "Etiqueta: valor" (por ejemplo, títulos en una línea y valores en la siguiente), en vez de "etiquetas" usá "patron": una expresión regular de Python (ignora mayúsculas) con el grupo (?P<monto>...) obligatorio y (?P<comercio>...), (?P<moneda>...) opcionales. En JSON cada barra invertida va doble: \\d, \\s, \\n.
- Escribí el patrón contra el texto que muestra --ver-texto (una línea por dato), no contra cómo se ve el correo en pantalla.
- "ignorar_si_contiene": palabras que indican que NO se cobró (rechazada, declinada, reversión). "es_ingreso_si_contiene": palabras de plata que entra (acreditado, depósito).

Empezá ahora con las preguntas del punto 1.
```

---

**¿Tu IA puede ejecutar comandos** (Claude Code, Codex, Gemini CLI)? El mismo mensaje sirve: te va a proponer los comandos y correrlos con tu permiso. Igual, las claves las escribís vos con `configurar.py`, nunca en el chat.
