from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field, model_validator
from urllib.parse import urlsplit


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="RAILSYNC_", extra="ignore")
    database_url: str = "postgresql+psycopg://railsync:railsync@127.0.0.1:55432/railsync"
    environment: str = "development"
    browser_origins: list[str] = Field(default_factory=lambda: ['https://localhost:3000'])
    session_cookie_secure: bool = True
    session_ttl_minutes: int = Field(default=480, ge=5, le=1440)

    @model_validator(mode='after')
    def browser_security(self):
        if not self.browser_origins:
            raise ValueError('At least one explicit browser origin is required')
        for origin in self.browser_origins:
            url = urlsplit(origin)
            if (url.username or url.password or url.path or url.query or url.fragment
                    or not url.hostname or url.scheme not in ('http', 'https')):
                raise ValueError('Browser origins must be exact HTTP(S) origins without paths')
            local = url.hostname in ('localhost', '127.0.0.1', '[::1]', '::1')
            if url.scheme != 'https' and (self.session_cookie_secure
                    or self.environment not in ('development', 'test') or not local):
                raise ValueError('HTTP browser origins require explicit local development mode')
        if not self.session_cookie_secure and (self.environment not in ('development', 'test')
                or any(urlsplit(o).hostname not in ('localhost', '127.0.0.1', '::1')
                    for o in self.browser_origins)):
            raise ValueError('Insecure cookies are restricted to loopback development origins')
        return self


@lru_cache
def settings():
    return Settings()
