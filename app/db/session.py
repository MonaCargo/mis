# # Session and enginemaker





# from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession

# from sqlalchemy.orm import sessionmaker

# import os

# from dotenv import load_dotenv

# load_dotenv()

# # DATABASE_URL = f"postgresql+asyncpg://{os.getenv('POSTGRES_USER')}:{os.getenv('POSTGRES_PASSWORD')}@{os.getenv('POSTGRES_HOST')}:{os.getenv('POSTGRES_PORT')}/{os.getenv('POSTGRES_DB')}"

# # DATABASE_URL = "postgresql+asyncpg://postgres:dcsc@191.168.75.199:5432/cosys_test_postgresql"
# # DATABASE_URL_FOR_ALEMBIC_MIGRATION_SYNCDB = "postgresql://postgres:dcsc@191.168.75.199:5432/cosys_test_postgresql"
# # DATABASE_URL = "postgresql+asyncpg://postgres:dcsc@192.168.0.56:5432/cosys_test_postgresql"
# # DATABASE_URL_FOR_ALEMBIC_MIGRATION_SYNCDB = "postgresql://postgres:dcsc@192.168.0.56:5432/cosys_test_postgresql"
# DATABASE_URL = "postgresql+asyncpg://postgres:dcsc@localhost:5432/cosys_test_postgresql"
# DATABASE_URL_FOR_ALEMBIC_MIGRATION_SYNCDB = "postgresql://postgres:dcsc@localhost:5432/cosys_test_postgresql"

# engine = create_async_engine(DATABASE_URL,
#                              pool_pre_ping=True,  # Check connection before using
#     pool_recycle=300,    # Recycle connections every 5 minutes
#     pool_timeout=60,     # Timeout for getting connection
#     max_overflow=20,     # Allow extra connections
#     pool_size=10    ,     # Base pool size
#     # echo=True)                            
#     echo = False)  

# async_session = sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)

# async def get_db():
#     print("DATABASE_URL:", DATABASE_URL)


#     async with async_session() as session:

#         yield session





























# Session and enginemaker





from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
import os
from dotenv import load_dotenv

load_dotenv()

def get_env_variable(name: str) -> str:
    """Get environment variable or raise error if missing."""
    value = os.getenv(name)
    if not value:
        raise EnvironmentError(f"Missing environment variable: {name}")
    return value

# Build database URLs from environment variables
DATABASE_URL = (
    f"postgresql+asyncpg://{get_env_variable('POSTGRES_USER')}:"
    f"{get_env_variable('POSTGRES_PASSWORD')}@"
    f"{get_env_variable('POSTGRES_HOST')}:"
    f"{get_env_variable('POSTGRES_PORT')}/"
    f"{get_env_variable('POSTGRES_DB')}"
)

DATABASE_URL_FOR_ALEMBIC_MIGRATION_SYNCDB = (
    f"postgresql://{get_env_variable('POSTGRES_USER')}:"
    f"{get_env_variable('POSTGRES_PASSWORD')}@"
    f"{get_env_variable('POSTGRES_HOST')}:"
    f"{get_env_variable('POSTGRES_PORT')}/"
    f"{get_env_variable('POSTGRES_DB')}"
)

# Create async engine
engine = create_async_engine(
    DATABASE_URL,
    pool_pre_ping=True,      # Check connection before using
    pool_recycle=300,        # Recycle connections every 5 minutes
    pool_timeout=60,         # Timeout for getting connection
    max_overflow=20,         # Allow extra connections
    pool_size=10,            # Base pool size
    echo=False               # Set to True for SQL query logging
)

# Create session factory
async_session = sessionmaker(
    bind=engine, 
    class_=AsyncSession, 
    expire_on_commit=False
)

async def get_db():
    """Dependency for FastAPI to get database session."""
    print("DATABASE_URL:", DATABASE_URL)
    async with async_session() as session:
        yield session