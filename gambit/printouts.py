"""Words on the printouts that go home: account cards, class card sets and the Welcome sheet –
in English, Spanish, or both on the same page. Every phrase can be reworded (Settings →
Appearance and safety → Printouts), per language.

Placeholders like {name} are filled with plain replacement – never str.format – so wording
typed by a person can't reach into Python objects.
"""

from __future__ import annotations

import html
import json

from .settings import settings

LANGS = {"en": "English", "es": "Español (Spanish)", "both": "English and Spanish"}
LANG_KEY = "printouts/lang"
WORDING_KEY = "printouts/wording"           # {lang: {key: text}}

# (key, what it is, English, Spanish). Short labels sit side by side when printing both
# languages ("Email / Correo electrónico"); sentences go on their own line.
PHRASES = [
    ("email", "label", "Email", "Correo electrónico"),
    ("temp_password", "label", "Temporary password", "Contraseña temporal"),
    ("password", "label", "Password", "Contraseña"),
    ("chromebook", "label", "Chromebook", "Chromebook"),
    ("school", "label", "School", "Escuela"),
    ("choose_own", "sentence", "You'll choose your own password when you sign in.",
     "Elegirás tu propia contraseña cuando inicies sesión."),
    ("card_signin", "sentence", "Sign in at accounts.google.com – or scan the code.",
     "Inicia sesión en accounts.google.com o escanea el código."),
    ("cards_title", "label", "Google sign-in", "Inicio de sesión de Google"),
    ("cards_signin", "sentence", "Sign in at accounts.google.com",
     "Inicia sesión en accounts.google.com"),
    ("cards_count", "label", "{n} card(s)", "{n} tarjeta(s)"),
    ("family_note", "sentence",
     "For families: this is your child's school Google account. Help them sign in at "
     "accounts.google.com with the email and password above, and please keep the password "
     "private. Questions? Contact your child's school.",
     "Para las familias: esta es la cuenta escolar de Google de su hijo o hija. Ayúdele a "
     "iniciar sesión en accounts.google.com con el correo electrónico y la contraseña de "
     "arriba, y por favor mantenga la contraseña en privado. ¿Preguntas? Comuníquese con la "
     "escuela de su hijo o hija."),
    ("welcome_title", "title", "Welcome, {name}!", "¡Le damos la bienvenida, {name}!"),
    ("welcome_ready", "sentence", "Your Google Workspace account is ready.",
     "Su cuenta de Google Workspace está lista."),
    ("welcome_user", "label", "Email / username", "Correo electrónico / usuario"),
    ("welcome_signin_at", "label", "Sign in at", "Inicie sesión en"),
    ("step_go", "sentence", "Go to accounts.google.com and sign in with the email above.",
     "Vaya a accounts.google.com e inicie sesión con el correo electrónico de arriba."),
    ("step_type", "sentence", "Type the temporary password.",
     "Escriba la contraseña temporal."),
    ("step_choose", "sentence", "Choose a new password you'll remember. Don't share it.",
     "Elija una contraseña nueva que pueda recordar. No la comparta con nadie."),
    ("step_apps", "sentence",
     "Open Gmail, Drive and Classroom from the app grid (the 9 dots, top right).",
     "Abra Gmail, Drive y Classroom desde el menú de aplicaciones (los 9 puntos, arriba a la "
     "derecha)."),
    ("keep_safe", "sentence",
     "Keep this sheet somewhere safe, or shred it once you've signed in.",
     "Guarde esta hoja en un lugar seguro, o destrúyala después de iniciar sesión."),
]
KIND = {k: kind for k, kind, _en, _es in PHRASES}
DEFAULT = {"en": {k: en for k, _kind, en, _es in PHRASES},
           "es": {k: es for k, _kind, _en, es in PHRASES}}


def default_lang() -> str:
    v = settings.get(LANG_KEY, "en") or "en"
    return v if v in LANGS else "en"


def set_default_lang(lang: str):
    settings.set(LANG_KEY, lang if lang in LANGS else "en")


def custom() -> dict:
    try:
        d = json.loads(settings.get(WORDING_KEY, "") or "{}")
        return d if isinstance(d, dict) else {}
    except ValueError:
        return {}


def save_custom(d: dict):
    clean = {}
    for lang in ("en", "es"):
        clean[lang] = {k: str(v)[:600] for k, v in (d.get(lang) or {}).items()
                       if k in KIND and str(v).strip() and str(v) != DEFAULT[lang][k]}
    settings.set(WORDING_KEY, json.dumps(clean))


def phrase(key: str, lang: str, **values) -> str:
    """One phrase in one language (en/es), with your wording if you changed it."""
    text = (custom().get(lang) or {}).get(key) or DEFAULT[lang][key]
    for k, v in values.items():
        text = text.replace("{" + k + "}", str(v))
    return text


def t(key: str, lang: str, **values) -> str:
    """HTML for a phrase in the chosen language – for 'both', English then Spanish."""
    esc = html.escape
    if lang != "both":
        return esc(phrase(key, lang if lang in ("en", "es") else "en", **values))
    en, es = phrase(key, "en", **values), phrase(key, "es", **values)
    if en == es:
        return esc(en)
    if KIND[key] == "label":
        return f"{esc(en)} / <i>{esc(es)}</i>"
    return f"{esc(en)}<br><i>{esc(es)}</i>"


def lang_combo(current: str | None = None):
    from PySide6.QtWidgets import QComboBox
    c = QComboBox()
    for k, label in LANGS.items():
        c.addItem(label, k)
    c.setCurrentIndex(max(0, c.findData(current or default_lang())))
    return c
