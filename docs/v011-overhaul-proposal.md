# v0.11 elden geçirme ÖNERİSİ — review sistemi, worker döngüsü, gate ve release

Tarih: 2026-10-13. Durum: **ÖNERİ, uygulanmadı.** Her madde sahibin onayıyla, madde madde
uygulanır (sahip kararı, 2026-10-13: kit sahipsiz elden geçirilmez). Bağlayıcı kaynak:
`docs/research-ai-review-workflows.md` (master 247e040); M–O maddeleri ayrıca
`docs/research-token-optimization.md` (T) ve `docs/research-agent-kits-in-practice.md` (P)
raporlarına (master 733dc54) dayanır; her madde raporun numaralı bulgusunu
`§x.y` (yönetici özeti maddesi) ve `[n]` (kaynak) ile anar, kanıt olmayan yerde "raporda kanıt
yok" der. Kit'in amacı sahibin tanımıyla: **AI destekli uzun soluklu proje geliştirme için
best-practice kiti; review makinesi değil.**

## 0. Bizim kendi sayılarımız — RESEARCH_LOG'A TAŞINDI (13 Ekim)

12–13 Ekim review verisi (39 arşiv, bulgu dağılımı, süreler, en sık sınıflar) `RESEARCH_LOG.md`
13 Ekim "the kit's own numbers" girdisinde; F'nin `accepted=` oranı kayıtta.

## 1. Korunanlar (rapor §6; bu öneri bunlara dokunmaz)

- Taze bağlamlı, yazarı olmayan reviewer; throwaway kopya; sandbox (§6.1, [1][22]).
- Çapraz vendor ikinci model; AUTHOR/REVIEWER rol olarak kalır, vendor olarak değil (§6.2, [8][26]).
- Severity + `Fix sketch` + REPRODUCED/REASONED kanıt formatı; tek evidence formatı iki yönde (§6.4, [2][8]).
- Tam self-test, `check.sh --self-test`, "gate kırmızı görülmeden bitmez" (§6.5, [1][22][23]).
- Adaptörlerin mekaniği (`claude_bridge.py`, `codex_bridge.py`, `review_dispatch.py`, usage kayıtları, chain checkpoint'leri): **değişmez.** Elden geçirme politika, prompt ve ölçüm katmanındadır; kod değişikliği yalnızca D ve F'de.

## 2. Öneri maddeleri

Her madde: **Ne değişir · Nasıl · Neden (kanıt) · Risk · Efor · Dosyalar · Sahibin kararı.**
Efor: K = yalnız belge, bir oturum; O = küçük kod + killing test; B = yeni mekanizma, tasarım + test + review.

### A. Risk katmanlı, tek geçişli review — UYGULANDI (13 Ekim)

`REVIEW_GATE.md` "Risk tiers": low = gate + bir hafif review, medium = bir reviewer bir geçiş,
high = iki paralel dar reviewer (`REVIEW_FOCUS`); katmanı brief'in `Risk:` satırı seçer,
`REVIEW_RISK` prompt'a girer. Dar prompt'lar için yeni bayrak yok.

### B. Blocking eşiği — UYGULANDI (13 Ekim)

`REVIEW_GATE.md` "Verdicts and who decides" + "Findings and dispositions": Reject yalnız
Critical/High; Medium tek yerde ve testli ise aynı turda, değilse dosyalanır; Low dosyalanır;
`validate()` ve Codex Accept kontrolü Low/Pre-existing taşıyan Accept'e izin verir. Süren v0.11
işi için eski "Low'lar fix edilir" kararı geçerli kaldı (item F'de uygulandı).

### C. Yakınsama kuralı — UYGULANDI (13 Ekim)

Bir etiket altında iki tur; tur 2 yalnız Critical/High doğrulama + yeni Critical/High (prompt
söyler). Üçüncü deneme `prior_rounds()` içinde BridgeError (exit 2); yalnız
`REVIEW_ROUND_EXCEPTION=<neden>` açar ve kayıt nedeni taşır. Routing kural 4 silindi.

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
high katman review. **Karar (sahip, 14 Ekim).** 3 zaten zorunlu suite'lerde (boundary_restore,
check_gate, check_gate_windows, `check.sh --self-test`), yeni fixture yok; 4 yalnız eksik olan
tek test: 260+ karakterlik cwd'deki süreç worktree'sini korur. 5 upstream'e karşı diff'te,
`tests/` değişmeden eklenen ret satırı için NOTE.

### E. Reviewer prompt'u — UYGULANDI (13 Ekim)

`claude_bridge.REVIEW_PROMPT` (iki köprü aynı sabit; onaylı metin SP4BE/E-review-prompt-approved.txt):
alt eşik + tamlık cümlesi, kit'e özgü severity tanımı, "do not report" listesi, Low tavanı 5,
tur ≥ 2 daraltması, `REVIEW_TASK_FILE`/`REVIEW_RISK`/`REVIEW_FOCUS` bağlamı; Fix sketch kalktı.
Ölçüm F'nin `accepted=` oranıyla; precision görülmeden ikinci prompt değişikliği yok.

### P. Review kural dosyaları — UYGULANDI (13 Ekim)

`REVIEW_GATE.md` 742 kelime (sahip tavanı 600: kalan fark Priorities ya da saldırı listesini
kesmek demek, sahip kararı), `REVIEW_RUNNING.md` 626 kelime (env tablosu ≈130 kelime); AGENTS.md
üç satır + işaretçi, WORKFLOW yalnız routing/effort tabloları, SKILL.md ve cross-review.md
işaretçi. 89 kuralın kalır/birleşir/silinir listesi sahip onaylı; silinen 14'ün gerekçesi
`RESEARCH_LOG.md` (13 Ekim, "fourteen rules deleted").

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

### H. Review zaman kutusu ve yük — UYGULANDI (13 Ekim)

`REVIEW_TIMEOUT_SECONDS` 2700 varsayılan / 3600 tavan (`agent_process.py`, `review.sh`); iş
tavanı yok, bellek tek sınır; effort REVIEW_RISK'ten (high → high, diğer → medium; xhigh/max
review seçeneği değil). "model at capacity" otomatik retry'ı `docs/BACKLOG.md` satırı (sahip
kararı), mekanizma değil. İzleme: yükseltmeden sonraki ilk büyük review süresi ölçülür; 3600'de
kesilirse `MAX_REVIEW_TIMEOUT` sahibin kararı.

