"""``PinealExecutor._execute_with_timeout`` — imza pazarlığı sözleşmesi.

[AUDIT 2026-10-07 · Madde 5] Ölçülen kusur::

    try:
        return await agent.execute(input_data, memory, gateway)
    except TypeError:
        return await agent.execute(input_data)      # <-- İKİNCİ KOŞU

``TypeError`` yalnızca "yanlış argüman sayısı" demek DEĞİLDİR; ajanın
gövdesindeki gerçek bir hatadan da gelir. Eski kod bu durumda ajanı
yeniden koşturuyordu:

  * **Yan etki tekrarı:** ücretli LLM çağrıları / ağ istekleri / kanıt
    yazımları bir kez daha tetikleniyordu.
  * **Hata maskeleme:** gerçek hata kayboluyor, yerine "execute() missing 2
    required positional arguments" gibi aldatıcı bir mesaj geliyordu.

Yeni sözleşme: imza ``inspect.signature`` ile ÇAĞIRMADAN okunur, ajan TAM
BİR KEZ koşar, gövdeden gelen ``TypeError`` olduğu gibi yükselir.
"""

from __future__ import annotations

import asyncio

import pytest

from agent_core.task_executor import PinealExecutor


# ─────────────────────────────────────────────────────────────────────────
# Denek ajanlar
# ─────────────────────────────────────────────────────────────────────────


class ThreeArgAgent:
    """Tam imzalı ajan: ``(input_data, memory, gateway)``."""

    def __init__(self):
        self.calls: list[tuple] = []

    async def execute(self, input_data, memory, gateway):
        self.calls.append((input_data, memory, gateway))
        return {"ok": True}


class OneArgAgent:
    """Yalnızca ``input_data`` alan ajan (repo'da 8 ajan böyle)."""

    def __init__(self):
        self.calls: list[tuple] = []

    async def execute(self, input_data):
        self.calls.append((input_data,))
        return {"ok": True}


class DefaultedAgent:
    """``(input_data, memory=None, gateway=None)`` — 3 konumsal parametre."""

    def __init__(self):
        self.calls: list[tuple] = []

    async def execute(self, input_data, memory=None, gateway=None):
        self.calls.append((input_data, memory, gateway))
        return {"ok": True}


class VarArgsAgent:
    """``(*args)`` — her iki çağrı biçimini de yer."""

    def __init__(self):
        self.calls: list[tuple] = []

    async def execute(self, *args):
        self.calls.append(args)
        return {"ok": True}


class BodyTypeErrorAgent(ThreeArgAgent):
    """Tam imzalı ama GÖVDESİNDE gerçek bir ``TypeError`` fırlatır.

    Eski kodda bu, ajanın İKİNCİ KEZ (ve yanlış argümanlarla) koşmasına
    yol açıyordu.
    """

    async def execute(self, input_data, memory, gateway):
        self.calls.append((input_data, memory, gateway))
        # Gerçek bir gövde hatası: imzayla İLGİSİ YOK.
        # `.get` bilinçli: KeyError değil, tip hatası üretmek istiyoruz.
        payload = input_data.get("missing_key")
        return payload + 1  # None + 1 -> TypeError


class SignaturelessAgent:
    """``inspect.signature`` okuyamaz (C uzantısı benzeri)."""

    def __init__(self):
        self.calls: list[tuple] = []

    def __getattr__(self, name):
        if name == "execute":
            raise AttributeError(name)
        raise AttributeError(name)


def _run(agent, limit: float = 0) -> asyncio.Future:
    """``_execute_with_timeout`` çağrısı (limit 0 = süre sınırı yok)."""
    return PinealExecutor._execute_with_timeout(
        agent, {"x": 1}, "MEMORY", "GATEWAY", limit
    )


# ─────────────────────────────────────────────────────────────────────────
# 1) Doğru imzayla TEK çağrı
# ─────────────────────────────────────────────────────────────────────────


def test_three_arg_agent_receives_all_arguments_once():
    agent = ThreeArgAgent()
    result = asyncio.run(_run(agent))

    assert result == {"ok": True}
    assert agent.calls == [({"x": 1}, "MEMORY", "GATEWAY")], (
        f"tam imzalı ajan tam argüman almalı ve BİR kez çağrılmalı: {agent.calls}"
    )


def test_one_arg_agent_receives_only_input_data_once():
    agent = OneArgAgent()
    result = asyncio.run(_run(agent))

    assert result == {"ok": True}
    assert agent.calls == [({"x": 1},)], (
        f"tek argümanlı ajan yalnızca input_data almalı ve BİR kez çağrılmalı: {agent.calls}"
    )


def test_defaulted_signature_is_treated_as_full():
    agent = DefaultedAgent()
    asyncio.run(_run(agent))
    assert agent.calls == [({"x": 1}, "MEMORY", "GATEWAY")]


def test_varargs_signature_is_treated_as_full():
    agent = VarArgsAgent()
    asyncio.run(_run(agent))
    assert agent.calls == [({"x": 1}, "MEMORY", "GATEWAY")]


def test_unreadable_signature_falls_back_to_full_call():
    """İmza okunamazsa baskın sözleşme (tam imza) denenir — ajan 1 kez koşar."""

    class Exotic:
        def __init__(self):
            self.calls = []

        async def execute(self, input_data, memory, gateway):
            self.calls.append((input_data, memory, gateway))
            return {"ok": True}

    exotic = Exotic()
    assert PinealExecutor._agent_takes_full_signature(exotic) is True


