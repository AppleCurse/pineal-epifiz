//! PINEAL-HERETIC v5.0 - Stealth Vault
//!
//! API anahtarları ve oturum verileri için bellek-içi şifreli kasa.
//! age + argon2 ile diskte şifreli, RAM'de sadece ihtiyaç anında açık.
//!
//! # [VAULT_PERSISTENCE_FIX 2026-10-07] — halı altından çıkarılan üç gerçek arıza
//!
//! Bu modülde uzun süre `VAULT_PERSISTENCE_BUG: age file truncated on
//! store->reload` hatası yaşandı ve hata çözülmek yerine ilgili test
//! `#[ignore]` ile susturuldu. Kök nedenler tek tek bulundu ve onarıldı:
//!
//! 1. **Kesik age akışı (veri kaybının asıl sebebi).**
//!    `age::Encryptor::wrap_output` bir `StreamWriter` döndürür ve bu
//!    yazarın SON chunk'ı + MAC'i yazması için `finish()` ÇAĞRILMALIDIR.
//!    age kaynak sözleşmesi (age 0.10.1, `primitives/stream.rs`):
//!    "You **MUST** call `finish` … Failing to call `finish` will result in a
//!    truncated file that will fail to decrypt."
//!    Eski kod `write_all` sonrası writer'ı sadece scope sonunda düşürüyordu;
//!    `Drop` son chunk'ı YAZMAZ. Sonuç: diske her zaman kesik `.cipher`
//!    dosyası indi, reload'da `age file is truncated` patladı.
//!
//! 2. **Gizli anahtar diskte DÜZ METİN duruyordu.**
//!    `vault.json` age x25519 GİZLİ anahtarını (`AGE-SECRET-KEY-…`) açık
//!    metin yazıyordu. Yani "diskte şifreli kasa" iddiası boştu: `.cipher`
//!    dosyalarını çözen anahtar, şifreli metnin hemen yanında duruyordu.
//!    Artık kimlik, operatör parolasıyla (age scrypt) şifrelenmiş
//!    `identity_encrypted` alanında tutulur. Düz metin `identity` alanı
//!    taşıyan eski/bozuk dosyalar **fail-closed** reddedilir.
//!
//! 3. **Kilit, kilit gibi davranmıyordu.**
//!    `secure_wipe()` anahtarın BİR KOPYASINI sıfırlayıp atıyordu (asıl
//!    sıfırlanan hiçbir şey yoktu) ve wipe sonrası `store`/`retrieve`
//!    çalışmaya devam ediyordu. Artık wipe kalıcıdır: kasa mühürlenir ve
//!    sonraki her okuma/yazma `VaultError::VaultLocked` ile reddedilir.
//!
//! Ek olarak: şifreleme yolundaki `.expect(...)` panikleri kaldırıldı —
//! bir kasa arızası süreci çökertmek yerine `VaultError` olarak döner.

use age::secrecy::{ExposeSecret, Secret, SecretString};
use argon2::{password_hash::SaltString, Argon2, PasswordHasher, PasswordVerifier};
use rand::rngs::OsRng;
use serde::{Deserialize, Serialize};
use std::fs;
use std::path::{Path, PathBuf};
use thiserror::Error;
use zeroize::Zeroize;

/// Vault hataları
#[derive(Error, Debug)]
pub enum VaultError {
    #[error("Şifreleme hatası: {0}")]
    EncryptionError(String),

    #[error("Şifre çözme hatası: {0}")]
    DecryptionError(String),

    #[error("Dosya erişim hatası: {0}")]
    FileError(String),

    #[error("Anahtar üretimi hatası: {0}")]
    KeyGenerationError(String),

    #[error("Parola doğrulama hatası: {0}")]
    PasswordError(String),

    /// [VAULT_PERSISTENCE_FIX] Kasa mühürlendi (`secure_wipe`) ama kullanılmaya
    /// çalışıldı. Sessizce devam edilmez; işlem reddedilir.
    #[error("Kasa kilitli: {0}")]
    VaultLocked(String),

    /// [VAULT_PERSISTENCE_FIX] Diskteki kasa dosyası güvenli biçimde
    /// yazılmamış (age gizli anahtarı düz metin). Fail-closed: açılmaz.
    #[error("Güvensiz kasa dosyası: {0}")]
    InsecureVaultFile(String),
}

