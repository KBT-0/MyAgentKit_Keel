# AI sektörü taraması (ai-watch): kapsam ve son tarama

Son tarama: 2026-11-10

Soru (sahip, 2026-11-10): "Sadece Claude Code değil: sektördeki tüm AI güncellemelerini ara ara tarayalım; yeni sürümler,
skill'ler, işimize yarayacak her şey. Bir arama kapsamı tanımla; kit geliştirilirken haftada bir, NotebookLM yardımıyla
bakalım; son araştırmanın tarihini yaz; bir kit oturumu açtığımda bir haftadan fazla geçmişse araştırmayı paralelde başlat."
PLAN maddesi 10B. Bu dosya iki iş görür: **kapsam** (bölüm 1–4, değişmez kısım) ve **son taramanın bulguları** (bölüm 5, her
taramada baştan yazılır). Yukarıdaki `Son tarama:` satırını kitin SessionStart hook'u okur (`.claude/settings.json`,
`tests/test_aiwatch_stale.py`): satır 7 günden eskiyse ya da yoksa lead'e tek satır yazar. Satırın biçimi sabittir:
satır başında `Son tarama: YYYY-MM-DD`.

Etiketler `context-hygiene.md` ile aynı: **P** vendor birincil doküman (changelog, release notes, spec), **R**
araştırma/benchmark, **B** blog/pratisyen, **F** forum/issue, **S** ikincil (tracker, haber özeti, NotebookLM özeti;
birincil sayfa açılmadıysa). Kanıt dili: **vendor beyanı**, **ölçüm**, **anekdot**, **çıkarım**.

---

## 1) Kaynaklar ve her birinde ne aranır

| Kaynak | URL | Ne aranır |
|---|---|---|
| Claude Code CHANGELOG | https://raw.githubusercontent.com/anthropics/claude-code/main/CHANGELOG.md | Son taramadan beri gelen sürümler: hook olayları/alanları, settings anahtarları, env değişkenleri, subagent/background, effort, worktree, izinler, compact/context, cache davranışı |
| Claude docs release notes | https://docs.claude.com/en/release-notes/overview | Claude Code ve API doküman değişiklikleri; varsayılanların değişmesi |
| Claude API / model duyuruları | https://www.anthropic.com/news, https://docs.claude.com/en/docs/about-claude/models/overview | Yeni model ve model ID'leri, fiyat, emeklilik tarihleri: `WORKFLOW` "Model routing" tablosu |
| anthropics/skills + Agent Skills spec | https://github.com/anthropics/skills, https://agentskills.io/specification | Spec alanları, yönetişim, örnek skill'ler; kitin `plugins/myagentkit/skills` biçimine etkisi |
| OpenAI Codex CLI | https://github.com/openai/codex/releases | Hook'lar, config (TOML), onay/izin modeli, subagent, skill, MCP, reasoning effort, compaction: kitin Codex işçileri ve `cross` modu |
| OpenAI API / model notları | https://platform.openai.com/docs/changelog | Model adları ve effort seviyeleri: "Model routing" Codex sütunu |
| Gemini CLI | https://github.com/google-gemini/gemini-cli/releases | Hook/config/subagent/sandbox fikirleri (kit Gemini'yi desteklemez; yalnız fikir kaynağı) |
| Cursor / Windsurf | https://cursor.com/changelog, https://windsurf.com/changelog | Agent iş akışı özellikleri (çalışan agent'ı yönlendirme, hook, zamanlanmış agent): fikir kaynağı |
| MCP spec + registry | https://modelcontextprotocol.io/specification, https://registry.modelcontextprotocol.io | Spec revizyonları, kaldırılan özellikler; kitin MCP kullanımına etkisi |
| Makaleler | https://arxiv.org/list/cs.SE/recent, https://arxiv.org/list/cs.AI/recent | Arama terimleri: "coding agent" evaluation, "agentic workflow", "code review" LLM, "multi-agent" software engineering, "context management" agent, "SWE-bench" cost |
| Kitin saha projeleri | `gh issue list --repo KBT-0/MyAgentKit_Keel --label kit-feedback --state open` | Projelerin kit-feedback issue'ları: sahada kırılan kural, eksik araç |

## 2) "Kite yarar" filtresi

