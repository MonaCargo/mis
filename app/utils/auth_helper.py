
import os
from datetime import datetime, timedelta
import jwt
from passlib.context import CryptContext
from dotenv import load_dotenv

# Load environment variables from .env
load_dotenv()

# Get secret key from environment
SECRET_KEY = os.getenv("JWT_SECRET_KEY")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 43200 # 30 days

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")



def hash_password(password: str) -> str:
    print(f"Password: {password}")
    print(f"Password length (chars): {len(password)}")
    
    password_bytes = password.encode('utf-8')
    print(f"Password bytes: {password_bytes}")
    print(f"Password length (bytes): {len(password_bytes)}")
    
    try:
        result = pwd_context.hash(password)
        print("Hash successful!")
        return result
    except Exception as e:
        print(f"Hash failed: {e}")
        print(f"Error type: {type(e)}")
        raise

def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)

def create_access_token(data: dict, expires_delta: timedelta | None = None) -> str:
    to_encode = data.copy()
    expire = datetime.utcnow() + (expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

def decode_access_token(token: str) -> dict | None:
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        print(f"Decoded JWT payload: {payload}")
        return payload
    except jwt.ExpiredSignatureError:
        return None
    except jwt.InvalidTokenError:
        return None