# ─────────────────────────────────────────────────────────────────────────
# 2) KRİTİK: gövde hatasında İKİNCİ KOŞU YOK
# ─────────────────────────────────────────────────────────────────────────


def test_body_type_error_does_not_trigger_a_second_call():
    """[AUDIT] Eski kod burada ajanı İKİNCİ KEZ koşturuyordu."""
    agent = BodyTypeErrorAgent()

    with pytest.raises(TypeError):
        asyncio.run(_run(agent))

    assert len(agent.calls) == 1, (
        f"ajan {len(agent.calls)} kez koştu! Gövde hatası ikinci (ve yan "
        "etkili) bir koşuyu tetiklememeli."
    )


def test_body_type_error_is_not_masked_by_an_argument_message():
    """Gerçek hata mesajı kaybolmamalı: 'missing ... positional argument' olmamalı."""
    agent = BodyTypeErrorAgent()

    with pytest.raises(TypeError) as excinfo:
        asyncio.run(_run(agent))

    message = str(excinfo.value)
    assert "positional argument" not in message, (
        "hata MASKELENMİŞ: gövde hatası yerine argüman-sayısı hatası geliyor "
        f"(ajan ikinci kez koşturulmuş): {message}"
    )
    # Orijinal hata (None + 1) görünür olmalı.
    assert "NoneType" in message or "unsupported operand" in message, (
        f"orijinal gövde hatası yüzeye çıkmadı: {message}"
    )


def test_no_second_invocation_is_ever_attempted():
    """ÇAĞRI sayısını (gövdeye girişi değil) sayan denek.

    Neden ayrı bir denek: bağlama (binding) hataları gövdeye GİRMEDEN
    oluşur. Bu yüzden gövdeye sayaç koyan bir ajan, eski kodun ikinci
    koşusunu göremez. Burada ``execute`` gerçek bir fonksiyon değil,
    çağrılabilir bir NESNEDİR; her çağrı denemesi — argüman bağlama
    başarısız olsa bile — kaydedilir.
    """

    class InvocationCountingAgent:
        def __init__(self):
            self.invocations: list[tuple] = []

        class _Execute:
            def __init__(self, owner):
                self.owner = owner

            def __call__(self, *args):
                self.owner.invocations.append(args)
                raise TypeError("gövde hatası: NoneType + int")

        def __init_subclass__(cls, **kwargs):  # pragma: no cover - koruma
            super().__init_subclass__(**kwargs)

        @property
        def execute(self):
            return self._Execute(self)

    agent = InvocationCountingAgent()

    with pytest.raises(TypeError):
        asyncio.run(_run(agent))

    assert len(agent.invocations) == 1, (
        f"execute {len(agent.invocations)} kez ÇAĞRILDI: {agent.invocations}. "
        "Gövde hatasından sonra ikinci bir koşu denenmemeli "
        "(yan etki tekrarı + hata maskeleme)."
    )


def test_body_type_error_in_a_one_arg_agent_is_also_not_retried():
    """Tek argümanlı ajanda da gövde hatası tek koşuyla yükselmeli."""

    class OneArgBoom:
        def __init__(self):
            self.calls = 0

        async def execute(self, input_data):
            self.calls += 1
            raise TypeError("gövde hatası: beklenmeyen tip")

    agent = OneArgBoom()
    with pytest.raises(TypeError, match="gövde hatası"):
        asyncio.run(_run(agent))

    assert agent.calls == 1, f"ajan {agent.calls} kez koştu; beklenen 1"


def test_non_typeerror_is_never_retried_either():
    """Diğer istisnalar da tek koşuyla yükselir (regresyon koruması)."""

    class Boom:
        def __init__(self):
            self.calls = 0

        async def execute(self, input_data, memory, gateway):
            self.calls += 1
            raise ValueError("boom")

    agent = Boom()
    with pytest.raises(ValueError, match="boom"):
        asyncio.run(_run(agent))
    assert agent.calls == 1


# ─────────────────────────────────────────────────────────────────────────
# 3) Sözleşmenin kaynakta da korunması
# ─────────────────────────────────────────────────────────────────────────


def test_source_contains_no_typeerror_recall():
    """Kaynakta 'except TypeError' ile ikinci koşu kalmadığının statik kanıtı.

    Yalnızca YORUM DIŞI kod satırları taranır; bu dosyanın kendi docstring'i
    eski kusurlu kodu alıntıladığı için ham tarama yanlış pozitif verirdi.
    """
    import ast
    from pathlib import Path

    source = Path("agent_core/task_executor.py").read_text(encoding="utf-8")
    tree = ast.parse(source)

    offenders = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Try):
            continue
        for handler in node.handlers:
            # `except TypeError:` korusunun İÇİNDE yeni bir execute çağrısı var mı?
            if not isinstance(handler.type, ast.Name) or handler.type.id != "TypeError":
                continue
            for inner in ast.walk(ast.Module(body=handler.body, type_ignores=[])):
                if (
                    isinstance(inner, ast.Call)
                    and isinstance(inner.func, ast.Attribute)
                    and inner.func.attr == "execute"
                ):
                    offenders.append(ast.unparse(node)[:200])

    assert not offenders, (
        "gövde-tavanı değil: 'except TypeError' içinde execute() YENİDEN çağrılıyor "
        f"(yan etki tekrarı kusuru geri gelmiş): {offenders}"
    )
