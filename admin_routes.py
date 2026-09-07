from functools import wraps

from flask import (
    Blueprint, render_template, request, redirect, url_for,
    session, flash
)
from werkzeug.security import check_password_hash, generate_password_hash

import db
import utils
import photo_storage

admin_bp = Blueprint("admin", __name__, url_prefix="/admin")

PERSON_FIELDS = [
    "full_name", "document_id", "address", "phone",
    "emergency_contact_1_name", "emergency_contact_1_phone", "emergency_contact_1_relationship",
    "emergency_contact_2_name", "emergency_contact_2_phone", "emergency_contact_2_relationship",
    "emergency_contact_3_name", "emergency_contact_3_phone", "emergency_contact_3_relationship",
    "blood_type", "conditions", "allergies", "medications",
    "medical_device", "care_instructions", "insurance",
]

PET_FIELDS = [
    "pet_name", "species", "breed", "color_markings", "sex", "age_approx", "microchip",
    "owner_name", "owner_phone", "owner_address",
    "conditions", "allergies", "medications",
    "temperament_notes", "reward_offered",
]


def admin_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not session.get("admin_id"):
            flash("Debes iniciar sesión como administrador.", "error")
            return redirect(url_for("admin.login", next=request.path))
        return view(*args, **kwargs)
    return wrapped


def _unique_slug(full_name_or_pet_name, custom=""):
    base = utils.slugify(custom) or utils.slugify(full_name_or_pet_name)
    slug = base
    while db.slug_exists(slug):
        slug = f"{base}-{utils.random_suffix()}"
    return slug


@admin_bp.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        admin = db.query_one("SELECT * FROM admins WHERE username = ?", [username])
        if admin and check_password_hash(admin["password_hash"], password):
            session["admin_id"] = admin["id"]
            session["admin_username"] = admin["username"]
            return redirect(request.args.get("next") or url_for("admin.dashboard"))
        flash("Usuario o contraseña incorrectos.", "error")
    return render_template("admin_login.html")


@admin_bp.route("/logout")
def logout():
    session.pop("admin_id", None)
    session.pop("admin_username", None)
    return redirect(url_for("admin.login"))


@admin_bp.route("/")
@admin_required
def dashboard():
    q = request.args.get("q", "").strip()
    estado = request.args.get("estado", "activos")   # activos | inactivos | todos
    tipo = request.args.get("tipo", "todos")           # todos | personas | mascotas

    def build_where(kind_columns):
        where, params = [], []
        if estado == "activos":
            where.append("is_active = 1")
        elif estado == "inactivos":
            where.append("is_active = 0")
        if q:
            like = f"%{q}%"
            conds = " OR ".join(f"{c} LIKE ?" for c in kind_columns)
            where.append(f"({conds})")
            params += [like] * len(kind_columns)
        return where, params

    records = []

    if tipo in ("todos", "personas"):
        where, params = build_where(["full_name", "slug", "document_id"])
        sql = "SELECT * FROM users"
        if where:
            sql += " WHERE " + " AND ".join(where)
        sql += " ORDER BY created_at DESC"
        for u in db.query(sql, params):
            u["_type"] = "persona"
            u["_display_name"] = u["full_name"]
            records.append(u)

    if tipo in ("todos", "mascotas"):
        where, params = build_where(["pet_name", "slug", "microchip"])
        sql = "SELECT * FROM pets"
        if where:
            sql += " WHERE " + " AND ".join(where)
        sql += " ORDER BY created_at DESC"
        for p in db.query(sql, params):
            p["_type"] = "mascota"
            p["_display_name"] = p["pet_name"]
            records.append(p)

    records.sort(key=lambda r: r["created_at"], reverse=True)

    return render_template("admin_dashboard.html", records=records, q=q, estado=estado, tipo=tipo)


# ---------------------------------------------------------------------------
# Personas
# ---------------------------------------------------------------------------

@admin_bp.route("/crear", methods=["GET", "POST"])
@admin_required
def create_user():
    if request.method == "POST":
        full_name = request.form.get("full_name", "").strip()
        if not full_name:
            flash("El nombre completo es obligatorio.", "error")
            return render_template("admin_create_user.html", form=request.form)

        slug = _unique_slug(full_name, request.form.get("slug", ""))
        pin = utils.generate_pin()
        values = [request.form.get(f, "").strip() for f in PERSON_FIELDS]

        db.execute(
            f"""INSERT INTO users (slug, {", ".join(PERSON_FIELDS)}, password_hash, password_is_temp)
                VALUES (?, {", ".join(["?"] * len(PERSON_FIELDS))}, ?, 1)""",
            [slug] + values + [generate_password_hash(pin)],
        )

        photo = request.files.get("photo")
        if photo and photo.filename:
            try:
                photo_url, photo_public_id = photo_storage.upload_photo(photo, slug, kind="persona")
                db.execute(
                    "UPDATE users SET photo_url = ?, photo_public_id = ? WHERE slug = ?",
                    [photo_url, photo_public_id, slug],
                )
            except ValueError as exc:
                flash(f"Usuario creado, pero la foto no se pudo subir: {exc}", "error")

        return render_template(
            "admin_created.html", slug=slug, pin=pin, name=full_name, kind="persona"
        )

    return render_template("admin_create_user.html", form={})