/// Şifrelenmiş veri paketi (age formatında)
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct EncryptedPayload {
    pub ciphertext: Vec<u8>,
    pub recipient: String,
}

/// Kasanın disk şeması (`vault.json`).
///
/// [VAULT_PERSISTENCE_FIX] Eski şema `identity` alanına age GİZLİ anahtarını
/// düz metin yazıyordu. Yeni şemada gizli anahtar yalnızca parola ile
/// şifrelenmiş `identity_encrypted` içinde yaşar; `recipient` (açık anahtar)
/// gizli değildir ve bütünlük denetimi için saklanır.
#[derive(Debug, Clone, Serialize, Deserialize)]
struct VaultFile {
    /// Parolayla (age scrypt) şifrelenmiş age x25519 kimliği.
    identity_encrypted: Vec<u8>,
    /// Açık alıcı anahtarı (`age1…`): kimlikle eşleşmek ZORUNDADIR.
    recipient: String,
    /// Argon2id parola hash'i (PHC biçimi) — aynı zamanda master key türevinin girdisi.
    password_hash: String,
    version: String,
}

/// Kasa dosyası şema sürümü.
const VAULT_SCHEMA_VERSION: &str = "5.1";

/// Stealth Vault - Ana şifreli kasa yapısı
/// [W4.3] Tek sahiplikli vault yolu. create/open/get komutları (src-tauri)
/// bu fonksiyonu kullanır; tauri_bridge'deki /tmp'li ikiz kaldrıldı.
/// Öncelik: $PINEAL_VAULT_DIR/vault.json, yoksa $USERPROFILE|$HOME/.pineal_vault/vault.json
pub fn default_vault_path() -> std::path::PathBuf {
    if let Ok(dir) = std::env::var("PINEAL_VAULT_DIR") {
        if !dir.trim().is_empty() {
            return std::path::PathBuf::from(dir).join("vault.json");
        }
    }
    let home = std::env::var("USERPROFILE")
        .or_else(|_| std::env::var("HOME"))
        .unwrap_or_else(|_| ".".to_string());
    std::path::PathBuf::from(format!("{}/.pineal_vault", home)).join("vault.json")
}

pub struct StealthVault {
    vault_path: PathBuf,
    master_key: Secret<Vec<u8>>,
    recipient: age::x25519::Recipient,
    identity: age::x25519::Identity,
    password_hash: Option<String>,
    /// [VAULT_PERSISTENCE_FIX] `true` = kasa mühürlendi; store/retrieve REDDEDİLİR.
    wiped: bool,
}

impl StealthVault {
    pub fn new(vault_path: &Path, password: &str) -> Result<Self, VaultError> {
        let salt = SaltString::generate(&mut OsRng);
        let argon2 = Argon2::default();
        let password_hash = argon2
            .hash_password(password.as_bytes(), &salt)
            .map(|h| h.to_string())
            .map_err(|e| VaultError::KeyGenerationError(format!("Argon2id hatası: {}", e)))?;

        let identity = age::x25519::Identity::generate();
        let recipient = identity.to_public();

        let vault = Self {
            vault_path: vault_path.to_path_buf(),
            master_key: Self::derive_master_key(&password_hash),
            recipient,
            identity,
            password_hash: Some(password_hash),
            wiped: false,
        };

        vault.save_to_disk(password)?;
        Ok(vault)
    }

