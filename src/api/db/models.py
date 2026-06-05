"""SQLAlchemy ORM models"""

from sqlalchemy import String, Text, func
from sqlalchemy.orm import DeclarativeBase, Mapped, MappedAsDataclass, mapped_column


class Base(DeclarativeBase):
    pass


class DeveloperFile(MappedAsDataclass, Base):
    __tablename__ = "developer_files"

    download_url: Mapped[str] = mapped_column(String, unique=True)
    developer_name: Mapped[str | None] = mapped_column(Text, default=None)
    title: Mapped[str | None] = mapped_column(Text, default=None)
    regon: Mapped[str | None] = mapped_column(String(14), default=None)
    file_format: Mapped[str | None] = mapped_column(String(20), default=None)
    institution_city: Mapped[str | None] = mapped_column(
        String, default=None, index=True
    )
    data_date: Mapped[str | None] = mapped_column(String(10), default=None)
    dataset_url: Mapped[str | None] = mapped_column(Text, default=None)

    id: Mapped[int] = mapped_column(primary_key=True, init=False)
    first_seen_at: Mapped[str] = mapped_column(server_default=func.now(), init=False)
    last_seen_at: Mapped[str] = mapped_column(server_default=func.now(), init=False)
