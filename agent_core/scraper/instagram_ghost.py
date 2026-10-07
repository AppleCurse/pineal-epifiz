"""
PINEAL-HERETIC v2.0 - Instagram Ghost Scraper (Self-Hosted)
Faz 5 / Görev 3 - Türkiye Operasyonu

Mimari Karar: Sıfır SaaS, sıfır Apify, sıfır kart.
X scraper.py'nin ikizi - Playwright hayalet tarayıcı, kendi bilgisayarında çalışır.
Halüsinasyon = 0. Kanıt yoksa HALT.

Bu modül asla veri uydurmaz. Instagram'ın döndüğü gerçek JSON'u alır,
Pydantic V2 ile doğrular, güven düşükse InsufficientEvidenceError fırlatır.

[GÖREV 1] Tamamlayici kazima: /reel/ + video yakalama, 1-to-1 dogrulanmis
post nesneleri (capraz-liste eslesmesi yasak), taken_at/like/comment parse,
kronolojik siralama t_0 -> t_N.
"""

from __future__ import annotations
import asyncio
import json
import logging
logger = logging.getLogger(__name__)
import os
import random
import re
from datetime import datetime, timezone
from typing import List, Optional, Dict, Any

from pydantic import BaseModel, Field, ConfigDict, field_validator


# --- Faz 1: post-detay zenginleştirme anahtarları (kontrollü, geri alınabilir) ---
def _post_detail_enabled() -> bool:
    """PINEAL_POST_DETAIL_ENABLED=false ise grid-verisiyle yetin (eski davranış)."""
    return os.getenv("PINEAL_POST_DETAIL_ENABLED", "true").strip().lower() == "true"


def _post_detail_limit() -> int:
    """Zenginleştirilecek en fazla post sayısı (1..12, varsayılan 12)."""
    try:
        return max(0, min(12, int(os.getenv("PINEAL_POST_DETAIL_LIMIT", "12"))))
    except (TypeError, ValueError):
        return 12


# --- Anti-Halüsinasyon Çekirdeği ---
class InsufficientEvidenceError(Exception):
    """Kanıt yoksa uydurma, DUR. Faz 4 kuralı."""


# --- Pydantic V2 Şemalar (ConfigDict, extra="forbid" - halüsinasyon filtresi) ---
class InstagramPost(BaseModel):
    model_config = ConfigDict(extra="forbid")

    shortcode: str = Field(..., description="Post ID, örn: C123...")
    caption: Optional[str] = Field(None, max_length=2200)
    display_url: str = Field(..., description="Fotoğrafın gerçek URL'i, uydurma değil")
    is_video: bool = False
    location_name: Optional[str] = None
    taken_at: Optional[datetime] = None
    like_count: Optional[int] = None
    comment_count: Optional[int] = None
    # [GÖREV 1] Medya turu + ham video URL'i. None = "bilinmiyor/olcülmedi";
    # tur bilinmiyorsa "image" varsayilmaz (uydurma yasak).
    post_type: Optional[str] = Field(
        None, description="image | video | carousel | reel; None = bilinmiyor"
    )
    video_url: Optional[str] = Field(
        None, description="Video dosyasinin gercek URL'i (mp4), varsa"
    )

    @field_validator("display_url")
    @classmethod
    def url_must_be_real(cls, v: str) -> str:
        if not v.startswith("http"):
            raise ValueError("Sahte URL halüsinasyondur")
        return v


class InstagramProfile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    username: str
    full_name: Optional[str] = None
    biography: Optional[str] = None
    is_private: bool
    is_verified: bool = False
    follower_count: Optional[int] = None
    following_count: Optional[int] = None
    post_count: Optional[int] = None
    profile_pic_url: Optional[str] = None
    posts: List[InstagramPost] = Field(default_factory=list)
    scraped_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    evidence_source: str = Field(default="self_hosted_ghost_browser", description="Kanıtın nereden geldiği, şeffaflık için")

    @field_validator("posts")
    @classmethod
    def posts_must_be_real(cls, v: List[InstagramPost]) -> List[InstagramPost]:
        # 12 posttan fazla istemiyoruz, OSINT için yeterli
        return v[:12]


