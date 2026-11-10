# -*- coding: utf-8 -*-
"""P1 Fixes:
1. backend/checkpoint_store.py: eliminate truncate risk on replace failure.
2. agent_core/services/dependency_health.py: add phonenumbers requirement.
3. agent_core/capabilities/adapters_identity.py: check phonenumbers in availability().
4. agent_core/services/phone_probe.py: separate dependency_missing from is_valid=False.
"""
import re
import sys

def fix_checkpoint_store():
    path = r"C:\Projects\pineal-epifiz\backend\checkpoint_store.py"
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()

    target_pattern = re.compile(
        r"(\s+try:\s+os\.replace\(tmp, path\)\s+except PermissionError:[\s\S]*?except Exception:\s+pass)",
        re.MULTILINE
    )

    replacement = """    try:
        os.replace(tmp, path)
    except PermissionError:
        # Windows / OneDrive kilit gecikmesi (WinError 5): 50ms bekle ve tekrar dene
        import time
        time.sleep(0.05)
        try:
            os.replace(tmp, path)
        except Exception as retry_err:
            # P1 Guvenlik: Eski dosyayi ASLA "w" moduyla acip ezmiyoruz (truncate riski sifir).
            logger.error(
                "checkpoint atomik degistirme basarisiz oldu (eski veri korundu): %s -> %s (%s)",
                tmp,
                path,
                retry_err,
            )
            raise CheckpointError(
                f"Checkpoint atomik olarak yazilamadi (eski veri korundu): {retry_err}"
            ) from retry_err
    except Exception as e:
        logger.error("checkpoint yaziminda beklenmeyen hata: %s", e)
        raise CheckpointError(f"Checkpoint yazilamadi: {e}") from e"""

    new_content, count = target_pattern.subn(replacement, content, count=1)
    if count == 0:
        print("FAILED: Could not find target pattern in checkpoint_store.py")
        return False
    with open(path, "w", encoding="utf-8", newline="\r\n") as f:
        f.write(new_content)
    print("SUCCESS: backend/checkpoint_store.py updated without truncation risk.")
    return True

def fix_dependency_health():
    path = r"C:\Projects\pineal-epifiz\agent_core\services\dependency_health.py"
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()

    target = '    DependencyRequirement("aiofiles", "aiofiles"),'
    replacement = '    DependencyRequirement("aiofiles", "aiofiles"),\n    DependencyRequirement("phonenumbers", "phonenumbers"),'

    if target in content and 'DependencyRequirement("phonenumbers", "phonenumbers")' not in content:
        content = content.replace(target, replacement, 1)
        with open(path, "w", encoding="utf-8", newline="\r\n") as f:
            f.write(content)
        print("SUCCESS: agent_core/services/dependency_health.py updated with phonenumbers.")
        return True
    elif 'DependencyRequirement("phonenumbers", "phonenumbers")' in content:
        print("ALREADY_PRESENT: phonenumbers already in dependency_health.py")
        return True
    else:
        print("FAILED: Target not found in dependency_health.py")
        return False

def fix_adapters_identity():
    path = r"C:\Projects\pineal-epifiz\agent_core\capabilities\adapters_identity.py"
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()

    target = """    def availability(self) -> Availability:
        return Availability.ok()"""

    replacement = """    def availability(self) -> Availability:
        try:
            import phonenumbers  # noqa: F401
            return Availability.ok()
        except ImportError:
            return Availability.missing("dependency_missing:phonenumbers")"""

    if target in content:
        content = content.replace(target, replacement, 1)
        with open(path, "w", encoding="utf-8", newline="\r\n") as f:
            f.write(content)
        print("SUCCESS: agent_core/capabilities/adapters_identity.py availability() updated.")
        return True
    else:
        print("FAILED: Target not found in adapters_identity.py")
        return False

def fix_phone_probe():
    path = r"C:\Projects\pineal-epifiz\agent_core\services\phone_probe.py"
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()

    target = """    try:
        import phonenumbers
        from phonenumbers import carrier, geocoder, number_type, PhoneNumberType"""

    replacement = """    try:
        import phonenumbers
        from phonenumbers import carrier, geocoder, number_type, PhoneNumberType
    except ImportError as e:
        logger.error("phonenumbers dependency is missing: %s", e)
        return PhoneMetadata(
            raw_input=raw_phone,
            e164=cleaned,
            national_format=raw_phone,
            international_format=cleaned,
            is_valid=False,
            is_possible=False,
            error="dependency_missing:phonenumbers",
        )
    try:"""

    if target in content:
        content = content.replace(target, replacement, 1)
        with open(path, "w", encoding="utf-8", newline="\r\n") as f:
            f.write(content)
        print("SUCCESS: agent_core/services/phone_probe.py updated to distinguish dependency_missing.")
        return True
    else:
        print("FAILED: Target not found in phone_probe.py")
        return False

if __name__ == "__main__":
    ok1 = fix_checkpoint_store()
    ok2 = fix_dependency_health()
    ok3 = fix_adapters_identity()
    ok4 = fix_phone_probe()
    if all([ok1, ok2, ok3, ok4]):
        print("ALL P1 FIXES APPLIED SUCCESSFULLY!")
    else:
        sys.exit(1)
