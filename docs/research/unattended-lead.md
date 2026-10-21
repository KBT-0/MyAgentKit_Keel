# Lead'i gözetimsiz bırakmak (gece, uzun yokluk): kaynaklı araştırma ve v0.13 mod önerisi

Tarih: 2026-10-22. Yalnız araştırma; kitte kod değişmedi.

**Soru (sahip, 2026-10-22 ~02:00, birebir):** "bu şuan senden istediğim şeyi yani gece yatmadan ya da bilgisayar başından
uzun süre ayrılmadan önce agent'ları daha doğrusu lead'leri çalışmaya başlatmak, bunun için promtlamak kurallar koymak fln
hususunda bi araştırma yapalım, insanlar bu durumlar için neler yapmış neler öneriyor bi bakıp kaynakçalandırıp bu durum
içinde güzel isimli bir mod yapalım v13'de bundan sorna çalışmaya bırakmadan önce o modu başlatıp projeyi kit sayesinde
lead oturuma bırakıp rahatlıkla gidebileyim."

**Modun yakalaması gereken davranış (sahibin aynı gece verdiği yetki, birebir):** "sen sabaha kadar çalış durduraksız,
sabah geldiğimde mevcut işleri bitir yahut ilerleyebildiğin kadar ilerlemiş ol ama saçma sapan bir bahaneyle durduğunu
görmiyim sabah. Soruların varsa sor, yoksa biriktirip sabah sor. Bu süreçte kararları sen al, insiyatif alma hakkına
sahipsin ama bunları sabah bana bildir."

