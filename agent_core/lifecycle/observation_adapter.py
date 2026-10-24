"""Observation Adapter - Raw Profile Data to Canonical Signal Observations.

Mevcut target_profile ve TaskSnapshot verilerini tip güvenli SignalObservation listesine dönüştürür.
Eksik, geleceğe ait (future timestamp) veya indirilemeyen görsel verilerini güvenle işler.
Ölçülemeyen görselleri asla sıfır saymaz (not_measurable bayrağı atar).
"""

from __future__ import annotations

from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional, Union
from agent_core.lifecycle.baseline_builder import SignalObservation

# Gelecek zaman tavanı (saat kaymaları için 1 gün tolerans)
MAX_FUTURE_DRIFT = timedelta(days=1)


def _parse_iso(t: Any) -> Optional[datetime]:
    if isinstance(t, datetime):
        return t if t.tzinfo else t.replace(tzinfo=timezone.utc)
    if not isinstance(t, str) or not t.strip():
        return None
    try:
        parsed = datetime.fromisoformat(t.strip().replace("Z", "+00:00"))
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    except ValueError:
        return None


class ObservationAdapter:
    """Hedef verisini veya TaskSnapshot çıktısını zaman serisi sinyal gözlemlerine dönüştürür."""

    def extract(self, target_data: Union[Dict[str, Any], Any]) -> List[SignalObservation]:
        data: Dict[str, Any] = {}
        if hasattr(target_data, "model_dump"):
            data = target_data.model_dump()
        elif isinstance(target_data, dict):
            data = target_data
        else:
            return []

        observations: List[SignalObservation] = []
        posts = data.get("posts") or []
        post_times = data.get("post_times") or []
        posts_with_media = data.get("posts_with_media") or []
        now_utc = datetime.now(timezone.utc)

        # 1. Zamanlama Sinyalleri (Timing)
        for idx, t_str in enumerate(post_times):
            dt = _parse_iso(t_str)
            ref = f"post_{idx}"
            if not dt:
                continue

            status = "measured"
            if dt > now_utc + MAX_FUTURE_DRIFT:
                status = "invalid"

            hour = float(dt.hour) + float(dt.minute) / 60.0
            is_night = 1.0 if (hour >= 23.0 or hour < 6.0) else 0.0

            observations.append(SignalObservation(
                signal_id="timing.post_hour",
                timestamp=dt,
                value=hour,
                source_ref=ref,
                measurement_status=status,
                signal_family="timing",
            ))
            observations.append(SignalObservation(
                signal_id="timing.is_night_post",
                timestamp=dt,
                value=is_night,
                source_ref=ref,
                measurement_status=status,
                signal_family="timing",
            ))

        # 2. Metin Sinyalleri (Text)
        for idx, text in enumerate(posts):
            if idx >= len(post_times):
                break
            dt = _parse_iso(post_times[idx])
            if not dt:
                continue
            ref = f"post_{idx}"
            status = "invalid" if dt > now_utc + MAX_FUTURE_DRIFT else "measured"
            text_str = str(text) if text else ""

            observations.append(SignalObservation(
                signal_id="text.char_length",
                timestamp=dt,
                value=float(len(text_str)),
                source_ref=ref,
                measurement_status=status,
                signal_family="text",
            ))
            words = text_str.split()
            observations.append(SignalObservation(
                signal_id="text.word_count",
                timestamp=dt,
                value=float(len(words)),
                source_ref=ref,
                measurement_status=status,
                signal_family="text",
            ))

        # 3. Görsel / Medya Sinyalleri (Kare bazlı görsel kanıt akışı)
        for p in posts_with_media:
            dt = _parse_iso(p.get("timestamp"))
            if not dt:
                continue
            ref = str(p.get("post_id", "media"))
            status = "invalid" if dt > now_utc + MAX_FUTURE_DRIFT else "measured"

            # Görsel indirilemedi veya bozuksa: not_measurable bayrağı ile işaretle
            is_downloadable = p.get("is_downloadable", True)
            if not is_downloadable or p.get("download_error"):
                observations.append(SignalObservation(
                    signal_id="visual.is_daylight",
                    timestamp=dt,
                    value=0.0,
                    source_ref=ref,
                    measurement_status="not_measurable",
                    signal_family="visual",
                ))
                continue

            if "is_daylight" in p:
                observations.append(SignalObservation(
                    signal_id="visual.is_daylight",
                    timestamp=dt,
                    value=1.0 if p["is_daylight"] else 0.0,
                    source_ref=ref,
                    measurement_status=status,
                    signal_family="visual",
                ))
            if "is_isolated" in p:
                observations.append(SignalObservation(
                    signal_id="visual.is_isolated",
                    timestamp=dt,
                    value=1.0 if p["is_isolated"] else 0.0,
                    source_ref=ref,
                    measurement_status=status,
                    signal_family="visual",
                ))
            if "is_staged" in p:
                observations.append(SignalObservation(
                    signal_id="media.is_authored_or_staged",
                    timestamp=dt,
                    value=1.0 if p["is_staged"] else 0.0,
                    source_ref=ref,
                    measurement_status=status,
                    signal_family="media",
                ))

        return sorted(observations, key=lambda o: (o.timestamp, o.signal_id))
