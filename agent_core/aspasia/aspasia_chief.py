import logging
logger = logging.getLogger(__name__)
from typing import Any, Optional
from pydantic import BaseModel

from agent_core.services.llm_gateway import LLMGateway

ASPASIA_SYSTEM_PROMPT = """Sen ASPASIA'sın: PINEAL sisteminin kullanıcıyla konuşan chief asistanı.

KİMLİK: Sakin, zarif, ölçülü ve analitiksin; ince ve kuru bir mizah kullanabilirsin. Zekânı sergilemezsin, kullanırsın. Kullanıcıya "Mösyö" diye hitap edersin — her cümlede değil, doğal aralıkla.

KONU: Hedef profil, kanıt zinciri ve sistem durumu. Kullanıcının mesajını ya da kişiliğini analiz konusu yapmazsın.

KANIT SÖZLEŞMESİ:
- Sadece elindeki sistem verisinin (telemetri/kanıt özeti) söylediğini söylersin; veride olmayanı uydurmazsın.
- Doğrulamadığın şeyi kesin gibi sunmazsın; bilmiyorsan "Bunu henüz doğrulamadım, Mösyö." dersin.
- Kanıt yetersizse bunu açıkça söylersin; sonucu şişirmezsin; ham log veya iç etiket kopyalamazsın.

ÜSLUP:
- Kısa ve net: önce sonuç, gerekiyorsa bir-iki cümle neden, sonra tek bir sonraki adım. Duvar-metin yazmazsın.
- Jargonu çevirirsin ("dizin" değil "klasör"); teknik terim şartsa aynı cümlede kısaca açıklarsın.
- Komut satırı / PowerShell önerisi VERMEZSİN. Ne yapılması gerektiğini ve nedenini günlük dille söylersin; uygulamayı kullanıcı yapar.
- Sokak ağzı, abartılı emoji, yapay samimiyet, teatral ton yok. Kullanıcı öfkelenirse sakin kalır, konuya dönersin.

KARAR: Teknik seçimi sen yapmazsın — CognitiveRouter yapar. Öneri sunar, gerekçeni söyler, tek yol tavsiye edersin; seçenek menüsü sunmazsın. Kullanıcının planına itirazın varsa gerekçeni bir-iki cümleyle söylersin, kararı ona bırakırsın. Kendinle çelişmezsin; yanıldıysan savunmaz, düzeltir ve devam edersin.

SINIR: Sisteme doğrudan müdahale yetkin yok; gereken işlem kullanıcıya gerekçesiyle iletilir. Kusursuz Türkçe konuşursun.

ROL GENİŞLETMESİ — MERKEZİ ARAYÜZ VE DENETİM:
- Sen Pineal'in merkezi doğal-dil arayüzüsün: sistem, ajan, routing, kota ve maliyet durumunu elindeki DENETİM KATMANI özetinden kullanıcıya şeffafça açıklarsın (rota neden seçildi, kota ne durumda, indirimli fiyat listeye göre ne, fallback neden işledi, ikame neden reddedildi).
- Kullanıcı isteğini yapılandırılmış komuta çevirebilirsin; komut yalnız CommandGateway üzerinden geçer: doğrulama, rate limit, yaşam döngüsü ve gerçek planlayıcı (CognitiveRouter) katmanlarından geçtikten sonra yürür. Bu, "doğrudan müdahale" değil, yetkili kanaldan iletilen taleptir.
- Politika atlatma öneremezsin; model/provider/ajan adı uyduramazsın; ajan listesi senin işin değil planlayıcının işidir. Özetlerde kanıt yoksa "veri yok" dersin — ham log dökmezsin.
"""

class AspasiaResponse(BaseModel):
    message: str
    confidence_assessment: str = "high"
    signature_quote: Optional[str] = None

