# ID de Emergencia (NFC) — Personas y Mascotas

Ficha de identificación de emergencia. Cada persona o mascota tiene un
perfil con URL única (`tu-dominio.com/slug`), pensado para grabar en una
tarjeta o manilla NFC / código QR: al acercar el celular, cualquiera ve los
datos de contacto (y para personas, un resumen médico protegido) y puede
avisar por WhatsApp con un toque, compartiendo su ubicación si el navegador
lo permite.

## Stack

- **Backend:** Flask (Python)
- **Base de datos:** Turso (libSQL, compatible con SQLite) vía `libsql-client`
- **Fotos:** Cloudinary
- **Frontend:** HTML + CSS propio, estilo iOS / glassmorphism, responsive
- **Deploy:** Docker + Google Cloud Run

## Estructura del proyecto

```
app.py              Punto de entrada Flask + comandos CLI (init-db, create-admin)
config.py           Configuración vía variables de entorno
db.py                 Acceso a Turso/libSQL + esquema (users, pets, admins)
utils.py              Slugs, PIN, validación de contraseña, link de WhatsApp
photo_storage.py      Subida de fotos a Cloudinary
public_routes.py      Rutas públicas: perfil (persona o mascota), desbloqueo, edición
admin_routes.py       Rutas de admin: login, dashboard combinado, CRUD de ambos tipos
templates/            Plantillas Jinja2 (persona y mascota por separado)
static/                CSS y JS
Dockerfile
requirements.txt
```

## Modelo de datos

**users** (personas): `slug`, datos personales, hasta 3 contactos de
emergencia (nombre + teléfono + parentesco), resumen médico (tipo de
sangre, condiciones, alergias, medicamentos, dispositivo médico y cómo
usarlo, qué hacer en caso de crisis, EPS), foto, `password_hash`, `is_active`.

**pets** (mascotas): `slug`, nombre, especie, raza, color/señas, sexo, edad
aproximada, esterilización, microchip, datos del dueño/a (nombre, teléfono,
zona), resumen médico breve, **temperamento y cómo acercarse** (clave para
un rescate seguro), recompensa opcional, foto, `password_hash`, `is_active`.

**admins**: `username`, `password_hash` — un único super-admin, creado por
comando de terminal, sin ruta web para crear más cuentas admin.

> El **slug es un único espacio de nombres compartido** entre `users` y
> `pets` — no pueden repetirse URLs entre una persona y una mascota.

## Diferencias clave entre perfiles de persona y mascota

| | Persona | Mascota |
|---|---|---|
| Datos médicos | Protegidos con PIN | Públicos (no tan sensibles) |
| Contactos | Hasta 3, con parentesco | Solo dueño/a |
| Campo especial | — | Temperamento / cómo acercarse, recompensa |
| Edición | Requiere PIN propio | Requiere PIN propio |

## Seguridad y privacidad

- **Personas:** nombre, documento, dirección, teléfono y contactos de
  emergencia son siempre públicos (para poder avisar rápido). Los datos
  médicos quedan detrás de un PIN — la sesión del navegador queda
  desbloqueada 10 minutos (`UNLOCK_SESSION_SECONDS`).
- **Mascotas:** todo el perfil es público al escanear (dueño, zona,
  temperamento, resumen médico) — decisión tomada porque no maneja datos
  tan sensibles como una persona. Solo la **edición** requiere PIN.
- **Contraseña inicial:** PIN numérico de 6 dígitos generado por el admin.
  Al editar, se exige una contraseña fuerte (8+ caracteres, letra + número
  + símbolo) para reemplazarlo.
- **Mostrar/ocultar contraseña:** todos los campos de PIN/contraseña
  incluyen un botón de ojo para verificar lo que se está escribiendo antes
  de enviarlo.
