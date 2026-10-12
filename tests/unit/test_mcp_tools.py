"""FAZ D · D1 — yetenek → MCP aracı türetimi (tek kaynak kuralı).

Kilitlenen iddialar:
    * Araç listesi ``CapabilityRegistry``den TÜRETİLİR; ikinci bir envanter yok.
      Deftere yetenek eklenince araç listesi kendiliğinden büyür.
    * Araç adı dönüşümü deterministiktir ve çakışma FAIL-CLOSED yakalanır.
    * Girdi şeması ya yeteneğin kendi beyanıdır ya da sözleşme varsayılanı;
      uydurma alan üretilmez.
"""

from __future__ import annotations

import pytest

from agent_core.capabilities import (
    Availability,
    BaseCapability,
    CapabilityContext,
    CapabilityKind,
    CapabilityRegistry,
    CapabilityResult,
    bootstrap,
)
from agent_core.mcp import tools as mcp_tools


class _DeclaredSchemaCapability(BaseCapability):
    """Şemasını kendi beyan eden test çifti (tek kaynak: yeteneğin kendisi)."""

    id = "test.declared.schema"
    kind = CapabilityKind.EXTRACTOR
    license = "test"
    gates = frozenset({"vault"})
    description = "Şema beyan eden test yeteneği."
    mcp_input_schema = {
        "type": "object",
        "properties": {"target": {"type": "string", "description": "hedef dil"}},
        "required": ["subject", "target"],
    }

    def availability(self) -> Availability:
        return Availability.ok()

    async def run(self, ctx: CapabilityContext) -> CapabilityResult:  # pragma: no cover
        return CapabilityResult(capability_id=self.id, available=True)


class _PlainCapability(BaseCapability):
    id = "test.plain"
    kind = CapabilityKind.ANALYZER
    license = "test"
    description = "Şemasız test yeteneği."

    def availability(self) -> Availability:
        return Availability.ok()

    async def run(self, ctx: CapabilityContext) -> CapabilityResult:  # pragma: no cover
        return CapabilityResult(capability_id=self.id, available=True)


class TestNaming:
    def test_dots_become_underscores(self):
        assert mcp_tools.tool_name_for("sensor.identity.maigret") == "sensor_identity_maigret"

    def test_real_registry_has_no_collisions(self):
        index = mcp_tools.build_tool_index(bootstrap())
        assert index["extractor_text_language"] == "extractor.text.language"
        assert index["voice_tts_local"] == "voice.tts.local"
        assert len(index) == len(bootstrap().ids())

    def test_collision_is_loud_failure_not_silent_overwrite(self):
        registry = CapabilityRegistry()
        registry.register(_PlainCapability(), replace=True)

        class _Twin(BaseCapability):
            id = "test.plain.x"  # "test_plain_x"
            kind = CapabilityKind.ANALYZER
            license = "test"

            def availability(self) -> Availability:
                return Availability.ok()

            async def run(self, ctx):  # pragma: no cover
                return CapabilityResult(capability_id=self.id, available=True)

        class _TwinDash(BaseCapability):
            id = "test.plain_x"  # "test_plain_x" — aynı ada düşer
            kind = CapabilityKind.ANALYZER
            license = "test"

            def availability(self) -> Availability:
                return Availability.ok()

            async def run(self, ctx):  # pragma: no cover
                return CapabilityResult(capability_id=self.id, available=True)

        registry.register(_Twin(), replace=True)
        registry.register(_TwinDash(), replace=True)
        with pytest.raises(ValueError) as info:
            mcp_tools.build_tool_index(registry)
        assert "çakışma" in str(info.value)
        assert "test.plain.x" in str(info.value) and "test.plain_x" in str(info.value)


