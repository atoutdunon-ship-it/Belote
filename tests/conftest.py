import os
import tempfile
from pathlib import Path

# La base de test est isolee : doit etre defini avant tout import de tbr.db.
_TMP = Path(tempfile.mkdtemp(prefix="tbr-tests-"))
os.environ.setdefault("TBR_DATABASE_URL", f"sqlite:///{_TMP / 'test.db'}")
os.environ.setdefault(
    "TBR_SECRET_KEY", "cle-de-test-uniquement-suffisamment-longue-pour-hmac-sha256"
)
os.environ.setdefault("TBR_ADMIN_PIN", "1234")