    pub fn load(vault_path: &Path, password: &str) -> Result<Self, VaultError> {
        if !vault_path.exists() {
            return Err(VaultError::FileError("Vault dosyası bulunamadı".to_string()));
        }

        let identity_data = fs::read(vault_path)
            .map_err(|e| VaultError::FileError(format!("Dosya okuma hatası: {}", e)))?;

        let vault_value: serde_json::Value = serde_json::from_slice(&identity_data)
            .map_err(|e| VaultError::DecryptionError(format!("JSON parse hatası: {}", e)))?;

        // `to_owned()`: `vault_value` aşağıda `serde_json::from_value` ile
        // TAŞINACAK; ondan ödünç alınmış bir `&str` taşınmayı engellemesin.
        let stored_hash = vault_value
            .get("password_hash")
            .and_then(|v| v.as_str())
            .ok_or_else(|| VaultError::DecryptionError("Password hash bulunamadı".to_string()))?
            .to_owned();

        // 1) Parola ÖNCE doğrulanır: dosya biçimi hakkında bilgi sızdırmadan
        //    önce "bu kasayı açmaya yetkin misin?" sorusu cevaplanır.
        {
            let argon2 = Argon2::default();
            let parsed_hash = argon2::PasswordHash::new(&stored_hash)
                .map_err(|e| VaultError::PasswordError(format!("Hash parse hatası: {}", e)))?;

            argon2
                .verify_password(password.as_bytes(), &parsed_hash)
                .map_err(|_| VaultError::PasswordError("Yanlış parola".to_string()))?;
        }

        // 2) [VAULT_PERSISTENCE_FIX] Eski şema age GİZLİ anahtarını düz metin
        //    taşıyordu. Böyle bir dosya "açılıp kullanılabilir" sayılmaz:
        //    fail-closed reddedilir (güvenli kasa iddiası geriye dönük olarak
        //    da geçerli olmak zorunda).
        if vault_value.get("identity").and_then(|v| v.as_str()).is_some() {
            return Err(VaultError::InsecureVaultFile(
                "Kasa dosyası age GİZLİ anahtarını düz metin içeriyor (şema <5.1). \
                 Bu dosya açılamaz; kasayı yeniden oluşturun ve anahtarları tekrar mühürleyin."
                    .to_string(),
            ));
        }

        let vault_file: VaultFile = serde_json::from_value(vault_value).map_err(|e| {
            VaultError::DecryptionError(format!("Kasa şeması okunamadı (şema 5.1 beklenir): {}", e))
        })?;

        // 3) Tanınmayan şema sürümü sessizce açılmaz (fail-closed).
        if !vault_file.version.starts_with("5.") {
            return Err(VaultError::DecryptionError(format!(
                "Tanınmayan kasa şema sürümü: {}",
                vault_file.version
            )));
        }

        // 4) Gizli anahtar yalnızca parola ile çözülür (age scrypt).
        let identity_secret = Self::decrypt_identity(&vault_file.identity_encrypted, password)?;
        let identity: age::x25519::Identity = identity_secret
            .expose_secret()
            .trim()
            .parse()
            .map_err(|e| VaultError::DecryptionError(format!("Identity parse hatası: {}", e)))?;

        let recipient = identity.to_public();

        // 5) Bütünlük: dosyadaki açık alıcı, çözülen kimliğin alıcısı olmalı.
        //    Aksi halde dosya kurcalanmıştır → reddedilir (sessiz devam yok).
        if !vault_file.recipient.is_empty() && vault_file.recipient != recipient.to_string() {
            return Err(VaultError::DecryptionError(
                "Kasa dosyasındaki alıcı anahtarı çözülen kimlikle eşleşmiyor (dosya kurcalanmış)"
                    .to_string(),
            ));
        }

        // Master key, struct literalinden ÖNCE türetilir: `vault_file.password_hash`
        // literalin içinde TAŞINIR; türetme ödünç alması taşınmayı engellemesin.
        let master_key = Self::derive_master_key(&vault_file.password_hash);

        Ok(Self {
            vault_path: vault_path.to_path_buf(),
            master_key,
            recipient,
            identity,
            password_hash: Some(vault_file.password_hash),
            wiped: false,
        })
    }

    /// Kasa açık mı? (`secure_wipe` sonrası `false` ve kalıcıdır.)
    pub fn is_unlocked(&self) -> bool {
        !self.wiped
    }

    pub fn store<T: Serialize>(&self, label: &str, data: &T) -> Result<(), VaultError> {
        self.ensure_unlocked()?;

        let plaintext = serde_json::to_vec(data)
            .map_err(|e| VaultError::EncryptionError(e.to_string()))?;

        let encrypted_data = self.encrypt_data(&plaintext)?;

        let payload = EncryptedPayload {
            ciphertext: encrypted_data,
            recipient: self.recipient.to_string(),
        };

        let cipher_path = self.cipher_path(label);
        let cipher_json = serde_json::to_vec(&payload)
            .map_err(|e| VaultError::EncryptionError(e.to_string()))?;

        // [VAULT_PERSISTENCE_FIX] Atomik yazım: yarım kalmış `.cipher` dosyası
        // bir sonraki açılışta "kesik age dosyası" olarak geri dönmesin.
        Self::write_atomic(&cipher_path, &cipher_json)?;

        tracing::info!("Veri '{}' etiketiyle şifrelenerek kasaya kondu", label);
        Ok(())
    }

