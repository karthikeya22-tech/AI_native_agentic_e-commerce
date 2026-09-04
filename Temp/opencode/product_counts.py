from app.db.session import SessionLocal
from app.models.product import Product

db = SessionLocal()
try:
    total = db.query(Product).count()
    active = db.query(Product).filter(Product.is_active.is_(True)).count()
    with_emb = (
        db.query(Product)
        .filter(Product.is_active.is_(True), Product.embedding.isnot(None))
        .count()
    )
    print(f"total={total} active={active} active_with_embedding={with_emb}")
finally:
    db.close()
