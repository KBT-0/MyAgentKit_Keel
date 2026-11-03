# Lead bağlamını ne dolduruyor, nasıl küçük tutulur, hand-off otomatikleşebilir mi? Kanıta dayalı araştırma raporu

Tarih: 2026-11-03. Soru (sahip): "Oturumlar 200k bağlama çok hızlı ulaşıyor. Ya hand-off'u otomatik yapan bir sistem kuralım ya da bağlamı çok daha sert optimize edelim; kaynaklı, derin araştır." Bu rapor bandın sayılarıyla (sahip kararı 2026-11-03: 150k plan / 200k kes / 300k tavan) ilgilenmez; **bağlamı neyin doldurduğu, neyin kesilebileceği ve hand-off'un ne kadarının otomatikleşebileceği** ile ilgilenir. Önceki rapor: `docs/research/context-limit.md` (bant, cache ekonomisi, sıkıştırmanın kayıplılığı); bu rapor onun açık sorusu 7'yi (forum kaynakları) NotebookLM ile kapatır.

Etiketler `context-limit.md` ile aynı: **R** araştırma/benchmark, **P** vendor birincil doküman, **B** blog/pratisyen, **F** forum/issue, **S** ikincil (NotebookLM özeti dahil; birincil sayfa açılmadıysa). Kanıt dili: **ölçüm**, **vendor beyanı**, **anekdot**, **çıkarım**. Kaynaklar `[n]`, liste bölüm 7'de. "Bizim ölçüm" = bu raporda transkriptlerden çıkarılan sayı (yöntem bölüm 3).

---

## 1) Kısa özet

