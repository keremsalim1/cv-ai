# Faz 2B — Optimize & Otomatik Başvuru Frontend (`/optimize`)

Tarih: 2026-07-23
Durum: Tasarım onaylandı (sohbet içinde), implementasyon planı bekliyor.

## Amaç

Faz 2A'da inşa edilen apply backend'ini (`POST /apply/prepare`, `POST /apply/submit`)
tüketen `/optimize` sayfasını inşa etmek: kullanıcı bir CV ve başvuru linki seçer;
LLM CV'yi ilana göre optimize edip form sorularını cevaplar; kullanıcı onay ekranında
her şeyi inceler/düzenler; sonra ya başvuruyu otomatik gönderir ya da materyalleri
teslim alır. Her başvuru geçmişe kaydedilir.

Bu doküman, `docs/superpowers/specs/2026-07-16-app-shell-and-auto-apply-design.md`
içindeki Faz 2 tasarımının frontend dilimini (2B) somutlaştırır ve şu kapsam
kararlarını sabitler:

- **Başvuru geçmişi DAHİL:** `applications` tablosu (yeni migration) + "son
  başvurular" listesi.
- **Login duvarı akışı TAM uygulanır:** `login_required` → görünür pencerede
  giriş → `headed:true` ile tekrar prepare.
- **Onay ekranında optimize CV salt-okunur:** sadece motivasyon mektubu ve form
  cevapları düzenlenebilir.
- **Optimize CV `cvs` tablosuna `is_ats=false`, `source_cv_id`=kaynak CV ile
  kaydedilir** (ATS kopyalarından ayrı, işe-özel optimize kopya).
- **Teslim modunda da optimize yapılır:** `captcha` ve `form_not_found`
  durumlarında da LLM çağrılır ve optimize CV + motivasyon + changes üretilir
  (aşağıdaki backend eklentisi). Bu, 2B planına bir backend görevi ekler.

## Backend sözleşmesi

Faz 2A `/apply/submit`'i hazır ve değişmez. `/apply/prepare` bu plan kapsamında
**küçük bir eklenti** alır (Task 1): LLM optimizasyonu artık sayfa görünür
olduğu her durumda (`ready`, `captcha`, `form_not_found`) çalışır — yalnız
`login_required`'da atlanır (sayfa henüz görünmüyor). Böylece teslim modunda da
optimize CV + motivasyon teslim edilir ("optimize yine yapılır" spec niyeti).

`POST /apply/prepare` — girdi `{cv, url, language, headed?}`. Günlük AI limitine
LLM'in çağrıldığı her durumda sayılır (`login_required` hariç). Yanıt:
- `{status: "ready", form: FormField[], cv, changes: string[], cover_letter, answers: FieldAnswer[], job_text}`
  — form bulundu, otomatik gönderim mümkün.
- `{status: "captcha", form, cv, changes, cover_letter, answers, job_text}`
  — form olabilir; optimize + cevaplar üretilir ama otomatik gönderim YOK
  (kullanıcı cevapları kopyalar).
- `{status: "form_not_found", form: [], cv, changes, cover_letter, answers: [], job_text}`
  — form yok; optimize CV + motivasyon teslim edilir.
- `{status: "login_required"}` — sayfa görünmüyor, optimizasyon yapılmaz.

Backend değişikliği özeti (Task 1): `prepare_application`'da `captcha` ve
`form_not_found` dalları erken dönmek yerine, `login_required` dışındaki tüm
yollar ortak LLM optimizasyon adımından geçer (boş form → `answers: []`);
`status` alanı yalnızca otomatik gönderimin mümkün olup olmadığını belirtir.
Mevcut `test_apply_prepare.py` testleri bu yeni yanıt şekline göre güncellenir.

`POST /apply/submit` — girdi `{cv, url, language, answers, headed?}`, yalnız auth.
Yanıt: `{status: "submitted", screenshot}` (base64 png) | `{status: "failed", reason}` |
`{status: "login_required"}` | `{status: "captcha"}`.

`FormField = {id, selector, label, type: "text"|"textarea"|"select"|"radio"|"checkbox"|"file", options: string[], option_selectors: string[], required: bool}`.
`FieldAnswer = {field_id, value}`.

Not: Backend veritabanına hiçbir şey yazmaz; persistans (cvs + applications)
tamamen frontend'in sorumluluğundadır (`/ats` sayfasındaki `insertCv` kalıbı).

## Mimari — tek sayfa, istemci durum makinesi

`/optimize` tek rota; `step` state'i akışı sürer:

```
form → preparing → [login] → approve → submitting → result
```

Rota arası büyük "prepared" verisi taşınmaz — sayfa state'inde tutulur
(`/ats` ve `/score` ile aynı desen). Çok rotalı sihirbaz (B) ve modal (C)
alternatifleri, geçici veriyi rotalar arası taşımanın kırılganlığı ve mevcut
kalıba yabancılığı nedeniyle elendi.

### Durumlar