- **Compartir ubicación por WhatsApp:** al pulsar "Avisar por WhatsApp", el
  navegador pide permiso de geolocalización (diálogo nativo del sistema; el
  servidor nunca ve ni guarda esa ubicación). Si el usuario acepta, se
  agrega un link de Google Maps al mensaje; si rechaza o no hay soporte, el
  mensaje se envía igual sin ubicación. Solo funciona sobre HTTPS (Cloud Run
  ya lo da por defecto).

## 1. Desarrollo local

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

cp .env.example .env
# Sin TURSO_DATABASE_URL, se usa un archivo local.db automáticamente.

export FLASK_APP=app.py
flask init-db
flask create-admin admin "TuPass123!"

# Si vas a correr algo más en el puerto 8080, usa otro:
export PORT=8081
python app.py
```

## 2. Turso

```bash
turso auth login
turso db create nfc-id-app
turso db show nfc-id-app --url          # -> TURSO_DATABASE_URL
turso db tokens create nfc-id-app       # -> TURSO_AUTH_TOKEN
```

Con esas variables puestas, corre una vez:
```bash
export TURSO_DATABASE_URL="libsql://..."
export TURSO_AUTH_TOKEN="..."
export FLASK_APP=app.py
flask init-db
flask create-admin admin "TuPass123!"
```

## 3. Cloudinary

Cuenta gratis en https://cloudinary.com/users/register/free → copia
**Cloud name**, **API Key**, **API Secret** al `.env` / variables de Cloud
Run. Las fotos de persona se guardan como `nfc-id/persona/<slug>` y las de
mascota como `nfc-id/mascota/<slug>` (así nunca chocan entre sí).

## 4. Deploy en Google Cloud Run

```bash
gcloud auth login
gcloud config set project TU_PROJECT_ID
gcloud services enable run.googleapis.com artifactregistry.googleapis.com

gcloud builds submit --tag gcr.io/TU_PROJECT_ID/nfc-id-app

gcloud run deploy nfc-id-app \
  --image gcr.io/TU_PROJECT_ID/nfc-id-app \
  --platform managed \
  --region us-central1 \
  --allow-unauthenticated \
  --set-env-vars SECRET_KEY="clave-aleatoria-larga" \
  --set-env-vars SITE_NAME="ID de Emergencia" \
  --set-env-vars TURSO_DATABASE_URL="libsql://..." \
  --set-env-vars TURSO_AUTH_TOKEN="..." \
  --set-env-vars CLOUDINARY_CLOUD_NAME="..." \
  --set-env-vars CLOUDINARY_API_KEY="..." \
  --set-env-vars CLOUDINARY_API_SECRET="..."
```

Sin dominio propio, usas la URL que da Cloud Run
(`https://nfc-id-app-xxxxx-uc.a.run.app/slug`) para grabar en las
tarjetas/manillas NFC.

## 5. Flujo de uso

- **Admin** entra a `/admin/login`, y desde el dashboard puede crear
  personas (`+ Crear persona`) o mascotas (`+ Crear mascota`), buscar,
  filtrar por tipo (Personas/Mascotas/Todos) y estado
  (Activos/Bloqueados/Todos), editar, resetear PIN, bloquear/reactivar o
  eliminar cualquier perfil.
- **La persona/dueño** recibe la URL + PIN y puede entrar a `/slug/editar`
  para completar sus datos y cambiar el PIN por una contraseña propia.
- **Quien encuentra** a la persona o mascota abre la URL (NFC o QR): ve la
  info relevante y puede pulsar WhatsApp para avisar, compartiendo su
  ubicación si lo permite.

## Notas

- Super-admin único, gestionado por `flask create-admin` desde terminal —
  no hay ruta web para crear más admins.
- Límite de foto: 5 MB, recortada automáticamente a 500x500 centrada en el
  rostro por Cloudinary.
- El panel de admin es responsive: en pantallas angostas la tabla se
  convierte en tarjetas apiladas.
- Si más adelante quieres auditar accesos a datos médicos, es una tabla
  adicional sencilla de sumar.
