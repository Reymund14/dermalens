"""Brings an existing database up to date without a migration tool.

create_all() adds new tables but never new columns on old tables, so a
database created by an earlier version would miss them. This adds any
missing nullable or defaulted column. It never drops or changes anything.
Run: python -m app.schema_upgrade (start.sh does this on every start)."""
from __future__ import annotations

from sqlalchemy import inspect, text

from . import models  # noqa: F401  (registers every table)
from .db import Base, engine

# Columns added after the first release, with the default existing rows get.
ADDED = {
    "users": {"email_verified_at": None, "failed_logins": "0", "locked_until": None},
}


def upgrade() -> list[str]:
    Base.metadata.create_all(engine)
    done = []
    insp = inspect(engine)
    with engine.begin() as conn:
        for table, cols in ADDED.items():
            have = {c["name"] for c in insp.get_columns(table)}
            for name, default in cols.items():
                if name in have:
                    continue
                col = Base.metadata.tables[table].c[name]
                ddl = f"ALTER TABLE {table} ADD COLUMN {name} {col.type.compile(engine.dialect)}"
                if default is not None:
                    ddl += f" NOT NULL DEFAULT {default}"
                conn.execute(text(ddl))
                done.append(f"{table}.{name}")
                if (table, name) == ("users", "email_verified_at"):
                    # Staff and admin accounts were made by an admin: count them as verified.
                    conn.execute(text("UPDATE users SET email_verified_at = created_at WHERE role <> 'patient'"))
    return done


if __name__ == "__main__":
    added = upgrade()
    print("schema up to date" + (f"; added {', '.join(added)}" if added else ""))
