# v0.11 elden geçirme ÖNERİSİ — review sistemi, worker döngüsü, gate ve release

Tarih: 2026-10-13. Durum: **ÖNERİ, uygulanmadı.** Her madde sahibin onayıyla, madde madde
uygulanır (sahip kararı, 2026-10-13: kit sahipsiz elden geçirilmez). Bağlayıcı kaynak:
`docs/research-ai-review-workflows.md` (master 247e040); her madde raporun numaralı bulgusunu
`§x.y` (yönetici özeti maddesi) ve `[n]` (kaynak) ile anar, kanıt olmayan yerde "raporda kanıt
yok" der. Kit'in amacı sahibin tanımıyla: **AI destekli uzun soluklu proje geliştirme için
best-practice kiti; review makinesi değil.**

## 0. Bizim kendi sayılarımız (12–13 Ekim, master + 8 worktree, `.myagentkit/usage` ve `docs/reviews`)

Rapor §4 "bizim kitten eksik veri" diyordu; eldeki kayıtlardan çıkarılabilen kısım:

| Ölçüm | Değer |
|---|---|
| Tamamlanmış review arşivi | 39 (33 Reject, 6 Accept with Manual Checks, 0 Accept) |
| Bulgu dağılımı | 0 Critical, 10 High, 77 Medium, 104 Low (High = %5) |
| docs dalı (7 kB belge değişikliği) | 10 tur, hepsi Reject; Codex 5 tur 16.603 s (ort. 55 dk), Claude 5 tur 455 s (ort. 1,5 dk) |
| Codex high-effort review süresi | 37–58 dk (backend 2.246 s, peer-r2 2.288 s, behaviour-r2 3.372 s, cluster-a merge 3.475 s) |
| Claude review süresi (native Windows, Bash yok, REASONED) | 1–9 dk |
| Verdict'siz biten reviewer denemeleri | 3 timeout (2×7.198 s, 5.398 s), 5 content_flagged, 6 cli_error: toplam 35.074 s ≈ 9,7 saat |
| master finalleri (v011-master-r3…r6) | 4 tur, Reject / Accept-MC / Reject / Accept-MC sırasıyla |
| En sık bulgu sınıfı (arşivlerde anahtar kelime) | Windows 273, locale/UTF-8 91, quoting/echo/dash 80, mktemp/TMPDIR 64, trap/signal 64, symlink 44, killing test yok 39, mode bit 39, MAX_PATH 24 |
| Review başına kabul edilen bulgu oranı (precision) | **ölçülmüyor** (madde F) |

Yorum: profil rapor §1.2 ile birebir: Critical yok, High nadir, Medium/Low bol; "temiz" hiç
gelmiyor (0 düz Accept), yani döngü yakınsamıyor. Üç zaman aşımı altı ağır işin aynı anda
koşmasından (rapor bu konuda kanıt vermez; bizim gözlemimiz).

## 1. Korunanlar (rapor §6; bu öneri bunlara dokunmaz)

