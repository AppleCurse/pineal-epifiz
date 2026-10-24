#!/usr/bin/env python3
"""UYANDIR — kapıları aç, ama ne olacağını ÖNCE söyle.

Sorun: "hepsini açalım" cümlesi tek bir dosyaya `true` yazmak gibi görünür,
oysa ölçüm başka bir şey söylüyor — kapıyı açmak, kütüphanesi kurulu olmayan
bir yeteneği ÇALIŞTIRMAZ. Bu betik o farkı kapatır:

  1. Yetenek defterini **bu makinede** iki senaryoda ölçer
     (şalterler kapalı / şalterler açık).
  2. Her yeteneği bir uyanma sınıfına koyar:
        hazır           → şu an çalışıyor
        sadece_kapi     → şalteri açınca GERÇEKTEN uyanır
        kurulum_gerekli → şalter açılsa da eksik kütüphane/motor/uç var
  3. `--uygula` ile seçilen grubun `ENABLE_*` satırlarını `.env` dosyasına
     yazar (varsa `true`/`false` değerini değiştirir, yoksa ekler).
     `.env` yoksa `.env.example`'dan kopyalayarak başlar; mevcut dosya
     `*.bak-<zaman>` olarak YEDEKLENİR.
  4. Yazdıktan sonra "ne açıldı, ne AÇILMADI ve neden" tablosunu basar.

GÜVENLİK:
  * Varsayılan **kuru çalışma** (dry-run). Dosyaya yazmak için `--uygula`.
  * Yalnız `ENABLE_*` anahtarlarına dokunur; hiçbir gizli değer okunmaz/yazılmaz.
  * Kasa (vault) mandalı ve çocuk kilidi bu betikle DEĞİŞTİRİLEMEZ — onlar
    çalışma anındaki oda durumudur, env kapısı değildir.

Kullanım::

    python scripts/uyandir.py                  # plan (hiçbir şey yazmaz)
    python scripts/uyandir.py --uygula guvenli # sadece şalterle uyananlar
    python scripts/uyandir.py --uygula hepsi   # 17 kapının tamamı
    python scripts/uyandir.py --uygula ENABLE_MAIGRET,ENABLE_HOLEHE
"""

from __future__ import annotations

import argparse
import os
import re
import shutil
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Tuple

REPO = Path(__file__).resolve().parents[1]
ENV = REPO / ".env"
ENV_EXAMPLE = REPO / ".env.example"
FLAG_LINE_RE = re.compile(r"^\s*(ENABLE_[A-Z0-9_]+)=(.*)$")
#: Değeri YERİNDE değiştirir: hizalanmış yorumlar ve boşluklar bozulmaz
#: (`ENABLE_X=false       # not` → `ENABLE_X=true        # not`).
FLAG_VALUE_RE = re.compile(r"^(\s*)(ENABLE_[A-Z0-9_]+)=[^\s#]*(.*)$")


def _bootstrap():
    sys.path.insert(0, str(REPO))
    from agent_core.capabilities.policy import MANAGED_GATE_FLAGS
    from agent_core.capabilities.registry import bootstrap

    return MANAGED_GATE_FLAGS, bootstrap


def measure() -> Tuple[List[dict], List[str]]:
    """Yetenekleri iki senaryoda ölç (kapalı / tüm kapılar açık)."""
    managed, bootstrap = _bootstrap()
    closed = bootstrap()
    saved = {flag: os.environ.get(flag) for flag in managed}
    #: "ŞİMDİ" ölçümü env değiştirilmeden ÖNCE alınır; aksi hâlde kapılar açık
    #: sanılır ve rapor yalan söyler (bu hata gerçekten bir kez yapıldı).
    now_rows: Dict[str, object] = {}
    for cid in sorted(closed.ids()):
        now_rows[cid] = closed.get(cid).availability()
    try:
        for flag in managed:
            os.environ[flag] = "true"
        opened = bootstrap()
        rows = []
        for cid in sorted(closed.ids()):
            now = now_rows[cid]
            later = opened.get(cid).availability()
            cap = closed.get(cid)
            gates = sorted(g for g in (capture_gates(cap)) if g in set(managed))
            if now.available:
                klass = "hazır"
            elif later.available:
                klass = "sadece_kapi"
            else:
                klass = "kurulum_gerekli"
            rows.append(
                {
                    "id": cid,
                    "gates": gates,
                    "kclass": klass,
                    "reason_now": now.reason,
                    "reason_open": later.reason,
                }
            )
    finally:
        for flag, value in saved.items():
            if value is None:
                os.environ.pop(flag, None)
            else:
                os.environ[flag] = value
    return rows, list(managed)


def capture_gates(cap) -> List[str]:
    return list(getattr(cap, "gates", ()) or ())


