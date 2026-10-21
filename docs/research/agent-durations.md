# Süre cevapları: agent'ın ölçülmüş hızı mı, insan ekibinin hızı mı? Kaynaklı araştırma notu

Tarih: 2026-10-21. Soru (sahip, leeway'den): "Senden süre istersem agent'ların gerçek hızıyla ölçülsün, insan ekibinin
hızıyla değil. Bu sürekli yaşadığım bir sorun." Sahip ek olarak: araştırma kapsamlı olsun (resmi kaynaklar, ölçüm
araştırmaları, pratisyenler, tahmin literatürü) ve kitte uygulanan her kural kaynaklandırılsın.

> **Kitteki karar (v0.12.1):** `BEHAVIOUR.md`'ye bir satır (süre = ölçülmüş zamanlardan kurulan agent duvar saati, ya
> da "ölçülmedi"); `docs/WORKFLOW.md`, "Task sizing" bölümüne süre kuralı ve yedi sabit satırlı "Measured agent times"
> tablosu (değer üzerine yazılır, satır eklenmez); `docs/COMMUNICATION.md` soru seçeneklerinde "ne kadar sürer"
> aynı biçimde. Zaman damgası enjekte eden bir hook bu sürümde YOK (Bulgu 10).

Etiketler: **R** araştırma/makale/kılavuz, **P** vendor birincil doküman, **B** blog/pratisyen, **F** forum/issue, **K** kitin
kendi proje kanıtı. Güç: **güçlü** (hakemli ya da vendor dokümanı, ölçüm), **orta** (preprint, workshop, uzman blogu,
tek setli ölçüm), **zayıf** (anekdot, forum). Kaynak numaraları `[n]`, liste bölüm 4'te. "İkincil" yazan kaynağı
birincil sayfasından okuyamadım; sayılar aktaranın sözüdür.

---

## 1) Kısa özet

1. **Model süreyi insan ölçeğinde verir ve agent işi için fazla tahmin eder.** Ölçümler: ön-görev tahmini gerçeğin
   4–7 katı, çok adımlı işte 5–10 katı [5]; Claude Code ~3 kat, Codex 6–10 kat, en kötüsü kısa görevlerde [6]. Kullanıcı
   raporları aynı yönde: "birkaç hafta" denen iş ~1 saat [12a], "haftalar" denen iş ~30 dakika ve agent işi bırakıyor
   [12b]; "6–8 saat" denen faz ~10 dakika [13].
2. **Sadece "ayarla" demek yetmez; saat ya da ölçülmüş veri düzeltir.** Geçen süreyi söyleyen bir araç verilince
   agent'lar zamanlamayı neredeyse her seferinde doğru bildi [6]; prompt ile hizalama çoğu modelde az işe yarıyor [7];
   prompt kısmi, harness daha güvenilir [10]. Leeway'de ölçümden kurulan tahmin tuttu (4–6 sa tahmin, 5,5–6 sa gerçek),
   ölçüm anılmayınca lead insan çerçevesine geri kaydı [24]. **Sonuç: kural tek başına tutmaz; projenin kendi ölçülmüş
   zamanlarının durduğu bir yer gerekir.**
3. **Doğru referans sınıfı projenin kendi geçmiş işleri.** Benzer geçmiş işlerin gerçek sonuçlarından tahmin, iç
   görüşten tahmini yener [19][20]; geçmiş hatadan aralık kur, basit yerel model kullan [22].
4. **İnsan ölçekli sayılar agent süresi değildir.** METR'in zaman ufku insanın kaç dakikada bitirdiğiyle ölçülür [1];
   insanların "AI hızlandırır" öngörüsü de ölçümle ters çıktı (−%24 öngörü, +%19 gerçek) [2]. Ekip sezgisi agent
   tahmininin yerine konmaz [11].
5. **Duvar saati agent çalışması değildir.** Geçen sürenin çoğu insan geri bildirimi ve bekleme olabilir [3]; leeway'in
   27 saati gece arasını içeriyor [24]. Bekleme ayrı söylenir.
6. **Oturum başı ve sıkıştırma maliyeti gerçek ve ölçülebilir.** Taze oturum hafızasız başlar, durumu dosyadan okur
   [15]; sıkıştırma ince bağlamı kaybedebilir [16]; Claude Code `claude_code.compaction` olayına `duration_ms` yazar [17].
   Leeway'in son adımı 4 sıralı worker'ın sıkıştırmalarıyla 2 kat aştı [24].