Bir değişiklik şu anahtar kelimelerden birine dokunuyorsa okunur, yoksa geçilir: effort, subagent, hook, settings, env,
worktree, permission, compact, context, model, review, gate, token, cache, skill, MCP, eval, cost. Filtreden geçen her
madde için tek soru: "kitin bir kuralını, aracını ya da varsayılanını değiştirir mi?"

## 3) Rapor biçimi

En fazla bir sayfa. Her bulgu tek satır: **ne değişti · kaynak [etiket] · kitte neyi değiştirebilir (PLAN adayı / eylem
yok)**. Eylem gerektirmeyen ama bilinmesi gereken madde "eylem yok" ile yazılır ki sonraki tarama aynı şeyi yeniden
tartmasın. Çıkarım kanıttan ayrı yazılır.

## 4) Taramanın işleyişi

1. Kit oturumu açılınca SessionStart, `Son tarama` 7 günden eskiyse lead'e "ai-watch: son tarama N gün önce …" satırını
   yazar (işçilere yazmaz; projeler bu hook'u almaz: tarama yalnız kitin işi, projeler kit-feedback ile bildirir).
2. Lead paralelde bir araştırma işçisi başlatır (`aiwatch` görevi): web araması gereken, yargı taşıyan bir özet işi,
   "Model routing" tablosunda katman 2; Claude için Sonnet 5.5 medium, bir bulgu tasarım kararı tartacaksa Opus 5.5 medium.
   İşçi bu dosyanın bölüm 5'ini yeniden yazar ve `Son tarama`yı o günün tarihine çeker; kendi worktree'sinde tek commit.
3. Lead raporu okur; "PLAN adayı" satırları için PLAN satırı ya da kit-feedback issue açar. Karar lead'in ve sahibin.
4. Sahip istediğinde NotebookLM notlarını elle bölüm 5'e ekler (etiket **S**, kaynak "NotebookLM: …").

---

## 5) Bulgular — tarama 2026-11-10 (önceki tarama yok; pencere ~2026-10-27 → 2026-11-10)

1. **Claude Fable 5.2 Claude Code'un varsayılan Fable modeli oldu (2.1.321)** · [1] P · "Model routing" katman 3 satırı ve
   tasarım danışmanı satırı hâlâ "Fable 5.1" diyor: **PLAN adayı** (`core/docs/WORKFLOW.md` tablosunu ve `docs/ACCEPTANCE.md`'yi 5.2'ye çek).
2. **`permissions.denyInsteadOfPrompting` (2.1.319): izin istemi bekleyecek bir araç çağrısı reddedilir** · [1] P ·
   kitin işçileri izlenmeyen panelde çalışır ve "soru sorma" kuralı var; takılı izin istemi bugün işçiyi bekletiyor:
   **PLAN adayı** (işçi settings'ine ekleyip bir işçi turunda denemek; çıkarım, ölçülmedi).
3. **PostToolUse hook'ları en fazla 10 saniye ile çalışıyor (2.1.319)** · [1] P · kitin `progress_reminder.py` timeout'u
   zaten 10: **eylem yok**.
4. **Background subagent kabuk komutunu 3 dk sonra arka plana alıyor; soğuk cache'te 5 dk bekleyebiliyor (2.1.318)** · [1]
   P · `CONTRIBUTING`/WORKFLOW "Worker cost" 2.1.318'e göre zaten yeniden kontrol edildi (subeffort, 2026-11-10): **eylem yok**.
5. **Subagent'lar farklı modeldeyse o modelin kayıtlı effort'unu alıyor (2.1.317); `CLAUDE_CODE_SUBAGENT_EFFORT` (2.1.316)** ·
   [1] P · RESEARCH_LOG 2026-11-10 "subeffort" girdisiyle işlendi: **eylem yok**.
6. **Background komut bildirimleri ve TaskStop sonuçları Claude'a yalnız komutun başını ve sonunu gösteriyor (2.1.321)** · [1]
   P · arka planda çalışan `check.sh` çıktısının ortası lead'e gelmez; kitin "çıktı dosyaya, `CHECK: PASS` satırı okunur"
   kuralı bunu zaten karşılıyor: **eylem yok** (çıkarım).
7. **`.claude/skills` klasörleri `~/.claude/plugins` içinde artık yüklenmiyor (2.1.321)** · [1] P · kitin plugin'i skill'leri
   `plugins/myagentkit/skills` kökünde taşıyor, iç içe `.claude/skills` yok: **eylem yok**.
8. **`/usage` bugün/hafta/ay harcamasını gösteriyor (2.1.319)** · [1] P · `usage_summary` ile karşılaştırılabilir ikinci
   kaynak: **eylem yok** (sahip isterse doğrulama kaynağı).
9. **Codex CLI 0.167.0 (2026-11-06): PreToolUse hook'ları Guardian politika kontrolünden önce çalışıyor; yönetilen komut
   checkpoint'leri taze insan onayı istiyor; otomatik compaction başarısız yanıtların çıktısını sayıyor** · [2] P · kitin
   Codex işçileri onay istemine takılırsa bekler (2. madde ile aynı soru, Codex tarafı): **PLAN adayı** (Codex işçisinde
   checkpoint davranışını bir turda gözlemek).
10. **MCP 2026-07-28 spec'i durumsuz: `initialize` el sıkışması ve `Mcp-Session-Id` kalktı; Roots, Sampling, Logging
    deprecated** · [3] P, [4] S · kit kendi MCP sunucusu taşımıyor (yeni bağımlılık/MCP DECIDED dışı): **eylem yok**.
11. **Agent Skills standardının AAIF'e (Linux Foundation) devredildiği bildiriliyor (2026-10-22)** · [5] S, birincil sayfa
    açılmadı · spec alanları değişirse kit plugin'i etkilenir: **eylem yok**; sonraki taramada agentskills.io'yu doğrudan aç.
12. **Gemini CLI v0.67.0 (2026-11-04): model listeleme komutu, container sandbox içinde IDE companion** · [6] S · fikir
    kaynağı, kit Gemini'yi desteklemiyor: **eylem yok**.
13. **SWE-TaskFlow (JetBrains, arXiv 2610.09633, 2026-10-11): 700 SWE-Bench Pro görevinde işi sıralı adımlara bölmek ajan
    maliyetini ~2 katına çıkarıyor, çözme oranında kararlı değişim yok** · [7] R (özet sayfası; PDF açılmadı) · kitin
    "büyük işi küçük işçi görevlerine böl" pratiğinin maliyet tarafına dair ilk dış ölçüm: **PLAN adayı** (makaleyi oku,
    WORKFLOW "Task sizing" ile karşılaştır).
14. **Cursor: Kasım girdisi bulunamadı; son girdiler çalışan agent'ı yönlendirme (Ağustos) ve "Cloud Hooks" (3.11, Temmuz)** ·
    [8] S · **eylem yok**.
15. **Kitin saha projeleri: açık `kit-feedback` issue'su yok** (`gh issue list --label kit-feedback --state open` boş döndü) ·
    [9] F · **eylem yok**.

Bu taramada açılamayan/zayıf kalanlar: OpenAI API changelog ve Windsurf (aranmadı), Claude docs release notes sayfası
(CHANGELOG yeterli görüldü), Agent Skills için birincil kaynak. Sonraki tarama bunlardan başlar.

## 6) Kaynaklar

1. Claude Code CHANGELOG, 2.1.316–2.1.322 — https://raw.githubusercontent.com/anthropics/claude-code/main/CHANGELOG.md [P]
2. openai/codex releases, 0.167.0 (2026-11-06) — https://github.com/openai/codex/releases [P]
3. MCP spec 2026-07-28 changelog — https://modelcontextprotocol.io/specification/2026-07-28/changelog [P, arama özeti üzerinden]
4. noze.it, "MCP 2026-07-28: a stateless protocol…" — https://www.noze.it/en/insights/mcp-2026-07-28-stateless/ [S]
5. letsdatascience, "Anthropic donates Agent Skills standard to Agentic AI Foundation" — https://letsdatascience.com/news/anthropic-donates-agent-skills-standard-to-agentic-ai-founda-f70093cd [S]
6. Havoptic, Gemini CLI v0.67.0 — https://www.havoptic.com/r/gemini-cli-v0.67.0 [S]
7. SWE-TaskFlow, arXiv 2610.09633v2 — https://alphaxiv.org/abs/2610.09633v2 [R, özet]
8. Cursor changelog (es, 08-19-26) — https://cursor.com/es/changelog/08-19-26 ; Havoptic Cursor — https://www.havoptic.com/tools/cursor [P/S]
9. `gh issue list` on KBT-0/MyAgentKit_Keel, 2026-11-10 [F]
