# Dal (Branch) Temizlik Rehberi

Projede şu anda ana dalımız (`main`) dışında, geçmişte yapılan çalışmalardan veya yapay zeka ajanlarının denemelerinden kalan birçok "çöp" dal bulunuyor. Bu dallar kod karmaşasına sebep olur.

Aşağıdaki dallar **eski deneme dallarıdır (arena/... ve fix/... serisi)** ve projenin sağlıklı gelişimi için Github üzerinden silinmeleri gerekir:

- `arena/01a07f2a-pineal-clean`
- `arena/01a08e47-pineal-clean`
- `arena/01a0920b-pineal-clean`
- `arena/01a098e1-pineal-clean`
- `arena/01a0b318-pineal-clean`
- `arena/01a0b34e-pineal-clean`
- `arena/01a0c190-pineal-clean`
- `arena/01a0c336-pineal-clean`
- `arena/01a0c35d-pineal-clean`
- `arena/01a0c3e1-pineal-clean`
- `arena/01a0c461-pineal-clean`
- `arena/01a0cd94-pineal-epifiz`
- `arena/01a0cece-pineal-epifiz`
- `arena/01a0dbeb-pineal-epifiz`
- `arena/01a0de24-pineal-epifiz`
- `arena/01a0df70-pineal-epifiz`
- `arena/01a10b08-pineal-epifiz`
- `arena/9f0718d0-pineal-epifiz`
- `arena/a49c5a64-pineal-epifiz`
- `bolt-cache-provider-catalog...` ve `bolt/optimize-env-secrets...`
- Bütün eski `fix/...` dalları.

**Nasıl Silinir?**
GitHub sayfana girip "Branches" (Dallar) bölümüne tıkladığında bu listeyi göreceksin. Sadece `main` dalı kalacak şekilde, diğerlerinin yanındaki "Çöp Kutusu" simgesine basarak hepsini silebilirsin. Ana kodun (`main`) güvende, hiçbir şey kaybetmeyeceksin.
