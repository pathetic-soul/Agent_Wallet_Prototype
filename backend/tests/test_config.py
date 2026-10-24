import pytest
from pydantic import ValidationError

from app.config import Settings


@pytest.mark.unit
def test_defaults_are_safe_for_local_development():
    settings = Settings(_env_file=None)
    assert settings.chain_id == 84532
    assert settings.chain_name == "Base Sepolia"
    assert settings.rpc_url is None
    assert settings.bundler_rpc_url is None
    assert settings.configured is False


@pytest.mark.unit
def test_empty_optional_values_are_normalized():
    settings = Settings(
        _env_file=None,
        rpc_url="",
        bundler_rpc_url="",
        entry_point_address="",
        wallet_factory_address="",
    )
    assert settings.rpc_url is None
    assert settings.entry_point_address is None


@pytest.mark.unit
def test_cors_origins_parse_from_comma_separated_environment(monkeypatch):
    monkeypatch.setenv("CORS_ORIGINS", "https://one.test, https://two.test")
    assert Settings(_env_file=None).cors_origins == [
        "https://one.test",
        "https://two.test",
    ]


@pytest.mark.unit
@pytest.mark.parametrize(
    "value",
    ["0x1234", "not-hex", "1111111111111111111111111111111111111111"],
)
def test_invalid_contract_addresses_are_rejected(value):
    with pytest.raises(ValidationError, match="20-byte"):
        Settings(_env_file=None, entry_point_address=value)


@pytest.mark.unit
def test_address_hex_payload_is_validated():
    with pytest.raises(ValidationError, match="valid hexadecimal"):
        Settings(
            _env_file=None,
            entry_point_address="0xzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzz",
        )


@pytest.mark.unit
def test_configured_requires_rpc_bundler_and_entry_point(configured_settings):
    assert configured_settings.configured is True
    assert configured_settings.model_copy(update={"rpc_url": None}).configured is False

