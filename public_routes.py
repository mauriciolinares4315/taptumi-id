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

# Resumen médico de EMERGENCIA, no una historia clínica completa.
PERSON_MEDICAL_FIELDS = [
    ("blood_type", "Tipo de sangre"),
    ("conditions", "Condiciones / enfermedades relevantes"),
    ("allergies", "Alergias"),
    ("medications", "Medicamentos actuales"),
    ("medical_device", "Dispositivo o kit que porta y cómo usarlo"),
    ("care_instructions", "Qué hacer si presenta una crisis"),
    ("insurance", "EPS / Seguro médico"),
]

PET_MEDICAL_FIELDS = [
    ("conditions", "Condiciones / enfermedades"),
    ("allergies", "Alergias"),
    ("medications", "Medicamentos actuales"),
]

PERSON_EDITABLE_FIELDS = [
    "full_name", "document_id", "address", "phone",
    "emergency_contact_1_name", "emergency_contact_1_phone", "emergency_contact_1_relationship",
    "emergency_contact_2_name", "emergency_contact_2_phone", "emergency_contact_2_relationship",
    "emergency_contact_3_name", "emergency_contact_3_phone", "emergency_contact_3_relationship",
    "blood_type", "conditions", "allergies", "medications",
    "medical_device", "care_instructions", "insurance",
]

PET_EDITABLE_FIELDS = [
    "pet_name", "species", "breed", "color_markings", "sex", "age_approx", "microchip",
    "owner_name", "owner_phone", "owner_address",
    "conditions", "allergies", "medications",
    "temperament_notes", "reward_offered",
]


def _contact_message(name):
    return (
        f"Hola, encontré a {name} y tengo su ficha de identificación de "
        f"emergencia. Vi que eres su contacto de emergencia, ¿me puedes confirmar "
        f"si está todo bien o cómo puedo ayudar?"
    )


def _pet_contact_message(pet_name):
    return (
        f"Hola, encontré a {pet_name} y vi que eres su dueño/a en su ficha de "
        f"identificación. ¿Me confirmas dónde te la puedo devolver o si vienes por ella?"
    )


def _unlock_key(slug):
    return f"unlocked:{slug}"


def _is_unlocked(slug):
    entry = session.get(_unlock_key(slug))
    return bool(entry) and time.time() < entry


def _unlock(slug):
    ttl = current_app.config["UNLOCK_SESSION_SECONDS"]
    session[_unlock_key(slug)] = time.time() + ttl


def _build_person_contacts(user):
    contacts = []
    for i in (1, 2, 3):
        name = user.get(f"emergency_contact_{i}_name")
        phone = user.get(f"emergency_contact_{i}_phone")
        relationship = user.get(f"emergency_contact_{i}_relationship")
        if not (name or phone):
            continue
        message = _contact_message(user["full_name"])
        contacts.append({
            "name": name or f"Contacto de emergencia {i}",
            "relationship": relationship,
            "phone": phone,
            "phone_digits": utils.digits_only(phone),
            "message": message,
            "wa_link": utils.whatsapp_link(phone, message),
        })
    return contacts


def _build_owner_contact(pet):
    if not (pet.get("owner_name") or pet.get("owner_phone")):
        return None
    message = _pet_contact_message(pet["pet_name"])
    return {
        "name": pet.get("owner_name") or "Dueño/a",
        "phone": pet.get("owner_phone"),
        "phone_digits": utils.digits_only(pet.get("owner_phone")),
        "message": message,
        "wa_link": utils.whatsapp_link(pet.get("owner_phone"), message),
    }


@public_bp.route("/")
def home():
    return render_template("home.html")


