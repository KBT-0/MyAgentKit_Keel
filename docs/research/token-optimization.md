# Agentic kodlamada token ve maliyet optimizasyonu (2025–2026): kanıta dayalı araştırma raporu

Tarih: 2026-10-13. Kapsam: Claude Code ve Codex CLI ile uzun soluklu proje geliştirmede prompt cache mekaniği ve fiyatlandırması, abonelik kotalarının hesaplanması, ölçülmüş tasarruf teknikleri ve maliyet ölçüm araçları. Kaynak numaraları `[n]` köşeli parantezle, tam liste bölüm 6'da. Güvenilirlik etiketleri: **R** (resmi doküman), **P** (hakemli/preprint makale), **B** (mühendislik blogu / vendor), **F** (forum, issue, anekdot), **S** (ikincil aktarım; birincil kaynak doğrulanamadı).

Değerlendirilen bağlam ("bizim kit", MyAgentKit): lead session + arka plan worker'lar; `core/docs/WORKFLOW.md` "Worker cost", "Token economics", "MCP hygiene", "Model routing" bölümleri; `docs/context-is-a-budget.md`; `docs/worker-cost-setups.md` (altı kurulumlu ölçüm, 2026-10-03); `core/scripts/agent_cost.py` (transkriptten request bazlı cache-write/poll sayımı). Test edilen inançlarımız: sub-agent cache 5 dk / ana session 1 sa; cache'i aşan bekleme context'i >10× fiyata yeniden yazar; polling iki kez ödenir; arka plan işi tek başına tasarruf etmez; tool çıktısı küçük kaldıraç; her always-loaded doküman session başına fatura; MCP katalogları her request'te ödenir; 200k'da compaction/hand-off; mekanik iş ucuz modele medium effort; review medium, riskliyse yukarı.

---

## 1) Yönetici özeti

Her madde bizim inancımıza karşı: **Doğrulandı / Çürütüldü / Kanıt yok**.

