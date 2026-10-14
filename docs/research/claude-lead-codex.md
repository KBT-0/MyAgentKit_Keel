# Claude lead, yanında Codex: işi paylaşmak, çapraz review, maliyet ve başarısızlıklar. Kanıta dayalı araştırma raporu

Tarih: 2026-10-14. Soru (sahip): Claude'un yönetiminde, yanına takılan ikinci bir model (bugün OpenAI Codex CLI) iş alıp iş birliği yaparsa insanlar bunu nasıl kullanıyor, ne öneriyor, benzer kit ve projelerde nasıl işliyor? Kaynaklı ilerleyip karar alınacak.

Bu rapor `docs/research/ai-review-workflows.md` (K1) üzerine kurulur, onu tekrarlamaz. Biçim `docs/research/context-limit.md` (K2) ile aynıdır. Kitin kendi dosyalarına dosya + bölüm olarak atıf yapılır (K1…K10, bölüm 9).

> **Dürüstlük notu (okumadan önce).** Reddit hiçbir araçla açılamadı (WebFetch "unable to fetch from www.reddit.com"; arama aracı alan adını engelliyor). X gönderileri HTTP 402 verdi, yalnız arama özetleri görüldü. Sahibin istediği Reddit ve X kapsamı bu yüzden **zayıf**: yerine Hacker News (Algolia API ile yorumlar tam okundu), GitHub issue'ları, mühendislik blogları ve arXiv kullanıldı. Bu açık bölüm 8'de yeniden yazıldı.

---

## 0) Kaynak derecelendirme açıklaması