### I. Kod dışı değişiklik — UYGULANDI (13 Ekim)

Belge değişikliği low katman (`REVIEW_GATE.md` "Risk tiers"): gate + bir hafif review, bir tur,
bloklamaz; prose linter eklenmedi.

### J. İnsan "on the loop" — UYGULANDI (13 Ekim)

`REVIEW_GATE.md` "Verdicts and who decides": verdict girdidir, lead doğrular, sahip gönderime
karar verir; katman ataması brief'te, blast-radius diff'leri sahibin okumasından geçer, "yeter"
ve Medium'un kaderi sahibin.

### K. Çalışma modları ve routing — UYGULANDI (13 Ekim)

Üç mod: solo (varsayılan) / normal / saver (`WORKFLOW.md` "Working modes, by name";
`working_mode.py` eski adı reddeder ve eşlemeyi basar). "A mode never lowers a change's tier";
routing kural 4 silindi, effort tablosu review satırı H'ye göre.

### L. Açık soru: `claude@NAME` (GLM gibi Anthropic-uyumlu backend) ikinci model sayılır mı?

**Öneri: EVET.** Dekorelasyonun kaynağı model ailesidir, CLI değil ([26] Nine Judges: etkin
bağımsızlık model ailesine göre; [8] "farklı agent'lar ortak kör noktayı paylaşmaz"). GLM/Kimi
başka bir ailedir; aynı Claude CLI'dan geçmesi bağımsızlığı azaltmaz, çünkü sandbox/prompt aynı
olsa da ağırlıklar farklıdır. Kayıt tarafı: usage kaydı `model` alanına backend'in gerçek model
adını yazmalı (attestation `modelUsage` ile mümkün mü, backend'e bağlı; mümkün değilse "requested,
unattested" — Codex'teki gibi). **Efor.** K (REVIEW_GATE "roles not vendors" paragrafına bir
cümle) + backend dalındaki kayıt alanı (O, dal zaten açık). **Karar (sahip, 13 Ekim).** EVET;
gerçek model adı kayda girer, attest edilemezse "requested, unattested".

### M. Token ve bağlam tasarrufu — UYGULANDI (13 Ekim)

M-1 `CLAUDE_CODE_SUBAGENT_PROMPT_CACHE_TTL=1h` spawn ortamında + overlay settings `env`, frontmatter
`cacheTtl` kalktı; M-2 = H; M-3 overlay settings `promptCacheTtl`/`subagentPromptCacheTtl` 1h
(claude-code-guide ile doğrulandı: v2.1.242+); M-4 `docs/context-is-a-budget.md` "Compaction is a
purchase too" + WORKFLOW kural 8; M-5 WORKFLOW fork maddesi (lead <120k); M-6 `agent_cost.py` `hit`
sütunu (hedef %80), kayıt zaten `total_cost_usd`/`modelUsage`/TTL kovasını taşıyordu. Düzeltmeler
(cache gerekçesi, MCP katalogu, effort geçişi) ve retler aynen uygulandı.

### N. Talimat dosyalarının yüklenmesi — N-1, N-2 UYGULANDI (13 Ekim); N-3/N-4 v0.12

N-1 ölçüm `RESEARCH_LOG.md` (13 Ekim, "startup prefix measured"): 244 satırlık AGENTS.md ilk istekte
5.828 token, 165 satırlık harita 4.124 (−%29); sahibin kontrolü dışındaki prefix 16k yazma + 16k
okuma. N-2: `core/AGENTS.md` 165 satır harita (tavan 200, sahip kararı), review paragrafı üç
satır + işaretçi, STATE disiplini `core/docs/AGENTS.md` + overlay `.claude/rules/state.md`
(`paths: docs/**`). N-3 (`omitClaudeMd` + Haiku teşhis agent'ı) ve N-4 (`/skill-doctor`,
`disable-model-invocation`) v0.12.