@admin_bp.route("/usuario/<int:user_id>/editar", methods=["GET", "POST"])
@admin_required
def edit_user(user_id):
    user = db.query_one("SELECT * FROM users WHERE id = ?", [user_id])
    if not user:
        flash("Usuario no encontrado.", "error")
        return redirect(url_for("admin.dashboard"))

    if request.method == "POST":
        values = [request.form.get(f, "").strip() for f in PERSON_FIELDS]
        set_clause = ", ".join(f"{f} = ?" for f in PERSON_FIELDS)

        photo_url = user.get("photo_url")
        photo_public_id = user.get("photo_public_id")
        photo = request.files.get("photo")
        if photo and photo.filename:
            try:
                photo_url, photo_public_id = photo_storage.upload_photo(photo, user["slug"], kind="persona")
            except ValueError as exc:
                flash(f"No se pudo actualizar la foto: {exc}", "error")
        if request.form.get("remove_photo") == "1":
            photo_storage.delete_photo(photo_public_id)
            photo_url, photo_public_id = None, None

        db.execute(
            f"UPDATE users SET {set_clause}, photo_url = ?, photo_public_id = ?, "
            f"updated_at = datetime('now') WHERE id = ?",
            values + [photo_url, photo_public_id, user_id],
        )
        flash("Perfil actualizado.", "success")
        return redirect(url_for("admin.dashboard"))

    return render_template("admin_edit_user.html", user=user)


@admin_bp.route("/usuario/<int:user_id>/estado", methods=["POST"])
@admin_required
def toggle_status(user_id):
    user = db.query_one("SELECT * FROM users WHERE id = ?", [user_id])
    if user:
        db.execute(
            "UPDATE users SET is_active = ?, updated_at = datetime('now') WHERE id = ?",
            [0 if user["is_active"] else 1, user_id],
        )
        flash("Usuario bloqueado." if user["is_active"] else "Usuario reactivado.", "success")
    return redirect(request.referrer or url_for("admin.dashboard"))


@admin_bp.route("/usuario/<int:user_id>/eliminar", methods=["POST"])
@admin_required
def delete_user(user_id):
    user = db.query_one("SELECT * FROM users WHERE id = ?", [user_id])
    if user:
        photo_storage.delete_photo(user.get("photo_public_id"))
        db.execute("DELETE FROM users WHERE id = ?", [user_id])
        flash(f"Usuario '{user['full_name']}' eliminado permanentemente.", "success")
    return redirect(url_for("admin.dashboard"))


@admin_bp.route("/usuario/<int:user_id>/reset-password", methods=["POST"])
@admin_required
def reset_password(user_id):
    user = db.query_one("SELECT * FROM users WHERE id = ?", [user_id])
    if not user:
        flash("Usuario no encontrado.", "error")
        return redirect(url_for("admin.dashboard"))
    pin = utils.generate_pin()
    db.execute(
        "UPDATE users SET password_hash = ?, password_is_temp = 1, updated_at = datetime('now') WHERE id = ?",
        [generate_password_hash(pin), user_id],
    )
    return render_template(
        "admin_created.html", slug=user["slug"], pin=pin, name=user["full_name"],
        kind="persona", reset=True,
    )


# ---------------------------------------------------------------------------
# Mascotas
# ---------------------------------------------------------------------------

