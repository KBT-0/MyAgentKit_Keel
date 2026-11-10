# graphify: nerede token kazandırır, nerede kaybettirir; kural ve ölçüm protokolü

Soru (sahip, 2026-11-09): "Graphify doğru yerde tasarruf, yanlış yerde zarar; araştır, kurallandır, sınırla." PLAN
maddesi 9. Araştırma 2026-11-09'da yapıldı ve PLAN'da duruyordu; bu rapor onu PLAN'dan çıkarıp derecelendirir, kitin
kuralını yazar (`core/docs/WORKFLOW.md`, "MCP hygiene" altındaki graphify paragrafı) ve leeway'de koşulacak ölçümün
protokolünü verir. Kuralın kendisi 2026-11-10'da yazıldı.

Etiketler `context-hygiene.md` ile aynı: **P** vendor birincil doküman, **R** araştırma/benchmark, **B** blog/pratisyen,
**F** forum/issue, **S** ikincil. Kanıt dili: **vendor beyanı**, **ölçüm**, **anekdot**, **çıkarım**.

---

## 1) Durum (2026-11-10, bizim okumamız)

- Skill 0.6.7 global kurulu (`~/.claude/skills/graphify/SKILL.md`, Mayıs 2026; CLI `graphify`, uv aracı `graphifyy`
  0.6.7). Hook yok; hiçbir projede `graphify-out/` yok: hiç koşmadı, bugünkü maliyeti sıfır.
- Ama sahibin ev dizinindeki `~/CLAUDE.md` bir "## graphify" bloğu taşıyordu: "mimari sorudan önce GRAPH_REPORT.md'yi
  oku", "kod değiştirince `graphify update .` çalıştır". Ev dizini altındaki her projede her lead bunu yüklüyordu; grafik
  olmadığı için zarar etmedi ama ilk grafikte bulgu 3'teki "önce oku" maliyetini her soruya bindirecekti. Blok
  2026-11-10'da kaldırıldı (metni graphify işçisinin RESULT dosyasında). `~/.claude/CLAUDE.md`'deki `/graphify`
  tetik satırı kaldı: yalnız slash komutunu skill'e bağlar, bir şey okutmaz.

## 2) Bulgular

### Bulgu 1. Kod çıkarımı yerel ve token'sız; dokümanlar ve görseller LLM alt ajanı ister (vendor beyanı, kod okundu)

- **P [4] skill metni, Step 3:** kod dosyaları tree-sitter AST ile "deterministic, free" çıkarılır; doküman, makale ve
  görseller paralel alt ajanlara gider (parça başına 20–25 dosya, `ceil(dosya/22)` ajan), dosya başına cache'lenir.
  Yalnız kod içeren bir derlemde Part B hiç koşmaz ("Fast path").
- **P [4] Step 5:** topluluk adlarını oturumun kendi modeli yazar (rapor başına birkaç yüz–birkaç bin token; **çıkarım**,
  ölçülmedi). Yani "kod-only = sıfır API token" yaklaşık doğrudur, tam sıfır değildir.
- **P [4] "For --update" ve CLI `graphify update <path>`:** yalnız değişen dosyalar; değişiklik yalnız kodsa "skipping
  semantic extraction (no LLM needed)". Bizim okumamız (graphify 0.6.7 `detect.py`): `node_modules`, `build`, `dist`,
  `graphify-out`, sanal ortamlar ve nokta ile başlayan klasörler (`.myagentkit`, `.claude`) varsayılan olarak atlanır;
  başka hariç tutma `.graphifyignore` dosyasıyla yapılır (gitignore sözdizimi; `.gitignore` okunmaz).
- **P [4] Step 2:** 200'den fazla dosya ya da 2 milyondan fazla kelimede skill durur ve hangi alt klasörde koşacağını
  sorar.
- **P [4] sorgu:** `graphify query` cevabı varsayılan 2000 token tavanlıdır (`--budget N`).

### Bulgu 2. "71x" iddiası tek seçilmiş derlemden; bağımsız ölçümler karışık

- **B [2] graphify.com blogu:** "71x daha az token"; tek, seçilmiş, karışık (kod + doküman) derlem, harness yok
  (**vendor beyanı**).
- **B/S [1][3] bağımsız yazılar (pantheon-org analizi, mejba.me):** FastAPI üzerinde 11 soruda okunan dosya %14 azaldı
  ama girdi token'ı **%49 arttı**; tek bir YouTube koşusunda token %18 azaldı, üç sorgunun ikisi ıskaladı (**anekdot**,
  küçük örnek; PLAN'daki not hangi rakamın hangi yazıdan geldiğini ayırmamış, ikisi birlikte okunmalı).
- **F issue #985 (graphify deposu, açık):** sıradan sorularda düz Claude Code eşit ya da daha az token harcıyor
  (**anekdot**, kullanıcı raporu).

### Bulgu 3. Zarar "her soruda önce raporu oku" talimatından ve hook dürtmesinden geliyor

