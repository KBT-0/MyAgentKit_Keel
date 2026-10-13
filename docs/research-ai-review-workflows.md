<!-- BINDING RESEARCH: every proposal about the review system, worker loops, gates or release practice of this kit must cite a numbered finding of this report, or say that the report has no evidence on the point. Owner decision of 2026-10-13. -->

# AI destekli yazılım geliştirmede code review pratiği (2025–2026): kanıta dayalı araştırma raporu

Tarih: 2026-10-13. Kapsam: AI tarafından yazılan değişikliklerin review'u; resmi dokümanlar, mühendislik blogları, arXiv makaleleri, forum/topluluk ve açık kaynak "kit"ler. Kaynak numaraları `[n]` köşeli parantezle, tam liste bölüm 7'de. Her kaynak için güvenilirlik etiketi: **R** (resmi doküman), **P** (hakemli/preprint makale), **B** (mühendislik blogu / vendor), **F** (forum/anekdot), **S** (ikincil aktarım; birincil kaynak doğrulanamadı).

Değerlendirilen bağlam ("bizim kit"): her branch için worker-fix → bağımsız Codex reviewer (yüksek reasoning, 40–60 dk, sandbox kopya, Accept/Reject + High/Medium/Low) → ikinci reviewer (Claude Opus) → tüm High/Medium fix, Low fix-or-file → temiz olana kadar tekrar; sonra cluster ve master seviyesinde aynı döngü + iki "final" review + tam self-test. Branch başına 3–10 tur, release günler sürüyor, review timeout 2 saate kadar, 7 kB docs değişikliği 10 tur.

---

## 1) Yönetici özeti

Her madde: **Doğrulandı / Çürütüldü / Kanıt yok** = gözlenen pratik bizim yöntemi destekliyor mu?

