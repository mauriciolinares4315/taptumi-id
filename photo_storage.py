"""
Manejo de fotos de perfil vía Cloudinary.

Cloud Run tiene disco efímero, así que no sirve para guardar archivos
subidos por los usuarios. Cloudinary da una URL pública, estable, con CDN,
gratis en su plan free (25 créditos/mes, de sobra para este caso de uso).
"""
from __future__ import annotations

import cloudinary
import cloudinary.uploader
from flask import current_app

_configured = False


def _ensure_configured():
    global _configured
    if _configured:
        return
    cloudinary.config(
        cloud_name=current_app.config["CLOUDINARY_CLOUD_NAME"],
        api_key=current_app.config["CLOUDINARY_API_KEY"],
        api_secret=current_app.config["CLOUDINARY_API_SECRET"],
        secure=True,
    )
    _configured = True


def is_enabled() -> bool:
    return bool(current_app.config["CLOUDINARY_CLOUD_NAME"])


def upload_photo(file_storage, slug: str, kind: str = "persona", max_bytes: int = 5_000_000):
    """Sube la foto a Cloudinary. public_id = nfc-id/<kind>/<slug>, así que
    volver a subir una foto para el mismo perfil SOBRESCRIBE la anterior
    (evita imágenes huérfanas). Devuelve (secure_url, public_id) o levanta
    ValueError con un mensaje amigable si algo falla.
    """
    if not is_enabled():
        raise ValueError(
            "La subida de fotos no está configurada. Define las variables "
            "CLOUDINARY_CLOUD_NAME, CLOUDINARY_API_KEY y CLOUDINARY_API_SECRET."
        )

    data = file_storage.read()
    if len(data) > max_bytes:
        raise ValueError("La foto es muy pesada (máximo 5 MB).")
    file_storage.stream.seek(0)

    _ensure_configured()
    public_id = f"nfc-id/{kind}/{slug}"
    result = cloudinary.uploader.upload(
        data,
        public_id=public_id,
        overwrite=True,
        resource_type="image",
        transformation=[{"width": 500, "height": 500, "crop": "fill", "gravity": "face"}],
    )
    return result["secure_url"], result["public_id"]


def delete_photo(public_id: str | None):
    if not public_id or not is_enabled():
        return
    _ensure_configured()
    try:
        cloudinary.uploader.destroy(public_id)
    except Exception:
        pass
