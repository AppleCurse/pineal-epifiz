import sys
import os
import json
import base64
import requests
from dotenv import load_dotenv

sys.stdout.reconfigure(encoding='utf-8')
load_dotenv()

from instagrapi import Client

base_url = os.environ.get('NINEROUTER_BASE_URL', 'http://127.0.0.1:20128/v1')
api_key = os.environ.get('NINEROUTER_API_KEY')
session_id = os.environ.get('IG_SESSIONID')

cl = Client()
cl.login_by_sessionid(session_id)
target_id = 51422244608

medias = cl.user_medias(target_id, amount=100)
medias_chronological = sorted(medias, key=lambda m: m.taken_at)

print(f"Total Medias: {len(medias_chronological)}")
print("Analyzing the FIRST (EARLIEST) 10 POSTS from the beginning of the account...")

origin_results = []

for idx, m in enumerate(medias_chronological[:10], 1):
    taken_at_str = m.taken_at.strftime('%Y-%m-%d %H:%M')
    print(f"\n==========================================")
    print(f"POST {idx}/10 | Date: {taken_at_str} | Code: {m.code}")
    print(f"Caption: {m.caption_text}")
    print(f"Likes: {m.like_count} | Comments: {m.comment_count}")

    img_url = None
    if hasattr(m, 'thumbnail_url') and m.thumbnail_url:
        img_url = str(m.thumbnail_url)
    elif hasattr(m, 'resources') and m.resources:
        for r in m.resources:
            if hasattr(r, 'thumbnail_url') and r.thumbnail_url:
                img_url = str(r.thumbnail_url)
                break

    # Get comments
    comments_list = []
    try:
        raw_comments = cl.media_comments(m.pk, 5)
        for c in raw_comments:
            comments_list.append(f"@{c.user.username}: {c.text}")
            print(f"  Comment: @{c.user.username}: {c.text}")
    except Exception:
        pass

    vision_text = "Goruntu alinamadi"
    if img_url:
        try:
            resp = requests.get(img_url, timeout=15)
            if resp.status_code == 200:
                b64_img = base64.b64encode(resp.content).decode('utf-8')
                v_prompt = (
                    "Sen adli gorsel istihbarat analistisin. Bu fotograf hedefin hesabindaki EN ILK gonderilerden biridir.\n"
                    "Asagidaki basliklarda falcilik ve edebiyat yapmadan sadece gordugun somut gercekleri yaz:\n"
                    "1. Mekan: (Ev, sokak, bahce, araba, kafe neresi?)\n"
                    "2. Isik ve Vakit: (Gunduz gunesi, gece, flas, lamba?)\n"
                    "3. Canli Varlik: (Insan var mi, kac kisi, kadin/erkek/cocuk? Hayvan var mi, kopek/kedi/cins?)\n"
                    "4. Yuz ve Duygu/Bakis: (Insan varsa yuzu acik mi, guluyor mu, nereye bakiyor?)\n"
                    "5. Odak Nesneleri: (Tasima cantasi, araba, masa, icki, kopek yavrusu, giyim tarzi vs.)\n"
                    "Maddeler halinde net dök."
                )
                payload = {
                    "model": "pineal-vision",
                    "stream": False,
                    "messages": [
                        {
                            "role": "user",
                            "content": [
                                {"type": "text", "text": v_prompt},
                                {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64_img}"}}
                            ]
                        }
                    ],
                    "max_tokens": 350
                }
                vr = requests.post(f"{base_url}/chat/completions", json=payload, headers={"Authorization": f"Bearer {api_key}"}, timeout=30)
                if vr.status_code == 200:
                    vision_text = vr.json().get("choices", [{}])[0].get("message", {}).get("content", "").strip()
        except Exception as e:
            vision_text = f"Hata: {e}"

    print(f"Vision Analizi:\n{vision_text}")
    origin_results.append({
        "post_num": idx,
        "code": m.code,
        "date": taken_at_str,
        "caption": m.caption_text,
        "likes": m.like_count,
        "comments": comments_list,
        "vision": vision_text
    })

output_path = "C:/Users/gumus/pineal-epifiz/reports/cemiyet_origin_vision.json"
with open(output_path, "w", encoding="utf-8") as f:
    json.dump(origin_results, f, ensure_ascii=False, indent=2)

print(f"\n[BASARILI] Ilk 10 post analiz edildi ve kaydedildi: {output_path}")
