import sys, os
sys.path.insert(0, r"C:\Projects\pineal-epifiz")

env_path = r"C:\Projects\pineal-epifiz\.env"
if os.path.exists(env_path):
    with open(env_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                val = v.split("#")[0].strip().strip("\"'")
                os.environ[k.strip()] = val

from agent_core.capabilities.registry import bootstrap
reg = bootstrap()
total = len(reg)
available_count = 0

print(f"=== PINEAL CAPABILITIES AUDIT (Total: {total}) ===")
for cap in reg:
    av = cap.availability()
    status = "CANLI (Aktif)" if av.available else f"KAPALI ({av.reason})"
    if av.available:
        available_count += 1
    print(f"{cap.id:<35} : {status}")

print("=" * 60)
print(f"SONUC: {available_count}/{total} Yetenek Kullanima Hazir.")
