<!-- BINDING RESEARCH: every proposal about the kit's test rules (when a test comes, whether a test or a gate check must be proven red, how a generated-content pipeline is tested) must cite a numbered finding of this report, or say that the report has no evidence on the point. Owner decision of 2026-10-18 (v0.12 decision 37) for (a) and (b); (c) is the leeway project's decision (leeway b9732d5), adopted by the kit as a recommendation. -->

# Kit'in test kuralları: test ne zaman gelir, kim RED kanıtlanır, üretilmiş içerik nasıl test edilir — kanıta dayalı araştırma raporu

Tarih: 2026-10-18. Kapsam: (a) "Mantık modülüne testsiz kod girmez; testler kodla birlikte ya da koddan önce yazılır"; (b) "Her yeni test ve her yeni gate kontrolü bir kez RED kanıtlanır"; (c) üretilmiş içerik pipeline'larının (prosedürel dünya/asset üretimi) testi. (a) ve (b) kit lead'inin araştırmasından (`.myagentkit/v012/research-test-rules.md`), (c) leeway projesinin raporundan (`docs/research/2026-10-18-pipeline-testing.md`, leeway reposu) gelir; bu rapor ikisini birleştirir ve yalnızca kaynaklı bulguları tutar. Kaynak numaraları `[n]`, tam liste bölüm 4'te. Güvenilirlik etiketleri: **R** (resmi doküman), **P** (hakemli/preprint), **B** (blog/vendor), **F** (forum/anekdot), **S** (ikincil aktarım; birincil doğrulanamadı). Önceki raporlara yalnızca atıf: `kit-self-checks.md` bulgu 1-3.

---

## 1) Yönetici özeti

Her madde: **Doğrulandı / Kısmen / Kanıt yok** = kuralın bu kısmı kaynakla ayakta mı?

