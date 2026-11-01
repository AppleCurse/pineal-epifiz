"""Medya kökeni kapısı — "kurgu mu, sızıntı mı?" sorusunun tek cevap yeri.

Neden (denetim 2026-10-24 · "sırtındaki bıçağı kendi yapıştıran adam" bulgusu):
    Aynı hesabın 2022'deki ev karelerinde arka plandaki koltuk/kitaplık/çocuk
    KADRAJA KONMAMIŞTIR — sızıntıdır. 2026'daki siyah stüdyo karesinde bıçak,
    maske, kanat KENDİSİ tarafından kompoze edilmiştir — vitrindir. İkisini
    ayırmayan bir hat, "oda karardı, yalnızlaştı" der; oysa ölçülebilen şey
    "kurgulanmış üretim oranı arttı"dır.

Kapı üç eksen besler (ve yalnız beslediği ekseni besler):
    * ``feeds_habitat`` → yalnız GERÇEK, kurgulanmamış ve ÖLÇÜLEBİLİR arka plan.
    * ``feeds_somatic`` → gerçek çekim (stüdyo dahil): yüz gerçektir, bakış
      ölçülebilir. Montaj/sentetik karede yüz YÖNETİLMİŞ olduğu için okunmaz.
    * ``feeds_authored`` → kurgu ekseni: "üretim biçimi" kendi başına bir
      sinyaldir, yaşam koşulu değişimi olarak OKUNMAZ.

Fail-closed: hiçbir kanıt yoksa ``unknown`` döner ve HİÇBİR yaşam eksenini
beslemez. "Emin olamadım" bilgisi kaybolmaz (``evidence`` alanında saklanır).

Not: platform (Instagram vb.) görselleri yeniden kodlarken EXIF'i siler; bu
yüzden kamera metadata'sı YOKLUĞU "kurgu" sayılmaz — yalnız kanıt sayılmaz.

Tüketici: ``agent_core.lifecycle.observation_adapter.VisualFrameExtractor``.
Test: ``tests/lifecycle/test_lifecycle_media_provenance.py``.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Literal, Mapping, Optional

CaptureClass = Literal[
    "camera_incidental",  # gerçek çekim, ölçülebilir arka plan → habitat + somatik
    "camera_staged",  # gerçek çekim, arka plan ölçülemez (stüdyo) → yalnız somatik
    "edited_composite",  # montaj / ağır retouch → yalnız kurgu ekseni
    "synthetic_or_render",  # üretilmiş görsel → yalnız kurgu ekseni
    "unknown",  # karar verilemedi → hiçbir eksen (fail-closed)
]

#: Arka plan varyansı bunun altındaysa "ölçülecek arka plan yok" (düz duvar/stüdyo).
BACKGROUND_VARIANCE_FLOOR = 25.0
#: Kenar yoğunluğu bunun altındaysa arka planda yapı yok.
BACKGROUND_EDGE_FLOOR = 0.004

_EDITOR_SOFTWARE = re.compile(
    r"photoshop|lightroom|affinity|gimp|canva|picsart|snapseed|facetune|remini|vsco",
    re.IGNORECASE,
)
_SYNTH_SOFTWARE = re.compile(
    r"midjourney|stable\s*diffusion|dall-?e|firefly|comfyui|automatic1111|flux|imagen",
    re.IGNORECASE,
)
_AUTHORED_TAGS = re.compile(
    r"#(digitalart|digitalartist|edit|edited|photoshop|aiart|concept|conceptart|artwork|"
    r"manipulation|composite|photomanipulation|cgi|render|3dart|surreal)",
    re.IGNORECASE,
)

__all__ = [
    "BACKGROUND_EDGE_FLOOR",
    "BACKGROUND_VARIANCE_FLOOR",
    "BackgroundStats",
    "CaptureClass",
    "MediaProvenance",
    "classify_media",
    "measure_background",
]


@dataclass(frozen=True)
class BackgroundStats:
    """Arka planın ölçülebilirliği (yüz maskelendikten sonra kalan alan)."""

    variance: float
    edge_density: float
    sampled_pixels: int = 0

    @property
    def has_measurable_background(self) -> bool:
        return self.sampled_pixels > 0 and (
            self.variance >= BACKGROUND_VARIANCE_FLOOR and self.edge_density >= BACKGROUND_EDGE_FLOOR
        )


@dataclass(frozen=True)
class MediaProvenance:
    """Tek bir medyanın kökeni ve hangi ekseni besleyebileceği."""

    media_ref: str
    capture_class: CaptureClass
    has_measurable_background: bool
    background_variance: float = 0.0
    background_edge_density: float = 0.0
    evidence: tuple[str, ...] = ()

    @property
    def feeds_habitat(self) -> bool:
        return self.capture_class == "camera_incidental" and self.has_measurable_background

    @property
    def feeds_somatic(self) -> bool:
        return self.capture_class in ("camera_incidental", "camera_staged")

    @property
    def feeds_authored(self) -> bool:
        return self.capture_class in ("edited_composite", "synthetic_or_render")


def _software_of(exif: Optional[Mapping[str, Any]]) -> str:
    if not exif:
        return ""
    for key in ("Software", "software", "ProcessingSoftware"):
        value = exif.get(key)
        if value:
            return str(value)
    return ""


def classify_media(
    media_ref: str,
    *,
    exif: Optional[Mapping[str, Any]] = None,
    caption: Optional[str] = None,
    background: Optional[BackgroundStats] = None,
) -> MediaProvenance:
    """Medyanın hangi ekseni besleyebileceğini belirler (fail-closed).

    Sıralama kanıt gücüne göredir: üretim yazılımı > beyan edilmiş kurgu etiketi
    > düzenleme yazılımı > ölçülen arka plan > bilinmiyor.
    """
    evidence: list[str] = []
    software = _software_of(exif)
    variance = float(background.variance) if background else 0.0
    edge = float(background.edge_density) if background else 0.0
    measurable_bg = bool(background and background.has_measurable_background)

    def _make(capture_class: CaptureClass, has_bg: bool) -> MediaProvenance:
        return MediaProvenance(
            media_ref=media_ref,
            capture_class=capture_class,
            has_measurable_background=has_bg,
            background_variance=variance,
            background_edge_density=edge,
            evidence=tuple(evidence),
        )

    if software and _SYNTH_SOFTWARE.search(software):
        evidence.append(f"synth_software={software}")
        return _make("synthetic_or_render", measurable_bg)

    if caption and _AUTHORED_TAGS.search(caption):
        evidence.append(f"authored_tag={_AUTHORED_TAGS.search(caption).group(0).lower()}")
        return _make("edited_composite", measurable_bg)

    if software and _EDITOR_SOFTWARE.search(software):
        evidence.append(f"editor_software={software}")
        return _make("edited_composite", measurable_bg)

    if measurable_bg:
        evidence.append(f"background_measurable(var={variance:.1f},edge={edge:.4f})")
        if exif and (exif.get("Make") or exif.get("Model")):
            evidence.append("camera_metadata")
        return _make("camera_incidental", True)

    if background is not None:
        # Ölçüm YAPILDI ve arka plan yok: stüdyo/düz fon. Çekim gerçek olabilir,
        # ama habitat ÖLÇÜLEMEZ — "oda kararmış" diye okunamaz.
        evidence.append(f"background_not_measurable(var={variance:.1f},edge={edge:.4f})")
        return _make("camera_staged", False)

    evidence.append("no_provenance_signal")
    return _make("unknown", False)


def measure_background(
    image_path: str, face_box: Optional[tuple[int, int, int, int]] = None
) -> Optional[BackgroundStats]:
    """Arka plan varyansı/kenar yoğunluğu (yüz maskelenir, kırpılmaz).

    OpenCV yoksa ``None`` döner: ölçüm yapılmadığı AÇIKÇA bellidir ve sayı
    uydurulmaz (fail-closed). Yüzü kırpıp atmıyoruz — yalnız maskeliyoruz,
    çünkü ölçmek istediğimiz şey yüzün ARKASINDA kalan hayat.
    """
    try:
        import cv2  # type: ignore
        import numpy as np  # type: ignore
    except Exception:  # pragma: no cover - opsiyonel bağımlılık
        return None

    image = cv2.imread(image_path)
    if image is None:
        return None

    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    mask = np.ones(gray.shape, dtype=bool)
    if face_box:
        x, y, w, h = face_box
        pad = int(0.25 * max(w, h))
        y0, y1 = max(0, y - pad), min(gray.shape[0], y + h + pad)
        x0, x1 = max(0, x - pad), min(gray.shape[1], x + w + pad)
        mask[y0:y1, x0:x1] = False

    background_pixels = gray[mask]
    if background_pixels.size < 1000:
        return BackgroundStats(variance=0.0, edge_density=0.0, sampled_pixels=int(background_pixels.size))

    edges = cv2.Canny(gray, 100, 200)
    return BackgroundStats(
        variance=float(np.var(background_pixels)),
        edge_density=float(np.mean(edges[mask] > 0)),
        sampled_pixels=int(background_pixels.size),
    )
