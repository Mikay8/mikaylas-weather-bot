import os

from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

load_dotenv()


def get_engine():
    database_url = os.environ["DATABASE_URL"]
    return create_engine(database_url, pool_pre_ping=True)


_engine = None
_Session = None


def get_session():
    global _engine, _Session
    if _Session is None:
        _engine = get_engine()
        _Session = sessionmaker(bind=_engine)
    return _Session()