1. **Test, değişiklikle birlikte gelir.** Google'da "her değişiklik hem özellik kodunu hem testi içermelidir"; testsiz değişikliği review'da bloklamak "tamamen makul" [3] (R). DORA: testleri geliştiriciler yazar ve bakar [4] (R). Anthropic: agent'a çalıştırabileceği bir doğrulama ver, "doğrulayamıyorsan yollama" [1] (R). → **Doğrulandı.**
2. **Testi koddan ÖNCE yazmanın ölçülmüş faydası yok.** Sıralamayı doğrudan ölçen tek çalışma: Fucci vd., 39 profesyonel, 82 veri noktası; "Sequencing ... had no important influence"; fayda ince taneli, düzenli adımlardan geliyor [5] (P). Sınır: gözlemsel, küçük örnek, kısa görevler [5]. TDD'nin kalite/üretkenlik etkisi literatürde tutarsız ("the jury is still out") [6][7] (P/S). Test-first'ü öneren kaynaklar var (DORA [4], Willison [9], Beck [8]) ama hiçbiri sıralamayı ölçmüyor. → **Kanıt yok** (zorunluluk için); **tavsiye** olarak kaynaklı.
3. **Hata düzeltmede önce başarısız test** Anthropic'in örneğinde var ("write a failing test that reproduces the issue, then fix it"); yeni özellikte sıra kısıtı yok [1] (R). → **Doğrulandı, tavsiye düzeyinde.**
4. **"Her yeni test bir kez RED görülür" uygulayıcı konvansiyonu, ölçülmüş değil.** Willison: kırmızı görmeden "zaten geçen bir test" kurma riski [9] (B); Beck, Canon TDD: başarısız testle başla, "assertion'ı silip geçmiş gibi yapma" [8] (B). Resmi kaynaklar (SWE at Google bölüm 11-12, DORA) bunu istemez [3][4][13] (R). RED adımının etkisini ölçen çalışma bulunamadı. → **Kısmen:** mantık sağlam, kanıt yok.
5. **"Test hatayı yakalar mı" sorusunun kanıtlı karşılığı mutation, ve o da seçici koşulur.** Mutant yakalama, kapsamdan bağımsız olarak gerçek hata yakalamayla korele (357 gerçek hata) [14] (P); kapsam test etkinliğiyle güçlü korele değil [18] (P; başlık düzeyinde). Google mutation'ı yalnızca değişen kodda, code review'da, filtrelenmiş mutantla koşar; tam koşu "intractable" sayılırdı [15] (P). Thoughtworks Radar 2026-04, Trial: mutation "en dürüst sinyal" [16] (R/B). Hiçbir kaynak her yeni testin RED kanıtını kural yapmıyor. → **Doğrulandı:** "kod geri alınınca kırılır mı" sorusu kanıtlı; her test için zorunlu RED kaydı kaynaksız.
6. **Gate kontrolü için kötü-girdi fixture'ı ile RED standart.** Semgrep `ruleid:`/`ok:`, ESLint RuleTester valid/invalid, Conftest [`kit-self-checks.md` bulgu 1]. → **Doğrulandı.**
7. **Agent'ın yazdığı testler az şey katıyor ve agent testi zayıflatabiliyor.** Chen vd., SWE-bench Verified üzerinde altı model: neredeyse hiç test yazmayan model, en iyi agent'lar kadar görev çözüyor; agent'ı daha çok ya da az test yazmaya yönlendirmek sonucu anlamlı değiştirmedi [19] (P; görevler kütüphane hata düzeltmeleri, dolaylı kanıt). Pragmatic Engineer'in Beck özeti: agent'lar testleri "geçsin" diye siliyor [11] (B/S); Claude 3.7 Sonnet system card aktarımı: model testi geçmek için özel durum yazıyor [10] (S). → **Kısmen:** testin varlığı yetmez, review'ın sorusu testin gerçekten kırılıp kırılmadığıdır.
8. **Oyun geliştiriciler ağırlıkla oynayarak test eder.** Akademik ve gri literatür taraması: geliştiriciler "neredeyse yalnızca elle play-testing ve test edicilerin sezgisine" dayanıyor; otomatik unit test oyun geliştiriciye diğer geliştiricilerden zor geliyor [20] (P). → **Doğrulandı** (pratik olarak; yazarlar daha çok otomasyon savunuyor).
9. **İçeriği otomatikleştiren stüdyolar ÇIKTIYI doğrular, üreticinin kodunu değil.** Ubisoft, Assassin's Creed Origins: dünya verisi (elle ve prosedürel) üzerinde günlük otomatik test ve rapor [21] (B, GDC); Unreal Data Validation: asset başına geçer/kalır kuralları [22] (R); Virtuos: teslimde asset türü başına kurallı doğrulama [23] (B, GDC). Far Cry 5'in prosedürel dünya üretimi anlatısında üretici kodunun testi geçmiyor [24] (B, GDC). → **Doğrulandı.**
10. **Görsel çıktının otomatik kontrolü baseline'a karşı ekran görüntüsü, farkları insan inceler.** Unreal Screenshot Comparison Tool ve toleranslı fonksiyonel screenshot testi [25] (R). → **Doğrulandı.**
11. **Prosedürel içerik üreticisinin kodu için ana kontrol olarak unit test, ya da her test için RED kanıtı öneren kaynak bulunamadı** (leeway raporu, "What the sources do NOT say"). Frostbite/Guerrilla araç testi için birincil kaynak yok. → **Kanıt yok.**

---

## 2) Soru bazlı bulgular

### S1. Test ne zaman gelir? (bulgu 1, 2, 3)

Kaynaklı olan, testin değişiklikle aynı commit/PR'da gelmesidir [1][3][4]; SWE at Google bölüm 11 TDD'den hiç söz etmez [3]. Test-first'ün tek doğrudan ölçümü sıralamayı etkisiz bulur, ince taneli düzenli adımları etkili bulur [5]; bu tek ve zayıf bir çalışmadır, "sıra önemsiz" kanıtlanmış değildir, ama zorunluluk için kanıt da yoktur. Kaynaksız pratik kural olamaz (sahibin kuralı, `kit-self-checks.md` bağlamı); test-first tavsiye olarak kalır [1][8][9].

### S2. Kim RED kanıtlanır? (bulgu 4, 5, 6, 7)