7. **Satır sayısı bir kütüphanenin örtük işini görmez.** Eski kod gerçek kullanımda bulunmuş düzeltmeleri taşır;
   yeniden yazım onları yeniden keşfeder [23]. Leeway: ~2.000 satır planı ~5.500 satır oldu [24].

---

## 2) Bulgular ve kök neden adayları

**Bulgu 1 — İnsan önsel bilgisi (aday 1): DOĞRULANDI.** Ölçüm [5][6], anekdot [12a][12b][13]. Mekanizma: eğitim verisi
insanların yazdığı süre ve efor metinleri; modelin kendi çıkarım hızına erişimi yok [10] (uzman blogu, çıkarım), [5]
yazarları da "genel süre bilgisi var, kendi zamanlamasına dayanağı yok" diyor. LLM'ler efor tahmininde insanlara benzer
çapalama gösteriyor [8] (hakemli).

**Bulgu 2 — Ölçülmüş süre tablosu yok (aday 2): DOĞRULANDI.** Kitte grep (2026-10-21): `core/docs/WORKFLOW.md`,
"Worker cost" "Measure in passing: wall-clock from brief to merge" diyor ama ölçümün yazılacağı bir yer yok;
`docs/research/agent-kits-in-practice.md` "worker başına wall-clock" verisini eksik veri olarak listeliyor. Dışarıdan:
referans sınıfı tahmini ancak geçmiş işlerin gerçek sonuçları kayıtlıysa çalışır [20][22]; agent süreleri harness'a ve
göreve göre çok değişiyor (Claude Code medyan ~90 dk, Codex ~30 dk [6]; vendor: 1 dk–7 sa [18]), bu yüzden kitte sabit
bir sayı değil, proje başına ölçüm gerekir.

**Bulgu 3 — "Ölçülmüş zamanı an ya da 'ölçülmedi' de" kuralı yok (aday 3): DOĞRULANDI.** `BEHAVIOUR.md`, `AGENTS.md`,
`COMMUNICATION.md`'de süre kuralı yoktu; `COMMUNICATION.md` soru seçeneklerinde "how long" istiyor ama biçim vermiyordu.
Tahmin isteyen başka şablon yok (PHASES, STATE, HANDOFF "Sizing the task" yalnız kapsamla boyutluyor). Kaynak: erken ve
iyimser bir sayı sonraki tahminlere çapa olur; bilgi yetersizse tahmini ertele ya da verme [21]; yanıltıcı ve ilgisiz
bilgiden kaçın [22]. Bu yüzden ölçüm yoksa uydurma sayı değil "ölçülmedi".

**Bulgu 4 — Sıkıştırma ve okuma maliyeti hesapta yok (aday 4): DOĞRULANDI.** Kitte süre hesabında yoktu. Kaynak [15]
[16][17][24] (Özet 6).

**Bulgu 5 — Satır sayısı örtük kütüphane işini kaçırır (aday 5): DOĞRULANDI.** [23] (uzman denemesi, orta) ve [24].
"Satır sayısı tek başına eforu belirlemez": COCOMO II'de efor boyutun üssü ile 17 efor çarpanının çarpımıdır ve
aynı 100 KSLOC proje yalnız ölçek faktörleriyle 105 ile 331 kişi-ay arasında değişir; uyarlanan kod "software
understanding" maliyetiyle eşdeğer boyuta çevrilir [25]. Bu model insan ekibi kişi-ayıyla çalışır; kitte yalnız "boyut
tek başına yetmez" için alınır, süre birimi olarak değil.

**Bulgu 6 — İnsan ölçekli kıyas yerine geçmez.** [1][2][11]. METR ufkunu bir süreye çevirmek yanlış olur: ufuk insan
dakikasıdır ve başarı uzun görevlerde üstel düşer [1][4].

**Bulgu 7 — Bekleme ayrı.** [3] (METR notu, varsayımsal proje, orta) ve [24].

**Bulgu 8 — Aralık ver, tek nokta değil.** Geçmiş hatadan aralık [22]; planlama yanılgısında en kötü senaryo tahmini
bile tutmadı (tez: en iyi tahmin ortalaması 33,9 gün, iyimser senaryo 27,4, kötümser senaryo 48,6, gerçek 55,5;
kötümserle gerçek arasındaki fark anlamlı değil, en iyi tahmin süresinde bitiren %29,7) [19].