@public_bp.route("/<slug>")
def profile(slug):
    kind, record = db.find_active_profile(slug)
    if not record:
        abort(404)

    if kind == "persona":
        unlocked = _is_unlocked(slug)
        contacts = _build_person_contacts(record)
        medical_fields = [(label, record.get(key)) for key, label in PERSON_MEDICAL_FIELDS if record.get(key)]
        return render_template(
            "profile.html", user=record, contacts=contacts,
            unlocked=unlocked, medical_fields=medical_fields,
        )
    else:
        owner_contact = _build_owner_contact(record)
        medical_fields = [(label, record.get(key)) for key, label in PET_MEDICAL_FIELDS if record.get(key)]
        return render_template(
            "pet_profile.html", pet=record, owner_contact=owner_contact,
            medical_fields=medical_fields,
        )


@public_bp.route("/<slug>/desbloquear", methods=["POST"])
def unlock(slug):
    user = db.query_one("SELECT * FROM users WHERE slug = ? AND is_active = 1", [slug])
    if not user:
        abort(404)
    pin = request.form.get("pin", "")
    if pin and check_password_hash(user["password_hash"], pin):
        _unlock(slug)
    else:
        flash("Código incorrecto. Intenta de nuevo.", "error")
    return redirect(url_for("public.profile", slug=slug))


@public_bp.route("/<slug>/editar", methods=["GET", "POST"])
def edit_profile(slug):
    kind, record = db.find_active_profile(slug)
    if not record:
        abort(404)

    login_template = "edit_login.html" if kind == "persona" else "pet_edit_login.html"
    form_template = "edit_profile.html" if kind == "persona" else "pet_edit_profile.html"
    table = "users" if kind == "persona" else "pets"
    context_key = "user" if kind == "persona" else "pet"
    editable_fields = PERSON_EDITABLE_FIELDS if kind == "persona" else PET_EDITABLE_FIELDS

    if not _is_unlocked(slug):
        if request.method == "POST" and "pin" in request.form:
            pin = request.form.get("pin", "")
            if check_password_hash(record["password_hash"], pin):
                _unlock(slug)
                return redirect(url_for("public.edit_profile", slug=slug))
            flash("Contraseña o PIN incorrecto.", "error")
        return render_template(login_template, **{context_key: record})

    if request.method == "POST":
        values = [request.form.get(f, "").strip() for f in editable_fields]

        photo_url = record.get("photo_url")
        photo_public_id = record.get("photo_public_id")
        new_photo = request.files.get("photo")
        if new_photo and new_photo.filename:
            try:
                photo_url, photo_public_id = photo_storage.upload_photo(new_photo, slug, kind=kind)
            except ValueError as exc:
                flash(str(exc), "error")
                return render_template(form_template, **{context_key: record})
        if request.form.get("remove_photo") == "1":
            photo_storage.delete_photo(photo_public_id)
            photo_url, photo_public_id = None, None

        extra_updates = {}
        if kind == "mascota":
            sterilized_raw = request.form.get("sterilized", "")
            extra_updates["sterilized"] = (
                1 if sterilized_raw == "si" else (0 if sterilized_raw == "no" else None)
            )

        set_parts = [f"{f} = ?" for f in editable_fields]
        params = list(values)
        for col, val in extra_updates.items():
            set_parts.append(f"{col} = ?")
            params.append(val)
        set_parts += ["photo_url = ?", "photo_public_id = ?"]
        params += [photo_url, photo_public_id]

        new_password = request.form.get("new_password", "").strip()
        if new_password:
            error = utils.password_strength_error(new_password)
            if error:
                flash(error, "error")
                return render_template(form_template, **{context_key: record})
            set_parts += ["password_hash = ?", "password_is_temp = 0"]
            params.append(generate_password_hash(new_password))
            flash("Perfil y contraseña actualizados correctamente.", "success")
        else:
            flash("Perfil actualizado correctamente.", "success")

        params.append(slug)
        db.execute(
            f"UPDATE {table} SET {', '.join(set_parts)}, updated_at = datetime('now') WHERE slug = ?",
            params,
        )
        return redirect(url_for("public.profile", slug=slug))

    return render_template(form_template, **{context_key: record})
