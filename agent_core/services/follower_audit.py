"""Takipçi/kitle denetimi — saf deterministik aritmetik (LLM'siz).

``audit_followers`` takipçi sayısı, takip edilen sayısı ve gönderilerden
oransal/örüntüsel sinyaller üretir (``FollowerAuditReport``). LLM çağrısı ve
rastgelelik YOKTUR; aynı girdi her zaman aynı çıktıyı verir, bu yüzden
mühürlenebilir kanıt sayılır.

Eksik/aykırı girdi "sahte kitle" diye YORUMLANMAZ: yalnız ölçülen oran ve
güven raporlanır.
"""

from typing import Dict, List, Any, Optional
from pydantic import BaseModel, ConfigDict

class FollowerAuditReport(BaseModel):
    follower_count: int = 0
    following_count: Optional[int] = None  # [024] None = ölçülmedi (0 ölçümdür)
    post_count: int = 0
    median_likes: Optional[float] = None
    median_comments: Optional[float] = None
    engagement_rate: Optional[float] = None
    expected_rate_range: str = "N/A"
    verdict: str = "BİLİNMİYOR"  # SAĞLIKLI, ŞÜPHELİ, ŞİŞİRME ŞÜPHESİ, VERİ YETERSİZ
    # W2: makine-okunur sözleşme — UI Turkce metin eslemek yerine bunu okur.
    verdict_code: str = "unknown"  # healthy | suspicious | inflated | insufficient | unknown
    evidence: List[str] = []
    data_completeness: float = 0.0
    model_config = ConfigDict(extra="allow")

def audit_followers(follower_count: int, following_count: Optional[int], posts: List[Dict[str, Any]]) -> FollowerAuditReport:
    """
    Deterministik aritmetik takipçi ve kitle denetimi.
    LLM veya sübjektif yorum içermez; saf formül ile çalışır.
    """
    if follower_count <= 0:
        return FollowerAuditReport(
            follower_count=follower_count,
            following_count=following_count,
            verdict="VERİ YETERSİZ",
            verdict_code="insufficient",
            evidence=["Takipçi sayısı 0 veya eksik."],
            data_completeness=0.0
        )

    # Beğeni ve yorum sayılarını topla
    likes = [p.get("like_count") for p in posts if p.get("like_count") is not None]
    comments = [p.get("comment_count") for p in posts if p.get("comment_count") is not None]

    evidence = []
    # [024] fix: following ölçülmediyse "0" yazmak sahte ölçümdür; ölçülmedi denir.
    following_str = "ölçülmedi" if following_count is None else str(following_count)
    evidence.append(f"Toplam Takipçi: {follower_count}, Takip Edilen: {following_str}, İncelenen Post: {len(posts)}")

    if not likes:
        # Beğeni sayıları gizli veya anonim kazımada gelmedi
        return FollowerAuditReport(
            follower_count=follower_count,
            following_count=following_count,
            post_count=len(posts),
            verdict="VERİ YETERSİZ (GİZLİ ETKİLEŞİM)",
            verdict_code="insufficient",
            evidence=evidence + ["Post beğeni sayıları herkese açık değil veya çekilemedi; etkileşim oranı hesaplanamadı."],
            data_completeness=0.3
        )

    def _median(lst):
        s = sorted(lst)
        n = len(s)
        return s[n//2] if n % 2 != 0 else (s[n//2 - 1] + s[n//2]) / 2.0

    med_likes = _median(likes)
    med_comm = _median(comments) if comments else 0.0
    eng_rate = round(((med_likes + med_comm) / follower_count) * 100, 2)

    # Takipçi baremine göre beklenen organik oranlar
    if follower_count < 5000:
        exp_range = "%2.0 - %8.0"
        min_healthy = 1.5
    elif follower_count < 25000:
        exp_range = "%1.0 - %5.0"
        min_healthy = 0.8
    elif follower_count < 100000:
        exp_range = "%0.7 - %3.5"
        min_healthy = 0.5
    else:
        exp_range = "%0.4 - %2.0"
        min_healthy = 0.3

    evidence.append(f"Medyan Beğeni: {med_likes}, Medyan Yorum: {med_comm}")
    evidence.append(f"Hesaplanan Etkileşim Oranı: %{eng_rate} (Beklenen Organik Aralık: {exp_range})")

    if eng_rate < (min_healthy * 0.3):
        verdict = "ŞİŞİRME ŞÜPHESİ YÜKSEK (BOT/SATIN ALINMIŞ TAKİPÇİ)"
        verdict_code = "inflated"
        evidence.append(f"Kritik Uyarı: Etkileşim oranı beklenen eşiğin (%{min_healthy}) çok altında. Kitle organik olmayabilir.")
    elif eng_rate < min_healthy:
        verdict = "ŞÜPHELİ / DÜŞÜK ETKİLEŞİM"
        verdict_code = "suspicious"
        evidence.append("Uyarı: Takipçi sayısına kıyasla beğeni hacmi düşük.")
    else:
        verdict = "SAĞLIKLI / ORGANİK GÖRÜNÜYOR"
        verdict_code = "healthy"
        evidence.append("Kitle etkileşimi organik standartlarla uyumlu.")

    return FollowerAuditReport(
        follower_count=follower_count,
        following_count=following_count,
        post_count=len(posts),
        median_likes=med_likes,
        median_comments=med_comm,
        engagement_rate=eng_rate,
        expected_rate_range=exp_range,
        verdict=verdict,
        verdict_code=verdict_code,
        evidence=evidence,
        data_completeness=1.0
    )
