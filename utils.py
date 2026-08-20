import re
import secrets
import unicodedata


def slugify(text: str) -> str:
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    text = text.lower().strip()
    text = re.sub(r"[^a-z0-9]+", "-", text)
    return re.sub(r"-+", "-", text).strip("-")


def random_suffix(length: int = 4) -> str:
    alphabet = "abcdefghijkmnpqrstuvwxyz23456789"
    return "".join(secrets.choice(alphabet) for _ in range(length))


def generate_pin(length: int = 6) -> str:
    """PIN numérico inicial (fácil de escribir en una tarjeta/manilla NFC).
    El usuario debe reemplazarlo por una contraseña fuerte al editar su perfil.
    """
    return "".join(secrets.choice("0123456789") for _ in range(length))


_SPECIAL_CHARS = re.compile(r"[!@#$%^&*()_+\-=\[\]{};:'\",.<>/?\\|`~]")


def password_strength_error(password: str) -> str | None:
    """Devuelve un mensaje de error si la contraseña no es suficientemente
    fuerte, o None si es válida. Requisitos: 8+ caracteres, al menos una
    letra, un número y un carácter especial.
    """
    if len(password) < 8:
        return "La contraseña debe tener al menos 8 caracteres."
    if not re.search(r"[A-Za-z]", password):
        return "La contraseña debe incluir al menos una letra."
    if not re.search(r"[0-9]", password):
        return "La contraseña debe incluir al menos un número."
    if not _SPECIAL_CHARS.search(password):
        return "La contraseña debe incluir al menos un carácter especial (ej. ! @ # $ %)."
    return None


def digits_only(phone: str | None) -> str:
    if not phone:
        return ""
    return re.sub(r"\D", "", phone)


def whatsapp_link(phone: str | None, message: str) -> str | None:
    number = digits_only(phone)
    if not number:
        return None
    from urllib.parse import quote

    return f"https://wa.me/{number}?text={quote(message)}"