1. **"Sıfır bulgu kalana kadar LLM review turu" bilinen ya da önerilen bir pratik değil.** Hiçbir resmi doküman, mühendislik blogu ya da makale bunu önermiyor. Tam tersi: Anthropic'in resmi best-practices sayfası "boşluk bulması istenen reviewer, iş sağlam olsa da bulgu üretir; her bulgunun peşine düşmek over-engineering'e götürür" diyor [1]; Code Review dokümanı "ilk review'dan sonra yeni nit'leri bastır, sadece Important bildir; tek satırlık fix yedinci tura stil yüzünden ulaşmasın" kuralını örnek veriyor [2]. → **Çürütüldü.**
2. **LLM reviewer'lar sistematik olarak aşırı bulgu üretir; "temiz" olmak bir yakınsama değil, reviewer'ın o turda tetiklenmemesidir.** 31.073 CodeRabbit yorumunun %56,3'ü geliştirici tarafından reddedildi (ana neden false positive) [30]; iteratif bug-fix çalışması LLM'lerin hatasız programlarda ısrarla "bug buldu" ve doğru kodu bozma oranının bozuk kodu düzeltme oranından yüksek olduğunu gösterdi [29]. Bizim bulguların "edge case ağırlıklı, fonksiyonel bug nadir" profili bu literatürle birebir örtüşüyor. → **Çürütüldü (turların marjinal değeri düşük).**
3. **İki farklı vendor'dan reviewer, korelasyonlu hataları tam gidermez ama bir miktar yardımcı olur.** Apple'ın "Nine Judges, Two Effective Votes" çalışması 7 model ailesinden 9 judge'ın etkin bağımsız oy sayısının 2,18 olduğunu, en iyi tek judge'ın paneli yakaladığını ya da geçtiğini buldu [26]. Adversarial Review makalesinde iki bağımsız reviewer tek reviewer'ı geçemedi (LCB %75 vs %77) [25]. Anthropic ve Cloudflare çoklu-agent kullanıyor ama **dar odaklı paralel uzmanlar + verification adımı** şeklinde, seri "ikinci görüş" olarak değil [7][8]. → **Kısmen doğrulandı, uygulama biçimi farklı.**
4. **Review süresi ve maliyeti: sektör referansı dakikalar ve 1–25 $; bizimki 40–120 dk.** Cloudflare 5.169 repo üzerinde median 3 dk 39 sn, ortalama 1,19 $ [7]; Anthropic'in managed Code Review'u ortalama 20 dk, 15–25 $ [2]; ultrareview 5–17 dk [62]. Bizim tek review süremiz sektördeki en ağır üründen 2–6 kat uzun, tur sayısı ile çarpıldığında 1–2 büyüklük mertebesi fazla. → **Çürütüldü.**
5. **Blocking eşiği: pratik "sadece kritik/P0–P1 bloklar, geri kalanı yorum" yönünde.** Codex GitHub review'u yalnızca P0/P1 bildiriyor [3]; Claude Code Review Important/Nit ayrımı yapıp hiçbir PR'ı bloklamıyor [2]; Cloudflare'de tek bir warning bloklamıyor, yalnızca critical "request changes" yapıyor [7]. Bizim "her Medium fix" kuralı sektörden daha katı. → **Çürütüldü (Medium için), Doğrulandı (High için).**
6. **İnsanın rolü: hesap verebilir son karar + risk tiering; AI reviewer tavsiye verir.** Anthropic kritik/regüle kod için insan onayı, düşük risk için otomatik onay + risk ağırlıklı örnekleme [8]; Duckbill'de blast-radius tetikleyicileri (auth, public API, non-additive schema) zorunlu insan review'u açıyor [9]; Ghostty "insan kodu AI yardımı olmadan açıklayabilmeli" [19]. Bizim modelde insanın yeri (verdict'i kim onaylıyor, tiering var mı) belirsiz. → **Kanıt, risk-tiered insan karar noktası lehine; bizde eksik.**
7. **Efor, review'dan çok spec/test/harness'e kayıyor.** Willison: "işin kanıtlanmış kodu teslim etmek" — manuel test + regresyon testi + agent'ın kendi kanıtı [12]; Beck: TDD "superpower" [20]; Böckeler: insan "on the loop" — artefact'ı değil harness'i düzelt [21]; harness çalışması: frontier model için sürekli sensor gereksiz, **tek final gate yeterli**, zayıf model için harness kabul oranını 3/10→10/10 çıkardı [22]. Bizim self-test suite'imiz bu yönde doğru; ağırlığın review'da olması ters. → **Kısmen doğrulandı.**
8. **Çok turlu/çok agent'lı review'da azalan getiri ölçülmüş.** Self-Refine sıfır kazanç (77%→77%) [25]; çok agent'lı öğrenme çerçevesinde 3 agent en büyük sıçrama, ek turlar ~8. turda plato [36]; Cursor "iteration counts, validators, agentic designs" dahil birçok değişikliğin metrikleri **geriye götürdüğünü** raporladı [6]; grader'larda self-consistency 5× maliyetle %38 daha kötü kalibrasyon [64]. → **Çürütüldü (3–10 tur için).**
9. **Küçük iç araç/kit release'i için "günler süren doğrulama" normu yok.** Claude Code ekibi günde 60–100 iç release, ~1 dış release; dogfooding ilk gün %20 → beşinci gün %50 [10]; Thorsten Ball feature flag arkasında prod'a çıkıp kendi üzerinde test [18]; Duckbill human review'lu PR'da median merge 26 saat, review'suz 1 saat [9]. → **Çürütüldü.**
10. **Docs/ops/data gibi kod-dışı alanlarda QA: deterministik linter (Vale) + insan spot-check + insana kalibre LLM judge; çok turlu LLM review yok.** Stripe docs asistanı: nightly eval, insan skorlarına kalibre LLM-as-judge, haftada yüzlerce özet insan review'u [58]; Anthropic REVIEW.md örneği "docs repo'da Important tanımını daralt, nit'leri 5'le sınırla" [2]. 7 kB docs için 10 tur → **Çürütüldü.**

---

## 2) Soru bazlı bulgular

### S1. Ciddi pratisyenler AI kodunu nasıl review ediyor?

**Kim review ediyor.** Baskın model üç katmanlı: (a) deterministik gate'ler (test, lint, typecheck, SAST, coverage eşiği), (b) tek geçişli AI review (tavsiye niteliğinde), (c) risk katmanına göre insan onayı. Pragmatic Engineer'ın 2026 yazısı en yaygın yaklaşımı "insanlar AI review'unu review ediyor" olarak tarif ediyor; Weaviate CTO'sunun döngüsü: adversarial agent review → **insan scope kararı** → agent fix → tekrar ya da bitir ("muhtemelen insan kararı") [9]. Uber uReview düşük güvenli yorumları atıp sadece önemli olanları gösteriyor [9][68]. WeTravel gürültü yüzünden AI review'u kapattı, Haziran'da yeniden denedi, hâlâ gerekçelendiremedi [9].

**Anthropic'in kendi SDLC'si** [8] **(B, birincil ama vendor):** CLAUDE.md'de güvenli kodlama kuralları; PR öncesi `/security-review`; CI'da **her biri dar odaklı, ayrı context'li çok sayıda review agent'ı** ("tek mega-prompt'tan iyi, çünkü ortak kör noktaları yok"); agent'lar bulgularını **kanıtlamak zorunda**; deterministik SAST doğrudan PR'a yazıyor; invariant testleri (bir kullanıcı başkasının verisini okuyamaz) ek manuel review tetikliyor; kod tabanları riske göre katmanlı, kritik/regüle kod insan onayı istiyor; otomatik onaylar loglanıp risk-ağırlıklı örneklemle insan tarafından denetleniyor; yeni reviewer'lar **shadow mode**'da başlıyor ve kötü niyetli değişikliklerle red-team ediliyor. Sayılar: Claude merged kodun ~%80'ini yazıyor; "substantive review comment" alan PR oranı %16→%54; geçmiş claude.ai incident'larının ~1/3'ü bugünkü otomatik süreçle yakalanırdı. Claude Code ekibinde Claude Tag product-engineering PR'larının ~%65'ini landed ediyor; **core için insan code owner onayı sürüyor**, dış katmanlar için otomatik review + CI + incident'lardan türeyen eval seti [11][67].

**Cloudflare** [7] **(B, ölçülü):** koordinatör + 7 uzman reviewer (quality, docs, performance, security, internal codex uyumu, AGENTS.md doğruluğu, release). Risk tier'a göre derinlik: trivial 2 agent, lite 4, full 7+. "En çok gürültü azaltan şey prompt'taki 'What NOT to flag' bölümleri oldu." Sınırlamalar: mimari bağlam, cross-system etki, subtle concurrency. "İnsan review'un yerine geçmez."

**Bireysel uzmanlar.** Willison: author işin çalıştığını **kanıtlamakla** yükümlü; happy path + edge case manuel test, komut çıktısı/ekran kaydı PR'a yapıştırılır, her değişikliğe revert edilince kırılan bir test eklenir, agent'a kendi işini kanıtlatılır [12]; "review etmediğin kodu PR'a koyma" anti-pattern [15]; ama 2026'da kendisi de "implementasyonu okumadan feature prompt'lamaya" başlayıp zihinsel modelini kaybettiğini (cognitive debt) yazdı [13]. Ronacher: agent'ı izleyerek güven kazanıyor, nadiren müdahale, kritik araçlar Makefile'da, gözlemlenebilirlik ilk shot'tan [16]. Ball: "fonksiyonel teste dayanıyorum; agent'a uçtan uca test ettirip kanıt istiyorum; kritik kısımları okurum, çoğunu okumam"; feature flag arkasında prod'a çık, kendin aç [18]. Beck: TDD guardrail, agent'lar testleri siler/sonradan uydurur, insan bunu yakalar [20]. Hashimoto/Ghostty: disclosure zorunlu, "insan tüm kodu AI olmadan açıklayabilmeli", maintainer'a validasyon yükü yıkmak saygısızlık [19][66].

**Anketler (self-report, orta güvenilirlik).** BairesDev Q3 2026 (n=705): %51 haftasının >1/4'ünü AI çıktısı review'una harcıyor, %67 geçen yıla göre daha fazla [46]. Sonar 2026 (n=1.149): %95 AI çıktısını review/test/düzeltmeye efor harcıyor; %38 AI kodunu review etmenin insan kodundan daha zor olduğunu söylüyor [47]. Faros telemetri (10k dev): yüksek adopsiyonda PR review süresi +%91, PR boyutu +%154, bug/dev +%9 — korelasyon [44]. METR RCT (n=16, 246 görev): AI ile %19 yavaşlama, AI üretimlerinin <%44'ü kabul edildi [43]. DORA 2025: AI throughput'u artırıyor ama instability de artıyor; "mirror and multiplier" [45].

**İnsanın rolü (kanıt özeti):** niyet/risk/güvenlik sahipliği, mimari ve iş mantığı yargısı, blast-radius'a göre zorunlu onay, AI reviewer çıktısını filtreleme ("sadece önemli olanları bubble-up" [48]). Hiçbir kaynak insanı tamamen devreden çıkaran bir **çoklu-LLM verdict** modeli raporlamıyor; en radikal pozisyon Monperrus'un "kod review'un sonu" position paper'ı [38], ki abstract'ta veri yok ve "agent yazar, insan zorunlu reviewer" modelini çıkmaz olarak eleştiriyor, yerine LLM-verdict döngüsü önermiyor.

### S2. "Sıfır bulguya kadar çoklu LLM review turu" bilinen pratik mi? Azalan getiri, hallucinated bulgu, nitpick enflasyonu, kalibrasyon, precision/recall

**Önerilen yerde yok; karşı uyarı var.** Anthropic best-practices: reviewer "istendiği için" bulgu üretir; "sadece doğruluğu ya da belirtilen gereksinimi etkileyen boşlukları bildir, kalanı opsiyonel say" [1]. Code Review dokümanı REVIEW.md için "Re-review convergence" ve "Nit volume cap (en fazla 5)" ve "Verification bar (behavior claim için `file:line` kanıtı)" kurallarını öneriyor [2]. Codex: "kuralları 2–3 ile başlat, gürültü yaratanları daralt/kaldır; formatting/lint'i CI'a bırak" [3]. Cloudflare: "What NOT to flag" [7].

**Hallucinated / "reasoned" bulgular (ölçüm).**
- CodeRabbit saha çalışması: 31.073 yorum, %36,4 kabul, %7,3 tartışma, **%56,3 red**; red nedenleri false positive, redundant, scope dışı; agentic review'lar fonksiyonel odaklı ama **daha yüksek oranda geçersiz** [30] (P).
- "If It's Not Buggy, Don't Fix It": LLM'ler hatasız programlarda ısrarla bug "buluyor"; iteratif fix "pseudo-bug-fixing cycle"e giriyor (aynı edit ekle-çıkar); doğru kodu bozma oranı > bozuk kodu düzeltme oranı; modelde "buggy code" için yanlış tetiklenen bir steering vector var [29] (P). Bu, bizim 7 kB docs'ta 10 tur gözlemimizin mekanizması olabilir.
- LLM-as-judge for code (Crupi vd.): en iyi judge bile sık yanılıyor; false negative'lerin çoğu "artificial hallucination" (kodda olmayan gereksinim/ifade); %37 uncaught wrong behavior false positive'den, %27 belirsiz gereksinimden [28] (P).
- Hallucination çalışması (2505.20206, Augment aktarımı): doğru kod bloklarının %24,8'ine yanlış öneri; problem açıklaması yoksa oran ikiye katlanıyor [50] (S).
- Framing etkisi (2603.18740): değişiklik "bug-free" diye sunulunca vulnerability tespiti 16–93 puan düşüyor [50] (S) — reviewer'a verilen bağlam verdict'i sürüklüyor.
- Bias in the Loop: judge verdict'i pozisyon/verbosity/authority cue'larına göre kayıyor; tekrar tutarlılığı küçük modellerde %50–65 (şans seviyesi); "yüksek tutarlılık doğruluk değil, tekrarlanabilirlik"; öneri: judgment'ı **yürütülebilir kanıta** (compile/test/static analysis) bağla [27] (P).

**Precision/recall (benchmark).**
- Martian Code Review Bench (online, Ekim 2026): Greptile F1 61,9 / P 79,0 / R 50,8; CodeRabbit F1 61,8 / P 70,0 / R 55,3; cubic 65,3; **Codex 15 araçta #13**. Offline (50 zor PR): CodeRabbit precision %32,6 [39] (B, vendor aktarımı). Martian'ın kendisi "online veri head-to-head karşılaştırmayı desteklemez" diyor.
- SWE-PRBench (350 PR): 8 frontier model insan tarafından işaretlenen sorunların **%15–31'ini** buluyor (diff-only); daha fazla context verince performans **düşüyor** (attention dilution) [31] (P).
- Synthetic vs real bugs: en iyi model sentetik bug'da F1 0,847, **gerçek bug-fix PR'larında 0,066** [37] (P). Yani benchmark skorları gerçek PR'a taşınmıyor.
- CR-Bench (Augment aktarımı): Reflexion recall'u 27→33'e çıkarırken signal-to-noise 5,11→1,95'e düştü [50] (S) — ek tur recall'u biraz, gürültüyü çok artırıyor.
- Vendor kendi benchmarkları çelişkili: Greptile 50 bug'da %82 (11 FP) vs CodeRabbit %44 (2 FP) [40]; Tenki aynı araçlara F1 22–27 veriyor [39]. Bağımsız hakemli karşılaştırma **yok**.
- Endüstri kabul eşiği: Google Tricorder bir analizörü yalnızca etkin FP <%10 iken review'da tutuyor; Coverity: FP >%30 araç yok sayılır [50] (S, orijinaller CACM 2018/2010).

**Kalibrasyon / verdict.** Grader'larda self-consistency oylaması self-reported confidence'tan daha kötü kalibre (ECE 0,229 vs 0,166) ve 5× maliyetli [64] (P). LLM-judge refusal literatüründe "güvenilir" kabul edilen kurgu: vendor-çeşitli panel + 3/5 konsensüs [S, 2605.20351]. Ancak Nine Judges: 9 judge'ın etkin bağımsızlığı ~2,18, panel bağımsız oydan 8–22 puan geride, en iyi tek judge paneli yakalıyor [26] (P). Bizim "Codex Accept + Claude Accept" AND-gate'i pratikte ~1,5 bağımsız oy değerinde; ve her reviewer'ın tetiklenmemesi gerekiyor, bu da red oranını (false positive dahil) toplar.

**Azalan getiri (tur/agent sayısı).** Self-Refine: 0 kazanç [25]; 2 reviewer < 1 reviewer (gürültü içinde) [25]; MARS 5 agent, +5 puan, token maliyeti yüksek [25]; Information-theoretic verification: 2→4 agent kazançlar +14,9/+13,5/+11,2, submodülerlikle azalan getiri kanıtı [35]; Lessons Learned: 3 agent optimum, ek turlar ~8'de plato [36]; Cursor: 40 deneyde iteration count, validator, agentic design değişikliklerinin çoğu metriği geriletti, erken en etkili şey **majority voting across parallel passes** oldu (seri tur değil) [6].

**Topluluk.** HN "AI code review bubble" [48]: kritik bug'ları ~%80 yakalıyor ama "signal-to-noise poor", insan dikkati asıl darboğaz; Greptile kurucusu: "LLM'ler severity'yi düşük göstermeyi riske etmek istemiyor, bu yüzden nit'leri filtreleyemiyor"; kullanıcılar AI review'u önce çalıştırıp seçerek insan review'una taşıyor; "Claude yorumlarının %50'si faydalı, bu harika". HN [49]: "10–20 yorumdan 1'i faydalı"; "bazen tek gereken 'LGTM' — LLM'ler buna yapısal olarak yetersiz"; bir ekip AI review büyük değişiklikleri onaylayıp merge etmek için kullanıldığı için yasakladı.

### S3. Efor nereye gidiyor: spec, küçük PR, test, mutation, CI, canary, type/lint; zaman oranları

- **Spec/plan önce.** Anthropic: explore → plan → implement → commit; "diff'i tek cümlede anlatabiliyorsan plan atla"; büyük feature için interview → SPEC.md → temiz session [1]. Spec Kit: specify/plan/tasks/implement + `/speckit.analyze` cross-artifact tutarlılık kontrolü [55] (S). Pragmatic Engineer: ekipler "implementasyonu değil planı, testleri, şemayı review ediyor" (/grill-me skill) [9]. Böckeler/Fowler serisi: harness (spec + sensors) tasarla, insan "on the loop" [21]; Jain: sensor'lar insan yazımı spec/örneklerden türemeli, implementasyon agent'ı kendi testini yazıyorsa aynı yanlış okuma iki yere giriyor [22].
- **Küçük PR.** Zechner/Willison: günlük üretilen kod miktarını review kapasitesine göre sınırla, mimari/API'yi elle yaz [14]. Augment aktarımı: Haiku 4.5 F1 10–50 satırlık diff'te 0,80, 150–600 satırda 0,043 [50] (S, kaynak belirsiz). Skylos önerisi: >500 satır PR split [S]. ThoughtWorks Radar "Complacency with AI-generated code" (Hold): agent'lar daha büyük change set üretiyor, review yükü artıyor; TDD + static analysis'i iş akışına göm; automation bias, review fatigue'e dikkat [23].
- **Test / harness.** Jain deneyi: frontier model (GPT-6 Sol) harness'siz 10/10, harness 10,5× token, 7× maliyet, kazanç yok; zayıf model (Luna) 3/10 → 10/10. Öneri: frontier için **yalnızca final gate olarak tam test**, zayıf model için sürekli sensor [22]. Anthropic: "check'i ver — test/build/lint/screenshot — döngü kendi kapanır"; Stop hook ile deterministik gate; `/goal` ile evaluator [1].
- **Mutation / property testing.** MutGen: mutation feedback ile LLM test suite'i %53→%89,5 mutation score; feedback'siz 4 iterasyon sabit [52] (P). SWE-Mutation: agent testleri zayıf (DeepSeek-V3.1 %10 verification) [52] (P). Anthropic red team PBT agent'ı: 100 Python paketinde bug raporlarının %56'sı geçerli, %32'si bildirilecek düzeyde; top-21'de %86 [51] (P/B). ThoughtWorks Radar "feedback sensors for coding agents" örneğinde cargo-mutants [23].
- **Canary/dogfood/flag.** Claude Code: günde 60–100 iç release, ~1 dış [10]; Ball: feature flag arkasında prod [18]; Duckbill: lint'lerin tamamı, %85 coverage floor, e2e, post-deploy observability ile review'suz merge'e geçiş [9]; Statsig/Whatnot: employee-only prod rollout [S].
- **Zaman oranları.** Ölçülü oran yok. Self-report: BairesDev %51 → haftanın >1/4'ü review [46]; ikincil "11,4 saat review vs 9,8 saat yazma" iddiası kaynağı doğrulanamadı [S]. Faros: review süresi +%91 [44]. METR: "considerable time" review/edit, yüzde yok [43]. **Kanıt yok**: write/review/test için güvenilir oran.

### S4. Çok-agent'lı pattern'ler: planner/worker/reviewer, adversarial, LLM-as-judge, cross-vendor, self-review, ensemble; maliyet

- **Adversarial Review (reviewer + critic, zorunlu AGREE / DISAGREE_EVIDENCE / DISAGREE_CONCERN verdict'i)** [25] (P): LCB %87 vs zero-shot %77 vs 5-agent MARS %82; SWE-bench Verified 75,2 vs 71,6; **4,5× token**; inner loop 5 turla sınırlı; naive versiyonda "false consensus" (agent'lar yetersiz kanıtla anlaşıyor; critic'in haklı itirazı reviewer'ın kendinden emin cevabıyla düşüyor; ya da hedge'ler onaylanıp spekülatif bug'lar ekleniyor, judge 5 yorumun 3'ünü fabricated sayıyor). Çıkarım: **yapılandırılmış anlaşmazlık + kanıt zorunluluğu** iki serbest reviewer'dan daha iyi.
- **Paralel dar uzmanlar + verification** (Anthropic Code Review: paralel agent'lar, verification step "candidates'ı gerçek davranışa karşı kontrol edip FP'leri eler", dedup, severity rank [2]; Cloudflare 7 uzman + koordinatör [7]; Cursor 8 paralel pass + majority vote + validator model [6]). Bu, **tek turda genişlik**, seri turda derinlik değil.
- **Writer/Reviewer ayrı session** Anthropic'in önerdiği pattern; gerekçe: fresh context, kendi yazdığına yanlı değil [1]. Codex, Claude Code içinden "second opinion" plugin'i olarak kullanılabiliyor; kullanıcılar "review only, rewrite yok" diye kısıtlıyor [S].
- **Self-review** 0 kazanç [25]; self-training collapse literatürü [S, 2606.28438].
- **Ensemble/panel** korelasyonlu hatalarla sınırlı [26]; self-consistency pahalı ve kötü kalibre [64].
- **Maliyet/süre per PR (ölçülü):** Cloudflare 0,98 $ median, 1,19 $ ort., P99 4,45 $; 3m39s median, P99 10m21s; ~1,2 bulgu/review; 2,7 review/MR [7]. Anthropic Code Review 15–25 $, ~20 dk [2]. Ultrareview 5–20 $, 5–17 dk; bir kullanıcı 18 PR'a 241 $ [62] (S). Cursor Bugbot: 0,7 bug/run, ~0,5 çözülmüş bug/PR [6]. Codex `/review` için resmi süre/maliyet yok; xhigh için üçüncü taraf "2–4× token" [65] (S, düşük güven). Meta: AI patch'leri reviewer'a gösterilince review süresi +%5 ("large regression"), author-only'ye çekildi [33] (P) — reviewer'ın gördüğü her ek öğe maliyetlidir.

### S5. Review scope: diff vs repo, severity eşiği, "sadece High bloklar", Low backlog, time-box, one-shot vs iteratif

- **Diff + gerekli bağlam, repo'nun tamamı değil.** SWE-PRBench: full-context recall'u düşürüyor; 2.000 token'lık diff+summary 2.500 token'lık full context'i geçti [31]. Anthropic Code Review "diff'i ve çevre kodu" analiz ediyor [2]. Cloudflare tier'ı diff boyutu + security-sensitive dosya ile seçiyor [7].
- **Severity eşiği.** Codex yalnızca P0/P1 [3]; Claude Important / Nit / Pre-existing, nit cap, Important tanımını repo'ya göre daralt [2]; Cloudflare critical bloklar, warning onayla-yorumla, çoklu warning pattern'i önceki bot onayını geri alır; "break glass" insan override'ı (%0,6) [7]; Uber düşük güvenli yorumları atar [9]. **Hiçbir kaynak Medium'u zorunlu fix yapmıyor.**
- **Low = backlog.** Anthropic "kalanı opsiyonel" [1]; REVIEW.md "plus N similar items" özetle [2]. Bizim "fix-or-file" pratiği uyumlu; ama Low'u aynı turda **fix etmek** gürültüyü iş haline getiriyor.
- **Time-box.** Anthropic review ~20 dk ortalama ve "time limit" aşılırsa review başarısız sayılıp merge'i bloklamıyor [2]; Cloudflare P99 10 dk [7]. 2 saatlik timeout'un emsali yok.
- **One-shot vs iteratif.** Pratik: push başına bir review, fix edilen thread otomatik resolve [2][3]; iteratif döngü varsa **insan scope kararıyla** sonlanıyor [9]. Anthropic REVIEW.md: "ilk review'dan sonra sadece Important" [2] — yani ikinci tur daraltılmış scope ile, aynı scope ile değil.

### S6. Kod-dışı alanlar (docs, ops, data, research, content): QA nasıl?

- **Docs.** Vale gibi deterministik prose linter agent iş akışına gate olarak giriyor (CircleCI vale-linter skill: hataları düzelt, dosya başına PR) [61] (S); ReadMe AI linter + docs audit [S]; Anthropic REVIEW.md: docs repo için Important tanımını daralt, nit cap [2]; coding agent'ların doküman okuma/yazma davranışı üzerine ampirik çalışma var ama bulgu çekilemedi [S, 2608.20195]. **Çok turlu LLM review for docs: kanıt yok.**
- **Ops/SRE.** Google SRE Gemini incident akışı: her prod mutasyonu risk metadata + policy + reversibility + **açık insan onayı** [60] (S); sektör önerisi: investigation/action ayrımı, bounded düşük riskli aksiyonlar otomatik, kalanı approval gate [60] (S). Anthropic: alert triage ve fix taslağı Claude, deploy ayrı agent-insan reviewer; bir agent başka agent'ı fix push'a ikna etmeye çalışırken insan gate yakaladı [8].
- **Data/research.** Stripe docs asistanı: golden set + sentetik sorular, nightly eval, MRR, LLM-as-judge insan skorlarına kalibre, haftada yüzlerce özet insan review'u [58] (B). Araştırma annotation'ında ikinci model çağrısı confidence + discrepancy üretip insan yan yana karşılaştırıyor [S]. Ortak kalıp: **ölçülebilir eval + insan örneklemi**, LLM verdict'inin tekrarı değil.

### S7. Küçük iç araç/kit için release pratiği

- Claude Code (≈10–12 müh.): 60–100 iç release/gün, ~1 dış/gün, dogfooding gün 1 %20, gün 5 %50; müh. başına ~5 PR/gün; kodun ~%90'ı Claude Code ile [10]. Core için insan code owner, dış katman otomatik [11].
- Duckbill: review'suz merge için guardrail paketi (tüm lint, %85 coverage, e2e, post-deploy observability) + blast-radius label'ı [9].
- Ball: flag arkasında prod, kendin aç [18]. Whatnot/Statsig: employee-only prod rollout [S]. Flag-first checklist: default OFF, kill switch, rollback [S].
- Anthropic: yeni otomatik reviewer'lar **shadow mode** ile başlar [8].
- Ghostty (OSS): disclosure + açıklayabilme + vouch; maintainer'lar kendi AI kullanımında serbest [19].
- **Günler süren pre-release doğrulama normu: kanıt yok.** Norm: CI yeşil + bir insan reviewer (ya da düşük risk için sıfır) + dogfood/flag.

### S8. Claude Code / Codex'e özgü resmi rehberlik

- **Claude Code** [1][2] (R): `/code-review` (alias `/review`) arka planda forked subagent, fresh context; effort `low` → yalnızca en emin bulgular (az FP), `medium..max` kapsamı genişletir; `ultra` cloud multi-agent, bulgular bağımsız reproduce edilir (Pro/Max'te sınırlı ücretsiz, sonra extra usage; üçüncü taraf: 5–20 $, 5–17 dk [62]). Managed Code Review: paralel uzman agent'lar + verification + dedup; ~20 dk, 15–25 $; **bloklamaz**, check run'dan `bughunter-severity` JSON okunarak CI'da gate yapılabilir; REVIEW.md ile severity, nit cap, skip rules, verification bar, re-review convergence; Stop hook deterministik gate; `/goal` evaluator; "adversarial review step" tek subagent, "gaps, not style preferences". Resmi "loop size" önerisi yok; tek uyarı "iki düzeltmeden sonra /clear" [1].
- **Codex** [3][4][5] (R): GitHub review `@codex review`, yalnızca P0/P1; AGENTS.md'de `## Code Review Rules` (2–3 kural, lint/format CI'a); "kurallar test, branch protection ve required approval'ın yerini almaz"; `/review` CLI local diff, working tree'ye dokunmaz; `review_model` ayrı model; `model_reasoning_effort` minimal..xhigh, xhigh model-dependent; süre/maliyet resmi değil. Codex Martian online bench'te #13/15 [39] (S). Kullanıcı rehberi: "her bulguyu latest diff, beklenen davranış ve testlere karşı kontrol et; Codex'ten kanıt iste" [4].
- **GitHub Copilot** [63] (R): custom instructions, 4.000 karakter limiti Haziran 2026'da kaldırıldı; "çok uzun dosyada bazı talimatlar gözden kaçabilir".
- **Devin Review** [56] (R): confidence etiketli bug checker; "extra set of eyes, not a replacement".

---

## 3) Karşılaştırma tablosu: bizim kit vs gözlenen pratik

| Boyut | Bizim kit | Gözlenen pratik (kaynak) |
|---|---|---|
| Reviewer sayısı/biçimi | 2 seri LLM reviewer (Codex, Opus), her biri genel kapsam, verdict verir | Paralel dar uzman agent'lar + verification/dedup (Anthropic [2][8], Cloudflare [7], Cursor [6]); ya da tek adversarial reviewer+critic çifti [25]; insan son söz |
| Tur sayısı | 3–10 branch; + cluster + master + 2 final | 1 review/push, fix → thread auto-resolve [2][3]; ikinci turda yalnızca Important [2]; insan "yeter" der [9] |
| Review süresi | 40–60 dk, timeout 2 sa | Cloudflare median 3,6 dk, P99 10 dk [7]; Claude managed ~20 dk [2]; ultrareview 5–17 dk [62] |
| Maliyet/review | ölçülmemiş (high effort, uzun) | 1–25 $ [2][7]; ultrareview 5–20 $ [62] |
| Blocking eşiği | High+Medium zorunlu fix, Low fix-or-file | Yalnızca critical/P0–P1 bloklar [3][7]; Important "merge öncesi düzelt" ama bloklamaz [2]; warning yorum |
| Karar veren | LLM verdict (Accept/Reject) | İnsan, risk tier'a göre; düşük risk otomatik + örneklem denetim [8][9] |
| Scope | Her turda tam branch, aynı scope | Diff + çevre; context büyüdükçe recall düşer [31]; re-review daraltılmış [2] |
| Test stratejisi | Tam self-test suite (release'te) | Test/lint/typecheck her PR'da deterministik gate; frontier model için final gate yeter [22]; mutation/PBT seçici [51][52] |
| Release gate | Cluster + master döngüleri + 2 final review + suite; günler | CI yeşil + 1 insan (ya da 0, düşük risk) + dogfood/flag; dakikalar-saatler [9][10][18] |
| Reviewer bağımsızlığı | Sandbox throwaway kopya, fresh context | Fresh subagent context (önerilen) [1]; shadow mode ile reviewer'ı önce kalibre et [8] |
| Gürültü kontrolü | Yok (her bulgu işleniyor) | "What NOT to flag" [7], nit cap, verification bar, Important tanımı [2], low-confidence drop [9] |

---

## 4) Nicel veri tablosu

| Metrik | Değer | Kaynak | Tür/Güven |
|---|---|---|---|
| AI review yorumu red oranı | %56,3 (31.073 yorum, 239 repo) | [30] | P |
| Agentic reviewer insan-flagged sorun recall'u (diff-only) | %15–31 | [31] | P |
| Gerçek bug-fix PR'da en iyi model F1 | 0,066 (sentetikte 0,847) | [37] | P |
| Martian online F1 / P / R | Greptile 61,9/79,0/50,8; CodeRabbit 61,8/70,0/55,3; Codex #13/15 | [39] | B (vendor aktarımı) |
| Martian offline precision | CodeRabbit %32,6 | [39] | B |
| Doğru kod bloğuna yanlış öneri | %24,8 | [50]→2505.20206 | S |
| Reflexion ekstra turu | recall 27→33, SNR 5,1→1,95 | [50]→CR-Bench | S |
| Self-Refine / 2 reviewer vs 1 | 77→77 / 75 vs 77 | [25] | P |
| Adversarial Review kazancı ve maliyeti | LCB +10 puan, SWE-bench +3,6 puan, 4,5× token | [25] | P |
| 9 LLM judge etkin bağımsız oy | 2,18; en iyi tek judge ≥ panel | [26] | P |
| Self-consistency vs self-reported confidence (grader) | ECE 0,229 vs 0,166; 5× maliyet | [64] | P |
| Çok-agent tur platosu | ~8. tur; 3 agent optimum | [36] | P |
| Judge tekrar tutarlılığı (küçük modeller) | %50–91 göreve göre | [27] | P |
| Cloudflare review | median 3m39s, P99 10m21s; ort. 1,19 $, P99 4,45 $; 1,2 bulgu/review; break-glass %0,6 | [7] | B (ölçülü) |
| Anthropic managed Code Review | ~20 dk, 15–25 $/review | [2] | R |
| Cursor Bugbot | resolution %52→%70+; 0,4→0,7 bug/run; ~0,5 çözülen/PR; 40 deney, çoğu değişiklik regres | [6] | B |
| ByteDance BitsAI-CR | precision %75; outdated rate %26,7 (Go); 12k WAU | [32] | P |
| Meta MetaMateCR | ActionableToApplied %19,7; reviewer'a gösterince review +%5 süre | [33] | P |
| Google ML comment resolution | %7,5 yorum ML edit ile çözüldü | [34] | B/P |
| Anthropic SDLC | Claude ~%80 merged kod; substantive review %16→%54; incident'ların ~1/3'ü yakalanırdı | [8] | B (vendor) |
| Claude Code ekibi | Claude Tag ~%65 product PR; 60–100 iç release/gün; ~5 PR/müh/gün | [10][11] | B |
| Duckbill | median merge 26 sa (insan) vs 1 sa (insansız); PR/hafta 80→154 | [9] | B |
| Harness deneyi | frontier: 10,5× token, 7× $ , 0 kazanç; zayıf: 3/10→10/10 | [22] | B (ölçülü, n=10) |
| METR RCT | %19 yavaşlama; <%44 kabul; n=16 | [43] | P |
| Faros telemetri | review süresi +%91, PR boyutu +%154, bug/dev +%9 | [44] | B (korelasyon) |
| Greptile 50-bug bench | Greptile %82 (11 FP), CodeRabbit %44 (2 FP) | [40] | B (vendor) |
| Graphite Diamond kabul | ~%52 (insan %45–50); FP iddiaları <%3 ile %5–8 arası çelişkili | [42] | B (vendor) |
| PBT agent bug raporu geçerlilik | %56 geçerli, %32 bildirilecek | [51] | P/B |
| MutGen mutation score | %53→%89,5 | [52] | P |
| Tricorder / Coverity FP eşiği | <%10 / >%30 terk | [50] | S (CACM) |
| HN anekdot | "10–20 yorumda 1 faydalı"; "%50 faydalı, harika"; "~%80 kritik bug yakalar, SNR kötü" | [48][49] | F |

**Bizim kitten eksik veri:** review precision (kabul edilen / üretilen bulgu), tur başına yeni bulgu eğrisi, review başına token/$, release'e kadar wall-clock dağılımı. Bu dört metrik olmadan "çürütüldü" yargılarının bizim özel bağlamımızda doğrulanması mümkün değil; ilk adım bunları loglamak.

---

## 5) Radikal değişiklik adayları

**A. Risk-tiered, tek geçişli review + deterministik gate (Cloudflare/Duckbill/Anthropic modeli).**
Branch'i diff boyutu ve dokunulan dosya sınıfına göre tier'la (trivial / lite / full). Trivial (docs, test-only, tek dosya): lint + test + **tek** `/code-review low` (yalnızca en emin bulgular [2]); lite: + bir reviewer, yalnızca High bloklar; full (shell portability, hooks, state file, concurrency): iki reviewer ama paralel ve dar prompt'lu (biri portability/edge, biri logic/security), koordinatör dedup. Kanıt: [7] 1,19 $/3,6 dk; [2] low effort = az FP; [9] blast-radius tetikleyicileri; [31] diff-odaklı context.

**B. Tur sayısı sabit, scope daralan "convergence" kuralı.**
Tur 1: tam scope. Tur 2: yalnızca tur 1'in High bulgularının fix'i doğrulanır + yeni **High**; Medium/Low ikinci turda üretilmez (REVIEW.md "after first review, suppress nits, Important only" [2]). Tur 3 yok; kalan şüphe insana ya da issue'ya. Kanıt: [25] Self-Refine 0; [29] iterasyon pseudo-fix döngüsü; [36] plato; [6] iteration count artışının regresyonu.

**C. Adversarial pair yerine seri ikinci görüş.**
Codex ve Opus'u ardışık iki "Accept" kapısı yapmak yerine aynı turda **reviewer + critic**: critic her bulgu için AGREE / DISAGREE_EVIDENCE / DISAGREE_CONCERN verdict'i vermeye zorlanır, kanıt `file:line` ya da çalıştırılmış komut çıktısı olmalı; kanıtsız bulgu düşer. Kanıt: [25] F1 0,457→0,533, false consensus'un çözümü; [2] "verification bar"; [27] judgment'ı yürütülebilir kanıta bağla; [8] "agent'lar bulgularını kanıtlamak zorunda".

**D. Verification-first: reviewer'ın yerine sensor.**
Bulguların sık türü (locale, BSD mktemp, MAX_PATH, trap ordering) **deterministik test/matris** haline getirilebilir: `LC_ALL=tr_TR.UTF-8` + `C` ile test koşusu, BSD-uyumlu `mktemp` için shellcheck/ bats testi, uzun path fixture'ı, `trap` sıralaması için bats. Bir kez yazılır, her PR'da saniyeler sürer, LLM reviewer bunları tekrar bulmak yerine kalan şeye bakar. Kanıt: [22] frontier model için final-gate yeter; [1] "give Claude a check it can run"; [23] feedback sensors; [12] revert edilince kırılan test; [52] mutation feedback test kalitesini 53→89,5.

**E. İnsan "on the loop": artefact değil harness düzelt.**
Her review turunda tekrar eden bulgu sınıfı → CLAUDE.md/REVIEW.md/test matrisine kural; bulgu bir daha LLM tarafından üretilmez, worker tarafından baştan uygulanır. Kanıt: [21] on-the-loop; [1] "CLAUDE.md'yi kod gibi review et, hook'a çevir"; [7] "What NOT to flag" en büyük gürültü azaltıcı.

**F. Reviewer'ı shadow mode'da kalibre et, kabul oranını ölç, eşik altındakini kapat.**
Yeni reviewer konfigürasyonu (model/effort/prompt) önce bloklamadan yorum yazar; 20–30 PR sonra kabul oranı (<%40 → Tricorder/Coverity mantığıyla [50] ayarla ya da kapat). Codex'in bench'te #13 olması [39] ve high-effort'un resmi bir kazanç verisi olmaması [65] göz önünde, Codex'in review'daki effort'u düşürüp süreyi 10 dk'ya çekmek bir deney adayı. Kanıt: [8] shadow mode; [6] online resolution rate ile deney; [30] red oranı ölçümü.

**G. Release: cluster/master döngülerini kaldır, yerine "merge sonrası dogfood + flag + tek final review".**
Master'da iki final review yerine: tam self-test suite (zaten var) + bir `ultra`/full review + kit'i kendi üstünde 1 iş günü dogfood (worker spawn/watch gerçek kullanım). Kanıt: [10] günlük release + dogfood; [18] flag arkasında prod; [9] guardrail paketi ile insansız merge.

Beklenen etki (kanıta dayalı tahmin, ölçüm değil): tur 3–10 → 1–2; review süresi 40–120 dk → 5–20 dk; release günler → saatler. Risk: portability edge-case'lerinin bir kısmı test matrisi yazılmadan kaçar; D maddesi bu riskin bedelini bir kez öder.

---

## 6) Yöntemimizin savunulabilir yanları

1. **Fresh-context, bağımsız reviewer.** Anthropic resmi olarak "writer'dan ayrı, yalnızca diff'i ve kriterleri gören subagent" öneriyor [1]; Böckeler/Jain "aynı agent kod+test yazarsa aynı yanlış okuma iki yere girer" [22]. Sandbox throwaway kopya bunu güçlendiriyor.
2. **Cross-vendor ikinci model.** Korelasyonlu hata problemi tam çözülmese de [26], Anthropic "farklı agent'lar ortak kör noktayı paylaşmaz" diyor [8] ve Codex-in-Claude-Code plugin'i resmi olarak bu amaçla var [S]. Kazanç bir ölçüde gerçek; sorun seri AND-gate ve tur sayısı.
3. **Severity + fix-or-file.** Low'u backlog'a yazmak sektörün "nits as count/backlog" kuralıyla uyumlu [2][1].
4. **Kanıt odaklı bulgu formatı (High/Medium/Low + gerekçe).** Verification bar / "why this was flagged" ile aynı ruh [2][8].
5. **Tam self-test suite.** Deterministik gate literatürde en güçlü kaldıraç [1][22][23]; bizde zaten var.
6. **Edge-case bulguları gerçek bug olabilir.** Cross-platform shell kit'inde BSD `mktemp`, `MAX_PATH`, locale, trap sıralaması "nit" değil, taşınabilirlik hatasıdır; Anthropic Code Review bu sınıfı "Important: bug that should be fixed before merging" sayar [2]. Savunulamayan kısım bunların **her turda LLM tarafından yeniden keşfedilmesi**, test matrisine girmemesi.
7. **Çok-agent review'un faydası sıfır değil.** Information-theoretic verification 2→4 agent'ta +11–15 puan [35]; Adversarial Review +3,6–10 puan [25]. Doğru kurgulanınca (paralel, dar, kanıt zorunlu) iki agent tek agent'tan iyi.

---

## 7) Kaynaklar

Format: [n] Başlık — URL — tarih — tür (R resmi / P makale / B blog-vendor / F forum / S ikincil).

1. Claude Code — Best practices — https://code.claude.com/docs/en/best-practices — 2026 — R
2. Claude Code — Code Review (managed + `/code-review`, REVIEW.md, pricing) — https://code.claude.com/docs/en/code-review — 2026 — R
3. OpenAI Codex — Review GitHub pull requests with Codex — https://learn.chatgpt.com/docs/third-party/github (eski: developers.openai.com/codex/integrations/github) — 2026 — R
4. OpenAI Codex — Code review — https://learn.chatgpt.com/docs/code-review — 2026 — R
5. OpenAI Codex — Custom instructions with AGENTS.md — https://developers.openai.com/codex/guides/agents-md — 2026 — R
6. Cursor — Building Bugbot — https://cursor.com/blog/building-bugbot — Jan 2026 — B
7. Cloudflare — Orchestrating AI Code Review at scale — https://blog.cloudflare.com/ai-code-review/ — 2026-04-20 — B
8. Anthropic — How Anthropic secures its AI-native software development lifecycle — https://claude.com/blog/how-anthropic-secures-its-ai-native-software-development-lifecycle — 2026 — B
9. Gergely Orosz — What is happening with code reviews? — https://newsletter.pragmaticengineer.com/p/what-is-happening-with-code-reviews — 2026 — B (kısmen paywall)
10. Pragmatic Engineer — How Claude Code is built — https://newsletter.pragmaticengineer.com/p/how-claude-code-is-built — 2025/26 — B (kısmen paywall)
11. Simon Willison — Fireside chat with Cat Wu and Thariq (annotated) — https://simonwillison.net/2026/Jul/21/cat-and-thariq/ — 2026-07-21 — B
12. Simon Willison — Your job is to deliver code you have proven to work — https://simonwillison.net/2025/Dec/18/code-proven-to-work/ — 2025-12-18 — B
13. Simon Willison — Cognitive debt — https://simonwillison.net/2026/feb/15/cognitive-debt — 2026-02-15 — B
14. Simon Willison — Thoughts on "slowing the fuck down" (Mario Zechner) — https://simonwillison.net/2026/mar/25/thoughts-on-slowing-the-fuck-down — 2026-03-25 — B
15. Simon Willison — Agentic Engineering Patterns (guide) — https://simonwillison.net/guides/agentic-engineering-patterns/ — 2026 — B
16. Armin Ronacher — Agentic Coding Recommendations — https://lucumr.pocoo.org/2025/6/12/agentic-coding/ — 2025-06-12 — B
17. Armin Ronacher — The Coming Loop — https://lucumr.pocoo.org/2026/6/23/the-coming-loop/ — 2026-06-23 — B
18. Thorsten Ball — How I use Amp / Do you have to know every line? — https://ampcode.com/notes/how-i-use-amp ; https://archive.thorstenball.com/p/joy-and-curiosity-71/ — 2025 — B
19. Ghostty — AI_POLICY.md — https://github.com/ghostty-org/ghostty/blob/main/AI_POLICY.md — Jan 2026 — R (proje politikası)
20. Kent Beck — Augmented Coding: Beyond the Vibes — https://newsletter.kentbeck.com/p/augmented-coding-beyond-the-vibes — 2025 — B
21. Birgitta Böckeler — Humans and Agents in Software Engineering Loops — https://martinfowler.com/articles/exploring-gen-ai/humans-and-agents.html — 2026-03-04 — B
22. Naresh Jain (martinfowler.com) — Are Harnesses Worth the Cost? — https://martinfowler.com/articles/are-harnesses-worth-the-cost.html — 2026-10-13 — B (ölçülü deney, n=10/koşul)
23. ThoughtWorks Technology Radar — Complacency with AI-generated code (Hold) — https://www.thoughtworks.com/radar/techniques/complacency-with-ai-generated-code — Nov 2025 — B
24. Addy Osmani — Code review in the age of AI — https://addyo.substack.com/p/code-review-in-the-age-of-ai — 2026 — B (bazı sayıları kaynaksız)
25. Adversarial Review: Structured Disagreement for Grounded Agentic Code Review — https://arxiv.org/abs/2608.18167 — Aug 2026 — P (preprint)
26. Nine Judges, Two Effective Votes: Correlated Errors Undermine LLM Evaluation Panels (Apple) — https://arxiv.org/abs/2605.29800 — May 2026 — P
27. Bias in the Loop: Auditing LLM-as-a-Judge for Software Engineering — https://arxiv.org/abs/2604.16790 — Apr 2026 — P
28. On the Effectiveness of LLM-as-a-judge for Code Generation and Summarization — https://arxiv.org/abs/2507.16587 — Jul 2025 — P
29. If It's Not Buggy, Don't Fix It: On the Dynamics of Iterative Bug-fixing with LLMs — https://arxiv.org/abs/2609.10123 — Sep 2026 — P
30. CodeRabbit field study: developer acceptance of agentic code reviews (31,073 yorum) — https://arxiv.org/abs/2607.03316 — Jul 2026 — P
31. SWE-PRBench — https://arxiv.org/abs/2603.26130 — Mar 2026 — P
32. BitsAI-CR: Automated Code Review via LLM in Practice (ByteDance) — https://arxiv.org/abs/2501.15134 — Jan 2025 — P
33. AI-Assisted Fixes to Code Review Comments at Scale (Meta, FSE 2026) — https://arxiv.org/abs/2507.13499 — Jul 2025 — P
34. Google Research — Resolving code review comments with ML — https://research.google/blog/resolving-code-review-comments-with-ml/ — 2023 — B/P
35. Multi-Agent Code Verification via Information Theory — https://arxiv.org/abs/2511.16708 — Nov 2025 — P
36. Lessons Learned: A Multi-Agent Framework for Code LLMs to Learn and Improve — https://arxiv.org/abs/2505.23946 — 2025 — P
37. Bigger Isn't Always Better: Comparative Evaluation of LLMs for Automated Code Review (synthetic vs real bugs) — https://arxiv.org/abs/2606.15689 — Jun 2026 — P
38. Monperrus — The End of Code Review: Coding Agents Supersede Human Inspection — https://arxiv.org/abs/2606.13175 — Jun 2026 — P (position paper, veri yok)
39. cubic.dev — CodeRabbit vs Greptile (Martian Code Review Bench aktarımı) — https://www.cubic.dev/blog/coderabbit-vs-greptile — 2026-10 — B (vendor, rakip)
40. Greptile — Benchmarks (50 bugs, 5 tools) — https://greptile.com/benchmarks — 2025 — B (vendor)
41. CodeRabbit — State of AI vs Human Code Generation Report — https://coderabbit.ai/blog/state-of-ai-vs-human-code-generation-report — 2025-12-17 — B (vendor)
42. Graphite — Building developer trust with high-signal AI feedback; AI Engineer 2025 talk — https://graphite.dev/guides/building-developer-trust-high-signal-ai-feedback — 2025 — B (vendor)
43. METR RCT (DX özeti) — https://getdx.com/blog/metr-study-on-how-ai-affects-developer-productivity/ — Jul 2025 — P/S
44. Faros AI — AI Productivity Paradox — https://faros.ai/research — 2025 — B (telemetri, korelasyon)
45. DORA 2025 State of AI-assisted Software Development (Splunk özeti) — https://www.splunk.com/en-us/blog/learn/state-of-devops.html — Sep 2025 — S
46. BairesDev — Dev Barometer Q3 2026 — https://www.bairesdev.com/blog/dev-barometer-q3-2026-devs-answering-for-code/ — 2026 — B (anket)
47. Sonar — State of Code Developer Survey 2026 — https://www.sonarsource.com/state-of-code-developer-survey-report.pdf — 2026 — B (anket)
48. Hacker News — "There is an AI code review bubble" — https://news.ycombinator.com/item?id=46766961 — 2026 — F
49. Hacker News — "I still don't get the idea about AI code reviews" — https://news.ycombinator.com/item?id=46348957 — 2026 — F
50. Augment Code — How accurate is AI code review? (literatür derlemesi: RevMate 2411.07091, Tricorder, Coverity, CR-Bench 2603.11078, 2505.20206, 2603.18740) — https://www.augmentcode.com/guides/ai-code-review-accuracy — 2026 — S (vendor derleme; alt kaynaklar P)
51. Anthropic Frontier Red Team — Agentic property-based testing (NeurIPS 2025 DL4C) — https://red.anthropic.com/2026/property-based-testing ; https://arxiv.org/abs/2510.09907 — 2025/26 — P/B
52. MutGen / SWE-Mutation / replicability study — https://pith.science/paper/2605.22175 ; https://arxiv.org/pdf/2607.22880 — 2026 — P
53. obra/superpowers (plan → subagent-driven dev → iki aşamalı review) — https://github.com/obra/superpowers — 2025/26 — OSS kit (S aktarım)
54. Ralph loop (Geoffrey Huntley; codecentric açıklaması) — https://www.codecentric.de/en/knowledge-hub/blog/the-ralph-wiggum-loop-autonomous-code-generation-with-a-fresh-context — 2025/26 — S
55. Spec Kit / BMAD / OpenSpec karşılaştırmaları — https://pub.towardsai.net/spec-driven-development-with-ai-agents-spec-kit-vs-openspec-vs-bmad-plus-a-hands-on-openspec-7b6997074582 — 2025/26 — S
56. Devin — Devin Review docs — https://docs.devin.ai/work-with-devin/devin-review — 2026 — R
57. Aider — architect/editor mode (ikincil) — https://www.promptlayer.com/glossary/aider-architect-mode — 2025 — S
58. Stripe — Stripe's AI assistant (docs asistanı eval süreci) — https://stripe.dev/blog/stripes-ai-assistant-vs-code ; Minions aktarımı https://chatprd.ai/how-i-ai/stripes-ai-minions-ship-1300-prs-weekly-from-a-slack-emoji — 2025/26 — B/S
59. Anthropic — 2026 Agentic Coding Trends Report — https://resources.anthropic.com/hubfs/2026%20Agentic%20Coding%20Trends%20Report.pdf — 2026 — B
60. AI SRE / Google Gemini incident workflow aktarımları — https://www.softwareseni.com/what-ai-sre-agents-actually-do-in-an-incident-and-when-you-should-not-deploy-one — 2026 — S
61. CircleCI docs vale-linter skill (docs-as-code agent gate) — https://tessl.io/registry/skills/github/circleci/circleci-docs/vale-linter/review — 2026 — S
62. Ultrareview üçüncü taraf kapsamı (süre/maliyet) — https://allthings.how/claude-code-ultrareview-deep-cloud-bug-hunt-before-you-merge/ ; https://infoq.com/news/2026/04/claude-code-review — 2026 — S
63. GitHub — Copilot code review docs + changelog 2026-06-12 — https://docs.github.com/en/copilot/tutorials/customize-code-review ; https://github.blog/changelog/2026-06-12-copilot-code-review-new-configurations-and-controls/ — 2026 — R
64. When Can We Trust LLM Graders? Calibrating Confidence for Automated Assessment — https://arxiv.org/html/2603.29559v1 — Mar 2026 — P
65. Codex `model_reasoning_effort` / `/review` üçüncü taraf rehberleri — https://codex.danielvaughan.com/2026/03/30/codex-cli-review-command-code-review-workflows/ — 2026 — S (düşük güven)
66. Mitchell Hashimoto AI disclosure (Ghostty PR #8289 aktarımı) — https://newsletter.specstory.com/p/mitchell-hashimoto-on-the-ai-assisted — 2025 — S
67. Anthropic — How Anthropic teams use Claude Code — https://www.anthropic.com/news/how-anthropic-teams-use-claude-code — 2025 — B
68. Uber uReview (Pragmatic Engineer [9] içinde) — 2026 — S
69. Duckbill metrikleri (Pragmatic Engineer [9] içinde) — 2026 — B
70. Google — AI-Assisted Assessment of Coding Practices in Modern Code Review (~%40 resolution) — https://arxiv.org/abs/2405.13565 — 2024 — P

**Erişilemeyen / doğrulanamayan:** OpenAI "Introducing upgrades to Codex" (403); Pragmatic Engineer makalelerinin paywall bölümleri; Reddit thread'leri doğrudan açılamadı (yalnızca ikincil aktarım); Codex review için resmi süre/maliyet; "11,4 saat review vs 9,8 saat yazma" iddiasının birincil kaynağı.
