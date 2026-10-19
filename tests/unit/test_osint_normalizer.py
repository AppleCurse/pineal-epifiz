"""Unit tests for unified OSINT normalizer / safe getter."""
import pytest
from pydantic import BaseModel
from agent_core.services.osint_normalizer import safe_osint_get, osint_to_dict


class DummyModel(BaseModel):
    name: str
    status: str
    exists: bool = True


class DummyClass:
    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)


def test_safe_osint_get_none():
    assert safe_osint_get(None, "foo") is None
    assert safe_osint_get(None, "foo", default="bar") == "bar"


def test_safe_osint_get_dict():
    d = {"name": "test_site", "exists": True}
    assert safe_osint_get(d, "name") == "test_site"
    assert safe_osint_get(d, "exists") is True
    assert safe_osint_get(d, "missing", 42) == 42


def test_safe_osint_get_pydantic():
    m = DummyModel(name="test_pydantic", status="claimed")
    assert safe_osint_get(m, "name") == "test_pydantic"
    assert safe_osint_get(m, "status") == "claimed"
    assert safe_osint_get(m, "nonexistent", "def") == "def"


def test_safe_osint_get_custom_object():
    obj = DummyClass(site="custom", domain="custom.com")
    assert safe_osint_get(obj, "site") == "custom"
    assert safe_osint_get(obj, "domain") == "custom.com"
    assert safe_osint_get(obj, "absent") is None


def test_osint_to_dict():
    assert osint_to_dict(None) == {}
    assert osint_to_dict({"a": 1}) == {"a": 1}
    m = DummyModel(name="m", status="ok")
    assert osint_to_dict(m) == {"name": "m", "status": "ok", "exists": True}
    obj = DummyClass(x=10, _private=99)
    assert osint_to_dict(obj) == {"x": 10}
