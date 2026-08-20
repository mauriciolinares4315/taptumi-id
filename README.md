# ID de Emergencia (NFC)

Ficha de identificación de emergencia. Cada persona tiene un perfil con URL
única (`tu-dominio.com/slug`), pensado para grabar en una tarjeta o manilla
NFC / código QR: al acercar el celular, cualquiera ve sus datos de contacto
y un resumen médico básico, y puede avisar a la familia por WhatsApp con un
toque.

## Stack

- **Backend:** Flask (Python)
- **Base de datos:** Turso (libSQL, compatible con SQLite) vía `libsql-client`
- **Fotos:** Cloudinary (Cloud Run no tiene disco persistente)
- **Frontend:** HTML + CSS propio, estilo iOS / glassmorphism (sin frameworks)
- **Deploy:** Docker + Google Cloud Run

## Estructura del proyecto

```
app.py              Punto de entrada Flask + comandos CLI (init-db, create-admin)
config.py           Configuración vía variables de entorno
db.py                Acceso a Turso/libSQL + esquema de la base de datos
utils.py             Slugs, PIN, validación de contraseña, link de WhatsApp
photo_storage.py     Subida de fotos a Cloudinary
public_routes.py     Rutas públicas: ver perfil, desbloquear datos médicos, editar
admin_routes.py      Rutas de administración: login, dashboard, crear/editar/bloquear/eliminar
templates/           Plantillas Jinja2
static/               CSS y JS
Dockerfile
requirements.txt
```

## Modelo de datos (resumen)

**users**: `slug`, datos personales (nombre, documento, dirección, teléfono),
hasta 3 contactos de emergencia (nombre + teléfono + parentesco), resumen
médico (tipo de sangre, condiciones, alergias, medicamentos, dispositivo
médico y cómo usarlo, qué hacer en caso de crisis, EPS), foto (URL de
Cloudinary), `password_hash` (PIN o contraseña), `is_active`.

**admins**: `username`, `password_hash`.

