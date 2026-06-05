"""Abstract base repository"""

from abc import ABC, abstractmethod

from sqlalchemy.orm import Session


class BaseRepository[T](ABC):
    def __init__(self, session: Session) -> None:
        self._session = session

    @abstractmethod
    def insert_or_ignore(self, record: T) -> None: ...

    @abstractmethod
    def insert_or_ignore_batch(self, records: list[T]) -> int: ...