**Bulgu 9 — Tablo güncel tutulmazsa çürür.** Öğrenme sonuç ve neden bilgisine ve hızlı geri bildirime bağlı [21]. Kitin
"yaşayan belge şişmez" kuralı (sahip kuralı, dış kaynak yok): sabit satır, değer üzerine yazılır.

**Bulgu 10 — Harness seçeneği (bu sürümde alınmadı).** Her tura geçen süreyi ya da zaman damgasını enjekte eden bir hook
[6][10] en güçlü düzeltme olarak görünüyor. Alınmadı: lead'in kabuğunda `date`, git ve RESULT zaman damgaları zaten
var ve kural onları okumayı söylüyor; hook her istekte bağlam maliyeti ekler. Kural ve tablo yetmezse sıradaki adım bu
(BACKLOG adayı).

**Kaynakla çelişki kontrolü:** Kaynaklar brief'in 2. adımıyla çelişmiyor; [6][7][10] ek olarak "kural tek başına
tutmaz" diyor, bu yüzden tablo eklendi (brief "araştırma gösterirse" diyordu).

---

## 3) Kurallar ve dayandıkları kaynaklar

| Kitteki satır | Kaynak |
|---|---|
| `BEHAVIOUR.md`: süre ölçülmüş zamanlardan kurulan agent duvar saati ya da "ölçülmedi"; hafta, kişi-gün asla | [5][6][10][12][21][22][24] |
| `BEHAVIOUR.md`: "yalnız satır sayısı" asla | [25][23][24] |
| WORKFLOW "Task sizing": parçalar (adım, review ve düzeltme turu, gate, merge, oturum başı ve sıkıştırma) | [15][16][17][24] |
| Aralık ve n ile ver | [19][22] |
| Ölçüm yoksa "ölçülmedi", tahmin uydurma | [21][22] |
| Bekleme (sahip, gece, onay) ayrı söylenir | [3][24] |
| İnsan ölçekli sayı ya da METR ufku süre değildir | [1][2][11] |
| Yeniden yazım, kütüphanenin örtük işiyle boyutlanır | [23][24][25] |
| Kitin kendi checkout'unda tablo `CONTRIBUTING.md`, "Measured agent times" (şablon "not measured" kalır) | lead'in yargısı, kaynaksız (kitin kendi kuralları CONTRIBUTING'de, `claude_bridge.py` gibi) |
| Sabit yedi satırlı tablo, değer üzerine yazılır | [20][22] (referans sınıfı); satır sabitliği sahip kuralı, kaynaksız |
| Ölçüm kaynakları: git zaman damgaları, RESULT, `usage_summary.py`, `claude_code.compaction` `duration_ms` | [17]; git/RESULT lead'in yargısı |
| `COMMUNICATION.md`: seçeneğin "ne kadar sürer"i aynı biçimde | Bulgu 3 ile aynı |

---

## 4) Kaynaklar

1. **R, güçlü.** Kwa, West, Becker ve ark. (METR), "Measuring AI Ability to Complete Long Tasks", arXiv 2503.14499,
   v1 2025-03-18, v4 2026-07-10. https://arxiv.org/abs/2503.14499 — 50% zaman ufku insanların görevi bitirme süresiyle
   ölçülür; ufuk ~7 ayda ikiye katlanıyor.
2. **R, güçlü (n=16).** Becker, Rush, Barnes, Rein (METR), "Measuring the Impact of Early-2025 AI on Experienced
   Open-Source Developer Productivity", arXiv 2507.09089, 2025-07. https://arxiv.org/abs/2507.09089 — geliştiriciler
   %24 kısalma öngördü, ölçülen %19 uzama.
3. **R, orta (varsayımsal).** Kwa, Cunningham (METR), "org uplift game" notu, 2026-03-19.
   https://metr.org/notes/2026-03-19-org-uplift-game/ — "six weeks of wall-clock time, with maybe 8 hours of agent
   work"; sürenin çoğu insan verisi, deney ve geri bildirim.
4. **R, orta (tek set).** Ord, "Is there a half-life for the success rates of AI agents?", arXiv 2505.05115,
   2025-05-08. https://arxiv.org/abs/2505.05115 — insan dakikası başına sabit hata oranı; başarı uzunlukla üstel düşer.
5. **R, orta (workshop, ReAct scaffold).** Garikaparthi, "Can LLMs Perceive Time? An Empirical Investigation", arXiv
   2604.00010, ICLR 2026 ICBINB workshop. https://arxiv.org/abs/2604.00010 — tahmin 4–7 kat fazla, agentic 5–10 kat;
   saniyelik işlere insan ölçekli dakika.
6. **R, orta (preprint; sayılar ikincil).** Ofengenden, Andriushchenko, "Your Agents Are Not Time Aware", LessWrong /
   alphaXiv, 2026-08-14 (https://www.greaterwrong.com/posts/eAbuPXbjakop5rSJx/your-agents-are-not-time-aware); aktaran
   The Decoder, 2026-08-30 (https://the-decoder.com/ai-agents-have-no-sense-of-time-and-are-not-aware-of-it/) — Claude
   Code ve Codex fazla tahmin ediyor (~3 kat, 6–10 kat), en kötüsü kısa görevler; geçen süre aracıyla neredeyse her
   seferinde doğru; Claude Code medyan ~90 dk, Codex ~30 dk.
7. **R, güçlü (hakemli; komşu konu).** Cheng ve ark., "Your LLM Agents are Temporally Blind", Findings of ACL 2026.
   https://aclanthology.org/2026.findings-acl.1848/ — zaman damgasıyla bile hizalama ≤%65; prompt ile hizalama çoğu
   modelde az yardım ediyor.
8. **R, güçlü (hakemli).** Çalıklı, Alhamed, "Impact of Request Formats on Effort Estimation: Are LLMs Different than
   Humans?", FSE 2025, DOI 10.1145/3715771. https://eprints.gla.ac.uk/346083 — LLM'ler efor tahmininde insanlara benzer
   çapalama gösteriyor.
9. **R, orta (preprint).** Shetty ve ark., "Story Point Estimation Using Large Language Models", arXiv 2603.06276,
   2026-03/04. https://arxiv.org/abs/2603.06276 — sıfır örnekli LLM story point tahmini iyi sıralıyor; projeden birkaç
   örnek iyileştiriyor (projenin kendi verisiyle temellendirme).
10. **B, orta.** Monperrus, Stenqvist, "Coding agents' sense of time", 2026-09-07.
    https://www.monperrus.net/martin/coding-agents-sense-of-time — "anthropocentric time bias"; nedenler eğitim verisi
    ve saat yokluğu; prompt kısmi, harness (zaman damgası, süre kaydı) daha güvenilir.
11. **B, zayıf-orta.** agentpatterns.ai, "Agent Time Estimates Are Not Schedules", 2026.
    https://agentpatterns.ai/human/agent-time-estimates-not-schedules/ — tahmin kapsam sinyalidir; geçmiş benzer
    koşuların duvar saatini ölç ve sakla; ekip sezgisiyle değiştirme.
12. **F, zayıf (doğrudan).** (a) anthropics/claude-code #10994, 2025-11-04, https://github.com/anthropics/claude-code/issues/10994
    — "several weeks ... can solve the problem in an hour". (b) #55576, 2026-05-02,
    https://github.com/anthropics/claude-code/issues/55576 — "time estimates numbered in weeks for tasks ... 30 minutes",
    fazla tahmin işi erken bırakmaya yol açıyor.
13. **B, zayıf (anekdot).** Stark, Stark Insider, 2026-05-14.
    https://www.starkinsider.com/2026/05/claude-code-autonomous-coding-time-hack.html — 6–8 saat denen faz ~10 dakika;
    gerçek saati kabuktan okutmak.
14. **B, zayıf.** openclaw/skills `agent-estimation` (ilk görülme 2026-03-04).
    https://www.skills.sh/openclaw/skills/agent-estimation — agent'ın kendi birimiyle tahmin (tur ≈ 2–4 dk, modül 2–15
    tur), insan saatine en sonda çevir. Kitte birim olarak alınmadı: tur süresi ölçülmüş değil, projenin kendi ölçümü
    daha dar referans sınıfı [20].
15. **P, güçlü.** Anthropic (Young), "Effective harnesses for long-running agents", 2025-11-26.
    https://www.anthropic.com/engineering/effective-harnesses-for-long-running-agents — her yeni oturum hafızasız başlar,
    durumu ilerleme dosyası ve git'ten okur; bir oturumda tek özellik; sıkıştırma tek başına yetmez.
16. **P, güçlü.** Anthropic, "Effective context engineering for AI agents", 2025-09-29.
    https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents — "overly aggressive compaction can
    result in the loss of subtle but critical context"; bağlam azalan getirili sınırlı kaynak.
17. **P, güçlü.** Claude Code dokümanı, "Monitoring" (kontrol 2026-10-21). https://code.claude.com/docs/en/monitoring-usage
    — `claude_code.active_time.total` (boşta süre hariç), `claude_code.compaction` olayında `duration_ms`, `pre_tokens`,
    `post_tokens`; `interaction.duration_ms` turun duvar saati.
18. **P, orta (ikincil aktarım).** OpenAI, Codex lansmanı 2025-05 (görevler 1–30 dk) ve "Introducing upgrades to Codex"
    2025-09-15 (GPT-5-Codex 7 saati aşan koşular). https://openai.com/index/introducing-upgrades-to-codex/
19. **R, güçlü.** Buehler, Griffin, Ross, "Exploring the 'Planning Fallacy'", JPSP 1994.
    https://bear.warrington.ufl.edu/brenner/mar7588/Papers/buehler-et-al-1994.pdf — Çalışma 1, tez süresi (n=37): en iyi
    tahmin ortalaması 33,9 gün, iyimser senaryo 27,4, kötümser senaryo 48,6 (gerçekle farkı anlamlı değil, ns), gerçek
    55,5; en iyi tahmin süresinde bitiren %29,7. PDF'den okundu 2026-10-21.
20. **R, güçlü.** Flyvbjerg, "From Nobel Prize to Project Management: Getting Risks Right", Project Management Journal
    37(3), 2006. https://arxiv.org/abs/1302.3642 — referans sınıfı tahmini: benzer projelerin gerçek performansından.
21. **R, güçlü.** Jørgensen, "Practical Guidelines for Expert-Judgment-Based Software Effort Estimation", IEEE Software
    2005, DOI 10.1109/MS.2005.73. https://cms.simula.no/sites/default/files/publications/Jorgensen.2005.3.pdf —
    "an overoptimistic early effort estimate can easily act as an anchor for subsequent estimates"; bilgi azken tahmini
    ertele ya da hiç verme; öğrenme hızlı geri bildirime bağlı.
22. **R, güçlü (özetinden okundu).** Jørgensen, "What we do and don't know about software development effort
    estimation", IEEE Software 2014. https://acawiki.org/What_we_do_and_don%27t_know_about_software_development_effort_estimation
    — geçmiş hatadan aralık; yanıltıcı/ilgisiz bilgiden kaçın; basit yerel model; yetersiz bilgiyle erken tahmin verme.
23. **B, orta (uzman denemesi).** Spolsky, "Things You Should Never Do, Part I", 2000-04-06.
    https://www.joelonsoftware.com/2000/04/06/things-you-should-never-do-part-i/ — "When you throw away code and start
    from scratch, you are throwing away all that knowledge."
24. **K.** project-leeway-9a, platform geçişi, 2026-10-21 (`.myagentkit/v012/durations-request.md`): plan "4–6 hafta
    worker zamanı", ~2.000 satır; gerçek ~27 sa duvar saati (gece dahil), ~5.500 satır. Ölçülen: adım 18–60 dk, review
    düzeltmesi ~20 dk, gate ~10 dk, hafif review 4–10 dk; ölçümden kurulan tahmin tuttu (4–6 sa / 5,5–6 sa); son adım
    sıkıştırmalarla 2 kat aştı; lead sonra insan çerçevesine döndü.
25. **R, güçlü (birincil kılavuz).** USC, "COCOMO II.1997 Reference Manual", University of Southern California, 1997.
    https://www.cs.montana.edu/courses/spring2004/352/public/cocomo/referman.pdf — efor = A × Boyut^B × Π(efor
    çarpanları); 5 ölçek faktörü ve 17 çarpan; örnek: 100 KSLOC, tüm faktörler en iyi 105 PM, en kötü 331 PM; uyarlanan
    kod "Software Understanding (SU)" ve "Assessment and Assimilation (AA)" ile eşdeğer boyuta çevrilir.
