## Ne değişti?

<!-- Tek cümle: bu PR ne yapıyor? -->

## Neden?

<!-- Hangi sorun/issue? (varsa #numara) -->

## Kapılar

- [ ] `ruff check .` temiz
- [ ] `pytest -q --cov=agent_core --cov=backend --cov-fail-under=80` yeşil
- [ ] `cd frontend && npm run check && npm run build` yeşil
- [ ] `scripts/dead_code_audit.py` + `scripts/audit_regression.py` yeşil
- [ ] Sayı değiştiyse README güncellendi (`test_readme_claims.py` kilitli)
- [ ] Dosya eklendi/silindiyse `docs/envanter.html` yenilendi
- [ ] `backend/api.py` 5760 satır tavanının altında
