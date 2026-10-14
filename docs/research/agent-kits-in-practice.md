<!-- RESEARCH: how comparable agent-development kits are used in practice, what they do differently from this kit, and what token-saving practices they measured. Companion to docs/research/ai-review-workflows.md (review loops). Owner decides what, if anything, becomes a proposal. 2026-10-13. -->

# Agent geliştirme kit'leri pratikte (2025–2026): kanıta dayalı araştırma raporu

Tarih: 2026-10-13. Kapsam: karşılaştırılabilir "agent development kit"lerin ve çerçevelerin (obra/superpowers, BMAD-METHOD, GitHub Spec Kit, OpenSpec, claude-flow/Ruflo, Ralph loop, Aider architect/editor, Cursor rules/subagents, Anthropic'in Claude Code rehberliği, OpenAI Codex rehberliği ve "harness engineering", Amp, Devin/Cognition, Willison'ın pattern rehberi, Stripe/Ramp/Uber/HumanLayer iç kit'leri) günlük kullanımı; bizim kit'ten farkları; token optimizasyonu ve ölçülmüş sonuçlar. Kaynak numaraları `[n]`, tam liste bölüm 7'de. Güvenilirlik etiketi: **R** (resmi doküman / proje deposu), **P** (makale/teknik rapor), **B** (mühendislik blogu / vendor), **F** (forum / issue / anekdot), **S** (ikincil aktarım; birincil doğrulanamadı). "Ölçüldü" = yöntemi belirtilen bir koşudan çıkan sayı; "iddia" = yöntemsiz vendor/yazar sayısı.

Değerlendirilen bağlam ("bizim kit", MyAgentKit): lead session planlar ve brief yazar; worker'lar (Claude Code session'ı, sub-agent ya da tmux/Windows Terminal'de Codex CLI) git worktree'de uygular; çapraz-vendor review gate'i (Codex Claude'un işini, Claude Codex'inkini, throwaway kopyada); kanonik `AGENTS.md` + `docs/STATE.md` + `PHASES.md` + `PROJECT.md` + `ARCHITECTURE.md`; `scripts/check.sh` pre-commit'e bağlı; bütçeye göre yönlendiren yedi adlı çalışma modu; prompt-cache ömrü üstüne kurulu maliyet modeli (sub-agent 5 dk, session 1 sa). Her session'ın okuduğu set: `AGENTS.md` (228 satır, 14,8 kB) + `PHASES.md` + `STATE.md` + `ARCHITECTURE.md` + hedef klasörün `AGENTS.md`'si; `WORKFLOW.md` (1.054 satır, 72,6 kB) lead tarafından bölüm bölüm.

---

## 1) Yönetici özeti

Her madde: **Doğrulandı / Çürütüldü / Kanıt yok** = gözlenen pratik bizim yöntemi destekliyor mu?

1. **Tek kanonik, kısa, "harita" niteliğinde talimat dosyası.** Üç vendor aynı şeyi söylüyor: Anthropic "CLAUDE.md dosya başına 200 satırın altında hedefle; uzun dosya context tüketir ve uyumu düşürür" [1][3]; OpenAI'nin kendi harness ekibi `AGENTS.md`'yi "ansiklopedi değil içindekiler tablosu, yaklaşık 100 satır" yapıyor [23]; Codex `project_doc_max_bytes` ile 32 KiB'de kesiyor [20]; Cursor kural dosyasını 500 satırla sınırlıyor [25]. Hakemli kanıt iki yönlü: geliştirici yazımı AGENTS.md ile medyan koşu süresi −%28,6, çıktı token −%16,6 [64]; ama ETH çalışmasında context dosyaları başarıyı genelde artırmıyor, maliyeti ortalama +%20 artırıyor, "repo özeti" bölümleri işe yaramıyor, yalnızca "kod tabanından türetilemeyen özel talimatlar" değer taşıyor [63]. Bizim `AGENTS.md` 228 satır ve her session'da ayrıca `ARCHITECTURE.md` + `PHASES.md` + `STATE.md` yükleniyor; "pointer, kopya değil" ilkesi sektörle örtüşüyor, boyut disiplini sektörün üst sınırında. → **Doğrulandı (ilke), kısmen çürütüldü (ARCHITECTURE.md gibi türetilebilir içeriğin her session yüklenmesi).**
2. **Lead/worker ayrımı, worktree'de tek uygulayıcı, paralellik yalnızca bağımsız iş için.** superpowers "asla birden fazla implementation subagent'ı paralel gönderme" [28]; Cognition 2026 revizyonu "çok agent zekâ katar ama yazma tek thread'de kalır; paralel-yazar sürüleri benimsenmedi" [54]; Huntley'nin Ralph'ında build/test için tek agent "back pressure" [42]; Anthropic Writer/Reviewer'ı ayrı session'da, `/batch`'i worktree başına bir subagent'la öneriyor [2]; Stripe Blueprints deterministik ve agentic düğümleri sıralı bir state machine'de [59]. → **Doğrulandı.**
3. **Çapraz-vendor review gate'i (Codex↔Claude).** Hiçbir kit, rehber ya da iç sistem iki vendor'ı tek review döngüsünde kullanmıyor; "multi-model" her yerde kademe demek (ucuz uygulayıcı, güçlü reviewer: superpowers tur 4'te model yükseltir [28]; Cognition "smart friend" eskalasyonu [54]; Aider architect/editor [47]). Willison Claude Code ve Codex'i yan yana ama ayrı işlerde koşturuyor [58]. Değeri önceki rapor ele aldı; burada yalnızca yaygınlık sorusu var. → **Kanıt yok (emsal yok); bize özgü.**
4. **Deterministik gate pre-commit'te, prose kural yerine.** Anthropic: hook'lar "deterministik", CLAUDE.md "tavsiye niteliğinde" [2]; OpenAI harness ekibi mimariyi "Codex'in yazdığı özel linter'lar ve yapısal testlerle mekanik olarak" zorluyor, insan review'u isteğe bağlı [23]; Stripe lint push'ta 1–5 sn [59]; Huntley "statik analiz ve tip kontrolü olmadan sonuçların şenlik ateşi" [42]; Spec Kit anayasasında gate'ler var ama metin ("Complexity Tracking" ile gerekçelendirilebilir) [33]; OpenSpec `verify` ve `archive` "uyarır ama bloklamaz" [36]. Bizim "gate kırmızı görülmeden bitmiş sayılmaz" kuralı hiçbir kitte yok. → **Doğrulandı; "proven red" bize özgü.**
5. **Session'lar arası durum dosyada, chat'te değil; biten iş silinir.** Ralph `fix_plan.md` + "AGENT.md'ye durum raporu YAZMA" [42]; superpowers plan + ledger ("conversation memory compaction'ı atlatamaz") [28]; OpenSpec `tasks.md` checkbox'ları ile kaldığı yerden devam [36]; HumanLayer "her fazdan sonra durumu plan dosyasına geri sıkıştır" [62]; OpenAI `docs/exec-plans/{active,completed}` + `tech-debt-tracker.md` + bayat doküman için "doc-gardening" agent'ı [23]; Amp handoff = model taslak yazar, insan düzenler [50][73]. `Done:` trailer'ıyla **zorunlu** silme hiçbir kitte yok; BMAD'de ticket insan "done" diyene kadar `built` kalıyor [31]. → **Doğrulandı (dosya tabanlı durum); zorunlu silme bize özgü.**
6. **Maliyet modeli prompt-cache ömrü üstüne.** Resmi rakamlar bizim modelle örtüşüyor: 5 dk cache yazma 1,25×, 1 sa yazma 2×, okuma 0,1× (5.5 modellerde 0,05×, Fable 5.1'de 0,025×) [5]; sub-agent/teammate/fork/compaction istekleri abonelikte bile 5 dk'da, ana konuşma 1 sa'da; `subagentPromptCacheTtl`/`experimental.cacheTtl: 1h` ile uzatılır, usage credit'te 1h yok sayılır [4][7]. Claude Code ekibi "cache hit oranını uptime gibi izle, düşünce SEV aç" diyor [12]. Tek kullanıcı ölçümü: üç session'da geçmişin yeniden okunması faturanın %39–65'i [70]. Hiçbir OSS kit maliyeti cache ömrüyle modellemiyor. → **Doğrulandı (mekanizma resmi); modelleme bize özgü.**
7. **Sub-agent vs session ekonomisi: kısa, çıktısı gürültülü iş sub-agent'a; uzun iş ayrı session'a.** Anthropic: sub-agent kendi token'ını harcar, değeri ana context'i temiz tutmak; "on binlerce" token harcayıp 1.000–2.000 token özet döner [7][13]; fork ana cache'i okuduğu için aynı context'li iş için daha ucuz [4]; agent teams "yaklaşık 7× token" [3]; çok-agent araştırma sistemi chat'in 15× token'ı ve "çoğu kodlama işi için uygun değil" [14]; Cursor "5 paralel subagent ≈ 5× token", 2–3 öneriliyor [26]. Willison "subagent'ın asıl değeri kök context'i korumak" [57]. → **Doğrulandı.**
8. **Tool çıktısını kısaltmak küçük kaldıraç; fatura input/cache okumalarıyla belirlenir.** JetBrains'in bağımsız benchmark'ı: RTK düşük effort'ta **+%7,6 daha pahalı** (p=0,004), yüksek effort'ta ±0, kalite aynı; aynı koşularda `rtk gain` "96,2 M token tasarruf" yazdı [67]; Caveman: ilan %65, ölçülen çıktı tasarrufu %8,5, toplam maliyet tersine döndü [68]; projenin kendi dürüst sayfası "faturanın çoğu input ve cache yeniden okuması, çıktı stiline dokunmaz" [69]; SWE-bench'te 8 frontier model: maliyeti input token'ları sürüyor, aynı görevde koşular arası 30× fark [66]. Bizim "tool çıktısı sorun değil, hijyen" ölçümü [kit]. → **Doğrulandı.**
9. **MCP kataloğu gerçek sabit maliyet; ama Claude Code artık varsayılan olarak erteliyor.** Beş sunuculu tipik kurulum ~55k token, tool search ile >%85 azalma [18]; Anthropic iç ölçümü 77k→8,7k [16]; Cursor A/B: yalnızca tool adlarını statik tutmak toplam token'ı −%46,9 [27]. Claude Code'da tool search varsayılan: başlangıçta yalnızca adlar, şemalar isteğe bağlı; `ENABLE_TOOL_SEARCH=auto` eşik %10 [9][11]. Bizim "MCP sunucusu bağımlılık gibi onay ister" kuralı yerinde ama gerekçesi (her istekte tam şema) Claude Code için artık eski; Codex ve diğer host'lar için geçerli. → **Doğrulandı (maliyet), kural gerekçesi güncellenmeli.**
10. **Model/effort yönlendirmesi kademeyle.** Anthropic: Sonnet varsayılan, Opus mimari için, basit sub-agent'a `model: haiku` [3]; Opus 4.5 medium effort Sonnet 4.5'in en iyi SWE-bench skorunu %76 daha az çıktı token'ıyla yakalıyor (vendor) [19]; Codex rehberi effort'u iş türüne göre başlatıyor, xhigh yalnızca "uzun, agentic, reasoning-ağır" iş için [21]; Aider polyglot: R1 architect + Sonnet editor %64 / 13,29 $ vs o1 tek başına %61,7 / 186,5 $ [48]. Hiçbir kaynak **abonelik kıtlığına** göre (bizim "scarcity, not capability") yönlendirmiyor; herkes API fiyatı ya da kaliteyle yönlendiriyor. → **Doğrulandı (kademe); kıtlık temelli yönlendirme için Kanıt yok.**
11. **Adlı çalışma modları.** En yakın emsal Amp'in dört modu (`low/medium/high/ultra` = model + effort + system prompt + tool seti paketi) [50]; bütçeye göre "kim yazar, kim review eder, kim fix'ler" seçen yedi mod hiçbir yerde yok. → **Kanıt yok; bize özgü.**
12. **Spec/plan önce — ama küçük işte seremoni maliyeti ölçülmüş.** Eberhardt (Copilot + Sonnet 4.5): Spec Kit ile 689 satır kod için 2.577 satır markdown, 33,5 dk agent + 3,5 sa insan review; aynı işi iteratif 8 dk agent + 24 dk insan, "~10× hızlı, niteliksel kazanç görmedim" [34]; uvik (vendor, doğrulanamadı): 3 dosyanın altında spec rework'ten pahalı, 6+ dosyada spec merge oranını %50→%80 çıkarıyor [39]; superpowers #743: "2 satır için 20 dakika, 4 saatlik limitin %75'i" (18 raporcu, yanıt yok) [29]; BMAD tek feature ~200 $ ve 6 gün [32]. Bizim "bir cümlede anlatılabilen iş plan atlar" ve "yeni mekanizma = bir sayfa tasarım" eşiği bu kanıtla uyumlu. → **Doğrulandı (eşikli).**
13. **Fix döngüsü sınırlı ve eskalasyonlu.** superpowers: en fazla 5 tur, tur 1–3 aynı uygulayıcı, tur 4–5 daha güçlü modelde taze uygulayıcı, sonra controller karar verir; minör bulgular "döngüye hiç girmez" [28]; Stripe CI "çoğunlukla bir, en fazla iki tur" sonra insana [59]; Claude Code `/goal` kendi beyanı değil kanıt kontrol eder [43][46]. Bizim "ikinci kirli turdan sonra bir kademe yukarı" kuralı superpowers'la aynı şekil; "temiz olana kadar" kısmı önceki raporda çürütüldü. → **Doğrulandı (eskalasyon).**
14. **Handoff/compaction eşiği.** `/clear` bedava, `/compact` tam prefix isteği (cache sıcakken ucuz, soğukken tam fiyat) [3][4]; HumanLayer %40–60 doluluk [62]; Ball ~100k'da "erken talimatları unutmaya başlıyor" [51]; Willison "benchmark'lar 200k altında daha iyi" [57]; Chroma 18 modelde uzunlukla tutarlı bozulma [65]. Claude Code'un otomatik compaction'ı 1M pencerede ~967k'da [10]; yani bizim 200k hook'u araçtan katı, pratisyenlerle aynı bantta. → **Doğrulandı.**
15. **Kit'li iş akışı vs ad-hoc için ölçülmüş sonuç.** Kontrollü karşılaştırma yok. ETH [63] ve Lulla [64] yalnızca talimat dosyasının etkisini ölçüyor; uvik tek vendor sayfası ve koşu tarihi gelecekte [39]; METR RCT'si AI izinli işte %19 yavaşlama (n=16) [71]; Anthropic kurumsal telemetrisi geliştirici başına günde ~13 $, %90'ı 30 $ altında [3]. Belgelenmiş başarısızlıklar: claude-flow'un 300+ MCP tool'unun ~%97'si stub, token sayan kod yok [41]; Anthropic'in ralph-wiggum plugin'i aynı session'da biriktirdiği için "amacını ıskalıyor" [44][45]; Spec Kit "sea of markdown" [34][38]. → **Kanıt yok (kit vs ad-hoc); başarısızlıklar belgelenmiş.**

---

## 2) Kit bazlı bulgular

Her alt bölümde: ne tutuyor · session nasıl başlıyor · iş nasıl bölünüyor · durum nasıl taşınıyor · review nasıl · neyi reddediyor · ölçülmüş sayı.

### 2.1 Anthropic — Claude Code resmi rehberliği [1][2][3][4][6][7][8][9][10][11][12][13]

- **Tutulan:** `CLAUDE.md` (proje, kullanıcı, yönetilen), `.claude/rules/*.md` (path-scoped, yalnızca eşleşen dosyaya dokununca yüklenir), `@import` (en fazla 4 atlama; import "context maliyetini azaltmaz, hepsi başlangıçta yüklenir"), auto memory (`MEMORY.md`, ilk 200 satır ya da 25 KB), skills (açıklama her zaman context'te, gövde çağrılınca; açıklama+when_to_use 1.536 karakterde kesilir; SKILL.md 500 satır altı; compaction sonrası yeniden eklenen skill'ler 5k/skill, toplam 25k), subagent tanımları (`.claude/agents/`), hook'lar, plugin'ler. `AGENTS.md` doğrudan okunur (v2.1.277+) ya da `@AGENTS.md` ile import.
- **Session başı (resmi simülasyon değerleri):** system prompt 4.200 token, auto memory 680, ortam 280, MCP tool adları 120, skill açıklamaları 450, kullanıcı CLAUDE.md 320, proje CLAUDE.md 1.800 [11]. Sub-agent kendi system prompt'u + CLAUDE.md hiyerarşisi + git snapshot'ıyla başlar; Explore/Plan ajanları CLAUDE.md'yi atlar; `omitClaudeMd: true` ile kapatılır [7].
- **İş bölümü:** explore → plan → implement → commit; "diff'i bir cümlede anlatabiliyorsan planı atla"; büyük feature için interview → `SPEC.md` → **temiz session'da uygulama**; Writer/Reviewer iki ayrı session; `/batch` 5–30 subagent, her biri kendi worktree'sinde; agent teams deneysel, varsayılan kapalı, "3–5 teammate ile başla", "önce daha hafif seçeneği dene" [2][8].
- **Durum:** CLAUDE.md + auto memory + session resume (`--resume`, uzun aradan sonra "özetten devam" teklifi) + compaction (mimari kararlar, çözülmemiş bug'lar, son 5 dosya korunur) [13].
- **Review:** `/code-review` taze subagent; adversarial review "yalnızca diff ve kriterleri görür"; uyarı: "boşluk bulması istenen reviewer iş sağlam olsa da bulur; her bulgunun peşine düşmek over-engineering" [2].
- **Reddettikleri (tasarım kararı):** system prompt'u session ortasında değiştirmek (plan mode bir tool, timestamp yok), tool'ları session ortasında çıkarmak (deferred stub), modeli session ortasında değiştirmek (bunun yerine Haiku subagent'a handoff), compaction'ı farklı prompt'la koşmak [12].
- **Ölçülmüş:** kurumsal ortalama ~13 $/gün/geliştirici, 150–250 $/ay, %90'ı <30 $/gün; arka plan <0,04 $/session; agent teams ~7× (yöntem yok) [3]; çok-agent araştırma: agent chat'in ~4×, çok-agent ~15×; BrowseComp'ta token kullanımı varyansın %80'ini açıklıyor [14]; MCP tool tanımları 77k→8,7k, Opus 4.5 MCP eval'i %79,5→%88,1 tool search ile [16].

### 2.2 OpenAI — Codex rehberliği ve "harness engineering" [20][21][22][23][24]

- **Tutulan:** `AGENTS.md` zinciri (global `~/.codex/AGENTS.md`, proje kökünden cwd'ye bir dosya/klasör, yakın olan üstün; `AGENTS.override.md`), toplam **32 KiB** sınırı (`project_doc_max_bytes`), skills (`.agents/skills`, context payı varsayılan pencerenin %2'si, en fazla 10k token), `tool_output_token_limit`, `features.multi_agent` varsayılan açık, `features.rollout_budget` (token limiti, her %10'da hatırlatma), `features.memories` varsayılan kapalı [20][22].
- **Session başı:** talimat zinciri session başına bir kez kurulur, önbellek yok, düzenleme için yeniden başlat [20]. "Kısa ve doğru bir AGENTS.md uzun ve belirsiz kurallarla dolu dosyadan yararlıdır"; "temel kurallarla başla, tekrarlayan hatadan sonra kural ekle; aynı hata ikinci kez olunca retrospektif iste ve AGENTS.md'yi güncelle" [21].
- **İş bölümü (OpenAI harness ekibi, 2026-02):** üç mühendis + Codex, beş ayda ~1 M satır, ~1.500 PR, "insanlar doğrudan hiç kod yazmadı", mühendis başına günde 3,5 PR; tek Codex koşusu 6+ saat [23]. `AGENTS.md` ~100 satır içindekiler tablosu; `ARCHITECTURE.md`, `docs/design-docs`, `docs/exec-plans/{active,completed,tech-debt-tracker.md}`, `docs/generated/db-schema.md`, `docs/product-specs` [23].
- **Durum:** exec-plan dosyaları + "doc-gardening" agent'ı bayat dokümana fix-up PR açıyor; "garbage collection" refactor PR'ları "bir dakikanın altında review edilip automerge" [23].
- **Review:** Codex self-review, sonra "lokal ve cloud'da ek agent review'ları, tüm agent reviewer'lar tatmin olana kadar döngü"; **asıl gate** özel linter'lar + yapısal testler + "taste invariants" (dosya boyutu, yapılandırılmış log); "insanlar review edebilir, zorunlu değil"; darboğaz "insan QA kapasitesi" [23]. Codex rehberi: `code_review.md` AGENTS.md'den referanslı; "OpenAI'de Codex PR'ların %100'ünü review eder" (öz-bildirim) [21].
- **Reddettikleri:** "monolitik manuel bayat kural mezarlığına döner" [23]; "bir proje için tek chat şişmiş context ve giderek kötü sonuç verir; tutarlı iş birimi başına bir chat" [21].
- **Ölçülmüş:** yukarıdaki PR/LOC sayıları öz-bildirim (B). Cache: GPT-5.6+ okuma 0,1× (Sol 0,05×), yazma 1,25×, yalnızca 30 dk TTL; önceki modeller 5–10 dk bellek ya da 24 sa saklama [24].

### 2.3 Cursor — rules / subagents / dynamic context [25][26][27]

- **Tutulan:** `.cursor/rules/*.mdc` (Always / Apply Intelligently / glob / Manual), **500 satır sınırı**, "stil rehberini kopyalama, linter kullan", "Agent aynı hatayı tekrarlayınca kural ekle"; `AGENTS.md` kök ve iç içe; subagent tanımları `.cursor/agents/`, `.claude/agents/`, `.codex/agents/` ile birlikte çalışır; `model: claude-opus-5[effort=high]` [25][26].
- **İş bölümü:** subagent temiz context'le başlar, ebeveyn gerekli her şeyi geçirir; worktree ya da cloud VM izolasyonu; "5 paralel subagent ≈ 5× token", öneri 2–3 odaklı subagent, ~2.000 kelimelik subagent prompt'u anti-pattern [26]; `/multitask` kuyruktaki istekleri async subagent'lara dağıtır [S].
- **Ölçülmüş (vendor A/B):** uzun tool çıktısını dosyaya yazıp `tail`'letmek, chat geçmişini dosya olarak referanslamak, skill ve MCP'den yalnızca adları statik tutmak: MCP çağıran koşularda toplam token **−%46,9**, "yüklü MCP sayısına göre yüksek varyans" [27].

### 2.4 obra/superpowers [28][29][30]

- **Tutulan:** 15 skill (TDD, systematic-debugging, verification-before-completion, brainstorming, writing-plans, executing-plans, subagent-driven-development, using-git-worktrees, requesting/receiving-code-review…). Bellek dosyası yok; CLAUDE.md/AGENTS.md üstüne biner. Deterministik gate yok; "gate"ler todo'ya dönüşen prose checklist.
- **Session başı:** SessionStart hook'u ~750 kelimelik bootstrap enjekte eder ("2k token'dan küçük bir doküman", Vincent); compaction sonrası yeniden enjekte (host desteklerse). Kural: "bir skill uygulanıyorsa SEÇİMİN YOK, KULLANMAK ZORUNDASIN".
- **İş bölümü:** brainstorming → worktree → plan ("2–5 dakikalık, tam path'li görevler") → ya her görev için taze subagent + görev başına review (en kapsamlı) ya da aynı session'da uygulayıp branch sonunda tek review (en ucuz). SDD'de controller asla uygulamaz, bulguları kendi düzeltmez, **birden fazla implementation subagent'ı paralel göndermez**, subagent'a plan dosyasının tamamını okutmaz; artefact'lar **dosya yolu** olarak geçer ("yapıştırılan içerik session boyunca context'te kalır"); uygulayıcı yalnızca durum döner (DONE / DONE_WITH_CONCERNS / NEEDS_CONTEXT / BLOCKED).
- **Durum:** plan dosyası + plan başına ledger + brief/rapor dosyaları + git.
- **Review:** görev başına bir reviewer (spec uyumu + kalite tek geçişte); fix döngüsü **5 turla sınırlı** (1–3 aynı uygulayıcı, 4–5 güçlü modelde taze uygulayıcı, yalnızca fix diff'i yeniden review), 5'ten sonra controller karar verir ve park eder; minör bulgular döngüye girmez; branch sonunda en güçlü modelde bir final review → bir fix subagent → bir scoped re-review. Tek vendor.
- **Reddettikleri:** test öncesi yazılan kodu siler; worker'ın kendi reviewer'ını spawn etmesi yok; dispatch'te model belirtilmemesi "model seçimini sessizce bozar".
- **Ölçülmüş / iddia:** v6 "wall-clock −%50, token −%60" (release yazısı erişilemedi, ikincil kaynaklar 50/50 ve 50/60 diye çelişiyor → iddia); Willison'ın deneyi: 5 alt görevde subagent başına 50k+ token çünkü ortak context tekrarlanıyor [30]; **issue #743** (Mar–Ağu 2026, 18 raporcu, root cause yok): "2 satır için 20 dk, 4 saatlik limitin %75'i, fix yine yanlış"; "CRUD endpoint 35 dk vs düz Claude Code 2 dk"; Codex 5 saatlik kotasında "tek görev" [29]; HN: tek satırlık değişiklik ~1 saat; "en yüksek PR başı maliyetli ekip bunu körlemesine benimsemişti" [30].

### 2.5 BMAD-METHOD [31][32][39]

- **Tutulan (v6.12):** 12+ persona (PM, Architect, Developer, UX, Scrum Master…), "Party Mode"; skill'ler `bmad`, `bmad-build`, `bmad-spec`, `bmad-project-context`, `bmad-build-auto`; çıktı ağacı `_bmad-output/initiative-*/intent-*/`, epic başına `tickets.toml`, `plan-*.md`, `deferred-work.md`. Eski "sharding ile %90 token tasarrufu" iddiası v6 README'sinde yok.
- **Session başı:** build başına "taze chat"; her zaman yüklenen context'in boyutu belirtilmiyor.
- **İş bölümü:** tek döngü; üç kontrol (niyet boşluğu, geri alınamaz aksiyon, ayak izi) temizse "hafif yol" (plan + uygulama tek session), aksi halde onaylı yazılı plan; session başına ~500 LOC; `bmad-build-auto` tek ticket, subagent yoksa "blocked".
- **Durum:** plan dosyaları, ticket durumu (`built`; "bmad-build asla done işaretlemez", insan işaretler), deferred-work, git; kurtarma `git revert HEAD`.
- **Review:** "bağımsız reviewer'lar", tur sayısı yok, tek vendor; Test Architect ücretli eklenti.
- **Ölçülmüş:** Kdosha (Cursor + Sonnet 4.5, bir backend feature): ~200 $, 6 gün, "okuması pahalı, bitirmesi yavaş" (rakip araç geliştiricisi) [32]; Gurgui: ilk kod satırından önce 12–16 saat, party mode "context'i ve kredileri bitirdi" [32]; uvik: spec fazı 227k token (%43,9), merge'e 55 dk, 4,23 $/merged ticket — en pahalı kol [39]. "31.667 token/run", "847 $/ay", "230 M token/hafta" sayıları birincil kaynaksız (S).

### 2.6 GitHub Spec Kit [33][34][35][38][39]

- **Tutulan:** `specify` CLI; `/speckit-constitution|specify|plan|tasks|implement|converge`, isteğe bağlı clarify/checklist/analyze; bug ve assess uzantıları ("SDD feature akışı önkoşul değil"). Anayasa: Library-First, CLI zorunlu, Test-First "pazarlıksız", en fazla 3 proje, Anti-Abstraction, Integration-First; başarısız gate "Complexity Tracking"te gerekçelendirilir.
- **İş bölümü:** `tasks.md`'de `[P]` paralel görevler; worker rolü ya da worktree yok; "implement → converge, Converged diyene kadar".
- **Durum:** feature branch'inde markdown; yarım kalan implement'i nasıl sürdüreceği sorusu (issue #1193) 180 gün yanıtsız kalıp bot tarafından kapatıldı [35].
- **Review:** insan her artefact'ı okur; analyze/checklist isteğe bağlı; multi-model yok.
- **Ölçülmüş (Eberhardt, Copilot + Sonnet 4.5):** feature 1: agent 33,5 dk, 689 LOC, **2.577 satır markdown**, 3,5 saat insan review, uygulama çalışmadı; artım 2: 23,5 dk, ~300 LOC, 2.262 satır md, ~2 saat review; aynı iş iteratif: 8 dk agent, ~1.000 LOC, 0 md, 15 dk review + 9 dk test → "~10× hızlı, niteliksel fayda görmedim; saf haliyle uygulanabilir bir süreç değil" [34]. uvik: spec 147k token (%34), 18 dk ek, %80 merge, 3,33 $/ticket [39].

### 2.7 OpenSpec [36][37][38][39]

- **Tutulan:** `openspec/specs/` (mevcut gerçek) + `openspec/changes/<ad>/{proposal,design,tasks,specs/…}`; delta formatı `## ADDED|MODIFIED|REMOVED Requirements`, en az bir `#### Scenario` (WHEN/THEN); komutlar `/opsx:explore|propose|apply|archive` (+ expanded profil); düz markdown + YAML, "MCP yok, API anahtarı yok", 30+ tool için üretilmiş talimat dosyası.
- **İş bölümü:** rol, subagent, worktree yok; "artefact'lar faz değil aksiyon"; küçük/orta iş için `new → ff → apply → verify → archive`.
- **Durum:** change klasörü; `tasks.md` checkbox'larıyla resume; archive deltaları spec'e birleştirir.
- **Review:** apply öncesi insan; `verify` ve `archive` "uyarır, bloklamaz". Hiçbir şey zorlanmıyor. "Typo/tek satır için atla" kuralı resmi değil, topluluk skill'inde (folklor).
- **Ölçülmüş:** Rails karşılaştırması ~250 satır artefact (OpenSpec) vs ~800 (Spec Kit) [37]; uvik en iyi kol: %84 merge, 105k spec token (%28,3), 12 dk ek, 36 dk merge, 2,71 $/ticket [39]. Yönetişim: ~54k yıldız, en üst katkıcı 504 commit vs ikinci insan 3 → bus factor 1 [37].

### 2.8 claude-flow / Ruflo [40][41]

- **İddia:** "100+ agent", "314 MCP tool", 27 hook, Queen-led hiyerarşi (Raft/Byzantine/Gossip), HNSW bellek, cost-tracker plugin.
- **Bağımsız denetim (v3.5.51, issue #1513, maintainer yanıtı yok):** 300+ MCP tool'un ~290'ı (%97) yürütme arka ucu olmayan stub; `agent_spawn` Map'e `status: "idle"` yazar, LLM çağırmaz; tüm konsensüs türleri aynı JSON handler'a gider; `verifySignature()` her zaman true; `neural_train` %93,6 doğruluk raporlar, her tahmin "coder"; "ReasoningBank −%32 token" sabit 1000 baseline; "352× hızlı" baseline `sleep(352)`; **pakette token sayan kod yok**; tool tanımları + tekrarlı enjeksiyon session başına ~15–25k token ek yük [41]. Discussion #1666 kabul edilen yanıt: "anlamlı iyileşme yok, kaldırdım" [41]. 12,5 M npm indirmesi kullanım değil kurulum sayısı.
- **Ders:** vendor sayfalarındaki "%84,8 SWE-bench / −%32,3 token" sayıları bugünkü README'de yok; "cost-tracker" varlığı ölçüm demek değil.

### 2.9 Ralph loop ve Anthropic'in ralph-wiggum plugin'i [42][43][44][45][46]

- **Huntley'nin Ralph'ı:** `while :; do cat PROMPT.md | claude-code; done`; `PROMPT.md` (her döngüde aynı), `specs/` (dosya başına bir spec), `fix_plan.md` ("en önemli 10 şeyi seç, BİRİNİ yap"), `AGENT.md` (build/test adımları + öğrenilenler; "durum raporu YAZMA"), git. Her döngü taze context; "stack'i deterministik ayırma"; ~170k pencere, olabildiğince az kullan. Alt-agent yalnızca döngü içinde; Rust build/test için 1 ("back pressure"). Reddettikleri: placeholder uygulama; aramadan "yok" varsayma; mevcut kod tabanında kullanma ("greenfield only"). Zayıf nokta: tekrarlı implementasyonlar [42].
- **Plugin:** Stop hook aynı session içinde aynı prompt'u yeniden besler; `--max-iterations` varsayılan sınırsız ("birincil güvenlik mekanizman"); `--completion-promise` tam string eşleşmesi [43]. Eleştiri: Horthy "amacı ıskalıyor: işi bağımsız context pencerelerine bölmek" [44]; Pocock: 3 iterasyonda %20→%35→%50 context, "3–4 iterasyondan sonra tamamen dumb zone'da" (eşik iddia) [45]; d4hines: "trust the process" ifadesini model "dürüstlük taahhüdünün silahlandırılması" saydı; Haziran 2026'da Claude Code `/goal` ekledi: "kendi beyanı yerine tamamlanma kanıtını kontrol eder" [46].
- **Ölçülmüş / iddia:** "50k $'lık sözleşme 297 $'a" tek ekran görüntüsü, aynı 297 $ başka projeye de atfediliyor → folklor [42][44]; Horthy'nin React refactor'ı ~6 saat, merge conflict'le hiç merge olmadı, öneri "gecede bir küçük değişiklik" [44]; 8 saatlik auth refactor 47 commit 23 $ (B); "50 iterasyon 50–100 $" tahmin; runaway subagent recursion issue'su "5 dk'da 4 M token" (S).

### 2.10 Aider architect/editor [47][48][49]

- **Mekanizma:** architect modeli çözümü anlatır, editor modeli dosya edit'ine çevirir; `--architect`. CONVENTIONS.md `--read` ile salt-okunur ve cache'lenir; repo map `--map-tokens` varsayılan 1k.
- **Ölçülmüş:** 133 Exercism görevinde pairing +3–5 puan (o1-preview+DeepSeek %85 vs o1-preview tek %79,7; Sonnet+Sonnet %80,5 vs %77,4) [47]; polyglot: **R1 + Sonnet %64 / 13,29 $ vs o1 tek %61,7 / 186,5 $** ("14× ucuz") [48]; ama o3(high)+gpt-4.1 editor %78,2 / 17,55 $ vs o3 tek %76,9 / 13,75 $ — pairing burada daha doğru ama daha pahalı [S, leaderboard aynası]. Çıkarım: ucuz editor pahalı reasoner'ı ucuzlatır, güçlü reasoner + güçlü editor pahalanır.

### 2.11 Amp (Sourcegraph) [50][51][52][73]

- **Tutulan:** `AGENTS.md` (cwd'den $HOME'a kadar ebeveynler + alt ağaçlar, alt ağaç dosyası o ağaçtan dosya okununca yüklenir; `@path/glob` lazy; yönetici dosyası subagent'lara gitmez); dört mod `low/medium/high/ultra` = model + effort + system prompt + tool + oracle paketi; subagent'lar Search/Task/Librarian/Read-Thread, "izole, birbiriyle konuşmaz, yalnızca final özet döner"; Agent-to-Agent: spawn edilen thread'in kendi context'i, çalışma kopyası ve "orb"u var, dosya yalnızca açık transferle geçer [50].
- **Pratik (Ball):** "thread'leri küçük tut, sık yeni aç"; ~100k token sonrası "erken talimatları unutuyor / doom loop"; MCP yok, framework yok, slash komutu yok, 1–2 skill; dizin başına AGENTS.md (kök: dev server/browser komutları; alt dizin: Storybook portu, nasıl doğrulanır); "how-to bilgisini prompt'tan repo'ya taşı"; review: yük taşıyan kısımları (protokol, sleep/wake) yakından, çevresel kodu (CSS) az; prompt'ların ~%90'ı ekran görüntüsü içeriyor; delege etmediği: mimari karar, denetimsiz kritik kod, yeni yapı [51][52]. Handoff: Amp yeni thread prompt'unu taslaklar, insan düzenler ("Claude'un /compact'inin daha iyi hali") [73]. Hiçbir yerde maliyet sayısı yok.

### 2.12 Devin / Cognition [53][54][55][56][72]

- **2025 tezi:** "context'i ve tam agent izlerini paylaş; aksiyonlar örtük karar taşır"; paralel subagent'lar çelişen varsayımla çalışır (Flappy Bird örneği); tek thread'li agent + ayrı bir sıkıştırma modeli (Cognition küçük model fine-tune etti) [53].
- **2026 revizyonu:** işe yarayan üç kalıp: yalnızca diff'i gören temiz-context reviewer; daha güçlü modele "smart friend" eskalasyonu; manager/children map-reduce; "yazmalar tek thread'de kalır"; "paralel-yazar sürüleri anlamlı benimsenme görmedi" [54]. Devin Review "PR başına ortalama 2 bug, %58'i ciddi" (vendor) [54].
- **Kit:** Playbook = tekrarlanan iş için özel system prompt (Procedure / Specifications / Advice / Forbidden Actions / What's Needed; "aşırı belirtmek problem çözmeyi kısıtlar"; iki Devin'i aynı playbook'ta paralel koşturup farkları geri katla) [56]; Knowledge küçük tetikleyicili parçalar, "ilgili olunca çekilir, başta hepsi değil"; **Knowledge artık deprecated, Skills'e geçiyor** [56]. Haftada 659 Devin PR'ı (2025'in en iyi haftası 154); "darboğaz kod yazmaktan review'a kaydı"; büyük iş "küçük izole session'lara" [55].
- **Dış kanıt:** 654 reddedilen agent PR'ı: yalnızca agent PR'larına özgü yedi red türü ("AI koduna güvensizlik" dahil), redlerin %67,9'u gerekçesiz [72].

### 2.13 Simon Willison — Agentic Engineering Patterns [57][58]

- Tek anti-pattern: "review etmediğin kodu iş arkadaşlarına dayatmak"; ilk review geçişi senin işin, dışarı verilmez; kanıt ekle (manuel test notu, ekran görüntüsü, video); küçük PR [57]. Subagent: "asıl değer kök context'i korumak"; çok sayıda uzman subagent yaratma; paralel alt işler için Haiku; test-runner subagent gürültülü çıktıyı saklar [57].
- Paralel: Claude Code + Codex CLI ayrı terminallerde, worktree yerine /tmp'de taze checkout; "aynı anda yalnızca bir önemli değişikliği review edip landed edebiliyorum" → paralellik yalnızca düşük bilişsel yüklü iş için (araştırma, PoC, küçük bakım, sıkı belirtilmiş uygulama); "keşif eri gönder" (hangi dosyaların zor olduğunu öğrenen atılabilir agent); "kendi spec'inden başlayan kodu review etmek çok daha az efor"; riskli iş async Codex Cloud'a [58]. Sayı yok.

### 2.14 İç kit'ler: Stripe, Ramp, Uber, HumanLayer [59][60][61][62]

- **Stripe Minions:** Block'un goose'unun "insan denetim özellikleri sökülmüş, tam izinle" izole devbox'ta koşan fork'u (prod yok, egress yok; izolasyon izin prompt'unun yerine); Blueprints = deterministik (lint, push, git) + agentic düğümlü state machine, düğüm başına tool kısıtlama ve context budama; "global kurallar context'i doldurmasın diye seyrek", çoğu kural alt dizin/dosya kalıbına kapsamlı (Cursor formatı kanonik, Claude Code'a senkron); **CI "çoğunlukla bir, en fazla iki tur"**, sonra insan; her PR insan review'lu; haftada >1.300 PR; Toolshed'in ~500 MCP tool'undan minion "küçük varsayılan alt küme" alır [59].
- **Ramp Inspect:** OpenCode agent'ı Modal sandbox'ta; PR kullanıcının kendi GitHub token'ıyla açılır ("yazar kendi değişikliğini onaylayamasın"); "takip prompt'unu koşu ortasına sokma, kuyruğa al"; ekran görüntüsü yerine DOM/React internals (token için); frontend+backend merged PR'ların ~%30'u "birkaç ayda" (gönüllü benimseme) [60].
- **Uber (Pragmatic Engineer):** %84 agentic kullanım; PR'ların %11'i agent açıyor; Claude Code %32→%63 (Ara→Şub); **AI maliyeti 2024'ten beri 6×**, paralel agent'lar sürücü; MCP Gateway; "yukarıdan mandate aşağıdan paylaşılan kazanımdan daha az işe yaradı" [61].
- **HumanLayer ACE-FCA:** Research → Plan → Implement; "sık, kasıtlı compaction, doluluk %40–60 bandında"; "kötü bir plan satırı yüzlerce kötü kod satırına yol açar: 2.000 satır kod yerine 200 satır plan review et"; her fazdan sonra durumu plan dosyasına geri sıkıştır; üç kişilik ekip ~12k $/ay Opus; 35k LOC Rust ~7 saat (anekdot) [62].

---

## 3) Karşılaştırma tablosu: bizim kit vs gözlenen pratik

| Boyut | Bizim kit | Gözlenen pratik (kaynak) |
|---|---|---|
| Her session yüklenen set | `AGENTS.md` (228 satır) + `PHASES.md` + `STATE.md` + `ARCHITECTURE.md` + klasör `AGENTS.md` | CLAUDE.md <200 satır [1][3]; OpenAI ~100 satır "içindekiler" + pointer [23]; Codex 32 KiB kesme [20]; Cursor <500 satır [25]; Stripe "global kural seyrek, kapsamlı kural çoğunlukta" [59]; Ball dizin başına küçük AGENTS.md [52] |
| Türetilebilir içerik | `ARCHITECTURE.md` her session | "Kodu okuyarak bulabileceği her şeyi dışarıda bırak"; dosya-dosya açıklama yok [2]; repo özeti bölümleri ölçülebilir fayda vermiyor [63]; LSP plugin'i okumayı azaltır [3] |
| Koşullu yükleme | Yok (klasör AGENTS.md hariç) | `.claude/rules` `paths:` [1]; iç içe AGENTS.md [20][50]; skill gövdesi isteğe bağlı [6]; Devin Knowledge tetikleyici tabanlı [56] |
| Lead/worker | Lead planlar, brief yazar, uygulamaz; worker worktree'de tek modül | superpowers controller uygulamaz, tek implementation subagent [28]; Cognition "yazma tek thread" [54]; Anthropic `/batch` worktree başına subagent [2]; Ralph döngü başına bir iş [42] |
| Worker türü | Sub-agent (kısa, read-only) · ayrı session (>1 sa) · Codex CLI | Sub-agent = context firewall, 1–2k özet döner [7][13]; fork ana cache'i okur [4]; agent teams 7× [3]; Amp thread spawn [50]; Codex Cloud workspace [S] |
| Çoklu vendor | Zorunlu çapraz review (Codex↔Claude) | Yok; "multi-model" = kademe [28][47][54]; Willison ikisini ayrı işlerde [58] |
| Gate | `check.sh` pre-commit; "gate kırmızı görülmeden bitmez" | Hook deterministik, CLAUDE.md tavsiye [2]; OpenAI linter + yapısal test asıl gate [23]; Stripe lint 1–5 sn [59]; Spec Kit anayasa (metin, gerekçeyle geçilir) [33]; OpenSpec bloklamaz [36] |
| Session'lar arası durum | `STATE.md` CAS ile; biten iş `Done:` trailer'ıyla silinir, hook zorlar | Plan/ledger/tasks dosyası [28][36][42][62]; exec-plans active/completed + doc-gardening agent [23]; zorunlu silme yok; BMAD insan "done" der [31] |
| Handoff | `HANDOFF.md` şablonu; result file `Kind:` protokolü; 200k hook | SPEC.md → temiz session [2]; Amp taslak+insan düzenler [73]; superpowers durum kodları [28]; `/clear` bedava, `/compact` tam prefix [3][4]; %40–60 doluluk [62] |
| Review döngüsü | Çapraz, inner round'lar, 2. kirli turdan sonra kademe yükselt | superpowers 5 tur, 4.'te model yükselt, minör döngüye girmez [28]; Stripe 1–2 CI turu [59]; OpenAI agent'lar tatmin olana kadar ama gate linter [23]; Anthropic "yalnızca doğruluğu etkileyen boşluk" [2] |
| Maliyet modeli | Cache TTL (5 dk / 1 sa), poll yok, `agent_cost.py` gün sonu | Cache hit oranı SLO, SEV [12]; `/usage` "Prompt cache (main)" satırı [3]; wmedia yeniden okuma %39–65 [70]; OSS kit'lerde maliyet modeli yok; claude-flow "cost-tracker" token saymıyor [41] |
| Model/effort yönlendirme | Kıtlığa göre tier tablosu; brief model+effort taşır; mid-task değişmez | Kaliteye/API fiyatına göre [3][21]; dispatch'te model zorunlu [28]; mid-session model/effort değiştirme cache kırar [4][12] |
| Çalışma modları | 7 adlı mod (kim yazar/review eder/fix'ler, effort, worker sayısı) | Amp 4 mod (model+effort+prompt paketi) [50]; bütçe modu yok |
| MCP | Yeni sunucu = bağımlılık onayı | Claude Code adları yükler, şema ertelenmiş [9]; Cursor −%46,9 [27]; Stripe küçük varsayılan alt küme [59]; Ball "MCP yok" [52] |
| Tool çıktısı | Dosyaya, özet satırı; "küçük kaldıraç" | RTK +%7,6 maliyet [67]; Caveman %8,5 [68]; hook ile test çıktısını filtrele [3]; Cursor çıktıyı dosyaya, `tail` [27] |
| Worker raporu | ~350 kelime, iki zorunlu bölüm | superpowers yalnızca durum kodu + 1 satır test özeti [28]; Anthropic 1–2k özet [13] |
| Web isteği PII kuralı | Var, brief'te tekrar | Hiçbir kitte yok |

---

## 4) Nicel veri tablosu

| Metrik | Değer | Kaynak | Tür/Güven |
|---|---|---|---|
| Cache yazma/okuma çarpanı | 5 dk 1,25×; 1 sa 2×; okuma 0,1× (5.5: 0,05×; Fable 5.1: 0,025×); min prefix 512 token | [5] | R |
| Cache TTL kovaları (Claude Code) | Ana konuşma 1 sa (abonelik, plan içi) / 5 dk (credit, API); sub-agent/teammate/fork/compaction 5 dk; `1h` credit'te yok sayılır | [4][7] | R |
| OpenAI cache | okuma 0,1× (Sol 0,05×), yazma 1,25×, TTL 30 dk (GPT-5.6+) | [24] | R |
| Geçmişin yeniden okunması | 3 session: 61×/16×/39× yeni token; faturanın %65/%39/%54'ü | [70] | F (n=3, jq) |
| Claude Code kurumsal maliyet | ~13 $/gün/dev; 150–250 $/ay; %90 <30 $/gün; arka plan <0,04 $/session | [3] | R (telemetri) |
| Agent teams / çok-agent | ~7× (plan mode'da); agent 4× chat, çok-agent 15× chat; token kullanımı varyansın %80'i | [3][14] | R (yöntemsiz) / B |
| Cursor subagent | 5 paralel ≈ 5× token; öneri 2–3 | [26] | R (iddia) |
| Startup prefix (resmi simülasyon) | sistem 4.200; auto memory 680; ortam 280; MCP adları 120; skill açıklamaları 450; proje CLAUDE.md 1.800 token | [11] | R (örnek) |
| MCP tool tanımları | tipik 5 sunucu ~55k token, tool search >%85 azaltır; iç ölçüm 77k→8,7k; Opus 4.5 MCP eval %79,5→%88,1 | [16][18] | R/B |
| Cursor dynamic context | toplam token −%46,9 (MCP çağıran koşular, A/B) | [27] | B (ölçüldü) |
| Code execution with MCP | 150k→2k token (tek örnek, %98,7) | [17] | B (örnek) |
| Skill bütçeleri | açıklama 1.536 kr; SKILL.md <500 satır; compaction sonrası 5k/skill, 25k toplam; Codex skill context %2, max 10k | [6][22] | R |
| Codex AGENTS.md sınırı | 32 KiB toplam, aşınca kesilir | [20] | R |
| AGENTS.md etkisi (geliştirici yazımı) | medyan süre −%28,6; çıktı token −%16,6; tamamlanma eşdeğer (10 repo, 124 PR) | [64] | P |
| Context dosyası etkisi (ETH) | LLM üretimi: −0,5 / −2 puan, +2,45/+3,92 adım, +%20/%23 maliyet; geliştirici yazımı ≈ +4 puan (anlamsız), ≤+%19 maliyet; ortalama 641 kelime | [63] | P |
| RTK (bağımsız) | düşük effort +%7,6 maliyet (p=0,004); yüksek effort ±0; `rtk gain` aynı koşularda "96,2 M token tasarruf" | [67] | B (ölçüldü, 425 deneme) |
| Caveman (bağımsız) | ilan %65 → ölçülen çıktı %8,5; kalite p=0,82; toplam maliyet tersine | [68] | B (ölçüldü, ~240 deneme) |
| Caveman (proje kendi) | çıktı −%3 (caveman) / −%35 (ultracave), input 0; dış A/B: çıktı −%44, toplam +%0,06 | [69] | B |
| Token tüketimi (SWE-bench, 8 model) | agentic iş kod chat'in 1000×; input maliyeti sürüyor; aynı görevde 30× fark; çok token ≠ doğruluk | [66] | P |
| Opus 4.5 effort | medium = Sonnet 4.5 skoru, −%76 çıktı token; max +4,3 puan, −%48 token | [19] | B (vendor) |
| Aider architect | R1+Sonnet %64 / 13,29 $ vs o1 %61,7 / 186,5 $; pairing +3–5 puan (133 görev) | [47][48] | B (ölçüldü) |
| Spec Kit vs iteratif (Eberhardt) | 33,5 dk + 3,5 sa review / 689 LOC / 2.577 satır md vs 8 dk + 24 dk / ~1.000 LOC / 0 md | [34] | B (n=1 proje) |
| SDD benchmark (uvik) | OpenSpec %84 / 2,71 $ / 36 dk; Spec Kit %80 / 3,33 $ / 44 dk; BMAD %82 / 4,23 $ / 55 dk; spec'siz %72 / 2,43 $ / 29 dk; <3 dosya spec zararına, 6+ dosya %50→%80 | [39] | B (vendor; koşu tarihi gelecekte, ham veri yok) |
| superpowers yavaşlık | "2 satır 20 dk, 4 sa limitin %75'i"; CRUD 35 dk vs 2 dk; 18 raporcu, 5 ay yanıtsız | [29] | F |
| superpowers bootstrap | <2k token; subagent deneyi 50k+/subagent × 5 | [28][30] | R/F |
| BMAD tek feature | ~200 $, 6 gün; ilk kod öncesi 12–16 sa | [32] | S/B (rakip ilgisi beyan edildi) |
| claude-flow denetimi | ~290/300 tool stub; token sayan kod yok; session başına 15–25k token ek yük | [41] | F (kod denetimi) |
| Ralph | 297 $ hikâyesi folklor; 6 sa refactor merge olmadı; 47 commit 8 sa 23 $ | [42][44][S] | F/B |
| OpenAI harness ekibi | ~1 M LOC / 5 ay / 3 müh. / ~1.500 PR / 3,5 PR/müh/gün; Codex koşusu 6+ sa | [23] | B (öz-bildirim) |
| Stripe | >1.300 PR/hafta; CI 1–2 tur; ~500 MCP tool'dan küçük alt küme | [59] | B |
| Ramp / Uber | merged PR'ın ~%30'u Inspect; Uber AI maliyeti 6×, PR'ların %11'i agent | [60][61] | B/S |
| HumanLayer | %40–60 doluluk; 3 kişi ~12k $/ay Opus | [62] | B (anekdot) |
| Context rot | 18 modelde uzunlukla tutarlı düşüş; 113k vs 300 token odaklı prompt'ta hepsi daha iyi | [65] | P |
| METR RCT | AI izinli iş +%19 süre (n=16, 246 görev); beklenti −%24 | [71] | P |
| Agent PR redleri | 654 red; yalnızca agent'a özgü 7 red türü; %67,9 gerekçesiz | [72] | P |

**Bizim kitten eksik veri:** session başına startup prefix token'ı (`/context` ile bir ölçüm yok); cache hit oranı ve miss nedenleri (`/usage` "Prompt cache (main)" satırı v2.1.251+ bunu veriyor, kaydedilmiyor); worker başına toplam token / wall-clock / review tur sayısı dağılımı (WORKFLOW "ölçerek doldur" diyor, n=1); `ARCHITECTURE.md` ve `PHASES.md`'nin her session'da kaç token olduğu.

---

## 5) Bizden farklı yaptıkları (bize potansiyel değere göre sıralı)

1. **Koşullu yükleme: path-scoped kural ve iç içe talimat dosyası, her session'da tek büyük set yerine.** Anthropic `.claude/rules/*.md` `paths:` ile yalnızca eşleşen dosyaya dokununca yükler [1]; Codex ve Amp alt dizin AGENTS.md'sini o ağaçtan dosya okununca ekler [20][50]; Stripe "koşulsuz kurallar ölçeklenmez" [59]; Ball kök dosyayı komutlara, alt dizini doğrulama bilgisine ayırıyor [52]. Kanıt: context dosyası +%20 maliyet, "repo özeti" faydasız [63]; geliştirici yazımı dosya süre −%28 [64]. Bizde `ARCHITECTURE.md` ve `PHASES.md` her session; `AGENTS.md`'nin "Review gate" ve "STATE.md discipline" blokları yalnızca o işi yapan session'a lazım. Potansiyel: startup prefix'i ölçüp (eksik veri) riskli-alan kurallarını `paths:`'e, review kurallarını reviewer brief'ine taşımak.
2. **Cache hit oranını SLO olarak izlemek, gün sonu toplamı yerine.** Claude Code ekibi hit oranına alarm koyup SEV açıyor [12]; `/usage` artık istek sayısı, cache'ten gelen input payı, miss sayısı ve "likely cause: tool definitions changed" veriyor [3]; wmedia'nın ölçümü faturanın yarısından fazlasının yeniden okuma olduğunu gösterdi [70]. Bizim `agent_cost.py` gün sonunda harcamayı sayıyor; miss nedenini ve TTL kovasını (`ephemeral_1h_input_tokens` vs `ephemeral_5m_input_tokens`, `claude -p … --output-format json`) [4] kaydetmiyor.
3. **Fork sub-agent: aynı context'i gerektiren kısa iş için taze sub-agent yerine fork.** Fork ebeveynin system prompt'u, tool'ları ve geçmişini aynen alıp ebeveyn cache'ini okur; "aynı context'e ihtiyaç duyan iş için taze subagent'tan ucuz" [4][7]. Bizim "inner review round'u aynı worker'a döner" kuralı bu mekanizmayı kullanmıyor; lead'in kendi context'indeki bir diff'in review'u fork'la 1–2k'lık bir ek istek olabilir.
4. **Kanıta dayalı tamamlanma: `/goal` evaluator ve Stop hook, worker'ın "bitti" beyanı yerine.** `/goal` ayrı evaluator her turdan sonra koşulu yeniden kontrol eder, Stop hook deterministik gate [2]; Ralph plugin'inin "promise" string'i tam da bu yüzden eleştirildi ve yerini `/goal` aldı [46]. Bizim result file `Kind: completed` worker'ın beyanı; `Proof:` satırı var ama kontrol eden lead.
5. **Minör bulgular döngüye hiç girmez; tur sınırı ve model yükseltme sabit.** superpowers 5 tur, 4.'te model; Stripe 1–2 CI turu [28][59]. Bizim rule 4 eskalasyonu var; "Low fix-or-file" aynı turda fix'e izin veriyor. (Önceki raporun B/C maddeleriyle örtüşür; burada yalnızca emsal.)
6. **Doküman bahçıvanlığı agent'ı ve tech-debt tracker.** OpenAI bayat dokümanı bulan ve fix-up PR açan arka plan agent'ı + `tech-debt-tracker.md` [23]. Bizim "living docs never bloat" kuralı silmeyi zorluyor ama bayatlamayı (yanlış path, eski model adı) yalnızca review bulur. `scripts/check.sh`'e "doc'ta geçen path var mı" sensörü aynı işi deterministik yapar.
7. **Explore/araştırma sub-agent'ı CLAUDE.md'siz ve Haiku'da.** Anthropic'in Explore/Plan ajanları CLAUDE.md'yi ve git snapshot'ını atlar; `omitClaudeMd: true` [7]; Haiku'ya handoff model değişiminden ucuz [12]; Willison paralel alt iş için Haiku [57]. Bizim her sub-agent AGENTS.md hiyerarşisini yükler; salt-okunur teşhis için gereksiz.
8. **Skill'i context'ten tamamen çıkarmak.** `disable-model-invocation: true` açıklamayı bile listeden siler; Codex skill context'i pencerenin %2'siyle sınırlı [6][22]. Bizim overlay'in skill/command sayısı ve açıklama toplamı ölçülmemiş (`/skill-doctor` verir).
9. **Durumu iki sayıyla değil, worker'ın döndürdüğü sabit durum koduyla iletmek.** superpowers DONE / DONE_WITH_CONCERNS / NEEDS_CONTEXT / BLOCKED [28]. Bizim `Kind:` dört değeri buna eşdeğer; farklı olan superpowers'ın raporu bir satır test özetiyle sınırlaması. Düşük değer; zaten yakın.
10. **Tool çıktısını hook'la kaynağında filtrelemek.** Anthropic PreToolUse hook'u test komutunu `grep FAIL | head -100`'e çevirir [3]; Cursor çıktıyı dosyaya yazıp `tail`'letir [27]. Ölçülmüş kazanç küçük (RTK/Caveman) [67][68]; bizim "dosyaya yaz, özet oku" kuralı aynı sınıf. Düşük değer.

**Bizim yapıp kimsenin yapmadıkları** (kanıt yokluğu = emsal yokluğu, yanlışlık değil): çapraz-vendor review gate; bütçeye göre yedi adlı mod; cache TTL'ye dayalı maliyet modeli ve "poll etme" kuralı; `Done:` trailer'ıyla zorunlu silme; "gate kırmızı görülmeden bitmiş sayılmaz"; web isteğinde PII yasağı; brief'te model+effort zorunluluğunu spawn script'inin reddetmesi (superpowers yalnızca "silently defeats" diye uyarır [28]).

---

## 6) Token tasarrufu pratikleri: ne yapıyorlar, sayılar, güven

| Pratik | Kim | Sayı | Güven |
|---|---|---|---|
| Prefix'i sabit tut: system prompt'a timestamp koyma, tool sırasını değiştirme, model/effort'u session ortasında değiştirme, güncellemeleri mesaj olarak gönder | Claude Code ekibi [12]; docs [4] | "birkaç puanlık miss oranı maliyeti ve gecikmeyi dramatik etkiler"; 100k'lık Opus konuşmasında Haiku'ya geçmek daha pahalı | B/R (yöntem açık, sayı yok) |
| Compaction'ı aynı prefix'le fork olarak koş | Claude Code [12] | özet ~20k token, cache'ten "onda bir fiyata" | B |
| 1 sa TTL'yi sub-agent'a uzat | docs [4][7]; bizim ölçüm [kit] | yazma 2× vs 1,25×; bizde bekleyen worker'da −36…−38 % | R / kit (n=6 kurulum) |
| Tool şemalarını ertele (tool search) | Claude Code varsayılan [9]; Cursor [27]; Anthropic [16][18] | 55k→<8k; 77k→8,7k; toplam −%46,9 (A/B) | R/B (ölçüldü) |
| Kod ile MCP çağır, ara sonucu modele geçirme | Anthropic [17] | 150k→2k (tek örnek) | B (örnek) |
| CLAUDE.md'yi kısa tut, workflow'u skill'e taşı | Anthropic [1][3]; OpenAI [21][23]; Cursor [25] | <200 satır; ~100 satır; 32 KiB; <500 satır | R (limit), ölçüm [63][64] |
| Path-scoped kural | Anthropic [1]; Stripe [59]; Amp [50] | ölçüm yok | R/B |
| Skill gövdesi isteğe bağlı; açıklama 1.536 kr; `disable-model-invocation` | Anthropic [6] | ölçüm yok; Codex %2 bütçe [22] | R |
| `/clear` iş arası; `/compact` yalnızca sıcakken ve doğal molada; iki başarısız düzeltmeden sonra `/clear` | Anthropic [2][3] | "`/clear` bedava"; compact soğuk cache'te tam fiyat | R |
| Doluluk %40–60'ta kasıtlı compaction; plan dosyasına geri sıkıştır | HumanLayer [62] | ölçüm yok | B (anekdot) |
| Thread'i küçük tut, ~100k'da yenisini aç | Ball [51] | folklor | B |
| Sub-agent'ı gürültülü iş için, özeti 1–2k | Anthropic [7][13]; Willison [57] | "on binlerce" → 1–2k | B |
| Fork'u aynı context'li iş için | Anthropic [4][7] | "taze subagent'tan ucuz", sayı yok | R |
| Agent teams'i son çare | Anthropic [3][8] | ~7×, lineer | R (yöntemsiz) |
| Ucuz model araştırma/editor'e | Aider [48]; Anthropic [3][12]; Willison [57] | 13,29 $ vs 186,5 $ | B (ölçüldü) / folklor |
| Effort'u işe göre | Anthropic [10][19]; Codex [21] | medium −%76 çıktı token (vendor) | B |
| Tool çıktısını kısalt (RTK, caveman, hook) | [3][27][67][68][69] | bağımsız: +%7,6 maliyet / %8,5 çıktı; input baskın [66] | B (ölçüldü, olumsuz) |
| Çıktıyı dosyaya, `tail` | Cursor [27]; bizim kural | −%46,9 paketin parçası | B |
| Spec'i yalnızca 3+ dosyalık işte | uvik [39]; Eberhardt [34]; Anthropic "bir cümle = plan atla" [2] | <3 dosya 1,64 $ vs 1,59 $ (doğrulanamadı) | B (zayıf) / R |
| Brief'e tam içerik değil dosya yolu | superpowers [28] | ölçüm yok | R |
| Subagent prompt'u ~2.000 kelimeyi geçmesin | Cursor [26] | ölçüm yok | R |
| Poll etme; bekleyen worker cache'i kaybeder | bizim kit; docs "her scheduled task / cross-session mesaj tam context gönderir" [3] | bizde cache yazmanın %87'si beklemelerden | R / kit |
| Kota/bütçe tavanı | Codex `rollout_budget` [22]; Claude `--max-budget-usd` (headless) [3] | — | R |

Folklor olarak işaretlenenler: "smart zone %40'ta biter" [45]; "Haiku subagent %60–80 tasarruf" (liste fiyatı aritmetiği); "autocompact %95'te" (güncel dokümanda yok, mekanizma token penceresi [10]); "Chroma: 50k'da belirgin düşüş" (raporda yok [65]); "BMAD sharding %90" [31]; "claude-flow −%32 token" [41]; superpowers v6 "−%60 token" [28].

---

## 7) Kaynaklar

Format: [n] Başlık — URL — tarih — tür (R resmi/proje deposu, P makale, B blog-vendor, F forum/issue, S ikincil).

1. Claude Code — How Claude remembers your project (CLAUDE.md, rules, auto memory, AGENTS.md) — https://code.claude.com/docs/en/memory — 2026 — R
2. Claude Code — Best practices — https://code.claude.com/docs/en/best-practices — 2026 — R
3. Claude Code — Manage costs effectively — https://code.claude.com/docs/en/costs — 2026 — R
4. Claude Code — How Claude Code uses prompt caching — https://code.claude.com/docs/en/prompt-caching — 2026 — R
5. Claude API — Prompt caching (pricing, TTL, breakpoints) — https://platform.claude.com/docs/en/build-with-claude/prompt-caching — 2026 — R
6. Claude Code — Skills — https://code.claude.com/docs/en/skills — 2026 — R
7. Claude Code — Subagents — https://code.claude.com/docs/en/sub-agents — 2026 — R
8. Claude Code — Agent teams — https://code.claude.com/docs/en/agent-teams — 2026 — R
9. Claude Code — MCP (tool search, output limits) — https://code.claude.com/docs/en/mcp — 2026 — R
10. Claude Code — Model configuration (effort, auto-compact) — https://code.claude.com/docs/en/model-config — 2026 — R
11. Claude Code — Explore the context window (startup simülasyonu) — https://code.claude.com/docs/en/context-window — 2026 — R
12. Thariq Shihipar — Lessons from building Claude Code: prompt caching is everything — https://claude.dev/blog/lessons-from-building-claude-code-prompt-caching-is-everything/ — 2026-04-30 — B
13. Anthropic — Effective context engineering for AI agents — https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents — 2025-09-29 — B
14. Anthropic — How we built our multi-agent research system — https://www.anthropic.com/engineering/multi-agent-research-system — 2025-06-13 — B
15. Anthropic — How Anthropic teams use Claude Code — https://claude.com/blog/how-anthropic-teams-use-claude-code — 2025-07-24 — B
16. Anthropic — Advanced tool use (tool search, programmatic tool calling) — https://www.anthropic.com/engineering/advanced-tool-use — 2025-11 — B
17. Anthropic — Code execution with MCP — https://www.anthropic.com/engineering/code-execution-with-mcp — 2025-11-04 — B
18. Claude API — Tool search tool — https://platform.claude.com/docs/en/docs/agents-and-tools/tool-use/tool-search-tool — 2026 — R
19. Anthropic — Introducing Claude Opus 4.5 (effort vs token) — https://www.anthropic.com/news/claude-opus-4-5 — 2025-11 — B (vendor)
20. OpenAI Codex — Custom instructions with AGENTS.md — https://learn.chatgpt.com/docs/agent-configuration/agents-md — 2026 — R
21. OpenAI Codex — Best practices — https://learn.chatgpt.com/docs/learn/best-practices — 2026 — R
22. OpenAI Codex — Config reference — https://learn.chatgpt.com/docs/config-file/config-reference — 2026 — R
23. Ryan Lopopolo (OpenAI) — Harness engineering: leveraging Codex in an agent-first world — https://openai.com/index/harness-engineering/ — 2026-02-11 — B
24. OpenAI — Prompt caching guide — https://developers.openai.com/api/docs/guides/prompt-caching — 2026 — R
25. Cursor — Rules — https://cursor.com/docs/context/rules — 2026 — R
26. Cursor — Subagents — https://cursor.com/docs/agent/subagents — 2026 — R
27. Cursor — Dynamic context discovery — https://cursor.com/blog/dynamic-context-discovery — 2026-01-06 — B (A/B)
28. obra/superpowers — README; skills/subagent-driven-development/SKILL.md; skills/using-superpowers/SKILL.md — https://github.com/obra/superpowers — v6.4, 2026-09 — R (OSS)
29. obra/superpowers issue #743 — "slowness since using the skill" — https://github.com/obra/superpowers/issues/743 — 2026-03-15, açık — F
30. Hacker News — Superpowers (Ekim 2025) ve Superpowers 6 tartışmaları — https://news.ycombinator.com/item?id=45547344 ; https://news.ycombinator.com/item?id=48739459 — 2025/26 — F
31. BMAD-METHOD — README, docs/build/build-a-change.md — https://github.com/bmad-code-org/BMAD-METHOD — v6.12, 2026 — R (OSS)
32. BMAD deneyimleri — Kdosha review (rywalker.com/research/bmad-method aktarımı); Dan Gurgui "patience required" — https://rywalker.com/research/bmad-method ; https://dev.to/arch4g/my-experience-using-the-bmad-framework-on-a-personal-project-patience-required-28aa — 2025-12/2026 — S/B
33. GitHub Spec Kit — README, spec-driven.md — https://github.com/github/spec-kit — 2026 — R (OSS)
34. Colin Eberhardt — Putting Spec Kit Through Its Paces: Radical Idea or Reinvented Waterfall? — https://blog.scottlogic.com/2025/11/26/putting-spec-kit-through-its-paces-radical-idea-or-reinvented-waterfall.html — 2025-11-26 — B
35. Spec Kit issue #1193 (resume / mid-way change / merge) — https://github.com/github/spec-kit/issues/1193 — 2025-11-15, stale kapatıldı 2026-05-16 — F
36. OpenSpec — README, docs/workflows.md — https://github.com/Fission-AI/OpenSpec — v1.4, 2026 — R (OSS)
37. Ry Walker — OpenSpec profile (Rails karşılaştırması, yönetişim) — https://rywalker.com/research/openspec — 2026-06 — S
38. dabase — SDD framework comparison — https://dabase.com/blog/2026/sdd-framework-comparison/ — 2026-05-18 — B
39. uvik.net — Spec-Driven Development Benchmark (Spec Kit / Kiro / BMAD / OpenSpec / no spec) — https://uvik.net/spec-driven-development-benchmark/ — "2026-10-08" (koşu tarihi gelecekte) — B (vendor, doğrulanamadı)
40. ruvnet/claude-flow (Ruflo) — README — https://github.com/ruvnet/claude-flow — 2026 — R (OSS)
41. Ruflo issue #1513 (v3.5.51 kod denetimi) ve discussion #1666 — https://github.com/ruvnet/ruflo/issues/1513 ; https://github.com/ruvnet/ruflo/discussions/1666 — 2026-04 — F
42. Geoffrey Huntley — Ralph Wiggum as a "software engineer" — https://ghuntley.com/ralph/ — 2025-07-14 — B
43. Anthropic — ralph-wiggum plugin README — https://github.com/anthropics/claude-code/tree/main/plugins/ralph-wiggum — 2026 — R
44. Dex Horthy — A Brief History of Ralph — https://www.humanlayer.dev/blog/brief-history-of-ralph — 2026-01-06 — B
45. Matt Pocock — Why the Anthropic Ralph plugin sucks — https://www.aihero.dev/why-the-anthropic-ralph-plugin-sucks — 2026-01-22 — B
46. d4hines — Ralph-wiggum is Bad and Anthropic Should Fix It (+ Haziran 2026 `/goal` güncellemesi) — https://www.greaterwrong.com/posts/bmNHsY5i3EoP4BAoJ/ — 2026-02-04 — F
47. Aider — Separating code reasoning and editing (architect mode) — https://aider.chat/2024/09/26/architect.html — 2024-09-26 — B
48. Aider — R1+Sonnet set SOTA on aider's polyglot benchmark — https://aider.chat/2025/01/24/r1-sonnet.html — 2025-01-24 — B
49. Aider — Repository map; Specifying coding conventions — https://aider.chat/docs/repomap.html ; https://aider.chat/docs/usage/conventions.html — 2025 — R
50. Amp — AGENTS.md; Models and subagents; Agent to Agent — https://ampcode.com/docs/markdown/customize/agents-md ; https://ampcode.com/docs/models-and-subagents ; https://ampcode.com/docs/orbs/agent-to-agent — 2026 — R
51. Thorsten Ball — How I use Amp — https://ampcode.com/notes/how-i-use-amp — 2025-05-15 — B
52. Thorsten Ball — Think Harder: How I Prompt (Laracon US) — https://thorstenball.com/talks/how-i-prompt/ — 2026-07-29 — B
53. Walden Yan (Cognition) — Don't Build Multi-Agents — https://cognition.com/blog/dont-build-multi-agents — 2025-06-12 — B
54. Cognition — Multi-Agents: What's Actually Working — https://cognition.com/blog/multi-agents-working — 2026-04-22 — B
55. Cognition — How Cognition uses Devin to build Devin — https://cognition.com/blog/how-cognition-uses-devin-to-build-devin — 2026-02-27 — B
56. Devin docs — Knowledge (deprecated → Skills); Creating playbooks — https://docs.devin.ai/product-guides/knowledge ; https://docs.devin.ai/product-guides/creating-playbooks — 2026 — R
57. Simon Willison — Agentic Engineering Patterns (Anti-patterns; Subagents; Using Git) — https://simonwillison.net/guides/agentic-engineering-patterns/ — 2026 (canlı) — B
58. Simon Willison — Embracing the parallel coding agent lifestyle — https://simonwillison.net/2025/Oct/5/parallel-coding-agents/ — 2025-10-05 — B
59. Stripe — Minions: Stripe's one-shot end-to-end coding agents (Part 1, Part 2) — https://stripe.dev/blog/minions-stripes-one-shot-end-to-end-coding-agents — 2026-02-09 / 02-19 — B
60. Ramp — Why we built our background agent (Inspect) — https://builders.ramp.com/post/why-we-built-our-background-agent — 2026-01 — B
61. Pragmatic Engineer — How Uber uses AI for development — https://newsletter.pragmaticengineer.com/p/how-uber-uses-ai-for-development — 2026-03-10 — S (paywall)
62. HumanLayer — Advanced Context Engineering for Coding Agents (ace-fca.md) — https://github.com/humanlayer/advanced-context-engineering-for-coding-agents — 2025-08 — B
63. Gloaguen, Mündler, Müller, Raychev, Vechev (ETH/LogicStar) — Evaluating AGENTS.md: Are Context Files Helpful for Coding Agents? — https://arxiv.org/abs/2602.11988 — 2026-02-12 (ICLR 2026) — P
64. Lulla et al. — On the Impact of AGENTS.md Files on the Efficiency of AI Coding Agents — https://arxiv.org/abs/2601.20404 — 2026-01/03 — P
65. Chroma — Context Rot: How Increasing Input Tokens Impacts LLM Performance — https://www.trychroma.com/research/context-rot — 2025-07-14 — P (teknik rapor)
66. Bai et al. — Token consumption of agentic coding on SWE-bench Verified (8 frontier model) — https://arxiv.org/abs/2604.22750 — 2026-04 — P
67. JetBrains AI — RTK and Claude Code token savings: an independent benchmark — https://blog.jetbrains.com/ai/2026/07/rtk-claude-code-token-savings/ — 2026-07-20 — B (bağımsız ölçüm)
68. JetBrains AI — Speak to AI agents like cavemen to save tokens? (benchmark) — https://blog.jetbrains.com/ai/2026/07/speak-to-ai-agents-like-cavemen-tosave-tokens/ — 2026-07 — B (bağımsız ölçüm)
69. rtk-ai/rtk README; JuliusBrussee/caveman docs/HONEST-NUMBERS.md — https://github.com/rtk-ai/rtk ; https://github.com/JuliusBrussee/caveman/blob/main/docs/HONEST-NUMBERS.md — 2026 — B (proje kendi)
70. wmedia — Claude Code token usage: every turn re-reads the history (3 session, jq) — https://wmedia.es/en/tips/claude-code-token-usage-every-turn — 2026 — F (n=3)
71. METR — Measuring the impact of early-2025 AI on experienced open-source developer productivity — https://metr.org/blog/2025-07-10-early-2025-ai-experienced-os-dev-study/ — 2025-07-10 — P
72. Why Agentic-PRs Get Rejected (654 PR) — https://arxiv.org/abs/2602.04226 — 2026-02-04 — P
73. Hamel Husain — Notes on Amp (handoff, oracle) — https://hamel.dev/notes/coding-agents/amp.html — 2025/26 — S

**Erişilemeyen / doğrulanamayan:** superpowers v6 release yazısı ("−%50 süre / −%60 token"; ikincil kaynaklar çelişkili); BMAD "%90 token", "31.667 token/run", "847 $/ay"; claude-flow "%84,8 SWE-bench" (arşiv README'si 404/403); Ralph "297 $" hikâyesinin birincil bağlamı; uvik benchmark'ının ham verisi ve gerçek koşu tarihi; OpenAI "Codex PR'ların %100'ünü review eder" / ">%92 benimseme" birincil sayfası (403); Devin ACU fiyatları ve "PR başına 2 bug"; Anthropic "agent teams ~7×" yöntemi; Codex effort çarpanları (3–5×, 8–15×: topluluk tahmini); Claude Code autocompact yüzdesi (güncel dokümanda token penceresi var, yüzde yok); Chroma "50k'da düşüş"; Pocock "%40 smart zone"; Uber ">%70 PR agent'lı" (Pragmatic Engineer %11 diyor); Shopify/Block/Google/Microsoft CEO yüzdeleri; HumanLayer "100k session'dan dumb zone"; Amp'in herhangi bir maliyet rakamı; Anthropic'in iç lead/worker + worktree kullanımına dair birincil kaynak (yalnızca S).
