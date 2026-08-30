from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.models.user import User


class UserRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def get_by_external_subject(self, subject: str) -> User | None:
        return self._session.scalar(select(User).where(User.external_subject == subject))

    def add(self, user: User) -> None:
        self._session.add(user)
