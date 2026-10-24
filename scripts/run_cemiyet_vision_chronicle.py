import sys
import os
import json
import base64
import requests
from datetime import datetime
from dotenv import load_dotenv

sys.stdout.reconfigure(encoding='utf-8')
load_dotenv()

from instagrapi import Client

base_url = os.environ.get('NINEROUTER_BASE_URL', 'http://127.0.0.1:20128/v1')
api_key = os.environ.get('NINEROUTER_API_KEY')
session_id = os.environ.get('IG_SESSIONID')

if not session_id or not api_key:
    print("Error: Missing IG_SESSIONID or NINEROUTER_API_KEY")
    sys.exit(1)

print("1. Connecting to Instagram Client via session...")
cl = Client()
cl.login_by_sessionid(session_id)

target = "cemiyettesimyaci"
user_info = cl.user_info_by_username(target)
print(f"Target: {user_info.username} (ID: {user_info.pk}) | Media Count: {user_info.media_count}")

# Fetch 12 media posts to get a representative chronological distribution
print("2. Fetching media items...")
medias = cl.user_medias(user_info.pk, amount=12)
print(f"Fetched {len(medias)} medias.")

results = []

for idx, m in enumerate(medias, 1):
    print(f"\n--- Analyzing Media {idx}/{len(medias)}: Code {m.code} ({m.taken_at.strftime('%Y-%m-%d %H:%M')}) ---")
    
    # Identify image or thumbnail URL
    img_url = None
    if hasattr(m, 'thumbnail_url') and m.thumbnail_url:
        img_url = str(m.thumbnail_url)
    elif hasattr(m, 'resources') and m.resources:
        for r in m.resources:
            if hasattr(r, 'thumbnail_url') and r.thumbnail_url:
                img_url = str(r.thumbnail_url)
                break
    
    if not img_url and hasattr(m, 'video_url'):
        # Video without thumbnail url directly available, check display_url
        pass

    caption = m.caption_text or ""
    likes = m.like_count or 0
    comments_count = m.comment_count or 0
    taken_at_str = m.taken_at.strftime('%Y-%m-%d %H:%M UTC')

    # Fetch comments for this media
    comment_details = []
    try:
        raw_comments = cl.media_comments(m.pk, 5)
        for c in raw_comments:
            comment_details.append({
                "author": c.user.username,
                "text": c.text,
                "created_at": c.created_at_utc.strftime('%Y-%m-%d %H:%M') if c.created_at_utc else ""
            })
    except Exception as e:
        pass

    vision_analysis = "Goruntu indirilemedi"
    if img_url:
        try:
            # Download image bytes
            resp = requests.get(img_url, timeout=15)
            if resp.status_code == 200:
                b64_img = base64.b64encode(resp.content).decode('utf-8')
                
                vision_prompt = (
                    "Sen adli görsel istihbarat ve yaşam kırılması (Life Rupture) analistisin. "
                    "Bu fotoğrafa bakarak sadece somut gözlemleri şu 5 başlıkta tarafsız ve net olarak çıkar:\n"
                    "1. Mekan: (İç mekan mı, dış mekan mı, araba içi mi, sokak mı, ev mi?)\n"
                    "2. Işık/Zaman: (Gündüz mü, gece mi, loş ışık mı, neon/yapay ışık mı?)\n"
                    "3. Sosyal Varlık: (Fotoğrafta insan var mı? Tek başına mı, kalabalık/grup mu, yoksa sadece cansız nesne/araç mı?)\n"
                    "4. Yüz ve Bakış: (Yüz görünüyor mu? Doğrudan kameraya mı bakıyor, profil/uzak mı, bakış kaçırma mı, gözler/yüz gizli veya maskeli mi? İfade: Gülümseme, donukluk, keder, gerginlik?)\n"
                    "5. Odak Nesneleri ve Detaylar: (Direksiyon, klasik araba, sigara, alkol bardağı/şişe, kıyafet, filtre/grain var mı?)\n"
                    "Cevabını kısa, net ve maddeler halinde ver. Falcılık yapma, ne görüyorsan onu yaz."
                )
                
                v_payload = {
                    "model": "pineal-vision",
                    "stream": False,
                    "messages": [
                        {
                            "role": "user",
                            "content": [
                                {"type": "text", "text": vision_prompt},
                                {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64_img}"}}
                            ]
                        }
                    ],
                    "max_tokens": 400
                }
                
                vr = requests.post(
                    f"{base_url}/chat/completions",
                    json=v_payload,
                    headers={"Authorization": f"Bearer {api_key}"},
                    timeout=30
                )
                if vr.status_code == 200:
                    v_json = vr.json()
                    vision_analysis = v_json.get("choices", [{}])[0].get("message", {}).get("content", "").strip()
                else:
                    vision_analysis = f"Vision API error: {vr.status_code}"
        except Exception as e:
            vision_analysis = f"Vision download/eval error: {str(e)}"

    print("Vision Output:\n", vision_analysis)
    
    results.append({
        "code": m.code,
        "date": taken_at_str,
        "timestamp": m.taken_at.timestamp(),
        "likes": likes,
        "comments_count": comments_count,
        "comments": comment_details,
        "caption": caption,
        "vision": vision_analysis
    })

# Save output to json for persistent inspection
output_path = "C:/Users/gumus/pineal-epifiz/reports/cemiyet_life_rupture.json"
os.makedirs(os.path.dirname(output_path), exist_ok=True)
with open(output_path, "w", encoding="utf-8") as f:
    json.dump(results, f, ensure_ascii=False, indent=2)

print(f"\n[DONE] Saved complete chronological vision report to {output_path}")