- **F issue #580:** CLAUDE.md'deki "önce GRAPH_REPORT.md'yi oku" satırı soru başına 12–25k token ekliyor (**anekdot**,
  kullanıcı ölçümü). `graphify claude install` tam bu satırı ve bir hook'u projeye yazar; bu yüzden kitte çalıştırılmaz.
- **F/S 0.9.87 sürüm notu (PLAN'da):** hook dürtmesi 87 transkriptte 651k token; sınırı 0.9.87 getirdi. Kurulu sürüm
  0.6.7: hook kurulmadığı sürece etkisi yok (**çıkarım**).

### Bulgu 4. Kazancın yeri dar: büyük, yabancı repoda çapraz dosya sorusu (çıkarım, bulgu 2–3'ten)

- Yaklaşık 20k satırın altındaki repoda kazanç yok: grep + birkaç okuma zaten ucuz.
- Düzenleme, debug ve tam metin aramada kazanç yok: dosya yine okunur, grafik üstüne eklenir.
- Kazanç adayı: "ne neyi çağırır", "A B'ye nasıl ulaşır", "bu struct değişirse ne etkilenir" soruları, 3+ dosyaya yayılan.
- Leeway (2026-11-10, `git ls-files` + `wc -l`): `engine` 8,7k, `game` 9,3k, `tests` 7,5k satır C++ (248 dosya,
  25,5k satır); `tools` 49k satır Python, `prototypes` 13k, kitin `scripts`'i 28,5k; 1.040 `.md`. Oyun kodu tek başına
  eşiğin hemen üstünde; ölçüm (bölüm 4) kazancın gerçekten olup olmadığını söyleyecek.

## 3) Kural (kitte: `core/docs/WORKFLOW.md`, "MCP hygiene" altındaki graphify paragrafı)

- graphify'ı **yalnız sahip çağırır**; lead ya da işçi kendiliğinden `/graphify` ya da `graphify claude install`
  koşmaz.
- Yalnız sahibin **o projenin** `CLAUDE.md`'sine `## graphify` bloğu koyarak açtığı projede; ev dizinindeki ya da
  kullanıcı düzeyindeki dosyada asla. Kitin kendi deposunda hayır (küçük ve bilinen).
- İlk koşu **kod-only, `--no-viz`**; hariç: `node_modules`, `.myagentkit`, `graphify-out`, transkriptler, görseller
  (`.graphifyignore`). Doküman çıkarımı ancak sahip "N dosya × M ajan" tahminini duyup "evet" derse.
- Blok "her soruda önce GRAPH_REPORT oku" demez; şunu der: çapraz dosya sorusunda (ne neyi çağırır, A B'ye nasıl
  ulaşır, değişiklik etkisi) `graphify query/path/explain` koşulabilir; düzenleme, debug ve tam metin arama dosyaları
  okur. Kod değişikliğinden sonra `graphify update .` yalnız blok varken (AST, API maliyeti yok). `--watch` ve
  post-commit hook yok.
- Ölçüm kazanç göstermezse blok kaldırılır; proje için graphify kapanır.

## 4) Ölçüm protokolü (leeway, hazır, koşulmadı)

Dosyalar kitin `.myagentkit/v016-reset/graphify-trial/` klasöründe (git dışı): `questions.md` (beş çapraz dosya sorusu
ve referans cevapları), `graphify-block.md` (B kolunun proje bloğu), `run_trial.sh`, `README.md` (sahibin adımları).

- Her soru iki taze `claude -p --output-format json` oturumunda, leeway'in geçici bir klonunda sorulur: **A** olduğu
  gibi, **B** proje bloğu + sahibin ürettiği `graphify-out/` kopyalanmış. Aynı model, aynı araçlar (B'de ayrıca yalnız
  `graphify query/path/explain`).
- Her oturumun JSON'undan toplam token (girdi + cache yazma + cache okuma + çıktı), maliyet ve tur sayısı
  `trial-table.md`'ye; cevaplar `out/`'a. Lead doğruluğu referans cevaplara göre işaretler.
- Karar kuralı: B, beş sorunun toplamında daha az token harcamıyorsa ya da A'dan daha çok yanlış veriyorsa leeway için
  graphify kapanır. Grafiği kurmanın maliyeti ayrıca yazılır (kod-only'de Step 5'in birkaç bin token'ı).

## Kaynaklar

1. [B] pantheon-org.github.io/agentic-context/analysis/graphify
2. [B] graphify.com/blog/reduce-claude-code-token-usage (vendor blogu)
3. [B] mejba.me/blog/graphify-knowledge-graph-codebase-claude-code
4. [P] `~/.claude/skills/graphify/SKILL.md` 0.6.7 ve kurulu paketin `graphify/detect.py`'si (2026-11-10 okundu)
5. [F] graphify deposu, issue #580 ve #985; 0.9.87 sürüm notu (PLAN maddesi 9'dan; bu raporda yeniden açılmadı)
