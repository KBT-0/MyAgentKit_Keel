# v0.11 elden geçirme ÖNERİSİ — review sistemi, worker döngüsü, gate ve release

Tarih: 2026-10-13. Durum: **ÖNERİ, uygulanmadı.** Her madde sahibin onayıyla, madde madde
uygulanır (sahip kararı, 2026-10-13: kit sahipsiz elden geçirilmez). Bağlayıcı kaynak:
`docs/research-ai-review-workflows.md` (master 247e040); M–O maddeleri ayrıca
`docs/research-token-optimization.md` (T) ve `docs/research-agent-kits-in-practice.md` (P)
raporlarına (master 733dc54) dayanır; her madde raporun numaralı bulgusunu
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
| Review başına kabul edilen bulgu oranı (precision) | kaydediliyor (F uygulandı; yazar beyanı, `usage_summary.py accepted=`) |

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
| low (trivial) | yalnız belge, yalnız test, tek dosya, risk listesi dışı | gate + **bir** hafif reviewer (medium effort, daraltılmış Important tanımı, nit tavanı); emsal: Cloudflare trivial = 2 hafif agent [7], Anthropic docs repo'da review'u daraltır, kaldırmaz [2] |
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

**Karar (sahip, 13 Ekim).** Üç katman kabul; low katmanda LLM review sıfır değil, tek hafif
reviewer. high tanımı (gate/hook/review/STATE/silme/eşzamanlılık) kabul, proje başına
`{{RISKY_AREAS}}` ile genişler. Uygulama onayı ayrı.

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
metni. **Karar (sahip, 13 Ekim).** Kabul: ileriye dönük kural High bloklar, Medium koşullu
fix, Low dosyalanır. Süren v0.11 işi için eski "Low'lar fix edilir" kararı geçerli kalır.

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
**Karar (sahip, 13 Ekim).** İki tur; sınır `review_dispatch.py`'de kod olarak (üçüncü tur
`exit 2`, yalnız `REVIEW_ROUND_EXCEPTION=neden` ile açılır, kayıtlı). Routing kural 4 kalkar.

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
**Karar (sahip, 13 Ekim).** Beş sensor da v0.11'e; sıra 1→5 (sıklık); her biri ayrı görev,
high katman review.

### E. Reviewer prompt'u yeniden yazılır: alt eşik, severity tanımı, "Do not report", Low tavanı, tur 2 daraltma, görev/risk bağlamı (kaynak: `docs/research-review-prompts-and-rules.md`, bundan sonra R)

**Ne değişir.** Bugünkü prompt "Report EVERY finding you can establish in this pass" ile başlar;
yayınlanmış hiçbir reviewer prompt'u böyle başlamaz (R §1-1: Codex "prefer outputting no findings"
[W5], Anthropic plugin "not certain → do not flag" [W3], ECC "a clean review is a valid review"
[W16]). İki köprüye tek paylaşılan sabit (R §4.1 taslağı, ≤ 350 kelime):
- **Alt eşik + kanıt üçlüsü:** bulgu = dosya/satır + tetikleyen girdi/durum + yanlış sonuç; üçü
  yoksa Low'a düşer ya da yazılmaz [W16][W5][W1].
- **Severity tanımı** bir cümleyle, bu kit için (Critical = veri kaybı, sessiz gate geçişi,
  güvenlik sınırı, sensor'suz platformda yanlış davranış; High = reproduce/caller ile izlenen
  yanlış davranış; Medium = adlandırılabilen girdiyle gerçek defect; Low = kalan) [W5][W7][W16].
