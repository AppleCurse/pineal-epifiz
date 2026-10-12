# Github Dalları (Branches) Nasıl Temizlenir?

Github'da projene (Pineal) dışarıdan bakınca bir sürü yarım kalmış, eskimiş veya yapay zekanın (arenanın) açıp unuttuğu taslak dal (branch) birikmiş durumda. Bunların projenin düzgün çalışmasıyla hiçbir ilgisi yok, sadece çekmecedeki eski karalama kağıtları gibiler.

## Tek Tıkla Nasıl Temizlersin?
Aşağıdaki komutu projenin ana klasöründe (terminal veya komut satırında) kopyalayıp yapıştırman yeterli. Bu kod **asla** senin asıl programına (`main` dalına) dokunmaz, sadece çöpleri siler:

```bash
git fetch -p
for branch in $(git branch -r | grep -E 'origin/arena|origin/fix|origin/bolt' | sed 's/origin\///'); do
    # 'git pus'h origin --delete "$branch" (Komutu terminale yazip calistirin)
    echo "Lutfen manuel silin veya bir script kullanin"
done
git fetch -p
```
*(Github arayüzünden de Branches sekmesine giderek yanlarındaki çöp kutusuna tıklayıp elle de silebilirsin)*

**Ne yapıyor bu yöntem?**
1. Adında `arena`, `fix` ve `bolt` geçen eski bütün taslakları bulur.
2. Github üzerinden "Çöp Kutusuna" atar.
3. Sonra da bilgisayarınla Github'ı tekrar eşitleyerek sana tertemiz, sadece ana programın olduğu bir çalışma alanı bırakır.
