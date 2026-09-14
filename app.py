import os

import click
from flask import Flask, render_template
from werkzeug.security import generate_password_hash

import db
from config import Config
from public_routes import public_bp
from admin_routes import admin_bp


def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)

    db.init_app(app)

    app.register_blueprint(public_bp)
    app.register_blueprint(admin_bp)

    @app.context_processor
    def inject_globals():
        return {"site_name": app.config["SITE_NAME"]}

    @app.errorhandler(404)
    def not_found(_e):
        return render_template("404.html"), 404

    @app.cli.command("init-db")
    def init_db_command():
        """Crea las tablas en Turso/sqlite si no existen. Uso: flask init-db"""
        with app.app_context():
            db.init_schema()
        click.echo("Base de datos inicializada correctamente.")

    @app.cli.command("create-admin")
    @click.argument("username")
    @click.argument("password")
    def create_admin_command(username, password):
        """Crea (o resetea la contraseña de) el usuario administrador.
        Uso: flask create-admin admin "una-contraseña-segura"
        """
        with app.app_context():
            existing = db.query_one("SELECT id FROM admins WHERE username = ?", [username])
            if existing:
                db.execute(
                    "UPDATE admins SET password_hash = ? WHERE username = ?",
                    [generate_password_hash(password), username],
                )
                click.echo(f"Contraseña actualizada para el admin '{username}'.")
            else:
                db.execute(
                    "INSERT INTO admins (username, password_hash) VALUES (?, ?)",
                    [username, generate_password_hash(password)],
                )
                click.echo(f"Admin '{username}' creado correctamente.")

    return app


app = create_app()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8081))
    app.run(host="0.0.0.0", port=port, debug=True)
