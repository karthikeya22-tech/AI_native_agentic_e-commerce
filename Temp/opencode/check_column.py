from sqlalchemy import text

from app.db.session import engine

with engine.connect() as conn:
    row = conn.execute(
        text(
            "SELECT column_name, udt_name "
            "FROM information_schema.columns "
            "WHERE table_name = 'products' AND column_name = 'embedding'"
        )
    ).fetchone()
    print("column:", row)