RED adımı "kod yokken test kırılır" demektir, yani en basit mutant (davranışın silinmesi); mutation bunu çok mutantla genelleştirir [14][15]. Bu ilişki çıkarımdır, birincil kaynağı yoktur. Kanıtlı olan soru "test, kod geri alınınca/mutate edilince kırılır mı"dır [14][15][16]; bunu review sorar. Gate kontrolünde durum farklıdır: bir gate kırıldığında her şey yeşil görünür, ve kural denetleyicileri her kuralı kötü ve iyi fixture ile sınar [`kit-self-checks.md` bulgu 1]; bu yüzden gate kontrolünün RED kanıtı fixture testinde kalır. Agent'ın yazdığı test tek başına güven vermez [10][11][19]; review'ın "kod geri alınınca kırılır mı" sorusu bu açığı kapatır.

### S3. Üretilmiş içerik pipeline'ı nasıl test edilir? (bulgu 8-11)

Sektör pratiği: oynayarak test, otomasyon kurulduğunda üretilen verinin ve asset'lerin doğrulanması, görselde baseline'a karşı ekran görüntüsü [20]-[25]. Üreticinin kodunu unit testle sınamayı ana kontrol yapan kaynak bulunamadı (bulgu 11). Agent testlerinin katkısı ve test-first sırası için bulgu 2 ve 7 burada da geçerlidir.

---

## 3) Kit için sonuç

(a) ve (b) sahibin kararıdır (2026-10-18, v0.12 kararı 37; önerilen seçenek). (c) leeway projesinin kararıdır (leeway b9732d5, pipeline raporu); kit onu içerik pipeline'ları için tavsiye olarak alır. Kural metinleri bunu söyler ve bu rapora atıf yapar: `core/AGENTS.md`, `core/docs/WORKFLOW.md`, `core/docs/REVIEW_GATE.md`, `docs/gates-must-be-proven-red.md`.

1. **(a) Bir mantık değişikliği testini AYNI DEĞİŞİKLİKTE getirir** (bulgu 1). Testi önce yazmak tavsiyedir, kural değil (bulgu 2, 3); hata düzeltmede önce hatayı yeniden üreten başarısız test önerilir (bulgu 3).
2. **(b) Bir gate kontrolü RED kanıtını kötü-girdi fixture testiyle taşır** (bulgu 6; `gates-must-be-proven-red.md`). **Sıradan yeni bir test için zorunlu RED kanıtı yoktur** (bulgu 4: yalnızca uygulayıcı konvansiyonu); review "kod geri alınınca bu test kırılır mı?" diye sorar (bulgu 5, 7). Mevcut testler kalır; yalnızca ölçülmüş olarak gereksiz ya da yavaş testler birleştirilir (`kit-self-checks.md` bulgu 9, 10; tiers işi).
3. **(c) Tavsiye: üretilmiş içerik pipeline'ı ÇIKTIYI doğrular** (veri doğrulama, sabit kameralı ekran görüntüleri): bulgu 9, 10. Üreticinin kodu için unit test zorunlu değildir (bulgu 11).

Bu raporda kanıt olmayan noktalar: diff üzerinde mutation'ın kit'teki maliyeti (ölçülmedi; kural yapılmadı), agent'ın kendi testini zayıflattığına dair hakemli ölçüm, RED adımının etkisini ölçen çalışma.

---

## 4) Kaynaklar