Etiketler `docs/research/context-limit.md` ile aynıdır: **R** araştırma/makale/benchmark, **P** vendor birincil doküman, **B** blog/pratisyen yazısı (açık kaynak proje README'leri de burada), **F** forum/issue/sosyal, **S** ikincil/başka. Dikkat: `docs/research/ai-review-workflows.md` aynı harfleri başka anlamda kullanıyor; bu rapor K2'deki anlamı kullanır. Ek harf: **K** yalnız kitin kendi dosyaları ve sahip kararları (dosya + bölümle atıf).

Kanıt dili: **ölçüm** (sayı üreten deney), **vendor beyanı** (üreticinin kendi sözü), **anekdot** (kişi deneyimi), **çıkarım** (bu raporun kendi yargısı). Dört sınıf bilerek ayrı tutuldu. Her kaynak satırında okuma düzeyi (tam/özet) yazılı. Bir alıntıyı özgün sayfasında doğrulayamadıysam "üçüncü taraf kopya" ya da "arama özeti" diyorum.

Terimler: **çapraz review** (bir modelin yazdığını başka model ailesinin okuması), **rapor-only reviewer** (bulgu yazar, kodu değiştirmez), **lead** (planlayan ve doğrulayan Claude oturumu), **Stop review gate** (codex-plugin-cc'nin Claude her durduğunda Codex'e review yaptıran isteğe bağlı hook'u).

---

## 1) Özet

1. **"Claude planlar ve review eder, Codex uygular" en sık anlatılan düzen ama tek düzen değil.** Aynı sayıda kaynak tersini yapıyor: Codex planlıyor ve yazıyor, Claude denetliyor (Chase AI [25]), ya da Codex planlayıp görev dosyaları yazıyor, Claude uyguluyor [35]. Sürekli tekrarlanan tek şey: ikisi birbirinin işini review ediyor [25][26][36][49]. Görev bazında kural yok; Nimbalyst "sabit kural koyma, aynı görevi ikisiyle koş, farklarını karşılaştır" diyor [33]. (anekdot)
2. **Çapraz review'un tek kontrollü ölçümü asimetrik çıktı.** 116 LiveCodeBench görevi, Opus 4.7 ve GPT-5.5, tek review geçişi: Codex'in yazdığını Claude review edince geçme oranı %71,6 → %89,7 (+18,1 puan); Claude'un yazdığını Codex review edince %91,4 → %82,8 (−8,6 puan); Claude'un kendini review etmesi 0 kazanç [1]. Yazarlar yazar farkını karıştırıcı sayıyor, sonuç "betimleyici"; review eden model kodu **yeniden yazıyor** (kitte reviewer yalnız rapor yazar). Ölçüm, küçük n. İkinci bir bağımsız ölçüm aynı yönde: Codex'in başarısız olduğu 105 SWE-bench Pro vakasında Claude reviewer 15, Codex reviewer 8 vaka çözdü [2] (önyargılı küme, fark yedi vaka).
3. **Döngüyü sınırlamak herkesin ortak sonucu:** 3 tur varsayılanı en yaygın [28][30][40][50]; tek review + tek fix ve bitti diyenler var [29]; aynı anlaşmazlık 3 tur sürerse insana göster [26]. Sınırsız döngü kuranlar sorunla karşılaştı: Codex review → Claude fix hattında must-fix sayısı 3, 8, 7, 7, 6, 5, 6 gitti ve döngü daha önce silinen kapsam-dışı dosyaları geri ekledi [47]. OpenAI'nin kendi plugin'inin README'si gate için "uzun Claude/Codex döngüsü yaratabilir, kullanım limitini hızlı tüketebilir" diyor [7].
4. **Bağlama yolu MCP'den CLI/plugin'e kaydı.** `codex mcp-server` komutu OpenAI deposundan 2026-09-05'te silindi [17]; oh-my-claudecode v4.4.0 Codex/Gemini MCP sunucularını kaldırıp tmux'ta CLI işçilerine geçti [42]. Kalan yollar: `codex exec` [10], resmî `codex-plugin-cc` (34,2k yıldız) [7], app-server köprüleri [41]. Kitin `codex exec` yolu bu eğilimle uyumlu.
5. **Başarısızlıkların çoğu iş bölümünden değil, aynı dosyaya yazmaktan ve durdurulamayan döngüden çıkıyor:** iki ajanın aynı çalışma ağacında birbirini ezmesi [32], iki talimat dosyasının bir haftada ayrışması [32], reviewer'ın yazma yetkisiyle düzeltmeye girişmesi [33], kota bitince yarım kalan iş [31][45], review modelinin habersiz değişmesi [45]. Hepsinin çaresi biliniyor: ajan başına worktree, tek kanonik talimat dosyası, rapor-only reviewer, tur sınırı, handoff dosyası.
6. **Maliyet:** çapraz review ölçülen görevde yazar başına 1,7–2,3× maliyet [1]. Codex tarafında plan kotası modele göre 100 kat oynuyor (Plus'ta 5 saatte Astra 5–45, Luna 350–3.000 mesaj) [9]. Claude ve Codex limitlerini kâğıtta karşılaştırmak mümkün değil: biri çarpan, biri mesaj tahmini veriyor [22][56].
7. **"Kritik iş en güçlü Claude'da kalsın" kuralını kural olarak koyan kaynak bulamadım.** Kaynaklar fazla (plan modu/uygulama: `opusplan` [18]), zorluk (Opus zor/belirsiz iş, Sonnet rutin [20]) ve rol (Cursor: her rol için en uygun model [24]) ile yönlendiriyor. Anthropic'in kendi etiketiyle en zor iş **Fable**'a gidiyor, Opus'a değil [18][20]. Güçlü yazarı zayıf reviewer'ın review etmesi zarar veriyor [1]: bu, kritik işin review'unun en az yazar kadar güçlü modelde olması için dolaylı dayanak (çıkarım).
8. **v0.11 ile çelişme riski.** Önerilen "ikisi de yazar" modu eski düzenin hatalarını (sınırsız tur, reviewer'ın kendi bulgusunu düzeltmesi, iki final review, yüksek maliyet) yeniden açabilir. Önerilerin hepsi v0.11 kararlarına karşı bölüm 6'da tek tek sınandı; çoğu onları pekiştiriyor, biri (öneri 1) eski düzenin yarısını **koşullu** açıyor ve bunu açıkça söylüyor.

---

## 2) Bulgular

Her bulgu "Kanıt gücü" taşır: **Güçlü** (birden çok bağımsız ölçüm ya da resmî doküman, güncel), **Orta**, **Zayıf**, **Yok**.

### Bulgu 1. Görev bölüşümü: yön kişiye göre değişiyor; ortak payda "belirsiz iş Claude, belirli ve uzun iş Codex" ama tersi de var

Kanıt gücü: **Zayıf** (anekdot, yönler çelişiyor).

- **Claude'a planlama/mimari, Codex'e uygulama/review diyenler.** Chase AI (2026-05-10): ikisi aynı projede; ama kendi demosunda Codex plan modunda planlıyor, Claude boşlukları sıralıyor, Codex yazıyor, Claude diff'i denetleyip Codex'in kaçırdığı yaklaşık 20 hatayı buluyor [25]. Pablo Stanley (2026-01-26): "Claude Code builds, Codex reviews, yeniden yazmasın, yalnız review etsin"; gerekçe: Claude kendi kör noktalarını bulmakta zayıf [36]. HN JanSchu (2026-04-13, 3 haftada bir ürün): Opus 4.6 planlama ve ilk geçiş, "Opus büyük bağlamı daha iyi tutuyor ve dosyalar arası mimari kararları daha güvenilir veriyor"; Codex 5.3 her uygulamaya meydan okuyup güvenlik ve hata buldu; token harcaması "yaklaşık eşit" [52]. Üçüncü taraf özet sitesi (Vaughan, S): Claude mimari, karmaşık hata ayıklama, çok dosyalı refactor, frontend; Codex test üretimi, doküman, bağımlılık güncelleme, CI, altyapı betiği, arka plan toplu iş [55].
- **Tersini yapanlar.** tigranbs (DEV, Ocak): Codex "kıdemli proje yöneticisi" olarak CLAUDE.md'yi okuyup görev dosyaları yazıyor, Claude `claude -p` ile her görev dosyasını ayrı oturumda uyguluyor [35]. Engineered Intelligence (2025-10-08): Codex keşif ve yan etkili açık uçlu işler (bağımlılık zincirlerini izlemekte iyi), Claude iş tanımlandıktan sonra uygulama [27].
- **Davranış farkları (HN, Aralık 2025, yorumcular adlarıyla).** lmeyerov: Codex plandan sapıyor, üretim PR'ı için Claude, prototip ve hata ayıklama için Codex; willaaam: Codex "kendi tercih ettiği stilde yazıyor, kod tabanının bağlamına uymuyor"; cube2222: "çok savunmacı programlama, hacky uygulamalar"; sebzim4500 ve cherryteastain: Codex uzun, elsiz oturumlarda ve Plus planda çok dayanıyor; veidr: Codex review'da makul ama yanlış hata üretiyor, Claude ise "kaçırıyor", anlaşmazlıkları test yazdırarak çözüyor [48]. (anekdot)
- **Cursor'un ölçülmüş tespiti (vendor beyanı):** GPT-5.2 uzun otonom işte talimata uyum, odak ve sapmama bakımından çok daha iyi; Opus 4.5 "daha erken duruyor, uygun olunca kısayol alıyor"; GPT-5.2 planlayıcı olarak GPT-5.1-Codex'ten bile iyi; sonuç: tek model yerine rol başına en uygun model [24]. Bu tarih Opus 4.5 dönemi; Opus 5.5 için geçerliliği bilinmiyor.
- **Vendor yönlendirmesi (Anthropic):** küçük model rutin ve tam tarif edilebilen iş, Opus daha zor ve belirsiz iş, Fable en zor ve uzun iş; "Claude bağlamı bilip denediyse ve yine yanlışsa büyük model dene; adımları atladıysa effort yükselt" [20].
- **Nimbalyst (2026-08-15, bir araç satıcısı):** kural koyma; failure mode'a göre böl: fazla düzenleyen ajana dar kapsamlı iş, erken duran ajana belirsiz iş; model sürümleri değişince yönlendirmeyi yeniden dene [33].

Okuma: iki yön de yaygın. Kanıtın taşıdığı şey "ikisinin farklı hata türleri var" (çıkarım), "Codex şu iş için, Claude bu iş için" değil. Kit için tek sağlam yön: iş belirliyse ve test edilebilirse Codex'e vermek ucuz ve kabul edilebilir (bölüm 3, Bulgu 5).

### Bulgu 2. Codex modeli ve effort: vendor rehberi "varsayılanla başla"; en pahalı seviyeler seyrek

Kanıt gücü: **Orta** (P güncel; fayda ölçümü yok).

- **Bugünkü Codex modelleri (P [8], 2026-10-14):** Astra `gpt-6-astra` ("en yetenekli, karmaşık iş"), GPT-6.1 Sol `gpt-6.1-sol` ("Astra'ya yakın, daha ucuz"; karmaşık kodlama ve uzun süren iş), GPT-6 Luna `gpt-6-luna` ("odaklı, yüksek hacimli, tekrarlı iş: çıkarma, sınıflandırma, dönüştürme, yapılandırılmış özet"). GPT-5.5 ChatGPT girişli Codex'ten 2026-10-14'te emekli; GPT-5.3-Codex-Spark 2026-09-14'te emekli oldu [8]. Kitin model tablosu (K9, "Model routing") zaten Luna/Sol/Astra katmanlı.
- **Effort (P [8][14]):** "Varsayılanla başla, daha derin planlama gerekince artır." Low "hızlı, iyi sınırlı iş", Medium/High "daha karmaşık değişiklik ve hata ayıklama", Extra High "uzun, agentic, akıl yürütmesi ağır iş"; "çoğu iş Max'e ya da Ultra'ya ihtiyaç duymaz" (Ultra alt ajanlar kullanır, Luna'da yok) [8]. Yapılandırma: `model_reasoning_effort` (`low`, `medium`, `high`, `xhigh`, `max`, `ultra`; hangi seviyelerin olduğu modele ve istemciye bağlı), `review_model` (`/review` için ayrı model), `agents.default_subagent_model` / `agents.default_subagent_reasoning_effort` / `agents.max_concurrent_threads_per_session` / `agents.enabled` [11][12].
- **Claude tarafı karşılığı (P [18]):** `medium` Opus 5.5 ve Sonnet 5.5 varsayılanı, net kapsamlı günlük iş; `high` doğrulamanın önemli olduğu iş; `max` "aşırı düşünmeye yatkın, geniş kullanmadan önce test et".
- **Effort'un faydası ölçülmüş değil, karışık:** hazırlanan ön baskıda (6 açık model + Claude Sonnet 5, 24 görev) fazladan çıkarım çabası zor görevlerde bazı model-görev ikililerinde başarıyı artırdı, bazılarında yalnız maliyet ekledi [5]. Üçüncü taraf Codex rehberleri effort çarpanlarını (low 1,5×, high 3×, xhigh 5×, max 8×, Ultra 12–20×) kaynaksız tablolarla veriyor [55]; kitin kendi token raporu bu tabloları zaten kaynaksız saydı (K6, kaynak 40). Kitin ölçümü: xhigh review high'ın 2,4–4,5 katı maliyetli, aynı çözünürlük; bu yüzden review'da yasak (K8, 2026-10-13 girdisi).
- **Plugin yolunda önemli bir boşluk (F [45], issue #769, 2026-09-18):** Stop review gate `--model`/`--effort` geçirmiyor, review hangi model varsayılansa onunla koşuyor; bir makinede dört günde dört farklı modelle review yapılmış. `/codex:rescue` ise `--model`/`--effort` kabul ediyor, verilmezse Codex kendi varsayılanını seçiyor [7].

Okuma: vendor rehberi kitin tablosunu (rutin Luna/Sol, Astra yalnız lead'in seçimiyle, review'da xhigh yok) destekliyor. Hangi iş türünde hangi effort'un kabul oranını artırdığına dair bağımsız veri yok; kit kendi `usage_summary.py` ölçümüne bırakmış (K9, kural 5).

### Bulgu 3. Bağlama biçimleri: MCP ölüyor, CLI ve plugin yaşıyor

Kanıt gücü: **Güçlü** (P + depo meta verisi), kit adları için **Orta**.

- **`codex exec` (P [10]):** talimat argüman, yalnız son mesaj stdout'a; varsayılan sandbox read-only, yazmak için `--sandbox workspace-write` (`--full-auto` artık desteklenmiyor); `--json` olay akışı, `-o` son mesajı dosyaya, `--output-schema` yapılandırılmış çıktı, `codex exec resume --last|<ID>`; Git deposu zorunlu; CI için `openai/codex-action` öneriliyor [10]. Kitin worker yolu bu.
- **Resmî plugin `openai/codex-plugin-cc` (P [7], depo meta verisi gh api ile):** 2026-03-30 açıldı, **34,2k yıldız**, Apache-2.0. Komutlar: `/codex:review` (salt okunur), `/codex:adversarial-review` (yönlendirilebilir meydan okuma), `/codex:rescue` (alt ajan `codex:codex-rescue`, `--model`, `--effort`, `--resume`, `--background`), `/codex:transfer` (Claude oturumunu Codex thread'ine aktarır), `/codex:status|result|cancel`. Mekanizma: yerel `codex` ikilisini ve app-server'ı sarar, aynı kimlik doğrulama ve `~/.codex/config.toml`. İsteğe bağlı **Stop review gate**: Claude cevabını bitirirken Codex'e hedefli review yaptırır, bulgu varsa durmayı bloklar; README: "uzun bir Claude/Codex döngüsü yaratabilir ve kullanım limitlerini hızla tüketebilir; yalnız oturumu izleyeceksen aç" [7]. Son commit 2026-07-08, ama issue'lar 2026-10'a kadar açılıyor (282 açık issue, README sayfasında görüldü): bakım var, olgunluk sınırlı.
- **Plugin'in Windows sorunları (F [45]):** #530 "Windows 11'de Stop hook review gate kapalıyken bile 900 sn zaman aşımına kadar takılıyor" (bir projede 25 çalışmanın 22'si zaman aşımı); #113 Windows kurulum hatası; #280 Windows'ta `--cwd` worktree için sandbox'ta boşa komutlar. Kit native Windows'ta çalışıyor (K8, 2026-10-07); (çıkarım) plugin kitin ana konağında risk taşır. Aksi yöndeki sorun da var: openai/codex #43832 Windows'ta Codex masaüstü uygulaması `claude.exe`'yi "Access is denied" ile başlatamıyor [46].
- **Codex'i MCP sunucusu olarak çağırma:** Resmî Codex MCP sayfası yalnız Codex'in MCP **istemcisi** olduğunu anlatıyor; `mcp-server` geçmiyor [16]. Ve `codex mcp-server` komutunu silen PR #42993 **2026-09-05'te birleşti** [17]. Üçüncü taraf sarmalayıcılar (tuannvm/codex-mcp-server 643★, son push 2026-05-25; leonardsellem/codex-subagents-mcp 161★, **arşivlenmiş**) bayatlıyor [41]. oh-my-claudecode (39,9k★) v4.4.0'da Codex/Gemini MCP sunucularını kaldırıp `omc team 2:codex "..."` ile tmux'ta gerçek CLI işçileri açıyor [42].
- **Çok model orkestrasyon kit'leri:** ccg-workflow (5,9k★, Claude lead, Codex/Grok/Kimi'ye Go ikilisi köprüsüyle iş dağıtır) [43]; pal-mcp-server (11,8k★ ama son push 2025-12-15) [41]; agent-bridge (387★, Claude Code Channels ↔ Codex App Server, son push 2026-10-13) [41]; TandemKit (Claude plugin'i, `codex-plugin-cc` üzerinden kalıcı Codex alt ajanı) [26]; claudex (160★, Stop hook ile plan/review döngüsü) [40]; Neal (27★, planner/coder/reviewer rolleri farklı vendor'larda) [44]; Zenflow (Zencoder, masaüstü uygulaması) [50]. HN Show HN listesinde "Claude ve Codex döngüsü" kuran onlarca küçük araç var, puanları 0–33 [53]: yaygın ilgi, belirgin bir kazanan yok (çıkarım).
- **Claude Code tarafı:** alt ajan tanımında `model` ve `isolation: worktree` alanları var; sayfa başka CLI'lardan söz etmiyor [19].

Okuma: kit için `codex exec` + kendi sarmalayıcısı ana yol olarak savunulabilir; plugin'i yalnız sahibin elle çağırdığı bir araç olarak düşünmek mantıklı (bölüm 5, öneri 4).

### Bulgu 4. Çapraz review: ölçülmüş kanıt asimetrik; anekdotlar iki yönde

Kanıt gücü: yön **Orta** (iki bağımsız ölçüm, ikisi de küçük ve önyargılı), büyüklük **Zayıf**.

- **Xiang ve ark., ArXiv 2607.21656, 2026-07-22 (R [1]):** Claude Opus 4.7 (Claude Code) ve GPT-5.5 (Codex CLI), `high` effort, 116 LiveCodeBench zor/orta görevi, **tek yazar + tek review geçişi, review eden kod çalıştıramaz ve testleri göremez**, her ikisi de nihai programı yazıyor.

  | Koşul | Geçme | Yazar tek başınaya göre | Görev başı maliyet | Gerileme oranı |
  |---|---|---|---|---|
  | Claude tek | %91,4 | – | 0,226 $ | – |
  | Codex tek | %71,6 | – | 0,190 $ | – |
  | Claude → Codex review | %82,8 | −8,6 puan | 0,382 $ | %11,2 |
  | Codex → Claude review | %89,7 | +18,1 puan | 0,443 $ | %4,3 |
  | Claude → Claude review | %91,4 | 0 | 0,389 $ | %2,6 |
  | Codex → Codex review | %84,5 | +12,9 puan | 0,312 $ | %5,2 |

  Çiftli karşılaştırmada Codex tek vs Claude→Codex-yazar-review anlamlı (p_BH 0,001); iki çapraz yönün birbirinden farkı **anlamsız** (p 0,144). Yazarların kendi sınırları: yalnız 116 görev, tek model çifti, tek benchmark (kendi içinde Python), reviewer yürütemiyor, yalnız doğruluk ölçülüyor, tek effort, yazar tabanlarının farkı sıralama etkisini karıştırıyor ("betimleyici, nedensel değil"). Yazarların önerisi: Codex yazıyorsa Claude review etsin; Claude yazıyorsa review'u atla, "Claude tek bu benchmark'ta Pareto-optimal". **Dikkat (çıkarım):** reviewer bu çalışmada programı **yeniden yazıyor**; Codex'in Claude çıktısını bozması "düzeltmeye girişme" mekanizmasından gelebilir; kitte reviewer bulgu yazar, yazmaz, bu yüzden −8,6'nın aynen taşınacağı kesin değil. Aynı mekanizmayı K1'in 29 numaralı kaynağı ("hatasız programda bug bulma") anlatıyor.
- **neal-swebench, Haziran 2026 (R [2]):** 105 SWE-bench Pro vakası, hepsi tek atışlı Codex'in üç kez başarısız olduğu vakalar (seçim kriteri). Hepsinde Codex GPT-5.5 `medium` planlayıcı + yazar. Aynı vendor reviewer (Codex) **8** vaka çözdü; çapraz vendor reviewer (Claude Opus 4.8) **15**. Yazarın sınırı: n küçük, fark yedi vaka, küme Codex'in başarısızlıklarına göre kasten önyargılı, bir "aynı vendor" vaka yeniden koşuda düştü [2]. Yön Xiang ile aynı (Claude'un Codex'i review etmesi iyi), ama aynı deneyimi ters yönde (Codex'in Claude'u review etmesi) ölçmedi.
- **Bansal, 2026-05-21 (R [3]):** 3 PR'lık ön kontrol: Claude Opus ve Codex 5.3-xhigh bulguları yalnız %39 örtüşüyor. Tek yazar, hakem yok. Yorum: iki model farklı şeyler buluyor (çıkarım).
- **Başka bağımsız kanıt (K1):** dokuz LLM judge'ın etkin bağımsız oyu 2,18 (Apple), ikinci bağımsız reviewer tek reviewer'dan ayırt edilemedi (0,503 vs 0,495); kazanç critic'e verilen yapılandırılmış üçlü verdict'ten geldi (K1 §1.3, §S4). Self-preference çalışmaları (R [6], yalnız arama özeti) LLM judge'ların kendi çıktısını tercih ettiğini gösteriyor; kod review'una özgü ölçüm bulamadım. Aynı sonuç bu raporda da geçerli: farklı aile yardımcı olur ama tam bağımsız değildir.
- **Anekdotlar iki yönlü.** Claude'un bulduğu: Chase AI ~20 hata [25]. Codex'in bulduğu: Pablo Stanley (kenar durumlar, bağlanmamış ekran, hiçbir yere gitmeyen buton) [36]; TandemKit'te Claude "PASS" verdi, Codex yeni sürüm yokken yerelleştirme yazımının yeniden denenmediğini buldu [26]; nunc (Temmuz): Codex plan ve uygulamada çıktı yakalama, yakınsama kuralı ve komut uzunluğu hatalarını buldu, her tur yeni Codex oturumu [30]; HN mrcode007: "diğer model, Claude Code'un kaçırdığı hataları (özellikle matematik formülleri) yakalıyor, hatasız kalana kadar ileri geri" [49]; JanSchu: her iki araç da güvenle yanlış kod üretti, bu hatalar testleri geçti, çok kiracılı izin mantığı sızdırdı [52]. Yani anekdotlar "ikinci aile farklı şey buluyor"u destekler, "şu yön daha iyi"yi desteklemez (çıkarım).
- **Zayıf yön:** veidr (HN): Codex review'da "makul ama yanlış" hata üretiyor [48]; Neal'in HN yazarı "yazar Claude, reviewer Codex" günlük düzenini kullanıyor ama kendi benchmark'ında tersi (Claude reviewer) daha iyi çıktı [51][2].

### Bulgu 5. Döngü sınırları: pratikte 2–3 tur, sert durdurma, taze oturum, ret defteri

Kanıt gücü: **Orta** (birçok bağımsız uygulama aynı yöne bakıyor; hiçbiri etkisini ölçmüyor).

| Kaynak | Sınır / durdurma kuralı | Tür |
|---|---|---|
| claudex (160★) [40] | 3 plan turu, 3 review turu; "önemli bulgu yok" ya da sınır dolunca durur ve kalan endişeleri listeler; her turda farklı Codex persona'sı (kıdemli mühendis, güvenlik/veri bütünlüğü, ops); hook hata verince "izin ver" (fail open); 15 dk bayat döngü temizlenir; tur başına yaklaşık 25–30k Codex token | B (README) |
| ching-kuo/claude-codex (24★) [40] | "Tüm döngülerde en çok 3 iterasyon"; CRITICAL ve HIGH fix edilip yeniden review edilir, MEDIUM/LOW kullanıcıya bırakılır | B |
| Aseem Shrey (2026-02-20) [28] | en çok 5 tur güvenlik sınırı; tipik 2–3 turda yakınsar (örnek: 8 → 6 → onay); "VERDICT: APPROVED/REVISE" olmadan döngünün durdurma sinyali olmuyor | B |
| nunc (Temmuz) [30] | plan için 3, "done-gate" için 2 tur sınırı ve açık "NOT CONVERGED" sonucu; her tur **taze Codex oturumu** ("reviewer önceki hükmünü savunmasın"); reddedilen bulgular ret listesi olarak sonraki tura geçer; gerçekte done-gate 3 tur koştu, sınır aşıldı | B |
| TandemKit [26] | HIGH/MEDIUM açık kalmayana kadar; aynı anlaşmazlık 3 tur sürerse iki görüşü kullanıcıya göster; tipik 2–4 tur; bulgular "agreed / partially / disputed" + severity | B |
| Banani (2026-07-04) [29] | tek review geçişi + tek fix geçişi + merge ("sonsuz review-fix-review döngüsü istemiyorum"); review yalnız yorum, asla onaylamaz; Claude atladığı her bulguyu nedeniyle yazar | B |
| Zenflow (HN, 2025-12-16) [50] | Implement → Review → Fix en çok üç iterasyon ("ıraksamayı önlemek için") | F |
| illlefr4u/review-loop (0★) [40] | varsayılan 10 iterasyon; "temiz" kararı anahtar kelime sezgisi | B (zayıf) |
| superpowers (K3 §2.4) | 5 tur; 4–5. turda güçlü modelde taze uygulayıcı; minör bulgu döngüye girmez | K |

Başarısızlıklar (yukarıdaki sınırların neden gerekli olduğu):

- **mattwwarren/claude-workspace #2485 (F [47], 2026-09-29):** Codex review → fix döngüsünün kapsam çiti yoktu; bir test-harness bileti ilgisiz bir üretim sunucusu yeniden yazımını aldı, 3. tur sildi 4. tur geri ekledi; must-fix sayısı tur başına 3, 8, 7, 7, 6, 5, 6; dört ayrı örnekte "fix_loop_diverging", fark 950 → 1.450 satıra büyüdü. Çare: her fix commit'inde plana karşı dosya yolu kontrolü (PR #2493), kapsam dışı dosya eklenirse park et; "bu kapsam dışı" diyen bulgu düzeltme değil geri al ya da reddet.
- **codex-plugin-cc (F [45]):** #790 (2026-09-28) gate aynı bulguyu tekrar tekrar blokluyor: iki günde 226 durmada 202 izin, 23 blok, 1 hata; bir oturumda aynı kontrolde 6 ardışık blok, kullanıcı "dur ve karar ver" demiş ama gate bu kararı göremiyor. #548 (2026-07-24) `stop_hook_active` korumasının eksikliği: gate Claude Code'un blok sınırına (9 ardışık) kadar döner. #298 (2026-05-05) yerel `/codex:review` çalıştırma başına en çok ~2–3 bulgu veriyor, 13 dosyalık 1.000 satırlık refactor'da ~20 gerçek sorun için 8 sıralı review → fix turu gerekmiş. #760 (2026-09-14) `/codex:adversarial-review` → Claude fix döngüsü altıncı turda Fable'ın siber sınıflandırıcısını tetiklemiş olabilir (kullanıcının şüphesi, doğrulanmadı). openai/codex #37964 (2026-08-11): iki bot da review için etiketlenince GitHub'da yorum döngüsü [46].
- **Primeline (arama özeti, S [57], sayfa açılamadı):** bir geliştiricinin 7 turlu bir PR'ında bulgu sayıları 19, 7, 7, 9; dört tur ve üstü süren beş PR'ın hiçbirinde son tur temiz çıkmamış; yazarın savı "tur sınırı soruyu çözmez, tur başlamadan yazılmış durdurma kuralı çözer". Doğrulanmadı.

Okuma: bağımsız uygulayıcıların çoğu kitin v0.11 kararına (etiket başına iki tur, tur 2 yalnız Critical/High) yakın bir yere varmış. Kitin farkı: sınır kodda zorlanıyor (`prior_rounds()` BridgeError, K7 madde C). (çıkarım) Dışarıda neredeyse hiç kimse sınırı kodla zorlamıyor, README ve istemle yetiniyor.

### Bulgu 6. Handoff/brief biçimleri: tek kanonik talimat dosyası, kısa üzerine yazılan handoff dosyası, dosya sahipliği, yapılandırılmış sonuç

Kanıt gücü: **Orta** (B + P).

- **Talimat dosyası:** Codex `AGENTS.md`'yi okur (global `~/.codex`, proje kökünden cwd'ye kadar bir dosya/klasör, toplam **32 KiB** `project_doc_max_bytes`; `project_doc_fallback_filenames` ile başka dosya adları) [13][12]. Claude Code `CLAUDE.md`'yi okur; `AGENTS.md` yedeği (v2.1.277+) ikincil kaynaklarda var, kitin K3 raporu da `@AGENTS.md` içe aktarmasını anıyor [32] (üçüncü taraf, sürüme bağlı doğrula). Uygulama: `CLAUDE.md` içinde `@AGENTS.md` + birkaç Claude'a özgü satır [32][33]. Rashid: elle senkron iki dosya bir haftada ayrıştı, ajanlar bayat kuralı izledi; sembolik bağ denendi ama Claude'un Edit/Write araçları sembolik bağdan yazmayı reddediyor ve Windows'ta sembolik bağ düz metin olarak çıkıyor [32] (anekdot; kit native Windows). Stafforini tersini yapıyor: iki dosyayı sürüm kontrollü eşli tutuyor, üç katmanlı zorlama (canlı bağ, düzenleme sonrası hatırlatma, commit koruması) ["tek dosya Claude'a özgü sözdizimi gerekince bozuldu"] [34]. Kitin tercihi (tek kanonik `AGENTS.md`, araca özgü dosyalar işaretçi) bu iki yaklaşımdan ilkine yakın (K10: `docs/one-canonical-instruction-file.md`).
- **Handoff dosyası:** `.agent/HANDOFF.md` (sahip, branch, dokunulan dosyalar, bitenler, açıklar, sıradaki; "dokunulan dosyalar" alanı aynı zamanda ajanlar arası dosya sınırı); handoff'u bitiren ajan **üzerine yazar**, AGENTS.md "dokunmadan önce oku" der; elle yapıştırmanın yaklaşık 11 dakikasından bir dakikanın altına [32]. Yorumcu: sadece-ekle dosyalar çürür, kısa "en son durum" başlığı üzerine yazılmalı [32]. Offrun: kota bitince hesap değiştirmeden önce ajan hedef, ilerleme, başarısız denemeler, sonraki adımlarla `HANDOFF.md` yazar [31]. Kitin `HANDOFF.md` şablonu ve `Kind:` sonuç dosyası zaten bu sınıfta (K3 §3 tablosu).
- **Görev dosyası:** tigranbs: her görev `/todo/task-NNN.md`, bölümler Goal / Context / Files to Modify / Acceptance Criteria; 200 satırı ya da 3–4 dosyayı geçerse böl; sonuçlar `/results`'a aynı adla [35]. TandemKit: `TandemKit/<mission>/Spec.md`, `Planner-Discussion/`, `Generator/Round-NN.md`, `Evaluator/Round-NN.md` [26]. OpenAI Codex rehberi: iyi istem "istenen davranışı adlandırır, ilgili koda ya da yeniden üretim adımlarına işaret eder, kısıtları korur, doğrulamayı söyler" [15].
- **Review girdisi/çıktısı:** Banani: diff'ler yeni dosya satır numaralarıyla işaretlenir, çıktı yapılandırılmış (özet + satır yorumları), diff'e bağlanamayan geçerli bulgular özette; Claude atladığı bulguyu gerekçesiyle belgelemek zorunda [29]. Codex `exec --output-schema` ve `-o` aynı işi komut satırında yapıyor [10]. Arun/Nimbalyst: reviewer yalnız bulgu bildirir; Codex için `codex review --uncommitted|--base main|--commit <SHA>`, Claude için `git add -N . && git diff HEAD | claude -p "..."`; başka worktree'deki commit SHA'sı review edilir, canlı çalışma ağacı değil [31][33].

Okuma: dışarıdaki uygulamalar kitin mevcut biçimiyle (brief + AGENTS.md + HANDOFF + dispositions + yapılandırılmış sonuç) örtüşüyor. Kitte eksik olan, dışarıda sık geçen tek şey: **dosya sahipliği alanı** (hangi yollara dokunabilir) ve bu alanın **mekanik kontrolü** (#2485'in kapsam çiti).

### Bulgu 7. Maliyet ve kota: iki plan karşılaştırılamaz; çapraz review maliyeti çarpıyor; limit gelince iş yarıda kalıyor

Kanıt gücü: **Orta** (P fiyat/limit, ölçüm tek benchmark).

- **Codex limitleri (P [9], 2026-10-14):** Plus ve standart Business'ta 5 saatlik yerel mesaj tahmini: Astra 5–45, GPT-6.1 Sol 15–160, GPT-6 Sol 15–150, Luna 350–3.000; "tahmin, sabit limit değil"; **Pro planlarında şu an 5 saatlik limit yok**; haftalık limit "uygulanabilir" ama boyut yayımlanmıyor; hızlı mod 2,5×, Ultrafast 8× kullanım; kredi satın alınabilir; 1M token başına (girdi / önbellekli / çıktı) Astra 250 / 25 / 1.250, Sol 6.1 50 / 2,5 / 250, Luna 2,5 / 0,25 / 12,5. Üçüncü taraf özet: Pro 100/200/500 katmanları, Pro 200 azaltılmış izinle yeniden açıldı (S [56]).
- **Claude limitleri (P [22]):** Pro ve Max'te 5 saatlik oturum + haftalık limit, ikisi de sayısız; Max'te Fable için ayrı haftalık limit; limitler Claude ve Claude Code arasında ortak. Üçüncü taraf: iki planı kâğıtta karşılaştırmak imkânsız, biri çarpan biri mesaj tahmini veriyor [56].
- **Pratisyen raporları (anekdot):** HN 2025-12: Claude limitleri deney yapmayı zorlaştırıyor, Codex Plus'ta uzun oturumlara dayanıyor; oldandboring Claude Max aldı [48]. JanSchu: dört paralel ajanla Max 5x'te oturum limitlerine çarptı [52]. Chase AI: OpenAI Pro'nun 5 saatlik limitleri Anthropic Max'ten cömert, GPT-5.5 Opus ile aynı token fiyatı ama daha az token kullanıyor, kendisi 100 $'lık OpenAI Pro + Anthropic Max kullanıyor [25] (vendor-bağımsız ama ölçüm yok). Composio (2025-09, Sonnet 4 vs GPT-5 medium, iki görev, n=1): Claude Code 6,23 M vs Codex 1,50 M token (Figma klonu), 235k vs 73k (zamanlayıcı) [37]; eski modeller.
- **Çapraz review maliyeti (ölçüm [1]):** yazar başına 1,6–2,3×; Claude→Claude 1,7×, Codex→Claude 2,3×. Yazarların net düzeltme başına tahmini: Codex→Claude yaklaşık 1,40 $, Codex→Codex 0,95 $ [1]. claudex: tur başına yaklaşık 25–30k Codex token [40]. Anthropic'in çok-ajan araştırma sistemi sohbetin 15× token'ını harcıyor ve "çoğu kodlama işi için uygun değil" [23].
- **Kota bitince:** codex-plugin-cc #700 (2026-08-30): beş paralel `/codex:rescue --background` denetimi kota penceresi dolunca öldü; plugin'den devam yolu yok, geçici çözüm `codex exec --sandbox read-only resume <id> "..."` [45]. Banani: kota hatasında PR'a açıklayıcı yorum, `reviewed_by_codex` etiketi yalnız tamamlanan review'da [29]. Offrun: hesap başına ayrı `CLAUDE_CONFIG_DIR`/`CODEX_HOME` ve `HANDOFF.md` [31].
- **Kitin kendi sayıları (K8, 2026-10-13):** Codex yüksek-effort review 37–58 dk (docs dalında 5 turda 16.603 sn, ortalama 55 dk); Claude review 1–9 dk; üç zaman aşımı (2×7.198 sn, 5.398 sn), 5 `content_flagged`, 6 `cli_error`: verdict'siz yaklaşık 9,7 saat. Kitin normal modundaki ders: Opus lead hiç Codex'e uygulama göndermeyip beş Opus oturumunu review turlarına harcadı (K9, "normal" modu, Lessons).

### Bulgu 8. Başarısızlık hikâyeleri ve sonradan değiştirilenler

Kanıt gücü: **Orta** (anekdot ağırlıklı; birkaçı issue ile belgeli).

| Başarısızlık | Kaynak | Sonrasında ne değişti |
|---|---|---|
| Claude bir modülü refactor ederken Codex onu içe aktaran bir testi düzenledi, bir yazma ötekini ezdi; bir saatte çakışma; iki oturum tek terminalde; ortak not dosyası çakışmanın kendisi oldu | Rashid [32] | Ajan başına `git worktree`, dosya sınırıyla iş bölümü (Codex `apps/auth`, Claude `apps/api`), kısa üzerine yazılan handoff |
| worktree'ler stash'i paylaşıyor; `.env` ve `node_modules` yeni worktree'de yok; port çakışması; aynı branch iki worktree'de açılamıyor | Arun/Offrun [31] | `wt` yardımcı fonksiyonu `.env` kopyalıyor; "stash yerine geçici commit" kuralı AGENTS.md'ye; worktree başına `PORT` |
| Canlı çalışma ağacında aynı dosyalara çalışmak (Codex'in kendi "yaygın hata" listesinde) | Codex best practices [14] | Worktree |
| Kilitleme: 20 ajan 2–3 ajan hızına düştü, kilitler kırılgan; entegratör rolü darboğaz yarattı | Cursor [24] | İyimser eşzamanlılık denetimi, hiyerarşi, entegratörün kaldırılması |
| Reviewer yazma yetkisiyle sorunu raporlamak yerine düzeltmeye girişti | Nimbalyst [33]; ölçüm [1] (reviewer programı yeniden yazıyor) | Reviewer'ı salt okunur yap (`neal`: "reviewer salt okunur, OS sandbox'ta zorlanıyor" [44]); kitte zaten rapor-only |
| İki talimat dosyası bir haftada ayrıştı | Rashid [32], Stafforini [34] | Tek kanonik dosya + içe aktarma ya da zorlanmış eşleştirme |
| Codex'in bulduğu şeyi Claude "PASS" saydı | TandemKit [26] | İki yönlü bağımsız değerlendirme, "agreed/disputed" seviyeleri |
| Her iki model güvenle yanlış kod yazdı, testler geçti; savunma kodu zayıftı | JanSchu [52] | Planlama aşaması "tüm oyun"; güvenlik bulguları insan işi |
| Codex yolo modunda geçici dosya temizliğinde OneDrive dahil geniş silme | Bandit, Zvi derlemesi [38] | Codex sandbox'ı bir aydan fazladır kullanılıyor |
| Gate aynı bulguyu tekrar blokluyor; review modeli habersiz değişiyor; aynı bulguya 6 blok | codex-plugin-cc #790, #769 [45] | Henüz çözülmedi (issue açık) |
| Kapsam dışı dosyaları geri ekleyen fix döngüsü | #2485 [47] | Fix commit'inde kapsam çiti, `plan_scope_drift` parkı |
| İki bot da review için etiketlenince yorum döngüsü | openai/codex #37964 [46] | Açık |
| Plugin Stop hook Windows'ta 900 sn takılıyor | #530 [45] | Açık |
| Yanlış hesapla faturalama: `ANTHROPIC_API_KEY` fark edilmeden faturayı API'ye çevirebiliyor | Nimbalyst [33] | Ortam değişkenini kontrol et |

"Bir modelin ötekinin işini geri alması": doğrudan böyle bir olay raporu **bulamadım**; en yakını #2485 (döngü kapsam dışı dosyayı sildi, sonra geri ekledi) ve #790 (gate'in kullanıcı kararını görmemesi). Ayrıca "stil kayması": HN yorumları ve Cursor [48][24] var, ölçülmüş bir çalışma yok.

### Bulgu 9. "Kritik iş en güçlü modelde": kural olarak yazan yok; kaynaklar faz, zorluk ya da rolle yönlendiriyor

Kanıt gücü: kural için **Yok**, yönlendirme ilkeleri için **Orta**.

- **Faz:** Claude Code `opusplan`: plan modunda Opus ("karmaşık akıl yürütme ve mimari kararlar"), yürütmede Sonnet; anahtar yalnız plan modu, görevin kritikliği değil; mid-task "danışman" için `advisor` aracı öneriliyor [18]. Advisor aracı (beta): hızlı yürütücü + güçlü danışman; Anthropic'in iç ölçümü: orta effort Sonnet + Opus danışmanı, varsayılan effort Sonnet kadar zeki ve daha ucuz; mid-conversation "nudge"ın Sonnet'te etkisi yok, Opus'ta hafif olumsuz; "sonuçlar göreve bağlı, kendi yükünde değerlendir" [21] (vendor beyanı).
- **Zorluk:** "Opus daha zor ve belirsiz iş (ince hata, tanıdık olmayan alan, mimari karar); Fable en zor, uzun, çok adımlı iş; Sonnet rutin" [20]. Teşhis sorusu: "yeterince denemedi mi, yoksa bilmiyor mu?" [20].
- **Rol:** Cursor: planlayıcı, işçi, yargıç için farklı modeller [24]. Anthropic çok-ajan araştırma sistemi: Opus lead + Sonnet alt ajanlar tek Opus'tan iç araştırma değerlendirmesinde %90,2 daha iyi, ama kodlama için uygun değil [23] (vendor beyanı, başka görev). Aider mimar/editör: güçlü akıl yürüten + editör pairing +3–5 puan (133 Exercism görevi) [39].
- **Review için dolaylı kanıt:** Zayıf reviewer güçlü yazarı kötüleştiriyor (Codex → Claude'u −8,6 puan) [1]; çapraz review'un faydası "yazarı kendi tabanından düşük olanı" kurtarmada [1][2]. Bu, kritik işin review'unun en az yazar kadar güçlü modelde olması için çıkarım.
- **Kritik iş için doğrudan ölçüm:** yok. JanSchu "mimari kararlar Opus'ta" der [52], Chase AI tersini yapar [25]. Kit bağlamında: Anthropic'in kendi etiketine göre en güçlü Claude **Fable**'dır, Opus değil [18][20]; kitin kural 2'si (K9) bunu zaten "lead'in tek işlik seçimi, abonelikte varsa" olarak yazmış.

---

## 3) Kitin boşluğu

K9 ("Working modes, by name") üç mod tanımlar: `solo` (varsayılan, tek aile), `normal` (STATE notu tek yazan tarafı adlandırır; öteki taraf review eder; Codex'e yalnız "kesin, sınırlı, mekanik, ucuz" errand gider), `saver`. **İkisinin birlikte yazdığı ve birbirini çapraz review ettiği bir mod yok.** Sahibin kitten istediği, Claude lead altında Codex'in gerçek iş alması (yalnız mekanik errand değil), her iki tarafın yazdığı diff'in öteki tarafça review edilmesi.

Bunu v0.11'in tersine çevirmeden mümkün kılmak mümkün mü, bölüm 6'da sınanıyor.

---

## 4) Eski düzenin hataları ve v0.11 kararları

Sahibin eki: v0.11'den önce Codex ile zaten çalışıldı (ikisi yazdı, çapraz review); v0.11 bunu araştırmaya dayanarak radikal değiştirdi. Aşağıda kitin kendi kayıtlarının listelediği her hata, onu karşılayan v0.11 kararı ve bu raporun önerisinin o kararla ilişkisi. Atıflar dosya + bölüm (K1…K10, bölüm 9).

| # | Eski düzenin hatası (kayıt) | v0.11 kararı | Bu raporun önerileriyle ilişki |
|---|---|---|---|
| 1 | **Sonu gelmeyen turlar.** 39 arşivin 33'ü Reject, 6'sı Accept-MC, hiçbiri Accept; bulgular 0 Critical, 10 High, 77 Medium, 104 Low; 7 kB'lık docs dalında 10 tur, hepsi Reject; master finalleri r3–r6 Reject / Accept-MC / Reject / Accept-MC (K8 "The review policy rewritten"; K7 §0, G) | **C** etiket başına iki tur, tur 2 yalnız Critical/High; üçüncü deneme `prior_rounds()` içinde BridgeError, yalnız `REVIEW_ROUND_EXCEPTION`; **B** Reject yalnız Critical/High (K7 B, C) | Öneri 6 aynen bu kuralı korur; dış kaynaklar (3 tur) kitten **gevşek**, yeni bir sınır eklemez. Çelişki yok. |
| 2 | **Maliyet ve süre.** Codex high review 37–58 dk, docs dalında 5 turda 16.603 sn; verdict'siz 9,7 saat (3 zaman aşımı, 5 `content_flagged`, 6 `cli_error`); xhigh high'ın 2,4–4,5× maliyeti (K8 aynı girdi) | **H** zaman aşımı 2700/3600 sn, effort `REVIEW_RISK`'ten (high→high, diğer→medium), review'da xhigh/max yok; "model at capacity" yeniden denemesi backlog'da (K7 H) | Öneri 2 ve 8: Codex reviewer yalnız high katmanda, `medium`; Claude review 1–9 dk. Çelişki yok; ek olarak çapraz review'un ölçülü 1,7–2,3× maliyeti [1] yeni gerekçe. |
| 3 | **İstem "Report EVERY finding"** ve "tüm diff'i yeniden gözden geçir" → 181 bulgu, 0 Accept; "Fix sketch" yanlış-ret oranını artırıyor (K4 §1.1, §1.5, §3) | **E** yeni `REVIEW_PROMPT`: alt eşik + tamlık cümlesi, severity tanımı, "do not report", Low tavanı 5, tur ≥2 daraltması, Fix sketch kalktı (K7 E; K8) | Öneri 2 ve 6 aynı istemi iki köprüde de kullanır, istemi çatallamaz. Dışarıda Codex review'unun bulgu tavanı (#298) ve gate'in tekrar blokları (#790) bu istem gerçeğinin dışarıdaki ayna görüntüsü. |
| 4 | **İki vendor'ın seri AND kapısı ve iki final review.** Etkin ~1,5 bağımsız oy; cluster-a'da `content_flagged` ve 58 dk merge review'u (K7 G; K1 §1.3) | **G** cluster katmanı kalktı; tek final, tek model (merged diff'in daha az kısmını yazan taraf, v0.11'de Claude), high, NEW label; bir dogfood günü; "iki modelli final kapanışı" silindi (K7 G; K8 silinenler) | Öneri 1 yeni bir final eklemez. Final tek ve tek modelde kalır. Çelişki yok. |
| 5 | **Reviewer'ın kendi bulgusunu düzeltmesi** ve üç ayrı "düzeltmeyi kim yazar" modeli (K5 §C.2 madde 3); sahibin 2026-10-11 kararı: "inceleyen model bulgusunu düzeltir; iki model yazıyorsa iki bağımsız final" (K8 "Routing effort and review ownership") | v0.11: bulgular **yazarın tarafından taze bir worker'a** gider, sonraki tur düzeltmeyi review eder; "reviewer fixing its own findings" ve "two final reviews" girdileri silindi (K9 "normal"; commit 4414ae6; K8 silinenler) | Öneri 1 ve 2 reviewer'ı **rapor-only** bırakır; fix yazarın tarafında. 2026-10-11 kararını **geri getirmiyorum**. Dışarıdaki kanıt da aynı yönde [1][33][44]. |
| 6 | **İstem ve kural hacmi.** 89 kural, ~14.000 kelime, kapanış kuralının 8 kopyası, 12 çelişki, iki köprü farklı istem, `validate()` asimetrisi (K4 §1.7–1.8; K5) | **P** 44 kalır, 31 birleşir, 14 silinir; `REVIEW_GATE.md` 742 kelime, `REVIEW_RUNNING.md` 626; tek istem sabiti; Low'lu Accept'e izin (K7 P, E) | Öneriler yeni kural dosyası açmaz; öneri 1 ve 5 mevcut belgelere birer ek cümle ve bir sensör ister. "Living docs never bloat" kuralına uygun: yeni kural eklerken eski satır silinir. |
| 7 | **Yedi çalışma modu** (cross-performance, codex-first, claude-saver, codex-saver, claude-only…) ve "Codex-first'te Opus lead yalnız yönetir" (K5; K8 10-11; CHANGELOG satır 399) | **K** üç mod: solo, normal, saver; "mode asla review'u kaldırmaz ya da tier'ı indirmez" (K7 K) | Öneri 1 **yeni dördüncü mod önermez**, `normal` modunun STATE notuna bir biçim ekler (aşağıda). |
| 8 | **Normal modda Opus lead'in review turlarına harcaması:** Codex'e uygulama göndermeyip beş Opus oturumu review'a gitti (K9 "normal" Lessons) | Ders mod tanımında kaldı; "kıtlığa göre yönlendir" kural 1–6 | Öneri 3 ve 11: hangi iş Codex'e gider ve ölçüm. Bu hatayı doğrudan hedefler. |
| 9 | **İkinci vendor'a bağımlılık ve kota.** Codex düşük kotada review'u başka tarafa vermek sahibin onayıyla (K9 saver) | **Q** kit tek model ailesiyle çalışır; ikinci vendor takılabilir, hiçbir gate ikisini birden istemez; **L** `claude@NAME` ikinci model sayılır (K7 Q, L) | Öneri 1 yalnız Codex takılıyken geçerli; `solo` varsayılan kalır. Codex yoksa mod kullanılamaz, başka hiçbir şey değişmez. |
| 10 | **Windows ve süreç hataları:** `codex exec` oturumunu aşıp sahipsiz kalıyor, "model at capacity", `stale_checkout` (review sırasında lead'in düzenlemesi), beş ağır işin birlikte başlatılması (K8 "Merging seven v0.11 branches", "Review launch capacity", 2026-10-14 girdisi) | Kapasite kuralları, paralel iş worktree'de, `REVIEW_TIMEOUT_SECONDS` sınırı (K7 H) | Öneri 4 (`codex exec` yolu, plugin'i bağımlılık yapma), öneri 7 (worktree, SHA review) bu dersleri izler. |
| 11 | **Reviewer'a görev ve risk iletilmiyordu** (K4 §1.9; K5 §A.7) | `REVIEW_TASK_FILE`/`REVIEW_RISK`/`REVIEW_FOCUS` istemde (K7 E) | Öneri 5: dosya sahipliği alanı brief'e girer, reviewer'a da iletilir. |
| 12 | **Ölçüm yoktu.** `accepted=` oranı, tur başına bulgu | **F** dispositions anahtarları, `REVIEW_SHADOW=1`, `usage_summary.py` `accepted=A/T`; oran yalnız bilgi, karar sahibin (K7 F) | Öneri 11 yeni mod için aynı ölçümü ister; "hareket ettirmeyen kural silinir" ilkesi (K8 2026-10-14). |

Özet: eski düzenin dört temel hatası (sınırsız tur, reviewer'ın düzeltmesi, iki final, maliyet) v0.11'de yedi kararla kapandı. Bu raporun hiçbir önerisi bunların yerine geçmiyor. Tek koşullu açılan nokta öneri 1'deki "iki taraf yazıyor" yapısı; aşağıda ayrıca işaretli.

---

## 5) Öneriler

Her öneri bulgu numarası ve kaynakla bağlı, bir güven sözcüğü taşır. "Kanıt yetersiz" dediğim yerde yargıyla dolduruyorum ve söylüyorum. Her önerinin v0.11 ile ilişkisi bölüm 6'da.

**Öneri 1. `normal` modunun STATE notu "iki taraf yazar, çapraz review" biçimini de alsın, dosya-ayrık sahiplik ve bütün v0.11 sınırlarıyla; yeni dördüncü mod açılmasın.**
Biçim: `**Working mode:** normal (writes: claude+codex, reviews: cross)`. Anlam: lead (Claude) görevleri dosya/modül bazında böler; her görev tek yazara gider, ayrı worktree'de; her diff'i **yazmayan taraf** taze oturumda review eder (Codex'in yazdığını Claude, Claude'un yazdığını Codex); bulgular yazan tarafın taze worker'ına gider; etiket başına iki tur; tek final, tek model, Claude. Dayanak: Bulgu 1 (pratisyenler ikisini bir arada kullanıyor), Bulgu 4 (ikinci aile farklı şey buluyor; Claude'un Codex'i review etmesi iki bağımsız ölçümde iyi) [1][2][3][25][26][36][49], Bulgu 8 (dosya ayrımı ve worktree çakışmayı çözüyor) [31][32]. **Güven: orta.** Gerekçe: yön tutarlı ama iki ölçüm de küçük, önyargılı, eski modellerle ve yazar-yeniden-yazıyor tasarımıyla; Codex→Claude yönü ölçüde olumsuz çıktı (−8,6), anlamsız fark olsa da. Bu yüzden **yalnız opt-in**, dogfood'ta ölçülür, sayılar desteklemezse silinir (K8, 2026-10-14 ilkesi). **Eski düzeni koşullu yeniden açıyor** (bölüm 6, satır 1).

**Öneri 2. Yön kuralı: Codex'in yazdığını Claude review eder (varsayılan, her tier); Claude'un yazdığını Codex yalnız orta ve yüksek tier'da, tek geçiş, rapor-only, `medium` effort review eder; Codex bulgusunu lead doğrular, doğrulanmamış bulgu fix turuna girmez.**
Dayanak: [1] (Claude→Codex-yazar iyi, Codex→Claude-yazar kötü), [2] (Claude reviewer 15 vs Codex reviewer 8), Bulgu 4 anekdotları (iki yönde de bulgu), kitin K10 kuralı "başka modelin verdict'i girdi, lead doğrular" (`docs/decorrelated-review.md`, "What does not count as review"), kitin kendi sayıları: Claude review 1–9 dk, Codex high 37–58 dk (K8). Neden Codex reviewer yine de var: Claude yazarın kör noktalarını yakalayan farklı aile değeri ([3] %39 örtüşme, anekdotlar [26][36]) ve [1]'de çapraz review'un zararı reviewer'ın programı yeniden yazmasından olabilir; kitte rapor-only. **Güven: orta-düşük** (yön için iki ölçüm; kitin konfigürasyonunda ölçüm yok). Kitin "Codex xhigh review yok" kararı (K8) ve zaman aşımı sınırı (K7 H) aynen geçerli.

**Öneri 3. Codex errand şekli ve effort tablosu: Codex'e giden iş "yazılı kabul ölçütü olan, testle doğrulanabilir, tek modüllük" iş; model/effort kitin mevcut tier tablosuyla.**
Konsolide (yargı, kaynakla): `Luna`, `medium`: mekanik iş (yeniden adlandırma, veri çekme, dönüştürme, toplu test iskeleti, doküman düzeltme) [8]; `Sol 6.1`, `medium`: sıradan, sınırlı uygulama ve hata düzeltme; `high`: çok dosyalı ya da test kaçırması muhtemel iş [8][14]; Astra yalnız lead'in tek işlik seçimi, varsayılan/`light` effort'la başla, `xhigh`/`max`/`ultra` yok (vendor: "çoğu iş Max/Ultra istemez" [8]; Anthropic'in `max` uyarısı [18]; kitin xhigh ölçümü K8). Claude'da kalan iş: kabul ölçütü yazılmamış, tasarım kararı gerektiren, talimata hassas ya da kritik blast-radius'lu iş (Bulgu 1, 9 ile tutarlı; Cursor GPT'nin uzun elsiz iş avantajı ayrıca not [24]). Kit tablosunu **değiştirme**: yeni bir "errand şekli" cümlesi eklemek yeterli; sınırları `usage_summary.py` ile ölçerek taşı (K9, kural 5). **Güven: orta** (effort eşleşmesi vendor rehberine dayanır, hangi iş türünün hangi tarafta daha çok kabul gördüğü anekdot düzeyinde ve çelişkili).

**Öneri 4. Bağlama yolu `codex exec` kalsın. `codex-plugin-cc`'yi bağımlılık yapma; özellikle Stop review gate'i açma. MCP yoluna dönme.**
Dayanak: `mcp-server` silindi [17]; plugin gate'i model/effort sabitlemiyor (#769), aynı bulguyu yineliyor (#790), `stop_hook_active` yok (#548), Windows'ta takılıyor (#530), kendi README'si döngü/kota uyarısı veriyor [7][45]. `codex exec` salt okunur varsayılan, `--output-schema`, `resume` veriyor [10]. Sahibin elle çağırdığı `/codex:review` ve `/codex:adversarial-review` bir **araç** olarak kabul edilebilir ama kitin kaydı, sandbox'ı ve rapor biçimi dışında kalır; kit review'u saymaz. **Güven: yüksek** (MCP ve gate için, birincil kaynaklar); orta (plugin'in elle kullanımı hakkında).

**Öneri 5. Brief'e "dokunulabilecek yollar" alanı ve bunun mekanik kontrolü: yazar worker'ın diff'i brief'in yol listesi dışına çıkarsa review öncesi gate durur.**
Dayanak: #2485'in çaresi tam bu (kapsam çiti, `plan_scope_drift`) [47]; Rashid'in dosya sınırı [32]; kitin "one task touches ONE module" kuralı (K10, `core/AGENTS.md` "Task discipline"); v0.11 D sınıfı "tekrarlanan sınıf sensör olur" (K7 D). Tek ek: brief şablonuna `Owns:` satırı, `check.sh`'ta diff yollarına karşı NOTE→FAIL kontrolü. Yeni kapı olduğundan "kırmızı görülmeden bitmez" kuralına tabi ve high tier review ister. **Güven: orta-yüksek.**

**Öneri 6. Review sınırı: v0.11'in iki turu aynen; ek olarak (a) her tur taze reviewer oturumu, (b) dispositions/ret listesi sonraki tura girdi, (c) fix commit'inde kapsam kontrolü (öneri 5), (d) otomatik Stop-hook döngüsü yok.**
Dayanak: Bulgu 5 tablosu (3 tur en yaygın; taze oturum ve ret defteri [30]; kapsam çiti [47]). Kitte (a) ve (b) zaten var (K7 F, K4 §4.2); öneri yeni mekanizma getirmez, yalnız dış kaynakların aynı noktaya vardığını kayda geçirir. **Güven: yüksek.**

**Öneri 7. Çakışma önleme: yazar başına worktree, kısa ömürlü; iki taraf aynı dosyaya dokunmaz; bir taraf iner, öteki rebase eder; review canlı ağaçta değil commit SHA'sında.**
Dayanak: Bulgu 8 [31][32][33], Codex rehberi [14], Cursor [24], Anthropic çok-ajan sistemi kodlama için uygun değil diyor [23] (paylaşılan bağlam). Kitin worktree politikası ve `stale_checkout` dersi (K8 2026-10-14) aynı yönde. Ek: Windows'ta uzun yol (260+) ve junction kitin mevcut sensörlerinde (K7 D-4). **Güven: yüksek.**

**Öneri 8. Maliyet kapısı: çapraz review'u risk tier'ına göre uygula (low tier'da yok), yeni modu başlatmadan önce `/status` ile Codex kotasını ölçmek; kota bitince Codex thread kimliğini kaydet.**
Dayanak: [1] 1,7–2,3× maliyet; kitin tier tablosu A (K7 A); K9 kural 5–6; #700 [45] (`codex exec resume <id>`); Pro'da 5 saatlik limit yok ama haftalık sayı yayımlanmıyor [9]. **Güven: orta** (kota/ücret sayıları tahmin).

**Öneri 9. "Kritik iş en güçlü Claude'da" kuralı rol ve riskle yazılsın, model adıyla değil: lead ve kritik/high-tier diff'in reviewer'ı, aboneliğin sunduğu en güçlü Claude katmanı (K9 kural 2); mimari, gate tasarımı, güvenlik sınırı Codex'e gitmez; Codex'in en güçlü modeli (Astra) bu kuralın yerine geçmez.**
Dayanak: kaynaklar kritikliği değil faz/zorluk/rol kullanıyor (Bulgu 9) [18][20][24]; zayıf reviewer güçlü yazarı kötüleştiriyor [1]; Anthropic'e göre en zor iş Fable'a gidiyor, Opus'a değil [20]. **Güven: orta**; tam kural için doğrudan ölçüm yok (Açık soru 4). Sahibin "Opus" sözünü "en güçlü Claude katmanı (şu an Anthropic etiketine göre Fable, abonelikte yoksa Opus)" diye okudum; bunu sahibe sormak gerekir.

**Öneri 10. Codex worker'ın kendi alt ajanlarını kapat ya da tavanla: worker config'inde `agents.enabled = false` ya da `agents.max_concurrent_threads_per_session` küçük; `ultra` effort yasak.**
Dayanak: Codex'in alt ajan ayarları var [12]; "Ultra alt ajanlar kullanır, çoğu iş istemez" [8]; kitin worktree tavanı ve worker sınırı (K9 "worker caps never exceed the worktree ceiling"); Anthropic çok-ajan maliyeti 15× [23]. Üçüncü taraf maliyet sayıları (3,6×, 6–12×) S [55], kullanma. **Güven: orta-düşük** (ayar anahtarları dokümanda görüldü, etkisi test edilmedi).

**Öneri 11. Ölçmeden yönlendirmeyi sabitleme: ilk on Codex errand'ı için görev türü, effort, kabul/ret, fix turu, kota çekimi `usage_summary.py` ile kaydedilsin; üç beş gerçek görevde aynı iş iki tarafta koşulup karşılaştırılsın (Nimbalyst yöntemi).**
Dayanak: Bulgu 1'de yönler çelişiyor [25][27][35][36][52]; [33]; kitin kural 5 ve F kararı (K9; K7 F). Ölçüm "bilgi verir, karar sahibin". **Güven: yüksek** (ölçüm gerekliliği için).

---

## 6) Önerilerin v0.11 kararlarıyla tutarlılığı

| Öneri | Dayandığı v0.11 kararı | Eski hatayı açıyor mu? |
|---|---|---|
| 1. `writes: claude+codex, reviews: cross` | Q (takılabilir ikinci vendor, hiçbir gate ikisini istemez), K (üç mod, yeni mod yok), A (risk tier), B, C (iki tur), G (tek final), F (ölçüm) | **Evet, koşullu.** Eski düzenin "ikisi de yazıyor, karşılıklı review" yarısını yeniden açıyor. Açmadığı kısımlar: sınırsız tur (C kodda zorlu), reviewer'ın düzeltmesi (bulgu yazarın tarafına gider), iki final (tek final, tek model), 7 mod (yeni mod yok), kural hacmi (bir cümle), model-dışı zorunluluk (Q: Codex yoksa mod yok). Yeni kanıt: [1][2] çapraz review yönünün önemli olduğunu ve [1] maliyetini gösteriyor; pratisyenler rapor-only reviewer ve tek fix geçişine varmış [29][31][33]. **Ama kanıt zayıf** (iki küçük ölçüm); bu yüzden opt-in, dogfood'ta ölçülür, ölçüm desteklemezse silinir. 2026-10-11 sahip kararı ("iki model yazıyorsa iki bağımsız final", K8) **geri getirilmiyor**: tek final kalıyor, çünkü iki finalin AND kapısı ~1,5 bağımsız oy değerinde (K1 §1.3) ve master finalleri r3–r6 sallandı (K7 G). |
| 2. Yön kuralı | A, B, C, H (Codex review `medium`, 2700 sn), E (aynı istem) | Hayır. Codex review'unu Claude'un yazdığına kısıtlıyor (daha dar), süresi ve effort'u H'nin içinde. [1]'in negatif sonucu kuralı gevşetmez, sıkılaştırır. |
| 3. Errand şekli ve effort | K (tier tablosu değişmez), K9 kural 1–6, F (ölçüm) | Hayır; "Opus lead hiç Codex'e iş vermedi" hatasını (satır 8) hedefler. Tabloyu değiştirmez. |
| 4. `codex exec` kalsın, plugin gate yok | "Adaptörlerin mekaniği değişmez" (K7 §1); AGENTS.md "yeni bağımlılık/MCP sahibin onayı"; H | Hayır. Plugin gate'i tam olarak eski "sonu gelmeyen tur" hatasının otomatik biçimi (#790, #548) olduğundan **reddediyor**. |
| 5. `Owns:` alanı ve yol kontrolü | D (tekrarlanan sınıf sensör olur, kırmızı görülmeden bitmez), E (görev bağlamı reviewer'a gider) | Hayır. Yeni gate kodu: high tier review ister (K7 D "Risk"). |
| 6. İki tur, taze oturum, ret listesi | C, F, E | Hayır; v0.11'i dış kaynaklarla doğruluyor. |
| 7. Worktree, SHA review | K8 2026-10-14 (parallel işin worktree'ye taşınması), K9 "Parallel work", H | Hayır. |
| 8. Maliyet kapısı | A (tier), H, M (maliyet/cache ölçümü), K9 kural 5–6 | Hayır; eski "maliyet" hatasına karşı koruma. |
| 9. Kritik iş en güçlü Claude | K9 kural 2, Q (Claude lead), AGENTS.md "Duties" (top model lead'in seçimi) | Hayır; "kıtlığa göre yönlendirme" ilkesini rol/risk diline çeviriyor. |
| 10. Codex alt ajanları kapat | K9 "worker caps never exceed the worktree ceiling" | Hayır; yalnız ek tavan. |
| 11. Ölçüm | F, K8 2026-10-14 ("hareket ettirmeyen kural silinir") | Hayır. |

Genel sonuç: on öneri v0.11 kararlarını doğruluyor ya da dar bir ek yapıyor. Tek açılan alan öneri 1'deki iki yazarlı yapı ve bu, v0.11'in kendi koşullarıyla (iki tur, rapor-only, tek final, opt-in) açılıyor, kanıt yetersizliğini söyleyerek.

---

## 7) Karar için seçenekler (sahibe)

1. **Hiçbir şey ekleme** (`solo` varsayılan, `normal` bugünkü hâli): dış kanıt iki yazarlı modu zorunlu kılmıyor; maliyet 1,7–2,3× [1]. Basit ve v0.11'in en sade okuması.
2. **Öneri 1 + 2 + 5 + 11 opt-in olarak, dogfood'ta ölçerek** (önerilen). Kanıt yönü destekliyor ama zayıf; ölçüm olmadan sabitlenmez.
3. **Yalnız Codex'i "yazan" tarafa al, Claude'u tek review yönü yap** (Öneri 2'nin yalnız ilk yarısı): [1] ve [2] bunu en çok destekliyor; Codex→Claude-yazar review'u hiç kullanılmaz. Daha ucuz ve ölçülen yönle tam örtüşen en temkinli seçenek. İki yönlü aile çeşitliliği değerinden vazgeçer.

---

## 8) Açık sorular ve kanıtın ince olduğu yerler

1. **Reddit ve X kapsamı yok.** Reddit hiçbir araçla açılamadı; X yazıları HTTP 402. X için yalnız arama özetleri var (Om Patel `codex mcp-server` kurulumu, Jason Zhou plugin kurulumu, Vox `/codex:rescue` ve `/codex:transfer`, Jim Prosser `codex exec` ile ad-hoc delegasyon; hepsi F, tarihi arama özetinde yok [54]). Sahibin sorusunun bu yarısı (r/ClaudeAI, r/codex, r/ChatGPTCoding) **cevapsız**.
2. **Kontrollü ölçüm tek.** Xiang ve ark. [1] ve neal-swebench [2] küçük, Python/SWE-bench, eski model çiftleriyle (Opus 4.7 / GPT-5.5, Opus 4.8 / GPT-5.5); GPT-5.5 Codex'ten 2026-10-14'te emekli oluyor [8]. Astra, Sol 6.1, Opus 5.5, Fable 5.1 için çapraz review ölçümü yok.
3. **Reviewer yeniden yazıyor mu, rapor mu yazıyor** farkı: [1] reviewer'ın programı yeniden yazdığı tasarımı ölçtü. Rapor-only reviewer'ın sonucunu aynen taşıyıp taşımadığı bilinmiyor.
4. **"Kritik iş en güçlü modelde" için doğrudan kanıt yok.** Kaynaklar faz, zorluk, rolle yönlendiriyor; kritikliği ölçen çalışma bulamadım.
5. **İki yazarlı modun çakışma ve entegrasyon oranı ölçülmemiş.** Worktree'nin diskte çakışmayı önlediği, ama anlamsal çakışmaları (iki değişiklik birleşir ama anlam olarak çelişir) önlemediği arama özetinde var (S), birincil kaynakta doğrulanmadı.
6. **Plan kotası.** OpenAI haftalık limit boyutu yayımlamıyor [9]; Anthropic'in iki limit türü de sayısız [22]. Karşılaştırma kâğıtta yapılamıyor, pratisyen raporları öznel ve çelişkili.
7. **Codex alt ajan ayarları** (öneri 10) dokümandan okundu, etkisi denenmedi. Config referansının son 58k karakteri okunmadı [12].
8. **Üçüncü taraf kaynakların güvenilirliği düşük:** Vaughan (kaynaksız tablolar), munderdiffl.in ve developersdigest (çok-ajan uygulama satan şirket), Nimbalyst (araç satıcısı) çıkar çatışması taşıyor; sayıları yön göstergesi.
9. **Primeline ve Charles Jones yazılarına erişilemedi** (alan adı çözümlenemedi, 404); yalnız arama özeti.
10. **Claude Code'un `AGENTS.md` yedeği (v2.1.277+)** yalnız ikincil kaynaklarda ve kitin K3 raporunda; Anthropic sayfasında bu oturumda doğrulamadım.
11. **Okuma düzeyi kısıtları:** arXiv 2607.21656 HTML sürümü tam okundu (PDF binary geldi); 2605.23108 ve 2607.20713 yalnız özet sayfası; 2608.01347 yalnız giriş ve kurulum; model-config ve sub-agents sayfaları ilk 100k karakter.

---

## 9) Kaynaklar

Biçim: [n] Başlık — URL — tarih — etiket — okuma düzeyi. Tüm okumalar 2026-10-14 (aksi belirtilmedikçe).

**R (araştırma, makale, benchmark)**
1. Xiang, Zhang, Zhang, Xu — Cross-Model LLM Code Review: Should you use Claude to review Codex or vice versa? (Agentic SE @ KDD'26) — https://arxiv.org/abs/2607.21656 (HTML: https://arxiv.org/html/2607.21656) — 2026-07-22 — R — tam (HTML)
2. navels — neal-swebench (cross-vendor reviewer deneyi, 105 vaka; blog: https://navels.dev/blog/neal/) — https://github.com/navels/neal-swebench — 2026-06-15…19 koşusu — R — tam (README), blog okunmadı
3. Bansal — Philosophical Dispositions as Behavioral Constraints for AI-Assisted Code Review — https://arxiv.org/abs/2605.23108 — 2026-05-21 — R — özet
4. Kahn ve Hastings — Security Vulnerability Patterns in AI-Generated Code: A Cross-Model Comparative Study — https://arxiv.org/abs/2607.20713 — 2026-07-22 — R — özet (bu raporda yalnız bağlam: risk modele değil görev kategorisine bağlı)
5. Weinberger ve Hozez — Prompt-Induced Waste in Coding Agents (PointFive) — https://arxiv.org/abs/2608.01347 — 2026-08 (v6 2026-09-10) — R — giriş, kurulum (pdftotext)
6. Self-Preference Bias in LLM-as-a-Judge — https://arxiv.org/abs/2410.21819 ; Quantifying and Mitigating Self-Preference Bias of LLM Judges — https://arxiv.org/abs/2604.22891 — 2024 / 2026 — R — arama özeti

**P (vendor birincil doküman)**
7. OpenAI — codex-plugin-cc (README, depo meta verisi: 34.211★, açılış 2026-03-30, son push 2026-07-08) — https://github.com/openai/codex-plugin-cc — 2026 — P — tam (gh api)
8. OpenAI Codex — Models — https://learn.chatgpt.com/docs/models (eski: developers.openai.com/codex/models) — 2026-10-14 — P — tam
9. OpenAI Codex — Pricing and usage limits — https://learn.chatgpt.com/docs/pricing — 2026-10-14 — P — tam
10. OpenAI Codex — Non-interactive mode (`codex exec`) — https://learn.chatgpt.com/docs/non-interactive-mode — 2026 — P — tam
11. OpenAI Codex — Code review (`/review`, `review_model`) — https://learn.chatgpt.com/docs/code-review — 2026 — P — tam
12. OpenAI Codex — Config reference — https://learn.chatgpt.com/docs/config-file/config-reference — 2026 — P — ilk 100k/158k karakter
13. OpenAI Codex — Custom instructions with AGENTS.md — https://learn.chatgpt.com/docs/agent-configuration/agents-md — 2026 — P — tam
14. OpenAI Codex — Best practices — https://learn.chatgpt.com/docs/learn/best-practices — 2026 — P — tam
15. OpenAI Codex — Prompting — https://learn.chatgpt.com/docs/prompting — 2026 — P — tam
16. OpenAI Codex — MCP (yalnız istemci anlatılıyor) — https://learn.chatgpt.com/docs/extend/mcp?surface=cli — 2026 — P — tam
17. openai/codex PR #42993 "Remove the deprecated `codex mcp-server` command" (birleşti 2026-09-05) — https://github.com/openai/codex/pull/42993 — 2026-09-05 — P — tam (gh api)
18. Claude Code — Model configuration (`opusplan`, effort, alt ajan modeli) — https://code.claude.com/docs/en/model-config — 2026 — P — ilk 100k/116k karakter
19. Claude Code — Subagents (`model`, `isolation: worktree`) — https://code.claude.com/docs/en/sub-agents — 2026 — P — ilk 100k/110k karakter
20. Lydia Hallie (Claude Code ekibi) — Choosing a Claude model and effort level in Claude Code — https://claude.com/blog/claude-model-and-effort-level-in-claude-code — 2026-07-07 — P — tam
21. Claude API — Advisor tool (beta) — https://platform.claude.com/docs/en/agents-and-tools/tool-use/advisor-tool — 2026 — P — ilk 100k/102k karakter
22. Claude Help — Using Claude Code with your Pro or Max plan — https://support.claude.com/en/articles/11145838-using-claude-code-with-your-pro-or-max-plan — 2026 — P — tam
23. Anthropic — How we built our multi-agent research system — https://www.anthropic.com/engineering/multi-agent-research-system — 2025-06-13 — P — tam
24. Cursor — Scaling agents (planner/worker/judge) — https://cursor.com/blog/scaling-agents — 2026 (tarih sayfada görünmedi) — P (vendor beyanı) — tam

**B (blog, pratisyen yazısı, açık kaynak proje README'si)**
25. Chase AI — How to Use Claude Code and Codex Together (Stop Choosing) — https://www.chaseai.io/blog/claude-code-and-codex-together — 2026-05-10 — B — tam
26. Cihat Gündüz — TandemKit: Pair Programming for Claude and Codex — https://fline.dev/blog/tandemkit-pair-programming-for-ai-agents/ — 2026-04-14 — B — tam
27. Engineered Intelligence — Dual Wielding Codex and Claude Code — https://engineeredintelligence.substack.com/p/dual-wielding-codex-and-claude-code — 2025-10-08 — B — tam
28. Aseem Shrey — I Made Claude and Codex Argue Until My Code Plan Was Actually Good — https://aseemshrey.com/blog/claude-codex-iterative-plan-review/ — 2026-02-20 — B — tam
29. Salman Ali Banani — A Two-Agent PR Workflow: Claude Writes, Codex Reviews — https://salmanalibanani.com/2026/07/04/a-two-agent-pr-workflow-claude-writes-codex-reviews/ — 2026-07-04 — B — tam
30. nunc — I Made Claude Code and Codex Argue About My Code Until They Agreed (DEV) — https://dev.to/nunc/i-made-claude-code-and-codex-argue-about-my-code-until-they-agreed-1pkd — Temmuz (yıl sayfada yok, 2026 çıkarım) — B — tam
31. Arun (Offrun) — Running Claude Code and Codex in parallel on one repo: git worktree gotchas and cross-review (DEV) — https://dev.to/offrun/running-claude-code-and-codex-in-parallel-on-one-repo-git-worktree-gotchas-and-cross-review-41eg — 13 Ekim (2026, araç sürümlerinden çıkarım) — B — tam
32. Rashid — Two agent CLIs, one repo (DEV) — https://dev.to/thedevtimeline/two-agent-clis-one-repo-sharing-context-between-claude-code-and-codex-without-stepping-on-each-1k13 — 10 Ekim (2026 çıkarım) — B — tam
33. Nimbalyst — Orchestrating Claude Code and Codex Together — https://nimbalyst.com/blog/orchestrating-claude-code-and-codex-together/ — 2026-08-15 — B (araç satıcısı) — tam
34. Pablo Stafforini — How I keep Claude Code and Codex in sync — https://stafforini.com/notes/how-i-keep-claude-code-and-codex-in-sync/ — 2026-05-10 (güncelleme 2026-06-08) — B — tam
35. tigranbs — How I stopped fighting AI… with Claude Code and Codex (DEV) — https://dev.to/tigranbs/how-i-stopped-fighting-ai-and-started-shipping-features-10x-faster-with-claude-code-and-codex-218 — 3 Ocak (yıl yok) — B — tam
36. Pablo Stanley — A Heated Rivalry: Claude Code + OpenAI Codex — https://pablostanley.substack.com/p/a-heated-rivalry-claude-code-openai — 2026-01-26 — B — kısmen (paywall)
37. Composio — Claude Code vs Codex dev workflow comparison (DEV) — https://dev.to/composiodev/claude-code-vs-codex-dev-workflow-comparison-4jjf — 2025-09-15 — B (vendor, n=1) — tam
38. Zvi Mowshowitz — Claude Code, Codex and Agentic Coding #8 — https://thezvi.substack.com/p/claude-code-codex-and-agentic-coding-f54 — 2026-05-08 — B — tam
39. Aider — Separating code reasoning and editing — https://aider.chat/2024/09/26/architect.html — 2024-09-26 — B (proje ölçümü) — tam
40. Açık kaynak döngü araçları: promptadvisers/claudex (160★, push 2026-04-28) https://github.com/promptadvisers/claudex ; ching-kuo/claude-codex (24★, push 2026-04-01) https://github.com/ching-kuo/claude-codex ; illlefr4u/review-loop (0★) https://github.com/illlefr4u/review-loop — 2026 — B — README tam
41. Açık kaynak köprüler: tuannvm/codex-mcp-server (643★, push 2026-05-25), BeehiveInnovations/pal-mcp-server (11.784★, push 2025-12-15), raysonmeng/agent-bridge (387★, push 2026-10-13), leonardsellem/codex-subagents-mcp (161★, arşivlenmiş), mkXultra/ai-cli-mcp (27★), crAK1644/orchestrator-mcp (10★), junyjeon/claude-codex-orchestrator (2★) — GitHub (gh api meta verisi) — 2025–2026 — B — yalnız meta veri ve arama özeti
42. Yeachan-Heo/oh-my-claudecode (39.907★, push 2026-10-14; v4.4.0 Codex/Gemini MCP kaldırıldı, `omc team N:codex`) — https://github.com/Yeachan-Heo/oh-my-claudecode — 2026 — B — README ilgili bölümler
43. fengshao1227/ccg-workflow (5.938★, push 2026-10-12) — https://github.com/fengshao1227/ccg-workflow — 2026 — B — README başı
44. navels/neal (27★, push 2026-10-13; planner/coder/reviewer farklı vendor, reviewer salt okunur) — https://github.com/navels/neal — 2026 — B — README ilgili bölümler

**F (forum, issue, sosyal)**
45. openai/codex-plugin-cc issue'ları: #790, #769, #764, #548, #530, #113, #280, #298, #760, #700 — https://github.com/openai/codex-plugin-cc/issues — 2026-04…2026-10 — F — gh api, ilgili issue gövdeleri tam
46. openai/codex #37964 (Claude Code ve Codex GitHub yorum döngüsü, 2026-08-11), #43832 (Windows'ta Codex'ten Claude Code başlatılamıyor, 2026-09-08) — https://github.com/openai/codex/issues/37964 ; https://github.com/openai/codex/issues/43832 — F — tam
47. mattwwarren/claude-workspace #2485 — codex-review fix loop has no scope fence — https://github.com/mattwwarren/claude-workspace/issues/2485 — 2026-09-29 (kapandı 2026-10-01) — F — tam
48. HN — Codex vs. Claude Code (today) — https://news.ycombinator.com/item?id=46391391 — 2025-12 — F — tam (Algolia API)
49. HN — Ask HN: Does anyone use codex to review Claude's code? — https://news.ycombinator.com/item?id=48150810 — 2026-05-15 — F — tam
50. HN — Show HN: Zenflow — https://news.ycombinator.com/item?id=46290617 — 2025-12-16 — F — tam
51. HN — Show HN: Neal — Codex writes the code, Claude reviews it — https://news.ycombinator.com/item?id=49168496 — 2026-08-04 — F — tam
52. HN — Show HN: I built a social media management tool in 3 weeks with Claude and Codex — https://news.ycombinator.com/item?id=47749674 — 2026-04-13 — F — tam
53. HN Algolia araması "codex claude code review" (587 sonuç, ilk 20) — https://hn.algolia.com/api/v1/search?query=codex%20claude%20code%20review&tags=story — 2026-10-14 — F — liste
54. X gönderileri (Om Patel, Jason Zhou, Vox, Jim Prosser, HarrisDecodes, charliejhills) — https://x.com/om_patel5/status/2026129939179692242 ; https://x.com/jasonzhou1993/status/2038956679069684172 ; https://x.com/Voxyz_ai/status/2092273872217186312 ; https://x.com/jimprosser/article/2047761059386380400 — 2026 — F — **yalnız arama özeti** (sayfalar HTTP 402)

**S (ikincil)**
55. Daniel Vaughan — How to Make Codex CLI and Claude Code Work Together (2026-04-18, güncelleme 2026-10-14) https://codex.danielvaughan.com/2026/04/18/codex-cli-claude-code-working-together/ ; The Ultra Mode Trade-Off (2026-07-24) https://codex.danielvaughan.com/2026/07/24/codex-cli-ultra-mode-trade-off-reasoning-budgets-subagent-cost-task-routing/ ; `mcp-server` kaldırma yazıları (2026-08) — S — tam (iki sayfa); sayılar kaynaksız, kitin K6 raporu aynı siteyi S saymıştı
56. munderdiffl.in — Codex vs Claude Code usage limits (2026-10-10) https://munderdiffl.in/blog/codex-vs-claude-code-usage-limits/ ; developersdigest.tech — Codex usage limits and pricing 2026 (2026-09-29) https://www.developersdigest.tech/blog/codex-usage-limits-pricing-2026 — S (çok-ajan uygulama satan şirket) — tam
57. primeline.cc — Do Claude Code Review Rounds Actually Converge? — https://primeline.cc/blog/review-rounds-converge — tarih yok — S — **yalnız arama özeti** (alan adı çözümlenemedi)

**K (kitin kendi dosyaları, dosya + bölüm olarak atıf)**
- K1: `docs/research/ai-review-workflows.md` (bağlayıcı; §1.3, §S2, §S4, §5-G, §6)
- K2: `docs/research/context-limit.md` (biçim)
- K3: `docs/research/agent-kits-in-practice.md` (§1.3, §1.13, §2.4 superpowers, §3 tablo)
- K4: `docs/research/review-prompts-and-rules.md` (§1, §3, §4)
- K5: `docs/research/review-rules-inventory.md` (§A.7, §C.2 çelişkiler)
- K6: `docs/research/token-optimization.md` (§ öneri I, kaynak 40)
- K7: `docs/v011-overhaul-proposal.md` (A, B, C, D, E, F, G, H, K, L, P, Q; §0)
- K8: `RESEARCH_LOG.md` girdileri: 2026-10-14 communication rules; 2026-10-13 "The review policy rewritten…"; 2026-10-13 "Merging seven v0.11 branches…"; 2026-10-13 "Review launch capacity…"; 2026-10-11 "Routing effort and review ownership"; 2026-10-11 "Claude-only keeps cross review…"
- K9: `core/docs/WORKFLOW.md` ("Model routing", "Working modes, by name", `solo`/`normal`/`saver` ve Lessons)
- K10: `docs/decorrelated-review.md`; `docs/delegation-is-not-symmetric.md`; `docs/one-canonical-instruction-file.md` (başlığı okundu, gövdesi okunmadı); `core/AGENTS.md` ("Multi-tool project", "Review gate", "Task discipline")
