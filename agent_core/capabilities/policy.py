"""PolicyKernel — her yeteneğin geçmek zorunda olduğu güvenlik/politika kapısı.

Tek kural: **bilinmeyen kapı = ret.** Bir yetenek, çekirdeğin tanımadığı bir
kapı (gate) bildiriyorsa çalıştırılmaz; bu, "yeni bir depo eklendi, kimse
hangi kapılardan geçtiğini okumadı" senaryosunu yapısal olarak imkânsız kılar.

Kapı sözlüğü:
    ``vault``    — kasa mandalı açık olmalı (kilitliyken dış ağa çıkış yok)
    (hedef rızası diye bir kapı YOKTUR — karar mercii operatördür)
    ``budget``   — görev bütçesi aşılmamış olmalı
    ``rate``     — hız durumu biliniyor ve izin veriyor olmalı (bilinmiyorsa RET)
    ``ENABLE_*`` — env anahtarı açık olmalı (örn. ``ENABLE_MAIGRET``); anahtar
                   ``MANAGED_GATE_FLAGS`` listesinde DEĞİLSE ``unknown_gate``
                   (fail-closed): yazım hatası "sadece kapalı" gibi görünemez

Bu modül harici bağımlılık içermez ve hiçbir ortam değişkenini kendisi
okumaz: durum dışarıdan ``PolicyState`` ile verilir (test edilebilirlik +
"örtük kaynak" yasağı).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

__all__ = ["PolicyDecision", "PolicyState", "PolicyKernel", "BUILTIN_GATES", "MANAGED_GATE_FLAGS"]


#: Çekirdeğin bildiği yapısal kapılar. Bunun dışındaki her şey fail-closed reddedilir.
BUILTIN_GATES = frozenset({"vault", "budget", "rate"})

#: YÖNETİLEN env kapıları — TEK KAYNAK BURASIDIR (denetim 2026-10-14, bulgu B1/B2).
#: ``agent_core.capabilities.state`` bu listeyi yeniden ihraç eder; ikinci bir liste
#: tutmak "kapı koda yazıldı ama duruma hiç girmedi" kusurunu doğuruyordu:
#: ``ENABLE_LOCAL_TTS``/``ENABLE_LOCAL_STT`` adaptörlerde kapı olarak vardı ama
#: listede olmadığı için üretim durumu onları HİÇ taşımıyordu → yetenek
#: ``availability()=True`` derken ``PolicyKernel`` kalıcı ``gate_disabled``
#: veriyordu (iki farklı gerçek). Yeni bir ``ENABLE_*`` kapısı kullanan yetenek
#: eklenirse ADI BURAYA da yazılır; yazılmazsa çekirdek onu ``unknown_gate`` ile
#: reddeder — sessizce "kapalı" gibi görünmez.
MANAGED_GATE_FLAGS: tuple[str, ...] = (
    "ENABLE_MAIGRET",
    # [2026-10-23] Native çapraz platform yoklaması (sensor.identity.handle_probe).
    # Kapı listede olmazsa PolicyKernel onu `unknown_gate` ile reddeder ve
    # yetenek "açık" görünürken kalıcı kapalı kalır (B1/B2 dersi).
    "ENABLE_CROSS_PLATFORM",
    "ENABLE_HOLEHE",
    "ENABLE_CRAWL4AI",
    "ENABLE_SCRAPLING",
    "ENABLE_X_SENSOR",
    "ENABLE_IG_SECONDARY",
    "ENABLE_AGENT_REACH",
    "ENABLE_SEARXNG",
    # [FAZ D · D4] Çeviri yerel motora bağlıdır; varsayılan KAPALI.
    "ENABLE_LOCAL_TRANSLATE",
    # [FAZ D · D2] Yerel jüri: yerel modeller hazır olana kadar varsayılan KAPALI.
    "ENABLE_LOCAL_JURY",
    # [FAZ D · D6] Kurum hedefi: theHarvester/ağ koşusu; varsayılan KAPALI.
    "ENABLE_COMPANY_TARGETING",
    # [FAZ D · D5] Rapor fabrikası: kanıt dışa aktarımı; varsayılan KAPALI.
    "ENABLE_REPORT_FACTORY",
    # [FAZ D · D3] Medya adli hattı: indirme/kare/transkript; varsayılan KAPALI.
    "ENABLE_MEDIA_FORENSICS",
    # [DENETİM 2026-10-14 · B1] Ses kapıları adaptörlerde vardı, listede YOKTU:
    # `/api/speech/*` kendi durumunu elle kurduğu için çalışıyordu ama MCP ve
    # `policy_state()` çağıran her yol bu yetenekleri KALICI kapalı görüyordu.
    "ENABLE_LOCAL_TTS",
    "ENABLE_LOCAL_STT",
)


@dataclass(frozen=True)
class PolicyDecision:
    """Kapı değerlendirmesinin sonucu."""

    allowed: bool
    gate: str | None = None
    reason: str | None = None

    @classmethod
    def allow(cls) -> "PolicyDecision":
        return cls(allowed=True, gate=None, reason=None)

    @classmethod
    def deny(cls, gate: str, reason: str) -> "PolicyDecision":
        return cls(allowed=False, gate=gate, reason=reason)


@dataclass(frozen=True)
class PolicyState:
    """Kapıların değerlendirileceği durum (çağıran sağlar)."""

    vault_locked: bool = False
    spent_usd: float = 0.0
    budget_usd: float | None = None
    rate_ok: bool | None = None          # None = bilinmiyor → "rate" kapısı RET
    enabled_flags: Mapping[str, bool] = field(default_factory=dict)
    #: Çocuk vakası bağlamı. subject_is_minor=True ise runner, politika
    #: kapılarından ÖNCE çocuk kilidini uygular (küresel, istisnasız).
    minor_case: Any | None = None


class PolicyKernel:
    """Yetenek kapılarını değerlendirir (durumsuz, deterministik)."""

    KNOWN_GATES = BUILTIN_GATES
    #: Yönetilen env bayrakları (state.py ile AYNI kaynak: MANAGED_GATE_FLAGS).
    KNOWN_GATE_FLAGS = frozenset(MANAGED_GATE_FLAGS)

    #: Kapı değerlendirme ÖNCELİĞİ (alfabetik DEĞİL — güvenlik sırası):
    #: bilinmeyen kapı (en gürültülü, fail-closed) → kasa → bütçe →
    #: hız → env bayrakları. Önemli: kasa kilidi, env bayrağı kapalı olsa bile
    #: ÖNCE reddedilir; aksi halde denetim izinde "gate_disabled" görünür ve
    #: kasa ihlali maskelenir (Tüzük Md.4.1: kasa istisnasızdır).
    _GATE_ORDER = {"vault": 1, "budget": 2, "rate": 3}

    @classmethod
    def _gate_rank(cls, gate: str) -> int:
        if gate.startswith("ENABLE_"):
            # Yönetilmeyen bir ENABLE_* adı en önce reddedilir (yazım hatası,
            # "sadece kapalı" gibi görünmesin): bilinmeyen kapıyla aynı sıra.
            return 5 if gate in cls.KNOWN_GATE_FLAGS else 0
        if gate not in cls.KNOWN_GATES:
            return 0  # bilinmeyen kapı en önce reddedilir
        return cls._GATE_ORDER[gate]

    def evaluate(self, gates: frozenset[str] | set[str], state: PolicyState) -> PolicyDecision:
        """Kapıları **öncelik** sırasında değerlendirir; ilk ret kararı kesindir."""
        for gate in sorted(gates or (), key=self._gate_rank):
            if gate.startswith("ENABLE_"):
                # [DENETİM 2026-10-14 · B2] ÖNCE "bu bayrak yönetiliyor mu?" —
                # eskiden bu denetim yoktu ve uydurma/yanlış yazılmış bir bayrak
                # adı bile `gate_disabled` dönüyordu: operatör onu açmaya
                # çalışıp başarısız olur, denetim izi de yanlış sınıflanırdı.
                if gate not in self.KNOWN_GATE_FLAGS:
                    return PolicyDecision.deny(gate, "unknown_gate")
                if not bool(state.enabled_flags.get(gate, False)):
                    return PolicyDecision.deny(gate, "gate_disabled")
                continue

            if gate not in self.KNOWN_GATES:
                # Fail-closed: tanınmayan kapı asla "yok sayılmaz".
                return PolicyDecision.deny(gate, "unknown_gate")

            if gate == "vault" and state.vault_locked:
                return PolicyDecision.deny(gate, "vault_locked")

            if gate == "budget":
                if state.budget_usd is not None and state.spent_usd >= state.budget_usd:
                    return PolicyDecision.deny(gate, "budget_exhausted")

            if gate == "rate":
                if state.rate_ok is None:
                    return PolicyDecision.deny(gate, "rate_state_missing")
                if not state.rate_ok:
                    return PolicyDecision.deny(gate, "rate_limited")

        return PolicyDecision.allow()