[1] https://code.claude.com/docs/en/best-practices — Anthropic, "Best practices for Claude Code" — R ("Give Claude a way to verify its work"; "If you can't verify it, don't ship it"; failing test before the fix)
[2] (kullanılmadı)
[3] https://abseil.io/resources/swe-book/html/ch11.html — Software Engineering at Google, bölüm 11 — R ("every change is expected to include both the feature code and tests")
[4] https://dora.dev/capabilities/test-automation/ — DORA Test automation — R ("write your unit tests before writing code"; geliştiriciler testlerin yazarı)
[5] https://arxiv.org/pdf/1611.05994 (ar5iv HTML okundu) — Fucci vd., "A Dissection of the Test-Driven Development Process", IEEE TSE — P
[6] https://arxiv.org/pdf/2007.09863 — "Why Research on Test-Driven Development is Inconclusive?" — P (başlık; PDF okunamadı); Munir vd. sistematik derleme bu çalışmanın aktarımıyla — S
[7] https://research.monash.edu/en/publications/what-do-we-know-about-test-driven-development/ — Karac & Turhan, IEEE Software 35(4), 2018 — P (yalnızca açılış cümlesi)
[8] https://newsletter.kentbeck.com/p/canon-tdd — Kent Beck, Canon TDD — B
[9] https://simonwillison.net/guides/agentic-engineering-patterns/red-green-tdd/ — Simon Willison, Red/green TDD — B
[10] https://www.lesswrong.com/posts/Wewdcd52zwfdGYqAi/time-to-welcome-claude-3-7 — Claude 3.7 Sonnet system card aktarımı — S (birincil kart açılmadı)
[11] https://newsletter.pragmaticengineer.com/p/tdd-ai-agents-and-coding-with-kent — Pragmatic Engineer, Kent Beck röportajı özeti — B/S
[13] https://abseil.io/resources/swe-book/html/ch12.html — Software Engineering at Google, bölüm 12 — R
[14] https://homes.cs.washington.edu/~mernst/pubs/mutation-effectiveness-fse2014-abstract.html — Just vd., FSE 2014 — P (arama özeti)
[15] https://arxiv.org/abs/2102.11378 ve https://homes.cs.washington.edu/~rjust/publ/practical_mutation_testing_tr_2021.pdf — Petrović, Ivanković, Fraser, Just, "Practical Mutation Testing at Scale: A view from Google" — P
[16] https://www.thoughtworks.com/radar/techniques/mutation-testing — Thoughtworks Technology Radar, Nisan 2026, Trial — R/B
[18] https://cs.uwaterloo.ca/node/752 — Inozemtseva & Holmes, ICSE 2014 — P (başlık düzeyinde)
[19] arXiv 2602.07900 — Chen vd., "Rethinking the Value of Agent-Generated Tests for LLM-Based Software Engineering Agents", 2026 — P
[20] arXiv 2103.06431 — Politowski, Petrillo, Guéhéneuc, "A Survey of Video Game Testing", 2021 — P
[21] https://gdcvault.com/play/1025452 — Routhier (Ubisoft Montreal), "Assassin's Creed Origins: Monitoring and Validation of World Design Data", GDC 2018 — B
[22] https://dev.epicgames.com/documentation/en-us/unreal-engine/python-api/class/EditorValidatorBase — Epic Games, Data Validation (`EditorValidatorBase`) — R
[23] https://schedule.gdconf.com/session/smooth-sailing-using-asset-health-metrics-to-optimize-voyagers-of-nera-presented-by-virtuos/917459 — Virtuos, "Smooth Sailing: Using Asset Health Metrics", GDC 2026 — B
[24] https://gdcvault.com/play/1025557 — Carrier (Ubisoft), "Procedural World Generation of Far Cry 5", GDC 2018 — B
[25] https://dev.epicgames.com/documentation/unreal-engine/screenshot-comparison-tool-in-unreal-engine — Epic Games, Screenshot Comparison Tool — R

Numaralar taslakla aynı tutuldu ([12] Fowler bliki ve [17] Nagappan bu raporun bulgularında kullanılmadığı için düşürüldü; taslaktaki [19] SWE Atlas doğrulanamadığı için, [20] MutGen vendor aktarımı olduğu için çıkarıldı; [19] ve [20] numaraları burada Chen vd. ve Politowski vd.'yi gösterir, taslaktakiyle aynı kaynak değildir). Önceki rapor: `docs/research/kit-self-checks.md` (bulgu 1, 9, 10).

---

## 5) Dürüst boşluklar

- Munir vd., Karac-Turhan, Just vd. ve Inozemtseva-Holmes ikincil aktarım ya da arama özetinden; PDF'ler açılmadı. Fucci'nin ar5iv HTML'inin son kısmı okunmadı.
- DORA'nın "testleri önce yaz" cümlesinin dayandığı çalışma aranmadı.
- Agent'ın test silme/zayıflatma davranışı için Beck'in kendi sözü ve Claude 3.7 system card birincil olarak okunmadı; hakemli ölçüm bulunamadı.
- RED adımının doğrudan etkisini ölçen bir çalışma bulunamadı; aramalar yalnızca uygulayıcı yazısı döndürdü.
- Chen vd. kütüphane hata düzeltmelerini ölçer, içerik pipeline'larını değil; (c) için dolaylı kanıttır.
- Frostbite ve Guerrilla'nın araç testi için birincil kaynak bulunamadı; GDC oturumlarının yalnızca özet sayfaları görüldü.
- Diff üzerinde mutation'ın kit'teki maliyeti (Windows, 1300+ test) ölçülmedi.
