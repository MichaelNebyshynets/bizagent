from pathlib import Path
import os
import secrets
import subprocess
import sys

root = Path("/keys")
if "--init" in sys.argv:
    for name in ("db", "jwt"):
        path = root / name
        if not path.exists():
            tmp = path.with_suffix(".tmp")
            tmp.write_text(secrets.token_urlsafe(32))
            tmp.chmod(0o444 if name == "db" else 0o600)
            tmp.replace(path)
else:
    os.environ.update(JWT_SECRET=(root/"jwt").read_text(), DATABASE_URL="host=postgres dbname=bizagent_db user=postgres password=" + (root/"db").read_text())
    subprocess.run([sys.executable, "db_init.py", "--schema", "../schema.sql"], check=True)
    os.execv(sys.executable, [sys.executable, "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0"])