    pub fn retrieve<T: for<'de> Deserialize<'de>>(&self, label: &str) -> Result<T, VaultError> {
        self.ensure_unlocked()?;

        let cipher_path = self.cipher_path(label);

        let cipher_data = fs::read(&cipher_path)
            .map_err(|e| VaultError::FileError(format!("Dosya okuma hatası: {}", e)))?;

        let payload: EncryptedPayload = serde_json::from_slice(&cipher_data)
            .map_err(|e| VaultError::DecryptionError(format!("JSON parse hatası: {}", e)))?;

        let plaintext = self.decrypt_data(&payload.ciphertext)?;

        let result: T = serde_json::from_slice(&plaintext)
            .map_err(|e| VaultError::DecryptionError(e.to_string()))?;

        Ok(result)
    }

    fn cipher_path(&self, label: &str) -> PathBuf {
        self.vault_path.with_file_name(format!("{}.cipher", label))
    }

    fn ensure_unlocked(&self) -> Result<(), VaultError> {
        if self.wiped {
            return Err(VaultError::VaultLocked(
                "secure_wipe çağrıldı; kasa mühürlü. Yeniden açmadan okuma/yazma yapılamaz."
                    .to_string(),
            ));
        }
        Ok(())
    }

    /// [VAULT_PERSISTENCE_FIX] Master key artık her `load`'da RASTGELE
    /// üretilmiyor (eski davranış: aynı kasa iki kez açıldığında iki farklı
    /// "master key" — yani alan süs eşyasıydı). Argon2id PHC çıktısının
    /// SHA-256'sı türetilir: aynı parola + aynı tuz → aynı anahtar, hem
    /// `new` hem `load` yolunda. Argon2id yavaş türetmeyi yapar; SHA-256
    /// yalnızca 32 baytlık sabit uzunluğa indirger.
    fn derive_master_key(password_hash_phc: &str) -> Secret<Vec<u8>> {
        use sha2::{Digest, Sha256};
        let mut hasher = Sha256::new();
        hasher.update(password_hash_phc.as_bytes());
        Secret::new(hasher.finalize().to_vec())
    }

    fn encrypt_data(&self, plaintext: &[u8]) -> Result<Vec<u8>, VaultError> {
        use age::Encryptor;
        use std::io::Write;

        let mut encrypted = Vec::new();
        {
            let recipients: Vec<Box<dyn age::Recipient + Send>> =
                vec![Box::new(self.recipient.clone())];
            // [VAULT_PERSISTENCE_FIX] `.expect(...)` YOK: kasa arızası panik
            // değil `VaultError` döndürür (sessiz çökme / süreci düşürme yok).
            let encryptor = Encryptor::with_recipients(recipients).ok_or_else(|| {
                VaultError::EncryptionError("age alıcı listesi boş; şifreleme başlatılamadı".to_string())
            })?;
            let mut writer = encryptor.wrap_output(&mut encrypted).map_err(|e| {
                VaultError::EncryptionError(format!("age wrap_output hatası: {}", e))
            })?;

            writer
                .write_all(plaintext)
                .map_err(|e| VaultError::EncryptionError(format!("age write hatası: {}", e)))?;

            // ★ KÖK NEDEN DÜZELTMESİ ★
            // `finish()` çağrılmadan age akışının SON chunk'ı ve MAC'i diske
            // inmez; dosya kesik kalır ve reload'da "age file is truncated"
            // verir. `Drop` bu işi YAPMAZ (age 0.10.1 sözleşmesi).
            writer
                .finish()
                .map_err(|e| VaultError::EncryptionError(format!("age finish hatası: {}", e)))?;
        }

        Ok(encrypted)
    }

    fn decrypt_data(&self, ciphertext: &[u8]) -> Result<Vec<u8>, VaultError> {
        use age::Decryptor;
        use std::io::Read;

        let decryptor = Decryptor::new(ciphertext)
            .map_err(|e| VaultError::DecryptionError(format!("age decryptor hatası: {}", e)))?;

        let mut decrypted = Vec::new();
        {
            let recipient_decryptor = match decryptor {
                Decryptor::Recipients(d) => d,
                _ => {
                    return Err(VaultError::DecryptionError(
                        "Beklenmeyen age decryptor tipi (kasa alıcı-şifreli değil)".to_string(),
                    ))
                }
            };

            let identities: Vec<Box<dyn age::Identity>> = vec![Box::new(self.identity.clone())];
            let mut reader = recipient_decryptor
                .decrypt(identities.iter().map(|i| i.as_ref()))
                .map_err(|e| VaultError::DecryptionError(format!("age decrypt hatası: {}", e)))?;

            reader
                .read_to_end(&mut decrypted)
                .map_err(|e| VaultError::DecryptionError(format!("age read hatası: {}", e)))?;
        }

        Ok(decrypted)
    }

