import pytest
from pydantic import TypeAdapter, ValidationError

from app.models import Address, Hash32, HexData, HexQuantity, PackedUserOperation


@pytest.mark.unit
@pytest.mark.parametrize(
    "value,expected",
    [("0x0", "0x0"), ("0x1A", "0x1a"), ("0xffff", "0xffff")],
)
def test_hex_quantity_accepts_canonical_values(value, expected):
    assert TypeAdapter(HexQuantity).validate_python(value) == expected


@pytest.mark.unit
@pytest.mark.parametrize("value", ["0x", "0x00", "0x01", "1", "0xzz"])
def test_hex_quantity_rejects_noncanonical_values(value):
    with pytest.raises(ValidationError):
        TypeAdapter(HexQuantity).validate_python(value)


@pytest.mark.unit
@pytest.mark.parametrize("value", ["0x", "0x00", "0xdeadBEEF"])
def test_hex_data_accepts_complete_bytes(value):
    assert TypeAdapter(HexData).validate_python(value) == value.lower()


@pytest.mark.unit
@pytest.mark.parametrize("value", ["0x0", "deadbeef", "0xgg"])
def test_hex_data_rejects_invalid_bytes(value):
    with pytest.raises(ValidationError):
        TypeAdapter(HexData).validate_python(value)


@pytest.mark.unit
def test_address_and_hash_normalize_case():
    address = "0x" + "AB" * 20
    digest = "0x" + "CD" * 32
    assert TypeAdapter(Address).validate_python(address) == address.lower()
    assert TypeAdapter(Hash32).validate_python(digest) == digest.lower()


@pytest.mark.unit
@pytest.mark.parametrize("digest", ["0x", "0x" + "00" * 31, "0x" + "00" * 33])
def test_hash_requires_exactly_32_bytes(digest):
    with pytest.raises(ValidationError, match="32-byte"):
        TypeAdapter(Hash32).validate_python(digest)


@pytest.mark.unit
def test_packed_user_operation_round_trips_bundler_aliases(operation_payload):
    operation = PackedUserOperation.model_validate(operation_payload)
    assert operation.model_dump(by_alias=True) == operation_payload

