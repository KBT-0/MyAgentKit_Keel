<!-- BINDING RESEARCH: every proposal about the kit's own test suite (check_kit), the project gate's --self-test, test tiers or test-time budgets must cite a numbered finding of this report, or say that the report has no evidence on the point. Owner decision of 2026-10-18. -->

# Kit'in kendi testleri: check_kit, gate --self-test, test katmanları ve süre bütçesi — kanıta dayalı araştırma raporu

Tarih: 2026-10-18. Kapsam: (a) bir gate'in/kontrolün kendisini negatif testle sınaması, (b) şablon/kit projelerinin kendi kabul (acceptance) suite'leri, (c) test süresi normları, katmanlama, zaman bütçesi ve suite büyümesinin kontrolü. İki araştırma turu: tur 1 arama özetleri (sayfalar tam okunmadı), tur 2 birincil sayfalar. Kaynak numaraları `[n]`, tam liste bölüm 4'te. Güvenilirlik etiketleri: **R** (resmi doküman / repo dosyası / API verisi), **P** (hakemli/preprint), **B** (blog / vendor), **F** (forum/anekdot), **S** (ikincil aktarım; birincil doğrulanamadı).

## Bağlam: kit'in ölçülmüş gerçekleri

- Test sayısı: 69 (2026-10-03) -> ~680 (2026-10-08) -> 1342 (2026-10-18).
- Kit CI süresi: 2-3 dk (2026-09-06, 2026-10-03) -> 28 dk (2026-10-08) -> 59 dk (2026-10-17).
- Windows'ta tam `check_kit`: 50-52 dk (2026-10-18). Acceptance birimi tek başına 1938 sn / 1964 sn (2026-10-15, RESEARCH_LOG).
- Projelerden gelen rapor: `check.sh --self-test` ~3 saate kadar çıkıyor (issue #80).
- Sahibin kuralı: kaynağı olmayan ve alanda benzer pratiği bulunmayan bir pratik silinir.

Araştırma bu üç şeye bakıyor: gate'in tam-build'li self-test'i, 1342 testlik tek bir seri suite ve büyümenin denetimi.

---

## 1) Yönetici özeti

Her madde: **Doğrulandı / Çürütüldü / Kanıt yok** = kit'in mevcut pratiği alanda desteklenen bir pratik mi? Bulgu numaraları sonraki bölümlerde ve "Kit için sonuç"ta `bulgu N` olarak anılır.

1. **Tek bir kontrolü küçük bir fixture'a karşı negatif testle sınamak standart pratik.** Semgrep `ruleid:`/`ok:` ve `semgrep --test` [1]; ESLint RuleTester her kural için en az bir geçerli ve bir geçersiz case ister [2]; OPA/Conftest `_test.rego` + `conftest verify` (kötü girdi deny, iyi girdi 0 deny) [3]. Hepsi tek kontrolü, küçük fixture ile, süreç içinde, milisaniye-saniye düzeyinde çalıştırır. → **Doğrulandı.**
2. **Gate'in tamamının self-test'i (CI gate'ine ihlal enjekte et, kırmızı bekle, geri al) için yerleşik pratik bulunamadı.** CI canary commit, fire drill, branch protection testi aramaları yalnızca vendor "guardrail" yazıları ve örnek bir hook döndürdü; harness ya da çalışma yok [8]. Her negatif case'te tüm build'i yeniden koşan bir kaynak da bulunmadı (ona karşı açık bir kaynak da yok; araçlar böyle kurulmuyor) [1][2][3]. Caveat: bu, arama sonucunun yokluğudur, yokluğun kanıtı değil; güvenlik-kontrolü doğrulama literatüründe chaos/GameDay benzeri tatbikatlar olabilir, bulunmadı ve doğrulanmadı. → **Kanıt yok.**
3. **"Testleri test eden" en yakın pratik mutation testing; pahalı olduğu biliniyor ve her commit'te tam koşulmuyor.** Google geleneksel mutation analizini "computationally prohibitive" buluyor; çözüm diff-bazlı, code review'da yalnızca değişen satırlarda, filtrelenmiş/sınırlı mutant (~17M üretilen, 2M gösterilen, 760k değişiklik) [4][5]. Stryker `--incremental` yalnızca değişen kod/testi tekrar koşar (örnekte 3.965 sonuçtan 3.731'i yeniden kullanıldı, 234 koşuldu) [6]. "PR'da incremental, gece tam" tavsiyesi topluluk görüşü, resmi değil [6]. → **Kısmen doğrulandı (zayıf kanıt):** pahalı meta-testler diff üzerinde ya da zamanlanmış koşar, her commit'te tam değil.
4. **Şablon/kit projelerinin kabul testi "birkaç cevap setinden proje üret, dosya/exit kodu doğrula, (bazen) üretilen projenin kendi testini koş" biçiminde ve küçük.** pytest-cookies `bake()` [9], pytest-copie [10], copier-template-tester (`_post_tasks` ile üretilen projenin kendi testi, ör. `uv run pytest`) [11], Yeoman `helpers.run()` [12]. cookiecutter-django bunu tam eşleşmeyle yapıyor: `tests/` altında az dosya (`test_cookiecutter_generation.py`, `test_hooks.py`, `test_docker.sh`, `test_bare.sh`, `test_generate.ps1`), CI'da projeyi bake edip projenin kendi suite'ini paralel matrix işlerinde koşuyor (4 docker + 7 bare + 1 Windows smoke) [36][37]. → **Doğrulandı, küçük biçimde:** bake-and-run var, ama varyant başına bir adım olarak ve paralel işlerle; 1300 test olarak değil.
5. **~1300 testlik (ya da 50 dk'lık) bir kendi-suite'i olan şablon/kit projesi bulunamadı.** Peer'ler: cookiecutter-django az dosya [37]; wshobson/agents `tests/` yok, `evals/`, `tools/tests/`, `plugins/plugin-eval`, yapı doğrulaması + mütevazı pytest [43]; anthropics/claude-code yalnızca `mod-tests.yml` (typecheck + `claude plugin test`, yalnızca `mods/**` değişince) [44]; anthropics/claude-plugins-official üst düzey test dizini görülmedi (genişletilmedi) [45]; agent-kit/plugin repolarında tipik olan lint/doğrulama düzeyi CI [17]. En yakın agent-kit peer'i obra/superpowers: 17 test alt dizini, `.github` içinde workflow yok (testler yerelde), `tests/claude-code` iki katmanlı: varsayılan hızlı (~2 dk) ve `--integration` yavaş (10-30 dk), test başı timeout varsayılan 5 dk (integration için 1800 sn, CI için 900 sn önerisi) [41][42]. Caveat: arama sığ; birçok repo'nun workflow dosyası açılmadı. → **Kanıt yok** (benzer büyüklükte bir pratik yok); en yakın peer'de suite var ama hızlı/yavaş ikiye bölünmüş.
6. **Tek bir 50 dk'lık seri suite, 10 dakika normuna aykırı.** Beck/Andres: "tüm sistemi otomatik build et ve tüm testleri on dakikada koş; on dakikadan uzun build daha az kullanılır" [18] (ikincil aktarım). Fowler CI makalesi (birincil): "on dakikalık build kuralı makul"; "uzun süren build Continuous Integration'ın kanını emer"; commit build hızlı olmalı ve "bug yakalama gücünü azaltan kısayollar alır"; ikinci aşama gerçek DB/uçtan uca, "birkaç saat sürebilir", "her commit'te koşmayabilir"; "10 dakika kuralından yavaşlamaya başlar başlamaz harekete geç" [29]. DORA: testler "birkaç dakikadan fazla sürmemeli, üst sınır ~10 dk"; uzunsa verimliliği artır, paralel işlem ekle ya da "uzun testleri ayrı bir build'e taşı" [30]; "10 dakikadan kısa geri bildirim" [31]. SWE at Google: "Suite ne kadar yavaşsa o kadar seyrek koşulur ve o kadar az fayda sağlar" [32]. → **Çürütüldü:** tek seri 50 dk suite normla çelişir; norm hızlı commit aşaması + ayrı yavaş katman.
7. **Katmanlama (hızlı ve başarısız olması muhtemel kontroller önce, yavaş entegrasyon/acceptance sonra) yerleşik.** Fowler staged build [29]; DORA "unit testler yavaş acceptance'tan önce" [31]; Molecule path filter'lı iş + rol başına job, pre-commit dışı [16]; dotfiles repolarında günlük tam iş + değişen yükleyicileri test eden iş [15]; Homebrew `brew test-bot` aşamalı (`--only-tap-syntax`, `--only-formulae`, PR-only) [14]; bir proje pytest-timeout'u bırakıp "yavaş testler uzun timeout yerine günlük build'e taşınmalı" demiş [24]. → **Doğrulandı.**
8. **Test boyutuna bağlı sert zaman sınırı altyapı tarafından uygulanıyor (Bazel).** Bazel Test Encyclopedia: small=short 60 sn, medium=moderate 300 sn, large=long 900 sn, enormous=eternal 3600 sn; varsayılan boyut medium; `--test_timeout` geçersiz kılar; runner testi öldürüp başarısız sayabilir [33]. SWE at Google bölüm 11: boyutlar süreyle değil **kaynakla** tanımlı (tek süreç / tek makine / her yer), kitapta sayısal sınır yok, boyutlar "altyapının uygulayabileceği kısıtlar" olarak kodlanır [32]. İkincil kaynaklardaki "small <1 sn, medium <5 dk, large <15 dk" rakamları birbirini tutmuyor ve kitap bölümüyle desteklenmiyor [21][22][23] (large=15 dk tutarlı). → **Doğrulandı (Bazel için, hedef/test başına sert tavan); proje düzeyi toplam bütçe için kanıt yok.**
9. **Zaman bütçesini zorlayan araçlar var; bir proje politikası olarak kullanıldığı vaka çalışması yok.** `pytest --durations=N` yavaş testleri listeler; pytest-timeout "kilitlenen/asılı testleri yakalamak için tasarlandı, hassas zamanlama ya da performans regresyonu için değil", son çare [34]; pytest-fail-slow geçen ama yavaş testi başarısız sayar (`@pytest.mark.fail_slow("5s")`, `--fail-slow DURATION`, yalnızca CI'da etkinleştirilebilir) [35]; CI runner'ları yerelden 2-5x yavaş olabilir [24]; katman başına CI job timeout'u olmazsa testler "sert tavanı sinyalsiz aşabilir" (zayıf kaynak) [25]. Dikkat: peer CI'larda (cookiecutter-django, wshobson) `timeout-minutes` yok [36][43]. → **Kısmen doğrulandı** (araç var, politika vakası yok).
10. **Suite büyümesinin kontrolü için kanıt ince.** Yoo & Harman: suite'ler yazılımla büyür, tümünü koşmak çok pahalı olur; çözüm sınıfları minimizasyon, seçim, önceliklendirme [26]; maliyet-farkındalıklı indirgeme yalnızca sayıyı değil çalışma süresini de kullanır [27]. Fowler: ikinci aşama bir bug yakalarsa "bu, commit build'in bir teste daha ihtiyacı olduğunun işaretidir" [29]; DORA: acceptance test hata bulursa daha erken yakalamak için unit test ekle [31]. SWE at Google: "kötü bir suite, hiç suite olmamasından kötü olabilir"; "yavaş ya da marjinal testleri refactor et" [32]. **Bulunamadı:** test silme/emekliye ayırma politikası, "bug başına test" pratiği üzerine uygulayıcı politikası, Fowler'ın test impact analysis yazısı. → **Kanıt yok** (silme/emeklilik için); büyümeyi **eklerken** doğru katmana koymak için kanıt var.
11. **Piramit çıkarımı (çıkarım, kanıt değil):** Fowler test piramidi: çok sayıda küçük hızlı test, az sayıda geniş yavaş test [28]. 1342 testin 50 dk sürmesi, ortalama testin ~2,2 sn olduğu anlamına gelir; bu da çoğunun süreç başlatan/git/shell testi olduğunu, yani ters piramit olduğunu düşündürür.
12. **Karşılaştırma süreleri (yaklaşık, API verisi, süre = updated_at - run_started_at):** cookiecutter-django ci.yml 4 dk 11 sn - 9 dk 01 sn (7 koşu, Ekim 2026) [38]; pre-commit ana workflow 8 dk 02 sn - 11 dk 20 sn [40]; copier PR koşuları 19 dk 12 sn, 19 dk 31 sn, 26 dk 03 sn, bir push koşusu 1 sa 19 dk 56 sn (kuyruk/matrix içerebilir) [39]. Yani olgun bir şablon motorunun CI'ı ~20-25 dk duvar saati, ama **paralel matrix işleri** üzerinden, tek seri 50 dk koşu değil. Next.js test türlerini ayırır (unit "çok hızlı", e2e, development, production, integration) ve belirli dizin deseniyle koşmayı önerir; dokümanda süre rakamı yok [46].

---

## 2) Soru bazlı bulgular

### S1. Gate'in kendisi nasıl sınanır? (bulgu 1, 2, 3)

Negatif test pratiği kontrol düzeyinde yaşar: kural + küçük girdi + beklenen sonuç. Semgrep'te `ruleid:` işaretli satırlar eşleşmek ZORUNDA (false-negative koruması), `ok:` işaretliler eşleşmemeli [1]. ESLint RuleTester `valid` ve `invalid` case ister; invalid case hata sayısı/messageId/autofix çıktısını doğrular [2]. Conftest'te politikanın yanında `_test.rego` durur [3]. Bunların hiçbiri tüm pipeline'ı case başına yeniden çalıştırmaz. En yakın gerçek biçim: kontrolün kendi reposunda yaşayan ve normal test suite'inde koşan fixture testleri, artı gate ilk bağlandığında ara sıra elle yapılan tatbikat (tur 1 notu; bu son kısım için ayrı bir kaynak yok).

"Hiç kırmızı görmemiş test hiçbir şey kanıtlamaz" kuralı (TDD red adımı) agent-skill dokümanlarında tekrarlanıyor; konvansiyon, sert otorite yok [7] (F/S). Bu, negatif fixture testini destekler; tüm-gate self-test'ini desteklemez.

Mutation testing (bulgu 3) "testleri test etme" alanının pahalı ucudur ve onun bile her commit'te tam koşulmaması, tüm-build'li self-test için zıt yönde bir uyarıdır [4][5][6].

Kapsanmayanlar (aranmadı/doğrulanmadı): CodeQL query testleri, Checkov/tfsec, ShellCheck/clang-tidy fixture'ları, pre-commit repoları, Danger.js, Bazel (bu soru için); mutmut/PIT rakamları.

### S2. Şablon/kit projeleri büyük bir kabul suite'i kuruyor mu? (bulgu 4, 5, 12)

Model "N proje üret, doğrula, temizle" [9][10][11][12]. Scaffolder'larda e2e: create-react-app deposunda `tasks/e2e-simple.sh`, `e2e-installs.sh`, `e2e-kitchensink.sh`, `e2e-behavior.sh` ve yerel registry (verdaccio) vardı [13]; yalnızca dosya listesi görüldü, süre ve CI bağlantısı doğrulanmadı (S). Homebrew `brew test-bot` ağır uçtur: sistemi hazırlar, formülü kurar, testleri/kontrolleri koşar, bottle eder, bağımlı formülleri test eder; makine/VM çiftliğinde [14]. Dotfiles CI'ı "temiz VM'de yükleyici hatasız bitiyor mu" düzeyinde smoke, bazen idempotency için iki kez; bir repo günlük tam iş + değişen yükleyici işi, bir diğeri Bats [15]. Molecule varsayılan dizisi create/converge/idempotence/verify/destroy, "dakikalar sürer", pre-commit dışında, rol başına iş, yalnızca o rolün dosyaları değişince; senaryosu olmayan roller test edilmez [16].

cookiecutter-django, Keel'in "bake et, projenin kendi self-test'ini koş" acceptance'ına tam eşleşir (ama paralel matrix işleri olarak; `fail-fast: false`, `timeout-minutes` yok) [36][37]. Agent-kit/plugin repoları: lint/doğrulama düzeyi CI tipik; 1340 teste benzer bir şey bulunamadı [17][41][43][44][45].

### S3. Süre normu, katmanlar, zaman bütçesi (bulgu 6, 7, 8, 9)

Norm: ~10 dk commit aşaması, geri kalanı ayrı yavaş katman [18][29][30][31][32]. Katmanlama örnekleri [14][15][16][24][29][31][42]. Boyut → sert timeout: Bazel [33]; kaynak-bazlı boyutlar ve zaman rakamı verilmemesi: SWE at Google [32]. Zorlama araçları: pytest `--durations`, pytest-timeout, pytest-fail-slow [34][35]; ikincil zayıf öneri: katman başı CI job timeout'u [25]. Proje düzeyinde "test bütçesi"ni politika olarak uygulayan birincil kaynak bulunamadı; Bazel boyut timeout'ları en yakın olanı.

### S4. Büyüme kontrolü (bulgu 10, 11)

Bkz. bulgu 10 ve 11. Uygulayıcı politikası (test emekliliği, bug başına test) ve test impact analysis bulunamadı.

### S5. Süre sınırları asılı testi mi yakalar, yavaş makineyi mi? (v0.12.1, 2026-10-21)

Tetik: 865c3a3'te hızlı katmanın 55 biriminden 42'si düştü; başka bir projenin Blender boru hattı 20 CPU'lu makineyi yüklüyordu, asılı test yoktu. Birim tavanı 480 s ve katman bütçesi 600 s (ikisi de SCALE 3 ile) bu makinenin hızına göre ayarlanmıştı; bütçe dolunca çalışan birimler durduruluyor, kuyruktakiler başlamıyordu. Aynı gün aynı yük, ölçeklenmemiş 30/60 s test-içi sınırlarla 5 yavaş birimi düşürdü.

Bulgular (hepsi 2026-10-21'de okundu):

- **Süre sınırı asılı-test korumasıdır, hız ölçüsü değil.** pytest-timeout: "designed to catch excessively long test durations like deadlocked or hanging tests", "not designed for precise timings or performance regressions"; sınırlar "a last resort, not an expected failure mode"; sınır sıkıysa öneri "firstly make the timeouts larger" [47]. Bazel: "A test is not penalized for an overgenerous timeout, although a warning may be issued"; boyutlar 60/300/900/3600 s; yavaş koşullar için `--test_timeout` [33]. Go: `go test -timeout` varsayılanı 10 dk, test binary'si başına; aşılırsa panic [48]. CTest: `--timeout` yalnızca varsayılan bir sınır koyar [49].
- **Yük, geçici başarısızlığın (flaky) en büyük kaynaklarından.** Silva ve diğ. 2023 (52 proje, 27 kaynak yapılandırması): flaky testlerin %46,5'i kaynağa bağlı (RAFT), yani kaynak ayarıyla önlenebilir [50]. Google: büyük (çok RAM'li, büyük binary'li) testler daha sık flaky; yazarın notu: bazı testler test ve altyapı kodundaki timeout'lara takılıyor [51]. Bir multivocal derleme: async wait, flaky düzeltmelerinin yaklaşık yarısı [52].
- **Paralellik yükü hesaba katabilir.** GNU make `-l`: en az bir iş çalışırken yük ortalaması sınırın altına inene kadar yeni iş başlatmaz, ilk iş her zaman başlar [53]. CTest `--test-load`: "try not to start tests when they may cause the CPU load to pass above a given threshold"; `-j` varsayılanı işlemci sayısı [49]. Go `-p` varsayılanı GOMAXPROCS, yani CPU sayısı [48]. Python: `os.getloadavg()` yalnızca Unix'te; Windows'ta standart kütüphanede yük yok [54] (GetSystemTimes'ın boşta/çekirdek/kullanıcı süreleri ctypes ile okunur; çıkarım, kaynak Win32 API).
- GitHub barındırılan runner'da bir iş en fazla 6 saat (360 dk) çalışır, sonra sonlandırılıp düşer [55].

Kit için sonuç (v0.12.1'de uygulandı): (1) birim tavanı yalnızca asılı-test korumasıdır, ölçülenin çok üstünde: hızlı 1800 s (yük altındaki en yavaş hızlı birim 461 s'nin ~4 katı), yavaş 5400 s (tam yükteki en yavaş 2703 s'nin 2 katı); (2) katman bütçesi artık bir **hedef**tir: aşılırsa saniyesiyle WARNING basılır, hiçbir şeyi düşürmez, birim durdurmaz (asılı test tavana takılır; Bazel'in "uyarı verilebilir"ine denk); (3) aynı anda koşan birim sayısı, başlangıçta başka işin meşgul ettiği CPU'ları düşer (POSIX: 1 dk yük ortalaması; Windows: GetSystemTimes ile 1 s örnek; make `-l` gibi, ama yalnızca başlangıçta); test-içi sınırların çarpanı yüksüz çalışmanınki kalır (yük, eksilen birimlerin yerini alır); (4) bugün yükte düşen test-içi sınırlar SCALE ile çarpılır. Çıkarım: yük ortalamasını "meşgul CPU" saymak make/CTest'in eşik pratiğinin sadeleştirilmiş hâlidir; birim başına dinamik kapı (make `-l`) gerekirse sonraki adımdır.

---

## 3) Kit için sonuç

Aşağıdaki sonuçlar sahibin kuralına ("kaynağı ve alandaki benzer pratiği olmayan pratik silinir") ve yukarıdaki bulgulara dayanır. Çıkarım olan kısımlar açıkça işaretlenmiştir.

1. **Proje gate'inin tüm-gate `--self-test`'i kaldırılır.** Gerekçe: her case için tam build'li tüm-gate self-test'in alanda yerleşik bir karşılığı bulunamadı (bulgu 2); sahibin kuralı kaynaksız pratiği siler. Yerine **kontrol başına fixture negatif testleri** gelir, build koşmadan: her kontrol küçük bir fixture'a karşı kötü girdide kırmızı, iyi girdide yeşil verir ve normal test suite'inde koşar (bulgu 1; saniyeler). Gate ilk bağlandığında ara sıra elle tatbikat yapılabilir (bulgu 2'nin tur 1 notu, ek kaynak yok; çıkarım). Bu, issue #80'deki ~3 saatlik süreyi de ortadan kaldırır.
2. **`check_kit` kalır, ama hızlı katman ve yavaş katman olarak bölünür.** Hızlı katman (hedef Windows'ta <=10 dk; bulgu 6, 7): saf birim/fixture testleri, yapısal kontroller. Yavaş katman: bootstrap/acceptance (bake-and-run: bulgu 4) ve POSIX sinyal suite'leri; CI'da hızlı katmanla **paralel** ve release öncesi koşar (bulgu 7, 12: peer'ler paralel matrix kullanıyor; superpowers hızlı/yavaş ayrımı: bulgu 5). Tek seri 50 dk suite normla çelişir (bulgu 6). Acceptance'ı küçük biçimde (varyant başına bir bake-and-run adımı) tutmak da kanıtlıdır (bulgu 4). Çıkarım: 10 dk hedefi Fowler/DORA'daki commit-build normundan gelir; Windows'a özgü bir kaynak yok.
3. **Zorlanan bir süre bütçesi eklenir.** Katman başına CI job timeout'u ve test başına tavan: Bazel boyut timeout'u en yakın örnek (bulgu 8); araçlar `pytest-timeout` (yalnızca asılı testler için, son çare) ve `pytest-fail-slow` (yavaş-ama-geçen testleri kırar) (bulgu 9). Uyarı: sayısal değerler (ör. 60/300/900 sn) Bazel'in varsayılanlarıdır, kit için doğrulanmış değil; kit'in kendi ölçümleriyle ve peer süreleriyle (bulgu 12) seçilmelidir. Proje düzeyinde toplam bütçeyi politika olarak uygulayan vaka çalışması yok (bulgu 9); bu kısım çıkarımdır. v0.12.1'den beri (S5): birim tavanı yalnızca asılı-test korumasıdır, katman bütçesi aşılınca uyarı basan bir hedeftir.
4. **Gereksiz/yinelenen testler birleştirilir.** Dayanak: suite büyümesi maliyet sorunudur ve çözüm sınıfı minimizasyon/seçimdir (bulgu 10); yavaş ya da marjinal testler refactor edilir (bulgu 10, SWE at Google); piramit çıkarımı çoğu testin yavaş olduğunu düşündürüyor (bulgu 11). Bir acceptance testi hata bulursa, aynı hatayı yakalayan **hızlı** test eklenir (bulgu 10, DORA/Fowler). Test emekliliği/silme politikası için alanda kanıt yok (bulgu 10); birleştirme kararı kit'in kendi ölçümüne (hangi testler yavaş, hangileri aynı şeyi kapsıyor, `--durations`: bulgu 9) dayanmalı.

---

## 4) Kaynaklar

Tur 1 (arama özetleri; sayfalar tam okunmadı):

[1] https://semgrep.dev/docs/writing-rules/testing-rules — Semgrep: Testing rules — R
[2] https://pt-br.eslint.org/docs/v8.x/extend/custom-rule-tutorial — ESLint custom rule tutorial, RuleTester (v8) — R (arama özeti)
[3] https://conftest.dev/ ; https://dev.to/pbnj/unit-test-your-configuration-files-3mnf ; https://oneuptime.com/blog/post/2026-01-28-opa-conftest-policy-testing/view — Conftest policy testing — R/B/B
[4] https://research.google/pubs/state-of-mutation-testing-at-google/ — Petrovic, Ivankovic, ICSE-SEIP 2018 — P
[5] https://research.google/pubs/practical-mutation-testing-at-scale-a-view-from-google/ (arXiv 2102.11378) — TSE 2021 — P
[6] https://stryker-mutator.io/blog/announcing-incremental-mode/ ; https://stryker-mutator.io/docs/stryker-js/incremental/ — Stryker incremental — R/B; gece-koşusu tavsiyesi: https://oneuptime.com/blog/post/2026-01-25-mutation-testing-with-stryker/view — B/S
[7] https://skills.sh/ (TDD skill sayfaları, ör. https://www.skills.sh/codeaholicguy/ai-devkit/tdd) — F/S
[8] https://hoop.dev/blog/ci-cd-accident-prevention-guardrails/ ; https://kindatechnical.com/git-version-control/server-side-hooks-pre-receive.html — vendor/örnek, test harness yok — B/S
[9] https://pytest-cookies.readthedocs.io/en/latest/getting_started/ — pytest-cookies — R
[10] https://pytest-copie.readthedocs.io/ — pytest-copie — R
[11] https://pypi.org/project/copier-template-tester/2.5.0/ — copier-template-tester — R
[12] https://yeoman.io/authoring/testing — Testing Generators — R
[13] https://code.morphllm.com/facebook/create-react-app/src/branch/3.x/tasks — CRA 3.x tasks listesi (mirror) — S
[14] https://docs.brew.sh/BrewTestBot — Homebrew BrewTestBot — R
[15] https://ashishb.net/programming/dotfiles-ci/ — B; https://github.com/iainelder/dotfiles — F; https://dev.to/shunk031/testable-dotfiles-management-building-development-environment-with-chezmoi-pbn (Bats) — F
[16] https://git.cqre.net/cqrenet/matrix-docker-ansible-deploy/raw/commit/c447e1528b6b954d115c84509ced859a67470a55/docs/molecule-testing.md — Molecule testing (mirror) — S
[17] https://www.claudepluginhub.com/marketplaces/yu-iskw-claude-plugin-template — Claude plugin template — S; https://github.com/aboudjem/10x — F
[18] https://www.stickyminds.com/article/keeping-your-build-under-ten-minutes — Beck & Andres, XP Explained 2e (2004) alıntısı — S
[19] https://www.goodreads.com/author_blog_posts/14566938-bliki-continuousintegrationcertification — Fowler bliki mirror — S
[20] https://gradle.com/solutions/dora-and-continuous-delivery/ ve diğer DORA ikincil sayfaları — B/S
[21] https://bazel.virtuslab.com/book/1~2~2/ — Test Sizes & Timeouts — S
[22] https://henrikwarne.com/2012/09/23/book-review-how-google-tests-software/ — 2012 — S
[23] https://pytest-test-categories.readthedocs.io/en/latest/user-guide/test-sizes.html — S
[24] https://lincc-ppt.readthedocs.io/en/latest/practices/pytest_timeout.html — B
[25] https://claudskills.com/skills/speed-budgets/SKILL.md — S (zayıf)
[26] https://www.cse.chalmers.se/~feldt/advice/yoo_2010_regression_testing_survey.pdf — Yoo & Harman, 2010 — P
[27] https://www.cs.allegheny.edu/sites/gkapfham/research/papers/Lin2012 — Lin vd., cost-aware reduction — P
[28] https://martinfowler.com/articles/practical-test-pyramid.html — Practical Test Pyramid, 2018 — B

Tur 2 (birincil sayfalar, 2026-10-18):

[29] https://martinfowler.com/articles/continuousIntegration.html — Fowler, Continuous Integration — R/B
[30] https://dora.dev/capabilities/continuous-integration/ — DORA CI — R
[31] https://dora.dev/capabilities/test-automation/ — DORA Test automation — R
[32] https://abseil.io/resources/swe-book/html/ch11.html — Software Engineering at Google, bölüm 11 — R
[33] https://bazel.build/reference/test-encyclopedia — Bazel Test Encyclopedia — R
[34] https://github.com/pytest-dev/pytest-timeout — R
[35] https://github.com/jwodder/pytest-fail-slow — R
[36] https://raw.githubusercontent.com/cookiecutter/cookiecutter-django/master/.github/workflows/ci.yml — R (repo dosyası)
[37] https://raw.githubusercontent.com/cookiecutter/cookiecutter-django/master/tests/test_docker.sh ve api.github.com/.../contents/tests — R
[38] https://api.github.com/repos/cookiecutter/cookiecutter-django/actions/workflows/ci.yml/runs — R (veri, süre yaklaşık)
[39] https://api.github.com/repos/copier-org/copier/actions/runs — R (yaklaşık)
[40] https://api.github.com/repos/pre-commit/pre-commit/actions/runs — R (yaklaşık)
[41] https://api.github.com/repos/obra/superpowers/contents/tests ve /contents/.github — R
[42] https://raw.githubusercontent.com/obra/superpowers/main/tests/claude-code/README.md — R
[43] https://raw.githubusercontent.com/wshobson/agents/main/.github/workflows/validate.yml — R
[44] https://raw.githubusercontent.com/anthropics/claude-code/main/.github/workflows/mod-tests.yml — R
[45] https://api.github.com/repos/anthropics/claude-plugins-official/contents — R
[46] https://github.com/vercel/next.js/blob/canary/contributing/core/testing.md — R

S5 (2026-10-21, sayfalar okundu):

[47] https://pypi.org/project/pytest-timeout/ — pytest-timeout README — R
[48] https://pkg.go.dev/cmd/go — `go test -timeout`, `-p` — R
[49] https://cmake.org/cmake/help/latest/manual/ctest.1.html — CTest `--test-load`, `-j`, `--timeout` — R
[50] https://arxiv.org/abs/2310.12132 — Silva ve diğ., The Effects of Computational Resources on Flaky Tests (2023) — R (özet)
[51] https://testing.googleblog.com/2017/04/where-do-our-flaky-tests-come-from.html — Google Testing Blog, Listfield 2017 — R (yalnızca başlık ve yazarın yorumları okunabildi)
[52] https://arxiv.org/pdf/2212.00908 — Test Flakiness' Causes, Detection, Impact and Responses: A Multivocal Review — R (arama özeti)
[53] https://www.gnu.org/software/make/manual/html_node/Parallel.html — GNU make, Parallel Execution, `-l` — R (arama özeti)
[54] https://docs.python.org/3/library/os.html — `os.getloadavg`, `os.cpu_count` — R
[55] https://docs.github.com/en/actions/reference/limits — GitHub Actions limits, job execution time — R

## 5) Dürüst boşluklar

Alanda ~1300 testlik ya da 50 dk'lık kendi-suite'i olan bir şablon/kit projesi bulunamadı. Doğrulanmadı: CRA e2e süreleri, Yeoman/brew süreleri, Anthropic'in plugin repoları için test rehberi, Fowler'ın test impact analysis yazısı, bug başına test / test emekliliği politikası, gerçek Claude plugin repolarının workflow'ları, proje düzeyinde "test bütçesi"ni politika olarak uygulayan birincil kaynak (Bazel boyut timeout'ları en yakın olanı), Next.js create-next-app testleri. Tur 1'deki DORA ve Fowler ikincil aktarımları tur 2'de birincil sayfalarla doğrulandı ([29][30][31]); [18][19][20] ikincil kaldı. Süre verileri (copier, pre-commit, cookiecutter-django) API'den yaklaşık hesaplandı ve kuyruk/matrix süresi içerebilir.