1. **"Sub-agent cache 5 dakika, ana session 1 saat" — doğru ama koşullu.** Claude Code TTL'yi request başına iki kovaya ayırır: ana konuşma ve "diğer her şey" (sub-agent, workflow, fork, compaction). Ana konuşma **yalnızca abonelikte ve plan dahilindeki kullanımda** 1 saat alır; usage credits'e geçince, API anahtarında ve bulut sağlayıcıda 5 dakikaya düşer. Sub-agent'lar abonelikte bile 5 dakika alır [4][3]. Bizim `experimental.cacheTtl: 1h` ayarı resmi olarak var (v2.1.248+), ama **usage credits kullanılırken yok sayılır**; önceliği daha yüksek olan `CLAUDE_CODE_SUBAGENT_PROMPT_CACHE_TTL` / `subagentPromptCacheTtl` ayarı kovanın tamamına uygulanır [4][5]. TTL, request'in **başından** ölçülür, cevabın bitişinden değil: 4 dakika süren bir yanıt 5 dakikalık cache'in 4 dakikasını yemiş olur [1]. → **Doğrulandı (abonelik, plan içi); usage credits/API'de Çürütüldü.**
2. **"Cache'i aşan bekleme context'i >10× fiyata yeniden yazar" — doğru, hatta eksik.** 5 dk yazma 1,25×, 1 sa yazma 2×, okuma 0,1× taban fiyat; Opus 5.5 ve Sonnet 5.5'te okuma 0,05×, Fable 5.1'de 0,025× [1][2]. Yani yeniden yazma/okuma oranı eski modellerde 12,5–20×, Opus/Sonnet 5.5'te 25–40×, Fable 5.1'de 50–80×. 1 saatlik yazma iki okumadan sonra kendini öder; 5 dakikalık yazma bir okumadan sonra [2]. → **Doğrulandı (5.5 modellerinde çarpan daha büyük).**
3. **"Polling iki kez ödenir" ve "arka plan işi tek başına tasarruf etmez" — mekanizma resmi, oranlar bize ait.** Claude Code her request'te tüm konuşmayı yeniden gönderir; "gün boyu açık bir session'da tek satırlık soru bile tüm konuşma için kullanım çeker"; cache ömründen uzun aradan sonraki ilk mesaj tüm context'i yeniden işler [3]. Sub-agent 5 dakikalık kovada olduğundan arka plana alınan 400 saniyelik iş yine cache'i öldürür [4]. Bizim %15 (poll turları) ve +%12 (arka plan tek başına) sayılarımızın dışarıda karşılığı yok. → **Mekanizma Doğrulandı; oranlar için dış Kanıt yok.**
4. **"Tool çıktısı küçük kaldıraç" — dolar için doğru, context kalitesi için eksik.** Claude Code zaten Bash çıktısını ~30.000 karakterde kesip dosyaya yazar [16], MCP çıktısını 25.000 token'da sınırlar [9]. Makale ölçümünde tool kaynaklı model maliyeti koşu maliyetinin %4–12'si ile sınırlı [44]. Ama Anthropic 10.000 satırlık logu hook ile yüzlerce token'a indirmeyi ilk sırada öneriyor [3] ve LangWatch 2.451 agent üzerinde "adım başına aktif context 6–8,5k token" olduğunu, maliyetin pencere boyutunun ~2,5. kuvvetiyle büyüdüğünü ölçtü [36]. Çıktı kesmek faturayı az, context'i çok etkiler. → **Doğrulandı (dolar), Kısmen çürütüldü (context büyümesi tool çıktısından gelir).**
5. **"Her always-loaded doküman session başına faturadır" — doğru ama bedel sanıldığından küçük ve sebep farklı.** Project context katmanı ilk request'te yazılır, sonra her turda 0,05–0,1× okunur [4][1]. Resmi rehber: CLAUDE.md dosya başına 200 satırın altında; "uzun dosyalar context tüketir ve uyumu düşürür" [8]; "şişkin CLAUDE.md gerçek talimatları yok saydırır" [17]. Yani gerçek bedel adherence, dolar değil. Ölçülmüş başlangıç context'i: 41–51k token, bunun 28,5k sistem araçları, 10,7k sistem prompt'u, ~4k auto-memory; CLAUDE.md sıfırdı [39]. → **Kısmen doğrulandı (bedel var, mekanizma ve büyüklük farklı).**
6. **"Always-loaded dokümanı session ortasında düzenlemek cache'i bozar" — Claude Code'da Çürütüldü.** Proje kökü ve kullanıcı CLAUDE.md'si session başında bir kez okunup bellekte tutulur; **session ortasındaki düzenleme cache'i bozmaz, ama uygulanmaz da**; yeni içerik `/clear`, `/compact` ya da yeniden başlatmada yüklenir [4]. Bizim "toplu doküman düzenlemesi ayrı task" kuralı tutarlılık için geçerli kalır, cache gerekçesi düşer. Cache'i gerçekten bozanlar: model değişimi, effort değişimi (5.5 modellerinde API/abonelikte artık bozmaz), fast mode, MCP sunucusu ekleme/çıkarma (tool search kapalıysa), tüm bir tool'u deny etmek, compaction, görsel birikimi, Claude Code yükseltmesi [4]. → **Çürütüldü.**
7. **"MCP katalogları her request'te ödenir" — Claude Code'da varsayılan olarak Çürütüldü, Codex'te Kanıt yok.** Claude Code tool search'ü varsayılan açar: yalnızca tool adları ve sunucu talimatları context'e girer, şemalar istendiğinde yüklenir [9][7]. Ölçüm: 69 MCP tool'u ile ilk request 20.819 token (deferred) vs 60.989 (hepsi yüklü); ilk koşu maliyeti 0,092 $ vs 0,613 $ [38]. Anthropic'in kendi ölçümü: 50+ tool için ~72k token → ~8,7k [32]. Tool search `ANTHROPIC_BASE_URL` gateway'de ve bazı sağlayıcılarda kapalı; o zaman eski kural geçerli [4][9]. Codex için deferred yükleme ayarı dokümante değil; MCP overhead sayıları yalnızca ikincil kaynaklardan [28][41]. → **Claude Code: Çürütüldü (varsayılanda). Codex: Kanıt yok.**
8. **"200k'da compaction/hand-off" — Doğrulandı, ölçülmüş optimum 220–250k.** Claude Code 1M modellerde varsayılan olarak ~967k'da compaction yapar; `/autocompact` 100k–1M arası ayarlanır [6]. LangWatch (287.748 API çağrısı, 873 compaction): maliyet ∝ pencere^2,55 (her ikiye katlama ~6×), maliyet modeli 220k, kapsama analizi 240k, görev tipine göre 250–450k öneriyor; pencereyi doldurup compaction 220k'da compaction'dan 2,3× kötü; compaction sonrası 5 adımda operatör düzeltmeleri %17,7 → %41,9 [36]. Chroma 18 modelde "girdi uzadıkça performans basit görevlerde bile düşer" [45]. Codex varsayılanı ham pencerenin ~%90'ı (272k'da 244.800) [46][28]. → **Doğrulandı; Claude Code'un kendi varsayılanı bizim çizgimizden çok yukarıda, bizimki kanıtla uyumlu.**
9. **"Mekanik iş ucuz modele medium effort" — Doğrulandı.** Claude Code'da Opus 5.5, Sonnet 5.5 ve Haiku 5.5 varsayılanı zaten `medium` [6]. Makale: Sonnet 5'te yalnızca effort düşürme billed maliyeti %74,7 azalttı, 15/15 başarı korundu; harness ayarı "ölçülen en büyük maliyet faktörü" [44]. Opus 4.5 medium effort, Sonnet 4.5'in SWE-bench skorunu %76 daha az output token'la tutturdu [33]. Uyarı: model geçişi cache'i sıfırdan kurar; 100k token içeride Opus'tan Haiku'ya geçmek Opus'un cevaplamasından pahalı, geçiş sub-agent ile yapılır [31]. → **Doğrulandı (model geçişi sub-agent sınırında).**
10. **"Review medium, riskliyse yukarı; gate review xhigh" — medium→high Doğrulandı, xhigh Kanıt yok/aleyhte.** SWE-bench Verified 25 görev: Sonnet 5 low 12 / high 19 / xhigh 17 çözüm; Opus 5 17 / 18 / 16; xhigh low'a göre 12–16k düşünme token'ı ve 23–30 tur ekleyip faturayı 2,4–4,5× artırdı; çözülmüş görev başına maliyet Opus 5'te 0,75 → 1,89 → 3,62 $; high vs low anlamlı (p=0,016), xhigh vs low değil [44]. Codex Astra 24 koşu: xhigh medium'un 1,76–2,52× token'ı, kalite kazancı gösterilemedi [37]. → **Çürütüldü (xhigh'ın gate review'da varsayılan olması için).**
11. **Codex: reasoning token'ları output olarak faturalanır; cached input %90–95 indirimli; abonelikte cache-write ücreti yok.** `reasoning.effort` değişimi cache'i bozar [24][25]. GPT-6.1 Sol 2 $ / 0,10 $ / 10 $ (input/cached/output), Luna 0,10 $ / 0,01 $ / 0,50 $, Astra 10 $ / 1 $ / 50 $ [23]. ChatGPT planında 5 saatlik pencerede yerel mesaj tahmini: Luna 350–3.000, Sol 6.1 15–160, Astra 5–45; bulut görevleri daha pahalı; yerel `/review` genel kotadan düşer [27][30]. Önbellek ömrü GPT-5.6+ için `prompt_cache_options.ttl: 30m` (minimum), eski modellerde 5–10 dk, 24 saate kadar uzatılabilir [24]. → **Doğrulandı; API cache-write ücreti konusunda sayfalar çelişkili (bkz. doğrulanamayanlar).**
12. **Abonelik kotası token ağırlığı: resmi formül yok.** Anthropic: kullanım "konuşmanın uzunluğu ve karmaşıklığı, özellikler, model ve effort" ile değişir; sayı yok [19]. Claude Code "prompt cache hit oranı abonelikler için daha cömert rate limit sağlıyor" diyor ama kotaya nasıl sayıldığını söylemiyor [31]. `/usage`, plan limitine sayılanların skill/subagent/plugin/MCP dağılımını ve "long context", "cache miss" bayraklarını (%10 eşik) gösterir [3]. Max'ın aylık 100/200 $ API kredisi Claude Code'da kullanılamaz [22]. → **Kanıt yok (ağırlık), ölçüm aracı var.**

---

## 2) Soru bazlı bulgular

### S1. Prompt cache mekaniği ve fiyatlandırma, bugün

**Claude API** [1][2] (R):
- Prefix eşleşmesi; sıra `tools → system → messages`; bir katmandaki değişiklik o katmanı ve sonrakileri bozar. Tool tanımı değişimi her şeyi bozar; `tool_choice`, görseller, thinking konfigürasyonu ve `output_config.effort` değişimi message katmanını bozar (effort'u modelin varsayılanına eşit açıkça yazmak bozmaz) [1].
- TTL 5 dk (varsayılan) ve 1 sa; her hit TTL'yi ücretsiz tazeler; süre request'in başından sayılır [1]. 1 saatlik girişler 5 dakikalıklardan önce gelmeli [1].
- En az önbelleklenebilir prefix: 512 token (Fable 5.1, Opus 5.5, Sonnet 5.5, Haiku 5.5, Opus 5, Sonnet 5), 1.024 (Opus 4.8, Sonnet 4.6), 4.096 (Opus 4.6, Haiku 4.5); kısa prompt sessizce cache'lenmez [1]. En fazla 4 breakpoint; otomatik caching bir slot kullanır [1].
- Paralel request'ler: cache girişi ilk yanıt **başladıktan** sonra kullanılabilir; paralel hit için ilk yanıtı bekle [1]. Claude Code workflow fan-out'u bu yüzden kardeş agent'ları 5 saniyeye kadar tutar [15].
- Cache organizasyonlar arasında, Claude API'de workspace'ler arasında izole; aynı model + prefix'li iki request aynı cache'i okur [1][4]. Model başına ayrı cache [4].
- Fiyatlar (USD/MTok, taban / 5m yazma / 1h yazma / okuma / output): Fable 5.1 10 / 12,5 / 20 / 0,25 / 50; Opus 5.5 4 / 5 / 8 / 0,20 / 20; Sonnet 5.5 2 / 2,5 / 4 / 0,10 / 10; Haiku 5.5 (≤100k prompt) 0,10 / 0,125 / 0,20 / 0,01 / 0,50, >100k'da 5× [2]. 1M context standart fiyat (Haiku 5.5 hariç) [2]. Batch %50 indirim, caching ile yığılır, batch içinde cache hit "best effort" %30–98 [2][18].
- Tool kullanımı sistem prompt'u 286 token (5.5 modelleri); computer toolset ~4.500, browser toolset ~6.600 token [2].

**Claude Code'un cache kullanımı** [4] (R):
- Katmanlar: sistem prompt'u + tool tanımları (tool seti değişince bozulur) → proje context'i (CLAUDE.md, auto memory, rules; session başı, `/clear`, `/compact`) → konuşma. Plan mode ve skill yüklemeleri mesaj olarak eklenir, prefix bozulmaz [4][31].
- TTL kovaları: ana konuşma abonelikte plan dahilinde 1 sa, aksi halde 5 dk; "diğer her şey" (sub-agent, workflow, teammate, fork, compaction, başlık üretimi) her durumda 5 dk; öncelik sırası `FORCE_PROMPT_CACHING_5M` → kovanın env var'ı → kovanın ayarı → sub-agent frontmatter `experimental.cacheTtl` (usage credits'te 1h yok sayılır) → `ENABLE_PROMPT_CACHING_1H` → kova varsayılanı [4]. Yazma TTL'si `usage.cache_creation.ephemeral_1h_input_tokens` / `ephemeral_5m_input_tokens` alanlarından doğrulanır [4]; `agent_cost.py` zaten bu alanları sayar.
- Cache kapsamı: sistem prompt'u auto-memory yollarını, konuşma başı çalışma dizini/platform/git durumunu içerir; **farklı dizinlerdeki iki session birbirinin cache'ini ıskalar**; aynı dizinde paralel session'lar paylaşır; ardışık session'lar yalnızca git snapshot'ı aynıysa [4]. Bizim worktree politikasında her worktree worker'ı kendi prefix'ini sıfırdan yazar.
- Cache'i bozmayanlar: repo dosyalarını düzenlemek, CLAUDE.md'yi session ortasında düzenlemek (uygulanmaz), izin modu değiştirmek, output style, skill/komut çağırmak, `/recap`, `/rewind` (önceki cache'e döner), sub-agent spawn etmek [4].
- Compaction: aynı prefix + özetleme talimatıyla ayrı request; cache sıcakken "context boyutunun ima ettiğinin küçük bir kısmına" mal olur; TTL geçtikten sonra tüm geçmiş uncached işlenir; en pahalı compaction eski session'ı resume edip compact etmektir [4][31]. Pro/Max'ta >100k token ve >1 saat aradan sonra "resume from summary" teklif edilir; hangi seçenek seçilirse seçilsin ilk request tüm geçmişi bir kez işler [14].
- Gözlem: `/usage` "Prompt cache (main)" satırı (v2.1.251+): request sayısı, cache'ten gelen input yüzdesi, miss sayısı ve muhtemel sebebi (v2.1.260+), sıcak/soğuk ve TTL; yalnızca ana konuşma, sub-agent'lar hariç [3].

**Abonelik kotası (Claude)** [19][20][21][22] (R): Pro/Max'ta 5 saatlik session limiti + haftalık limit (+ Fable için ayrı haftalık limit, Max'ta haftalık kotanın %50'sine kadar Fable); claude.ai, Claude Code ve IDE aynı havuzdan düşer; kullanım konuşma uzunluğu, araçlar, model ve effort ile değişir, sayı verilmez [19][20]. Usage credits "standart API fiyatlarıyla" faturalanır, aylık tavan/sınırsız seçilebilir [21]; Max'ın aylık 100/200 $ API kredisi interaktif Claude Code'da ve ek kullanımda geçmez [22]. Claude Code'daki dolar figürleri yerel, liste fiyatından tahmindir; aboneler için "faturalandırma açısından anlamsız" [3].

**OpenAI / Codex** [23][24][25][27][28][29][30] (R):
- API fiyatı (input / cached / output, USD/MTok, ≤272K): Astra 10 / 1 / 50; Sol 6.1 2 / 0,10 / 10; Sol 2 / 0,20 / 10; Luna 0,10 / 0,01 / 0,50; >272K'da 2×; Batch ve Flex %50; Fast 2×, Ultrafast 6× [23].
- Önbellek otomatik, prefix tabanlı, min 1.024 token; GPT-5.6+ için `prompt_cache_options.ttl: 30m` (minimum ömür), eski modellerde 5–10 dk, 1 saate kadar, `prompt_cache_retention: 24h` ile ~30 dk tipik/24 sa'ya kadar; `model`, `tools`, `reasoning.effort`, `text.verbosity` prefix'in parçası; cached token'lar TPM limitine sayılır [24]. Caching rehberi GPT-5.6+ için `cache_write_tokens` alanı ve 1,25× yazma çarpanından söz eder; fiyat sayfası yazma ücreti listelemez, Codex kredi faturalamasında "ayrı cache-write ücreti yok" [24][23][27].
- Reasoning token'ları output olarak faturalanır ve context'te yer kaplar; `max_output_tokens` reasoning'i de kapsar; deneye başlarken ≥25.000 token ayır; effort seviyeleri model bağımlı (`none…max`), GPT-6 ailesi varsayılanı `medium`; GPT-5.6+ önceki turların reasoning'ini varsayılan olarak yeniden render eder (`reasoning.context`), aynı model ailesinde [25].
- Codex planı: kredi oranları (kredi/MTok input / cached / output) Sol 6.1 50 / 2,5 / 250, Luna 2,5 / 0,25 / 12,5, Astra 250 / 25 / 1.250; "model seçimi, context, reasoning, tool kullanımı, retrieval ve caching kullanımı etkiler"; uzun session'lar "mesaj başına belirgin biçimde fazla" tüketir; Pro'da 5 saatlik limit yok; yerel review genel kotadan, GitHub review ayrı kotadan; `/status` kalan limitleri gösterir [27][30]. Topluluk, 5 saatlik pencerenin Temmuz 2026'da bazı planlarda kaldırıldığını bildiriyor, doğrulanmadı [50].
- Codex config: `model_reasoning_effort`, `model_auto_compact_token_limit` (ve `_scope`), `tool_output_token_limit`, MCP tool başına `output_token_limit`, `features.rollout_budget.limit_tokens` (token tavanı ve hatırlatma) [28]. `/status` context ve token kullanımı; `/usage` hesap token etkinliği; dolar yok [29]. Varsayılan auto-compact ham pencerenin %90'ı (272k'da 244.800; kullanılabilir %95'lik pencerenin %94,7'si) [46].

### S2. Ölçülmüş ve pratisyen tasarruf teknikleri

- **Başlangıç context'i.** Resmi simülasyonda sistem prompt'u ~4.200, auto memory ~680, ortam ~280, MCP (deferred) ~120, skill açıklamaları ~450, kullanıcı CLAUDE.md ~320, proje CLAUDE.md ~1.800 token [7]. Gerçek ölçüm (Sonnet 5, Ağustos 2026): 51.400 token; sistem araçları 28.500, sistem prompt'u 10.700, skill'ler 6.300, plugin'ler kapatılınca 45.600, auto-memory kapatılınca 41.400; CLAUDE.md yoktu [39]. Kullanıcının kontrolündeki pay ~10k.
- **CLAUDE.md uzunluğu.** Resmi: dosya başına <200 satır; `@import` organizasyon sağlar ama context düşürmez; yol kapsamlı `.claude/rules/` yalnızca eşleşen dosyada yüklenir; HTML yorumları context'e girmez [8]. "Her satır için: kaldırsam hata yapar mı?"; `/doctor` kesinti önerir [17]. 3.847 → 312 token'lık CLAUDE.md ile %91,9 context düşüşü iddiası ikincil ve doğrulanamadı [51] (S). Auto-memory ilk 200 satır / 25 KB [8].
- **Skill/plugin on demand.** Skill açıklamaları her session yüklenir, gövde çağrılınca; `disable-model-invocation: true` olan skill'ler listeye bile girmez; compaction sonrası çağrılan skill gövdeleri 5.000 token'a kadar yeniden eklenir, liste eklenmez [7]. Plugin skill/komut/agent/hook etkinleştirmek cache'i bozmaz (sona eklenir), plugin MCP sunucusu bozar [4].
- **Sub-agent context izolasyonu.** Her sub-agent kendi context'i, kendi sistem prompt'u (Claude Code'un sistem prompt'u değil), CLAUDE.md'yi yükler (Explore/Plan hariç; `omitClaudeMd` ile kapanır), auto-memory'yi yüklemez; kendi cache'ini kurar, 5 dk kovada; fork ise ebeveynin cache'ini okur ve "aynı context'i gerektiren işte taze sub-agent'tan ucuzdur" [5][4]. Çok sayıda sub-agent'ın uzun raporu ana context'i doldurur [5]. Anthropic'in araştırma sistemi: agent chat'in ~4×, çok-agent ~15× token; token kullanımı performans varyansının %80'ini açıklıyor [34]. Sub-agent ana context'e 1–2k token'lık özet döndürmeli [35].
- **Context bütçesi pratikleri.** Resmi: "context doldukça performans düşer", `/clear` görevler arası, iki düzeltmeden sonra `/clear`, `/btw` ile context'e girmeyen soru, `/compact` doğal molada [17][3]. Ölçüm: compaction sonrası düzeltme oranı iki kattan fazla [36]; 18 modelde uzunlukla düşüş [45]. Sabit bir "%40/%60" kuralı için kaynak bulunamadı; eşikler %30–40 (benchmark) ile %70–80 (vendor blog) arasında dağınık [S].
- **Tool çıktısı.** Claude Code Bash: inline ~30.000 karakter, fazlası dosyaya + 2.000 karakter önizleme, `bashOutputMaxChars` 128.000'e kadar; başarısız komutta 10.000; arka plan komutu 30 dk, en fazla 2 sa [16]. MCP: 10.000 token'da uyarı, 25.000'de dosyaya [9]. PreToolUse hook ile test çıktısını yalnızca hatalara indirgeme örneği resmi [3]. Programmatic tool calling 43.588 → 27.297 token (−%37) [32].
- **Worktree ve paralellik.** Agent teams ~7× token (plan mode'da), her teammate kendi penceresi, CLAUDE.md+MCP+skill'leri otomatik yükler [3]. Workflow'lar: 25 agent ya da 1,5M token projeksiyonunda "Large workflow" uyarısı; fan-out'ta eş prefix'li agent'lar ilk agent'ın cache'ini okur (5 s bekletme) [15]. Cache dizin kapsamlı olduğundan farklı worktree'lerdeki session'lar prefix paylaşmaz [4].
- **Uzun ömürlü worker.** Resmi: "uzun session'da kullanım artar" — tam geçmiş her request'te, cache miss aradan sonra, zamanlanmış görevler/cross-session mesajlar/goal check-in'leri boşta bile tam context gönderir (goal check-in'i prompt başına 3 ile sınırlı, v2.1.246+) [3]. Codex: `rollout_budget` ile token tavanı [28].
- **Hook ile kırpma.** Yukarıdaki PreToolUse örneği [3]; hook çıktısı `additionalContext` ile girer, exit 2 stderr'i modele verir [7].
- **Model routing.** Resmi: Sonnet çoğu iş, Opus mimari/çok adımlı; sub-agent'a `model: haiku`; Opus'a geçiş miras alan sub-agent'lara da uygulanır [3]. Codex: Luna/Sol/Astra API fiyat oranı 1 : 20 : 100 (input) [23]; plan mesaj tahmini Luna 350–3.000 vs Sol 15–160 [27]. Model geçişi = cache sıfırlama; `opusplan` her plan-mode geçişinde cache sıfırlar [4][31].
- **Effort.** Claude Code 5.5 modelleri varsayılan `medium`; kullanılmayan seviye bir altına düşer; 5.5 ve Fable 5.1'de API/abonelikte effort değişimi cache'i korur (Bedrock/Vertex/gateway'de korumaz) [6][4]. Ölçüm: effort-only arm −%74,7 maliyet, 15/15 başarı [44]; SWE-bench'te xhigh high'ı geçmedi [44]; Codex Astra xhigh 1,76–2,52× medium, 14 → 25–38 dk; Reddit'teki "xhigh kota tasarrufu" iddiası 122 vs 65 yanıt (daha az tur, daha az geçmiş yeniden okuma) ile açıklandı, genellenemez [37]. Blog tabloları (xhigh 3–5×, Ultra 12–20×) kaynaksız [40][41] (S).
- **Batch/async.** Claude ve OpenAI batch %50, 24 sa; interaktif session'larda batch yok (Managed Agents dahil) [2][18][26]. Kit'in etkileşimli worker'larına uygulanamaz.
- **Response uzunluğu.** Thinking output olarak faturalanır, 5.5/Fable'da kapatılamaz, yalnızca effort ile düşer [3][6]. Output faturanın küçük payı (bizim ölçüm ~%3, `docs/worker-cost-setups.md`).
- **Yeniden okumayı önleme.** Düzenlenen dosya için `<system-reminder>` eklenir, geçmişteki okuma değişmez [4]; compaction sonrası en son değiştirilen 5 dosya yeniden okunur [7][35]; code intelligence plugin'i "go to definition" ile grep+çoklu okuma yerine geçer [3].
- **Cache-aware sıralama.** Statik önce, değişken sona; timestamp'i sistem prompt'una koymak, tool sırasını karıştırmak, Agent tool parametrelerini değiştirmek geçmişte cache'i kırdı [31]. OpenAI: aynı ilke [24].
- **Session yeniden kullanım vs taze.** Resume: değişmemiş prefix TTL içindeyse cache'ten okunur; Claude Code yükseltmesi ya da farklı `--append-system-prompt` prompt'u değiştirir [4]. Taze session: başlangıç context'i yeniden yazılır (bizim ölçüm ~49–60k). Resmi öneri: yön değişince `/clear` ("bedava"), devam ederken `/compact` [3].
- **Compaction eşiği.** Claude Code 1M modellerde ~967k; Codex ~%90 ham pencere; ölçülmüş optimum 220–250k [6][46][36].

### S3. Bizim inançlar kanıta karşı

| İnanç | Durum | Dayanak |
|---|---|---|
| Sub-agent 5 dk, ana session 1 sa | Doğrulandı, abonelik ve plan içi; usage credits/API'de ana session da 5 dk | [4][3][5] |
| 1 sa cache abonelikte sub-agent'a `experimental.cacheTtl` ile verilir | Doğrulandı (v2.1.248+), usage credits'te yok sayılır; kova ayarı `subagentPromptCacheTtl` önceliklidir | [4][5] |
| Cache sub-agent çağrıları arasında geçerli mi | Hayır: her sub-agent kendi prefix'i; fork ebeveyni okur; resume edilen sub-agent ilk koşunun cache'ini okuyabilir; fan-out'ta eş kardeşler paylaşır | [4][15] |
| Bekleme > TTL → >10× yeniden yazma | Doğrulandı; 5.5'te 25–40×, Fable 5.1'de 50–80× | [1][2] |
| Polling iki kez ödenir | Mekanizma doğrulandı; %15 oranı yalnızca bizim ölçümümüz | [3][4] |
| Arka plan işi tek başına tasarruf etmez | Mekanizma doğrulandı (5 dk kova); +%12 bizim | [4] |
| Tool çıktısı küçük kaldıraç | Dolar için doğrulandı (%4–12); context için kısmen çürütüldü | [44][36][3] |
| Her always-loaded doküman session başına fatura | Kısmen; yazma bir kez, okuma 0,05–0,1×; gerçek bedel adherence | [4][8][17] |
| Session ortası doküman düzenlemesi cache'i bozar | Çürütüldü (uygulanmaz, bozmaz) | [4] |
| MCP katalogu her request'te ödenir | Claude Code varsayılanında çürütüldü; gateway/BASE_URL'de ve Codex'te kanıt yok | [9][38][28] |
| 200k'da compaction/hand-off | Doğrulandı (220–250k ölçülmüş optimum) | [36][6] |
| Mekanik iş ucuz model + medium | Doğrulandı | [3][6][44][33] |
| Review medium, riskli high | Doğrulandı | [44] |
| Gate review xhigh | Çürütüldü (çözüm artmadı, maliyet 2,4–4,5×) | [44][37] |
| Lead effort/modeli task sınırında değiştirir (cache) | Model için doğru; effort için 5.5/Fable 5.1 API-abonelikte artık gereksiz | [4] |
| Codex reasoning token'ları cached input ile etkileşir | Reasoning output'tur, cache'e girmez; effort değişimi prefix'i bozar; önceki tur reasoning'i GPT-5.6+'da render edilir | [25][24] |

### S4. Araçlar: ne ölçer, nerede yanılır

- **Claude Code `/usage` (`/cost` ve `/stats` alias)**: session token/dolar (yerel, liste fiyatı, `modelPricing` ile sözleşme fiyatı), "Prompt cache (main)" satırı, plan kullanım çubukları, skill/subagent/plugin/MCP attribution (v2.1.222 öncesi MCP payı abartılıydı), davranış bayrakları (%10 eşik), loop satırları; `/clear` sıfırlar (v2.1.211 öncesi birikiyordu); diğer cihazlar hariç [3][13]. `/context` context dağılımı; `/status` sürüm/model/hesap [13]. `/insights` davranış raporu, token harcar [3].
- **`claude -p --output-format json`**: `total_cost_usd` ve model bazlı dağılım; `--continue/--resume` ile session toplamı (v2.1.277+); `--max-budget-usd` arka plan işini de durdurur; **tahmin**, fatura değil [12][11]. SDK: `usage` sub-agent'ları saymaz, `total_cost_usd`/`modelUsage` sayar; assistant mesajındaki `output_tokens` placeholder'dır, gerçek sayı result'ta [11]. Bizim `agent_cost.py`'nin requestId başına en büyük output'u alması bu placeholder'ı kısmen telafi eder; `usage.input_tokens` placeholder'ı (#28197) ve her content block'ta tekrarlanan usage nesnesi (#87303, v2.1.233'te düzeltildi) transkript tabanlı sayımı etkileyebilir [48][49] (F). Transkript formatı "iç, sürümler arasında değişir" [14].
- **OpenTelemetry**: `claude_code.cost.usage` (USD, tahmin), `claude_code.token.usage` (type: input/output/cacheRead/cacheCreation; input cache'i dışlar), `api_request` olayında `cost_usd`, cache token'ları, `effort`, `speed`, `query_source` (main/subagent/auxiliary), `agent.name`; `OTEL_LOG_TOOL_DETAILS` olmadan isimler maskelenir; her sağlayıcıda çalışır, "gerçek zamanlı kullanıcı başı metrik" için tek seçenek [10][3].
- **ccusage**: yerel JSONL'den; cost modları `auto`/`calculate`/`display`; fiyat LiteLLM + models.dev; 1h cache yazması 2× input; TTL ayrımı yoksa standart cache-creation fiyatı; "maliyetler tahmindir", web search gibi ek ücretler yok [42]. Topluluk iddiaları çelişkili: sub-agent dosyalarını atlayıp %77–94 eksik sayma [53] (S) vs resume/rewind kopyaları yüzünden %30–70 fazla sayma [54] (S); ikisi de doğrulanamadı.
- **Codex `/status` ve `/usage`**: context yüzdesi ve kalan limit; hesap token etkinliği; dolar yok [29][27]. Gösterilen pencere ile compaction kararındaki pencere farklı olabilir [46][F].
- **Kesin fatura**: Claude Console Usage sayfası / Usage and Cost API; Codex için chatgpt.com usage sayfası (API sayfası abonelik tüketimini göstermez) [3][11][S].

---

## 3) Karşılaştırma tablosu: bizim pratik vs kanıt

| Boyut | Bizim kit | Kanıt |
|---|---|---|
| Worker cache ömrü | `worker.md` frontmatter `experimental.cacheTtl: 1h` | Doğru alan; usage credits'te yok sayılır; kova ayarı `CLAUDE_CODE_SUBAGENT_PROMPT_CACHE_TTL=1h` her sub-agent/workflow'a uygulanır ve öncelik sırasında üsttedir [4][5] |
| Lead session cache | 1 sa varsayılıyor | Yalnızca abonelik plan içi; usage credits'te `promptCacheTtl: 1h` yazılmazsa 5 dk [4] |
| Bekleme/poll kuralı | Worker poll yapmaz, iş arka planda, re-invoke | Resmi mekanizma aynı; Claude Code `Monitor` ve arka plan komutu var; `-p` koşusu arka plan işini 10 dk bekler [16][12] |
| Worker boyutu | ≤150 request, `maxTurns` | Resmi: `maxTurns` kısmi sonuçla durdurur, resume mümkün [5]; LangWatch: pencere büyüdükçe maliyet ^2,5 [36] |
| Fix turu taze worker'a | Her tur taze worker | Resume edilen sub-agent ilk koşunun cache'ini okuyabilir; fork taze'den ucuz [4][5]; bizim 377 request'lik resume ölçümü aleyhte |
| Always-loaded doküman | Küçük ve sabit; session ortası düzenleme yasak (cache) | <200 satır doğru [8]; cache gerekçesi yanlış [4] |
| MCP | Varsayılan RED, owner onayı | Claude Code'da deferred; gerçek bedel 120 token + çağrılınca şema; gateway'de eski bedel [7][9][4]; CLI araçları yine "daha verimli" [3] |
| Compaction eşiği | 200k'da uyarı, compact ya da hand-off | Ölçülmüş optimum 220–250k [36]; compact sıcakken 0,1×, soğukken tam [4] |
| Model/effort tablosu | Luna/Haiku medium; Sol/Opus high; gate xhigh | medium varsayılan [6]; high > low anlamlı; xhigh kazanç yok [44][37] |
| Model/effort geçişi | Yalnızca task sınırında | Model: doğru; effort: 5.5/Fable 5.1'de serbest [4] |
| Worktree paralelliği | Bağımsız modüller için | Her worktree ayrı cache prefix'i [4]; teams 7×, multi-agent 15× [3][34] |
| Rapor uzunluğu | ~350 kelime | Sub-agent özeti 1–2k token [35] |
| Ölçüm | `agent_cost.py` gün sonu | `/usage` cache satırı + attribution; OTel; `-p` JSON `total_cost_usd`; hepsi tahmin [3][10][12] |
| Batch | Yok | Etkileşimli session'da yok [2][18] |

---

## 4) Nicel veri tablosu

| Metrik | Değer | Kaynak | Tür |
|---|---|---|---|
| Cache yazma / okuma çarpanı | 5m 1,25×, 1h 2×, okuma 0,1× (5.5'te 0,05×, Fable 5.1'de 0,025×) | [1][2] | R |
| Opus 5.5 / Sonnet 5.5 / Haiku 5.5 / Fable 5.1 input-output | 4/20, 2/10, 0,10/0,50, 10/50 $/MTok | [2] | R |
| GPT-6 Astra / 6.1 Sol / Luna input-cached-output | 10/1/50, 2/0,10/10, 0,10/0,01/0,50 $/MTok | [23] | R |
| Codex plan mesaj tahmini (5 sa) | Astra 5–45, Sol 6.1 15–160, Luna 350–3.000 | [27] | R |
| Min. cache prefix | 512 token (5.5, Fable 5.1) | [1] | R |
| OpenAI cache | min 1.024 token; GPT-5.6+ ttl 30m; eski 5–10 dk, 24h opsiyon | [24] | R |
| Claude Code TTL kovaları | ana 1h (abonelik plan içi) / 5m; diğer 5m | [4] | R |
| Resume-from-summary teklifi | >100k token ve >~1 sa boşta (Pro/Max) | [14] | R |
| Auto-compact varsayılanı | Claude Code ~967k (1M modeller); Codex ~%90 ham pencere (244.800/272.000) | [6][46] | R / F |
| Başlangıç context'i (ölçüm) | 51.400 → 41.400 token; sistem araçları 28.500, sistem prompt'u 10.700 | [39] | B |
| Başlangıç context'i (resmi simülasyon) | ~7.850 token (sistem 4.200, proje CLAUDE.md 1.800, MCP 120, skill 450) | [7] | R |
| CLAUDE.md önerisi | <200 satır; auto-memory 200 satır/25 KB | [8] | R |
| Tool search etkisi | 69 tool: 20.819 vs 60.989 token; 0,092 vs 0,613 $ ilk koşu | [38] | B/F |
| Tool search (Anthropic) | ~72k → ~8,7k token; MCP eval Opus 4.5 %79,5 → %88,1 | [32] | B |
| 7 MCP sunucusu | 67,3k token (%33,7 / 200k) | [47] | F |
| Bash çıktı sınırı | ~30.000 karakter inline, dosyaya; MCP 25.000 token | [16][9] | R |
| Tool kaynaklı model maliyeti | koşunun %4–12'si | [44] | P |
| Gereksiz doğrulama | 1 seviye 1,48×, 2 seviye 2,36×, 3+ 18,25× medyan maliyet | [44] | P |
| Effort (Sonnet 5, 15 koşu) | effort-only −%74,7 maliyet, 15/15 başarı; full −%82,2 | [44] | P |
| Effort (SWE-bench 25) | Sonnet 5 çözüm 12/19/17, $/çözüm 1,76/2,32/3,00; Opus 5 17/18/16, 0,75/1,89/3,62; xhigh +12–16k thinking, +23–30 tur, 2,4–4,5× | [44] | P |
| Caching'in faturaya etkisi (makale ana benchmark) | fatura ≈ cache'siz gerçeğin %39'u (−%61) | [44] | P |
| Harness farkı | Claude Code vs PI.DEV: 12–15× sabit prefix, 2–7× tur, 5–30× $/başarı | [44] | P |
| Codex Astra effort (24 koşu) | xhigh 1,76–2,52× medium token; 14 → 25/38 dk | [37] | B |
| Opus 4.5 medium effort | Sonnet 4.5 SWE-bench'i %76 daha az output token'la | [33] | B |
| Context maliyet eğrisi | ∝ pencere^2,55; optimum 220–250k; compaction sonrası düzeltme %17,7 → %41,9 | [36] | B (ölçülü, n=1 müh.) |
| Agent / multi-agent token | chat'in ~4× / ~15×; teams ~7× | [34][3] | B / R |
| Programmatic tool calling | 43.588 → 27.297 token (−%37) | [32] | B |
| Workflow uyarı eşiği | >25 agent ya da >1,5M token; fan-out cache bekletme 5 s | [15] | R |
| Kurumsal ortalama | ~13 $/geliştirici/aktif gün, 150–250 $/ay, %90'ı <30 $/gün | [3] | R |
| Arka plan token tüketimi | tipik <0,04 $/session | [3] | R |
| Bizim ölçüm | 336 $/11 sa, %87 worker; 1h cache −36–38 %; 5 dk altı parçalama −52 % (100k context) | `docs/worker-cost-setups.md` | kit |

---

## 5) Uygulanabilir tasarruf adayları (beklenen tasarrufa göre)

**A. Worker cache ömrünü kova düzeyinde ayarla, frontmatter'a güvenme.** `CLAUDE_CODE_SUBAGENT_PROMPT_CACHE_TTL=1h` (ya da `subagentPromptCacheTtl`) öncelik sırasında frontmatter'ın üstünde ve workflow/fork/compaction kovasının tamamını kapsar; sub-agent frontmatter'ı usage credits'te yok sayılır [4][5]. Her worker koşusundan sonra `ephemeral_1h_input_tokens` doğrulaması zaten `agent_cost.py`'de. Beklenen: bizim ölçümümüz −36–38 % worker maliyeti (`docs/worker-cost-setups.md`), yalnızca 5 dakikayı aşan bekleme olan worker'larda; kısa worker'larda 1h yazma 2× olduğundan zarar [4]. Risk: usage credits döneminde 1h yazması gerçek para; lead 5 dakikadan kısa işlerde 5m'ye döner.

**B. Gate review effort'unu xhigh'dan high'a indir; medium'u varsayılan tut.** Kanıt: xhigh çözüm sayısını artırmadı, maliyeti 2,4–4,5× artırdı; high vs low anlamlı [44]; Codex xhigh 1,76–2,52× [37]. Beklenen: tier-3 review turlarında ~2× tasarruf. Risk: edge-case recall'u düşebilir; `docs/research/ai-review-workflows.md` bulgu 2 (reviewer gürültüsü) bunu dengeliyor. Model routing kural 4 (ikinci kirli turda effort yükselt) kalır: "kanıt tetikli yükseltme" makalede %64–68 görevde devreye girdi ve çalıştı [44].

**C. Lead session cache'ini usage credits'te koru.** Plan limiti dolunca Claude Code ana konuşmayı sessizce 5 dakikaya düşürür [4]; lead worker bekleyen bir session olduğundan `promptCacheTtl: 1h` yazılmalı; `/usage` "Prompt cache (main)" satırı sıcak/soğuk durumu gösterir [3]. Beklenen: lead'in aradan sonraki tam yeniden yazmalarını (bizim ölçümde lead ~250k/request okuma) önler. Risk: kısa, sık session'larda 2× yazma.

**D. Kompaksiyon politikasını kanıta çek.** 200k çizgisi doğru [36]; ekle: compact yalnızca cache sıcakken (TTL içinde) [4]; >1 sa aradan sonra resume'da "summary" seçeneğini kabul et [14]; yön değişince `/clear` + hand-off (bedava) [3]; Codex worker'larında `model_auto_compact_token_limit` ≈ 200–250k [28][46]. Beklenen: compaction başına tam context okuma (bizim ölçekte 300–700k uncached) kaçınılır.

**E. Model/effort geçiş kuralını güncelle.** Model geçişi task sınırında kalır (cache ayrı) [4][31]; effort geçişi Opus/Sonnet/Haiku 5.5 ve Fable 5.1'de API/abonelikte cache'i korur, kural gereksiz kısıt [4]. Codex'te `reasoning.effort` değişimi prefix'i bozar, kural orada kalır [24]. Tasarruf: küçük, ama lead'in bir review turu için effort yükseltmesinin bedeli kalkar.

**F. "Session ortasında always-loaded doküman düzenlenmez (cache)" gerekçesini düzelt.** Düzenleme cache'i bozmaz, uygulanmaz [4]. Kural tutarlılık gerekçesiyle kalsın, metin düzelsin; `docs/context-is-a-budget.md`'deki "bir satırlık açıklama cache'e mal olur" cümlesi yanlış. Tasarruf: sıfır; yanlış inanç gider.

**G. Worktree worker'larında prefix bedelini say.** Her worktree kendi cache prefix'ini yazar; ardışık session'lar git snapshot'ı aynıysa paylaşır [4]. Aynı context'i gerektiren kısa işler için fork taze sub-agent'tan ucuz [5]; eş prefix'li paralel worker'ları ilk yanıttan sonra başlat (workflow'un 5 s bekletmesi) [15][1]. Beklenen: worker başına bir başlangıç yazması (bizim ölçümde 36–60k × 1,25–2×). Risk: fork ebeveynin tüm geçmişini taşır, büyük lead'de pahalı.

**H. MCP kuralını Claude Code gerçeğine göre yumuşat, gateway istisnasını yaz.** Varsayılanda bedel tool adı + sunucu talimatı; şema çağrılınca [9][7]. `ANTHROPIC_BASE_URL`/gateway ya da Codex'te eski bedel geçerli [4][28]. Owner onayı kuralı kalır (plugin MCP sunucusu cache'i bozar [4]); "her request'te katalog" iddiası düzelir. Tasarruf: sıfır; CLI tercihi yine resmi öneri [3].

**I. Mekanik Codex işlerini Luna'ya, yerel review'u da kotadan say.** Luna Sol'un 1/20 fiyatı ve ~20× mesaj [23][27]; yerel `/review` genel kotadan düşer, GitHub review ayrı [27][30]. Zaten tier 1'de; eksik olan `/status` ile kota çekimini ölçmek (WORKFLOW kural 6). Tasarruf: kota, dolar değil.

**J. Ölçümü iki kaynağa bağla.** `agent_cost.py` transkriptten; eksikleri: placeholder usage alanları [48][49], format değişkenliği [14], sub-agent `usage` dışlanması [11]. Her worker `-p` koşusunun `total_cost_usd` + `modelUsage`'ını rapor dosyasına yazsın [12]; lead gün sonunda `/usage` attribution ve cache satırını not etsin [3]. Tasarruf: doğrudan yok; yanlış routing kararını önler.

**K. Tool çıktısı: var olan sınırlara güven, bir hook ekle.** Bash 30k / MCP 25k sınırları zaten var [16][9]; test koşularına PreToolUse filtre hook'u (resmi örnek) [3]. Beklenen: dolar <%12 [44]; context büyümesi ve compaction sıklığı düşer [36].

**Reddedilenler:** Batch API (etkileşimli session yok [2][18]); ccusage (tahmin, çelişkili doğruluk iddiaları [42][53][54]); "xhigh kota tasarrufu" (açıklandı, genellenmez [37]); keep-alive/poll plugin'leri (poll = tam context okuma [3]).

---

## 6) Kaynaklar

Format: [n] Başlık — URL — tarih — tür.

1. Claude API — Prompt caching — https://platform.claude.com/docs/en/build-with-claude/prompt-caching — 2026 — R
2. Claude API — Pricing — https://platform.claude.com/docs/en/about-claude/pricing — 2026 — R
3. Claude Code — Manage costs effectively — https://code.claude.com/docs/en/costs — 2026 — R
4. Claude Code — How Claude Code uses prompt caching — https://code.claude.com/docs/en/prompt-caching — 2026 — R
5. Claude Code — Subagents — https://code.claude.com/docs/en/sub-agents — 2026 — R
6. Claude Code — Model configuration (effort, auto-compact, 1M) — https://code.claude.com/docs/en/model-config — 2026 — R
7. Claude Code — Explore the context window — https://code.claude.com/docs/en/context-window — 2026 — R
8. Claude Code — How Claude remembers your project (CLAUDE.md, rules, auto memory) — https://code.claude.com/docs/en/memory — 2026 — R
9. Claude Code — MCP (tool search, output limits) — https://code.claude.com/docs/en/mcp — 2026 — R
10. Claude Code — Monitor usage (OpenTelemetry) — https://code.claude.com/docs/en/monitoring-usage — 2026 — R
11. Claude Agent SDK — Track cost and usage — https://code.claude.com/docs/en/agent-sdk/cost-tracking — 2026 — R
12. Claude Code — Run Claude Code programmatically (`-p`, budget) — https://code.claude.com/docs/en/headless — 2026 — R
13. Claude Code — Commands — https://code.claude.com/docs/en/commands — 2026 — R
14. Claude Code — Manage sessions (resume from a summary) — https://code.claude.com/docs/en/sessions — 2026 — R
15. Claude Code — Dynamic workflows (cost, fan-out caching) — https://code.claude.com/docs/en/workflows — 2026 — R
16. Claude Code — Tools reference (Bash output limits, background) — https://code.claude.com/docs/en/tools-reference — 2026 — R
17. Claude Code — Best practices — https://code.claude.com/docs/en/best-practices — 2026 — R
18. Claude API — Batch processing — https://platform.claude.com/docs/en/build-with-claude/batch-processing — 2026 — R
19. Claude Help — How do usage and length limits work? — https://support.claude.com/en/articles/11647753-how-do-usage-and-length-limits-work — 2026 — R
20. Claude Help — Use Claude Code with your Pro or Max plan — https://support.claude.com/en/articles/11145838-use-claude-code-with-your-pro-or-max-plan — 2026 — R
21. Claude Help — Manage usage credits for paid Claude plans — https://support.claude.com/en/articles/12429409-manage-usage-credits-for-paid-claude-plans — 2026 — R
22. Claude Help — Monthly API credits for Max and Team plans — https://support.claude.com/en/articles/17154008-monthly-api-credits-for-max-and-team-plans — 2026 — R
23. OpenAI — API pricing — https://developers.openai.com/api/docs/pricing — 2026 — R
24. OpenAI — Prompt caching guide — https://developers.openai.com/api/docs/guides/prompt-caching — 2026 — R
25. OpenAI — Reasoning models guide — https://developers.openai.com/api/docs/guides/reasoning — 2026 — R
26. OpenAI — Batch API guide — https://developers.openai.com/api/docs/guides/batch — 2026 — R
27. OpenAI Codex — Pricing and usage limits — https://learn.chatgpt.com/docs/pricing — 2026 — R
28. OpenAI Codex — Configuration reference — https://learn.chatgpt.com/docs/config-file/config-reference — 2026 — R
29. OpenAI Codex — Slash commands (`/status`, `/usage`, `/compact`) — https://learn.chatgpt.com/docs/cli/slash-commands — 2026 — R
30. OpenAI Help — Using Codex with your ChatGPT plan — https://help.openai.com/en/articles/11369540-using-codex-with-your-chatgpt-plan — 2026 — R (sayfa 403 verdi; alıntılar arama özetinden)
31. Thariq Shihipar (Anthropic) — Lessons from building Claude Code: Prompt caching is everything — https://claude.dev/blog/lessons-from-building-claude-code-prompt-caching-is-everything/ — 2026-04-30 — B
32. Anthropic — Introducing advanced tool use (tool search, programmatic tool calling) — https://www.anthropic.com/engineering/advanced-tool-use — 2025-11-24 — B
33. Anthropic — Introducing Claude Opus 4.5 (effort parameter) — https://www.anthropic.com/news/claude-opus-4-5 — 2025-11-24 — B
34. Anthropic — How we built our multi-agent research system — https://www.anthropic.com/engineering/multi-agent-research-system — 2025-06-13 — B
35. Anthropic — Effective context engineering for AI agents — https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents — 2025-09-29 — B
36. Rogerio Chaves (LangWatch) — Finding the optimal context window for coding agents — https://langwatch.ai/research/finding-the-optimal-context-window — 2026-08-02 — B (ölçülü; tek mühendis, tek harness)
37. Trilogy AI — Astra reasoning effort: does xhigh use fewer tokens than medium? — https://trilogyai.substack.com/p/astra-reasoning-effort-token-usage — 2026 — B (ölçülü, n=24)
38. rulestack — Tool search hid 40,170 tokens from our first request — https://dev.to/rulestack/tool-search-hid-40170-tokens-from-our-first-request-auto5-put-them-all-back-2jin — 2026-09-11 — B/F (ölçülü, v2.1.263)
39. XDA Developers — Claude Code was using 51,000 tokens before I even typed a prompt — https://www.xda-developers.com/claude-code-using-fifty-thousand-tokens-before-typed-prompt-fixed-it/ — 2026-08-28 — B (ölçülü)
40. Daniel Vaughan — The Ultra mode trade-off (Codex reasoning budgets) — https://codex.danielvaughan.com/2026/07/24/codex-cli-ultra-mode-trade-off-reasoning-budgets-subagent-cost-task-routing/ — 2026-07-24 — S (tablolar kaynaksız)
41. Daniel Vaughan — Codex CLI performance optimisation: token overhead — https://codex.danielvaughan.com/2026/04/08/codex-cli-performance-optimization/ — 2026-04-08 — S
42. ccusage — Guide ve Cost calculation modes — https://ccusage.com/guide/ ; https://ccusage.com/guide/cost-modes — 2026 — R (araç dokümanı)
43. badlogic — Context compaction research: Claude Code, Codex CLI, OpenCode, Amp (gist) — https://gist.github.com/badlogic/cd2ef65b0697c4dbe2d13fbecb0a0a5f — 2025-12-02 — F
44. Weinberger & Hozez — Prompt-Induced Waste in Coding Agents: Reasoning, Effort, Harness Design, and End-to-End Cost — https://arxiv.org/abs/2608.01347 — 2026-08 (v6 2026-09-10) — P (preprint)
45. Hong, Troynikov, Huber (Chroma) — Context Rot: How Increasing Input Tokens Impacts LLM Performance — https://www.trychroma.com/research/context-rot — 2025-07-14 — B/P (teknik rapor, 18 model)
46. openai/codex issue #40095 — Default auto-compaction waits until 94.7% of usable context — https://github.com/openai/codex/issues/40095 — 2026-08-22 — F
47. anthropics/claude-code issue #11364 — MCP tool definitions consume 67.3k tokens — https://github.com/anthropics/claude-code/issues/11364 — 2025-11-10 — F
48. anthropics/claude-code issue #87303 — transcript repeats the full usage object for every content block — https://github.com/anthropics/claude-code/issues/87303 — 2026 — F (arama özetinden)
49. anthropics/claude-code issues #28197, #27361 — JSONL `usage` placeholder değerleri, output_tokens loglanmıyor — https://github.com/anthropics/claude-code/issues/28197 ; https://github.com/anthropics/claude-code/issues/27361 — 2026 — F (arama özetinden)
50. OpenAI Developer Community — Has the 5-hour usage session been removed from Codex CLI? — https://community.openai.com/t/has-the-5-hour-usage-session-been-removed-from-codex-cli/1387701 — 2026-07 — F
51. Firecrawl — 12 ways to cut token consumption in Claude Code (3.847→312 token CLAUDE.md iddiası) — https://www.firecrawl.dev/blog/claude-code-token-efficiency — 2026 — S
52. getunblocked — GitHub MCP token cost: a 2026 autopsy — https://getunblocked.com/blog/github-mcp-token-cost/ — 2026 — S
53. tdimino — claude-code-minoan `claude-usage` skill (ccusage %77–94 eksik sayma iddiası) — https://skills.sh/tdimino/claude-code-minoan/claude-usage — 2026 — S
54. claude-tokens (PyPI) — ccusage %30–70 fazla sayma iddiası — https://pypi.org/project/claude-tokens/0.2.0/ — 2026 — S (sayfa yüklenemedi; arama özetinden)
55. oldeucryptoboi — How tool search defers tools to save tokens (147 tool: ~90k → ~15k) — https://oldeucryptoboi.substack.com/p/tool-search-deep-dive — 2026 — F
56. bestagent.dev — How big can your CLAUDE.md get before it hurts performance? — https://bestagent.dev/claude-md-size-performance-2026/ — 2026 — S (hesap, ölçüm değil)

### Doğrulanamayanlar

- Abonelik kotasında token/model/cache ağırlıklandırması: hiçbir resmi sayfa formül vermiyor [19][20][27]; "cache hit'ler kotaya daha az sayılır" iddiasının resmi dayanağı yalnızca [31]'deki dolaylı cümle.
- OpenAI API'de GPT-5.6+ cache-write ücreti: caching rehberi 1,25× ve `cache_write_tokens`'tan söz ediyor [24], fiyat sayfası yazma kalemi listelemiyor [23], Codex kredi faturalamasında "ayrı cache-write ücreti yok" [27]. Fatura görmeden karar verilemez.
- Codex'te sub-agent frontmatter dışı 1h TTL eşdeğeri, MCP şema erteleme ve Codex `/status` penceresinin compaction penceresiyle ilişkisi [28][46].
- Codex 5 saatlik pencerenin kaldırılıp kaldırılmadığı (Temmuz 2026 topluluk raporu vs Ağustos 2026 rehberler) [50].
- ccusage doğruluk yönü ve büyüklüğü (eksik mi fazla mı) [53][54].
- Blog tabloları: xhigh 3–5×, Ultra 12–20×, sub-agent 3,6×/6–12× çarpanları [40][41]; Firecrawl %91,9 CLAUDE.md iddiası [51]; "Mart 2026'da caching bug'ı 10–20× token şişirdi" iddiası (birincil kaynak yok).
- help.openai.com Codex planı makalesi doğrudan okunamadı (403); içerik arama özetinden [30].
- Bizim kit ölçümlerinin (polling %15, arka plan +%12, 1h cache −36–38 %) dış tekrarı yok; mekanizma resmi dokümanla uyumlu ama sayılar yalnızca bize ait.