@admin_bp.route("/mascota/crear", methods=["GET", "POST"])
@admin_required
def create_pet():
    if request.method == "POST":
        pet_name = request.form.get("pet_name", "").strip()
        if not pet_name:
            flash("El nombre de la mascota es obligatorio.", "error")
            return render_template("admin_create_pet.html", form=request.form)

        slug = _unique_slug(pet_name, request.form.get("slug", ""))
        pin = utils.generate_pin()
        values = [request.form.get(f, "").strip() for f in PET_FIELDS]

        sterilized_raw = request.form.get("sterilized", "")
        sterilized = 1 if sterilized_raw == "si" else (0 if sterilized_raw == "no" else None)

        db.execute(
            f"""INSERT INTO pets (slug, {", ".join(PET_FIELDS)}, sterilized, password_hash, password_is_temp)
                VALUES (?, {", ".join(["?"] * len(PET_FIELDS))}, ?, ?, 1)""",
            [slug] + values + [sterilized, generate_password_hash(pin)],
        )

        photo = request.files.get("photo")
        if photo and photo.filename:
            try:
                photo_url, photo_public_id = photo_storage.upload_photo(photo, slug, kind="mascota")
                db.execute(
                    "UPDATE pets SET photo_url = ?, photo_public_id = ? WHERE slug = ?",
                    [photo_url, photo_public_id, slug],
                )
            except ValueError as exc:
                flash(f"Mascota creada, pero la foto no se pudo subir: {exc}", "error")

        return render_template(
            "admin_created.html", slug=slug, pin=pin, name=pet_name, kind="mascota"
        )

    return render_template("admin_create_pet.html", form={})


@admin_bp.route("/mascota/<int:pet_id>/editar", methods=["GET", "POST"])
@admin_required
def edit_pet(pet_id):
    pet = db.query_one("SELECT * FROM pets WHERE id = ?", [pet_id])
    if not pet:
        flash("Mascota no encontrada.", "error")
        return redirect(url_for("admin.dashboard"))

    if request.method == "POST":
        values = [request.form.get(f, "").strip() for f in PET_FIELDS]
        set_clause = ", ".join(f"{f} = ?" for f in PET_FIELDS)

        sterilized_raw = request.form.get("sterilized", "")
        sterilized = 1 if sterilized_raw == "si" else (0 if sterilized_raw == "no" else None)

        photo_url = pet.get("photo_url")
        photo_public_id = pet.get("photo_public_id")
        photo = request.files.get("photo")
        if photo and photo.filename:
            try:
                photo_url, photo_public_id = photo_storage.upload_photo(photo, pet["slug"], kind="mascota")
            except ValueError as exc:
                flash(f"No se pudo actualizar la foto: {exc}", "error")
        if request.form.get("remove_photo") == "1":
            photo_storage.delete_photo(photo_public_id)
            photo_url, photo_public_id = None, None

        db.execute(
            f"UPDATE pets SET {set_clause}, sterilized = ?, photo_url = ?, photo_public_id = ?, "
            f"updated_at = datetime('now') WHERE id = ?",
            values + [sterilized, photo_url, photo_public_id, pet_id],
        )
        flash("Perfil de mascota actualizado.", "success")
        return redirect(url_for("admin.dashboard"))

    return render_template("admin_edit_pet.html", pet=pet)


@admin_bp.route("/mascota/<int:pet_id>/estado", methods=["POST"])
@admin_required
def toggle_pet_status(pet_id):
    pet = db.query_one("SELECT * FROM pets WHERE id = ?", [pet_id])
    if pet:
        db.execute(
            "UPDATE pets SET is_active = ?, updated_at = datetime('now') WHERE id = ?",
            [0 if pet["is_active"] else 1, pet_id],
        )
        flash("Mascota bloqueada." if pet["is_active"] else "Mascota reactivada.", "success")
    return redirect(request.referrer or url_for("admin.dashboard"))


@admin_bp.route("/mascota/<int:pet_id>/eliminar", methods=["POST"])
@admin_required
def delete_pet(pet_id):
    pet = db.query_one("SELECT * FROM pets WHERE id = ?", [pet_id])
    if pet:
        photo_storage.delete_photo(pet.get("photo_public_id"))
        db.execute("DELETE FROM pets WHERE id = ?", [pet_id])
        flash(f"Mascota '{pet['pet_name']}' eliminada permanentemente.", "success")
    return redirect(url_for("admin.dashboard"))


@admin_bp.route("/mascota/<int:pet_id>/reset-password", methods=["POST"])
@admin_required
def reset_pet_password(pet_id):
    pet = db.query_one("SELECT * FROM pets WHERE id = ?", [pet_id])
    if not pet:
        flash("Mascota no encontrada.", "error")
        return redirect(url_for("admin.dashboard"))
    pin = utils.generate_pin()
    db.execute(
        "UPDATE pets SET password_hash = ?, password_is_temp = 1, updated_at = datetime('now') WHERE id = ?",
        [generate_password_hash(pin), pet_id],
    )
    return render_template(
        "admin_created.html", slug=pet["slug"], pin=pin, name=pet["pet_name"],
        kind="mascota", reset=True,
    )
