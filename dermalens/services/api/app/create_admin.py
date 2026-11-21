"""Create (or reset) an admin account.

    python -m app.create_admin admin@yourclinic.ph "Full Name"        # asks for the password
    ADMIN_PASSWORD=... python -m app.create_admin admin@yourclinic.ph "Full Name"
"""
from __future__ import annotations

import getpass
import os
import sys

from . import models as M
from .db import SessionLocal
from .security import hash_password


def main() -> None:
    if len(sys.argv) < 2:
        raise SystemExit(__doc__)
    email = sys.argv[1].lower()
    name = sys.argv[2] if len(sys.argv) > 2 else "Admin"
    pw = os.getenv("ADMIN_PASSWORD") or getpass.getpass("Password (at least 10 characters): ")
    if len(pw) < 10:
        raise SystemExit("password must be at least 10 characters")
    with SessionLocal() as db:
        u = db.query(M.User).filter_by(email=email).first()
        if u is None:
            u = M.User(email=email, role="admin", email_verified_at=M.now())
            db.add(u)
        u.role, u.display_name, u.password_hash, u.disabled_at = "admin", name, hash_password(pw), None
        db.commit()
    print(f"admin ready: {email}")


if __name__ == "__main__":
    main()
