# CV-AI — MVP Aşama 1 Tasarım Dokümanı

**Tarih:** 2026-07-12
**Durum:** Onaylandı (kullanıcı ile bölüm bölüm gözden geçirildi)

## 1. Ürün Özeti

AI destekli CV analiz ve iş başvuru platformu. Uzun vadeli vizyon 5 özellik içerir;
bu doküman yalnızca **MVP Aşama 1** kapsamını tanımlar.

**MVP Aşama 1 kapsamı:**
1. Üyelik sistemi (e-posta + Google girişi)
2. PDF CV yükleme ve AI ile okuma (yapılandırılmış veriye dönüştürme)
3. İş ilanı linkine göre uygunluk skoru: 1-5 yıldız (%0-100) + gerekçeler
4. Tek tıkla ATS uyumlu CV'ye dönüştürme ve PDF indirme

**Kapsam DIŞI (sonraki aşamalar):** otomatik başvuru, iş ilanı eşleştirme (en iyi 10),
başvuru takip panosu, OCR (taranmış PDF desteği), ödeme sistemi.

**Hedef pazar:** Türkiye + yurtdışı. Arayüz TR/EN çift dilli (next-intl).

## 2. Mimari (Yaklaşım A — onaylandı)

```
Next.js (Vercel) ──▶ FastAPI (Railway) ──▶ OpenAI GPT-4o / GPT-4o-mini
      │                    │
      └────────┬───────────┘
               ▼
     Supabase (Auth + PostgreSQL + Storage)
```

**Monorepo yapısı:** `cv-ai/`
- `web/` — Next.js 15 + TypeScript + Tailwind + shadcn/ui (arayüz)
- `api/` — FastAPI + Python 3.11 (AI motoru)
- `docs/` — dokümantasyon

**Sorumluluklar:**