    /// age x25519 GİZLİ anahtarını operatör parolasıyla şifreler (age scrypt).
    fn encrypt_identity(identity_secret: &str, password: &str) -> Result<Vec<u8>, VaultError> {
        use age::Encryptor;
        use std::io::Write;

        let passphrase: SecretString = Secret::new(password.to_owned());
        let encryptor = Encryptor::with_user_passphrase(passphrase);

        let mut encrypted = Vec::new();
        let mut writer = encryptor.wrap_output(&mut encrypted).map_err(|e| {
            VaultError::EncryptionError(format!("age wrap_output (parola) hatası: {}", e))
        })?;
        writer
            .write_all(identity_secret.as_bytes())
            .map_err(|e| VaultError::EncryptionError(format!("age write (parola) hatası: {}", e)))?;
        // finish() zorunlu — bkz. encrypt_data'daki kök neden notu.
        writer
            .finish()
            .map_err(|e| VaultError::EncryptionError(format!("age finish (parola) hatası: {}", e)))?;

        Ok(encrypted)
    }

    /// Parolayla şifrelenmiş kimliği çözer; yanlış parola → `PasswordError`.
    fn decrypt_identity(ciphertext: &[u8], password: &str) -> Result<SecretString, VaultError> {
        use age::Decryptor;
        use std::io::Read;

        let decryptor = Decryptor::new(ciphertext).map_err(|e| {
            VaultError::DecryptionError(format!("age decryptor (parola) hatası: {}", e))
        })?;

        let passphrase_decryptor = match decryptor {
            Decryptor::Passphrase(d) => d,
            _ => {
                return Err(VaultError::DecryptionError(
                    "Kasa kimliği parola-şifreli bir age dosyası değil (dosya bozuk/kurcalanmış)"
                        .to_string(),
                ))
            }
        };

        let passphrase: SecretString = Secret::new(password.to_owned());
        let mut reader = passphrase_decryptor.decrypt(&passphrase, None).map_err(|e| {
            // age, yanlış parolayı MAC hatası olarak bildirir. Operatöre
            // dürüst cevap: parola uyuşmadı.
            VaultError::PasswordError(format!("Kasa kimliği çözülemedi (yanlış parola?): {}", e))
        })?;

        let mut plaintext = Vec::new();
        reader
            .read_to_end(&mut plaintext)
            .map_err(|e| VaultError::DecryptionError(format!("age read (parola) hatası: {}", e)))?;

        // `String::from_utf8` tamponu TAŞIYARAK devralır: arkada kopya kalmaz,
        // gizli anahtar bundan sonra `Secret` içinde yaşar ve `Drop`'ta sıfırlanır.
        let identity_string = String::from_utf8(plaintext).map_err(|e| {
            VaultError::DecryptionError(format!("Kasa kimliği UTF-8 değil: {}", e))
        })?;
        Ok(Secret::new(identity_string))
    }

    fn save_to_disk(&self, password: &str) -> Result<(), VaultError> {
        let identity_secret = self.identity.to_string();

        let vault_file = VaultFile {
            // [VAULT_PERSISTENCE_FIX] Gizli anahtar DÜZ METİN YAZILMAZ.
            identity_encrypted: Self::encrypt_identity(
                identity_secret.expose_secret().as_str(),
                password,
            )?,
            recipient: self.recipient.to_string(),
            password_hash: self.password_hash.clone().ok_or_else(|| {
                VaultError::KeyGenerationError("Parola hash'i yok; kasa diske yazılamaz".to_string())
            })?,
            version: VAULT_SCHEMA_VERSION.to_string(),
        };

        let vault_bytes = serde_json::to_vec(&vault_file)
            .map_err(|e| VaultError::FileError(e.to_string()))?;

        Self::write_atomic(&self.vault_path, &vault_bytes)?;

        tracing::info!("Vault {} konumuna kaydedildi", self.vault_path.display());
        Ok(())
    }

