"""FAZ D · D4 — dil tespiti: deterministik, modelsiz, ağsız.

Kilitlenen iddialar:
    * tr · en · de · es · fr · ru · az doğru ölçülür.
    * Sinyal yoksa ETİKET UYDURULMAZ: `unknown` + makine-okunur sebep.
    * Güven dürüsttür: tr/az ayrımında marj küçülür → güven ~0.50;
      üç sözcüklük metin 0.99 GÜVEN ALAMAZ.
    * Aynı metin her zaman aynı sonucu verir (determinizm).
"""

from __future__ import annotations

import pytest

from agent_core.services.language import (
    SUPPORTED_LANGUAGES,
    detect_language,
    last_finding,
    record_finding,
    reset_last_finding,
)

SAMPLES = {
    "tr": (
        "Merhaba, bugün hava çok güzel ve ben dışarı çıkmak istiyorum. Ama önce "
        "işlerimi bitirmem gerekiyor çünkü yarın için hazırlık yapmalıyım. Bu "
        "konuda senin fikrin nedir, nasıl bir yol izlemeliyiz?"
    ),
    "en": (
        "Hello, the weather is very nice today and I want to go outside. But "
        "first I have to finish my work because I should prepare for tomorrow. "
        "What do you think about this, how should we proceed with the plan?"
    ),
    "de": (
        "Hallo, das Wetter ist heute sehr schön und ich möchte nach draußen "
        "gehen. Aber zuerst muss ich meine Arbeit beenden, weil ich mich auf "
        "morgen vorbereiten sollte. Was denkst du darüber, wie sollen wir vorgehen?"
    ),
    "es": (
        "Hola, el tiempo está muy bueno hoy y quiero salir afuera. Pero primero "
        "tengo que terminar mi trabajo porque debería prepararme para mañana. "
        "¿Qué piensas sobre esto, cómo deberíamos proceder con el plan?"
    ),
    "fr": (
        "Bonjour, le temps est très beau aujourd'hui et je veux sortir dehors. "
        "Mais d'abord je dois finir mon travail parce que je devrais me préparer "
        "pour demain. Qu'est-ce que tu en penses, comment devrions-nous procéder ?"
    ),
    "ru": (
        "Привет, сегодня очень хорошая погода и я хочу пойти гулять. Но сначала "
        "мне нужно закончить работу, потому что я должен подготовиться к "
        "завтрашнему дню. Что ты думаешь об этом, как нам лучше поступить?"
    ),
    "az": (
        "Salam, bu gün hava çox gözəldir və mən çölə çıxmaq istəyirəm. Amma "
        "əvvəlcə işlərimi bitirməliyəm, çünki sabah üçün hazırlıq görməliyəm. "
        "Sən bu barədə nə düşünürsən, necə yol tutmalıyıq?"
    ),
}


class TestDetection:
    @pytest.mark.parametrize("lang", sorted(SAMPLES))
    def test_supported_languages_detected(self, lang):
        finding = detect_language(SAMPLES[lang])
        assert finding.language == lang
        assert finding.confidence >= 0.85  # temiz metin: yüksek ama dürüst

    def test_supported_language_list_is_fixed(self):
        assert SUPPORTED_LANGUAGES == ("tr", "en", "de", "es", "fr", "ru", "az")

    def test_ru_script_measured_as_cyrillic(self):
        assert detect_language(SAMPLES["ru"]).script == "cyrillic"

    def test_tr_script_measured_as_latin(self):
        assert detect_language(SAMPLES["tr"]).script == "latin"


class TestHonestUnknown:
    def test_too_short_is_unknown_with_reason(self):
        finding = detect_language("merhaba")
        assert finding.language == "unknown"
        assert finding.reason == "too_short"
        assert finding.confidence == 0.0

    def test_empty_text_is_unknown(self):
        assert detect_language("").language == "unknown"
        assert detect_language("   ").reason == "too_short"

    def test_digit_noise_has_no_signal(self):
        finding = detect_language("12345 67890 11111 22222 33333 44444 55555")
        assert finding.language == "unknown"

    def test_meaningless_latin_is_unknown(self):
        finding = detect_language("xyz qwe asd zxc vbn mnb lkj poi uytr")
        assert finding.language == "unknown"
        assert finding.reason == "no_signal"

    @pytest.mark.parametrize(
        "text,script",
        [
            ("مرحبا اليوم الطقس جميل جدا وأريد أن أخرج من البيت لكن يجب أن أنهي عملي", "arabic"),
            ("今天天气很好，我想出去走走，但是首先我必须完成我的工作计划", "cjk"),
            ("γειά σου σήμερα ο καιρός είναι πολύ καλός και θέλω να βγω έξω", "greek"),
        ],
    )
    def test_unsupported_scripts_reported_not_labeled(self, text, script):
        finding = detect_language(text)
        assert finding.language == "unknown"
        assert finding.reason == f"script_unsupported:{script}"
        assert finding.script == script


class TestConfidenceHonesty:
    def test_tr_az_ambiguous_gets_low_confidence(self):
        mixed = "Bu gün hava çox gözəldir və bu benim için çok güzel bir gün değil mi"
        finding = detect_language(mixed)
        assert finding.language in ("tr", "az")
        assert finding.confidence <= 0.60  # marj küçük: güven ŞİŞİRİLMEZ

    def test_tiny_text_never_gets_high_confidence(self):
        finding = detect_language("merhaba dünya bugün")
        assert finding.language == "tr"
        assert finding.confidence <= 0.75  # 3 sözcük 0.99 olamaz

    def test_confidence_within_bounds(self):
        for text in SAMPLES.values():
            conf = detect_language(text).confidence
            assert 0.5 <= conf <= 0.99


class TestDeterminismAndState:
    def test_same_input_same_output(self):
        first = detect_language(SAMPLES["tr"]).model_dump()
        second = detect_language(SAMPLES["tr"]).model_dump()
        assert first == second

    def test_record_and_last_finding(self):
        reset_last_finding()
        assert last_finding() is None
        finding = detect_language(SAMPLES["fr"])
        record_finding(finding, source_engine="trafilatura", url="https://ornek.example/x")
        last = last_finding()
        assert last is not None
        assert last["language"] == "fr"
        assert last["source_engine"] == "trafilatura"
        assert last["url"] == "https://ornek.example/x"
        assert last["at"]
        reset_last_finding()
        assert last_finding() is None
