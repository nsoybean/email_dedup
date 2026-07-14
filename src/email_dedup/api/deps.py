"""FastAPI dependency helpers for database sessions."""

from collections.abc import Iterator
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.orm import Session, sessionmaker


def get_session_factory(request: Request) -> sessionmaker[Session]:
    return request.app.state.session_factory


def get_db_session(
    session_factory: Annotated[sessionmaker[Session], Depends(get_session_factory)],
) -> Iterator[Session]:
    """Yield one SQLAlchemy session per request (not a process-wide singleton).

    Opens a session, hands it to the route, then commits on success, rolls
    back on error, and always closes. The shared ``session_factory`` on
    ``app.state`` owns the engine/pool; each request still gets its own Session.
    """
    session = session_factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
