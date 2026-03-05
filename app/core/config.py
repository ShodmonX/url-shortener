from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    debug: bool
    
    database_user: str
    database_password: str
    database_host: str
    database_port: int
    database_db: str 

    redis_host: str
    redis_port: int
    redis_db: int

    model_config = SettingsConfigDict(env_file='.env', extra='ignore')

    @property
    def db_async_url(self):
        return f"postgres+asyncpg://{self.database_user}:{self.database_password}@{self.database_host}:{self.database_port}/{self.database_db}"
    
    @property
    def db_sync_url(self):
        return f"postgres+psycopg://{self.database_user}:{self.database_password}@{self.database_host}:{self.database_port}/{self.database_db}"
    
    @property
    def redis_url(self):
        return f"redis://{self.redis_host}:{self.redis_port}/{self.redis_db}"
    

@lru_cache
def get_settings():
    return Settings()  # pyright: ignore[reportCallIssue]

settings = get_settings()