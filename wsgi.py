"""Adaptateur WSGI pour les hebergeurs sans support ASGI (PythonAnywhere...).

Sur PythonAnywhere, l'onglet Web attend un fichier WSGI. Copier le contenu de
ce fichier dans le fichier WSGI du compte, ou l'y importer :

    import sys
    sys.path.insert(0, "/home/<compte>/team-belote-re")
    from wsgi import application

FastAPI etant une application ASGI, `a2wsgi` fait la conversion :

    pip3 install --user a2wsgi

Limite a connaitre : les WebSockets ne passent pas par WSGI. L'interface le
detecte automatiquement et bascule sur une interrogation periodique
(voir PERIODE_SONDAGE dans web/app.js) : la synchronisation entre tables
reste assuree, avec quelques secondes de latence.
"""

from __future__ import annotations

import os
from pathlib import Path

BASE = Path(__file__).resolve().parent

# Ces variables peuvent aussi etre placees dans un fichier .env a la racine.
os.environ.setdefault("TBR_DATABASE_URL", f"sqlite:///{BASE / 'data' / 'tbr.db'}")
os.environ.setdefault("TBR_SECRET_KEY", "")  # a definir imperativement en production

if not os.environ.get("TBR_SECRET_KEY"):
    raise RuntimeError(
        "TBR_SECRET_KEY doit etre definie (48 caracteres aleatoires) "
        "avant de servir l'application."
    )

(BASE / "data").mkdir(parents=True, exist_ok=True)

from a2wsgi import ASGIMiddleware  # noqa: E402
from tbr.db import init_db  # noqa: E402
from tbr.main import app, bootstrap_admin  # noqa: E402

init_db()
bootstrap_admin()

application = ASGIMiddleware(app)
