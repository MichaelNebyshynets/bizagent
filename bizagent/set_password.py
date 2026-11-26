"""Set a password for an existing PostgreSQL account from a local terminal."""

import argparse
from contextlib import closing
from getpass import getpass

import psycopg2

from app.auth import hash_password
from app.config import Settings


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("email")
    args = parser.parse_args()
    password = getpass("Новый пароль (12–128 символов): ")
    if not 12 <= len(password) <= 128:
        parser.exit(1, "Пароль должен быть длиной от 12 до 128 символов.\n")
    if password != getpass("Повторите пароль: "):
        parser.exit(1, "Пароли не совпадают.\n")

    with closing(psycopg2.connect(Settings.from_env().database_url)) as conn, conn, conn.cursor() as cur:
        cur.execute(
            "UPDATE users SET password_hash = %s, session_version = session_version + 1 WHERE LOWER(email) = %s",
            (hash_password(password), args.email.strip().lower()),
        )
        if cur.rowcount != 1:
            raise SystemExit("Нужен один существующий аккаунт с этим email. Изменения отменены.")
    print("Пароль сохранён.")


if __name__ == "__main__":
    main()