def plan_text(rows: List[dict]) -> str:
    by_class: Dict[str, List[dict]] = {}
    for row in rows:
        by_class.setdefault(row["kclass"], []).append(row)
    lines = []
    lines.append(f"hazır            : {len(by_class.get('hazır', []))}")
    lines.append(f"sadece_kapi      : {len(by_class.get('sadece_kapi', []))}  (şalteri açınca gerçekten uyanır)")
    lines.append(f"kurulum_gerekli  : {len(by_class.get('kurulum_gerekli', []))}  (şalter açılsa da çalışmaz)")
    for klass in ("sadece_kapi", "kurulum_gerekli"):
        if not by_class.get(klass):
            continue
        lines.append("")
        lines.append(f"--- {klass} ---")
        for row in by_class[klass]:
            gates = ", ".join(row["gates"]) or "kapı yok"
            reason = row["reason_open"] or row["reason_now"] or "-"
            lines.append(f"  {row['id']:34} | {gates:26} | {reason}")
    return "\n".join(lines)


def select_flags(rows: List[dict], managed: List[str], target: str) -> List[str]:
    """Hedef grubu env kapı listesine çevir."""
    target = (target or "").strip()
    if target == "guvenli":
        wanted = [row["id"] for row in rows if row["kclass"] == "sadece_kapi"]
    elif target == "hepsi":
        return sorted(managed)
    elif target:
        explicit = {t.strip() for t in target.split(",") if t.strip()}
        if not explicit <= set(managed):
            unknown = sorted(explicit - set(managed))
            raise SystemExit(f"bilinmeyen kapı: {', '.join(unknown)} (yönetilen kapılar: {', '.join(sorted(managed))})")
        return sorted(explicit)
    else:
        raise SystemExit("hedef belirtilmedi: guvenli | hepsi | ENABLE_X,ENABLE_Y")

    flags = set()
    for cid in wanted:
        row = next(r for r in rows if r["id"] == cid)
        flags.update(row["gates"])
    return sorted(flags)


def write_env(flags: List[str], path: Path | None = None) -> Tuple[Path, Path | None, List[str]]:
    """`.env` dosyasına kapıları yaz. Dönen: (yol, yedek, eklenen satırlar).

    ``path`` yalnız testler için verilir (gerçek dosyaya dokunmadan yazma
    davranışını kilitlemek adına); üretimde her zaman depo kökündeki `.env`.
    """
    path = path or ENV
    backup = None
    if path.exists():
        backup = path.with_name(f"{path.name}.bak-{datetime.now().strftime('%Y%m%d-%H%M%S')}")
        shutil.copy2(path, backup)
        text = path.read_text(encoding="utf-8")
    elif ENV_EXAMPLE.exists():
        text = ENV_EXAMPLE.read_text(encoding="utf-8")
    else:
        text = "# Pineal ortam dosyası (uyandir.py tarafından oluşturuldu)\n"

    lines = text.splitlines()
    added: List[str] = []
    seen = set()
    for i, line in enumerate(lines):
        m = FLAG_LINE_RE.match(line.strip())
        if not m:
            continue
        name = m.group(1)
        seen.add(name)
        if name in flags:
            vm = FLAG_VALUE_RE.match(line)
            if vm:
                lines[i] = f"{vm.group(1)}{vm.group(2)}=true{vm.group(3)}"
    for flag in flags:
        if flag not in seen:
            lines.append(f"{flag}=true")
            added.append(flag)

    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path, backup, added


def main() -> int:
    ap = argparse.ArgumentParser(description="Kapıları aç ve ne olacağını önce söyle.")
    ap.add_argument("--uygula", metavar="HEDEF", help="guvenli | hepsi | ENABLE_A,ENABLE_B")
    ap.add_argument("--liste", action="store_true", help="yalnız planı göster (varsayılan)")
    args = ap.parse_args()

    rows, managed = measure()
    print(f"yönetilen kapı: {len(managed)}")
    print(plan_text(rows))

    if not args.uygula:
        print()
        print("KURU ÇALIŞMA — hiçbir dosya yazılmadı.")
        print("Yazmak için: python scripts/uyandir.py --uygula guvenli")
        return 0

    flags = select_flags(rows, managed, args.uygula)
    if not flags:
        print("\nseçilen grupta açılacak kapı yok — hiçbir şey yazılmadı.")
        return 0

    path, backup, added = write_env(flags)
    print()
    print(f"yazıldı: {path}")
    if backup:
        print(f"yedek  : {backup}")
    print(f"açılan kapılar ({len(flags)}): {', '.join(flags)}")
    if added:
        print(f"dosyada yoktu, eklendi: {', '.join(added)}")
    print()
    print("Beklenen sonuç: yalnız 'sadece_kapi' sınıfındaki yetenekler uyanır.")
    print("Kalanlar için gereken kurulum: python scripts/golge_denetimi.py → 'Uyanma planı'.")
    print("Doğrulama: python scripts/golge_denetimi.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