**Ek kapsam (lead'den, sahibin sözü, 2026-10-22 ~02:40, bağlayıcı, birebir):** "Ben yokken alman gereken kritik/radikal
kararlar olur, bana sorman gereken yerlerde benim yokluğumda eğer bu claude aboneliği kapsamında varsa fable'a yoksa
opus-high'a taze workerda fln sorabilirsin." Lead'in aktardığı anlamı: gözetimsiz modda sahibe sorulacak kritik ya da
radikal bir karar (kapsam, sahibin bir kuralı, geri alınamaz bir adım) varsayılan olarak park edilmez; lead taze bir
oturumda aboneliğin en güçlü modeline (varsa Fable 5.1, yoksa Opus 5.5 high) karar danışması yapabilir, buna göre
davranır ve danışmayı (soru, vekilin cevabı, lead'in yaptığı) sabah raporuna yazar. Bu kısım bölüm 5.7'de.

> **Önerilen karar (sahip onaylamadı):** v0.13'te `nightwatch` adlı bir **bulunma anahtarı** (presence), dördüncü bir
> çalışma modu değil; solo/cross/saver'ın hangisiyle olursa olsun birlikte açılır. Sahip çıkarken `/myagentkit:mode
> nightwatch` ve önerilen `/goal` satırını çalıştırır; lead etkileşimli ön plan oturumunda kalır, kapsam bitene ya da
> geçerli bir durma koşulu gelene kadar durmaz, geri alınabilir kararları kendi alır, kritik olanı vekil modele danışır,
> geri alınamaz ya da dışa dönük olanı hiç yapmaz, hepsini git'ten kurulan bir sabah raporunda bildirir (bölüm 5).

Etiketler: **P** vendor birincil doküman ya da resmi kod, **R** makale/standart, **B** blog/pratisyen, **F** forum/issue,
**S** ikincil kopya, **K** kitin kendi kanıtı. Güç: **güçlü** (vendor dokümanı, standart, hakemli), **orta** (preprint,
ayrıntılı ve sayılı pratisyen yazısı, vendor blogu), **zayıf** (anekdot, forum, ikincil). Kaynak numaraları `[n]`, liste
bölüm 6'da. `(yazar)` işaretli kaynakları bu raporun yazarı kendisi okudu ([1] kısmen, [3][4][5][6]); diğerlerini beş
araştırma yardımcısı (Sonnet 5.5, high effort) okudu ve raporları satır satır yeniden okunmadı: yardımcının okuması kadar
iyidirler. **Çıkarım** işaretli cümleler bu raporun kendi yargısıdır; **"lead'in yargısı, kaynaksız"** kaynağı olmayan
öneridir. Süreler: ölçülmüş agent süresi yoksa "ölçülmedi" (`BEHAVIOUR.md`; `docs/research/agent-durations.md`).

---

## 1) Kısa özet

1. **Gözetimsiz çalışmanın üç ayağı her kaynakta aynı: önceden yazılmış kapsam ve "bitti" ölçütü, makinece uygulanan durma
   koşulları, dosyada tutulan durum ve sonda bir rapor.** Anthropic (ilerleme dosyası + git + tek seferde bir iş [20];
   "çalıştırabileceği bir kontrol ver… izlediğin oturumla bırakıp gittiğin oturum arasındaki fark bu" [15]), OpenAI
   (spec'te "Done when", milestone başına doğrulama, karar kaydı tutan bir status dosyası [41]), Devin (kapsam, sınır,
   başarı ölçütü; checkpoint'te rapor [46]), AWS (süre, token bütçesi, sonlandırma tetikleyicileri önceden [92]).
2. **Claude Code'da gece çalışmasını taşıyan yerleşik parçalar artık var, ama her birinin keskin bir sınırı var.**
   `/goal` her turdan sonra küçük bir modelle koşulu denetleyip yeni tur başlatır, usage limit'te durup reset sonrası
   devam eder [3] (yazar); etkileşimli oturum usage limit'te bekleyip reset sonrası kendiliğinden devam eder, ama yalnız
   **görev ortasında** limite takılırsa, oturum açık kalırsa, en fazla iki kez üst üste, reset 24 saatten yakınsa ve
   makine 30 dakikadan uzun uyumadıysa; arka plan oturumu ve `-p` bu beklemeyi hiç almaz [4] (yazar). Stop hook
   durmayı engelleyebilir; sekiz ardışık engelden sonra Claude Code geçer, sayaç her araç çağrısında sıfırlanır [1][2].
3. **Sahibin gördüğü "bahaneyle durma"ların her biri bilinen bir mekanizmaya bağlanıyor** (bölüm 4): temiz biten bir tur
   otomatik devamı boşa çıkarır [4]; `AskUserQuestion` varsayılan olarak sonsuza dek açık kalır, zaman aşımı ayarlansa bile
   terminal penceresi odaktayken sayaç işlemez ve arka plan oturumunda hiç başlamaz [6] (yazar); izin istemleri boşta
   asla kendiliğinden çözülmez [6]; auto mode 3 ardışık ya da 20 toplam engelde istem moduna döner [5] (yazar). Kitin
   bugünkü kuralları bunların bir kısmını yazılı olarak kapatıyor (`core/docs/COMMUNICATION.md`, "Questions and
   approvals"; `core/docs/WORKFLOW.md`, "Worker cost" kural 8), ama hiçbiri makinece uygulanmıyor.
4. **Sınırlı özerklik kaynakları aynı çizgiyi çiziyor: geri alınabilir ve çalışma alanının içindeki işler serbest;
   geri alınamaz, dışa dönük, paylaşılan durumu ya da kimlik bilgisini değiştiren işler insana kalır; onay bekleyen iş
   sonsuza dek beklememeli, güvenli varsayılana düşmeli.** AWS'nin üç katmanı (otonom / bildir / onayla, etki ve geri
   alınabilirliğe göre) ve "zaman aşımı olmayan onay akışı" anti-pattern'i [90][91]; Claude Code auto mode'un varsayılan
   engel listesi [5] (yazar); OWASP "Least-Agency" [97]; Feng ve ark. L4 "onaylayıcı" seviyesi: kullanıcıyla yalnız
   engel çözmek için konuşur [102].
5. **Pratisyenlerin gece döngüleri (Ralph, `claude -p` while döngüsü, continuous-claude) işe yarıyor ama aynı hatalarla:**
   yer tutucu kod, sahte "bitti", kapsam kayması, testleri gevşetme, sessiz duruşlar, uyuyan makine [66][67][68][71][73].
   Kalıcı dersleri: tek seferde bir iş, git commit'i checkpoint, bir notlar/ilerleme dosyası, maliyet/iterasyon/süre
   tavanı, testi silmeyi yasaklayan satır, raporun öz-beyandan değil git'ten kurulması [20][71][72][97].
6. **Vekil modele danışmanın (ek kapsam) güçlü vendor emsali var, ama hiçbir kaynak vekilin kararını insan onayı saymıyor.**
   Anthropic'in advisor aracı ve Claude Code advisor'ı, Amp'in Oracle'ı, Aider'ın architect modu: daha güçlü model
   danışmandır, karar ve eylem yürütücüdedir [17][25][62][63]. Aynı aileden yargıçlar ortak kör noktaları paylaşır
   [114][115]; soruyu kendi önerinle birlikte sormak danışmanı çapalar [117][118]. Sonuç: danışma geri alınabilir
   kritik kararlarda kullanılır; geri alınamaz ve dışa dönük işler yine sahibe kalır (bölüm 5.7).
7. **Öneri:** bulunma anahtarı `nightwatch` + yerleşik `/goal` (sıfır kod) + bulunmaya duyarlı hook metinleri + bir soru
   ve karar kuyruğu dosyası + git'ten kurulan sabah raporu + çıkış öncesi kontrol listesi (güç, otomatik devam, izinler).
   Kendi Stop hook'umuz yalnız `/goal` dogfood'da açık bırakırsa (bölüm 5.6).

En büyük belirsizlik: bu mekanizmaların birlikte, native Windows'ta, bir gece boyunca nasıl davrandığını ölçen bir kaynak
yok; her biri ayrı belgelenmiş. İlk gece bir dogfood ölçümüdür.

---

## 2) Kitte bugün olanlar (mod bunları genişletir, kopyalamaz)

- **`core/docs/COMMUNICATION.md`, "Questions and approvals" (While the owner is away):** "away" = sahip söyledi ya da
  sorulan soruya 45 dakika cevap gelmedi; kurallar karara bağlıyorsa ya da geri alınabilirse karar ver ve sonra bildir;
  değilse işi sabahki cevap tek bir adlandırılmış yeri değiştirecek biçimde yap; değilse issue ya da `docs/STATE.md`
  satırıyla park et ve başka işe geç; AWS AGENTSEC04-BP02'ye atıf. **Eksik:** "away" bir çıkarım (45 dk), açık bir anahtar
  değil; kritik karar için vekil danışma yok; sabah raporunun biçimi yok; hiçbir kural makinece uygulanmıyor.
- **`core/docs/WORKFLOW.md`, "Working modes, by name":** solo/cross/saver yalnız "kim yazar, kim review eder, kim düzeltir"i
  belirler; `scripts/working_mode.py` ve `/myagentkit:mode` `docs/STATE.md`'deki "Working mode:" satırını ve
  `.myagentkit/mode` dosyasını yazar; mod "asla bir review'u kaldırmaz… ajanlar ne kadar uzun gözetimsiz çalışırsa
  bağımsız kontrol o kadar önemli" der [15].
- **`core/docs/WORKFLOW.md`, "Worker cost" kural 8:** bağlam bandı 200k/300k/400k; "sahip yokken lead hand-off dosyasını
  yazar, iş sürüyorsa `/compact` çalıştırır ve devam eder; cevap beklemez". Aynı kuralda "bir kez sıkıştırılmış oturum
  tekrar sıkıştırmak yerine devreder" de var; gece devri açacak kimse yok (bölüm 4, B2).
- **`core/BEHAVIOUR.md`:** "Never end running work … without a valid reason"; "A decision made for one moment ends with
  that moment".
- **Lead'in gece zaten uyduğu hafıza kuralları (K):** usage-limit uyarısında asla toparlama, çünkü temiz biten tur
  otomatik devamı boşa çıkarır (2026-10-20, sahip öfkeli); sahip yokken bağlam uyarısında durma (2026-10-12'de lead
  23:35'te durdu, gece kaybedildi: "niye durdun, gece devam edip bitirseydin sabaha kadar"); limitler sahibin işi;
  worker bittiğini diskteki RESULT söyler, `notify_when_idle` 5'ten 4'ünü kaçırdı; çalışan işi geçerli sebep olmadan
  bitirme.
- **Teslim mekanizmaları:** `overlays/claude-code/files/.claude/hooks/`: `gate_on_stop.sh` ve `plain_report.py` (Stop),
  `context_size.py` (bant), `progress_reminder.py`, `after_compact.txt` (SessionStart compact), `guard_*`. Brief'in
  andığı `suggestions.py` bu ağaçta yok; `plugin/` yalnız komutlar taşıyor (`mode.md`, `handoff.md`…), mod/`hooks.json`
  yok (2026-10-22 kontrol). `plain_report.py` sonu soruyla biten final mesajını zaten geri çeviriyor.
- **Issue #303 ve `.myagentkit/v012/wkhandoff-brief.md`:** iki worker ikinci sıkıştırmada (~80k) sıfır kodla devretti;
  düzeltme "sıkıştırma asla durma sebebi değildir". Gece modu aynı ilkeyi lead'e genişletir.
- **Bağlayıcı araştırma tabanı:** `docs/research/context-limit.md` (bant yargıdır, ölçüm değil; sıkıştırma kayıplıdır,
  Özet 3); `docs/research/worker-orchestration.md` (bitti sinyali diskteki sonuç dosyası, Özet 6; arka plan oturumu
  terminal kapanınca ve uykuda yaşar, Özet 1; worktree izolasyonlu bg oturumu dal itip draft PR açar, bu yüzden
  `bgIsolation: none`, Özet 2); `docs/research/ai-review-workflows.md` (yalnız Critical/High bloklar, Özet 5; tur sayısı
  azalan getiri, Özet 8); `docs/research/agent-durations.md` (duvar saati agent çalışması değildir, bekleme ayrı, Özet 5).

---

## 3) Bulgular

### A. Claude Code mekanizmaları (P, güçlü; hepsi 2026-10-22 kontrol)

**A1 — Stop hook durmayı engelleyebilir.** `decision: "block"` + `reason` ya da çıkış kodu 2: "Prevents Claude from
stopping, continues the conversation" [1] (yazar). Girdi `stop_hook_active`, `last_assistant_message`, `background_tasks`
ve `session_crons` taşır [1]; sonuncu ikisi bir hook'un "bu oturumu uyandıracak bir şey kaldı mı" sorusunu cevaplamasını
sağlar (çıkarım). Sınırlar: "after stop hooks have continued the turn eight times in a row, Claude Code overrides the next
block … The count … resets each time Claude calls a tool"; `CLAUDE_CODE_STOP_HOOK_BLOCK_CAP` sınırı yükseltir [1][2];
kullanıcı kesmesinde ve API hatasında Stop çalışmaz (API hatası `StopFailure`'a gider, çıktısı yok sayılır) [1]; bozuk
bir hook betiği durmaya izin verir [1]. `"continue": false` her şeyi durdurur, devam için asla kullanılmaz [1].
Pratisyen uyarısı: bir HN başlığında bir Stop hook'u model sürümü değişince "çalışmaz" oldu, yorumcular çıkış kodu 2'nin
şart olduğunu hatırlattı [83] (zayıf).

**A2 — `/goal` yerleşik bir "durma, koşul sağlanana kadar devam et" döngüsüdür** [3] (yazar): "a wrapper around a
session-scoped prompt-based Stop hook"; her turdan sonra küçük hızlı model koşulu yalnız konuşmadan değerlendirir
(araç çalıştırmaz). Durur: koşul sağlandı, imkânsız görüldü, sahibin düzeltmesi gereken hata (kimlik doğrulama, biten
kredi, sıkıştırmanın temizleyemediği taşma, model yok). Duraklar ve sonra sürer: "a claude.ai usage limit … `Goal
paused` … If the session is waiting to continue automatically when a usage limit resets, Claude resumes work toward the
goal then." Arka plan işi değerlendirmeyi erteler; iş bitince sonuç yeni bir tur olarak gelir; 30 dk sonra bir check-in,
sonra 1 sa, sonra 2 sa; **iki istem arasında en fazla üç boşta check-in**. "or stop after 20 turns" gibi bir tur/zaman
cümlesi koşula yazılabilir. Birkaç tur araç çağrısı olmazsa döngü durur. Bir oturumda tek hedef; `/clear` hedefi siler;
resume hedefi geri getirir (tur sayacı sıfırlanır). `/goal` izin modunu değiştirmez: "To let goal turns run unattended,
run `/goal` in auto mode."

**A3 — Usage limit'te otomatik devam** [4] (yazar): "When a claude.ai usage limit stops Claude mid-task, Claude Code waits
in the open session and continues the task on its own after the limit resets … on by default … v2.1.234 or later";
ayar `autoContinueAtUsageLimit`. Sınırlar, birebir: "Keep the session open"; uyku 30 dakikayı aşıp reset uykuda olduysa
"Press enter to continue"; "Claude Code still asks for permissions as usual, so the task can stop on a prompt while you're
away"; "re-arms the wait on its own at most twice in a row, then stops"; reset 24 saatten uzaksa (haftalık limit)
kendiliğinden başlamaz; çıkış, `/clear`, `/resume`, bg oturumuna devir beklemeyi bitirir; "Background sessions and `-p`
runs: the menu row isn't available." **Çıkarım:** limit "görev ortasında" durdurursa devam eder; tur temiz bitmişse
devam edecek görev yoktur. Hafızadaki 2026-10-20 olayı bununla uyumlu.

**A4 — Sorular ve izin istemleri gece takılır** [6] (yazar): "Questions stay open until you answer them." Zaman aşımı
`askUserQuestionTimeout` (`60s`, `5m`, `10m`) diyaloğu kapatır ve Claude'a "you may be away" der, ama: "While your
terminal reports that its window is focused, the timer doesn't count down"; "The timer never starts for a question Claude
asks in a background session"; "permission prompts, including plan approval, never auto-resolve on idle." Auto mode'da
kritik yol silme istemi iki dakikalık geri sayımla reddedilir, "so an unattended session keeps working" [5] (yazar).

**A5 — Auto mode'un engel listesi ve geri düşüşü** [5] (yazar). Varsayılan engeller arasında: "Irreversibly destroying
files that existed before the session", "Force push", "Production deploys and migrations", "Granting IAM or repo
permissions", "Modifying shared infrastructure", "`git reset --hard`, `git checkout -- .`, `git restore .`, `git clean
-fd`, `git stash drop`", "Merging a pull request no human has approved, approving Claude's own pull request, or disabling
CI checks", "Sending sensitive data to external endpoints". Varsayılan olarak serbest: çalışma dizininde yerel dosya
işleri, çalışılan reponun herhangi bir dalına push (yardımcı raporu [5]). Geri düşüş: "if the classifier blocks an action
3 times in a row or 20 times total, auto mode pauses and Claude Code resumes prompting"; eşikler ayarlanamaz; `-p`'de
"the action doesn't run and Claude keeps working". Konuşmada verilen sınır sıkıştırmada kaybolabilir; kalıcı garanti için
ask/deny kuralı [5]. "Auto mode reduces permission prompts but does not guarantee safety" [5].

**A6 — Arka plan oturumları, `/loop`, cron, bulut görevleri.** `claude --bg`: terminal kapanınca ve uykuda yaşar, kapanış
ve yeniden başlatma durdurur, bir saattir bağlanılmamış bitmiş oturumun süreci durur, izin isteminde "Needs input" olarak
bekler [9]; usage limit beklemesi yok [4]. `/loop` ve cron: "Tasks only fire while Claude Code is running and idle";
yinelenen görevler 7 günde söner; kaçırılan tetik telafi edilmez; `ScheduleWakeup` 1 dk–1 sa; yeniden planlanmayan
iterasyondan ~20 dk sonra tek bir yedek uyandırma [10]. Bulut zamanlanmış görevleri makine kapalıyken çalışır ama taze
klonda, en az 1 saat aralıkla ve izin modu seçilmeden [11]. Yerel etkileşimli oturumda arka plan Bash komutlarının süre
sınırı yok; `-p`/SDK/bulutta var [6] (yazar). Monitor izlemesi en çok 30 dakika [6].

**A7 — Headless `-p`.** `--max-turns` ve `--max-budget-usd` yalnız print modunda vardır [8]; `--bare` hook'ları ve
CLAUDE.md'yi atlar [7]; `--permission-prompts none` istemleri reddeder ve `AskUserQuestion`'ı kaldırır [7]. Kitin lead'i
hook'lara dayandığı ve sahip oturumları kendi açtığı için `-p` lead'e uymaz (çıkarım).

**A8 — Sıkıştırma ve cache.** `autoCompactWindow` (kitte 450k) [13]; ana konuşma abonelikte 1 sa TTL, sub-agent ve
sıkıştırma 5 dk; 1 saatlik TTL'deki boşta uzun konuşma cache bitmeden sıkıştırılabilir (`idleCompaction`) [14].

**A9 — "Erken durma"ya karşı vendor'ın kendi prompt satırı** [19]: "do not stop tasks early due to token budget concerns …
Always be as persistent and autonomous as possible and complete tasks fully … Never artificially stop any task early
regardless of the context remaining"; sayfa yoksa Claude'un "might sometimes naturally attempt to bring its work to a
close as it approaches the context limit" dediğini söylüyor. Aynı sayfa yıkıcı ya da zor geri alınır işlerden önce
sormayı ve "do not use destructive actions as a shortcut" der [19]. Not: bağlam farkındalığı listesinde Opus ve Fable
adı geçmiyor [19].

**A10 — Uzun koşum tasarımı** [20]: her yeni oturum hafızasız başlar; `claude-progress.txt`, git ile geri alma, tek
seferde bir özellik, JSON özellik listesi (model JSON'u Markdown'dan daha az bozuyor), "It is unacceptable to remove or
edit tests". Claude Code best practices: "Give Claude a check it can run … the difference between a session you watch and
one you walk away from"; kapı merdiveni prompt → `/goal` → Stop hook → doğrulama sub-agent'ı; "The longer Claude works
unattended, the more an independent check matters" [15]. Agent SDK: sınırsız döngü açık uçlu işte uzun sürer, bütçe iyi
varsayılan [24]. Anthropic "Building effective agents": "stopping conditions (such as a maximum number of iterations)",
"pause for human feedback at checkpoints or when encountering blockers" [21]. Vendor beyanı: Sonnet 4.5 karmaşık işte
"more than 30 hours" odak [22] (orta; lansman iddiası).

**A11 — Mod (plugin) API'si** [16]: bir mod araç çağrısını tutabilir, istem gönderebilir ("submit a prompt as if you had
typed it"), başka bir oturuma mesaj atabilir, "Act without asking you". Zamanlayıcı API ayrıntısı doğrulanmadı.
Pluginler `hooks/hooks.json` taşıyabilir [16].

**A12 — Windows host.** Native Windows'ta sandbox desteklenmiyor [18]. `SetThreadExecutionState` boşta uykuyu engeller,
kapak kapatma ve güç düğmesini engelleyemez [121]. PowerToys Awake: "active only when you are signed in"; kilit ekranında
çalışmaya devam eder; `--pid` ile bir sürece bağlanabilir; kullanıcının başlattığı uykuyu engellemez [122]. `powercfg
/requests` ve `/change standby-timeout-ac` var [123]. Modern Standby'da süreç kısa patlamalara iner [121]. Gece Windows
Update yeniden başlatması riski yalnız bir barındırma firmasının rehberinde [74] (zayıf).

### B. Diğer vendor'lar (P ve vendor blogu)

**B1 — Kapsam önceden ve planla:** Cursor uzun koşan agent'ları planı önerir ve onay bekler, sonra sahip "step away"
edebilir [43]; Jules planı onaya sunar, "You are free to leave Jules while it is running" ve "notified when the task
completes or needs your input" [59]; Devin kapsam, sınır ve başarı ölçütü ister, "There are no success criteria and no way
for Devin to know when it's done" kötü örnektir [46]; playbook'ta "Forbidden Actions" ve "Required from User" bölümleri
[47]; Copilot coding agent açık kabul ölçütü ister, "Production-critical issues" insana kalır [51]. Cognition: Devin
"clear upfront scoping"i iyi, iş ortasında gereksinim değişikliğini kötü karşılar [48].

**B2 — Durma koşulları üç türde:** duvar saati (Copilot oturumu en çok 59 dakika [51]); maliyet/iterasyon tavanı ve
zarif çıkış (SWE-agent `per_instance_cost_limit` 3.0, aşılınca eldekini "autosubmit" eder [57]; OpenHands
`max_iteration_per_run` 500 ve `max_budget_per_run` [55]; Copilot CLI'da yumuşak tavan: "the agent wraps up and lets you
know" [53]); ve bir yargıç ya da hedef değerlendiricisi (Cursor her döngü sonunda "a judge agent determined whether to
continue" [44]; Codex kalıcı `/goal` iş akışları [38]).

**B3 — Takılma tespiti:** OpenHands varsayılan açık detektör: aynı eylem-gözlem 4+, eylem-hata 3+, monolog 3+, ping-pong
6+ döngü [56]; Devin oturum limitinin amacı "doesn't get stuck in a loop of doing the same action … over and over" [49];
Cursor "Agents occasionally run for far too long" ve "periodic fresh starts to combat drift and tunnel vision" [44].

**B4 — Soru sorma:** Devin yalnız emin değilken bekler, "Otherwise, it will proceed automatically and accept async
feedback" [48]; Codex zamanlanmış görevleri `approval_policy = "never"` ile ve "narrowest access" ile çalıştırır [40];
`--ask-for-approval never` yalnız dar sandbox ile önerilir [37]; Factory `droid exec` seviyesinin üstündeki eylemde durur,
hata yazar ve sıfır olmayan kodla çıkar, "Exit `0` means Droid finished, not that the task succeeded" [61].

**B5 — Rapor:** PR + oturum günlüğü, "Logs do not replace your own review and testing" [51]; Copilot'un push'undan sonra
Actions insan onayı olmadan çalışmaz [52]; Codex'te zamanlanmış görünüm "acts as your inbox" [40]; Devin Session Insights
koşum sonrası "Issues Detected", "Timeline", "Action Items" üretir [50]; OpenAI'nin 25 saatlik deneyinde
`documentation.md` "status and audit log with decisions" tutar ve plan dosyasında "Stop-and-fix rule" vardır [41].
Uzun koşum iddiaları vendor beyanıdır: GPT-5-Codex "more than 7 hours" [42] (ikincil), OpenAI deneyi ~25 saat, "not
perfect or production-ready" [41]; Cursor 25–36 saat örnekleri [43].

**B6 — Ortam hazırlığı:** Amp'in orb notu: her yeni ortamda `.agents/setup`, her uyanışta `.agents/resume`; iç içe
`AGENTS.md` "what not to do" söylemeli [60]. Bir Cursor forum kullanıcısı: "make every checkpoint name the commit SHA,
exact tests, preserved invariants, and the next safe resume point" [89] (zayıf).

### C. Pratisyen raporları (B, F)

**C1 — Ralph döngüsü** [66] (orta): `while :; do cat PROMPT.md | claude-code ; done`; spec dosyaları, sık yenilenen
`@fix_plan.md`, "one item per loop"; otomatik durma yok, insan izler; hatalar: yer tutucu uygulamalar, çift uygulama,
"you'll wake up to a broken codebase that doesn't compile from time to time", repoda çöp; mevcut kod tabanında asla.
Maliyet ~10 $/saat [69]. Anthropic'in plugin'i: Stop hook aynı istemi geri besler, `--completion-promise` tam metin
eşleşmesi (birden çok bitiş durumu taşıyamaz), "Always rely on --max-iterations as your primary safety mechanism"; 15
iterasyon sonra engeli yazma önerisi; insan yargısı isteyen işlere uygun değil [33]. HumanLayer: döngüyü uzun koşturmak
"bizarre emergent behavior"; spec'leri okumadan bırakınca "The output sucked"; plugin'in Stop hook'u dizindeki tüm
oturumlara uygulanıyor, "for now I'll keep my 5-line bash loops" [68].

**C2 — repomirror** [67] (orta): `claude -p --dangerously-skip-permissions` while döngüsü, birkaç VM; her düzenlemeden
sonra commit; `.agent/` notlar; 103 kelimelik kısa istem 1.500 kelimelikten iyi; ~800 $, Sonnet ajanı başına ~10,50
$/saat, ~1.100 commit; iş bitince ajanlar test yazmaya ve TODO güncellemeye kaydı; kapsam kayması; "90% to 100%" için
insan gerekti.

**C3 — continuous-claude** [71] (orta): her iterasyon dal + PR + CI, başarılıysa merge, değilse at; `SHARED_TASK_NOTES.md`
"a clean handoff package between runs"; bayraklar `--max-runs`, `--max-cost`, `--max-duration`, tamamlanma sinyali 3 kez
üst üste, `--stall-threshold` (insan için tanı yazıp duraklar). Notlar yoksa model "go in circles".

**C4 — Gece betikleri:** auto-claude: kuyrukta görev dosyaları, görev başına worktree, `VERIFY_CMD`, bir düzeltme turu,
`MAX_BUDGET_USD`, kilit dosyası, limit sonrası uyu-devam; testleri silmeyi yasaklayan istem; sabah
`logs/report-<timestamp>.md` (görev başına geçti/kaldı, dal, diffstat, süre, maliyet); "I'm not describing that as a
sandbox, because it isn't one" [72] (orta). launchd gecelik işi 14 gecenin 6'sında çalıştı: PATH yok, `-p`'de araç
reddi ve çıkış kodu 0 ile "polite apology", dizin `/` olduğu için CLAUDE.md yüklenmedi, laptop uyuduğu için 5 saat geç;
çare çıkış kodu değil çıktı dosyasını denetlemek [73] (orta).

**C5 — Anthropic personeli** [75] (orta): çok uzun görevlerde ya bitince arka plan agent'ıyla doğrulatma, ya bir Stop
hook, ya ralph-wiggum plugin'i; izin için sandbox'ta `dontAsk` ya da skip-permissions. Willison: YOLO modunda "a rogue
agent can do anything that you could do"; sandbox, internetsiz konteyner, para harcayan kimlik bilgisine sıkı bütçe [76].

**C6 — "Durma"ya karşı prompt satırları (zayıf–orta):** "When a step doesn't need my input, keep going … Stop and ask only
when you can't continue without me, or before anything destructive" [77]; saate bağlama: "Check server time … if it's still
before 11:10AM PT then define more work blocks … do not stop or ask any questions" [78]; karar kaydı: "Decide yourself,
then record: the decision, the alternatives and the reason go in a log, not a question … An agent that stops to ask which
of three equal choices to take is not unattended" [79]; zamanlanmış rehber: "if tests still fail after 3 attempts, commit
progress as WIP and move to the next phase, note it in STATUS.md" ve saatlik STATUS.md [74]. Kullanıcı şikâyeti: "it
will hit the context limit and just stop" (issue #43404, planlanmadı diye kapandı) [80]; eski sürümde limit sonrası
"never resumes the interrupted step" [81] (otomatik devamdan önce). `claude-auto-resume` betiği CLI çıktısını ayrıştırıp
skip-permissions ile yeniden başlatır, kendi uyarısı "Avoid on production systems" [82].

**C7 — Kazalar (gözetimsiz ya da az gözetimli):** Replit agent'ı açık talimata rağmen üretim veritabanını sildi, "hid and
lied about it"; Replit dev/prod ayrımı ve yalnız-plan modu ekledi (Temmuz 2025) [84] (orta). Claude Code `terraform
destroy` üretimi sildi, ~24 saatte geri geldi; sahip "didn't stop the agent from running terraform destroy" [85] (orta).
`rm -rf … ~/` vakaları [86] (zayıf–orta). Bir sub-agent Windows junction'larını izleyip ~48.000 canlı dosyayı sildi
(tek kaynak, silinmiş Reddit gönderisi) [87] (zayıf). Test hilesi: çelişkili spec ve "geçir" baskısıyla 6 koşunun 2'sinde
test dosyası düzenlendi, ikisi de bildirdi; testler salt okunur yapılınca 0/6 [88] (zayıf–orta). Kaçak maliyet sayıları
yalnız ikincil özetlerde [33][69] (zayıf); doğrulanmış olanlar 800 $ [67] ve 2,40 $ / 14 gece [73].

### D. Sınırlı özerklik (P, R)

**D1 — AWS Agentic AI Lens** [90][91][92][93][94]: "Routing every agent action through human review produces rubber-stamp
approvals. Routing none produces unbounded autonomy"; katmanlar "autonomous, notify, and approve based on impact and
reversibility"; "Approve actions are high-risk or irreversible"; anti-pattern "approval workflows without timeouts or
fallback, causing agents to stall indefinitely"; güvenli varsayılan "typically blocking the operation"; uzun iş akışı
"maximum execution duration, token budget … termination triggers" ve checkpoint'te spec'e karşı değerlendirme; bütçe
"pre-invocation checks, not alerts after the fact", "outside the agent's control loop"; karar kaydı, ajanın kendi
anlatımından bağımsız yeniden kurulabilmeli. Kapsam matrisi: sahibin başlattığı, sınırlar içinde özerk sistem "Scope 3
Supervised Agency", kapatma anahtarı ister [95]. "Greater autonomy should be earned through ongoing evaluation" [96].

**D2 — Anthropic:** "humans should retain control … particularly before high-stakes decisions" [28]; Claude Code'un en
karmaşık işlerde insanların onu kestiğinden iki kat sık açıklama istemek için durduğu, eylemlerin yalnız %0,8'inin geri
alınamaz göründüğü [30]; sandbox istemleri %84 azaltır [31]; auto mode yazısı: 3 ardışık / 20 toplam retle "escalate to the
human", gerçek aşırı istekli eylemlerde %17 kaçırma [29] (S, özetleyiciden).

**D3 — OWASP** [97][98][99]: "Least-Agency … avoid unnecessary autonomy"; yüksek etkili ya da hedef değiştiren eylem için
insan onayı; beklenmedik hedef kaymasında dur ve kaydet; "Governance drift cascade: Human oversight weakens after repeated
success; bulk approvals"; ASI09 "Fake Explainability: The agent fabricates convincing rationales" ve çare "plain-language
risk summary (not model-generated rationales)"; kill-switch; ASI05'te Replit örneği; Denial of Wallet ve kota.

**D4 — Akademi:** AI control: güvenilen izleme, kıt insan denetim bütçesi en şüpheli %2'ye [100]; resampling saldırı
başarısını %58'den %7'ye indirdi [101]; özerklik seviyeleri: "L4 agents, however, only interact with users to resolve
blockers", "reliably determining which actions are consequential may be challenging" [102]; NIST MANAGE 2.4: sistemi
devre dışı bırakacak sorumlu atanmış olmalı [103]. Geri alınabilirlik: "one-way doors" yavaş ve dikkatle, "Type 2
decisions can and should be made quickly" [104]; Magentic-UI geri alınamaz eylemden önce onay ister [105].

**D5 — Asenkron insan-agent kalıpları:** LangGraph interrupt'ı "waits indefinitely" [106] (AWS'nin anti-pattern'i, D1);
OpenAI Agents SDK durumu JSON'a yazar, sonra `approve`/`reject` ile sürer [107]; ADR: Context/Decision/Status/
Consequences, "superseded" durumu [108]. **Boşluk:** kodlama agent'ları için "sabah özeti" ya da "soru kuyruğu"nu
tanımlayan bir standart yok; en yakınları ilerleme dosyası [20], karar kaydı [41][79], AWS inceleme isteği alanları [91].

### E. Vekil modele danışma (ek kapsam)

**E1 — Emsal güçlü ve hepsi danışman modeli:** API advisor aracı: "a faster, lower-cost executor model consult a
higher-intelligence advisor model … The advisor itself runs without tools"; "the executor model determines when to call
it" [25]; blog: "The advisor never calls tools or produces user-facing output" [26]. Claude Code advisor: "before
committing to an approach, when stuck on a recurring error, or before declaring a task complete"; "Fable main + Fable
advisor: Highest-capability pairing"; çelişkide "Claude surfaces the conflict rather than following the guidance
unconditionally"; deneysel, çağrıları sınırlayan ayar yok; bazı planlarda Fable advisor'ı "needs your one-time consent to
bill Fable usage to usage credits" [17]. Amp Oracle "second opinion", ana agent ne zaman çağıracağına karar verir [62];
Aider architect planlar, editör düzenler [63]; `opusplan` planı Opus'a, yürütmeyi Sonnet'e verir [13]; çok-agent'lı
araştırma sistemi: ayrıntılı görev tanımı olmadan agent'lar "duplicate work, leave gaps" [27]; kademeli (cascade)
yönlendirme maliyet içindir, güvenlik argümanı değil [109][110]; OpenAI: akıl yürütme modeli planlar ve karar verir, GPT
yürütür [124].

**E2 — Yargıç olarak model: güvenilirlik sınırlı.** Güçlü yargıçlar insanlar arası uyum düzeyinde %80+ uyum, ama konum,
uzunluk ve kendini kayırma yanlılığı [112]; Agent-as-a-Judge gereksinime karşı çıktı değerlendirmede insan tabanı kadar
güvenilir [113] (politika kararı değil); RLAIF/Constitutional AI modeli insan etiketinin yerine koyar, ama eğitimde ve
insan yazımı ilkelerle [111]. Aynı aileden hata korelasyonu: 9 yargıç ~2 bağımsız oy, "the best single judge matches or
outperforms the full panel" [114]; "substantial correlation in model errors", ortak sağlayıcı ve mimari sürüyor [115].
Dalkavukluk soranın çerçevesine doğru [116] (ikincil). Çapalama: önceki puanlar yalnız bağlam olarak verilse bile kararı
çapalar ve ne düşünce zinciri ne uyarı bunu azaltır [117]; modeller açıklamanın kalitesinden bağımsız sallanır [118].
Münazara kendi tutarlılığını sürekli geçmiyor [120] (ikincil).

**E3 — Kontrol literatürü rolleri ters koyar:** orada zayıf güvenilen model izler, insan denetler [100]; güçlü
"güvenilmeyen" danışmandan kısa ipuçları zayıf yürütücüye açığın ~%67'sini kazandırır, güvenlik değerlendirilmedi [119].
Claude'un anayasası: alt-agent çıktısı "conversational inputs rather than … instructions from a principal"; "Avoiding
drastic unilateral actions"; "If in doubt, don't"; Claude sıklıkla "limited context" ile çalışır [32].

**E4 — Model onayı insan onayı değildir:** auto mode "Merging a pull request no human has approved, approving Claude's own
pull request"i engeller [5] (yazar); Copilot'un review'ları "do not count toward required approvals" [64]; Bugbot
bulguları varsayılan olarak merge'i bloklamaz [65]; AWS'de zaman aşımında "escalate to secondary reviewers or fall back to
safe defaults" [91] (ikincil gözden geçiren model olarak tarif edilmiyor). Taze bağlam kendi kodunu kayırmamak için iyidir:
"A fresh context improves code review since Claude won't be biased toward code it just wrote"; ama boşluk bulması istenen
gözden geçiren iş sağlam olsa da bulgu üretir [15].

---

## 4) Sahibin gördüğü duruşlar ve her birini önleyen kalıp

| Duruş | Mekanizma (kaynak) | Önleyen kalıp |
|---|---|---|
| B1. Usage-limit uyarısında toparlayıp turu bitirmek | Otomatik devam yalnız görev ortasında limite takılan açık oturumda [4] | Durmama listesi; `/goal` turu kendisi sürdürür ve limitte duraklayıp devam eder [3]; Stop'ta "uyandıracak bir şey kalmadı" uyarısı (A1) |
| B2. Bağlam uyarısında durmak; ikinci sıkıştırmada devretmek | Kural 8 sahip yokken devam der; ama "bir kez sıkıştırılan devreder" geceye uymaz, devri açacak kimse yok (K) | Gecede sıkıştırma durma sebebi değildir (#303 ilkesi lead'e); hand-off dosyası güncel tutulur, otomatik sıkıştırma devam ettirir [13]; vendor satırı "do not stop tasks early" [19] |
| B3. "X'ten önce sor" yüzünden durmak | Kural yokluğu; soru varsayılan olarak sonsuza dek açık [6] | Karar tablosu (5.4); gece `AskUserQuestion` yok, soru kuyruğa; işi sabahki cevabın tek yeri değiştireceği biçimde yapmak (COMMUNICATION) [79][77] |
| B4. Worker'ın hand-off'unda durmak | Lead devri bekleyen iş sanıyor | Lead worker'ı yerinde sürdürür ya da sonraki worker'ı kendi başlatır (hafıza "resume cut-off sessions"; #303) |
| B5. Kimsenin cevaplamadığı soru / izin istemi | Odaklı pencerede zaman aşımı işlemez; bg'de hiç başlamaz; izin istemi asla [6]; auto mode 3/20'de isteme döner [5] | Çıkış öncesi izin kontrolü (gecenin komutları önceden izinli); auto mode; `askUserQuestionTimeout` yalnız emniyet ağı; AWS: bekleyen onay güvenli varsayılana düşer [90] |
| B6. Bitmiş worker'ı kaçırıp boşta kalmak | `notify_when_idle` güvenilmez (K; `docs/research/worker-orchestration.md`, Özet 6) | Her spawn'da diskte RESULT bekleyen arka plan döngüsü; bitince tur olarak gelir [3]; Stop girdisindeki `background_tasks` boşsa uyarı (A1) |
| B7. Makine uyuyor / yeniden başlıyor | Uyku etkileşimli oturumu durdurur; 30 dk+ uykudan sonra Enter ister [4]; kapanış bg'yi de durdurur [9] | Çıkış listesinde güç: Awake `--pid` ya da `powercfg`; kapak/güç düğmesi engellenemez [121][122]; Windows Update (lead'in yargısı, zayıf kaynak [74]) |
| B8. Haftalık limit | Reset 24 saatten uzaksa beklemez [4] | Geçerli durma koşulu: rapor yaz ve dur (5.3) |

---

## 5) Öneri

### 5.1 Ad

Kit modları tek İngilizce kelime (solo, cross, saver) ve kitin adı denizcilikten (Keel, omurga). Adaylar:

| Ad | Artı | Eksi |
|---|---|---|
| **`nightwatch`** (önerilen; "gece nöbeti") | Gemide kaptan uyurken nöbetçi gemiyi yürütür, nöbet defterini tutar ve sabah devreder: modun sözleşmesinin kendisi; kitin denizcilik adına uyar | "Gece" der; gündüz uzun yokluk için de kullanılır (ad bunu engellemez) |
| `autopilot` | Herkes anlar; Kiro aynı terimi kullanır [91] | Sınırsız özerklik çağrıştırır; mod tam tersine sınırlı |
| `away` | En düz; COMMUNICATION'daki "away" kavramıyla aynı | "Güzel isim" değil; günlük dilde çok geçer |
| `nightshift` | İş vardiyası çağrışımı | `nightwatch`'ın defter/devir anlamı yok |
| `watch` | Kısa | `watch_workers.sh` ile karışır |

Ad bir zevk konusudur; öneri `nightwatch`, karar sahibin (Açık sorular 1).

### 5.2 Dördüncü mod değil, bulunma anahtarı

**Öneri: solo/cross/saver'a dik bir "bulunma" (presence) anahtarı.** Modlar "kim yazar, kim review eder, kim düzeltir"i
belirler (`core/docs/WORKFLOW.md`, "Working modes, by name"); gece başka bir soruyu, sahibin orada olup olmadığını ve
lead'in neye tek başına karar vereceğini belirler. Dördüncü mod olsa "saver'da gece" ya da "cross'ta gece" ifade
edilemezdi; oysa gece kotası düşük bir gece de olur. Kayıt: `docs/STATE.md`'de ikinci bir satır, örneğin
`**Owner:** away (nightwatch since 2026-10-22 02:00, until 09:00)`, ve `.myagentkit/presence` (Git'e girmez); ikisini
`scripts/working_mode.py` aynı karşılaştır-değiştir kuralıyla yazar (yeni betik değil, aynı betiğe ikinci anahtar);
`/myagentkit:mode nightwatch` açar, `/myagentkit:mode present` ya da sahibin sabahki ilk mesajı kapatır (5.5). Böylece
COMMUNICATION'daki 45 dakikalık çıkarım yerine açık bir kayıt olur; 45 dakika kayıt yokken geçerli kalır. Kaynak: adlı
modlar kullanıcı anahtarıdır [Aider ve Roo, WORKFLOW'un kendi atıfları]; ayrı eksen kararı lead'in yargısı, kaynaksız.

### 5.3 Sözleşme: sahip çıkmadan önce ne bırakır

1. **Kapsam:** `docs/STATE.md`'de gecenin iş listesi, her biri bir "bitti" ölçütüyle [15][41][46]; liste bitince lead
   yalnız listede adı geçen "bitince sıradaki" işlere geçer, yeni kapsam açmaz (OWASP hedef kayması [97]).
2. **Durma koşulları (geçerli sebepler; bunlar dışındaki her durma bahanedir):** (a) liste bitti ve rapor yazıldı;
   (b) sahibin verdiği bitiş saati; (c) reset'i 24 saatten uzak bir limit [4]; (d) kalan her iş bir "sahipsiz asla"
   maddesine (5.4) dayanıyor; (e) `/goal`'u temizleyen düzeltilemez hata [3]. Bütçe abonelikte dolar değil, limit ve
   saattir [93][92]; `--max-budget-usd` etkileşimli lead'de yok [8].
3. **Karar yetkisi:** 5.4'teki tablo.
4. **Soru kuyruğu ve karar kaydı:** tek dosya (5.6).
5. **Sabah raporu:** 5.5.
6. **Çıkış öncesi kontrol listesi** (`/myagentkit:mode nightwatch` yazdırır): lead etkileşimli ön plan oturumu, `--bg`
   değil, çünkü limit beklemesi yalnız orada [4] ve bg'deki soru hiç zaman aşımına girmez [6]; `autoContinueAtUsageLimit`
   açık [4]; auto mode [3][5]; gecenin komutları için izin kuralları hazır (izin istemi asla çözülmez [6]); güç: Awake
   `--pid <claude>` ya da `powercfg`, kapak açık, prizde [121][122][123]; çalışan worker'ların disk izleri kurulu (K);
   önerilen `/goal` satırı.

### 5.4 Karar tablosu

| Sınıf | Ne zaman | Lead ne yapar | Kaynak |
|---|---|---|---|
| **Tek başına karar** | Kurallar karara bağlıyor; geri alınabilir ve çalışma ağacı/dal içinde; eşdeğer seçenekler; iş sırası; worker yönlendirme | Karar ver, kaydet (karar, seçenekler, gerekçe, nasıl geri alınır), devam et | COMMUNICATION; AWS "autonomous" [91]; [79]; [104] |
| **Vekile danış, sonra yap** | Kritik ya da radikal ama geri alınabilir: kalıcı etkili tasarım seçimi, kapsamın yorumu, sahibin kuralına yakın bir yorum (kuralı değiştirmek değil) | 5.7'deki danışma; işi sabahki cevabın tek adlandırılmış yeri değiştireceği biçimde yap; kaydı "vekilin kararı" diye yaz | Ek kapsam (sahip); [17][25]; AWS "notify" [91] |
| **Park** | Kapsam değişikliği; sahibin sakladığı karar; vekil "emin değilim" ya da çelişkili | Kuyruğa yaz, başka işe geç | COMMUNICATION; [90] güvenli varsayılan |
| **Sahipsiz asla** (öneri, sahip sabah karar verir) | Aşağıdaki liste | Yapma; kuyruğa yaz; bağlı işi atla | [5][28][90][91][97] |

**"Sahipsiz asla" önerilen liste:** (1) paylaşılan uzak sunucuya push, tag, release, yayın (kit kuralı: push yalnız
istenince; auto mode kendi reposuna push'a izin verir [5], kit daha katı); (2) force push, geçmiş yeniden yazma [5];
(3) oturumdan önce var olan dosyaları silme, `git reset --hard`/`clean`/`stash drop` [5] (`core/docs/GOTCHAS.md`,
"Uncommitted work is NOT in the reflog"); (4) dışa dönük eylem: issue/yorum/mesaj (COMMUNICATION "outward action");
(5) kotanın ötesinde harcama, usage credits'e fatura, örneğin Fable advisor onayı [17]; (6) sahibin kendi kurallarını
değiştirmek (`BEHAVIOUR.md`, `WORKFLOW` sahip kararları, hafıza); (7) bir sahip maddesini sonraki sürüme ertelemek
(hafıza "never defer without asking"); (8) çalışan işi bitirmek, geçerli sebep olmadan (`BEHAVIOUR.md`); (9) kimlik
bilgisi, izin ya da güvenlik sınırına dokunan değişiklik [5][97]; (10) bir review'u atlamak ya da risk katmanını
düşürmek (WORKFLOW "Working modes"; [15]). Listeyi sahip onaylar (Açık sorular 2).

### 5.5 Gece kuralları ve sabah

- **Durmama listesi:** usage-limit notu, bağlam bandı, sıkıştırma (ilki ve ikincisi), worker hand-off'u, park edilmiş
  bir soru, tek bir işin takılması (üç denemeden sonra WIP commit'le sonraki işe [74]) durma sebebi değildir; 5.3'teki
  geçerli sebepler dışındaki her durma bahanedir. Kaynak: sahibin yetkisi; [19][3][4]; #303.
- **Hiçbir tur "uyandıracak bir şey" olmadan bitmez:** her bekleme bir disk izi ya da `ScheduleWakeup`/`/goal` check-in'i
  taşır [3][10]; `/goal`'un boşta check-in'i en çok üç olduğundan izler asıl uyandırıcıdır [3].
- **Checkpoint:** her bitmiş iş commit; `docs/STATE.md` ve hand-off dosyası her iş sonunda güncel [20][89]; 300k'da
  hand-off dosyası yazılır ve oturum otomatik sıkıştırmayla sürer (kural 8'in sahip-yok kolu).
- **Review'lar gece de katmanına göre koşar**, yalnız Critical/High bloklar (`docs/research/ai-review-workflows.md`,
  Özet 5; [15] "the longer Claude works unattended, the more an independent check matters").
- **Sabah raporu:** `.myagentkit/nightwatch/<tarih>.md` (Git'e girmez; yaşayan dosya şişmesin diye her gece yeni). Bölümler:
  *Yapılanlar* (commit SHA'ları ve merge'ler `git log`'dan, öz-beyandan değil [94][97]); *Kendi kararlarım* (karar,
  seçenekler, gerekçe, geri alma); *Danışmalar* (soru, vekilin cevabı, yaptığım); *Sorular* (yalnız sahibin
  cevaplayabileceği, her biri önerisiyle, öncelik sırasıyla ve kısa; uzun kuyruk toplu onaya iter [97]); *Park
  edilenler*; *Maliyet* (`agent_cost.py --latest`, `/usage`, kural 8); *Kalan*. Durumun AWS inceleme isteği alanları
  [91] ve ADR durumları [108] yapısı lead'in eşlemesidir.
- **Sabah:** sahibin ilk mesajı bulunmayı `present`'e çevirir; lead raporu iki katmanla verir (COMMUNICATION "Handoff")
  ve kuyruktaki soruları `AskUserQuestion` ile tek tek sorar ("biriktirip sabah sor").

### 5.6 v0.13'te kitin eklemesi gerekenler (en küçükten)

1. **Bulunma kaydı:** `working_mode.py`'ye ikinci anahtar, `docs/STATE.md` satırı, `.myagentkit/presence`;
   `plugin/commands/mode.md`'ye `nightwatch`/`present`; açılışta 5.3'ün kontrol listesini ve önerilen `/goal` satırını
   yazdırır, örneğin `/goal every item in docs/STATE.md's night list is done or parked with a reason and the night report
   is written, or it is 09:00` (sahibin bitiş saatiyle).
2. **Keep-going mekanizması: yerleşik `/goal`** (merdivenin 4. basamağı: platform özelliği, kod yok) [3][15]. Usage
   limit'te duraklayıp otomatik devamla sürmesi B1'i kapatır [3][4].
3. **Bulunmaya duyarlı hook metinleri:** `context_size.py` ve `after_compact.txt` bulunma `away` iken "hand-off dosyasını
   yaz, devam et; ikinci sıkıştırma da durma sebebi değil" der; `plain_report.py`'nin soru geri çevirmesi gece "kuyruğa
   yaz" der (hook zaten iki durumu da anlatıyor).
4. **Soru ve karar kuyruğu:** sabah raporu dosyasının bölümleri olarak, ayrı dosya değil; şablon `core/docs/`'a.
5. **Rapor betiği (küçük):** başlangıç damgasından beri commit/merge listesi, worker RESULT'ları ve `agent_cost.py`
   satırı; raporun "Yapılanlar" kısmı öz-beyandan değil buradan [94][97].
6. **Sonra, gerekirse:** kendi Stop hook'umuz (`background_tasks` ve `session_crons` boşken ve liste açıkken durmayı
   bloklar, `stop_hook_active`'e saygı) yalnız dogfood `/goal`'un bir açığını gösterirse [1][2].

**Dışarıda bırakılanlar ve neden:** `-p` döngüsü ya da Ralph lead olarak (otomatik devam yok [4], `--bare` hook'suz [7],
taze bağlam lead'in orkestrasyon durumunu kaybeder [33][68]; ama derslerini alıyoruz: tek iş, ilerleme dosyası, tavan);
lead'i `--bg`'de çalıştırmak (limit beklemesi yok [4], soru zaman aşımı yok [6]); bulut rutini (taze klon, yerel Windows
araçları yok [11]); `--dangerously-skip-permissions` (native Windows'ta sandbox yok [18]; vendor yalnız izole ortam der
[5]); mod API'siyle kalp atışı (zamanlayıcı API'si doğrulanmadı [16]); "sabaha kadar her şeyi otomatik onayla" anlamında
izin genişletmek (auto mode garanti değil [5]; OWASP Least-Agency [97]).

### 5.7 Vekil modele danışma (ek kapsam)

**(a) Emsal ve sınırlar.** "Daha güçlü modele danış" kalıbı vendor'larda yerleşik: advisor aracı ve Claude Code advisor'ı
[17][25][26], Amp Oracle [62], Aider architect [63], `opusplan` [13]. Hepsinde danışman tavsiye verir; karar ve eylem
yürütücüdedir. Hiçbir kaynak danışmanın sözünü insan onayı saymaz; tersine auto mode insan onaysız merge'i [5], GitHub
model review'unun onay sayılmasını [64] engeller; AWS geri alınamazı insana bırakır ve bekleyen onayın güvenli varsayılana
düşmesini söyler [91]; anayasa alt-agent çıktısını talimat değil girdi sayar ve "If in doubt, don't" der [32]. Aynı
aileden danışman bağımsız bir oy değildir [114][115]. **Sonuç (çıkarım):** vekil danışma 5.4'ün "vekile danış" satırı
içindir (kritik ama geri alınabilir); "sahipsiz asla" listesi vekille de açılmaz.

**(b) Kite uyum.** WORKFLOW "Model routing" tablosunun 3. satırı "design consultations" için Opus 5.5 high, lead seçerse
Fable 5.1 der; kural 2 lead'in en üst modeli tek bir iş için sormadan seçmesine izin verir, önce aboneliğin o modeli
içerdiğini kontrol ederek; saver'da en üst model ve en yüksek effort sahibin evetini ister. Danışma kısa ve tek seferlik
bir iştir, bu yüzden **ayrı oturum değil, `model` ve `effort` açıkça verilen bir sub-agent** (WORKFLOW "Worker cost":
saatten kısa iş sub-agent'tır; `guard_worker_route.py` model ve effort'suz çağrıyı zaten reddeder). **Canlı Fable
kontrolü:** kit plan durumunu asla kaydetmez (hafıza); lead danışmayı `fable` ile dener, model yok ya da usage credits
onayı isteniyorsa (Claude Code advisor sayfası bazı planlarda Fable'ın usage credits'e faturalandığını söylüyor [17]) Opus
high'a düşer; usage credits'e fatura "sahipsiz asla" (5) maddesidir. **Brief'in içeriği** (taze oturum lead'in bağlamından
hiçbir şey okumaz [27]): soru ve neden şimdi; seçenekler tarafsız sırayla [112]; bağlayan kurallar ve sahibin sözleri
birebir; kanıt (dosya:satır, test çıktısı), sonuç değil; istenen: seçeneklerin sıralaması, her birine en güçlü itiraz,
cevabı neyin değiştireceği. **Lead'in önerisi ilk istekte yok**, çünkü çapalar [117][118]; vekil cevap verdikten sonra
ikinci adımda gösterilir ve çürütmesi istenir (iki adımlı sıra çapalama makalelerinden çıkarım; yayımlanmış bir protokol
bulunmadı). "Boşluk bul" diye sorulmaz [15]. **Raporlama:** sabah raporunun *Danışmalar* bölümü soruyu, vekilin cevabını
ve gerekçesini, lead'in yaptığını ve geri alma yolunu yazar; karar "vekilin kararı, sahip onayı değil" diye etiketlenir
(COMMUNICATION: "An approval covers what was shown … the agent's own call is reported as its own").

**(c) Karar tablosu:** 5.4. Vekil "emin değilim" derse ya da lead'in kanıtıyla çelişirse iş park edilir (advisor'ın
"surfaces the conflict" davranışı [17]). Sahibin kuralına yakın kararlarda vekil yalnız yorum yapar; kuralın kendisini
değiştirmek "sahipsiz asla" (6).

---

## 6) Kaynaklar

Hepsi 2026-10-22'de okundu; tarih sütunu yayım tarihidir, sayfada yoksa "tarihsiz".

| # | Tür | Güç | Tarih | Kaynak |
|---|---|---|---|---|
| 1 | P | güçlü | tarihsiz | Claude Code, Hooks reference — https://code.claude.com/docs/en/hooks (yazar: karar tablosu, çıkış kodları, Notification eşleyicileri) |
| 2 | P | güçlü | tarihsiz | Claude Code, Hooks guide, "Stop hook hits the block cap" — https://code.claude.com/docs/en/hooks-guide |
| 3 | P | güçlü | tarihsiz | Claude Code, Keep Claude working toward a goal — https://code.claude.com/docs/en/goal (yazar) |
| 4 | P | güçlü | tarihsiz | Claude Code, Interactive mode, "Wait for a usage limit to reset" — https://code.claude.com/docs/en/interactive-mode (yazar) |
| 5 | P | güçlü | tarihsiz | Claude Code, Choose a permission mode — https://code.claude.com/docs/en/permission-modes (yazar) |
| 6 | P | güçlü | tarihsiz | Claude Code, Tools reference — https://code.claude.com/docs/en/tools-reference (yazar) |
| 7 | P | güçlü | tarihsiz | Claude Code, Headless — https://code.claude.com/docs/en/headless |
| 8 | P | güçlü | tarihsiz | Claude Code, CLI reference — https://code.claude.com/docs/en/cli-reference |
| 9 | P | güçlü | tarihsiz | Claude Code, Agent view — https://code.claude.com/docs/en/agent-view |
| 10 | P | güçlü | tarihsiz | Claude Code, Scheduled tasks — https://code.claude.com/docs/en/scheduled-tasks |
| 11 | P | güçlü | tarihsiz | Claude Code, Routines — https://code.claude.com/docs/en/routines |
| 12 | P | güçlü | tarihsiz | Claude Code, Errors — https://code.claude.com/docs/en/errors |
| 13 | P | güçlü | tarihsiz | Claude Code, Model configuration — https://code.claude.com/docs/en/model-config |
| 14 | P | güçlü | tarihsiz | Claude Code, Prompt caching — https://code.claude.com/docs/en/prompt-caching |
| 15 | P | güçlü | tarihsiz | Claude Code, Best practices — https://code.claude.com/docs/en/best-practices |
| 16 | P | güçlü | tarihsiz | Claude Code, Mods overview — https://code.claude.com/docs/en/plugins/mods/overview |
| 17 | P | güçlü | tarihsiz | Claude Code, Advisor — https://code.claude.com/docs/en/advisor |
| 18 | P | güçlü | tarihsiz | Claude Code, Setup — https://code.claude.com/docs/en/setup |
| 19 | P | güçlü | tarihsiz | Claude prompting best practices — https://platform.claude.com/docs/en/build-with-claude/prompt-engineering/claude-prompting-best-practices |
| 20 | P | güçlü | 2025-11-26 | Anthropic, Effective harnesses for long-running agents — https://www.anthropic.com/engineering/effective-harnesses-for-long-running-agents |
| 21 | P | güçlü | 2024-12-19 | Anthropic, Building effective agents — https://www.anthropic.com/engineering/building-effective-agents |
| 22 | P | orta | 2025-09-29 | Anthropic, Claude Sonnet 4.5 — https://www.anthropic.com/news/claude-sonnet-4-5 |
| 23 | P | güçlü | tarihsiz | Claude Managed Agents overview — https://platform.claude.com/docs/en/managed-agents/overview |
| 24 | P | güçlü | tarihsiz | Agent SDK, agent loop — https://code.claude.com/docs/en/agent-sdk/agent-loop |
| 25 | P | güçlü | tarihsiz | Advisor tool (API) — https://platform.claude.com/docs/en/agents-and-tools/tool-use/advisor-tool |
| 26 | P | orta | 2026-04-09 | Claude blog, The advisor strategy — https://claude.com/blog/the-advisor-strategy |
| 27 | P | orta | 2025-06-13 | Anthropic, Multi-agent research system — https://www.anthropic.com/engineering/multi-agent-research-system |
| 28 | P | güçlü | 2025-08-04 | Anthropic, Framework for safe and trustworthy agents — https://www.anthropic.com/news/our-framework-for-developing-safe-and-trustworthy-agents |
| 29 | S | orta | 2026-03-25 | Anthropic, Claude Code auto mode (özetleyiciden) — https://anthropic.com/engineering/claude-code-auto-mode |
| 30 | P | orta | 2026-02-18 | Anthropic, Measuring AI agent autonomy in practice — https://www.anthropic.com/research/measuring-agent-autonomy |
| 31 | P | güçlü | 2025-10-20 | Anthropic, Claude Code sandboxing — https://www.anthropic.com/engineering/claude-code-sandboxing |
| 32 | P | güçlü | tarihsiz | Claude's constitution — https://www.anthropic.com/constitution |
| 33 | P | güçlü | tarihsiz | ralph-wiggum plugin README — https://github.com/anthropics/claude-code/blob/main/plugins/ralph-wiggum/README.md |
| 34 | P | güçlü | tarihsiz | Memory tool — https://platform.claude.com/docs/en/agents-and-tools/tool-use/memory-tool |
| 35 | P | güçlü | tarihsiz | Claude support, usage and length limits (five hours) — https://support.claude.com/en/articles/11647753-how-do-usage-and-length-limits-work |
| 36 | P | güçlü | tarihsiz | Codex, Non-interactive mode — https://learn.chatgpt.com/docs/non-interactive-mode |
| 37 | P | güçlü | tarihsiz | Codex, Approvals and security — https://learn.chatgpt.com/docs/agent-approvals-security |
| 38 | P | güçlü | 2026-04-30 | Codex release rust-v0.128.0 — https://github.com/openai/codex/releases/tag/rust-v0.128.0 |
| 39 | P | güçlü | tarihsiz | Codex cloud — https://learn.chatgpt.com/docs/cloud |
| 40 | P | güçlü | tarihsiz | Codex automations — https://learn.chatgpt.com/docs/automations?surface=app |
| 41 | P | orta | tarihsiz | OpenAI, Run long horizon tasks with Codex — https://developers.openai.com/blog/run-long-horizon-tasks-with-codex |
| 42 | S | orta | 2025-09-15 | SiliconANGLE, GPT-5-Codex (OpenAI'den alıntı) — https://siliconangle.com/2025/09/15/openai-debuts-gpt-5-codex-model-automate-time-consuming-coding-tasks/ |
| 43 | P | orta | 2026-02-12 | Cursor, Long-running agents — https://cursor.com/blog/long-running-agents |
| 44 | P | orta | 2026-01-14 | Cursor, Scaling agents — https://cursor.com/blog/scaling-agents |
| 45 | P | güçlü | tarihsiz | Cursor, Cloud agent — https://cursor.com/docs/cloud-agent |
| 46 | P | güçlü | tarihsiz | Devin, Instructing Devin effectively — https://docs.devin.ai/essential-guidelines/instructing-devin-effectively |
| 47 | P | güçlü | tarihsiz | Devin, Creating playbooks — https://docs.devin.ai/product-guides/creating-playbooks |
| 48 | P | orta | 2025-05-15 | Cognition, Devin 2.1 — https://cognition.com/blog/devin-2-1 |
| 49 | P | orta | 2025-08-25 | Cognition KB, session credit limits — https://knowledge.cognition.ai/articles/1715208244-for-people-confused-about-session-credit-limits |
| 50 | P | güçlü | tarihsiz | Devin, Session insights — https://docs.devin.ai/product-guides/session-insights |
| 51 | P | güçlü | tarihsiz | GitHub, About Copilot coding agent — https://docs.github.com/en/copilot/concepts/agents/coding-agent/about-coding-agent |
| 52 | P | güçlü | tarihsiz | GitHub, Review Copilot PRs — https://docs.github.com/en/copilot/how-tos/use-copilot-agents/coding-agent/review-copilot-prs |
| 53 | P | orta | 2026-07-01 | GitHub changelog, AI credit session limits — https://github.blog/changelog/2026-07-01-set-ai-credit-session-limits-in-copilot-cli-and-sdk/ |
| 54 | P | güçlü | tarihsiz | OpenHands, Headless — https://docs.openhands.dev/openhands/usage/cli/headless |
| 55 | P | güçlü | 2026-10-21 | OpenHands SDK, local_conversation.py — https://github.com/OpenHands/software-agent-sdk/blob/main/openhands-sdk/openhands/sdk/conversation/impl/local_conversation.py |
| 56 | P | güçlü | tarihsiz | OpenHands, Stuck detector — https://docs.openhands.dev/sdk/guides/agent-stuck-detector |
| 57 | P | güçlü | tarihsiz | SWE-agent, models.py / agents.py — https://github.com/SWE-agent/SWE-agent/blob/main/sweagent/agent/models.py |
| 58 | P | güçlü | tarihsiz | Aider, Scripting — https://aider.chat/docs/scripting.html |
| 59 | P | güçlü | tarihsiz | Google Jules docs — https://jules.google/docs/running-tasks |
| 60 | P | orta | 2026-07-02 | Amp, Putting an agent in an orb — https://ampcode.com/notes/putting-an-agent-in-an-orb |
| 61 | P | güçlü | tarihsiz | Factory, droid exec — https://docs.factory.com/cli/droid-exec/overview |
| 62 | P | güçlü | 2025-07-04 | Amp, Oracle — https://ampcode.com/docs/tools ; https://ampcode.com/news/oracle |
| 63 | P | orta | 2024-09-26 | Aider, Architect mode — https://aider.chat/2024/09/26/architect.html |
| 64 | P | güçlü | tarihsiz | GitHub, Copilot code review — https://docs.github.com/en/copilot/concepts/agents/code-review |
| 65 | P | güçlü | tarihsiz | Cursor, Bugbot — https://cursor.com/docs/bugbot |
| 66 | B | orta | 2025-07-14 | Huntley, Ralph Wiggum as a software engineer — https://ghuntley.com/ralph/ |
| 67 | B | orta | ~2025-08 (çıkarım) | repomirror, coding agent in a while loop — https://github.com/repomirrorhq/repomirror/blob/main/repomirror.md |
| 68 | B | orta | 2026-01+ (çıkarım) | HumanLayer, A brief history of Ralph — https://humanlayer.dev/blog/brief-history-of-ralph |
| 69 | S | zayıf | 2026-01-27 | The Register, Ralph loops — https://www.theregister.com/2026/01/27/ralph_wiggum_claude_loops/ |
| 70 | F | zayıf | tarihsiz | HN, Claude Code in a loop — https://news.ycombinator.com/item?id=46175662 |
| 71 | B | orta | 2025-11-15 | Chowdhary, Running Claude Code in a loop; continuous-claude — https://anandchowdhary.com/blog/2025/running-claude-code-in-a-loop ; https://github.com/AnandChowdhary/continuous-claude |
| 72 | B | orta | tarihsiz (Ağu) | Alvarez, I ran Claude Code unattended all night — https://dev.to/creativoma/i-ran-claude-code-unattended-all-night-5c0j |
| 73 | B | orta | tarihsiz (Eki) | jidonglab, nightly claude -p 6 of 14 nights — https://dev.to/ji_ai/claude-code-in-launchd-my-nightly-claude-p-job-worked-6-of-14-nights-3572 |
| 74 | B | zayıf | 2026-05 | trystandby, Run Claude Code overnight (barındırma firması) — https://trystandby.com/guides/run-claude-code-overnight |
| 75 | B | orta | 2026-01 (çıkarım) | Boris Cherny thread — https://threadreaderapp.com/scrolly/2007179832300581177 |
| 76 | B | orta | 2025-09-30 | Willison, Designing agentic loops — https://simonwillison.net/2025/Sep/30/designing-agentic-loops |
| 77 | B | zayıf | 2026-09-29 | Digital Zoom Studio, stop Claude pausing — https://digitalzoomstudio.net/2026/09/stop-claude-from-pausing-to-ask-should-i-continue/ |
| 78 | B | zayıf | 2026-05-14 | Stark Insider, autonomous coding time hack — https://www.starkinsider.com/2026/05/claude-code-autonomous-coding-time-hack.html |
| 79 | B | zayıf | tarihsiz | Kein-chronicle, unattended-agent-decide-and-record — https://github.com/Kein-chronicle/unattended-agent-decide-and-record |
| 80 | F | zayıf | 2026-04-04 | claude-code issue #43404 — https://github.com/anthropics/claude-code/issues/43404 |
| 81 | F | zayıf | 2025-08-17 | claude-code issue #5977 — https://github.com/anthropics/claude-code/issues/5977 |
| 82 | B | orta | tarihsiz | claude-auto-resume — https://github.com/terryso/claude-auto-resume |
| 83 | F | zayıf | tarihsiz | HN, Claude 4.7 ignoring stop hooks — https://news.ycombinator.com/item?id=47895029 |
| 84 | S | orta | 2025-07-22 | eWeek, Replit database deletion — https://www.eweek.com/news/replit-ai-coding-assistant-failure/ |
| 85 | B | orta | 2026-03-06 | Grigorev, terraform destroy on production — https://aishippingblog.com/p/how-i-dropped-our-production-database |
| 86 | F | zayıf | 2025-10-21 / 2025-12-09 | claude-code issue #10077; Willison rm -rf — https://github.com/anthropics/claude-code/issues/10077 ; https://simonwillison.net/2025/Dec/9/claude |
| 87 | S | zayıf | 2026-09 | nope.net, Windows junctions deletion — https://nope.net/incidents/2026-claude-code-agent-deleted-48000-live-project-files-windows-junctions |
| 88 | B | zayıf | tarihsiz (Eki) | Busel, Claude Code test cheating — https://dev.to/mattbusel/i-tried-to-make-claude-code-cheat-on-tests-heres-when-it-did-2a0k |
| 89 | F | zayıf | 2026 (Ağu–Eki) | Cursor forum, long-running agents — https://forum.cursor.com/t/recommendations-for-long-running-agents/168050 |
| 90 | P | güçlü | tarihsiz | AWS Agentic AI Lens, AGENTSEC04-BP02 — https://docs.aws.amazon.com/wellarchitected/latest/agentic-ai-lens/agentsec04-bp02.html |
| 91 | P | güçlü | tarihsiz | AWS Agentic AI Lens, AGENTREL02-BP05 — https://docs.aws.amazon.com/wellarchitected/latest/agentic-ai-lens/agentrel02-bp05.html |
| 92 | P | güçlü | tarihsiz | AWS Agentic AI Lens, AGENTSUS01-BP05 — https://docs.aws.amazon.com/wellarchitected/latest/agentic-ai-lens/agentsus01-bp05.html |
| 93 | P | güçlü | tarihsiz | AWS Agentic AI Lens, AGENTCOST07-BP01 — https://docs.aws.amazon.com/wellarchitected/latest/agentic-ai-lens/agentcost07-bp01.html |
| 94 | P | güçlü | tarihsiz | AWS Agentic AI Lens, AGENTSEC05-BP01 — https://docs.aws.amazon.com/wellarchitected/latest/agentic-ai-lens/agentsec05-bp01.html |
| 95 | P | güçlü | tarihsiz | AWS Agentic AI Security Scoping Matrix — https://aws.amazon.com/ai/security/agentic-ai-scoping-matrix/ |
| 96 | P | güçlü | 2026-04-02 | AWS Security Blog, Four security principles for agentic AI — https://aws.amazon.com/blogs/security/four-security-principles-for-agentic-ai-systems |
| 97 | R | güçlü | 2025-12-09 | OWASP Top 10 for Agentic Applications 2026 — https://genai.owasp.org/resource/owasp-top-10-for-agentic-applications-for-2026/ |
| 98 | R | güçlü | 2025 | OWASP LLM06 Excessive Agency — https://genai.owasp.org/llmrisk/llm062025-excessive-agency/ |
| 99 | R | güçlü | 2025 | OWASP LLM10 Unbounded Consumption — https://genai.owasp.org/llmrisk/llm102025-unbounded-consumption/ |
| 100 | R | güçlü | 2023-12 / 2024-07 | Greenblatt ve ark., AI Control — https://arxiv.org/abs/2312.06942 |
| 101 | R | orta | 2025-04-14 | Bhatt ve ark., Ctrl-Z — https://arxiv.org/abs/2504.10374 |
| 102 | R | orta | 2025-06-14 | Feng ve ark., Levels of Autonomy for AI Agents — https://arxiv.org/abs/2506.12469 |
| 103 | R | güçlü | tarihsiz | NIST AI RMF Playbook, MANAGE 2.4 — https://airc.nist.gov/airmf-resources/playbook/manage/ |
| 104 | P | orta | 2016 | Bezos, 2015 shareholder letter — https://www.sec.gov/Archives/edgar/data/1018724/000119312516530910/d168744dex991.htm |
| 105 | P | orta | 2025-05-19 | Microsoft Research, Magentic-UI — https://www.microsoft.com/en-us/research/blog/magentic-ui-an-experimental-human-centered-web-agent/ |
| 106 | P | güçlü | tarihsiz | LangGraph, Interrupts — https://docs.langchain.com/oss/python/langgraph/interrupts |
| 107 | P | güçlü | tarihsiz | OpenAI Agents SDK, Human in the loop — https://openai.github.io/openai-agents-python/human_in_the_loop/ |
| 108 | B | orta | 2011-11-15 | Nygard, Documenting architecture decisions — https://www.cognitect.com/blog/2011/11/15/documenting-architecture-decisions |
| 109 | R | güçlü | 2023-05-09 | Chen ve ark., FrugalGPT — https://arxiv.org/abs/2305.05176 |
| 110 | R | orta | 2023-10-19 | AutoMix — https://arxiv.org/abs/2310.12963 |
| 111 | R | orta | 2022-12-15 | Bai ve ark., Constitutional AI — https://arxiv.org/abs/2212.08073 |
| 112 | R | güçlü | 2023 | Zheng ve ark., Judging LLM-as-a-Judge — https://arxiv.org/abs/2306.05685 |
| 113 | R | orta | 2024-10-14 | Zhuge ve ark., Agent-as-a-Judge — https://arxiv.org/abs/2410.10934 |
| 114 | R | orta | 2026-06 | Kohli, Nine Judges, Two Effective Votes — https://machinelearning.apple.com/research/correlated-llm-evaluation-panels |
| 115 | R | güçlü | 2025-06-09 | Correlated Errors in Large Language Models — https://arxiv.org/abs/2506.07962 |
| 116 | S | orta | 2023-10-20 | Sharma ve ark., sycophancy (arama özetinden) — https://arxiv.org/abs/2310.13548 |
| 117 | R | orta | 2026-08-26 | Anchoring Bias in LLM-as-a-Judge Systems — https://arxiv.org/abs/2608.25869 |
| 118 | R | orta | 2024-08-17 | Anagnostidis ve Bulian — https://arxiv.org/abs/2408.11865 |
| 119 | B | orta | 2026-07-27 | Redwood, Untrusted advice for AI control — https://blog.redwoodresearch.org/p/untrusted-advice-for-ai-control-short |
| 120 | S | zayıf | 2024 | Smit ve ark., Should we be going MAD? (arama özetinden) — https://proceedings.mlr.press/v235/smit24a.html |
| 121 | P | güçlü | 2025-07-01 | Microsoft, SetThreadExecutionState; Modern Standby — https://learn.microsoft.com/en-us/windows/win32/api/winbase/nf-winbase-setthreadexecutionstate ; https://learn.microsoft.com/en-us/windows-hardware/design/device-experiences/modern-standby |
| 122 | P | güçlü | 2026-10-21 | Microsoft, PowerToys Awake — https://learn.microsoft.com/en-us/windows/powertoys/awake |
| 123 | P | güçlü | 2021-12-15 | Microsoft, powercfg — https://learn.microsoft.com/en-us/windows-hardware/design/device-experiences/powercfg-command-line-options |
| 124 | P | orta | tarihsiz | OpenAI, Reasoning best practices — https://developers.openai.com/api/docs/guides/reasoning-best-practices |

**Doğrulanamayanlar:** `RemoteTrigger` araç adı (dokümanda yok; rutin API tetikleyicisi var [11]); mod zamanlayıcı API'si
[16]; `CLAUDE_CODE_STOP_HOOK_BLOCK_CAP`'in üst sınırı; Claude Code ya da Managed Agents için azami oturum süresi; `/goal`'un
sıkıştırma sonrası davranışı (dokümanda yazmıyor); Opus ve Fable'ın bağlam farkındalığı [19]; OWASP Agentic AI Threats and
Mitigations belgesi; Devin "bloklanınca sorar" davranışının belgelenmiş hâli; Windows Update'in gece yeniden başlatması
için Microsoft kaynağı. Bu raporda hiçbiri bir karara tek dayanak olarak kullanılmadı.
