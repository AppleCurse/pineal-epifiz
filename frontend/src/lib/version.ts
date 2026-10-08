/**
 * Uygulama sürümünün TEK kaynağı: depo kökündeki `VERSION` dosyası.
 *
 * [AUDIT 2026-10-07 · Madde 2] Sürüm kimliği depoya dağılmıştı: `main.ts`
 * içinde `v5.0`, `tauriBridge.ts` içinde `5.0.0` yazılıydı — oysa kök
 * `VERSION` dosyası `3.0.0-rc.2` diyordu. Üç ayrı gerçeklik.
 *
 * Buradaki sabit kopya DEĞİLDİR: `tests/unit/test_version_identity.py`
 * bu değeri kök `VERSION` dosyası ile karşılaştırır ve saparsa CI kırılır.
 * Sürüm yükseltmede önce kök `VERSION` dosyasını, sonra bu satırı güncelle.
 */
export const APP_VERSION = '3.0.0-rc.2'

/** İmza dizesi (CI: `grep -q "PINEAL-HERETIC" dist/assets/*.js` ile doğrular). */
export const APP_SIGNATURE = `PINEAL-HERETIC v${APP_VERSION} - ATLAS PINEAL OBSERVATORY`