- **form:** `CvSelect` (mevcut) + başvuru linki `<input>` + TR/EN dil seçici
  (`/ats`'teki bileşenle aynı markup) + "Hazırla" butonu → `applyPrepare(cv, url, lang, false)`.
- **preparing:** `ProgressBar` (mevcut; 60sn sonrası yoğunluk uyarısı dahil).
- **login:** `applyPrepare` `login_required` dönerse. "Açılan pencerede giriş
  yapın" açıklaması + "Pencerede giriş yap ve devam et" butonu →
  `applyPrepare(cv, url, lang, true)`. Bu ikinci çağrı sırasında ProgressBar
  "tarayıcıda giriş bekleniyor" metniyle gösterilir (backend form görünene dek
  ~3dk bekler). Dönüş `ready` ise approve'a geçilir; yine `login_required` ise
  aynı ekranda kalınır (kullanıcı tekrar deneyebilir).
- **approve:** Onay ekranı (aşağıda).
- **submitting:** `applySubmit` beklenirken `ProgressBar`.
- **result:** Sonuç ekranı (aşağıda).

`captcha` veya `form_not_found` dönerse doğrudan **approve** ekranına geçilir
ama teslim modunda: "Onayla ve Başvur" butonu gizlenir, "bu sayfa otomatik
gönderime uygun değil, materyalleri teslim alabilirsiniz" notu gösterilir.
Backend eklentisi sayesinde bu durumlarda da `cv` + `changes` + `cover_letter`
gelir; `captcha`'da `form` + `answers` de gelir (kullanıcı kopyalar),
`form_not_found`'da form boş olur (yalnız CV özeti + motivasyon + ATS PDF).

## Onay ekranı — `ApprovalScreen`

- **Optimize CV özeti** (isim, başlık, özet, deneyim/eğitim/beceri satırları) —
  **salt-okunur inceleme.** Yanında **"neler değişti"** listesi (`changes`).
- **Motivasyon mektubu** (`cover_letter`) — düzenlenebilir `<textarea>`.
- **Form cevapları** — her `FormField` için `FormAnswerField` bileşeni, tipe göre:
  - `text` / `textarea` → `<textarea>`
  - `select` / `radio` → gerçek `options` ile `<select>`
  - `checkbox` → `<input type=checkbox>` (değer "yes"/"no")
  - `file` → düzenlenemez bilgi notu: "CV'niz ATS PDF olarak otomatik yüklenecek"
  - Boş bırakılmış **required** alan → "doldurmanız gerekiyor" rozeti.
- **Aksiyonlar:** "Onayla ve Başvur" → `applySubmit(cv, url, lang, düzenlenmiş answers)`.
  "Sadece bana teslim et" → gönderim yok, doğrudan teslim-modu sonucu.

Düzenlenen değerler (`answers`, `cover_letter`) sayfa state'inde tutulur;
motivasyon alanı formdaki bir alana karşılıksa (backend onu ilgili `answers`
kaydına da yazar) kullanıcının motivasyon düzenlemesi submit'te o alana yansıtılır.

## Sonuç ekranı — `ResultScreen`

- **submitted:** başarı durumu + gönderim sonrası **ekran görüntüsü**
  (`data:image/png;base64,<screenshot>` inline `<img>`).
- **delivered** (kullanıcı "teslim et" seçti) **veya failed** (submit `failed`
  döndü — emek kaybolmaz): **ATS PDF indir** (mevcut `atsPdf(cv, lang)` +
  `downloadBlob`), **motivasyon metni** ve **cevaplar** için kopyala butonları.
- captcha/form_not_found teslim modu da buraya düşer.
- `applySubmit` beklenmedik şekilde `login_required` / `captcha` dönerse
  (sayfa prepare ile submit arasında değiştiyse) `failed` gibi ele alınır →
  teslim modu (emek kaybolmaz, `status: failed` kaydedilir).

### Persistans (her sonuç yolunda)

1. Optimize CV `cvs` tablosuna eklenir: `insertCv({user_id, file_path, parsed_data: optimizedCv, is_ats: false, source_cv_id: seçilenCvId})`.
   ATS PDF Supabase storage'a yüklenir (file_path), `/ats` sayfasındaki kalıpla.
2. `applications` tablosuna bir satır düşülür: `insertApplication({...})` —
   `status`: `submitted` | `delivered` | `failed`.

## Veri katmanı

### `web/src/lib/api.ts` (yeni fonksiyonlar)

```
applyPrepare(cv, url, language, headed=false): Promise<PrepareResult>
applySubmit(cv, url, language, answers, headed=false): Promise<SubmitResult>
```

Mevcut `apiUrl` / `authHeaders` / `ensureOk` altyapısını kullanır (Bearer token,
`{detail.code}` hata şekli, `ApiError`).

### `web/src/types/api.ts` (yeni tipler — backend `schemas.py`'yi aynalar)

```ts
type FieldType = 'text'|'textarea'|'select'|'radio'|'checkbox'|'file'
interface FormField { id, selector, label, type: FieldType, options: string[], option_selectors: string[], required: boolean }
interface FieldAnswer { field_id: string, value: string }
// ready/captcha/form_not_found share the optimized payload; only `status`
// gates whether auto-submit is offered. login_required carries nothing.
interface OptimizedPayload { form:FormField[], cv:CVData, changes:string[], cover_letter:string|null, answers:FieldAnswer[], job_text:string }
type PrepareResult =
  | ({ status:'ready' } & OptimizedPayload)
  | ({ status:'captcha' } & OptimizedPayload)
  | ({ status:'form_not_found' } & OptimizedPayload)
  | { status:'login_required' }
type SubmitResult =
  | { status:'submitted', screenshot:string }
  | { status:'failed', reason:string }
  | { status:'login_required' }
  | { status:'captcha' }
```

### `applications` tablosu — yeni migration `supabase/migrations/0002_applications.sql`

`0001_init.sql`'deki RLS kalıbıyla:

```
id uuid pk default gen_random_uuid(),
user_id uuid not null references auth.users(id),
cv_id uuid references cvs(id) on delete set null,        -- kaynak CV
optimized_cv_id uuid references cvs(id) on delete set null, -- kaydedilen optimize kopya
url text not null,
job_text text,
cover_letter text,
qa jsonb not null default '[]',      -- form alanları + onaylı cevaplar
changes jsonb not null default '[]',
status text not null,                -- submitted | delivered | failed
created_at timestamptz not null default now()
```

RLS: owner = `user_id` (select/insert/delete self). `on delete set null` ile bir
CV silinse de başvuru geçmişi kalır.

### `web/src/types/db.ts` + `web/src/lib/db.ts`

```
interface ApplicationRow { id, user_id, cv_id, optimized_cv_id, url, job_text, cover_letter, qa, changes, status, created_at }
type NewApplication = Omit<ApplicationRow, 'id'|'created_at'>
insertApplication(sb, row): Promise<ApplicationRow>
listApplications(sb): Promise<ApplicationRow[]>   // created_at desc
```

## Bileşen ayrışımı

- `web/src/app/(app)/optimize/page.tsx` — orkestratör (durum makinesi, Suspense sarmalı).
- `OptimizeForm` — CV seç + link + dil + "Hazırla".
- `LoginPrompt` — login_required ekranı + headed tekrar-dene.
- `ApprovalScreen` — CV özeti (salt-okunur) + changes + motivasyon + form cevapları + 2 buton.
- `FormAnswerField` — tek alanı tipe göre render eder.
- `ResultScreen` — submitted (screenshot) / delivered-failed (indir + kopyala).
- `RecentApplications` — `listApplications` ile minimal liste (optimize sayfası altı).

Yeniden kullanım: `CvSelect`, `ProgressBar`, `Button`, `ui/textarea`, `ui/input`,
`downloadBlob`, `messageKeyForCode`, `insertCv`, `atsPdf`.

## Kenar taşları

- **Sidebar:** `AppSidebar`'daki pasif `<span>` (Send ikonu + "soon" rozeti,
  satır 46-55) aktif `<Link href="/optimize">`'e çevrilir; `/optimize` ITEMS'e eklenir.