> El resumen médico es intencionalmente **breve y orientativo** — no es una
> historia clínica. Está pensado para que alguien sin formación médica sepa
> qué hacer en los primeros minutos (ej. "Epilepsia — si convulsiona,
> colocar de lado y cronometrar").

## Seguridad y privacidad — cómo funciona

- **Datos públicos siempre visibles:** nombre, documento, dirección,

  teléfono propio y **contactos de emergencia** (para que cualquiera pueda
  avisar rápido — es el objetivo principal del proyecto).
- **Datos médicos protegidos:** ocultos detrás de un PIN/contraseña. Al
  ingresarlo correctamente, la sesión del navegador queda "desbloqueada"
  por 10 minutos (configurable con `UNLOCK_SESSION_SECONDS`).
- **Editar el perfil** requiere la misma contraseña/PIN.
- **Contraseña inicial:** el admin genera un **PIN numérico de 6 dígitos**
  al crear el usuario (fácil de escribir a mano en una tarjeta física). El
  perfil queda marcado como "PIN temporal" y, al editar, se anima a
  reemplazarlo por una contraseña fuerte (8+ caracteres, con letras,
  números y un símbolo). El admin puede resetear el PIN en cualquier
  momento desde el panel.
- Ten en cuenta que esto es un candado **disuasivo**, no cifrado de nivel
  hospitalario — adecuado para el caso de uso (evitar que cualquiera vea
  los datos médicos con solo tener la URL), no para datos ultra sensibles.

## 1. Desarrollo local

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

cp .env.example .env
# Edita .env: si dejas TURSO_DATABASE_URL vacío, se usa un archivo
# local.db automáticamente (no necesitas Turso para desarrollar).

export FLASK_APP=app.py
flask init-db                      # crea las tablas
flask create-admin admin "TuPass123!"   # crea el primer admin

python app.py                      # sirve en http://localhost:8080
```

## 2. Turso (base de datos en producción)

Ya tienes cuenta creada, así que solo necesitas la base de datos y sus
credenciales:

```bash
# Instala el CLI si no lo tienes: https://docs.turso.tech/cli/installation
turso auth login

turso db create nfc-id-app
turso db show nfc-id-app --url          # copia esto -> TURSO_DATABASE_URL
turso db tokens create nfc-id-app       # copia esto -> TURSO_AUTH_TOKEN
```

Con esas dos variables puestas en `.env` (o en Cloud Run, más abajo), corre
una vez:

```bash
export TURSO_DATABASE_URL="libsql://..."
export TURSO_AUTH_TOKEN="..."
export FLASK_APP=app.py
flask init-db
flask create-admin admin "TuPass123!"
```

Esto crea las tablas directamente en Turso y tu primer usuario admin.

## 3. Cloudinary (fotos de perfil)

1. Crea una cuenta gratis en https://cloudinary.com/users/register/free
2. En el dashboard copia: **Cloud name**, **API Key**, **API Secret**.
3. Ponlos en `.env` / variables de entorno de Cloud Run.

Si prefieres no usar Cloudinary, la app funciona igual — simplemente no se
podrá subir foto (queda oculto ese bloque de forma segura, no falla).
Alternativa: Google Cloud Storage con un bucket público, avísame si
prefieres esa ruta y ajusto `photo_storage.py`.

## 4. Deploy en Google Cloud Run

Ya tienes el proyecto de GCP, así que:

```bash
gcloud auth login
gcloud config set project TU_PROJECT_ID

# Habilita las APIs necesarias (una sola vez)
gcloud services enable run.googleapis.com artifactregistry.googleapis.com

# Build & push de la imagen con Cloud Build (no necesitas Docker local)
gcloud builds submit --tag gcr.io/TU_PROJECT_ID/nfc-id-app

# Deploy
gcloud run deploy nfc-id-app \
  --image gcr.io/TU_PROJECT_ID/nfc-id-app \
  --platform managed \
  --region us-central1 \
  --allow-unauthenticated \
  --set-env-vars SECRET_KEY="genera-una-clave-aleatoria-larga" \
  --set-env-vars SITE_NAME="ID de Emergencia" \
  --set-env-vars TURSO_DATABASE_URL="libsql://..." \
  --set-env-vars TURSO_AUTH_TOKEN="..." \
  --set-env-vars CLOUDINARY_CLOUD_NAME="..." \
  --set-env-vars CLOUDINARY_API_KEY="..." \
  --set-env-vars CLOUDINARY_API_SECRET="..."
```

> Como no tienes dominio propio todavía, Cloud Run te da una URL del tipo
> `https://nfc-id-app-xxxxx-uc.a.run.app`. Es la que grabarás en las
> tarjetas/manillas NFC (`.../slug-de-la-persona`). Cuando tengas un
> dominio, se mapea después con `gcloud run domain-mappings create` sin
> tocar código.

Cloud Run escala a cero: si nadie usa la app no cobra cómputo, solo Turso
(gratis en su plan free hasta cierto volumen) y Cloudinary (gratis hasta 25
créditos/mes).

**Importante:** las variables se pueden poner también con `--set-secrets`
usando Secret Manager en vez de `--set-env-vars` para el `SECRET_KEY` y el
`TURSO_AUTH_TOKEN` — recomendado antes de ir a producción real.

## 5. Grabar la tarjeta / manilla NFC

Una vez creado un usuario desde el panel de admin, la pantalla de
confirmación te muestra la URL completa (ej.
`https://nfc-id-app-xxxxx-uc.a.run.app/juan-perez`) y el PIN inicial.

Para grabar esa URL en un tag NFC (NTAG213/215/216, son los más comunes y
baratos) puedes usar apps gratuitas como **NFC Tools** (Android/iOS):
"Escribir" → "Añadir registro" → "URL/URI" → pega el enlace → "Escribir".
También puedes generar un QR con esa misma URL como respaldo (por si el
celular de quien encuentra a la persona no tiene NFC).

## 6. Flujo de uso

- **Admin** entra a `/admin/login`, crea usuarios desde `/admin/crear`
  (ahí se genera el slug y el PIN), y desde el dashboard puede buscar,
  editar, bloquear/reactivar, resetear el PIN o eliminar cualquier perfil.
- **La persona (o su acudiente)** recibe la URL + PIN, y puede entrar a
  `/slug/editar` para completar o corregir sus datos y cambiar el PIN por
  una contraseña propia.
- **Quien encuentra a la persona** solo abre la URL (por NFC o QR): ve el
  nombre, contactos y puede pulsar el botón de WhatsApp para avisar de
  inmediato. Si necesita el detalle médico, pide el PIN a quien lo tenga
  (la persona, su familia, o va grabado también físicamente en la tarjeta).

## Notas y próximos pasos posibles

- El acceso de administrador es **un único super-admin fijo**, creado y
  gestionado por comando (`flask create-admin usuario contraseña`) desde tu
  terminal o Cloud Shell — no existe ninguna ruta web para crear más
  cuentas admin, así se reduce la superficie de ataque ya que solo tú
  operas la plataforma. Si más adelante quieres sumar otro admin, corre de
  nuevo `flask create-admin` con otro usuario apuntando a tu base de Turso.
- El límite de subida de foto es 5 MB; Cloudinary la recorta automáticamente
  a un cuadrado 500x500 centrado en el rostro.
- Si más adelante quieres registrar quién accedió a los datos médicos
  (auditoría), es una tabla adicional sencilla de sumar.