1. **Lead bağlamının üçte biri modelin kendi çıktısı, üçte biri araç sonuçları, beşte biri enjeksiyonlar.** Üç projede (45 lead oturumu) bağlama giren token'ların %33–35'i modelin kendi çıktısı (yarısı araç çağrısı girdisi, ~%35–40'ı düşünce, ~%10'u görünen metin), %32–36'sı araç sonuçları, %20–26'sı harness/hook enjeksiyonları, %7–11'i sistem istemi + araç şemaları (bizim ölçüm, bölüm 3). Opus 4.5+ ve 5.x modelleri önceki turların düşünce bloklarını bağlamda tutar ve girdi olarak faturalar [3]; yani **effort lead bağlamını doğrudan büyütür**.
2. **Büyüme istek başına ~1,3–1,4k token, sabit.** Oturum ~44–53k ile açılıyor; 150k'ya medyan 60–70. istekte, 200k'ya 99–108. istekte varılıyor (bizim ölçüm). Tek bir "büyük kalem" yok: büyük çıktıları kesmek (Bash 8.000 karakter tavanı) bağlamın yalnız %0,5–1,7'sini kurtarırdı. Bağlamı dolduran şey **çok sayıda orta boy okuma + modelin kendi çıktısı**.
3. **Kitin kendi kuralları leeway ve labricore'da bağlamın ~%17–19'unu üretiyor.** STATE.md (oturum başına 13–40 okuma çağrısı; dosya 1.177–1.182 satır), hand-off dosyaları, worker RESULT/brief dosyaları, WORKFLOW/AGENTS/COMMUNICATION bölümleri, inceleme kayıtları ve check/doctor çıktıları (bizim ölçüm). Kitin kendi deposunda ~%8. En büyük tek kalem STATE.md + hand-off okumaları.
4. **Kitin overlay'i `outputStyle: "Concise"` ayarlıyor; Claude Code bunun için her turda bir hatırlatma ekliyor.** leeway'de 20 oturumda 2.080 hatırlatma, ~139k token (%2,9); kit deposunda %3,8 (bizim ölçüm). Kısa yanıt sahibin isteği (memory: owner-replies-too-long); bedeli ilk kez sayıldı.
5. **Literatürde ölçülmüş en büyük kaldıraç eski araç sonuçlarını atmak (gözlem maskeleme / tool-result clearing).** SWE-agent'ta maliyet %50+ düşüyor, çözme oranı korunuyor ya da artıyor [10]; LOCA-bench'te araç sonucu temizleme doğruluğu ~10 puan artırıyor [11][S]; Anthropic'in iç ölçümü %84 token azalması ve +%29 başarı [2]. **Claude Code CLI bunu kullanıcıya ayar olarak sunmuyor** (yalnız API'de `clear_tool_uses` [4]); CLI'da aynı etkinin tek yolu temiz oturum: `/clear` + dosyadan devralma. Hand-off = %100 maskeleme.
6. **"Az token" her zaman "ucuz" değil.** 35.000 koşuluk sistematik çalışma: token'ı üçte bire indiren sıkıştırma politikaları Terminal-Bench'te %20–80 daha uzun sürebiliyor [12]; ortadaki sıkıştırma cache'i kırar [4]. Kesme kararları cache'i bozmayan noktalarda (oturum başı, hand-off) yapılmalı.
7. **Otomatik hand-off'un güvenli kısmı büyük, tam otomatik kısmı yok.** Hiçbir hook `/clear`, `/compact` ya da yeni oturum başlatamaz (hook dokümanı; Stop/PreCompact yalnız engeller) [5]. Ama `SessionStart` hook'u `clear` kaynağında `additionalContext` (≤10.000 karakter) ekleyebilir [5]: **lead hand-off dosyasını yazar, sahip aynı terminalde `/clear` yazar, hook yeni bağlama "önce şu dosyayı oku" satırını koyar.** Model, effort ve terminal aynı kalır; `/clear` bedavadır [1]. Tam otomatik devir (sahip yokken lead'in kendini yeniden başlatması) yalnız kitin süpervizör betikleriyle mümkün ve "sahip oturum açar" kuralına dokunur: sahip kararı.
8. **Sıkıştırmayı yönlendirmek bedava.** Claude Code proje köküne yazılan "# Compact instructions" bölümünü otomatik ve boşta sıkıştırmada da kullanır [1]; boşta sıkıştırma varsayılan olarak 200k'nın üstünde ~1 saat beklemeden sonra açık [6]. Kitte bu bölüm yok.

En büyük belirsizlik: kalite tarafı. Bağlam küçülünce lead'in kural uyumunun ne kadar düzeldiğini bu üç model için ölçen yayın yok (context-limit.md açık soru 1 hâlâ açık); elimizde yön ve maliyet var.

---

## 2) Bulgular

### Bulgu 1. Bağlamın bileşimi: modelin kendi çıktısı, araç sonuçları, enjeksiyonlar (bizim ölçüm)

Kanıt gücü: **Orta-güçlü** (45 oturum, üç proje; token sayısı karakterden kalibre edildi, bölüm 3).

| Kaynak (lead bağlamına giren token payı) | leeway (20) | kit (16) | labricore (9) | Oturum başına medyan (leeway) | Ne zaman |
|---|---|---|---|---|---|
| Modelin kendi çıktısı (araç çağrısı girdisi + düşünce + metin) | %34,2 | %33,0 | %34,7 | 83k | her tur |
| Araç sonuçları (Bash, Read, Agent, …) | %32 | %36 | %35 | ~75k | her tur |
| Enjeksiyonlar (harness + hook) | %26,2 | %19,6 | %19,6 | 55k | çoğu bir kez, bir kısmı her tur |
| Sistem istemi + araç şemaları | %7,4 | %11,3 | %11,0 | 17k | bir kez |

- **Modelin kendi çıktısı:** leeway örneğinde (oturum başına 39–141k çıktı) ~%48'i araç çağrısı girdisi (komutlar, heredoc'lar, Write içeriği, brief metinleri), ~%12'si görünen metin, ~%40'ı transkriptte görünmeyen düşünce (çıktı sayısı eksi görünen karakterler). Anthropic: Opus 4.5 ve 4.6+ modelleri önceki turların düşünce bloklarını bağlamda tutar ve girdi olarak faturalar [3]. Kalibrasyonumuz bununla tutarlı (iki istek arasındaki büyüme, önceki çıktının tamamı + giren karakterlerle açıklanıyor). **Çıkarım:** lead'in effort'u düştükçe düşünce, dolayısıyla bağlam büyümesi düşer; effort değişimi 5.5/Fable 5.1'de abonelikte cache'i bozmaz [7].
- **Araç sonuçları:** leeway'de en büyük alt kalemler `bash:read` (cat/sed/head ile dosya okuma, %13,6), `bash:vcs` (git diff/log/show, %4,7), `bash:search` (grep/find/ls, %4,1), `bash:other` (%4,2); Read aracı yalnız %1,4. Sub-agent raporları küçük (leeway'de 16k toplam, %0,3). Test çıktısı lead'de küçük (%0,2 leeway, %1,8 kit): test işi zaten worker'larda.
- **Enjeksiyonlar, bir kez:** skill listesi oturum başına 8,5–11k (kullanıcı düzeyi eklentiler; `anthropic-skills` 27 oturumda hiç çağrılmadı ama listede ~5,3k/oturum), talimatlar (AGENTS.md/CLAUDE.md/memory) 4,5–10,5k, SessionStart hook'ları ~2k. Bunlar ctx0'ı (44–53k) oluşturur.
- **Enjeksiyonlar, her tur:** çıktı stili hatırlatması (leeway 6,5k, kit 9,5k medyan/oturum; Bulgu 5), arka plan görev bildirimleri (`queued_command`: worker watch'larının `<task-notification>` blokları; leeway 3,9k/oturum, %2,6), ortam anlık görüntüsü (`environment`, 1,3–4k), lead'in daha önce okuduğu bir dosya değişince eklenen kesit (`edited_text_file`: çoğu worker RESULT dosyası; ~2k/oturum), kitin hook satırları (PostToolUse:Bash ~0,5k, UserPromptSubmit ~0,4k). Kitin hook satırları küçük.

### Bulgu 2. Büyüme hızı sabit; 200k'ya ~100 istekte varılıyor (bizim ölçüm)

| | leeway (30 oturum) | kit (37) | labricore (9) |
|---|---|---|---|
| İstek başına büyüme (medyan) | 1.344 | 1.435 | 1.278 |
| 150k'ya varan oturum / medyan istek / medyan süre | 28 / 67 / 51 dk | 34 / 70 / 18 dk | 7 / 60 / 26 dk |
| 200k'ya varan oturum / medyan istek / medyan süre | 25 / 108 / 157 dk | 33 / 106 / 30 dk | 6 / 99 / 273 dk |

Sahibin gözlemi doğru: oturumların %80–90'ı 200k'yı geçiyor. **Çıkarım:** ctx0'ı 10k düşürmek 200k'ya varışı ~7 istek geciktirir; istek başı büyümeyi %25 düşürmek ~27 istek. Kaldıraç ctx0'dan çok istek başı büyümede (araç sonuçları + çıktı).

### Bulgu 3. Kitin kendi kuralları leeway/labricore'da bağlamın ~%17–19'u (bizim ölçüm)

Komut etiketine göre eşleşen araç sonuçları (ilk eşleşen kategori; üst sınır değil, yaklaşık):

| Kaynak | leeway | labricore | kit | Oturum başına çağrı (en yüksek 4) |
|---|---|---|---|---|
| STATE.md okumaları | %4,3 (282 çağrı) | %6,6 (172) | %0,1 | leeway 38/33/32/32, labricore 40/30/23/23 |
| Hand-off dosyaları | %5,0 (321) | %2,2 | %0,4 | leeway 52/44/35/31 |
| Worker RESULT / brief | %2,7 (183) | %1,4 | ~0 | leeway 28/22/19/18 |
| WORKFLOW / AGENTS / COMMUNICATION / GOTCHAS | %2,5 | %3,2 | %3,2 | kit 30/20/20/13 |
| PHASES / BACKLOG | %1,0 | %1,5 | %0,1 | |
| İnceleme kayıtları | %0,5 | %1,7 | %2,6 | |
| check.sh / check_kit / doctor | %0,6 | %0,5 | %2,3 | kit 36/23/16/16 |
| **Toplam** | **~%16,6** | **~%18,8** | **~%8,3** | |

- STATE.md her iki projede ~1.180 satır. Kural zaten "yalnız Active work ve Blocked bölümlerini oku" diyor (`core/AGENTS.md` 24. satır, `after_compact.txt`); lead bunu `grep -n '^###'` + `sed -n` ile yapıyor, ama oturum başına 13–40 kez. Bölüm okumaları tek tek küçük, toplamı büyük. labricore'da bir oturumda `cat docs/PHASES.md && sed -n 1,160p docs/STATE.md && cat docs/BACKLOG.md` tek başına 12k token; Read ile tam STATE.md 29k.
- Kit deposunda (lead kendi kodunu düzenliyor) baskın kalemler farklı: kod okuma (`sed -n` ile hook/test dosyaları), check çıktıları, inceleme kayıtları.
- **Çıkarım:** bu kalemlerin her biri kitin metninde bir kuraldan geliyor ("STATE'i oku", "hand-off'u oku", "RESULT'u oku", "check'i çalıştır"). Okumanın kendisi gerekli; pahalı olan **dosyaların boyutu ve tekrar sayısı**.

### Bulgu 4. Literatür: en çok kazandıran şey eski araç sonuçlarını bağlamdan atmak

Kanıt gücü: **Güçlü** yön, büyüklük modele/iskeleye bağlı.

- **R [10] JetBrains, The Complexity Trap (NeurIPS 2025 workshop):** SWE-agent, SWE-bench Verified 500 görev: son 10 tur dışındaki gözlemleri yer tutucuyla değiştirmek maliyeti Qwen3-Coder 480B'de %52,7, Gemini 2.5 Flash'ta %56,1 düşürdü; çözme oranı 53,4→54,8 ve 32,8→35,6. LLM özetlemesi benzer başarı, %13–15 daha uzun koşu, özet çağrıları maliyetin %5–7'si. Gözlemler ortalama turun ~%84'ü.
- **R [11] LOCA-bench (arXiv 2602.07962):** bağlam 8k→256k büyürken her modelde doğruluk monoton düşüyor; araç sonucu temizleme ve programatik araç çağrısı doğruluğu belirgin artırıyor (NotebookLM özeti: GPT-5.2-Medium'da ~10 puan) [S].
- **P [2] Anthropic (2025-09-29):** 100 turluk web arama değerlendirmesinde context editing token tüketimini %84 azalttı; iç ajan arama setinde context editing tek başına +%29, memory tool ile +%39 başarı. Vendor iç ölçümü.
- **R [13] CoACT (arXiv 2607.02911):** sonraki eylemi değiştirmeyen gözlem sıkıştırma, mini-swe-agent: toplam token −%33, Pass@1 korunuyor/artıyor (NotebookLM özeti; özet sayfası doğrulandı) [S].
- **R [14] TokenEconomizer (arXiv 2610.22732):** Claude Code, Codex, Copilot CLI üzerinde dış kontrolcü (hiç çağrılmayan araçları budamak, mikro-beceri enjeksiyonu, başarısız döngüye müdahale): ortalama token maliyeti −%18,4–30,9, başarı benzer (özet doğrulandı).
- **R [12] Beyond Token Savings (arXiv 2609.32961):** ~35.000 koşu: "daha az token daha hızlı ya da ucuz demek değil"; token'ı üçte bire indiren politikalar Terminal-Bench'te %20–80 daha uzun sürebiliyor; aynı politika modeller arasında farklı davranıyor (özet doğrulandı). Önceki v0.14 araştırması da araç çıktısını %38 kesmenin cache yeniden yazımı yüzünden faturayı %6,8 artırdığını bulmuştu (`.myagentkit/v014/tokresearch/PLAN.md` Y6).
- **R [15] Context Length Alone Hurts (arXiv 2510.05381):** kanıt bağlamda kesin olarak varken bile uzunluk arttıkça performans %13,9–85 düşüyor; alakasız metni boşlukla değiştirmek düşüşü gidermiyor (NotebookLM özeti) [S]. Yani "gereksiz okuma zararsızdır" yanlış: uzunluğun kendisi zarar.
- **B [16] Hexaware (vendor-dışı danışman, 1.296 koşu, Opus/Sonnet 4.6 dahil):** hedefli yükleme (~10k) %88,5 doğruluk, tüm kod tabanı (~200k) %80,2, sıkıştırılmış özet %68,8 ve %54 halüsinasyon (NotebookLM özeti; birincil sayfa açılmadı) [S]. Çıkarım: **özet, yerine geçtiği ham bilgiden kötü olabilir**; hand-off dosyası özet değil işaretçi (dosya yolu, commit, karar) taşımalı.
- **Kitle ilgisi:** Claude Code CLI bu tekniklerin hiçbirini ayar olarak açmıyor. Dokümanda yalnız "/usage, compaction ya da araç sonucu temizlemeyi beklenen yeniden kurulum sayar" cümlesi var [8]; ne zaman ve nasıl yaptığı yazılı değil (açık soru 2).

### Bulgu 5. Çıktı stili hatırlatması her turda (bizim ölçüm + P)

Kitin overlay `settings.json` dosyası `"outputStyle": "Concise"` ayarlıyor. Claude Code stil talimatını bir kez, ayrıca her turda kısa bir `turnReminder` ekliyor (transkriptte `output_style` eki; metin: "Be concise: lead with the result, …"). leeway: 2.080 ek, ~139k token, bağlamın %2,9'u; kit: %3,8; labricore'da bu ayar kapalıymış (medyan 0). Stil değişimi cache'i bozmaz [8]. Bedel-fayda: hatırlatma ~67 token/tur; görünen metin çıktının yalnız ~%12'si. Kısa yanıtı stil yerine tek bir AGENTS/COMMUNICATION kuralıyla istemek bu %3–4'ü kurtarır, ama sahip "yanıtlar uzun" şikâyetiyle bu ayarı istemişti (memory: owner-replies-too-long). **Sahip kararı**.

### Bulgu 6. Claude Code'un sunduğu kollar (P)

- **Bash çıktı tavanı:** başarılı komut ~30.000 karaktere kadar satır içi, fazlası dosyaya + 2.000 karakter önizleme; `bashOutputMaxChars` 4.000–128.000 arası [9]. Simülasyonumuz: 8.000 karakter tavanı bağlamın %0,5–1,7'sini, 12.000 %0,3–0,8'ini kurtarırdı; bedeli kesilen dosyayı yeniden okuma çağrısı. **Küçük kaldıraç.**
- **Read tavanı:** dosya okuma 25.000 token'da sınırlı (`CLAUDE_CODE_FILE_READ_MAX_OUTPUT_TOKENS`) [9].
- **Skill listesi:** `skillOverrides` ile tek skill gizlenir, `enabledPlugins` ile eklenti kapanır, `skillListingBudgetFraction` / `skillListingMaxDescChars` (kit 160 kullanıyor) [6]. leeway'de hiç çağrılmayan `anthropic-skills` ~5,3k/oturum, `cowork-plugin-management` ve `frontend-design` ek ~0,5k.
- **Sıkıştırma talimatı:** `/compact <odak>` ya da proje kökü CLAUDE.md içinde "# Compact instructions" bölümü [1]; `/rewind` → "Summarize from here" kısmi sıkıştırma [17].
- **Boşta sıkıştırma (`idleCompaction`):** 1 saatlik TTL'de, bağlam ≥200.000 (`CLAUDE_CODE_IDLE_COMPACT_MIN_TOKENS`) ve ~1 saat boşta kalınca varsayılan açık; PreCompact `auto` olarak tetiklenir [6][5]. Worker bekleyen lead bu koşula uyar: kitin "ikinci sıkıştırma = hand-off" kuralı sahibin haberi olmadan tetiklenebilir.
- **Sıkıştırmadan ne sağ çıkar:** kök CLAUDE.md, kapsamsız kurallar, auto-memory, skill açıklamaları yeniden eklenir; okunan dosyalardan en yeni 5'i yeniden okunur (>5k token olan yalnız yol olarak); hook'ların eklediği bağlam özetlenip kaybolur; `compact` kaynaklı SessionStart hook'ları yeniden çalışır [8].
- **`/clear` bedava, `/compact` büyük bir istek** [1]; sıkıştırma, cache sıcakken bağlam boyutunun "küçük bir kısmına" mal olur [8].

### Bulgu 7. Otomatik hand-off: ne mümkün, ne değil (P + F + çıkarım)

Mekanizmalar (Claude Code hook dokümanı [5]):
- **PreCompact:** `trigger` (manual/auto) ve `custom_instructions` alır; exit 2 ya da `decision: "block"` ile sıkıştırmayı engelleyebilir (otomatik, bağlam limitinden önce tetiklendiyse oturum sıkıştırılmadan sürer). Sıkıştırma talimatı **ekleyemez**. Kit bunu git gerçeklerini not etmek için kullanıyor (`before_compact.py`).
- **PostCompact:** `compact_summary` alır; karar kontrolü yok; özetin kaydı için uygun.
- **SessionStart:** `startup`, `resume`, `clear`, `compact`, `fork` kaynakları; `additionalContext` ile bağlama bilgi ekler (her dize ≤10.000 karakter; fazlası dosyaya, yalnız 2.000 karakter önizleme) [5].
- **Stop:** durmayı engelleyip modele bir gerekçe verebilir (çalışmaya devam ettirir); oturumu yeniden başlatamaz.
- **Hiçbir hook `/clear`, `/compact` ya da yeni oturum başlatamaz** (dokümanda yok).

Diğer araçlar:
- **Cline `new_task` [18][19]:** model bir `<context>` bloğu (yapılan iş, durum, sonraki adım) ile yeni görev önerir; kullanıcı onaylar; `.clinerules` örnekleri "%50 kullanımda öner" der. Eşik varsayılan değil, kullanıcı kuralı. Yani Cline'da da **son adım kullanıcının onayı**.
- **Codex [20][21]:** otomatik sıkıştırma eşik (`model_auto_compact_token_limit`, pencerenin ~%90'ını aşamaz) ve özel sıkıştırma istemi (`compact_prompt`, `experimental_compact_prompt_file`), tur sonu sıkıştırma (`model_post_turn_compact_threshold_percent`), araç çıktısı bütçesi (`tool_output_token_limit`). Sıkıştırma OpenAI uç noktasında şifreli özet üretiyor (üçüncü taraf analizi) [21][S].
- **Cursor [22]:** uzun araç çıktılarını kesmek yerine dosyaya yazıp `tail`/`grep` ile okutma; özetlemede tam geçmişi dosyada saklama (ajan eksik ayrıntıyı oradan geri alır); MCP araçlarını isteğe bağlı yükleme A/B testinde −%46,9 token (vendor iç ölçümü).
- **Pratisyenler (F, NotebookLM üzerinden):** PreCompact/PostCompact ile tam transkripti SQLite'a yazıp sıkıştırma sonrası geri enjekte eden bir kurulum 1.300+ oturumda "0 kayıp mesaj" bildiriyor [23][S, anekdot]; hand-off'u `/clear` öncesi ~90 satırlık bir markdown dosyasına yazdırmak yaygın [24][F]. Raporlanan arızalar: özetin yığın izlerini, dosya yollarını, satır numaralarını silmesi; sıkıştırma sonrası kural unutma; uzun oturumlarda dosyaları tekrar okuma döngüsü (LoCoBench-Agent: kavrama 15–20 turda tepe, verimlilik 12–15 turdan sonra süperlineer düşüş, r=−0,71) [25][S].

**Güvenle otomatikleşebilen (çıkarım):**
1. Hand-off dosyasının yazımı ve doğrulanması (lead yazar; bir betik "commit edilmemiş değişiklik yok, hand-off son commit'ten yeni, STATE güncel" kontrol eder).
2. Yeni bağlamın dosyayı okuması: `SessionStart` (`clear` ve `startup`) hook'u, tüketilmemiş bir hand-off işareti görünce tek satır ekler ("Önce docs/handoffs/X.md'yi oku; yazıldığı commit Y"). İşaret bir kez tüketilir (döngü olmaz).
3. Sahibin tek eylemi: aynı terminalde `/clear`. Model ve effort aynı kalır; sistem istemi + araç cache'i aynı dizinde sıcak kalır [8].

**Sahipte kalması gereken:** `/clear`'ı yazmak ya da yeni oturumu açmak (memory: owner-opens-sessions; hook bunu zaten yapamaz). Sahip yokken (autopilot) lead kendini temizleyemez; seçenekler: (a) bugünkü gibi sıkıştırıp devam (`after_compact.txt`), (b) kitin süpervizör betikleriyle yeni bir lead oturumu başlatmak — bu "sahip oturum açar" kuralını değiştirir, **sahip kararı**.

**Riskler ve önlemler:** commit edilmemiş iş (hook, `git status` temiz değilse satırı eklemez ve uyarır); hand-off döngüsü (işaret tek kullanımlık, oturum başına bir); yeniden okuma maliyeti (yeni bağlam ~45–55k + hand-off dosyası; context-limit.md bölüm 3: Opus'ta ~25 istekte kendini öder); arka plan işlerin ölmesi (`/clear` oturumu kapatmaz ama yeni bağlam onları bilmez: kitin "iş sürerken hand-off yok" kuralı (memory: no-handoff-while-work-runs) geçerli kalır).

---

## 3) Kendi sayılarımız: yöntem ve sınırlar

- **Veri:** `~/.claude/projects/-home-kbt--Development-project-leeway` (son 4 gün, 20 lead + 22 sub-agent), `-home-kbt--Development-MyAgentKit-Keel` (son 4 gün, 16 lead), `-home-kbt--Development-labricore-web` (son 10 gün, 9 lead). Araç: `core/scripts/token_audit.py --items` (her taşınan öğe bir JSON satırı) + öğeleri kaynağa ve komut etiketine göre toplayan küçük betikler (iş klasöründe, depoya girmedi). Büyüme ve eşik süreleri transkriptteki her isteğin `input + cache_read + cache_write` değerinden.
- **Toplam görünüm:** leeway lead'leri: 3.104 istek, $231, ctx0 medyan 44.498, ctx max medyan 236.170, 4 sıkıştırma; kit: 2.055 istek, $118, ctx0 43.476, ctx max 216.772; labricore: 1.257 istek, $103, ctx0 53.433, ctx max 237.857.
- **"Giren token" ölçüsü:** her öğenin karakteri / 2,4 (token_audit'in kalibrasyonu). Bu oturumlarda gözlenen oran 1,8–2,3 karakter/token, yani öğe token'ları ~%5–25 eksik sayılmış olabilir; **paylar** (yüzdeler) bundan az etkilenir. Modelin çıktısı API'nin kendi `output_tokens` sayısı.
- **Sınırlar:** etiket eşlemesi ilk eşleşen kategoriye yazar (ör. hem STATE hem HANDOFF okuyan bir komut tek kategoriye); "Oturum başına çağrı" komut içinde dosya adı geçen çağrılar, okuma olmayanları da (ör. `git add docs/STATE.md`) sayabilir. Kit deposunun ana klasörü inceleme ve kısa yardımcı oturumlar da içerebilir (200k'ya 30 dk medyanı bu yüzden kısa olabilir). Kalite (kural ihlali) bu ölçümde yok.
- **Bu oturumun kendisi:** bu araştırma worker'ı ~45 dakikada 200k'ya ulaştı; büyük kalemler Claude Code doküman sayfalarının tam metinleri (WebFetch, sayfa başına 8–15k) ve ölçüm betiklerinin tablo çıktılarıydı. Aynı örüntü: orta boy, çok sayıda okuma.

---

## 4) Çıkarım: neyi kesmek, ne kadar kazandırır?

Varsayım: tipik lead 235k'da kesiliyor (bugünkü medyan), istek başı büyüme 1.350.

| Kalem | Bugün (bağlam payı) | Gerçekçi kesinti | Tahmini kazanç (pay) | Kaynak |
|---|---|---|---|---|
| Kitin belge okumaları (STATE, hand-off, RESULT, kurallar) | %17–19 | yarıya | ~%8–9 | Bulgu 3 |
| Lead effort (düşünce bağlamda kalır) | düşünce ~%12–14 | high→medium ile ~%30–50 daha az düşünce (ölçülmedi) | ~%4–6 | Bulgu 1, [3]; v0.14 Y2 |
| Çıktı stili turnReminder | %3–4 | sıfır (stil kuralı AGENTS'a) | ~%3–4 | Bulgu 5 |
| Çağrılmayan skill/eklenti listesi | ~%2–3 (ctx0'da ~5–6k) | sıfır | ~%2–3 | Bulgu 1, 6 |
| Görev bildirimleri + düzenlenen-dosya kesitleri | ~%3–4 | yarıya | ~%1,5–2 | Bulgu 1 |
| Bash çıktı tavanı 12k | — | — | ~%0,3–0,8 | Bulgu 6 |

**Toplam (çıkarım):** ~%18–24 daha yavaş büyüme; 200k'ya varış ~100 istekten ~125–130 isteğe. Bu, sahibin "çok hızlı doluyor" sorununu **kısmen** çözer; asıl çözüm yine kesme anının ucuz ve güvenli olması (Bulgu 7), çünkü literatürdeki en büyük kaldıraç (eski araç sonuçlarını atmak, %50+) CLI'da yalnız temiz bağlamla elde ediliyor.

---

## 5) Kit için ÖNERİ

Sıra: beklenen etki / bedel oranına göre. Her biri için tür: **doküman kuralı**, **hook**, **betik**, **proje ayarı**. Lead karar verir.

**Öneri 1. `/clear` ile tek tuş hand-off: SessionStart(clear|startup) hook'u + hand-off işareti. (hook + küçük betik)**
- Ne: lead hand-off'u yazıp commit eder ve bir işaret dosyası bırakır (`.myagentkit/handoff-pending`: dosya yolu + commit). `SessionStart` hook'u `clear` ve `startup` kaynağında işareti görürse ve `git status` temizse bir satır ekler ("Önce X'i oku; commit Y; kalan iş Z") ve işareti tüketir. Sahip aynı terminalde `/clear` yazar; yeni oturum açmaya, model id'si yazmaya gerek kalmaz.
- Kazanç: 200k'dan ~50k'ya (%75) bedava geçiş; tam "gözlem maskeleme" [10][2]; sahibin eylemi tek komut. Bugünkü hand-off akışı (yeni terminal, tam model id, yapıştırılan istem) ortadan kalkar.
- Bedel: ~60 satır hook + test; `/clear` arka plan işlerini bilmeyen bir bağlam bırakır, bu yüzden hook "iş sürüyor" işaretinde (kitin mevcut `no-handoff-while-work-runs` mantığı) satırı eklemez. Döngü riski yok (tek kullanımlık işaret). Sahip kuralına dokunmaz (`/clear` sahibin eylemi).
- context_size.py ve progress_reminder.py metni: kesme noktasında "`/clear` yaz, hook hand-off'u yükler" der.

**Öneri 2. STATE.md'yi iki katmana böl: ≤80 satırlık "baş" + arşiv. (doküman kuralı + check.sh sınırı)**
- Ne: STATE.md'nin başı yalnız Active work / Blocked / Next (≤80 satır, check.sh satır sınırıyla zorlanır); kapanan kayıtlar ve uzun geçmiş `docs/state/ARCHIVE-YYYY-MM.md`'ye. Lead "STATE'i oku" kuralında yalnız başı okur (`sed -n 1,80p`). Living-docs-never-bloat mekanizmasının STATE'e uygulanması.
- Kazanç: leeway %4,3 + labricore %6,6'nın büyük kısmı; hand-off dosyaları da aynı kuralla (≤120 satır, yalnız işaretçi: yollar, commit'ler, kararlar, sonraki adım) leeway'in %5,0'ının yarısı. Toplam ~%5–7 (bizim ölçüm, Bulgu 3). Hedefli yükleme özetten iyi [16][S].
- Bedel: arşive taşıma işi (betikle); arşivde kalan bir bilgiyi lead görmez — gerekirse `grep`. Projelerde sync ile gelir.

**Öneri 3. Worker sonucunu lead'e "dört satır + yol" olarak ver. (doküman kuralı)**
- Ne: lead RESULT dosyasını önce `head -4` (Kind/Task/Attempt/Remaining) ile okur; gövdeyi yalnız karar gerekiyorsa, bölüm bölüm. RESULT'u Read aracıyla okumamak, worker'ın sonraki düzenlemelerinin `edited_text_file` kesitleri olarak lead'e akmasını da önler (çıkarım: kesit, Read ile okunan dosyalar için ekleniyor). Watch bildirimlerinin metni tek satır.
- Kazanç: leeway RESULT/brief %2,7 + düzenlenen-dosya ~%1 + bildirim ~%2,6'nın yarısı → ~%3.
- Bedel: lead bir ayrıntıyı ikinci okumada alır (bir çağrı).

**Öneri 4. Lead varsayılan effort'u medium; high/xhigh adım bazında. (doküman kuralı, zaten v0.14 Y2 yönü)**
- Kazanç: düşünce lead bağlamının ~%12–14'ü ve bağlamda kalıyor [3]; effort düşünceyi azaltır. Büyüklük bu modellerde ölçülmedi (~%4–6 tahmin). Effort değişimi 5.5/Fable 5.1'de abonelikte cache'i bozmaz [7].
- Bedel: zor tasarım adımında kalite riski; o adımda `/effort high`.

**Öneri 5. "# Compact instructions" bölümü kök CLAUDE.md/AGENTS.md'ye; boşta sıkıştırma kararı. (doküman + proje ayarı)**
- Ne: 5–8 satırlık bölüm: korunacaklar = açık kararlar, bağlayıcı kurallar, değişen dosyalar ve commit'ler, sonraki adım, sahibin sözleri aynen; atılacaklar = bitmiş işin araç çıktıları. Otomatik ve boşta sıkıştırma bunu kullanır [1]. Boşta sıkıştırma (`idleCompaction`, ≥200k + ~1 saat boşta [6]) için karar: açık kalırsa kitin "ikinci sıkıştırma = hand-off" sayacı onu da sayar; kapatılırsa (`"idleCompaction": false`) bir saatlik molanın ardından ilk istek tüm bağlamı yeniden yazar. Öneri: açık kalsın, sayılsın (bedava ve cache'i sıcakken yapılıyor [8]).
- Bedel: ~8 satır her oturumda (~150 token).

**Öneri 6. Proje düzeyinde çağrılmayan eklentileri kapat. (proje ayarı, sahip kararı)**
- Ne: kit projelerinin `.claude/settings.json` dosyasında `enabledPlugins` ile `anthropic-skills`, `cowork-plugin-management`, `frontend-design` `false`; token_audit zaten bunu öneriyor.
- Kazanç: ctx0'dan ~5–6k her lead, worker ve sub-agent'ta (%2–3 lead; worker ctx0'ında ~%15). Bedel: sahip bu skill'leri o projede kullanamaz (leeway'de 27 oturumda 0 çağrı).

**Öneri 7. Çıktı stilini kural metnine taşımayı ölç; karar sahipte. (proje ayarı)**
- Ne: bir hafta `outputStyle` kapalı, kısalık kuralı `docs/COMMUNICATION.md`'de; yanıt uzunluğu ve bağlam payı karşılaştırılır.
- Kazanç: %3–4 (bizim ölçüm). Bedel: yanıtlar uzayabilir; sahip bunu bir kez şikâyet etmişti.

**Öneri 8. Kitin kendi deposunda: kod okuma `grep -n` + dar `sed -n`; check çıktısı yalnız başarısızlık + son satır. (doküman kuralı)**
- Kazanç: kit lead'inde check/doctor %2,3 + inceleme kayıtları %2,6'nın yarısı (~%2–3). Anthropic'in test-çıktısı filtresi örneği aynı yönde [1].

**Öneri 9. Bash çıktı tavanını değiştirme.** 12k tavan yalnız %0,3–0,8 kazandırır (Bulgu 6); büyük çıktı sorunu yok. Yapılmasın.

**Önerilmeyen:** orta-oturum araç sonucu temizleme ya da özetleme için üçüncü taraf araç/proxy (CLI'da yok; cache kırar [4][12]; v0.14 ölçümünde headroom/Context Mode maliyeti artırdı, PLAN.md Y6).

**Ölçüm (her öneriden sonra):** aynı `token_audit.py --items` + bu raporun kategori betiği; hedef ölçüler: istek başı büyüme (bugün 1.278–1.435), 200k'ya varış isteği (bugün 99–108), kitin belge okuma payı (bugün %17–19). Öneri 1 için: hand-off başına sahip eylemi sayısı ve yeni bağlamın ilk 20 isteğindeki "tekrar okuma" çağrıları.

---

## 6) Açık sorular

1. **Kalite:** bağlam payını %20 düşürmenin lead'in kural uyumuna etkisi ölçülmedi; context-limit.md açık sorusu 1 ve 3 sürüyor. LOCA-bench ve Context Length Alone Hurts yön veriyor, hedef modelleri ölçmüyor.
2. **Claude Code'un kendi "araç sonucu temizleme"si:** `/usage` ve statusline dokümanı compaction'ın yanında "tool-result clearing"i beklenen yeniden kurulum sayıyor [8][26]; ne zaman tetiklendiği, ayarı olup olmadığı dokümanda yok. Transkriptlerde izi aranmadı.
3. **`edited_text_file` kesitleri** yalnız Read ile okunan dosyalar için mi ekleniyor, Bash ile okunanlar için de mi? Öneri 3'ün bir parçası buna bağlı; doğrulanmadı.
4. **Effort'un bağlam büyümesine etkisi** bu modellerde ölçülmedi; aynı görevde medium/high lead A/B'si gerekir.
5. **NotebookLM özetleri:** [11][13][15][16][23][25] sayıları NotebookLM'in kaynak özetinden; [12][13][14] için arXiv özet sayfaları doğrulandı, makale gövdeleri okunmadı. Hexaware [16] ve SQLite kurulumu [23] tek kaynak/anekdot.
6. **Abonelik limiti:** bağlam payı düşüşünün sahibin 5 saatlik limitine yansıması ölçülmedi (context-limit.md açık soru 4).

---

## 7) Kaynaklar (hepsi 2026-11-03 okundu)

1. **P** Claude Code docs, "Manage costs effectively" (reduce token usage, compact instructions, test-output hook, `/clear` bedava, why usage climbs): https://code.claude.com/docs/en/costs
2. **P** Anthropic, "Managing context on the Claude Developer Platform" (2025-09-29; %84, +%29, +%39): https://claude.com/blog/context-management
3. **P** Claude API docs, "Extended thinking" (Opus 4.5 ve 4.6+ önceki düşünce bloklarını bağlamda tutar, girdi olarak faturalar): https://platform.claude.com/docs/en/build-with-claude/extended-thinking
4. **P** Claude API docs, "Context editing" (`clear_tool_uses_20250919`: tetik 100k, keep 3, `clear_at_least`, cache'i kırar; `clear_thinking_20251015`): https://platform.claude.com/docs/en/build-with-claude/context-editing
5. **P** Claude Code docs, "Hooks reference" (PreCompact/PostCompact girdileri, SessionStart kaynakları, Stop, 10.000 karakter sınırı): https://code.claude.com/docs/en/hooks
6. **P** Claude Code docs, "Settings reference" (`idleCompaction`, `autoCompactWindow`, `bashOutputMaxChars`, `skillOverrides`, `enabledPlugins`) ve "Environment variables" (`CLAUDE_CODE_IDLE_COMPACT_MIN_TOKENS` 200000): https://code.claude.com/docs/en/settings-reference , https://code.claude.com/docs/en/env-vars
7. **P** Claude Code docs, "Prompt caching" — effort değişimi 5.5/Fable 5.1'de cache'i korur: https://code.claude.com/docs/en/prompt-caching
8. **P** Claude Code docs, "Explore the context window" (sıkıştırmadan ne sağ çıkar) ve "Prompt caching" (compaction maliyeti, çıktı stili değişimi, /usage "expected rebuilds"): https://code.claude.com/docs/en/context-window , https://code.claude.com/docs/en/prompt-caching
9. **P** Claude Code docs, "Tools reference" (Bash çıktı sınırları: ~30.000 / başarısızda ~10.000) ve env-vars (`CLAUDE_CODE_FILE_READ_MAX_OUTPUT_TOKENS` 25.000): https://code.claude.com/docs/en/tools-reference
10. **R** Lindenbauer ve ark. (JetBrains / TUM), "The Complexity Trap: Simple Observation Masking Is as Efficient as LLM Summarization for Agent Context Management", NeurIPS 2025 workshop: https://arxiv.org/abs/2508.21433
11. **R [S]** "LOCA-bench: Benchmarking Language Agents Under Controllable and Extreme Context Growth": https://arxiv.org/abs/2602.07962 (özet doğrulandı; sayı NotebookLM özetinden)
12. **R** "Beyond Token Savings: A Systematic Study of Context Compression in LLM Agents": https://arxiv.org/abs/2609.32961 (özet doğrulandı)
13. **R [S]** "CoACT: Action-Preserving Observation Compression for Coding Agents": https://arxiv.org/abs/2607.02911 (özet doğrulandı; sayılar NotebookLM'den)
14. **R** "TokenEconomizer: Experience-Driven Black-Box Cost Control for Coding Agents": https://arxiv.org/abs/2610.22732 (özet doğrulandı: −%18,4–30,9)
15. **R [S]** Du ve ark., "Context Length Alone Hurts LLM Performance Despite Perfect Retrieval": https://arxiv.org/abs/2510.05381
16. **B [S]** Hexaware, "Your Context Window Is Lying to You — And It's Costing You": https://hexaware.com/blogs/your-context-window-is-lying-to-you-and-its-costing-you/ (NotebookLM özeti; açılmadı)
17. **P** Claude Code docs, "Checkpointing" (`/rewind` → Summarize from here): https://code.claude.com/docs/en/checkpointing
18. **P** Cline docs, "New Task Tool": https://docs.cline.bot/exploring-clines-tools/new-task-tool ; Cline blog, "Unlocking persistent memory: how Cline's new_task tool…": https://cline.bot/blog/unlocking-persistent-memory-how-clines-new_task-tool-eliminates-context-window-limitations (arama özeti)
19. **P** Cline docs, "Auto Compact": https://docs.cline.bot/features/auto-compact
20. **P** OpenAI Codex config reference (`model_auto_compact_token_limit`, `compact_prompt`, `experimental_compact_prompt_file`, `model_post_turn_compact_threshold_percent`, `tool_output_token_limit`, `rollout_budget`): https://learn.chatgpt.com/docs/config-file/config-reference
21. **B [S]** D. Vaughan, "Mastering Context Compaction in Codex CLI" ve "Context Compaction Showdown": https://codex.danielvaughan.com/2026/04/16/codex-cli-context-compaction-tuning-long-sessions/ , https://codex.danielvaughan.com/2026/04/10/context-compaction-showdown-coding-agents/ (arama özeti)
22. **P** Cursor blog, "Dynamic context discovery" (Ocak 2026; MCP −%46,9): https://cursor.com/blog/dynamic-context-discovery (arama özeti)
23. **B [S, anekdot]** M. Dolan, "Claude Code compaction kept destroying my work, I built hooks that fixed it": https://dev.to/mikeadolan/claude-code-compaction-kept-destroying-my-work-i-built-hooks-that-fixed-it-2dgp (NotebookLM)
24. **F [S]** Hacker News, zomglings (hand-off dosyası + `/clear`): https://news.ycombinator.com/item?id=43737377 ; theptip (sub-agent okumaları): https://news.ycombinator.com/item?id=46661725 ; r/ClaudeCode "Claude Code was burning my context window…": https://www.reddit.com/r/ClaudeCode/comments/1t1gibs/ ; r/ClaudeAI "My Claude Code context window strategy" (MCP 133k→38k): https://www.reddit.com/r/ClaudeAI/comments/1p05r7p/ ; r/ClaudeCode "/context uses 2k of context every time you run it": https://www.reddit.com/r/ClaudeCode/comments/1xgsh9k/ (hepsi NotebookLM üzerinden; doğrudan açılmadı)
25. **R [S]** "LoCoBench-Agent: An Interactive Benchmark for LLM Agents in Long-Context Software Engineering": https://arxiv.org/abs/2511.13998 (özet sayfası var; sayılar NotebookLM'den)
26. **P** Claude Code docs, "Status line" (`context_window.*`, `exceeds_200k_tokens`, prompt_cache misses tanımı): https://code.claude.com/docs/en/statusline
27. **P** Anthropic Applied AI, "Effective context engineering for AI agents" (2025-09-29; araç sonucu temizleme en hafif sıkıştırma, NOTES.md, sub-agent 1–2k özet, head/tail/grep ile tam zamanında okuma): https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents
28. **R [S]** Chroma, "Context Rot" (18 model; LongMemEval ~113k'da ~%30 düşüş): https://research.trychroma.com/context-rot (context-limit.md [1] ile aynı; sayı NotebookLM'den)

NotebookLM: dört derin araştırma defteri (2026-11-03, "ctx 2026-11-03 A/B/C/D", 20–42 kaynak); yalnız metin sorgu gönderildi, depodan hiçbir dosya yüklenmedi.
