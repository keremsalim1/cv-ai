# KRESUME.ai — Uygulama İskeleti (Sol Panel) ve Optimize & Otomatik Başvuru

Tarih: 2026-07-16
Durum: Tasarım onaylandı (sohbet içinde), implementasyon planı bekliyor.

## Amaç

1. **Faz 1 — Uygulama iskeleti:** İşlemler (skor, ATS, optimize) tek tek gömülü
   butonlar yerine global bir sol panelden erişilen ayrı sayfalara ayrılır.
2. **Faz 2 — Optimize & Otomatik Başvuru:** Kullanıcının seçtiği CV (orijinal
   veya ATS kopyası) bir başvuru linkindeki ilana göre optimize edilir; LLM
   başvuru formundaki soruları kendisi görüp cevaplar; her şey kullanıcı
   onayından geçer; onay sonrası başvuruyu LLM kullanıcı yerine gönderir veya
   materyalleri kullanıcıya teslim eder.

Faz 3 (bu spec'in DIŞINDA): LinkedIn benzeri anti-bot platformlar için farklı
stratejiler. Bu spec zemin bırakır, içermez.

---

## Faz 1 — Global Sol Panel ve Sayfa Ayrıştırma

### Route yapısı

Giriş sonrası sayfalar `web/src/app/(app)/` route group'una taşınır; ortak
`layout.tsx` sol paneli çizer. Landing (`/`), `/login`, `/register`,
`/auth/callback` grubun dışında kalır (panelsiz).

```
web/src/app/(app)/
  layout.tsx        # sol panel + içerik alanı
  dashboard/page.tsx
  score/page.tsx    # /cv/[id]/score buraya taşınır
  ats/page.tsx      # CV detayındaki ATS bölümü buraya taşınır
  optimize/page.tsx # Faz 2'de eklenir
  cv/[id]/page.tsx  # salt görüntüleme (ATS dönüştürme UI'ı kalkar)
```

### Sol panel

- Öğeler: **Panel** (dashboard), **Skorla**, **ATS'ye Çevir**,
  **Optimize & Başvur** (Faz 2 gelene dek pasif, "yakında" rozetli).
- Aktif sayfa vurgulanır (pathname eşleşmesi).
- Masaüstü (md+): sabit sol sütun. Mobil: navbar altında yatay sekme şeridi
  (drawer yok).
- Panel yalnızca oturum açmış kullanıcıya görünür; oturum yoksa (app) sayfaları
  zaten login'e yönlendiriyor (mevcut davranış korunur).

### İşlem sayfalarında CV seçimi

- `/score`, `/ats` (ve `/optimize`) sayfalarının üstünde kullanıcının
  CV'lerini listeleyen bir seçici bulunur. ATS kopyaları "ATS" rozetiyle
  ayırt edilir.
- Dashboard'daki CV kartı aksiyonları `?cv=<id>` query parametresiyle
  yönlendirir; sayfa o CV'yi önceden seçili açar.
- Eski `/cv/[id]/score` URL'i `/score?cv=<id>`'ye redirect edilir.

### Değişen mevcut davranış

- CV detay sayfasındaki ATS dil seçici + dönüştürme butonu `/ats` sayfasına
  taşınır; detay sayfası yalnızca parse edilmiş CV'yi gösterir.
- Testler ve i18n mesajları taşınan akışlarla birlikte güncellenir.

---

## Faz 2 — Optimize & Otomatik Başvuru

### Kullanıcı akışı (`/optimize`)

1. **CV seç:** Orijinal ve ATS CV'ler tek seçicide, rozetli. Seçim tamamen
   kullanıcıda.
2. **Başvuru linki:** Kullanıcı ilana başvurulan sayfanın linkini yapıştırır.
   Skor sayfasındaki "doğrudan ilan sayfası linki" ipucunun benzeri gösterilir.
3. **Çıktı dili:** TR/EN seçici (ATS'dekiyle aynı bileşen).
4. **"Hazırla" butonu** → `POST /apply/prepare` (aşağıda). Yükleme durumu uzun
   sürebilir (tarayıcı + LLM); ilerleme metni gösterilir.
5. **Onay ekranı:** LLM'in ürettiği HER ŞEY satır satır ve düzenlenebilir:
   - Optimize CV özeti + "neler değişti" listesi,
   - Motivasyon metni (form istiyorsa veya alan varsa; düzenlenebilir),
   - Form alanları ve önerilen değerler: metin cevapları textarea,
     çoktan seçmeliler formdaki gerçek seçenekleriyle select olarak.
   - İki buton: **"Onayla ve Başvur"** (LLM gönderir) /
     **"Sadece bana teslim et"** (gönderim yok, materyaller verilir).
6. **Sonuç:**
   - Başvuru yapıldıysa: durum + gönderim sonrası ekran görüntüsü.
   - Teslim modundaysa: optimize CV dashboard'a kaydedilir, ATS PDF indirme,
     motivasyon metni ve cevaplar için kopyala butonları.

### Backend — yeni servis: `apply`

Bağımlılık: **Playwright (Python) + Chromium**. API kullanıcının kendi
makinesinde çalıştığı için görünür (headed) pencere açılabilir — login-destekli
akışın temeli.

Tarayıcı, **kalıcı profil** (persistent context, `user_data_dir` yerel bir
klasörde) ile açılır: kullanıcının bir kez girdiği site oturumları sonraki
başvurularda da geçerli kalır (gerçek tarayıcı profili gibi). Şifre hiçbir
zaman uygulamaya girilmez ve saklanmaz; login her zaman kullanıcının kendi
elleriyle, açılan pencerede yapılır.

#### `POST /apply/prepare`

Girdi: `{cv: CVData, url: str, language: "tr"|"en"}` (auth + günlük kullanım
kontrolü).

1. Playwright sayfayı açar (önce headless; kalıcı profildeki çerezler yüklü).
2. **Login duvarı tespiti** (form yok + login/signin işaretleri):
   `{"status": "login_required"}` döner. Frontend "Açılan pencerede giriş
   yapın" der ve kullanıcı onayıyla `headed: true` parametresiyle tekrar
   çağırır; görünür pencere açılır, backend form görünene dek bekler
   (timeout ~3 dk). Kullanıcı giriş yapar, akış kaldığı yerden sürer.
3. **CAPTCHA tespiti:** `{"status": "captcha"}` döner → frontend teslim moduna
   geçer (CAPTCHA aşılmaz). Form hiç bulunamazsa `{"status": "form_not_found"}`
   → yine teslim modu (ilan metni çekilebildiyse optimize yine yapılır).
4. Sayfadan **ilan metni** (trafilatura) ve **form şeması** çıkarılır:
   `[{id, label, type: text|textarea|select|radio|checkbox|file, options?,
   required?}]`. CV dosya alanı `file` tipiyle işaretlenir.
5. **LLM** (MODEL_SMART, mevcut `chat_json`) tek çağrıda üretir:
   - `cv`: ilana göre optimize edilmiş CVData (vurgu/sıralama/dil; ATS
     prompt'undaki "asla bilgi uydurma" kuralı aynen geçerli),
   - `changes: [str]`: yapılan değişikliklerin listesi,
   - `cover_letter: str|null`: her zaman üretilir (teslim modunda da lazım);
     formda motivasyon metni alanı varsa aynı metin o alanın `answers`
     kaydına da yazılır,
   - `answers: [{field_id, value}]`: her form sorusuna CV'deki gerçek
     bilgilere dayalı cevap; seçenekli alanlarda seçeneklerden biri;
     cevaplanamayan alan boş bırakılır ve onay ekranında kullanıcıya
     işaretlenir.
6. Yanıt: `{status: "ready", form: [...], cv, changes, cover_letter, answers,
   job_text}`. Tarayıcı kapatılır (oturum profili diskte kalır) —
   prepare/submit arası canlı oturum tutulmaz, submit sayfayı yeniden açar.

#### `POST /apply/submit`

Girdi: kullanıcı onayından geçmiş `{url, answers (düzenlenmiş halleriyle),
cv: CVData, language}`.

1. Optimize CV'den ATS PDF üretilir (mevcut `render_pdf`).
2. Playwright sayfayı yeniden açar (profil çerezleriyle; gerekirse yine
   login_required akışı), alanları onaylı değerlerle doldurur, PDF'i file
   input'a yükler, submit butonuna basar.
3. Gönderim sonrası ekran görüntüsü alınır, base64 olarak döner (diske
   kalıcı yazılmaz — YAGNI).
4. Yanıt: `{status: "submitted", screenshot}` veya
   `{status: "failed", reason}` → frontend teslim moduna düşer, emek kaybolmaz.

Hata kodları: `LOGIN_REQUIRED`, `CAPTCHA_DETECTED`, `FORM_NOT_FOUND`,
`SUBMIT_FAILED` (i18n mesajlarıyla).

### Veritabanı — `applications` tablosu (yeni migration)

```
id uuid pk, user_id uuid (RLS owner),
cv_id uuid → cvs (kaynak CV),
optimized_cv_id uuid|null → cvs (onay sonrası kaydedilen kopya),
url text, job_text text|null,
cover_letter text|null, qa jsonb (form + onaylı cevaplar),
changes jsonb, status text: submitted | delivered | failed,
created_at timestamptz
```

- Onay ekranından sonra hangi yol seçilirse seçilsin kayıt düşülür
  (submitted/delivered) — kullanıcı başvuru geçmişini görür (geçmiş listesi
  UI'ı bu spec'te minimal: optimize sayfasında son başvurular listesi).
- Optimize CV, "Onayla ve Başvur" ile de "teslim et" ile de `cvs` tablosuna
  `source_cv_id` bağlı yeni satır olarak eklenir (dashboard'da görünür).

### Güvenlik ve etik sınırlar

- Gönderim **yalnızca** kullanıcının onay ekranındaki açık aksiyonuyla olur;
  otomatik/toplu başvuru yok — her akış tek ilan.
- CAPTCHA/anti-bot aşma girişimi yok; tespitte teslim moduna düşülür.
- Kullanıcı şifreleri asla alınmaz/saklanmaz; login yalnızca kullanıcının
  kendisi tarafından, görünür tarayıcı penceresinde yapılır.
- LLM cevapları CV'deki bilgilere dayanır; bilgi uydurma yasağı prompt'ta
  açıkça yer alır. Emin olamadığı alanı boş bırakıp kullanıcıya sorar
  (onay ekranında "doldurmanız gerekiyor" işareti).

### Test stratejisi

- **API:** Playwright soyutlaması ince bir arayüz arkasına alınır
  (`BrowserSession` benzeri); testlerde sahte HTML form fikstürleriyle form
  şeması çıkarımı, login/CAPTCHA tespiti ve doldurma mantığı test edilir.
  LLM `override_llm` ile sahtelenir. Gerçek site testi manuel yapılır
  (Greenhouse/Lever demo formları).
- **Web:** Onay ekranı (düzenlenebilir alanlar, iki buton), teslim modu ve
  login_required/captcha durum geçişleri mevcut vitest kalıbıyla test edilir.
- Mesaj parite testi yeni i18n anahtarlarını otomatik kapsar.

### Kapsam dışı

- LinkedIn / Kariyer.net gibi anti-bot platformlarda gönderim (teslim modu
  devreye girer).
- CAPTCHA çözme, toplu/zamanlanmış başvuru, başvuru takip botları.
- Ekran görüntüsünün kalıcı depolanması.

---

## Uygulama sırası

1. **Faz 1** tek başına uygulanır ve doğrulanır (panel + sayfa taşımaları +
   testler).
2. **Faz 2** arkasından gelir: migration → apply servisi (Playwright) →
   `/optimize` sayfası → onay/teslim akışları → testler.