class AspasiaChief:
    def __init__(
        self,
        llm_gateway: Optional[LLMGateway] = None,
        command_gateway: Optional[Any] = None,
        executor: Optional[Any] = None,
    ):
        self.llm = llm_gateway or LLMGateway()
        # None → gateway tier-1 default. (Legacy hard-coded non-existent
        # "muse-spark-1.2-xhigh" slug removed; chat() now reads this field.)
        self.preferred_model: Optional[str] = None
        # ASPASIA PROMOTION: tek yazma kanalı CommandGateway'dir (api.py
        # örner). None = bu chief yalnız okuma/diyalog yetkili (geriye dönük
        # uyum: eski kurucular aynen calisir).
        self.commands = command_gateway
        self._executor = executor

    def _oversight_digest(self, room_state: Any) -> str:
        """Source-backed state block; any read failure degrades to silent empty.

        Denetim verisi uydurulmaz: okuma hatasinda diyest bosalir ve chat()
        bloğu hic eklemez — Yanit kotulugunun (fallback mesajinin) onune gecer.
        """
        try:
            from agent_core.aspasia.interface import build_oversight_digest

            last_agent = None
            if isinstance(room_state, dict):
                active = room_state.get("active_tasks") or {}
                if active:
                    snap = list(active.values())[-1]
                    last_agent = (snap.get("current_agent") if isinstance(snap, dict)
                                  else getattr(snap, "current_agent", None)) or None
            digest = build_oversight_digest(
                self.llm, room_state, self._executor, self.commands, last_agent=last_agent
            )
            if digest:
                return digest
        except Exception:
            logger.warning('Suppressed exception observed at agent_core/aspasia/aspasia_chief.py:79 (pass)')
        return ""


    def set_preferred_model(self, model_name: Optional[str]) -> None:
        self.preferred_model = model_name

    def build_telemetry_summary(self, room_state: Any) -> str:
        """Ajan telemetrisini ve kanıt zincirini yapılandırılmış veriden özetler."""
        if not room_state:
            return "Sistem beklemede. Henüz aktif görev tetiklenmedi."

        snapshot = None
        if hasattr(room_state, "task_id"):
            snapshot = room_state
        elif isinstance(room_state, dict):
            active_tasks = room_state.get("active_tasks", {})
            if active_tasks:
                snapshot = list(active_tasks.values())[-1]
            elif "task_id" in room_state:
                snapshot = room_state
            else:
                vault = room_state.get("vault", {})
                api_status = 'OK' if vault.get('or_key') else 'X'
                return f"Sistem boşta. API: {api_status} | Beklemedeyiz."
        else:
            return "Sistem beklemede. Henüz aktif görev tetiklenmedi."

        if not snapshot:
            return "Sistem beklemede. Henüz aktif görev tetiklenmedi."

        if isinstance(snapshot, dict):
            task_id = snapshot.get("task_id", "unknown")
            status = snapshot.get("status", "unknown")
            current_agent = snapshot.get("current_agent")
            planned = snapshot.get("planned_agents", [])
            completed = snapshot.get("completed_agents", [])
            halted_reason = snapshot.get("halted_reason")
            agent_runs = snapshot.get("agent_runs", {})
        else:
            task_id = getattr(snapshot, "task_id", "unknown")
            status = getattr(snapshot, "status", "unknown")
            current_agent = getattr(snapshot, "current_agent", None)
            planned = getattr(snapshot, "planned_agents", []) or []
            completed = getattr(snapshot, "completed_agents", []) or []
            halted_reason = getattr(snapshot, "halted_reason", None)
            agent_runs = getattr(snapshot, "agent_runs", {}) or {}

        # [FAZ 2] Enum repr ("PipelineStatus.COMPLETED") kullaniciya sizmaz;
        # durum degeri normalize edilir (interface._status_value ile ayni kural).
        from agent_core.aspasia.interface import _status_value

        status = _status_value(status) or "unknown"

        lines = [
            f"Görev: {task_id} | Durum: {status}",
            f"Aktif Ajan: {current_agent or 'Yok'}",
            f"Planlanan: {' -> '.join(planned) if planned else 'Henüz rota çizilmedi'}",
            f"Tamamlanan: {', '.join(completed) or 'henüz yok'}",
        ]
        
        if halted_reason:
            lines.append(f"DURDURMA NEDENİ: {halted_reason}")
            
        if agent_runs:
            for name, run in agent_runs.items():
                conf = f"{run.confidence:.2f}" if getattr(run, "confidence", None) is not None else "?"
                st = getattr(run, "status", "unknown")
                lines.append(f"  [{name}] {st} | güven:{conf}")
                err = getattr(run, "error_message", None)
                if err:
                    lines.append(f"    HATA: {err}")

        # 360° İnsan Tanıma Çözümleme Özeti
        holistic = getattr(snapshot, "holistic_profile", None) if not isinstance(snapshot, dict) else snapshot.get("holistic_profile")
        if holistic:
            lines.append("\n--- 360° İNSAN TANIMA ÇÖZÜMLEMESİ ---")
            passions = getattr(holistic, "passions", None) or (holistic.get("passions") if isinstance(holistic, dict) else None)
            if passions:
                cp = getattr(passions, "core_passions", []) if not isinstance(passions, dict) else passions.get("core_passions", [])
                lines.append(f"  [TUTKULAR & NEŞE]: {', '.join(cp) if cp else 'Belirgin tutku tespiti yok'}")
                
            frictions = getattr(holistic, "frictions", None) or (holistic.get("frictions") if isinstance(holistic, dict) else None)
            if frictions:
                sens = getattr(frictions, "sensitivities", []) if not isinstance(frictions, dict) else frictions.get("sensitivities", [])
                lines.append(f"  [HASSASİYETLER & SINIRLAR]: {', '.join(sens) if sens else 'Belirgin sınır tespiti yok'}")

            cognitive = getattr(holistic, "cognitive", None) or (holistic.get("cognitive") if isinstance(holistic, dict) else None)
            if cognitive:
                tone = getattr(cognitive, "communication_tone", "") if not isinstance(cognitive, dict) else cognitive.get("communication_tone", "")
                lvl = getattr(cognitive, "complexity_level", "") if not isinstance(cognitive, dict) else cognitive.get("complexity_level", "")
                lines.append(f"  [İLETİŞİM ÜSLUBU]: Ton: {tone} | Düzey: {lvl}")

            bridge = getattr(holistic, "bridge", None) or (holistic.get("bridge") if isinstance(holistic, dict) else None)
            if bridge:
                topic = getattr(bridge, "authentic_opening_topic", "") if not isinstance(bridge, dict) else bridge.get("authentic_opening_topic", "")
                msg = getattr(bridge, "suggested_opening_message", "") if not isinstance(bridge, dict) else bridge.get("suggested_opening_message", "")
                lines.append(f"  [ÖNERİLEN İLK DİYALOG KONUSU]: {topic}")
                lines.append(f"  [SAHİCİ İLETİŞİM KÖPRÜSÜ]: \"{msg}\"")
            lines.append("--------------------------------------")
                    
        return "\n".join(lines)

    async def chat(
        self,
        user_message: str,
        room_state: Any,
        model_override: Optional[str] = None,
        image_data: Optional[str] = None
    ) -> AspasiaResponse:
        """Aspasia Sokratik yanıt mekanizmasını çalıştırır.

        image_data: kullanıcının yüklediği görselin base64 data-URL'i.
        Görsel analizi (vision) henüz desteklenmiyor; varlığı oturuma dürüstçe kaydedilir.
        """
        from agent_core.domain.memory_models import AspasiaSession
        
        telemetry_summary = self.build_telemetry_summary(room_state)
        oversight = self._oversight_digest(room_state)
        oversight_block = (
            "\nDENETİM KATMANI (routing/kota/maliyet/komut — kaynaklı özet):\n"
            f"{oversight}\n"
            "Bu özet iki tür satır içerir, karıştırma: ROUTING-ADAY satırları PLANLANAN "
            "rotadır (henüz çalışmadı) — 'çalıştı/gerçekleşti' diye anlatma; TELEMETRİ/ "
            "SONUÇ/KOMUT/HAFIZA-DISK satırları GÖZLEMLENMİŞ gerçektir (HAFIZA-DISK = RAM boşken diskten okunan kanonik kayıt). Kullanıcı routing, kota, "
            "masraf veya ikame sorarsa buradan cevapla; alanda kanıt yoksa uydurma.\n"
        ) if oversight else ""

        # [FIX #4] Deterministik hüküm özeti: Aspasia "bu görevde ne
        # buldun?" sorusunu artık KANITTAN derlenmiş özetle cevaplar;
        # LLM katılmadı, uydurma hüküm yok, kanıt yoksa dürüst satır var.
        from agent_core.services.verdict_synthesizer import build_verdict_digest
        verdict = build_verdict_digest(room_state)
        verdict_block = (
            "\nHÜKÜM BELGESİ (deterministik kanıt özetı — LLM sentezi DEĞİL):\n"
            f"{verdict}\n"
            "Bunu KISA / TEK CÜMLE olarak aktar. Bu bir tıbbi veya hukuki "
            "hüküm DEĞİLDİR; yalnızca kanıt zincirinin mekanik özetidir. "
            "Kullanıcı sonuç/kanıt sorarsa buradan cevapla; özet boşsa "
            "'hüküm yok' de, uydurma.\n"
        ) if verdict else ""

        context_prompt = f"""
SİSTEM CANLI TELEMETRİ ÖZETİ (Event Bus):
{telemetry_summary}
{oversight_block}
{verdict_block}

KULLANICI MESAJI VEYA SORUSU: "{user_message}"
{"(Not: Kullanıcı bir görsel yükledi; görsel de isteğe eklenmiştir — varsa içeriğini yorumla.)" if image_data else ""}

Yukarıdaki sistem durumu ve kullanıcı mesajını dikkate alarak ASPASIA kimliğinle yanıt ver.
Kullanıcının sistem tercümanına ihtiyacı yok: ajanların ne yaptığını, hangi model/provider durumunun etkilediğini ve kanıtın ne söylediğini günlük dille kendin açıkla.
Senin sisteme doğrudan müdahale etme veya durdurma yetkin yok. Kullanıcının bir işlem yapması gerekiyorsa önce nedenini söyle; ne yapılacağını günlük dille anlat, komut satırı önerme.
Bir hata veya durma varsa hangi ajanın takıldığını, nedenini ve sonraki doğru adımı açıkla. Telemetride olmayan şeyi uydurma; kanıt yoksa bunu dürüstçe belirt.
Cevabın kısa ve net olsun: sonuç, sonra gerekiyorsa neden ve tek bir sonraki adım. Kullanıcıya "Mösyö" diye hitap et; duvar-metin yazma; gereksiz teknik jargon kullanma.
"""
        
        selected_model = model_override or self.preferred_model
        if not selected_model and any(w in user_message.lower() for w in ["yerel", "local", "kısıtlamasız", "ollama", "lmstudio"]):
            selected_model = "local"

        final_msg = ""
        assessment = "high"

        try:
            if selected_model:
                # Kullanıcının/operatörün AÇIK model tercihi: pin bilinçlidir,
                # chain devreye girmez (local veya explicit model override).
                raw_response = await self.llm.query(
                    prompt=context_prompt,
                    system_prompt=ASPASIA_SYSTEM_PROMPT,
                    temperature=0.4,
                    tier=1,
                    model=selected_model,
                    images=[image_data] if image_data else None,
                )
            else:
                # F-1: agent kimliği merkezi routing'e bağlandı —
                # AGENT_CHAINS["aspasia"] + provider maliyet merdiveni +
                # fallback/spend-cap/substitution gate'lerinin tamamı geçerli.
                raw_response = await self.llm.query_chain(
                    prompt=context_prompt,
                    task="dialogue",
                    temperature=0.4,
                    system_prompt=ASPASIA_SYSTEM_PROMPT,
                    agent_name="aspasia",
                    images=[image_data] if image_data else None,
                )
            final_msg = raw_response.strip()
            assessment = "high"
            # [FAZ C · C1] JENERİK YANIT FİLTRESİ: "Tabii ki! Harika bir soru..."
            # türü laf salatası KULLANICIYA ÇIKMAZ. Ölçüm deterministiktir;
            # elde VERİ varken ona değinmeyen yanıt en ağır sinyaldir.
            # Düşen yanıtın yerine kanıttan derlenmiş dürüst cümle konur ve
            # olay telemetriye yazılır (neden düştüğü görünür).
            try:
                from agent_core.services.taste_filter import filter_response

                decision = filter_response(
                    final_msg,
                    context={"verdict": verdict, "telemetry": telemetry_summary},
                )
                if not decision.kept:
                    final_msg = decision.message
                    assessment = "filtered_generic"
            except Exception:  # filtre asla sohbeti düşürmez
                logger.warning('Suppressed exception observed at agent_core/aspasia/aspasia_chief.py:286 (pass)')
        except Exception as e:
            # Fallback Aspasia Response
            final_msg = (
                "Tamam, şu an Aspasia'nın model bağlantısı çalışmadı. "
                f"Görünen hata: {str(e)[:60]}. "
                "Sistem verisini uydurmuyorum; bağlantıyı kontrol edip tekrar denemek en doğru adım."
            )
            assessment = "fallback"

        if isinstance(room_state, dict):
            if "aspasia_session" not in room_state or not isinstance(room_state["aspasia_session"], AspasiaSession):
                room_state["aspasia_session"] = AspasiaSession.create(room_state.get("client_id", "default"))
            room_state["aspasia_session"].add_message("user", user_message)
            room_state["aspasia_session"].add_message("aspasia", final_msg)

        return AspasiaResponse(
            message=final_msg,
            confidence_assessment=assessment
        )
