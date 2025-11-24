# class for models (declerative_base)


# this is used to create the base class for all ORM models
# app/db/base.py

from sqlalchemy.ext.declarative import declarative_base

Base = declarative_base()