### O. Emsalsiz pratikler — KARAR VERİLDİ (13 Ekim)

"Emsalsiz = kötü" anlık yorumdu, kalıcı kural değil; her satır kendi kanıtıyla: çapraz-vendor
döngüsü → A+B+C (uygulandı); yedi mod → üç mod (K, uygulandı); cache-TTL modeli → M (uygulandı);
Done trailer → `check.sh` sensoru (D sınıfı, açık; silme yine zorlanır); gate-red kuralı → D-5
sensoru (açık); PII yasağı ve spawn'ın model/effort zorunluluğu korunur.

### Q. Mandate — UYGULANDI (13 Ekim)

Kit tek model ailesiyle çalışır; "diğer model" = taze oturum, tercihen başka tier; ikinci vendor
(Codex, `claude@NAME`) takılabilir, hiçbir gate ikisini birden istemez. GATE "Invariant", WORKFLOW
solo modu, prompt ve iki kural dosyası tek-model dilinde.

### R. Sahiple iletişim kuralları — UYGULANDI (14 Ekim), review bekliyor

`docs/research-communication-style.md` raporunun 16 önerisinin hepsi v0.11'e (sahip kararı,
14 Ekim; v0.12 sonradan açılan issue'lar için). Tek kural dosyası `core/docs/COMMUNICATION.md`
(AGENTS.md "Language & style" oraya işaret eder; output style dosyası yok, tek stil sahibi
AGENTS.md); `core/docs/GLOSSARY.md` iki liste (sahibin bildiği terimler mülakat sorusu 12'den,
kit terimleri açıklanır); `{{CHAT_LANGUAGE}}` ve `{{KNOWN_TERMS}}` yer tutucuları; HANDOFF
"Owner summary" katmanı; worker/diff-reviewer çıktı biçimi; iki hook (sahip kararı: ikisi de
bloklayan/aktif): `plain_report.py` (Stop; etiket geçen son mesajı bir kez geri çevirir) ve
`progress_reminder.py` (PostToolUse; beş sessiz çağrıda bir satır). Ölçüm (öneri 15): dogfood
gününde sahip her raporu "anladım / bir yeri anlamadım / tekrar sordum" diye işaretler, hook
tetiklenme ve "bu ne demek" sayısı RESEARCH_LOG'a. Rapor kendi kanıt boşluğunu söylüyor
(hook'ların yan yana ölçümü yok, sahip anlayışı ölçülmemiş): bu yüzden ölçüm de v0.11'de.
Risk: high (hook + settings); etiketler v011-comm-logic / v011-comm-portability, brief
`.myagentkit/comm-brief.md`.

## 3. Uygulama sırası (sahip onayı 13 Ekim)

| Sıra | Madde | Neden bu sırada |
|---|---|---|
| 0 | F (ölçüm) — UYGULANDI | Ölçmeden değiştirmek raporun kendi uyarısına aykırı (§4) |
| 1 | A, B, C, H, I, J, K UYGULANDI; G adım 10 (release) | Tek belge görevi, tek oturum, tek low/medium geçiş (I'ya göre); worker değil lead yazar, çünkü kuralların gerekçesi bu dokümanda |
| 2 | E + P — UYGULANDI | Politika oturduktan sonra prompt ve iki kısa dosya onu söyler; P'nin envanter kararı E ile aynı oturum |
| 3 | D-1 ve D-2 (locale matrisi, shell lint) | En sık iki sınıf; gate kodu olduğundan A'nın full katmanı |
| 4 | D-3…D-5 | v0.11 (sahip kararı); sıra sıklığa göre |
| 4b | R (iletişim) — UYGULANDI, review bekliyor | Rapor 14 Ekim'de geldi; D-5 review ile aynı günde |
| 5 | L | Backend dalı merge edilirken |
| 1b | M, N-1, N-2, O — UYGULANDI; N-3/N-4 v0.12 | Politika belgeleriyle aynı oturum; N-3/N-4 v0.12 |

## 4. Süren v0.11 işine uygulanışı — MERGE'LER BİTTİ (13 Ekim)

Yedi dal master'a merge edildi, `check_kit` yeşil (`RESEARCH_LOG.md` "Merging seven v0.11
branches"); §0 tablosu RESEARCH_LOG'a girdi. Kalan: G'nin release yolu (tam self-test + CI → bir
final review, Claude high, NEW label → yalnız Critical/High fix → bir gün dogfood → push).

## 5. Sahibe sorular (cevaplananlar silinir)

Hepsi cevaplandı (13 Ekim batch). Doküman yaşam döngüsü: uygulanan madde silinir, kapanınca
dosya silinir (sahip kararı, soru 11).
