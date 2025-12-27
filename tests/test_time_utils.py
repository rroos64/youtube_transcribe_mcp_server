from datetime import datetime

from domain.time_utils import parse_iso_timestamp


def test_parse_iso_timestamp_handles_none_and_invalid():
    assert parse_iso_timestamp(None) is None
    assert parse_iso_timestamp("") is None
    assert parse_iso_timestamp("not-a-date") is None


def test_parse_iso_timestamp_accepts_z_suffix():
    value = parse_iso_timestamp("2024-01-01T12:00:00Z")
    assert isinstance(value, datetime)
    assert value.isoformat() == "2024-01-01T12:00:00"


def test_parse_iso_timestamp_accepts_plain_iso():
    value = parse_iso_timestamp("2024-01-01T12:00:00")
    assert isinstance(value, datetime)
    assert value.isoformat() == "2024-01-01T12:00:00"
