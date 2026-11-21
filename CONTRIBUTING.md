# Katkıda Bulunma

Pineal Epifiz'e katkı için temel kurallar. Proje dili **Türkçe**dir; kod
yorumları ve dokümanlar Türkçe yazılır.

## Kurulum

```bash
python3.11 -m venv .venv
.venv/bin/pip install -r requirements.lock ruff pytest pytest-asyncio pytest-cov pytest-timeout
cd frontend && npm ci
```

## Kapılar (PR öncesi hepsi yeşil olmalı)

```bash
.venv/bin/ruff check .
.venv/bin/python -m pytest tests -q --cov=agent_core --cov=backend --cov-fail-under=80
cd frontend && npm run check && npm run build
.venv/bin/python scripts/dead_code_audit.py
.venv/bin/python scripts/audit_regression.py
```

CI aynı komutları koşar (`.github/workflows/ci.yml`).

## Değiştirilemez kurallar

1. **`backend/api.py` tavanı 5760 satırdır.** Yeni uç eklemek yerine modül
   çıkar (`tests/unit/test_api_monolith_ratchet.py` kilitler). Tavanı
   yükseltmek istiyorsan gerekçeyi `docs/reports/API_MONOLITH_SPLIT_PLAN.md`'ye
   yaz.
2. **README'deki sayılar testle kilitlidir.** Ajan/yetenek/uç/dosya sayısı
   değişirse `tests/unit/test_readme_claims.py` kırmızıya döner — README'yi
   aynı PR'da güncelle.
3. **Uydurma veri yok.** Yetenekler araç yoksa `availability()` ile dürüstçe
   kapalı döner; kanıt yoksa panel doldurulmaz. Sahte çalıştırıcı/test
   verisi üretim yoluna karışmaz.
4. **Envanter bayatlamaz.** Dosya ekleyip/silince
   `python scripts/generate_inventory_page.py` ile `docs/envanter.html`'i
   yenile; CI `--check` ile yakalar.
5. **Ölü kod yok.** Yeni modül eklerken çağrı yerini de ekle;
   `scripts/dead_code_audit.py` kapıdır.

## Süreç

- Küçük düzeltmeler: doğrudan PR aç.
- Yeni yetenek/ajan: önce issue aç, `availability()` sözleşmesini ve
  kapı bayrağını (`ENABLE_*`) tanımla.
- Güvenlik açığı bulursan: **herkese açık issue açma** —
  [SECURITY.md](SECURITY.md)'ye bak.
