"""Gerçek PostgreSQL bağlantısı için entegrasyon testi."""

from sqlalchemy import text

from app.db.session import engine


def test_postgresql_connection() -> None:
    with engine.connect() as connection:
        result = connection.execute(text("SELECT 1"))
        assert result.scalar_one() == 1
