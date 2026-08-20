import os


class Config:
    """Configuración de la aplicación, cargada desde variables de entorno."""

    SECRET_KEY = os.environ.get("SECRET_KEY", "cambia-esta-clave-en-produccion")

    # Turso / libSQL
    # Producción: TURSO_DATABASE_URL="libsql://tu-db-org.turso.io"
    # Local (sin Turso): se deja vacío y se usa un archivo sqlite local.
    TURSO_DATABASE_URL = os.environ.get("TURSO_DATABASE_URL", "")
    TURSO_AUTH_TOKEN = os.environ.get("TURSO_AUTH_TOKEN", "")
    LOCAL_DB_PATH = os.environ.get("LOCAL_DB_PATH", "local.db")

    # Cloudinary (fotos de perfil). Gratis hasta 25 créditos/mes.
    CLOUDINARY_CLOUD_NAME = os.environ.get("CLOUDINARY_CLOUD_NAME", "")
    CLOUDINARY_API_KEY = os.environ.get("CLOUDINARY_API_KEY", "")
    CLOUDINARY_API_SECRET = os.environ.get("CLOUDINARY_API_SECRET", "")

    # Cloudinary — almacenamiento de fotos de perfil.
    # Se configura con la variable CLOUDINARY_URL="cloudinary://api_key:api_secret@cloud_name"
    # (Cloud Run tiene sistema de archivos efímero, por eso las fotos NO se guardan en disco).
    CLOUDINARY_URL = os.environ.get("CLOUDINARY_URL", "")
    CLOUDINARY_FOLDER = os.environ.get("CLOUDINARY_FOLDER", "id-emergencia")

    # Cuánto tiempo (segundos) queda "desbloqueada" la info médica / edición
    # en la sesión del navegador después de ingresar el PIN/contraseña correcta.
    UNLOCK_SESSION_SECONDS = int(os.environ.get("UNLOCK_SESSION_SECONDS", "600"))

    SITE_NAME = os.environ.get("SITE_NAME", "ID de Emergencia")

    SLUG_RANDOM_SUFFIX_LEN = 4

    # Política de contraseña cuando el usuario la cambia (el PIN inicial de 6
    # dígitos que genera el admin queda exento de esta política).
    PASSWORD_MIN_LENGTH = 8