| Bileşen | Görev |
|---------|-------|
| Next.js | Sayfalar, CV yükleme UI, skor gösterimi, dil değiştirme |
| FastAPI | `POST /cv/parse`, `POST /score`, `POST /ats/convert`, `POST /job/fetch` |
| Supabase | Auth (e-posta + Google), PostgreSQL (RLS ile), Storage (PDF'ler) |
| OpenAI | CV→JSON (4o-mini), kriter çıkarma (4o-mini), skorlama (4o), ATS yeniden yazma (4o) |

**Güvenlik:**
- FastAPI her istekte Supabase JWT doğrular; anonim erişim yok.
- OpenAI API anahtarı yalnızca backend ortam değişkeninde; tarayıcıya asla gönderilmez.
- Supabase Row Level Security: her kullanıcı yalnızca kendi verisini görür (KVKK/GDPR temeli).

## 3. Veri Modeli

### profiles
| Alan | Tip | Not |
|------|-----|-----|
| id | uuid PK | = auth.users.id |
| full_name | text | |
| language | text | 'tr' \| 'en' |

### cvs
| Alan | Tip | Not |
|------|-----|-----|
| id | uuid PK | |
| user_id | uuid FK→profiles | |
| file_path | text | Storage'daki PDF yolu |
| parsed_data | jsonb | GPT çıktısı: kişisel bilgiler, deneyim, eğitim, beceriler, diller, sertifikalar |
| is_ats | boolean | ATS dönüştürülmüş versiyon mu |
| source_cv_id | uuid FK→cvs, null | ATS versiyonsa kaynak CV |
| created_at | timestamptz | |

### job_postings
| Alan | Tip | Not |
|------|-----|-----|
| id | uuid PK | |
| user_id | uuid FK | |
| url | text, null | manuel yapıştırmada null olabilir |
| title, company | text | GPT ile çıkarılır |
| description | text | ilan metni |
| fetch_method | text | 'url' \| 'manual' — engelleme oranını ölçmek için |

### evaluations
| Alan | Tip | Not |
|------|-----|-----|
| id | uuid PK | |
| cv_id | uuid FK→cvs | |
| job_id | uuid FK→job_postings | |
| percent | int 0-100 | |
| stars | int 1-5 | percent'ten türetilir: 1★=0-20 ... 5★=81-100 |
| strengths | jsonb[] | güçlü yönler |
| gaps | jsonb[] | eksik kriterler |
| suggestions | jsonb[] | iyileştirme önerileri |

**Kararlar:**
- `parsed_data` bir kez üretilir, tüm işlemlerde yeniden kullanılır (maliyet 1 kez ödenir).
- ATS dönüştürme orijinali bozmaz; `source_cv_id` bağlantılı yeni satır oluşturur.
- Skor gerekçeli saklanır; arayüz "neden bu yıldız?" sorusunu cevaplar.
- Aşama 2+ tabloları (applications vb.) mevcut şemayı değiştirmeden eklenir.

## 4. AI Akışları

### 4.1 CV Yükleme ve Okuma
PDF yükle → Storage'a kaydet → PyMuPDF ile metin çıkar → GPT-4o-mini ile standart
JSON şemasına dönüştür → `cvs.parsed_data`.

### 4.2 İlan Metni Çekme (ikili yol)
httpx + trafilatura ile sayfa metni çekilir. Başarısızsa (LinkedIn engeli vb.)
kullanıcıya "ilan metnini yapıştır" alanı gösterilir. `fetch_method` kaydedilir.

### 4.3 Uygunluk Skoru
CV JSON + ilan kriterleri → GPT-4o, **sabit rubrikle**:
beceri eşleşmesi %40, deneyim uygunluğu %35, eğitim/diğer %25.
Çıktı: percent, stars, strengths, gaps, suggestions.

### 4.4 ATS Dönüştürme
parsed_data → GPT-4o (ATS kuralları: standart bölüm başlıkları, tek sütun,
tablo/grafik/ikon yok, ölçülebilir ifadeler) → HTML şablon → WeasyPrint → PDF
→ Storage + yeni `cvs` satırı (`is_ats=true`).

## 5. Hata Yönetimi

| Durum | Davranış |
|-------|----------|
| Taranmış (görüntü) PDF | Net mesaj: "Metin tabanlı PDF yükleyin." (OCR kapsam dışı) |
| Geçersiz dosya / >10MB | Yükleme öncesi doğrulama + anlaşılır hata |
| İlan sayfası çekilemedi | Yapıştırma alanına düş (ikili yol) |
| GPT bozuk JSON döndürdü | Pydantic doğrulama → 1 otomatik yeniden deneme → nazik hata |
| OpenAI hizmet hatası | Exponential backoff + "birazdan tekrar deneyin" |
| Kötüye kullanım | Kullanıcı başına günlük AI çağrı limiti (başlangıç: 20) |
| Tekrarlanan skor | Aynı CV+ilan çifti önbellekten döner |

## 6. Arayüz Sayfaları

| Rota | İçerik |
|------|--------|
| `/` | Landing — ürün tanıtımı, kayıt CTA |
| `/login`, `/register` | Supabase Auth (e-posta + Google) |
| `/dashboard` | CV kartları listesi + "CV Yükle" |
| `/cv/[id]` | Okunan veri önizlemesi, "ATS'ye Dönüştür", indirme |
| `/cv/[id]/score` | İlan linki girişi (+ yapıştırma yedeği) → yıldız/% sonuç + gerekçe kartları |

Üst menü: TR/EN değiştirici, profil, çıkış. Görsel dil: Tailwind + shadcn/ui, sade SaaS.

## 7. Test Stratejisi

| Katman | Araç | Kapsam |
|--------|------|--------|
| Birim | pytest | PDF metin çıkarma, şema doğrulama, yıldız dönüşüm mantığı |
| Entegrasyon | pytest + mock OpenAI | 4 endpoint tam akış (gerçek API çağrısı yok) |
| E2E | Playwright | kayıt → yükle → skorla → dönüştür → indir |
| Tip güvenliği | TS strict + mypy | derleme anı hataları |

Geliştirme TDD ile ilerler (önce test, sonra kod).

## 8. Teknoloji Kararları Özeti

| Alan | Seçim | Gerekçe |
|------|-------|---------|
| Frontend | Next.js 15 + TS + Tailwind + shadcn/ui | sektör standardı, Vercel'e kolay dağıtım |
| Backend | FastAPI + Python 3.11 | AI/PDF ekosistemi en olgun |
| AI | OpenAI GPT-4o + GPT-4o-mini | kullanıcı tercihi; maliyet için görev bazlı model seçimi |
| PDF okuma | PyMuPDF | hızlı, güvenilir metin çıkarma |
| PDF üretme | WeasyPrint | HTML→PDF, ATS şablonu için ideal |
| İlan çekme | httpx + trafilatura | ana metin çıkarmada en iyi açık kaynak |
| Auth/DB/Storage | Supabase | hazır altyapı, RLS, PostgreSQL standardı |
| i18n | next-intl | TR/EN çift dil |
| Barındırma | Vercel (web) + Railway (api) | düşük maliyetli başlangıç |
