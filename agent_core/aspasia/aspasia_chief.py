"""ASPASIA — kullanıcıya bakan Sokratik şef katmanı (danışman, kanıt bekçisi).

``chat`` akışı: oda durumu (telemetri + kanıt zinciri) yapılandırılmış özet
hâline getirilir (``build_telemetry_summary``), kaynak-destekli denetim bloğu
eklenir (``_oversight_digest`` — okuma hatası sessiz boşluğa düşer, uydurmaya
değil) ve model çağrısı gateway üzerinden yapılır.

ASPASIA görev YÜRÜTMEZ; komutları ``AspasiaCommandGateway`` üzerinden
yürütücüye devreder ve sonucu yorumlar. ``set_preferred_model`` ile model
tercihi oda bazında değiştirilebilir.

Tüketici: ``backend/api.py`` (``/api/aspasia/*``).
Test: ``tests/unit/test_aspasia_chief_layer.py``, ``tests/integration/test_aspasia_chief.py``.
"""

from typing import Any, Optional
from pydantic import BaseModel

from agent_core.services.llm_gateway import LLMGateway

ASPASIA_SYSTEM_PROMPT = """Sen ASPASIA'sın: PINEAL sisteminin kullanıcıyla konuşan başdanışmanı ve tek merkezli sohbet/komut arayüzüsün.

KİMLİK: Sakin, net, anlaşılır ve doğal bir Türkçe ile konuşursun. Kullanıcıya gerektiğinde doğal aralıkla "Mösyö" diye hitap edersin.

KONU: Hedef profil, toplanan bulgular ve şu anki işlem durumu. Kullanıcının mesajını ya da kişiliğini analiz konusu yapmazsın.

KANIT SÖZLEŞMESİ:
- Sadece elindeki sistem verisinin söylediğini söylersin; veride olmayanı uydurmazsın.
- Doğrulamadığın şeyi kesin gibi sunmazsın; bilmiyorsan "Bunu henüz doğrulamadım, Mösyö." dersin.
- Kanıt yetersizse veya bir bilgi eksikse bunu yalın, günlük bir dille açıkça söylersin; ham log, iç değişken adı veya teknik etiket kopyalamazsın.

ÜSLUP (YALIN VE DOĞAL DİL):
- Kısa, sade ve herkesin ilk okumada anlayacağı yalın bir Türkçe kullan: önce sonuç, sonra gerekiyorsa tek cümleyle neden, sonra tek bir sonraki adım.
- Asla karmaşık iç terimler ("telemetri", "canonical memory", "bayat snapshot", "pipeline", "routing-aday", "snippet", "7-pillar", "command gateway") kullanma; bunları günlük konuşma diline çevir.
- Komut satırı / PowerShell önerisi VERMEZSİN.
- Kullanıcıya ASLA "yukarıdaki kutuya yazın", "başka bir bölüme geçin" veya "CAPTURE tuşuna basın" DEME! Kullanıcı her şeyi doğrudan bu sohbet kutusuna yazarak halledebilir.
- Eğer bir inceleme başlatmak için hedef hesap linki veya kullanıcı adı eksikse: "Hangi hesabı incelememi istersiniz Mösyö? Kullanıcı adını (örneğin @kullanici) veya profil linkini doğrudan buraya yazmanız yeterli." de.
- Eğer yapılan incelemede bir veri eksik kaldıysa (örneğin Instagram oturumu açık olmadığı için gönderiler çekilemediyse veya açık web aramasında yeterli bilgi çıkmadıysa), neyin eksik olduğunu doğal dille söyle.

KARAR: Teknik seçimi sen yapmazsın — CognitiveRouter yapar. Öneri sunar, gerekçeni söyler, tek yol tavsiye edersin.

SINIR: Sisteme doğrudan müdahale yetkin yok; gereken işlem kullanıcıya gerekçesiyle iletilir. Kusursuz Türkçe konuşursun.

ROL GENİŞLETMESİ — MERKEZİ ARAYÜZ VE DENETİM:
- Sen Pineal'in merkezi doğal-dil arayüzüsün: sistem, ajan, routing, kota ve maliyet durumunu sorulduğunda elindeki özetten şeffafça ve sade bir dille açıklarsın.
- Kullanıcı isteğini yapılandırılmış komuta çevirebilirsin; komut yalnız CommandGateway üzerinden geçer.
- Politika atlatma öneremezsin; model/provider/ajan adı uyduramazsın. Özetlerde kanıt yoksa "veri yok" dersin — ham log dökmezsin.
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
            pass
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
            elif isinstance(room_state.get("latest_result"), dict) and room_state["latest_result"].get("task_id"):
                snapshot = room_state["latest_result"]
            else:
                vault = room_state.get("vault", {})
                api_status = 'OK' if vault.get('or_key') else 'X'
                recent_logs = room_state.get("logs") or []
                log_tail = ("\nSon Oda Kayıtları:\n" + "\n".join(str(x) for x in recent_logs[-10:])) if recent_logs else ""
                return f"Sistem boşta. API: {api_status} | Beklemedeyiz. (Henüz incelenecek bir profil linki veya @kullanıcı adı girilmedi.){log_tail}"
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
            agent_runs = snapshot.get("agent_runs", {}) or snapshot.get("runs", {})
            target_profile = snapshot.get("target_profile") or {}
            channel_status = snapshot.get("channel_status") or []
        else:
            task_id = getattr(snapshot, "task_id", "unknown")
            status = getattr(snapshot, "status", "unknown")
            current_agent = getattr(snapshot, "current_agent", None)
            planned = getattr(snapshot, "planned_agents", []) or []
            completed = getattr(snapshot, "completed_agents", []) or []
            halted_reason = getattr(snapshot, "halted_reason", None)
            agent_runs = getattr(snapshot, "agent_runs", {}) or {}
            target_profile = getattr(snapshot, "target_profile", {}) or {}
            channel_status = getattr(snapshot, "channel_status", []) or []

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

        if isinstance(target_profile, dict) and target_profile:
            t_name = target_profile.get("name") or target_profile.get("username") or ""
            t_bio = target_profile.get("bio") or ""
            t_posts = target_profile.get("posts") or []
            t_snips = target_profile.get("search_snippets") or []
            t_urls = target_profile.get("detected_urls") or []
            t_followers = target_profile.get("followers")
            t_following = target_profile.get("following")
            counts_part = []
            if t_followers is not None:
                counts_part.append(f"Takipçi: {t_followers}")
            if t_following is not None:
                counts_part.append(f"Takip: {t_following}")
            counts_str = f" | {' / '.join(counts_part)}" if counts_part else ""
            lines.append(
                f"Hedef Profil: {t_name or 'Bilinmiyor'}{counts_str} | Gönderi sayısı: {len(t_posts)} | "
                f"Web arama sonucu: {len(t_snips)} | Bulunan sosyal bağlantılar: {len(t_urls)}"
            )
            if t_bio:
                lines.append(f"Hedef Biyografisi (Bio): {str(t_bio)[:400]}")
                import re
                bio_mentions = re.findall(r"@[A-Za-z0-9_.-]+", str(t_bio))
                if bio_mentions:
                    lines.append(f"Biyografideki Bağlı/İş Hesapları: {', '.join(bio_mentions)}")

            # Zincirleme kazınan işletme hesapları (Faz 1):
            biz_entities = target_profile.get("business_entities") or []
            if biz_entities:
                biz_lines = []
                for b in biz_entities:
                    h = b.get("handle")
                    cnt = b.get("post_count", 0)
                    fol = b.get("followers")
                    priv = " (Gizli)" if b.get("is_private") else " (Açık)"
                    biz_lines.append(f"{h}{priv} [Gönderi: {cnt}, Takipçi: {fol if fol is not None else '?'}]")
                lines.append(f"İncelenen Bağlı İşletme Profilleri: {'; '.join(biz_lines)}")

            if t_urls:
                # Platformlara göre ayrıştır
                platforms_found = {}
                for u in t_urls:
                    u_low = str(u).lower()
                    if "facebook" in u_low:
                        platforms_found.setdefault("Facebook", []).append(u)
                    elif "linkedin" in u_low:
                        platforms_found.setdefault("LinkedIn", []).append(u)
                    elif "tiktok" in u_low:
                        platforms_found.setdefault("TikTok", []).append(u)
                    elif "threads" in u_low:
                        platforms_found.setdefault("Threads", []).append(u)
                    elif "instagram" in u_low and t_name not in u_low:
                        platforms_found.setdefault("Diğer Instagram", []).append(u)
                if platforms_found:
                    cat_summary = [f"{plat}: {len(urls_list)} bağlantı" for plat, urls_list in platforms_found.items()]
                    lines.append(f"Tespit Edilen Çapraz Platformlar: {', '.join(cat_summary)}")
                lines.append(f"Örnek Profil Bağlantıları: {', '.join(t_urls[:6])}")

        missing_notes = []
        if isinstance(channel_status, list):
            for ch in channel_status:
                if isinstance(ch, dict) and ch.get("status") in ("failed", "not_run"):
                    ch_name = ch.get("channel") or ""
                    reason = ch.get("reason") or ch.get("detail") or ""
                    if "instagram" in ch_name and ("login" in str(reason) or "session" in str(reason)):
                        missing_notes.append("Instagram doğrudan gönderi çekimi için Instagram oturumu (çerez) eksik; açık web araması kullanıldı.")
                    elif reason:
                        missing_notes.append(f"{ch_name}: {reason}")
        if missing_notes:
            lines.append("EKSİK / ÇALIŞMAYAN KANALLAR (Kullanıcıya yalın dille açıkla): " + " | ".join(missing_notes))
        
        if halted_reason:
            lines.append(f"DURDURMA NEDENİ: {halted_reason}")
            
        if agent_runs:
            for name, run in agent_runs.items():
                if isinstance(run, dict):
                    conf_val = run.get("confidence")
                    conf = f"{conf_val:.2f}" if isinstance(conf_val, (int, float)) else "?"
                    st = run.get("status", "unknown")
                    err = run.get("error_message")
                else:
                    conf = f"{run.confidence:.2f}" if getattr(run, "confidence", None) is not None else "?"
                    st = getattr(run, "status", "unknown")
                    err = getattr(run, "error_message", None)
                lines.append(f"  [{name}] {st} | güven:{conf}")
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
                    
        if isinstance(room_state, dict) and room_state.get("logs"):
            lines.append("Son Oda Kayıtları:\n" + "\n".join(str(x) for x in room_state["logs"][-10:]))
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

Yukarıdaki sistem durumu ve kullanıcı mesajını dikkate alarak ASPASIA kimliğinle yanıt ver:
1. YALIN VE DOĞAL TÜRKÇE KULLAN: Kullanıcıya iç teknik terimler ("telemetri", "canonical memory", "bayat snapshot", "pipeline", "routing-aday", "snippet", "7-pillar") kullanma; her şeyi herkesin anlayacağı yalın, günlük Türkçeyle anlat.
2. ORAYA YAZ BURAYA YAZ DEME: Kullanıcıya asla "yukarıdaki kutuya yazın", "CAPTURE tuşuna basın" veya "başka bir ekrana geçin" deme! Kullanıcı her şeyi doğrudan bu sohbet kutusuna yazabilir.
3. BULUNAN PLATFORMLARI VE İŞLETMELERİ DÜZENLİ LİSTELE: Eğer hedef hakkında bağlı işletme profilleri (@hesap) veya diğer sosyal ağlar (Facebook, LinkedIn, TikTok vb.) tespit edildiyse, bunları "Bulunan Profiller ve İşletmeler" başlığı altında net bağlantılar/kullanıcı adları olarak açıkça listele.
4. EKSİK VARSA AÇIKÇA SÖYLE: Eğer kullanıcı bir kişiyi/hesabı inceletmek istiyor ama henüz hangi profil veya @kullanıcı_adı olduğunu yazmadıysa, "Hangi hesabı incelememi istersiniz Mösyö? Kullanıcı adını (örneğin @kullanici) veya profil linkini doğrudan buraya yazmanız yeterli." de. Eğer tamamlanan bir incelemede eksik kalan bir veri varsa (örneğin Instagram oturumu açık olmadığı için gizli profilin gönderileri çekilemediyse veya bir platformda veri bulunamadıysa), neyin neden eksik olduğunu doğal dille söyle.
5. KISA VE NET OL: Önce doğrudan cevabı/sonucu söyle, ardından gerekiyorsa tek bir sonraki adımı belirt.
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
                pass
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
