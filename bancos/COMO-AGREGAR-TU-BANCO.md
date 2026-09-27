# Cómo agregar tu banco

El bot lee los correos que te manda tu banco cuando comprás con tarjeta. Cada banco escribe esos correos distinto, así que hay que decirle al bot **dónde está el monto**. Se hace una sola vez.

BAC Credomatic ya viene listo (`bac.json`). Para cualquier otro banco:

## 1. Bajá un correo de compra

En Gmail (en la compu): abrí un correo de compra de tu banco → los tres puntitos **⋮** arriba a la derecha → **Descargar mensaje**. Te baja un archivo `.eml`. Movelo a la carpeta del bot.

## 2. Mirá el texto como lo ve el bot

```
python3 probar_correo.py --ver-texto nombre-del-correo.eml
```

(En Windows: `py` en vez de `python3`.)

## 3. Pedile a tu IA que arme el patrón

**Antes de pegar**, tachá tu nombre, los números de tarjeta o cuenta y cualquier cosa que no quieras compartir (cambialos por XXXX). Los montos y el nombre del comercio pueden quedar.

Pegale a la IA el texto de arriba junto con esto:

> Armame el archivo de banco para bot-gastos según las reglas de COMO-AGREGAR-TU-BANCO.md. Devolveme SOLO el JSON completo.

## 4. Guardalo sin editar archivos

```
python3 configurar.py banco
```

Pegás el JSON, escribís `FIN`, y queda guardado en `bancos/mi_<banco>.json` y activado en `config.json`.

## 5. Probalo

```
python3 probar_correo.py nombre-del-correo.eml
```

Tiene que decir **✅ El bot entendió este correo** con el monto y el comercio correctos. Si no, pegale a la IA lo que salió y que lo corrija. Probalo con 2 o 3 correos distintos (una compra en dólares y otra en tu moneda, si tenés).

---

## Reglas del archivo de banco (para la IA)

Un archivo JSON con esta forma:

```json
{
  "nombre": "Mi Banco",
  "remitentes": ["mibanco"],
  "asuntos_a_ignorar": ["contraseña", "promoción", "estado de cuenta"],
  "formatos": [
    {
      "nombre": "Compra con tarjeta",
      "asunto_contiene": ["compra"],
      "tipo": "gasto",
      "ignorar_si_contiene": ["rechazada", "declinada"],
      "moneda_por_defecto": "USD",
      "etiquetas": { "monto": "Monto:", "comercio": "Comercio:" }
    }
  ]
}
```

- **`remitentes`**: pedazos del remitente (dirección o nombre que aparece en «De:»). Con que uno aparezca, el correo es de ese banco. Sin mayúsculas ni tildes.
- **`asuntos_a_ignorar`**: si el asunto tiene alguna de estas frases, el correo se ignora (avisos de seguridad, publicidad).
- **`formatos`**: una entrada por cada tipo de correo que avise de plata. Se prueban en orden; gana el primero que encuentra el monto.
  - **`asunto_contiene`**: el formato solo se usa si el asunto tiene alguna de estas frases. Si el asunto coincide pero no se encuentra el monto, el bot te avisa que no lo pudo leer (así sabés que el banco cambió el correo).
  - **`tipo`**: `gasto` (se anota solo), `movimiento` (salió plata pero el correo no dice en qué: el bot pregunta la categoría) o `ingreso` (solo avisa, no cuenta como gasto).
  - **`ignorar_si_contiene`**: si el texto tiene alguna de estas palabras, no se anota (ej. compra rechazada).
  - **`es_ingreso_si_contiene`**: si el texto tiene alguna de estas, se trata como ingreso (ej. «acreditado»).
  - **`moneda_por_defecto`**: código de 3 letras si el correo no dice la moneda.
  - **`patron_cuenta`** (opcional): expresión regular cuyo primer grupo captura los últimos 4 dígitos de la tarjeta.
  - Para encontrar el monto usá **UNA** de estas dos formas:
    - **`etiquetas`** (preferida, más fácil): el texto que va justo antes de cada dato. El bot toma lo que sigue en la misma línea o, si está vacía, la línea siguiente. Claves: `monto` (obligatoria), `comercio`, `moneda`, `cuenta`. El valor del monto puede traer la moneda pegada (`USD 12.50`, `$ 45.90`, `L 1,500.00`).
    - **`patron`**: una expresión regular de Python (sin distinguir mayúsculas) con grupos con nombre: `(?P<monto>...)` obligatorio; `(?P<comercio>...)`, `(?P<moneda>...)`, `(?P<cuenta>...)` opcionales. Usala cuando los datos no están en formato «Etiqueta: valor» (por ejemplo, una tabla donde los títulos están en una fila y los valores en la siguiente, como en `bac.json`).
- El texto que ve el bot es el de `--ver-texto`: una línea por dato, sin líneas vacías. Escribí el patrón contra ESE texto, no contra cómo se ve el correo en pantalla.
- En JSON cada barra invertida va doble: `\\d` en vez de `\d`, `\\s` en vez de `\s`.
- Los montos pueden venir como `1,500.00` o `1.500,00`: el bot entiende los dos.

`plantilla.json` es un ejemplo completo con un banco inventado; `bac.json` es un ejemplo real con `patron`.
