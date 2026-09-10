from urllib.parse import unquote, urlsplit

import pytest
from sqlalchemy.engine import make_url

from app.core.config import Settings


@pytest.mark.parametrize("property_name", ["db_async_url", "db_sync_url", "rabbitmq_url"])
def test_connection_urls_preserve_special_characters_in_credentials(property_name: str) -> None:
    config = Settings(
        _env_file=None,
        POSTGRES_USER="test@user",
        POSTGRES_PASSWORD="fake:p@ss/word%#",
        rabbitmq_user="test@user",
        rabbitmq_password="fake:p@ss/word%#",
    )
    value = getattr(config, property_name)
    if property_name == "rabbitmq_url":
        parsed = urlsplit(value)
        assert unquote(parsed.username) == "test@user"
        assert unquote(parsed.password) == "fake:p@ss/word%#"
        assert parsed.hostname == "rabbitmq"
    else:
        parsed = make_url(value)
        assert parsed.username == "test@user"
        assert parsed.password == "fake:p@ss/word%#"
        assert parsed.host == "db"