    /// Yarım dosya bırakmayan yazım: önce `<hedef>.tmp`, sonra `rename`.
    ///
    /// `rename` aynı dosya sisteminde atomiktir; süreç yazım sırasında
    /// ölürse hedef ya eski tam hâlinde kalır ya da hiç oluşmaz — asla
    /// kesik kalmaz (veri kaybı arızasının ikinci ayağı).
    fn write_atomic(path: &Path, bytes: &[u8]) -> Result<(), VaultError> {
        let tmp = path.with_extension("tmp");
        fs::write(&tmp, bytes).map_err(|e| VaultError::FileError(e.to_string()))?;
        fs::rename(&tmp, path).map_err(|e| {
            let _ = fs::remove_file(&tmp);
            VaultError::FileError(format!("Atomik yeniden adlandırma hatası: {}", e))
        })?;
        Ok(())
    }

    /// Kasayı bellekte mühürler. **Kalıcıdır**: sonrasında `store`/`retrieve`
    /// `VaultError::VaultLocked` döndürür.
    ///
    /// [VAULT_PERSISTENCE_FIX] Eski kod anahtarın BİR KOPYASINI sıfırlıyordu
    /// (`expose_secret().clone()` → `zeroize()`), yani asıl alan hiç
    /// temizlenmiyordu — saf tiyatro. `secrecy::Secret` `Drop`'ta sıfırlar;
    /// alanı boş bir secret ile DEĞİŞTİRMEK eski değeri düşürür ve gerçek
    /// sıfırlamayı tetikler.
    pub fn secure_wipe(&mut self) {
        self.master_key = Secret::new(Vec::new());
        if let Some(mut hash) = self.password_hash.take() {
            hash.zeroize();
        }
        self.wiped = true;
        tracing::warn!("Vault bellekten güvenli şekilde temizlendi (kasa mühürlendi)");
    }
}

