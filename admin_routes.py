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

EDITABLE_FIELDS = [
    "full_name", "document_id", "address", "phone",
    "emergency_contact_1_name", "emergency_contact_1_phone", "emergency_contact_1_relationship",
    "emergency_contact_2_name", "emergency_contact_2_phone", "emergency_contact_2_relationship",
    "emergency_contact_3_name", "emergency_contact_3_phone", "emergency_contact_3_relationship",
    "blood_type", "conditions", "allergies", "medications",
    "medical_device", "care_instructions", "insurance",
]


def admin_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not session.get("admin_id"):
            flash("Debes iniciar sesión como administrador.", "error")
            return redirect(url_for("admin.login", next=request.path))
        return view(*args, **kwargs)
    return wrapped


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
    estado = request.args.get("estado", "activos")  # activos | inactivos | todos

    where = []
    params = []
    if estado == "activos":
        where.append("is_active = 1")
    elif estado == "inactivos":
        where.append("is_active = 0")

    if q:
        like = f"%{q}%"
        where.append("(full_name LIKE ? OR slug LIKE ? OR document_id LIKE ?)")
        params += [like, like, like]

    sql = "SELECT * FROM users"
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY created_at DESC"

    users = db.query(sql, params)
    return render_template("admin_dashboard.html", users=users, q=q, estado=estado)


@admin_bp.route("/crear", methods=["GET", "POST"])
@admin_required
def create_user():
    if request.method == "POST":
        full_name = request.form.get("full_name", "").strip()
        if not full_name:
            flash("El nombre completo es obligatorio.", "error")
            return render_template("admin_create_user.html", form=request.form)

        custom_slug = utils.slugify(request.form.get("slug", ""))
        base = custom_slug or utils.slugify(full_name)
        slug = base
        while db.query_one("SELECT id FROM users WHERE slug = ?", [slug]):
            slug = f"{base}-{utils.random_suffix()}"

        pin = utils.generate_pin()
        values = [request.form.get(f, "").strip() for f in EDITABLE_FIELDS]

        db.execute(
            f"""INSERT INTO users (slug, {", ".join(EDITABLE_FIELDS)}, password_hash, password_is_temp)
                VALUES (?, {", ".join(["?"] * len(EDITABLE_FIELDS))}, ?, 1)""",
            [slug] + values + [generate_password_hash(pin)],
        )

        new_user = db.query_one("SELECT id FROM users WHERE slug = ?", [slug])
        photo = request.files.get("photo")
        if photo and photo.filename:
            try:
                photo_url, photo_public_id = photo_storage.upload_photo(photo, slug)
                db.execute(
                    "UPDATE users SET photo_url = ?, photo_public_id = ? WHERE id = ?",
                    [photo_url, photo_public_id, new_user["id"]],
                )
            except ValueError as exc:
                flash(f"Usuario creado, pero la foto no se pudo subir: {exc}", "error")

        return render_template(
            "admin_user_created.html", slug=slug, pin=pin, full_name=full_name
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
        values = [request.form.get(f, "").strip() for f in EDITABLE_FIELDS]
        set_clause = ", ".join(f"{f} = ?" for f in EDITABLE_FIELDS)

        photo_url = user.get("photo_url")
        photo_public_id = user.get("photo_public_id")
        photo = request.files.get("photo")
        if photo and photo.filename:
            try:
                photo_url, photo_public_id = photo_storage.upload_photo(photo, user["slug"])
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
        flash(
            "Usuario bloqueado." if user["is_active"] else "Usuario reactivado.",
            "success",
        )
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
        "UPDATE users SET password_hash = ?, password_is_temp = 1, updated_at = datetime('now') "
        "WHERE id = ?",
        [generate_password_hash(pin), user_id],
    )
    return render_template(
        "admin_user_created.html", slug=user["slug"], pin=pin,
        full_name=user["full_name"], reset=True,
    )
