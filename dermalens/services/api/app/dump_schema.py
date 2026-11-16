"""Write migrations/001_init.sql (PostgreSQL DDL) from the ORM models.

    python -m app.dump_schema > migrations/001_init.sql
"""
from sqlalchemy.dialects import postgresql
from sqlalchemy.schema import CreateIndex, CreateTable

from . import models  # noqa: F401  (registers tables)
from .db import Base


def main() -> None:
    dialect = postgresql.dialect()
    print("-- DermaLens schema (PostgreSQL 16). Generated from app/models.py; do not edit by hand.")
    print("CREATE EXTENSION IF NOT EXISTS pgcrypto;\n")
    for table in Base.metadata.sorted_tables:
        print(str(CreateTable(table).compile(dialect=dialect)).strip() + ";\n")
        for idx in sorted(table.indexes, key=lambda i: i.name or ""):
            print(str(CreateIndex(idx).compile(dialect=dialect)).strip() + ";\n")


if __name__ == "__main__":
    main()