impl Drop for StealthVault {
    fn drop(&mut self) {
        self.secure_wipe();
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use tempfile::tempdir;

    #[derive(Serialize, Deserialize, Debug, PartialEq)]
    struct TestSecret {
        api_key: String,
        session_token: String,
    }

    #[test]
    fn test_vault_create_and_store() {
        let dir = tempdir().unwrap();
        let vault_path = dir.path().join("test_vault.json");
        let vault = StealthVault::new(&vault_path, "test_password").unwrap();
        let secret = TestSecret {
            api_key: "sk-test-12345".to_string(),
            session_token: "sess-abcde".to_string(),
        };
        vault.store("test_credentials", &secret).unwrap();
        let mut vault_mut = vault;
        vault_mut.secure_wipe();
    }

    // [VAULT_PERSISTENCE_FIX 2026-10-07] Bu test eskiden
    // `#[ignore = "VAULT_PERSISTENCE_BUG: age file truncated on store->reload"]`
    // ile susturulmuştu: hata çözülmek yerine CI'dan gizlenmişti. Etiket
    // KALDIRILDI, kök neden (eksik `StreamWriter::finish()`) onarıldı ve test
    // artık hilesiz koşuyor.
    #[test]
    fn test_vault_roundtrip_store_reload_retrieve() {
        // [047] sözleşme: oluştur -> yaz -> (diskten) aç -> oku -> değer aynı
        let dir = tempdir().unwrap();
        let vault_path = dir.path().join("roundtrip_vault.json");
        {
            let vault = StealthVault::new(&vault_path, "parola").unwrap();
            #[derive(Serialize)]
            struct Credential { value: String }
            vault.store("OPENROUTER_API_KEY", &Credential { value: "sk-or-v1-x".to_string() }).unwrap();
        }
        let reloaded = StealthVault::load(&vault_path, "parola").unwrap();
        #[derive(Deserialize, Debug)]
        struct Credential { value: String }
        let cred: Credential = reloaded.retrieve("OPENROUTER_API_KEY").unwrap();
        assert_eq!(cred.value, "sk-or-v1-x");
    }

    /// Kesik age akışının REGRESYON KİLİDİ: diske inen `.cipher` yükü
    /// eksiksiz bir age v1 dosyası olmalı (sihirli başlık + tam gövde) ve
    /// kasayı yeniden yüklemeden da çözülebilmeli.
    #[test]
    fn test_vault_persisted_cipher_is_a_complete_age_file() {
        let dir = tempdir().unwrap();
        let vault_path = dir.path().join("complete_vault.json");
        let vault = StealthVault::new(&vault_path, "parola").unwrap();

        #[derive(Serialize, Deserialize, Debug)]
        struct Credential { value: String }
        vault
            .store("TOKEN", &Credential { value: "sk-or-v1-tam-akis".to_string() })
            .unwrap();

        let cipher_path = dir.path().join("TOKEN.cipher");
        assert!(cipher_path.exists(), ".cipher dosyası diske inmedi");

        let raw = fs::read(&cipher_path).unwrap();
        let payload: EncryptedPayload = serde_json::from_slice(&raw).unwrap();
        assert!(
            !payload.ciphertext.is_empty(),
            "şifreli gövde boş — veri kaybı"
        );
        assert!(
            payload.ciphertext.starts_with(b"age-encryption.org/v1\n"),
            "age v1 sihirli başlığı yok: {:?}",
            &payload.ciphertext[..payload.ciphertext.len().min(32)]
        );

        // Kesik akış tam burada patlardı ("age file is truncated").
        let plaintext = vault.decrypt_data(&payload.ciphertext).unwrap();
        let cred: Credential = serde_json::from_slice(&plaintext).unwrap();
        assert_eq!(cred.value, "sk-or-v1-tam-akis");
    }

    /// [VAULT_PERSISTENCE_FIX] Kasa dosyası age GİZLİ anahtarını DÜZ METİN
    /// taşıyamaz: "diskte şifreli kasa" iddiasının altı dolu olmak zorunda.
    #[test]
    fn test_vault_file_never_stores_identity_in_plaintext() {
        let dir = tempdir().unwrap();
        let vault_path = dir.path().join("no_plaintext_vault.json");
        let vault = StealthVault::new(&vault_path, "parola").unwrap();
        let identity_string = vault.identity.to_string();
        let plaintext_secret = identity_string.expose_secret().as_str().to_owned();
        assert!(plaintext_secret.starts_with("AGE-SECRET-KEY-1"));

        let on_disk = fs::read_to_string(&vault_path).unwrap();
        assert!(
            !on_disk.contains(&plaintext_secret),
            "GİZLİ age anahtarı düz metin olarak diske yazıldı"
        );
        assert!(
            !on_disk.contains("AGE-SECRET-KEY-"),
            "kasa dosyasında düz metin gizli anahtar öneki bulundu"
        );
        assert!(
            on_disk.contains("identity_encrypted"),
            "kimlik şifreli alanda saklanmıyor"
        );
        // Açık alıcı anahtarı gizli değildir; bütünlük denetimi için yazılır.
        assert!(on_disk.contains(&vault.recipient.to_string()));
    }

    /// Eski (güvensiz) şemayla yazılmış bir kasa dosyası fail-closed
    /// reddedilir — parola doğru olsa bile.
    #[test]
    fn test_legacy_plaintext_identity_vault_is_rejected() {
        let dir = tempdir().unwrap();
        let vault_path = dir.path().join("legacy_vault.json");

        let legacy_identity = age::x25519::Identity::generate();
        let salt = SaltString::generate(&mut OsRng);
        let legacy_hash = Argon2::default()
            .hash_password(b"parola", &salt)
            .unwrap()
            .to_string();
        let legacy = serde_json::json!({
            "identity": legacy_identity.to_string().expose_secret().as_str(),
            "password_hash": legacy_hash,
            "version": "5.0",
        });
        fs::write(&vault_path, serde_json::to_vec(&legacy).unwrap()).unwrap();

        let err = StealthVault::load(&vault_path, "parola").unwrap_err();
        assert!(
            matches!(err, VaultError::InsecureVaultFile(_)),
            "beklenen InsecureVaultFile, gelen: {:?}",
            err
        );
        // Yanlış parola hâlâ parola hatasıdır (biçim bilgisi sızmaz).
        let err = StealthVault::load(&vault_path, "yanlis").unwrap_err();
        assert!(matches!(err, VaultError::PasswordError(_)), "gelen: {:?}", err);
    }

    /// Kasa kurcalanırsa (açık alıcı ≠ kimliğin alıcısı) sessizce açılmaz.
    #[test]
    fn test_vault_rejects_tampered_recipient() {
        let dir = tempdir().unwrap();
        let vault_path = dir.path().join("tampered_vault.json");
        StealthVault::new(&vault_path, "parola").unwrap();

        let mut value: serde_json::Value =
            serde_json::from_slice(&fs::read(&vault_path).unwrap()).unwrap();
        let bogus_recipient = age::x25519::Identity::generate().to_public().to_string();
        value["recipient"] = serde_json::Value::String(bogus_recipient);
        fs::write(&vault_path, serde_json::to_vec(&value).unwrap()).unwrap();

        let err = StealthVault::load(&vault_path, "parola").unwrap_err();
        assert!(
            matches!(err, VaultError::DecryptionError(_)),
            "beklenen DecryptionError, gelen: {:?}",
            err
        );
    }

    /// [VAULT_PERSISTENCE_FIX] Mühürlenen kasa okuma/yazmayı REDDEDER.
    /// Kilit, kilit gibi davranmak zorunda.
    #[test]
    fn test_wiped_vault_refuses_store_and_retrieve() {
        let dir = tempdir().unwrap();
        let vault_path = dir.path().join("wiped_vault.json");
        let mut vault = StealthVault::new(&vault_path, "parola").unwrap();

        #[derive(Serialize, Deserialize, Debug)]
        struct Credential { value: String }
        vault
            .store("K", &Credential { value: "v".to_string() })
            .unwrap();
        assert!(vault.is_unlocked());

        // Mühürlemeden ÖNCE kasa gerçekten okunabilir olmalı (boş bir
        // "reddedildi" iddiasıyla değil, çalışan bir kasayla karşılaştırma).
        let before: Credential = vault.retrieve("K").unwrap();
        assert_eq!(before.value, "v");

        vault.secure_wipe();
        assert!(!vault.is_unlocked());

        let store_err = vault
            .store("K", &Credential { value: "v2".to_string() })
            .unwrap_err();
        assert!(
            matches!(store_err, VaultError::VaultLocked(_)),
            "mühürlü kasa yazmayı reddetmedi: {:?}",
            store_err
        );

        let retrieve_err = vault.retrieve::<Credential>("K").unwrap_err();
        assert!(
            matches!(retrieve_err, VaultError::VaultLocked(_)),
            "mühürlü kasa okumayı reddetmedi: {:?}",
            retrieve_err
        );

        // secure_wipe idempotent olmalı (Drop da çağırır).
        vault.secure_wipe();
        assert!(!vault.is_unlocked());
    }

    /// Master key artık süs değil: aynı parola + aynı dosya → aynı anahtar.
    /// (Eski davranış: her `load`'da rastgele 32 bayt, yani hiçbir anlamı yoktu.)
    #[test]
    fn test_master_key_is_stable_across_reload() {
        let dir = tempdir().unwrap();
        let vault_path = dir.path().join("stable_key_vault.json");
        let created = StealthVault::new(&vault_path, "parola").unwrap();
        let created_key = created.master_key.expose_secret().clone();
        assert_eq!(created_key.len(), 32);

        let reloaded = StealthVault::load(&vault_path, "parola").unwrap();
        assert_eq!(
            reloaded.master_key.expose_secret().as_slice(),
            created_key.as_slice(),
            "master key yeniden yüklemede değişti — alan gerçek bir anahtar değil"
        );
    }

    #[test]
    fn test_default_vault_path_single_source() {
        // [W4.3] env önceliği + varsayılan ev dizini altı (asla /tmp değil)
        std::env::set_var("PINEAL_VAULT_DIR", "/tmp/ozel_kasa");
        assert_eq!(default_vault_path(), std::path::PathBuf::from("/tmp/ozel_kasa/vault.json"));
        std::env::remove_var("PINEAL_VAULT_DIR");
        let path = default_vault_path();
        assert!(path.to_string_lossy().contains(".pineal_vault"));
        assert!(path.to_string_lossy().ends_with("vault.json"));
    }

    #[test]
    fn test_vault_load_with_wrong_password() {
        let dir = tempdir().unwrap();
        let vault_path = dir.path().join("test_vault.json");
        let _vault = StealthVault::new(&vault_path, "correct_password").unwrap();
        let result = StealthVault::load(&vault_path, "wrong_password");
        assert!(result.is_err());
        match result {
            Err(VaultError::PasswordError(_)) => {},
            _ => panic!("Beklenen PasswordError gelmedi"),
        }
    }
}