- Taze bağlamlı, yazarı olmayan reviewer; throwaway kopya; sandbox (§6.1, [1][22]).
- Çapraz vendor ikinci model; AUTHOR/REVIEWER rol olarak kalır, vendor olarak değil (§6.2, [8][26]).
- Severity + `Fix sketch` + REPRODUCED/REASONED kanıt formatı; tek evidence formatı iki yönde (§6.4, [2][8]).
- Tam self-test, `check.sh --self-test`, "gate kırmızı görülmeden bitmez" (§6.5, [1][22][23]).
- Adaptörlerin mekaniği (`claude_bridge.py`, `codex_bridge.py`, `review_dispatch.py`, usage kayıtları, chain checkpoint'leri): **değişmez.** Elden geçirme politika, prompt ve ölçüm katmanındadır; kod değişikliği yalnızca D ve F'de.

## 2. Öneri maddeleri

Her madde: **Ne değişir · Nasıl · Neden (kanıt) · Risk · Efor · Dosyalar · Sahibin kararı.**
Efor: K = yalnız belge, bir oturum; O = küçük kod + killing test; B = yeni mekanizma, tasarım + test + review.

### A. Risk katmanlı, tek geçişli review (serî "iki Accept kapısı" yerine)

**Ne değişir.** "Riskli diff → Codex review → Claude review → tüm High/Medium fix → temizlenene
kadar tekrar" yerine üç katman. Katmanı lead, brief'in zaten taşıdığı `Risk: low|medium|high`
satırıyla seçer; yeni alan yok.

| Katman | Ne girer | Review |
|---|---|---|
| low (trivial) | yalnız belge, yalnız test, tek dosya, risk listesi dışı | LLM review yok; gate + sahibin ya da brief'in manuel kontrolü (bugünkü "What counts as a risky diff" kuralı zaten bu; uygulamada aşılıyordu) |
| medium (lite) | risk listesindeki alanlara dokunan ama gate/hook/review araçlarına dokunmayan kod | **bir** reviewer, **bir** geçiş, yazarın karşı tarafı; yalnız High bloklar |
| high (full) | gate, hook, check script, review araçları, STATE helper, dosya silen/taşıyan mekanizma, eşzamanlılık | **iki** reviewer **aynı anda** (zaten WORKFLOW "The lead's steps" 2. adım), **dar prompt'larla**: biri taşınabilirlik/edge (Windows, locale, mktemp, trap, symlink), biri mantık/durum/test bütünlüğü; lead birleştirir ve dedup eder |

**Nasıl.** `REVIEW_GATE.md` "What counts as a risky diff" üç katmana ayrılır; `REVIEW_RUNNING.md`
"Rounds, labels and designs" katman başına kaç reviewer/tur olduğunu söyler; `HANDOFF.md`
`Risk:` satırının katmanı seçtiğini yazar; `AGENTS.md` review paragrafı kısalır. Dar prompt'lar
için `review.sh`'e yeni bayrak değil, `REVIEW_FOCUS=portability|logic` ortam değişkeni ile
prompt'a bir odak paragrafı (adaptörlerde tek satırlık ekleme; O).

**Neden.** §1.4 (sektör dakikalar ve 1–25 $; bizimki 40–120 dk), §1.5 (yalnız critical bloklar
[3][7]; Claude Code Review bloklamaz [2]), §1.3 (iki serbest reviewer tek reviewer'ı geçemedi
[25]; paralel dar uzmanlar + verification [7][8][6]), S5 (diff + çevre; context büyüdükçe recall
düşer [31]), [9] blast-radius tetikleyicileri. Bizim sayılar: 39 arşivde Critical 0, High 10.

**Risk.** medium katmanda taşınabilirlik hatası kaçar. Karşılığı D (sensor'lar): bulgu sınıfı
listemiz zaten belli, deterministik teste girer. İki paralel dar reviewer'ın toplam süresi
bugünkü tek Codex review'u kadar; token maliyeti tek genel review'dan fazla değil (aynı diff,
daha kısa prompt).

**Efor.** K (belgeler) + O (`REVIEW_FOCUS`). **Dosyalar.** `core/docs/REVIEW_GATE.md`,
`core/docs/REVIEW_RUNNING.md`, `core/docs/HANDOFF.md`, `core/AGENTS.md`, `core/docs/WORKFLOW.md`
("Review rounds"), `core/scripts/claude_bridge.py`, `core/scripts/codex_bridge.py` (prompt).

**Karar.** Katmanlar kabul mü? high katmanın tanımı (gate/hook/review/STATE/silme/eşzamanlılık)
yeterli mi, proje başına `{{RISKY_AREAS}}` ile genişler.

### B. Blocking eşiği: High bloklar, Medium karar ister, Low dosyalanır

**Ne değişir.** "Her High ve Medium fix, Low fix-or-file" yerine:
- **Critical/High:** merge öncesi fix, zorunlu (§1.5 Doğrulandı).
- **Medium:** aynı turda fix edilir *yalnızca* fix tek yerde ve testli ise; değilse issue olur ve
  sahip merge'de görür. Fix'i bir mekanizma ekleyen Medium (REVIEW_GATE "A fix that adds a
  mechanism…") doğrudan issue.
- **Low:** issue ya da BACKLOG satırı; **aynı turda fix edilmez.**

**Nasıl.** `REVIEW_GATE.md` "Verdicts" ve "Findings…" bölümleri; prompt'taki "Report EVERY
finding" kalır (reviewer her şeyi söyler), fakat verdict kuralı değişir: `Reject` yalnız
Critical/High ile; Medium/Low `Accept with Manual Checks`'e düşer ve manuel kontrol satırı
"issue #N açıldı" olur.

**Neden.** §1.5 ([3] yalnız P0/P1; [2] Important/Nit, bloklamaz; [7] yalnız critical "request
changes"), §1.2 ([30] %56 red; [29] hatasız kodda ısrarla bug bulma), S5 ("hiçbir kaynak
Medium'u zorunlu fix yapmıyor"; Low'u aynı turda fix etmek gürültüyü iş haline getirir).
Bizim sayılar: 181 bulgunun 104'ü Low, 77'si Medium; her biri bir fix turu + yeniden review.

**Risk.** Cross-platform shell kitinde bazı "Medium" gerçek taşınabilirlik hatasıdır (§6.6).
Karşılığı: D ile sensor'a giren sınıflar artık reviewer'a değil teste düşer; sensor'u olmayan
bir taşınabilirlik bulgusu reviewer prompt'unda **High** sayılır (E'deki "Important tanımı").

**Efor.** K. **Dosyalar.** `core/docs/REVIEW_GATE.md`, `core/AGENTS.md`, iki adaptörün prompt
metni. **Karar.** Sahibin 2026-10-13 kararı ("Low'lar yine fix edilir") v0.11'in süren işine
aitti; ileriye dönük kural için yeni karar gerekir. Önerim: Low = dosyala.

### C. Yakınsama kuralı: bir etiket altında en çok iki tur, ikinci tur daralmış kapsamla

**Ne değişir.** "Temizlenene kadar" döngüsü ve "ikinci kirli turdan sonra bir basamak yukarı"
(Model routing kural 4) kalkar. Yerine:
- **Tur 1:** tam kapsam, her bulgu.
- **Tur 2:** yalnız tur 1'in Critical/High fix'lerinin doğrulanması + yeni **Critical/High**.
  Medium/Low ikinci turda üretilmez (prompt bunu söyler).
- **Tur 3 yok.** Kalan şüphe sahibe ya da issue'ya gider; sahip "yeter" der ya da bir istisna
  turu ister (kayıtlı istisna, brief'te nedeniyle).
- Dispositions (`REVIEW_DISPOSITIONS`) ve etiket zinciri kalır: tur 2 tur 1'i görür.

**Nasıl.** `REVIEW_RUNNING.md` "Every round asks for the whole list" paragrafına tur 2 daraltması;
adaptör prompt'una "round ≥ 2: report Critical/High only, confirm earlier findings fixed or
not"; `WORKFLOW.md` kural 4 silinir, "Review rounds" ve "The lead's steps" 3. madde kısalır.
`review_dispatch.py` tur sayısını zaten biliyor (`round=`); üçüncü turu **reddetmek**
(`exit 2`, "round limit; owner exception needed: REVIEW_ROUND_EXCEPTION=reason") küçük kod (O);
sahip isterse yalnız belge (K).

**Neden.** §1.8 (Self-Refine 0 kazanç [25]; iterasyon pseudo-fix döngüsü [29]; plato [36];
Cursor'da iteration count artışı regresyon [6]; Reflexion ek turu SNR 5,1→1,95 [50]), §1.1
([2] "ilk review'dan sonra yalnız Important"), S5 one-shot vs iteratif ([9] insan scope
kararıyla sonlanır). Bizim sayılar: docs 10 tur hâlâ Reject; master r3–r6 Reject/Accept
sallanıyor; "0 düz Accept" döngünün tanım gereği bitmediğini gösterir.

**Risk.** İki turda kapanmayan gerçek bir High. Karşılığı: High için istisna turu sahibin bir
kelimesiyle açılır; D'nin sensor'ları tekrar eden sınıfı zaten yakalar.

**Efor.** K (+O için dispatcher limiti). **Dosyalar.** `core/docs/REVIEW_RUNNING.md`,
`core/docs/WORKFLOW.md`, `core/docs/REVIEW_GATE.md`, adaptör prompt'ları, (`review_dispatch.py`).
**Karar.** İki tur sınırı mı, üç mü? Dispatcher sınırı kodda mı, yalnız belgede mi (rules-that-
enforce: kodda olmayan kural ricadır; önerim kodda).

### D. Verification-first: tekrar eden bulgu sınıfları deterministik sensor olur

**Ne değişir.** REVIEW_GATE "What a reviewer attacks first" listesi bir reviewer listesi olmaktan
çıkıp **gate'in test matrisi** olur. Arşivlerimizdeki sıklık sırasıyla ilk beş sensor:

1. **Locale matrisi:** `check_kit.py` seçili suite'leri `LC_ALL=C` ve `LC_ALL=tr_TR.UTF-8`
   (Windows'ta `PYTHONUTF8=0` + ANSI code page) altında bir kez daha koşar. (locale/UTF-8: 91 anma)
2. **Shell taşınabilirlik lint'i:** `sh -n` zaten var; buna `shellcheck -s sh` (varsa) ve
   kit'in kendi grep'leri: `echo` ile değişken, `mktemp` `-p`/`--suffix`, `local` dışı bashism,
   `trap` sırası (`EXIT` öncesi `INT/TERM`). shellcheck yoksa NOTE, FAIL değil (CI'da zorunlu).
   (quoting/echo/dash 80, mktemp/TMPDIR 64, trap/signal 64)
3. **Symlink/junction fixture'ı:** boundary self-test'e symlink'li bir ağaç örneği; Windows'ta
   junction. (44)
4. **Uzun yol fixture'ı:** 260+ karakterlik bir worktree yolu ile spawn/close/clean testleri
   (`\\?\` öneki triage r3'te eklendi; testi matrise alınır). (24)
5. **Killing-test denetimi (mutation-lite):** `check_kit.py` yeni/değişen bir guard satırı için
   "hangi test bunu öldürür" sorusunu sormaz; bunun yerine `git diff` ile eklenen her `if …
   refuse/fail/exit` dalı için aynı diff'te bir test dosyası değişmemişse NOTE basar. Tam
   mutation testi (cargo-mutants benzeri) B efor; şimdilik NOTE yeterli. (39)

**Nasıl.** Her sensor kendi küçük görevi: tasarım bir paragraf, önce kırmızı görülür, negatif
test `check.sh --self-test`e girer ("Writing a gate" kuralı aynen). Sensor'a giren sınıf
REVIEW_GATE listesinden **silinir** (liste yalnız sensor'u olmayanları tutar; "living docs
never bloat").

**Neden.** §1.7 ([22] frontier model için tek final gate yeter, sürekli sensor gereksiz; zayıf
model için harness 3/10→10/10; [1] "Claude'a koşabileceği bir check ver"; [23] feedback
sensors; [12] revert edilince kırılan test; [52] mutation feedback 53→89,5), §5-D, §6.6 ("savunulamayan kısım
bunların her turda LLM tarafından yeniden keşfedilmesi"). Bizim sayılar: yukarıdaki beş sınıf
arşivlerde 350'den fazla anma; her biri bir fix turu üretmiş.

**Risk.** Sensor'un kendisi gate kodudur, yani high katman: her biri A'nın full review'undan
geçer; toplam efor en yüksek madde. Sensor yanlış pozitif verirse silinir ("test both
directions"). Windows'ta `shellcheck` kurulu değilse yalnız CI'da koşar.

**Efor.** O × 5 (her sensor ayrı görev; ilk ikisi en değerli). **Dosyalar.** `scripts/check_kit.py`,
`core/scripts/check.sh`, `core/scripts/boundary_selftests.sh`, `tests/`, `.github/workflows/ci.yml`,
`core/docs/REVIEW_GATE.md` (liste kısalır), `core/docs/WORKFLOW.md` "Writing a gate".
**Karar.** Beş sensor'un sırası ve hangilerinin v0.11'e (bence 1 ve 2), hangilerinin v0.12'ye
kalacağı.

### E. Reviewer prompt'una gürültü kontrolü: "What NOT to flag", nit tavanı, Important tanımı, kanıt çıtası

**Ne değişir.** İki adaptörün sabit prompt'una ve `REVIEW_GATE.md`'ye dört kural:
- **What NOT to flag:** D'nin sensor'ladığı sınıflar; stil/format (lint CI'da); diff dışı önceden
  var olan sorunlar ("Pre-existing" etiketiyle ayrı listelenir, verdict'e girmez); tasarım
  dışlamaları (zaten var).
- **Nit tavanı:** Low en çok 5 madde + "ve N benzeri"; docs değişikliğinde Low en çok 3.
- **Important (High) tanımı projeye göre:** bu kit için "sensor'u olmayan bir platformda yanlış
  davranış, veri kaybı, gate'in sessiz geçmesi, güvenlik sınırı". Bir docs repo'da daraltılır
  (yalnız yanlış ya da çelişkili talimat).
- **Kanıt çıtası (var olanı sertleştirme):** REASONED bir Medium da reproduce komutunu yazar;
  yazamıyorsa Low'a düşer. "Olabilir/muhtemelen" ile başlayan bulgu verdict'e sayılmaz.
- **Harness'i düzelt, artefact'ı değil:** aynı sınıftan bulgu iki ayrı review'da çıkarsa lead
  bunu D'ye (sensor) ya da E'ye ("What NOT to flag" / brief kuralı) işler; üçüncü kez LLM
  tarafından bulunması bir kit hatasıdır (RESEARCH_LOG'a girer).

**Nasıl.** Prompt metni iki adaptörde ortak bir Python sabiti (bugün de öyle mi, kontrol edilir;
değilse `review_test_support.py`'ye taşınır). Nit tavanı ve Important tanımı
`REVIEW_GATE.md`'de `{{REVIEW_IMPORTANT}}` benzeri bir yer tutucu değil, düz metin; proje
setup'ta kendi listesini yazar.

**Neden.** §1.1 ([1] boşluk bulması istenen reviewer bulgu üretir; [2] REVIEW.md: nit cap,
Important daraltma, verification bar, re-review convergence), [7] "en çok gürültü azaltan şey
'What NOT to flag'", [27] judgment'ı yürütülebilir kanıta bağla, [21] insan on the loop, §5-E.

**Risk.** Düşük: prompt değişikliği; test `test_claude_bridge`/`test_codex_quota` prompt
fixture'larını günceller. **Efor.** K + O (prompt + fixture). **Dosyalar.** adaptörler,
`core/docs/REVIEW_GATE.md`, `core/docs/HANDOFF.md`. **Karar.** Nit tavanı sayıları; Important
tanımı metni.

### F. Ölçüm: bulgu kabul oranı (precision) kayda girer; eşik altı reviewer konfigürasyonu kapanır; yeni konfigürasyon shadow'da başlar

**Ne değişir.** `REVIEW_DISPOSITIONS` dosyası zaten her bulguya "fixed / disproved / deferred"
diyor. `review_dispatch.py` bir sonraki turda bu dosyayı okuyor; aynı yerde sayar ve usage
kaydına `findings_total / fixed / disproved / deferred` yazar. `usage_summary.py` model×effort
başına **kabul oranı** (fixed+deferred / total) ve **tur başına yeni bulgu** basar. Kural: 20
review sonra kabul oranı %40'ın altındaki konfigürasyon (model, effort, odak) değiştirilir ya da
kapatılır; yeni bir konfigürasyon (örn. Codex medium yerine Claude Sonnet low; `gpt-6-astra`)
önce **shadow**: verdict'i sayılmaz, yalnız kaydedilir, 10–20 review sonra sayılara göre açılır.

**Nasıl.** Dispositions formatına her bulgu için zorunlu bir anahtar (`fixed:<sha>` /
`disproved:<kanıt>` / `deferred:#issue`); parse eden küçük fonksiyon + killing test;
`usage_summary.py`'ye iki sütun; `REVIEW_SHADOW=1` ile verdict `shadow` olarak arşivlenir ve
`closure`'a sayılmaz (dispatcher'da tek bayrak).

**Neden.** Rapor §4 son paragraf ("bu dört metrik olmadan çürütme yargıları bizim bağlamımızda
doğrulanamaz; ilk adım loglamak"), §5-F, [8] shadow mode, [30] red oranı ölçümü, [50]
Tricorder <%10 FP / Coverity >%30 terk, [6] online resolution rate ile deney, [39] Codex bench'te
#13/15 ve [65] high effort için kazanç kanıtı yok → Codex effort'unu düşürmek ölçülecek ilk deney.

**Risk.** Düşük; tamamen ek kayıt. Dispositions'ı yazan lead disiplini ister (zaten yazıyor).
**Efor.** O. **Dosyalar.** `core/scripts/review_dispatch.py`, `core/scripts/usage_summary.py`,
`core/scripts/agent_usage.py` (kayıt alanı), testleri, `core/docs/USAGE.md`,
`core/docs/REVIEW_RUNNING.md`. **Karar.** %40 eşiği; shadow süresi; ilk deney Codex high→medium mu.

### G. Release: cluster/master döngüleri yerine "merge → self-test → tek final review → bir gün dogfood → push"

**Ne değişir.** Sahip cluster katmanını kaldırdı (karar 1). Bu madde master'daki "her model bir
NEW-label final + kirli final → fix → diğer model fix'i review" döngüsünü de kaldırır:
1. Dallar master'a doğrudan merge (bağımlılık sırası, her merge'den sonra gate: WORKFLOW
   "Parallel work — contracts" aynen).
2. `check_kit` + tam self-test + CI üç OS (deterministik gate).
3. **Bir** final review, NEW label, high effort, **tek** model: merged diff'in daha az kısmını
   yazan taraf; ya da sahip isterse `/code-review ultra` (bulut, çok agent, 5–17 dk [62]).
   Final'in Critical/High'ı fix edilir ve yalnız o fix'i diğer model medium'da okur; Medium/Low
   issue'ya (B).
4. **Bir iş günü dogfood:** kit kendi üstünde kullanılır (spawn_codex, close_worker, mode, bir
   review); `docs/ACCEPTANCE.md`'ye "dogfood günü: koşulan komutlar, çıkan sorunlar" bir blok.
5. Sahibin OK'i ile push; sürüm başlığı push günü.

**Neden.** §1.9 ([10] günde 60–100 iç release, dogfood; [18] flag arkasında prod; [9] guardrail
paketi ile insansız merge; "günler süren doğrulama normu yok"), §1.3 ([26] AND-gate ~1,5
bağımsız oy değerinde), §5-G, §1.7 ([22] tek final gate). Bizim sayılar: master r3–r6 dört tur,
sallanan verdict; cluster-a'da content_flagged + 58 dk'lık merge review'u.

**Risk.** İki vendor'un ikisi de final'de bakmaz. Karşılığı: merged diff'in her parçası dal
seviyesinde A'nın katmanına göre zaten görüldü; final "merge'in kendisi"ni (çakışma çözümleri,
toplanan minimumlar) okur. Dogfood günü takvimde bir gün; sahip kabul ederse.

**Efor.** K. **Dosyalar.** `core/docs/WORKFLOW.md` ("The lead's steps" 3, "The strong review
cycle" dokunulmaz), `core/docs/REVIEW_GATE.md` (closure paragrafı), `core/docs/REVIEW_RUNNING.md`,
`core/AGENTS.md`, `docs/ACCEPTANCE.md` şablonu. **Karar.** Final'i hangi model; ultra kabul mü;
dogfood bir gün mü yarım gün mü.

### H. Review zaman kutusu ve yük: 45 dakika tavan, en çok üç ağır iş, Codex varsayılanı medium

**Ne değişir.**
- `REVIEW_TIMEOUT_SECONDS` varsayılanı 3600 → **2700**, tavan 7200 → **3600**. Zaman aşımı
  "verdict yok"tur: aynı kapsam bir daha 2 saat koşturulmaz; ya daha az yükle ya da `--commit`
  ile dilimlenerek yeniden (zaten böyle çözüldü).
- Lead aynı anda **en çok üç** ağır iş (review, Codex fix round, tam suite) başlatır; iki
  Codex review'dan fazlası yok. (Rapor bu konuda kanıt vermez; bizim gözlem: altı iş → üç
  timeout, 6 saat kayıp; dört iş → `git init` 0xC0000142.)
- Codex review'un varsayılan effort'u **medium**; high yalnız A'nın full katmanında ve yalnız
  bir reviewer için. F'nin ölçümü bunu doğrular ya da geri alır.
- `retry-capacity.sh`'nin yaptığı ("model at capacity" → 3 dk sonra tekrar) adaptöre girer:
  `unavailable` sınıfı, 12 denemeye kadar, kayıtlı (lead-notes'taki RESEARCH_LOG adayı).

**Neden.** §1.4 ([7] median 3,6 dk, P99 10 dk; [2] ~20 dk ve "time limit aşılırsa review başarısız
sayılır, merge'i bloklamaz"; S5 "2 saatlik timeout'un emsali yok"), [65] high effort için kazanç
verisi yok, [39] Codex #13/15. Bizim sayılar: docs'ta Codex medium bile 55 dk; 3 timeout × 2 saat.

**Risk.** 45 dk'da bitmeyen büyük bir diff → dilimleme (`--commit`) ya da sahibin tek seferlik
`REVIEW_TIMEOUT_SECONDS` yükseltmesi. **Efor.** K + O (varsayılanlar + retry sınıfı).
**Dosyalar.** `core/scripts/review.sh`, `review_dispatch.py`, `codex_bridge.py`,
`core/docs/REVIEW_RUNNING.md` "Unavailable reviewer", `core/docs/WORKFLOW.md` "Worker cost".
**Karar.** 2700/3600 değerleri; üç iş tavanı; Codex medium varsayılanı.

### I. Kod dışı değişiklik (docs, CHANGELOG, RESEARCH_LOG, brief'ler): LLM review döngüsü yok

**Ne değişir.** Belge değişikliği low katmandır: `test_doc_pointers` + `check.sh` belge
gate'leri + sahip ya da lead'in okuması. Bir belge değişikliği yalnızca davranış kuralı
değiştiriyorsa (WORKFLOW/REVIEW_GATE/AGENTS) **bir** Claude low/medium geçişi, **bir** tur,
Low tavanı 3, verdict bloklamaz. Vale benzeri prose linter **eklenmez** (YAGNI; rapor [61] S
düzeyinde kanıt).

**Neden.** §1.10 ([58] Stripe: deterministik + insan spot-check; [2] docs repo'da Important
daralt, nit 5; "çok turlu LLM review for docs: kanıt yok"). Bizim sayılar: docs dalı 7 kB için
10 tur, 17.058 s reviewer süresi, hâlâ Reject.

**Risk.** Yanlış bir talimat gözden kaçar; karşılığı belge gate'leri ve dogfood günü.
**Efor.** K. **Dosyalar.** `core/docs/REVIEW_GATE.md`, `core/docs/HANDOFF.md`. **Karar.** Davranış
kuralı değiştiren belgelerde tek geçiş kalsın mı, o da kalksın mı.

### J. İnsan "on the loop": karar noktaları adlandırılır

**Ne değişir.** Verdict LLM'in değil, lead'in doğrulamasından sonra **sahibin**dir (bugün de
"output is unverified INPUT" diyor; ama kapanış kuralı "iki model temiz dönünce kapanır" diyerek
kararı LLM'e bırakıyordu). Üç açık karar noktası:
1. **Katman ataması** brief'te (A): lead önerir, sahip görürse değiştirir.
2. **Blast-radius tetikleyicileri → sahibin okuması zorunlu:** gate/hook/check script, STATE
   helper, dosya silen/taşıyan mekanizma, `.claude/settings.json`/izinler, CI. Bu diff'ler
   LLM review'dan geçse de sahip diff'i (ya da lead'in 10 satırlık özetini) görmeden merge
   edilmez.
3. **"Yeter" kararı** (C'nin üçüncü tur istisnası) ve **Medium'un kaderi** (B) sahibindir; lead
   soruyu `AskUserQuestion` ile sorar, sahip yoksa issue açar ve devam eder (bloklamaz).

**Neden.** §1.6 ([8] risk-tiered insan onayı + risk ağırlıklı örneklem; [9] blast-radius
label'ı; [19] "insan kodu açıklayabilmeli"; S1 "insanlar AI review'unu review ediyor"; hiçbir
kaynak insanı devreden çıkaran çoklu-LLM verdict modeli raporlamıyor).

**Risk.** Sahibin zamanı; karşılığı 2. maddenin özeti 10 satır. **Efor.** K. **Dosyalar.**
`core/docs/REVIEW_GATE.md` "Verdicts", `core/docs/WORKFLOW.md` roller, `core/AGENTS.md`.
**Karar.** Tetikleyici listesi.

### K. Çalışma modları ve routing kuralları: döküman sadeleşir, mod kavramı kalır

**Ne değişir.** Yedi mod kalır (sahip kararıyla yeni). Değişen: her mod tanımındaki "independent
stopping rule ve fresh NEW-label final review" cümleleri A/C/G'ye referans olur; "A mode never
removes a review" → "a mode never lowers a change's tier". Model routing kural 4 (eskalasyon)
silinir (C), kural 6 F'nin ölçümünü kullanır, kural 7 (saver) aynen. Effort tablosu: review
satırı "medium; full katmanda bir reviewer high" olur (H).

**Neden.** Rapor §3 tablosunun "Karar veren / Tur sayısı / Blocking eşiği" satırları; A, C, H'nin
tutarlılığı. Raporda modların kendisi hakkında kanıt yok; dokunulmaz.

**Efor.** K. **Dosyalar.** `core/docs/WORKFLOW.md` "Model routing" ve "Working modes".
**Karar.** Yalnız tutarlılık; ayrı karar gerektirmez.

### L. Açık soru: `claude@NAME` (GLM gibi Anthropic-uyumlu backend) ikinci model sayılır mı?

**Öneri: EVET.** Dekorelasyonun kaynağı model ailesidir, CLI değil ([26] Nine Judges: etkin
bağımsızlık model ailesine göre; [8] "farklı agent'lar ortak kör noktayı paylaşmaz"). GLM/Kimi
başka bir ailedir; aynı Claude CLI'dan geçmesi bağımsızlığı azaltmaz, çünkü sandbox/prompt aynı
olsa da ağırlıklar farklıdır. Kayıt tarafı: usage kaydı `model` alanına backend'in gerçek model
adını yazmalı (attestation `modelUsage` ile mümkün mü, backend'e bağlı; mümkün değilse "requested,
unattested" — Codex'teki gibi). **Efor.** K (REVIEW_GATE "roles not vendors" paragrafına bir
cümle) + backend dalındaki kayıt alanı (O, dal zaten açık). **Karar.** Sahibin.

## 3. Uygulama sırası (sahip onayından sonra; hiçbiri başlamadı)

| Sıra | Madde | Neden bu sırada |
|---|---|---|
| 0 | F (ölçüm) | Ölçmeden değiştirmek raporun kendi uyarısına aykırı (§4); küçük kod, hemen veri üretir |
| 1 | A, B, C, G, H, I, J, K (politika belgeleri) | Tek belge görevi, tek oturum, tek low/medium geçiş (I'ya göre); worker değil lead yazar, çünkü kuralların gerekçesi bu dokümanda |
| 2 | E (prompt) | Politika oturduktan sonra prompt onu söyler |
| 3 | D-1 ve D-2 (locale matrisi, shell lint) | En sık iki sınıf; gate kodu olduğundan A'nın full katmanı |
| 4 | D-3…D-5 | v0.12 adayı; F'nin verisi sırayı değiştirebilir |
| 5 | L | Backend dalı merge edilirken |

## 4. Süren v0.11 işine uygulanışı (sahip kararı gerekir)

- Sekiz worktree'nin review döngüleri durmuş durumda (sahip emri). Süren üç Codex fix turu
  biter, commit edilir; **yeni review yok**.
- docs ve lint review-clean; triage/backend/behaviour/cluster-a son fix turuyla kapanır.
  Taşınan Low'lar (lead-notes) merge düzenlemesinde uygulanır: sahibin "Low'lar fix edilir"
  kararı süren iş için geçerli.
- Merge: watch + behaviour + backend → cluster-a yerine **doğrudan master'a**, bağımlılık
  sırasıyla (watch, peer, behaviour, backend, triage, lint, docs), her merge'den sonra
  `check_kit`. cluster-a dalı yalnız peer fix'lerinin kaynağı olarak kullanılır (cherry-pick).
- G'ye göre: tam self-test + CI → **bir** final review (öneri: Claude high, NEW label, çünkü
  v0.11'in büyük kısmını Codex fix turları yazdı; ya da ultra) → fix yalnız Critical/High →
  bir gün dogfood → push.
- CHANGELOG/RESEARCH_LOG: bu elden geçirmenin kendisi v0.11 başlığında bir madde; RESEARCH_LOG'a
  §0 tablosu "Kit'in kendi review verisi" olarak girer (rapor §4'ün istediği ilk ölçüm).

## 5. Sahibe sorular (cevaplananlar silinir)

1. A: üç katman ve high katman tanımı kabul mü?
2. B: ileriye dönük Low = dosyala, Medium = koşullu fix kuralı kabul mü?
3. C: iki tur sınırı; dispatcher'da kod olarak mı?
4. D: hangi sensor'lar v0.11'e (öneri: locale matrisi + shell lint), hangileri v0.12'ye?
5. G: final review tek model mi (hangisi), `ultra` mı; dogfood bir gün mü?
6. H: 2700/3600 s, üç iş tavanı, Codex medium varsayılanı kabul mü?
7. L: `claude@NAME` ikinci model sayılsın mı (öneri: evet)?
8. Bu dokümanın kendisi commit edilsin mi (öneri: evet, `docs/` altında; onaylanan maddeler
   uygulandıkça ilgili satırı silinir, kapanınca dosya silinir: living docs never bloat)?