class TestToolDefinitions:
    def test_every_registry_capability_becomes_a_tool(self):
        registry = bootstrap()
        tools = mcp_tools.build_tools(registry)
        assert len(tools) == len(registry.ids())
        assert {t["title"] for t in tools} == set(registry.ids())

    def test_list_is_deterministic(self):
        registry = bootstrap()
        assert mcp_tools.build_tools(registry) == mcp_tools.build_tools(registry)

    def test_order_follows_capability_ids(self):
        tools = mcp_tools.build_tools(bootstrap())
        names = [t["name"] for t in tools]
        assert names == sorted(names)

    def test_names_unique_and_mcp_safe(self):
        tools = mcp_tools.build_tools(bootstrap())
        names = [t["name"] for t in tools]
        assert len(set(names)) == len(names)
        for name in names:
            assert mcp_tools.TOOL_NAME_RE.match(name), name

    def test_gates_are_disclosed_in_description(self):
        tools = {t["title"]: t for t in mcp_tools.build_tools(bootstrap())}
        translate = tools["extractor.text.translate_local"]
        assert "ENABLE_LOCAL_TRANSLATE" in translate["description"]
        assert "vault" in translate["description"]

    def test_annotations_follow_capability_kind(self):
        tools = {t["title"]: t for t in mcp_tools.build_tools(bootstrap())}
        # Sensör dış dünyayı okur; yerel ses yerel dosya üretir.
        assert tools["sensor.identity.maigret"]["annotations"]["openWorldHint"] is True
        assert tools["voice.tts.local"]["annotations"]["readOnlyHint"] is False


class TestSchemas:
    def test_default_schema_is_subject_contract(self):
        schema = mcp_tools.default_input_schema()
        assert schema["required"] == ["subject"]
        assert schema["properties"]["subject"]["type"] == "string"
        assert schema["additionalProperties"] is False

    def test_declared_schema_is_used_and_subject_kept(self):
        schema = mcp_tools.input_schema_for(_DeclaredSchemaCapability())
        assert "target" in schema["properties"]
        assert "subject" in schema["properties"]
        assert schema["required"] == ["subject", "target"]

    def test_declared_schema_without_subject_gets_it_added(self):
        cap = _PlainCapability()
        cap.mcp_input_schema = {"properties": {"limit": {"type": "integer"}}}
        schema = mcp_tools.input_schema_for(cap)
        assert set(schema["properties"]) == {"subject", "limit"}
        assert schema["type"] == "object"

    def test_undeclared_schema_falls_back(self):
        assert mcp_tools.input_schema_for(_PlainCapability()) == mcp_tools.default_input_schema()


class TestSingleSource:
    def test_registering_a_capability_grows_the_tool_list(self):
        registry = CapabilityRegistry()
        assert mcp_tools.build_tools(registry) == []
        registry.register(_PlainCapability())
        tools = mcp_tools.build_tools(registry)
        assert [t["name"] for t in tools] == ["test_plain"]

    def test_unregistering_removes_the_tool(self):
        registry = CapabilityRegistry()
        registry.register(_PlainCapability())
        registry.unregister("test.plain")
        assert mcp_tools.build_tools(registry) == []


class TestArgumentMapping:
    def test_subject_and_params_are_separated(self):
        ctx = mcp_tools.arguments_to_context({"subject": "  hedef  ", "target": "en", "limit": 5})
        assert ctx.subject == "hedef"
        assert ctx.params == {"target": "en", "limit": 5}

    def test_meta_is_not_leaked_into_params(self):
        ctx = mcp_tools.arguments_to_context({"subject": "x", "_meta": {"a": 1}})
        assert ctx.params == {}

    def test_no_arguments_is_empty_context(self):
        ctx = mcp_tools.arguments_to_context(None)
        assert ctx.subject == "" and ctx.params == {}

    def test_matches_adapter_read_pattern(self):
        # Adaptörler `ctx.subject or ctx.params[...]` okur; eşleme birebir uyumlu olmalı.
        ctx = mcp_tools.arguments_to_context({"subject": "merhaba dünya", "target": "en"})
        text = (ctx.subject or ctx.params.get("text") or "").strip()
        target = str(ctx.params.get("target") or "en")
        assert text == "merhaba dünya" and target == "en"