class InstagramGhostScraper:
    """
    Self-hosted hayalet kazıyıcı.
    X scraper.py ile aynı mimari: Playwright, vault'tan cookie, stealth.
    Asla veri uydurmaz.
    """

    # [GÖREV 1] Yapisal dugum -> post_type eslemesi (IG __typename/product_type).
    _TYPENAME_MAP = {
        "GraphImage": "image",
        "GraphVideo": "video",
        "GraphSidecar": "carousel",
    }
    _PRODUCT_TYPE_MAP = {
        "reels": "reel",
        "clips": "reel",
    }

    def __init__(self, vault_cookies: Optional[Dict[str, str]] = None):
        self.vault_cookies = vault_cookies or {}
        self.base_url = "https://www.instagram.com"

    async def _random_delay(self):
        """İnsan gibi bekle, bot gibi değil — ama event loop'u kilitlemeden.

        [AUDIT P1-8] Bu metot eskiden senkron ``time.sleep`` kullanıyordu ve
        async ``scrape_async`` içinden çağrılıyordu. Sonuç: tek bir kazıma
        boyunca TÜM süreç (FastAPI event loop'u, /health, WebSocket telemetrisi,
        diğer kullanıcıların LLM istekleri) 2-5 saniye donuyordu; 3 denemeli
        retry döngüsünde bu 15 saniyeye kadar çıkabiliyordu.
        """
        await asyncio.sleep(random.uniform(2.0, 5.0))

    async def _post_detail_delay(self):
        """[FAZ 1] Post-detay istekleri arası kısa, kibar bekleme (1.0-2.5 sn).

        Profil sayfası nav'inden kısadır çünkü aynı oturumda 12'ye kadar
        istek atılır; toplam süre görev zaman aşımını (varsayılan 300 sn)
        zorlamaz. Event loop kilitlenmez (asyncio.sleep).
        """
        await asyncio.sleep(random.uniform(1.0, 2.5))

    @staticmethod
    def _parse_dt(value: Any) -> Optional[datetime]:
        """[FAZ 1] Tek zaman-parse uygulaması (DRY: grid + detay yolu paylaşır).

        Kabul: unix epoch (sn/ms, int/float/digit-str), ISO-8601.
        Red: bool, None, parse edilemeyen -> None (uydurma yok).
        """
        if isinstance(value, bool) or value is None:
            return None
        if isinstance(value, (int, float)):
            try:
                return datetime.fromtimestamp(float(value), tz=timezone.utc)
            except (ValueError, OSError, OverflowError):
                return None
        if isinstance(value, str):
            if value.isdigit():
                return InstagramGhostScraper._parse_dt(int(value))
            try:
                parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
                return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
            except ValueError:
                return None
        return None

    def _extract_from_html(self, html: str, username: str) -> Dict[str, Any]:
        """
        Instagram'ın sayfa içine gömdüğü JSON'u veya public meta tag'lerini bul.
        """
        patterns = [
            r'window\._sharedData\s*=\s*({.*?});</script>',
            r'"ProfilePage":\s*\[({.*?})\]',
            r'"userData":\s*({.*?}),"',
        ]

        for pattern in patterns:
            match = re.search(pattern, html, re.DOTALL)
            if match:
                try:
                    data = json.loads(match.group(1))
                    return data
                except Exception as e:
                    import logging
                    logging.warning(f"Failed to parse JSON in instagram_ghost: {e}")
                    continue

        # Meta tag fallback (Modern Instagram web sayfaları)
        if "og:description" in html or "og:title" in html:
            return {"_source": "meta_tags"}

        raise InsufficientEvidenceError(f"Instagram HTML'inde JSON bulunamadı: {username} - muhtemelen private veya rate-limit")

    @staticmethod
    def _collect_structured_posts(raw_json: Any) -> List[Dict[str, Any]]:
        """[025] fix: sayfaya gömülü JSON'dan GERÇEK post düğümlerini toplar.

        Sözleşme: caption/taken_at/like_count/comment_count yalnızca düğümde
        gerçekten varsa alınır; eksik alan ASLA tamamlanmaz (None kalır).
        Düğüm hem shortcode hem display_url taşımalıdır;aksi halde regex
        yoluna düşülür.
        [GÖREV 1] Dugumden post_type (__typename/product_type) + video_url
        de alinir; yoksa None kalir (tur varsayilmaz).
        """
        found: List[Dict[str, Any]] = []

        def _caption_of(node: Dict[str, Any]) -> Optional[str]:
            try:
                edges = (node.get("edge_media_to_caption") or {}).get("edges") or []
                if edges:
                    text = ((edges[0] or {}).get("node") or {}).get("text")
                    if isinstance(text, str) and text.strip():
                        return text[:2200]
            except Exception:
                logger.warning('Suppressed exception observed at agent_core/scraper/instagram_ghost.py:216 (pass)')
            cap = node.get("caption")
            if isinstance(cap, dict) and isinstance(cap.get("text"), str) and cap["text"].strip():
                return cap["text"][:2200]
            if isinstance(cap, str) and cap.strip():
                return cap[:2200]
            return None

        def _to_datetime(value: Any) -> Optional[datetime]:
            # [FAZ 1] Tek uygulamaya delege (InstagramGhostScraper._parse_dt);
            # davranış birebir aynı, grid + detay yolu aynı parse'ı kullanır.
            return InstagramGhostScraper._parse_dt(value)

        def _count_of(node: Dict[str, Any], *keys: str) -> Optional[int]:
            for key in keys:
                holder = node.get(key)
                if isinstance(holder, dict):
                    value = holder.get("count")
                    if isinstance(value, int) and not isinstance(value, bool):
                        return value
                elif isinstance(holder, int) and not isinstance(holder, bool):
                    return holder
            return None

        def _post_type_of(node: Dict[str, Any]) -> Optional[str]:
            # [GÖREV 1] product_type reels/clips dogrudan "reel"dir ve
            # __typename'den once gelir (reel dugumu GraphVideo tasir).
            product = node.get("product_type")
            if isinstance(product, str):
                mapped = InstagramGhostScraper._PRODUCT_TYPE_MAP.get(product.lower())
                if mapped:
                    return mapped
            typename = node.get("__typename")
            if isinstance(typename, str):
                return InstagramGhostScraper._TYPENAME_MAP.get(typename)
            return None

        def _video_url_of(node: Dict[str, Any]) -> Optional[str]:
            # [GÖREV 1] Yalniz gercek (http) video URL'i alinir.
            raw = node.get("video_url")
            if isinstance(raw, str) and raw.startswith("http"):
                return raw.replace("\\u0026", "&")
            return None

        def _walk(obj: Any, depth: int = 0) -> None:
            if depth > 14 or len(found) >= 24:
                return
            if isinstance(obj, list):
                for item in obj:
                    _walk(item, depth + 1)
                return
            if not isinstance(obj, dict):
                return
            shortcode = obj.get("shortcode")
            display_url = obj.get("display_url") or obj.get("display_src")
            if (
                isinstance(shortcode, str) and shortcode
                and isinstance(display_url, str) and display_url.startswith("http")
            ):
                raw_taken = obj.get("taken_at_timestamp")
                if raw_taken is None:
                    raw_taken = obj.get("taken_at")
                found.append({
                    "shortcode": shortcode,
                    "display_url": display_url.replace("\\u0026", "&"),
                    "caption": _caption_of(obj),
                    "taken_at": _to_datetime(raw_taken),
                    "like_count": _count_of(obj, "edge_liked_by", "edge_media_preview_like", "like_count"),
                    "comment_count": _count_of(obj, "edge_media_to_comment", "comment_count"),
                    "is_video": bool(obj.get("is_video", False)),
                    "post_type": _post_type_of(obj),
                    "video_url": _video_url_of(obj),
                })
            for value in obj.values():
                _walk(value, depth + 1)

        if isinstance(raw_json, dict) and raw_json.get("_source") != "meta_tags":
            _walk(raw_json)
        return found

    def _parse_real_profile(self, raw_json: Dict[str, Any], html: str, username: str) -> InstagramProfile:
        """
        Ham JSON veya meta tag'leri gerçek Pydantic modele çevirir.
        """
        import html as html_lib

        def _parse_num(val_str: Optional[str]) -> Optional[int]:
            if not val_str:
                return None
            clean = val_str.strip().upper().replace(',', '').replace(' ', '')
            try:
                if clean.endswith('M'):
                    return int(float(clean[:-1]) * 1_000_000)
                elif clean.endswith('K'):
                    return int(float(clean[:-1]) * 1_000)
                else:
                    return int(float(clean))
            except Exception:
                return None

        try:
            is_private = '"is_private":true' in html or '"isPrivate":true' in html or 'Bu hesap gizli' in html or 'This account is private' in html

            follower_count = None
            following_count = None
            post_count = None
            full_name = None
            biography = None

            # 1. Meta Description (Follower & Following & Post Count)
            og_desc_match = re.search(r'<meta property="og:description" content="([^"]*)"', html)
            if og_desc_match:
                og_desc = og_desc_match.group(1)
                fol_m = re.search(r'([\d\.,]+(?:\s*[KMkm])?)\s*(?:Takipçi|Followers)', og_desc, re.IGNORECASE)
                if fol_m:
                    follower_count = _parse_num(fol_m.group(1))
                fing_m = re.search(r'([\d\.,]+(?:\s*[KMkm])?)\s*(?:Takip\b|Following)', og_desc, re.IGNORECASE)
                if fing_m:
                    following_count = _parse_num(fing_m.group(1))
                post_m = re.search(r'([\d\.,]+(?:\s*[KMkm])?)\s*(?:Gönderi|Posts)', og_desc, re.IGNORECASE)
                if post_m:
                    post_count = _parse_num(post_m.group(1))

            # 2. Meta Title (Full Name)
            og_title_match = re.search(r'<meta property="og:title" content="([^"]*)"', html)
            if og_title_match:
                name_m = re.search(r'^(.*?)\s*(?:\(@|•|\-)', og_title_match.group(1))
                if name_m:
                    full_name = name_m.group(1).strip()

            # 3. Bio parse (Multilingual)
            bio_match = re.search(r'<meta\s+content="[^"]*(?:Instagram\'da|on Instagram):\s*&quot;([^&]*)&quot;"', html)
            if bio_match:
                biography = html_lib.unescape(bio_match.group(1).strip())
            elif og_desc_match and " - " in og_desc_match.group(1):
                parts = og_desc_match.group(1).split(" - ", 1)
                if len(parts) > 1 and not parts[1].startswith("See Instagram") and not parts[1].startswith("Instagram fotoğraflarını"):
                    biography = parts[1].strip()

            # 4. Profile Picture
            profile_pic_match = re.search(r'<meta property="og:image" content="([^"]+)"', html) or re.search(r'"profile_pic_url":"([^"]+)"', html)
            profile_pic_url = profile_pic_match.group(1).replace("&amp;", "&").replace("\\u0026", "&") if profile_pic_match else None

            # 5. Postlar ve Görseller
            # [025] fix: gömülü JSON'da gerçek post düğümleri varsa (caption,
            # taken_at, like/comment dahil) onlar kullanılır. Regex yalnızca
            # yapısal düğüm bulunamadığında URL kurtarmak için çalışır; o durumda
            # temporal/engagement alanları dürüstçe None kalır (uydurulmaz).
            posts = []
            for node in self._collect_structured_posts(raw_json)[:12]:
                try:
                    posts.append(InstagramPost(**node))
                except Exception:
                    logger.warning('Suppressed exception observed at agent_core/scraper/instagram_ghost.py:369 (continue)')
                    continue

            if not posts:
                # [GÖREV 1] 1-to-1 dogrulanmis post nesneleri: her gorsel URL'i
                # icin {shortcode, video_url, caption, tur} TEK post nesnesinde
                # birlesir. Capraz-liste eslesmesi (baska postun captionsini/
                #URLsini odunc alma) YASAKTIR.
                #
                # Shortcode kaynaklari (oncelik sirasiyla):
                #   1. Gomulu JSON "shortcode" alanlari (tur bilinmez -> None).
                #   2. /p/<code>/ ve /reel/<code>/ URL'leri (belge sirasinda).
                #      /reel/ tanimi geregi videodur (post_type="reel").
                sc_units: List[tuple] = []  # (start, end, code, kind)
                for m in re.finditer(r'"shortcode":"([A-Za-z0-9_-]+)"', html):
                    sc_units.append((m.start(), m.end(), m.group(1), "json"))
                if not sc_units:
                    for m in re.finditer(r'/p/([A-Za-z0-9_-]+)/', html):
                        sc_units.append((m.start(), m.end(), m.group(1), "post"))
                    for m in re.finditer(r'/reel/([A-Za-z0-9_-]+)/', html):
                        sc_units.append((m.start(), m.end(), m.group(1), "reel"))
                    sc_units.sort(key=lambda u: u[0])
                url_matches = list(re.finditer(r'"display_url":"([^"]+)"', html))

                display_urls = [m.group(1) for m in url_matches]
                url_positions = [m.start() for m in url_matches]

                # Ekstra yüksek çözünürlüklü fotoğraflar
                if not display_urls:
                    for m in re.finditer(r'https://scontent[^\s"\'<>&]+\.jpg[^\s"\'<>]*', html):
                        url = m.group(0).replace("&amp;", "&").replace("\\u0026", "&")
                        if url not in display_urls and ("s150x150" not in url and "s320x320" not in url):
                            display_urls.append(url)
                            url_positions.append(m.start())

                # [GÖREV 1] Video URL adaylari. Yalniz (shortcode, gorsel) span'i
                # ICINDE kalan video o posta aittir; span disi video baska posta
                # odunc verilmez (tek kullanim,tukenince biter).
                video_matches: List[tuple] = []  # (pos, url)
                for m in re.finditer(r'"video_url":"([^"]+)"', html):
                    video_matches.append((
                        m.start(),
                        m.group(1).replace("&amp;", "&").replace("\\u0026", "&"),
                    ))

                # [FAZ 1] Konum bazli shortcode eslesmesi: her gorsel, kendinden
                # once gelen en yakin shortcode ile eslenir (5000 karakter
                # penceresi). Eski index-zip (shortcodes[i] <-> display_urls[i]),
                # listelerden biri eksik/fazla eslestiginde captioni baska
                # postun gorseliyle eslestiriyordu. Belge sirasi korunur;
                # eslesmeyen gorsel kurtarma amacli `post_N` olur.
                # [GÖREV 1] Ayni kural korunur; ek olarak tur (kind) + video_url
                # ayni dogrulanmis birime baglanir.
                _PAIR_WINDOW = 5000
                _used_sc: set = set()
                _used_vid: set = set()
                shortcodes: List[str] = []
                sc_kinds: List[Optional[str]] = []
                post_videos: List[Optional[str]] = []
                _placeholder_n = 0
                for _url_pos in url_positions:
                    _best_idx = -1
                    _best_start = -1
                    for _idx, (_sc_start, _sc_end, _sc_code, _sc_kind) in enumerate(sc_units):
                        if _idx in _used_sc:
                            continue
                        _gap = _url_pos - _sc_start
                        if 0 <= _gap <= _PAIR_WINDOW and _sc_start > _best_start:
                            _best_idx = _idx
                            _best_start = _sc_start
                    if _best_idx >= 0:
                        _used_sc.add(_best_idx)
                        _unit = sc_units[_best_idx]
                        shortcodes.append(_unit[2])
                        sc_kinds.append(_unit[3])
                        _span_start = _unit[0]
                        _vid: Optional[str] = None
                        for _v_i, (_v_pos, _v_url) in enumerate(video_matches):
                            if _v_i in _used_vid:
                                continue
                            if _span_start < _v_pos < _url_pos:
                                _vid = _v_url
                                _used_vid.add(_v_i)
                                break
                        post_videos.append(_vid)
                    else:
                        _placeholder_n += 1
                        shortcodes.append(f"post_{_placeholder_n}")
                        sc_kinds.append(None)
                        post_videos.append(None)

                # Captions are often still present near the shortcode in the
                # rendered HTML. Recover only a uniquely adjacent caption;
                # otherwise keep None rather than guessing across posts.
                # [GÖREV 1] Ayni bitisiklik kurali /p/ ve /reel/ birimleri icin
                # de gecerlidir (pencere: eslesme bitiminden +3000 karakter).
                caption_by_shortcode: Dict[str, str] = {}
                for (_c_start, _c_end, _c_code, _c_kind) in sc_units:
                    shortcode = _c_code
                    if shortcode in caption_by_shortcode:
                        continue
                    window = html[_c_end:_c_end + 3000]
                    caption_match = re.search(
                        r'"edge_media_to_caption":\{"edges":\[\{"node":\{"text":"((?:[^"\\]|\\.)+)"',
                        window,
                    ) or re.search(r'"caption":"((?:[^"\\]|\\.){1,2200})"', window)
                    if caption_match:
                        raw_caption = caption_match.group(1)
                        try:
                            caption = json.loads('"' + raw_caption + '"')
                        except (TypeError, ValueError, json.JSONDecodeError):
                            caption = raw_caption.replace("\\u0026", "&").replace("\\n", "\\n")
                        if isinstance(caption, str) and caption.strip():
                            caption_by_shortcode[shortcode] = caption[:2200].strip()

                for i in range(min(len(display_urls), 12)):
                    try:
                        sc = shortcodes[i] if i < len(shortcodes) else f"post_{i+1}"
                        url = display_urls[i].replace("\\u0026", "&")
                        kind = sc_kinds[i] if i < len(sc_kinds) else None
                        posts.append(InstagramPost(
                            shortcode=sc,
                            display_url=url,
                            caption=caption_by_shortcode.get(sc),
                            is_video=(kind == "reel"),
                            post_type=("reel" if kind == "reel" else None),
                            video_url=post_videos[i] if i < len(post_videos) else None,
                        ))
                    except Exception:
                        logger.warning('Suppressed exception observed at agent_core/scraper/instagram_ghost.py:497 (continue)')
                        continue

            # Eğer private ve post yoksa, sonraki ajanlar boş veriyle halüsinasyon göreceği için durdur
            if is_private and len(posts) == 0:
                raise InsufficientEvidenceError(f"Hedef profil gizli (Private) ve gönderi okunamıyor: {username}")

            profile = InstagramProfile(
                username=username,
                full_name=full_name,
                biography=biography,
                is_private=is_private,
                follower_count=follower_count,
                following_count=following_count,
                post_count=post_count,
                profile_pic_url=profile_pic_url,
                posts=posts,
                evidence_source="self_hosted_ghost_browser"
            )

            # --- ANTI-HALÜSİNASYON KONTROLÜ ---
            # Eğer hem follower yok, hem bio yok, hem post yok -> bu sayfa boş, HALT
            if follower_count is None and biography is None and len(posts) == 0 and not is_private:
                raise InsufficientEvidenceError(f"Instagram profili boş geldi: {username} - rate-limit veya sayfa yapısı değişmiş")

            return profile

        except InsufficientEvidenceError:
            raise
        except Exception as e:
            # Beklenmedik parse hatası -> halüsinasyon yapma, halt et
            raise InsufficientEvidenceError(f"Instagram parse hatası, veri uydurmuyorum: {username} - {str(e)}")

    # ------------------------------------------------------------------ #
    # FAZ 1: post-detay zenginlestirme (caption/tarih/sira)
    # ------------------------------------------------------------------ #
    @staticmethod
    def _extract_post_detail(post_html: str, shortcode: str) -> Dict[str, Any]:
        """Tek post sayfasinin HTML'inden kanit alanlarini cikarir (saf fonksiyon).

        Kaynaklar (oncelik sirasiyla):
        1. Gomulu JSON'da bu shortcode'a ait dugum (taken_at/caption/counts).
        2. JSON-LD `uploadDate|datePublished|dateCreated` -> taken_at,
           JSON-LD `caption` -> caption (yalniz acik `caption` anahtari;
           `description` sablonlu/kirpik olabilir, alinmaz).
        3. `<meta property="article:published_time">` -> taken_at.

        [GÖREV 1] Ayrica: dugumden post_type + video_url; JSON-LD
        @type VideoObject/ImageObject -> post_type (+video ise is_video).

        Sozlesme: bulunan alanlar doner, bulunamayan ASLA uydurulmaz (anahtar
        eksik kalir). Login duvari / "sayfa yok" / shortcode eslesmezse BOS
        dict (yanlis posta ait veri birlestirilmez).
        """
        detail: Dict[str, Any] = {}
        if not post_html or not shortcode or shortcode.startswith("post_"):
            return detail
        # Duvar / yanlis sayfa kontrolleri (profil yoluyla ayni kural).
        if "Login \u2022 Instagram" in post_html or ('name="username"' in post_html and 'name="password"' in post_html):
            return detail
        if "Sorry, this page isn't available" in post_html:
            return detail
        if shortcode not in post_html:
            # Gercel post sayfasi og:url + JSON'da shortcode tasir; yoksa yanlis sayfa.
            return detail

        # 1) Gomulu JSON: yalniz bu shortcode'un dugumu alinir.
        for pattern in (
            r'window\._sharedData\s*=\s*({.*?});</script>',
            r'"ProfilePage":\s*\[({.*?})\]',
            r'"userData":\s*({.*?}),"',
        ):
            match = re.search(pattern, post_html, re.DOTALL)
            if not match:
                continue
            try:
                blob = json.loads(match.group(1))
            except (TypeError, ValueError):
                logger.warning('Suppressed exception observed at agent_core/scraper/instagram_ghost.py:574 (continue)')
                continue
            matched = None
            for node in InstagramGhostScraper._collect_structured_posts(blob):
                if node.get("shortcode") == shortcode:
                    matched = node
                    break
            if matched is not None:
                for key in ("caption", "taken_at", "like_count", "comment_count",
                            "post_type", "video_url"):
                    if matched.get(key) is not None:
                        detail[key] = matched[key]
                if matched.get("is_video"):
                    detail["is_video"] = True
                break

        # 2) JSON-LD: tarih + acik caption.
        if "taken_at" not in detail or "caption" not in detail or "post_type" not in detail:
            for ld_match in re.finditer(
                r'<script[^>]*type="application/ld\+json"[^>]*>(.*?)</script>',
                post_html, re.DOTALL | re.IGNORECASE,
            ):
                try:
                    ld = json.loads(ld_match.group(1).strip())
                except (TypeError, ValueError):
                    logger.warning('Suppressed exception observed at agent_core/scraper/instagram_ghost.py:598 (continue)')
                    continue
                candidates = ld if isinstance(ld, list) else [ld]
                for entry in candidates:
                    if not isinstance(entry, dict):
                        continue
                    if "taken_at" not in detail:
                        for date_key in ("uploadDate", "datePublished", "dateCreated"):
                            parsed = InstagramGhostScraper._parse_dt(entry.get(date_key))
                            if parsed is not None:
                                detail["taken_at"] = parsed
                                break
                    if "caption" not in detail:
                        cap = entry.get("caption")
                        if isinstance(cap, str) and cap.strip():
                            detail["caption"] = cap.strip()[:2200]
                    # [GÖREV 1] JSON-LD @type acik medya turu kanitidir.
                    if "post_type" not in detail:
                        ld_type = {"VideoObject": "video", "ImageObject": "image"}.get(
                            entry.get("@type")
                        )
                        if ld_type:
                            detail["post_type"] = ld_type
                            if ld_type == "video":
                                detail["is_video"] = True

        # 3) article:published_time meta.
        if "taken_at" not in detail:
            pub = re.search(
                r'<meta[^>]*property="article:published_time"[^>]*content="([^"]+)"',
                post_html, re.IGNORECASE,
            )
            if pub:
                parsed = InstagramGhostScraper._parse_dt(pub.group(1))
                if parsed is not None:
                    detail["taken_at"] = parsed
        return detail

    async def _enrich_posts_with_details(self, playwright_page, posts: List[InstagramPost]) -> List[InstagramPost]:
        """[FAZ 1] Grid postlarini tekil post sayfalarindan zenginlestirir.

        - Yalniz eksik alani olan + gercek shortcode'lu postlar ziyaret edilir
          (yer tutucu `post_N` icin URL kurulamaz -> atlanir; tam kanitli
          grid postu tekrar ziyaret edilmez).
        - Post basina TEK deneme; hata/duvar -> post grid verisiyle kalir,
          profil kazimasi ASLA oldurulmez.
        - Birlesme kurali: yalniz None alanlar doldurulur; grid'deki gercek
          degerin ustune yazilmaz. Sira korunur (belge sirasi).
        [GÖREV 1] Detay URL'i /p/<shortcode>/ olarak korunur: IG shortcode
        uzayi tektir (/p/X/ reel shortcode'leri icin de cozulur); ayrica
        hedef URL kilidi (goto sirasi) Faz-1 sozlesmesidir. Birlesmeye
        post_type + video_url eklendi (None-doldurma kurali aynidir).
        """
        if not _post_detail_enabled():
            return posts
        limit = _post_detail_limit()
        if limit <= 0 or not posts:
            return posts

        def _needs_detail(p: InstagramPost) -> bool:
            if p.shortcode.startswith("post_"):
                return False
            return p.taken_at is None or p.caption is None or p.like_count is None

        targets = [(i, p) for i, p in enumerate(posts) if _needs_detail(p)][:limit]
        if not targets:
            return posts

        enriched = list(posts)
        first = True
        for idx, post in targets:
            if not first:
                try:
                    await self._post_detail_delay()
                except Exception:
                    logger.warning('Suppressed exception observed at agent_core/scraper/instagram_ghost.py:672 (pass)')
            first = False
            try:
                await playwright_page.goto(
                    f"{self.base_url}/p/{post.shortcode}/",
                    wait_until="domcontentloaded", timeout=15000,
                )
                post_html = await playwright_page.content()
            except Exception:
                logging.warning(f"Post detay atlandi ({post.shortcode}): nav hatasi")
                continue
            try:
                detail = self._extract_post_detail(post_html, post.shortcode)
            except Exception:
                logger.warning('Suppressed exception observed at agent_core/scraper/instagram_ghost.py:686 (continue)')
                continue
            if not detail:
                continue
            update: Dict[str, Any] = {}
            if post.caption is None and detail.get("caption"):
                update["caption"] = detail["caption"]
            if post.taken_at is None and detail.get("taken_at") is not None:
                update["taken_at"] = detail["taken_at"]
            if post.like_count is None and detail.get("like_count") is not None:
                update["like_count"] = detail["like_count"]
            if post.comment_count is None and detail.get("comment_count") is not None:
                update["comment_count"] = detail["comment_count"]
            if not post.is_video and detail.get("is_video"):
                update["is_video"] = True
            if post.post_type is None and detail.get("post_type"):
                update["post_type"] = detail["post_type"]
            if post.video_url is None and detail.get("video_url"):
                update["video_url"] = detail["video_url"]
            if update:
                try:
                    enriched[idx] = post.model_copy(update=update)
                except Exception:
                    logger.warning('Suppressed exception observed at agent_core/scraper/instagram_ghost.py:708 (continue)')
                    continue
        return enriched

    @staticmethod
    def _sort_chronological(posts: List[InstagramPost]) -> List[InstagramPost]:
        """[GÖREV 1.3] Postlari kronolojik siralar: t_0 -> t_N (artan).

        Stabil siralama: tarihsiz postlar SONA duser ve kendi aralarindaki
        belge sirasi korunur (tarih uydurulmaz, tarihsiz post one cekilmez).
        """
        return sorted(
            posts,
            key=lambda p: (
                p.taken_at is None,
                p.taken_at.timestamp() if p.taken_at is not None else 0.0,
            ),
        )

    async def scrape_async(self, username: str, playwright_page=None) -> InstagramProfile:
        """
        Ana metod - Playwright page dışarıdan verilir (X scraper ile aynı vault izolasyonu)
        Eğer page yoksa, senkron fallback için hata fırlatır - uydurma tarayıcı açmaz.
        """
        if playwright_page is None:
            raise InsufficientEvidenceError("Playwright page verilmedi - hayalet tarayıcı vault'tan gelmeli, kendi kendine açmam")

        target_url = f"{self.base_url}/{username}/"

        html = ""
        max_retries = 3
        for attempt in range(max_retries):
            try:
                # Stealth navigation
                await playwright_page.goto(target_url, wait_until="domcontentloaded", timeout=15000)
                await self._random_delay()
                html = await playwright_page.content()
                break
            except Exception as e:
                err_str = str(e).lower()
                is_transient = any(term in err_str for term in ["timeout", "net::", "reset", "disconnected", "closed", "failed"])
                if not is_transient:
                    logging.error(f"Playwright permanent error on attempt {attempt+1}: {e}")
                    raise InsufficientEvidenceError(f"Scraper kalıcı hatası: {username} - {str(e)}") from e

                logging.warning(f"Playwright transient failure (attempt {attempt+1}/{max_retries}), Reason: {e}")
                if attempt == max_retries - 1:
                    logging.error(f"Playwright final failure after {max_retries} attempts.")
                    raise InsufficientEvidenceError(f"Scraper network timeout/transient hatası: {username} - {str(e)}") from e
                await asyncio.sleep(2)

        # Login duvarı mı?
        if "Login • Instagram" in html or 'name="username"' in html and 'name="password"' in html:
            raise InsufficientEvidenceError(f"Instagram login duvarı: {username} - cookie expired, vault'u yenile")

        # Rate limit duvarı mı?
        if "Try again later" in html or "We restrict certain activity" in html:
            raise InsufficientEvidenceError(f"Instagram rate-limit: {username} - bekle ve tekrar dene")

        raw = self._extract_from_html(html, username)
        profile = self._parse_real_profile(raw, html, username)

        # [FAZ 1] Post-detay zenginlestirme: grid'de eksik kalan caption /
        # taken_at / counts, tekil post sayfalarindan tamamlanir. Bu adim
        # profil kazimasini ASLA oldurmez (hata -> grid verisiyle devam).
        try:
            profile.posts = await self._enrich_posts_with_details(playwright_page, profile.posts)
        except Exception as e:
            logging.warning(f"Post detay zenginlestirme atlandi ({username}): {type(e).__name__}")

        # [GÖREV 1.3] Kronolojik siralama t_0 -> t_N. Zenginlestirmeden SONRA
        # uygulanir (goto sirasi belge sirasinda kalir; sira kilidi bozulmaz).
        profile.posts = self._sort_chronological(profile.posts)

        return profile

    @staticmethod
    def temporal_coverage(profile: InstagramProfile) -> float:
        """[FAZ 1] Tarih tasiyan post orani (0.0-1.0). Post yoksa 0.0."""
        total = len(profile.posts)
        if total == 0:
            return 0.0
        dated = sum(1 for p in profile.posts if p.taken_at is not None)
        return round(dated / total, 3)

    def evaluate_confidence(self, profile: InstagramProfile) -> float:
        """
        Uncertainty Engine için güven skoru.
        Düşükse HALT.
        [FAZ 1] Zamansal bonus: postlarin yarisi+ tarihliyse +0.1.
        Bonus-only'dir: tarihsiz guclu profilin skoru DUSMEZ (mevcut 0.6
        esigi sozlesmeleri korunur), tarihli profil odullendirilir.
        """
        score = 0.0
        if profile.follower_count is not None:
            score += 0.2
        if profile.biography:
            score += 0.2
        if len(profile.posts) >= 3:
            score += 0.4
        elif len(profile.posts) >= 1:
            score += 0.2
        if profile.posts and self.temporal_coverage(profile) >= 0.5:
            score += 0.1

        if profile.is_private:
            score = min(score, 0.4)  # Private ise max 0.4 - yetersiz kanıt

        # Eğer skor < 0.6 ise, task_executor bunu halt etmeli
        return round(min(score, 1.0), 2)