- **"Do not report" listesi:** pre-existing (ayrı başlık, verdict'e girmez [W1]); check.sh/lint'in
  zorladıkları; stil/ad/refactor; olasılıksız ön koşullu teorik risk; "consider X"; dispositions'taki
  tasarım dışlamaları [W7][W3][W1].
- **Low tavanı 5 + "plus N similar"** [W1].
- **Tur ≥ 2:** önceki Critical/High için fixed/not + kanıt; yeni yalnız Critical/High [W1][W7]
  (C ile aynı).
- **Görev/risk/odak satırları** prompt'a girer: `--task-file` wrapper'dan geçer, `REVIEW_RISK`,
  `REVIEW_FOCUS` env (A'nın dar reviewer'ı burada) [W2][W7].
- **"Fix sketch" zorunluluğu kalkar** (açıklama+düzeltme isteyen prompt yanlış-ret oranını
  yükseltir [W22]; Codex "Do not generate a PR fix" [W5]).
- **Dispositions satır biçimi** tanımlanır: `<id> fixed|disproved|deferred|wont-fix — <kanıt>`;
  reviewer `wont-fix`/`deferred`'i Manual checks'e taşır, yeniden şiddetlendirmez [W7][W21].
- `validate()` Low bulguyla Accept'e izin verir (Codex ile eşitlenir; I.C.2 madde 2).

**Nasıl.** Prompt sabitleri tek modüle (`review_prompt.py`), iki köprü ve plugin kopyası aynı
baytları taşır (`package --check`). Test fixture'ları güncellenir. **Risk.** Recall düşer; karşılığı
D (sensor'lar) ve F (ölçüm: precision görülmeden ikinci prompt değişikliği yok, Cursor [W8]).
Karşı kanıt R §3: Cursor "aggressive" prompt + validator katmanı; bizde validator lead'dir.
**Efor.** O (prompt + fixture + wrapper'a üç env/arg). **Dosyalar.** `core/scripts/claude_bridge.py`,
`codex_bridge.py`, `review.sh`, `review_dispatch.py`, testler, plugin kopyası.
**Karar (sahip, 13 Ekim).** Kabul: R §4.1 taslağı temel; Fix sketch kalkar; Low tavanı 5; alt
eşiğin yanına Codex'in tamlık cümlesi eklenir ("Do not stop at the first qualifying finding;
continue until every qualifying finding is listed" [W5]) ki araç kullanan reviewer susmasın
(Cursor [W8] itirazı). Son prompt metni uygulama öncesi sahibe gösterilir.

### P. Review kural dosyaları 8–9 dosyadan 2'ye iner (kaynak: R §4.2, envanter I)

**Ne değişir.** Review ile ilgili ~14 000 kelime, 8–9 dosya; kapanış kuralı 8 yerde kopya; tur
limiti üç dosyada üç cevap; 12 çelişki (I.C). Hedef: `REVIEW_GATE.md` ≤ 600 kelime (riskli diff
katmanları A, roller, verdict eşiği B, tur sınırı C, dispositions biçimi, kapanış kuralı **bir
kez**) ve `REVIEW_RUNNING.md` ≤ 500 kelime (komut, env, limitler, fallback, arşiv). AGENTS.md'de
üç satır + işaretçi; WORKFLOW'da yalnız routing tablosu; SKILL.md ve cross-review.md işaretçi
[W19]. 12 çelişkinin her biri tek cevapla kapanır (R §4.2 tablosu).

**Neden.** [W1] "a long REVIEW.md dilutes the rules that matter most"; [W13] Copilot 4 000
karakter sınırı, "very long instruction files may result in some instructions being overlooked";
[W7] 200 satır üstü AGENTS.md "context bloat"; resmi örnek REVIEW.md'ler 90–110 kelime [W1][W14];
P raporu §1 kısa harita dosyaları; living-docs-never-bloat (sahip kuralı). **Risk.** Silinen bir
cümlenin bir vakayı koruduğu sonradan anlaşılır; karşılığı: envanter I.B'deki 89 kuralın her biri
için "kalır / birleşir / silinir" satırı, silinenlerin gerekçesi RESEARCH_LOG'a. **Efor.** K
(belge; lead yazar). **Dosyalar.** yukarıdakiler. **Karar (sahip, 13 Ekim).** Kabul: REVIEW_GATE ≤ 600, REVIEW_RUNNING ≤ 500 kelime; lead 89 kural
için kalır/birleşir/silinir listesini çıkarır, sahip listeyi bir kerede onaylar.

### F. Ölçüm — UYGULANDI (13 Ekim)

Dispositions anahtarları (`fixed:` / `disproved:` / `deferred:`) ve `REVIEW_SHADOW=1`
kayda girdi; `usage_summary.py` konfigürasyon başına `findings`, `per_round` ve
`accepted=A/T (yazar beyanı)` basar. Sahip kararı: oran yalnız bilgi, Tricorder [50]
gibi yazar puanlar, sonraki tur reviewer'ı doğrular, kapatma/değiştirme kararı sahibin
(yan ajanın öz-beyan uyarısı üzerine; %40 otomatik eşiği yok). Kural `core/docs/USAGE.md`.

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
`core/AGENTS.md`, `docs/ACCEPTANCE.md` şablonu. **Karar (sahip, 13 Ekim).** Kabul: tek final, merged diff'in daha az kısmını yazan taraf
(v0.11'de Claude), high, NEW label; ultra yalnız sahip ayrıca isterse; dogfood bir iş günü.

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
**Karar (sahip, 13 Ekim).** 2700/3600 kabul; iş tavanı YOK, bellek tek sınır kalır (üç-iş
maddesi düşer; retry sınıfı kalır); effort: xhigh yasak, high katman high, low/medium katman
medium (review.sh varsayılanı REVIEW_RISK'e bağlanır; M-2 ile aynı karar).

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
**Efor.** K. **Dosyalar.** `core/docs/REVIEW_GATE.md`, `core/docs/HANDOFF.md`. **Karar (sahip, 13 Ekim).** Kabul: davranış kuralı değiştiren belgede tek Claude low/medium
geçişi, Low tavanı 3, bloklamaz; diğer belgeler gate + okuma.

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
cümle) + backend dalındaki kayıt alanı (O, dal zaten açık). **Karar (sahip, 13 Ekim).** EVET;
gerçek model adı kayda girer, attest edilemezse "requested, unattested".

### M. Token ve bağlam tasarrufu (kaynak: `docs/research-token-optimization.md`, bundan sonra T)

Kitin maliyet modeli üç yanlış inanç taşıyor; T bunları ölçülmüş sayılara karşı düzeltiyor.
Öneri, T §5'in 11 adayından **ölçülmüş kazancı olan altısı**; gerisi düzeltme ya da ret.

| # | Değişiklik | Kanıt (T) | Beklenen | Risk | Efor |
|---|---|---|---|---|---|
| M-1 | Worker cache ömrü kova düzeyinde: `CLAUDE_CODE_SUBAGENT_PROMPT_CACHE_TTL=1h` spawn ortamına; frontmatter `cacheTtl` kaldırılır (usage credits'te yok sayılıyor) | T §1 [4][5]; `docs/worker-cost-setups.md` −36–38 % | 5 dk'dan uzun bekleyen worker'larda −%36 | Kısa worker'da 1h yazma 2×; lead <5 dk işte 5m'ye döner | K (spawn_worker.sh bir satır) |
| M-2 | Gate review effort'u: xhigh yasak; high katman high, low/medium katman medium (H ile aynı; **sahip kabul etti, 13 Ekim**) | T [44] xhigh=high çözüm, 2,4–4,5× maliyet; Codex xhigh 1,76–2,52× [37] | Tier-3 turlarında ~2× | Edge-case recall; E'nin gürültü kontrolü dengeler | K (REVIEW_GATE + review.sh varsayılanı) |
| M-3 | Lead session'ında `promptCacheTtl: 1h` yazılı; `/usage` "Prompt cache (main)" satırı mod raporuna girer | T [3][4]: plan limiti dolunca ana konuşma sessizce 5 dk'ya düşer | Aradan sonraki tam yeniden yazma (lead ~250k/request) önlenir | Kısa sık session'da 2× yazma | K (settings + WORKFLOW bir paragraf) |
| M-4 | Kompaksiyon politikası: 200k çizgisi kalır; compact yalnız cache sıcakken; >1 sa aradan sonra resume'da summary; yön değişince `/clear` + hand-off; Codex worker'da `model_auto_compact_token_limit` 200–250k | T [36][4][14][3][28][46]; maliyet ∝ pencere^2,55 | Compaction başına 300–700k uncached okuma kaçınılır | Yok (metin) | K (context-is-a-budget.md) |
| M-5 | Aynı context gerektiren kısa iş (lead'in kendi diff'inin iç review'u, kısa teşhis) **fork** sub-agent; taze sub-agent yalnız bağımsız iş | T [4][5][15]; P §5-3 | Worker başına bir başlangıç yazması (36–60k × 1,25–2×) | Fork ebeveynin geçmişini taşır; büyük lead'de pahalı → eşik: lead <120k | K (WORKFLOW kural) |
| M-6 | Ölçüm: her `-p` worker koşusu `total_cost_usd` + `modelUsage` + TTL kovasını rapor dosyasına yazar; `agent_cost.py` cache hit oranını ve miss nedenini gösterir (SLO: hit ≥ %80) | T [12][3][48][49]; P §5-2 (Claude Code ekibi hit oranına alarm koyuyor) | Doğrudan yok; yanlış routing kararını önler; F ile aynı sınıf | Yok | O (agent_cost.py) |

**Düzeltmeler (tasarruf sıfır, yanlış inanç gider):** `docs/context-is-a-budget.md`'deki "oturum
ortasında always-loaded doküman düzenlenmez, cache bozulur" gerekçesi yanlış (düzenleme oturuma
uygulanmıyor; T [4]); kural tutarlılık gerekçesiyle kalır, metin düzelir. "Her request'te MCP
katalog bedeli" iddiası Claude Code için eski (varsayılan ertelemeli; T [9][7]), Codex/gateway
için geçerli; kural ikiye ayrılır. Effort geçişi 5.5/Fable'da cache'i koruyor (T [4]); model
routing kural 4'ün "effort değişimi cache bozar" cümlesi silinir (Codex'te kalır).
**Reddedilenler (T §5):** Batch API, ccusage, keep-alive/poll plugin'leri, tool-çıktı kısaltıcı
eklentiler (RTK +%7,6 maliyet, Caveman ilan %65 → ölçülen %8,5; P [67][68]).
**Karar (sahip, 13 Ekim).** M-1…M-6 altısı da v0.11'e; M-1 ve M-3 settings değişikliği onaylı;
düzeltmeler ve retler aynen.

### N. Talimat dosyalarının yüklenmesi: her session'da tek büyük set yerine koşullu yükleme (kaynak: `docs/research-agent-kits-in-practice.md`, bundan sonra P)

**Bulgu.** Üç vendor da always-loaded dosyayı kısa "harita" tutuyor (Anthropic <200 satır,
OpenAI ~100 satır TOC + 32 KiB kesme, Cursor <500 satır/kural; P §1). Hakemli ölçüm:
geliştirici yazımı AGENTS.md süre −%28,6 / token −%16,6 [64]; ama context dosyaları genelde
başarı artırmadan maliyeti +%20 artırıyor ve "repo özeti" bölümleri faydasız [63]. Bizde
`ARCHITECTURE.md` ve `PHASES.md` her session yükleniyor; `AGENTS.md`'nin "Review gate" ve
"STATE.md discipline" blokları yalnız o işi yapan session'a lazım; path-scoped kural yok.

**Öneri.**
- N-1 Startup prefix'i ölç (`/usage` istek başı cache okuma; `claude -p --output-format json`
  ilk istek `cache_creation_input_tokens`). Veri yok; ölçmeden kesmek F'nin ilkesine aykırı.
- N-2 `AGENTS.md`/`CLAUDE.md` = harita (≤150 satır): komutlar, repo adabı, "nerede ne var".
  Review gate kuralları → reviewer brief'i ve `REVIEW_GATE.md` (zaten var, tekrar silinir);
  STATE.md disiplini → `.claude/rules/state.md` `paths: [STATE.md]`; riskli alan kuralları →
  `paths:` ile ilgili ağaca. Codex tarafı: alt dizin `AGENTS.md` (o ağaçtan dosya okununca eklenir).
- N-3 Salt-okunur teşhis/araştırma sub-agent'ı `omitClaudeMd: true` + Haiku (P §5-7).
- N-4 Overlay skill/command açıklama toplamı ölçülür (`/skill-doctor`); lead'in çağırmadığı
  skill'ler `disable-model-invocation: true` (P §5-8).
**Risk.** Kuralın yüklenmediği session kuralı çiğner; karşı önlem: D'nin sensor'ları (kural
prose değil check). **Efor.** N-1 K; N-2 O (dört dosya + overlay); N-3/N-4 K.
**Karar (sahip, 13 Ekim).** N-1 ölçüm + N-2 harita dönüşümü v0.11'de, P ile aynı oturumda;
N-3/N-4 v0.12.

### O. Emsalsiz pratikler: sahibin kuralıyla kaldırma/değiştirme adayı

P §5 sonu yedi pratiğin hiçbir kitte bulunmadığını kaydediyor. Sahip kuralı (13 Ekim):
emsalsiz = kötü işaret, savunulmaz. Her biri için gözlenen pratik ve öneri:

| Pratik | Gözlenen pratik (P) | Öneri |
|---|---|---|
| Çapraz-vendor review döngüsü (iki model sıfır bulguya kadar) | Tek reviewer, sabit tur (superpowers 5, Stripe 1–2 CI turu); Anthropic: reviewer bulgu üretmeye meyilli, yalnız doğruluk bulguları [1.2] | **Değiştir**: A + B + C zaten bunu yapıyor; iki vendor tek geçişte kalır (rapor §1.3 dekorelasyon), döngü kalkar |
| Bütçeye göre yedi adlı mod | Model/effort session başında sabitlenir (cache); mod kavramı yok | **Sadeleştir** (K): üç mod (normal / tasarruf / kapalı), effort tablosu T [44]'e göre |
| Cache-TTL maliyet modeli + "poll etme" kuralı | Vendor dokümanı aynı modeli anlatıyor ama kit kuralı olarak değil (T §1) | **Koru, düzelt** (M): model doğru, üç cümlesi yanlış |
| `Done:` trailer'ıyla zorunlu silme | OpenAI doc-gardening agent'ı + tech-debt tracker [23]; kimse commit trailer'ı zorlamıyor | **Değiştir**: trailer gate'i kalkar; `check.sh`'e "doc'taki path var mı" + "Done başlığı altı boş mu" sensoru (D sınıfı) |
| "Gate kırmızı görülmeden bitmiş sayılmaz" | `/goal` evaluator, Stop hook (deterministik), pre-commit [1.2] | **Değiştir**: kural prose'dan çıkar; Stop hook / pre-commit zaten aynı işi yapıyor (D) |
| Web isteğinde PII yasağı | Vendor gizlilik ayarları; kit kuralı olarak yok | **Koru** (güvenlik; sahip kuralı) |
| Spawn script'inin model+effort'suz brief'i reddetmesi | superpowers yalnız uyarır [28] | **Koru**: deterministik kontrol prose uyarıdan iyi (P §4, Anthropic "hooks deterministic"); emsal yok ama ilke emsalli |

**Karar (sahip, 13 Ekim batch).** "Emsalsiz = kötü" sözü anlık yorumdu, kalıcı kural değil.
"Daha az review önerme" ve "Done'lar silinsin" kuralları aynen kalır. Emsal yokluğu tek başına
kaldırma gerekçesi değildir; tablonun her satırı kendi raporu ve kanıtıyla ayrı karar alır
Satır kararları (sahip, 13 Ekim): çapraz-vendor döngüsü → A+B+C (karar verildi); yedi mod →
**üç mod** (normal / tasarruf / kapalı; claude-only ve codex-first ayrı mod değil, "kim yazar /
kim inceler" satırı); cache-TTL modeli → M; Done trailer → `check.sh` sensoru (silme yine
zorlanır); gate-red kuralı → D-5 sensoru; PII yasağı ve spawn'ın model/effort zorunluluğu
korunur.

### Q. Mandate (sahip, 13 Ekim, O-2 cevabında): kit ana hatta TEK MODELLE çalışır

"Bu noktadan sonra odağımız iki model değil; ağırlıklı olarak sadece Claude ile çalışacağız.
Codex ya da Kimi gibi diğer modeller dahil olabilsin, ama kit kesinlikle ikinci modele bağımlı
olmasın; ana mevzusu tek modelde çalışabilecek şekilde olsun." Sonuçları:
- Her review/gate/release mekanizması tek modelle tanımlanır: "diğer model" = **taze oturum,
  tercihen farklı tier** (bugünkü claude-only modu varsayılan olur; L ile GLM/Kimi backend'i
  ikinci model sayılabilir ama şart değil).
- A'nın high katmanı: iki paralel dar reviewer = iki taze Claude oturumu (farklı odak), ikinci
  vendor varsa onlardan biri olabilir.
- G'nin final'i: merged diff'i yazmayan taze Claude oturumu (high); Codex varsa tercih edilebilir.
- Codex adaptörü, codex-first modu ve `claude@NAME` kalır, "takılabilir" statüsünde; hiçbir
  gate ikisinin birden varlığını istemez.
- Kaynak: Anthropic Writer/Reviewer ayrı oturum [W2]; Adversarial Review [W21] ikinci bağımsız
  reviewer'ın kazanç sağlamadığı; Nine Judges [26] bağımsızlık model ailesine göre (yani ikinci
  aile olursa iyidir, zorunlu değil).
**Uygulama.** 1. sıradaki politika belgeleriyle aynı oturumda; E'nin prompt'u ve P'nin iki
dosyası tek-model dilinde yazılır.

## 3. Uygulama sırası (sahip onayından sonra; hiçbiri başlamadı)

| Sıra | Madde | Neden bu sırada |
|---|---|---|
| 0 | F (ölçüm) — UYGULANDI | Ölçmeden değiştirmek raporun kendi uyarısına aykırı (§4) |
| 1 | A, B, C, G, H, I, J, K (politika belgeleri) | Tek belge görevi, tek oturum, tek low/medium geçiş (I'ya göre); worker değil lead yazar, çünkü kuralların gerekçesi bu dokümanda |
| 2 | E (prompt) + P (kural dosyaları) | Politika oturduktan sonra prompt ve iki kısa dosya onu söyler; P'nin envanter kararı E ile aynı oturum |
| 3 | D-1 ve D-2 (locale matrisi, shell lint) | En sık iki sınıf; gate kodu olduğundan A'nın full katmanı |
| 4 | D-3…D-5 | v0.11 (sahip kararı); sıra sıklığa göre |
| 5 | L | Backend dalı merge edilirken |
| 1b | M-1…M-6, N-1 (ölçüm), N-2 (harita, P ile), O (kararlar) | Politika belgeleriyle aynı oturum; N-3/N-4 v0.12 |

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

Hepsi cevaplandı (13 Ekim batch). Doküman yaşam döngüsü: uygulanan madde silinir, kapanınca
dosya silinir (sahip kararı, soru 11).