- **Rota koruması:** `/optimize` mevcut korumalı-rota kalıbıyla (auth yoksa
  `/login`'e yönlendir), boş-CV durumu (CV yoksa "önce CV yükleyin") — `/ats` ile aynı.
- **i18n:** `optimize.*` + `sidebar.optimize` (zaten var) + hata kodları
  (`LOGIN_REQUIRED` vb. gerekiyorsa) en/tr; parite testi otomatik kapsar.
- **Next.js:** `web/CLAUDE.md` uyarısı — kod yazmadan önce
  `node_modules/next/dist/docs/` ilgili rehber okunacak; `useSearchParams`
  kullanımı `/ats`'teki gibi `<Suspense>` içinde.

## Test stratejisi (mevcut vitest kalıbı)

- **Onay ekranı:** düzenlenebilir motivasyon + form cevapları, boş-required
  rozeti, iki buton doğru API'yi çağırır.
- **Durum geçişleri:** login_required → LoginPrompt → headed tekrar-dene;
  captcha/form_not_found → teslim modu; ready → approve.
- **Sonuç/persistans:** submitted ekran görüntüsü render; delivered ATS PDF
  indir + kopyala; her yolda `insertCv(is_ats=false)` ve `insertApplication`
  doğru argümanlarla çağrılır.
- **db/api:** yeni `applyPrepare`/`applySubmit`/`insertApplication`/`listApplications`
  birim testleri (mevcut `api.test.ts` / `db.test.ts` kalıbı, fetch/supabase mock'lu).
- Mesaj parite testi yeni i18n anahtarlarını otomatik kapsar.

## Kapsam dışı (sonraki fazlar)

- Anti-bot platformlar (LinkedIn/Kariyer.net) — teslim moduna düşer.
- Başvuru detay/düzenleme sayfası; geçmişte yeniden-gönderim.
- Ekran görüntüsünün kalıcı depolanması (sadece sonuç ekranında gösterilir).
- Toplu/zamanlanmış başvuru.
