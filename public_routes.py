import time

from flask import (
    Blueprint, render_template, request, redirect, url_for,
    session, flash, current_app, abort
)
from werkzeug.security import check_password_hash, generate_password_hash

import db
import utils
import photo_storage

public_bp = Blueprint("public", __name__)

# Campos médicos: un RESUMEN de emergencia para alguien sin formación
# médica, no una historia clínica completa.
MEDICAL_FIELDS = [
    ("blood_type", "Tipo de sangre"),
    ("conditions", "Condiciones / enfermedades relevantes"),
    ("allergies", "Alergias"),
    ("medications", "Medicamentos actuales"),
    ("medical_device", "Dispositivo o kit que porta y cómo usarlo"),
    ("care_instructions", "Qué hacer si presenta una crisis"),
    ("insurance", "EPS / Seguro médico"),
]

EDITABLE_TEXT_FIELDS = [
    "full_name", "document_id", "address", "phone",
    "emergency_contact_1_name", "emergency_contact_1_phone", "emergency_contact_1_relationship",
    "emergency_contact_2_name", "emergency_contact_2_phone", "emergency_contact_2_relationship",
    "emergency_contact_3_name", "emergency_contact_3_phone", "emergency_contact_3_relationship",
    "blood_type", "conditions", "allergies", "medications",
    "medical_device", "care_instructions", "insurance",
]


def _get_active_user(slug):
    user = db.query_one(
        "SELECT * FROM users WHERE slug = ? AND is_active = 1", [slug]
    )
    if not user:
        abort(404)
    return user


def _unlock_key(slug):
    return f"unlocked:{slug}"


def _is_unlocked(slug):
    entry = session.get(_unlock_key(slug))
    return bool(entry) and time.time() < entry


def _unlock(slug):
    ttl = current_app.config["UNLOCK_SESSION_SECONDS"]
    session[_unlock_key(slug)] = time.time() + ttl


def _contact_message(full_name):
    return (
        f"Hola, encontré a {full_name} y tengo su ficha de identificación de "
        f"emergencia. Vi que soy su contacto de emergencia, ¿me puedes confirmar "
        f"si está todo bien o cómo puedo ayudar?"
    )


def _build_contacts(user):
    contacts = []
    for i in (1, 2, 3):
        name = user.get(f"emergency_contact_{i}_name")
        phone = user.get(f"emergency_contact_{i}_phone")
        relationship = user.get(f"emergency_contact_{i}_relationship")
        if not (name or phone):
            continue
        contacts.append({
            "name": name or f"Contacto de emergencia {i}",
            "relationship": relationship,
            "phone": phone,
            "wa_link": utils.whatsapp_link(phone, _contact_message(user["full_name"])),
        })
    return contacts


@public_bp.route("/")
def home():
    return render_template("home.html")


@public_bp.route("/<slug>")
def profile(slug):
    user = _get_active_user(slug)
    unlocked = _is_unlocked(slug)
    contacts = _build_contacts(user)
    medical_fields = [(label, user.get(key)) for key, label in MEDICAL_FIELDS if user.get(key)]

    return render_template(
        "profile.html",
        user=user,
        contacts=contacts,
        unlocked=unlocked,
        medical_fields=medical_fields,
    )


@public_bp.route("/<slug>/desbloquear", methods=["POST"])
def unlock(slug):
    user = _get_active_user(slug)
    pin = request.form.get("pin", "")
    if pin and check_password_hash(user["password_hash"], pin):
        _unlock(slug)
    else:
        flash("Código incorrecto. Intenta de nuevo.", "error")
    return redirect(url_for("public.profile", slug=slug))


@public_bp.route("/<slug>/editar", methods=["GET", "POST"])
def edit_profile(slug):
    user = _get_active_user(slug)

    if not _is_unlocked(slug):
        if request.method == "POST" and "pin" in request.form:
            pin = request.form.get("pin", "")
            if check_password_hash(user["password_hash"], pin):
                _unlock(slug)
                return redirect(url_for("public.edit_profile", slug=slug))
            flash("Contraseña o PIN incorrecto.", "error")
        return render_template("edit_login.html", user=user)

    if request.method == "POST":
        values = [request.form.get(f, "").strip() for f in EDITABLE_TEXT_FIELDS]

        photo_url = user.get("photo_url")
        photo_public_id = user.get("photo_public_id")
        new_photo = request.files.get("photo")
        if new_photo and new_photo.filename:
            try:
                photo_url, photo_public_id = photo_storage.upload_photo(new_photo, slug)
            except ValueError as exc:
                flash(str(exc), "error")
                return render_template("edit_profile.html", user=user)
        if request.form.get("remove_photo") == "1":
            photo_storage.delete_photo(photo_public_id)
            photo_url, photo_public_id = None, None

        set_clause = ", ".join(f"{f} = ?" for f in EDITABLE_TEXT_FIELDS)
        params = values + [photo_url, photo_public_id]

        new_password = request.form.get("new_password", "").strip()
        if new_password:
            error = utils.password_strength_error(new_password)
            if error:
                flash(error, "error")
                return render_template("edit_profile.html", user=user)
            db.execute(
                f"UPDATE users SET {set_clause}, photo_url = ?, photo_public_id = ?, "
                f"password_hash = ?, password_is_temp = 0, updated_at = datetime('now') "
                f"WHERE slug = ?",
                params + [generate_password_hash(new_password), slug],
            )
            flash("Perfil y contraseña actualizados correctamente.", "success")
        else:
            db.execute(
                f"UPDATE users SET {set_clause}, photo_url = ?, photo_public_id = ?, "
                f"updated_at = datetime('now') WHERE slug = ?",
                params + [slug],
            )
            flash("Perfil actualizado correctamente.", "success")
        return redirect(url_for("public.profile", slug=slug))

    return render_template("edit_profile.html", user=user)
