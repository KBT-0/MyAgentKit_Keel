# Lead oturumu ne zaman kesilmeli? Bağlam boyutu, kalite ve maliyet: kanıta dayalı araştırma raporu

Tarih: 2026-10-14. Soru (sahip): Uzun süren, orkestra eden bir Claude Code lead oturumu (Claude Opus 5.5, Fable 5.1, Sonnet 5.5) kaç token bağlamda durup yeni oturuma devretmeli ya da `/compact` çalıştırmalı? Amaç denge: yalnız para değil, daha sağlıklı ve kaliteli iş (talimata uyum, az hata, kuralları unutmama).

> **Kitteki karar (sahip, 2026-10-14):** bant kabul edildi (200k sarı, 300k kırmızı, 400k tavan, belirti tetikleyicisi), `autoCompactWindow` 450k emniyet supabı, sıkıştırma sonrası hatırlatma hook'u; dogfood = leeway ve labricore-web'in v0.11 ile ilk 1,5 haftası. Öneri 5(a)(b) bu sürümde uygulanmadı. Not: "~300–400k" sayısı Anthropic'e ait değil (bkz. Bulgu 4 doğrulaması).

Kitteki mevcut kural: `core/docs/WORKFLOW.md`, "Worker cost", 8. kural. Çizgi 200k token. Gerekçesi yalnız maliyet. Hook: `overlays/claude-code/files/.claude/hooks/context_size.py`, 200k'da ve sonraki her 50k'da uyarır. Kalite (bağlam çürümesi) hiç hesaba katılmamış.

Etiketler bu görevin tanımına göredir: **R** araştırma/makale/benchmark, **P** vendor birincil doküman, **B** blog/pratisyen yazısı, **F** forum/issue/sosyal, **S** ikincil/başka. Dikkat: `docs/research-ai-review-workflows.md` aynı harfleri başka anlamda kullanıyor (orada R = resmi doküman, P = makale). Bu rapor görevdeki anlamı kullanır. Kaynak numaraları `[n]`, liste bölüm 7'de. Kanıt dili: **ölçüm** (sayı üreten deney), **vendor beyanı** (üreticinin kendi sözü), **anekdot** (kişi deneyimi), **çıkarım** (bu raporun kendi hesabı ya da yargısı). Dört sınıf bilerek ayrı tutuldu.

Terimler: **bağlam çürümesi** (context rot): bağlam büyüdükçe modelin doğruluğunun ve hatırlamasının düşmesi. **Sıkıştırma** (compaction): eski konuşmayı özetleyip yerine koymak. **Cache**: her istekte yeniden gönderilen bağlamın ucuz fiyatla okunması. **Hand-off**: temiz oturum açıp durumu dosyadan okutmak.

---

## 1) Kısa özet

1. **Uzunluk kaliteyi düşürür; bu ölçülmüş ve evrensel bir yön.** Chroma (18 model), NoLiMa, RULER, Lost in the Middle ve "uzunluk tek başına zarar verir" çalışması aynı yöne bakıyor [1][2][3][4][7]. Ama ölçülen modeller 2023–2025 modelleri (Claude için en yeni satır Claude 3.5/3.7 Sonnet). **Opus 5.5, Fable 5.1 ve Sonnet 5.5 için yayımlanmış bir uzun-bağlam sayısı bulamadım.**
2. **Hiçbir yerde "şu token'da kural unutma başlar" diye ölçülmüş bir sayı yok.** En yakın şeyler: çok turlu konuşmada ortalama %39 düşüş (güvenilirlik çöküyor) [6], Anthropic'in "erken talimatları unutabilir" cümlesi (sayısız) [14], bir GitHub issue'sundaki öznel tablo [39].
3. **Anthropic sayı vermiyor.** "~300–400k civarında biraz bağlam çürümesi" sayısı Claude Code ekibinin yazısında [29] yok (2026-10-14 doğrulandı); kaynağı Mejba'nın kendi Opus 4.7 denemesi [33] ve bir kopya sitedeki atıf [43]. Aynı yazıya göre sıkıştırma "kayıplı" ve model **sıkıştırırken en az zeki olduğu noktadadır** [29].
4. **Claude Code'un varsayılanı bu üç modelde ~967k'da sıkıştırmak** [17]. Yani varsayılan bir kalite eşiği değil, pencere sınırı. Kitin 200k çizgisi olmasa lead 967k'ya kadar giderdi.
5. **Maliyet hesabı güncel fiyatlarda kitin yazdığından farklı.** Cache okuma Opus 5.5 ve Sonnet 5.5'te girdi fiyatının 0,05 katı, Fable 5.1'de 0,025 katı [20]. 200k'dan taze oturuma geçişin kendini ödemesi "10 turdan az" değil: Opus/Sonnet'te yaklaşık 25 istek, Fable'da yaklaşık 49 istek (çıkarım, bölüm 3). "10 turdan az" yalnız ~400k'da tutuyor.
6. **Pratisyen eşikleri 120k ile 400k arasına dağılıyor ve hiçbiri ölçüm değil** [33][34][35][39].
7. **Öneri: tek çizgi yerine bant.** 200k "kesmeyi planla", 300k "bir sonraki temiz durakta kes", 400k "tavan". Üç model için aynı bant. Boyuttan bağımsız belirti tetikleyicisi de eklensin (aynı kural iki kez düzeltildi, `guard_worker_route` reddi). Bant kanıtla değil yargıyla seçildi; kanıtın en iyi söylediği şey "200k'dan önce acil bir uçurum yok, 300–400k'dan sonra pratisyenler risk görüyor". Dogfood günü bu üç sayıyı doğrulamak ya da kaydırmak için ölçüm yapacak (bölüm 5, öneri 7).

En büyük belirsizlik: elimizdeki sayıların hiçbiri bu üç modelin agent oturumundaki kural uyumunu ölçmüyor.

---

## 2) Bulgular

Her bulgu "Kanıt gücü" taşır: **Güçlü** (birden çok bağımsız ölçüm ya da resmi doküman, güncel), **Orta**, **Zayıf**, **Yok**.

### Bulgu 1. Bağlam uzadıkça doğruluk düşer; yön kesin, büyüklük modele ve göreve bağlı

Kanıt gücü: yön **Güçlü** (R, çok kaynak), güncellik **Zayıf** (eski modeller).

- **Chroma, Temmuz 2025 (R) [1].** 18 model (Claude Opus 4, Sonnet 4, Sonnet 3.7/3.5, Haiku 3.5; GPT-4.1, o3; Gemini 2.5; Qwen3). Basit görevlerde bile uzunlukla güvenilirlik düşüyor. Dağıtıcı (distractor) cümleler düşüşü hızlandırıyor. LongMemEval'de ~300 tokenlık odaklı istem ile ~113k tokenlık tam istem karşılaştırıldı: tüm modeller odaklıda belirgin iyi; Claude modellerinde fark en büyük, çünkü belirsizlikte "bulamadım" deyip çekiliyorlar (en düşük halüsinasyon oranı). Yani Claude'da çürüme "yanlış cevap" değil "çekilme" olarak görünebiliyor. Raporda sayılar grafiklerde; metinde tam rakam yok.
- **NoLiMa, ICML 2025 (R) [2].** Kelime eşleşmesi olmayan iğne-saman testi. 13 model, tek Claude satırı Claude 3.5 Sonnet: iddia edilen 200k, "etkili uzunluk" 4k; taban skor 87,5, 4k'da 77,6, 8k'da 61,7, 16k'da 45,7, 32k'da 29,8 (tabanın %34'ü). GPT-4.1: 32k'da tabanın ~%82'si, 128k'da 64,7. Makaleye göre tüm modeller 32k'da %50'nin altına düşüyor (GPT-4.1 hariç). Not: bu 2024-25 modelleri; tokenizer da farklı.
- **RULER (R) [3].** Sentetik, görev karmaşıklığı artırılmış testler: 32k+ iddia eden 10 modelden yalnız 4'ü 32k'da tatmin edici. (Yalnız arama özeti okundu, makale gövdesi okunmadı.)
- **Du ve ark., Ekim 2025 (R) [7].** Beş model (Claude 3.5/3.7 etiketi tutarsız). Doğru kanıtı mükemmel bulsalar bile girdi uzunluğu tek başına doğruluğu %13,9–85 düşürüyor; gereksiz tokenlar boşlukla değiştirilse ve hatta dikkat maskesiyle gizlense bile düşüş sürüyor. Kapalı modellerde (GPT-4o, Claude, Gemini) 30k'da düşüş açık modellerden küçük. Yani "yalnız hatırlama sorunu değil, uzunluğun kendisi".
- **Lost in the Middle (R) [4].** Bilgi bağlamın ortasındaysa başında/sonundaki duruma göre belirgin kötü (U şekli). (Özet düzeyinde okundu.)
- **LongBench v2 (R) [5].** 8k–2M kelime bağlamlı 503 soru; insan uzmanlar 15 dakikada %53,7, doğrudan cevap veren en iyi model %50,1, uzun düşünen o1-preview %57,7. Yani 2024 sonunda gerçek uzun-bağlam akıl yürütme insan seviyesinin altındaydı; sonra modeller ilerledi ama güncel skor alamadım.

Sınır: bu çalışmaların çoğu arama/çıkarma görevi ölçüyor. Kuralları tutma ya da uzun bir kodlama oturumunda tutarlılık ölçmüyorlar (Bulgu 3). Bu yüzden "kalite düşer" ile "lead kural unutur" arasında bir atlama var ve bu atlamayı yapan bizim yargımız.

### Bulgu 2. Güncel üç model için yayımlanmış uzun-bağlam sayısı yok; en yakın sayılar eski modelden ve nitel

Kanıt gücü: **Yok** (hedef modeller için), **Zayıf** (komşu modeller için).

- **P [27]:** Opus 4.6 duyurusu MRCR v2 (8 iğneli, 1M) için "Opus 4.6 %76, Sonnet 4.5 %18,5" diyor ve "yüzbinlerce tokenda daha az sapma" iddia ediyor. Sayı vendor beyanı. Aynı sayfada 1M'in o zaman beta olduğu ve 200k üstüne ek fiyat uygulandığı yazıyor ($10/$37,50) — bu fiyat sonradan kalktı (bkz. Bulgu 6).
- **P [28][23][24][25]:** Opus 5.5 duyurusu ve üç modelin "what's new" sayfaları uzun-bağlam skoru vermiyor. Fable 5.1 sayfası yalnız nitel: "1M pencerenin tamamında ayrıntıları bağlama ve akıl yürütmede iyileşme" [24]. Opus 5.5 için "18 saat boyunca görevde kaldı" gibi müşteri alıntıları var, bağlam boyutu belli değil [28].
- **S [45][46][47]:** Toplayıcı siteler Opus 4.7 için MRCR v2 128k–256k %59,2 (GPT-5.5 %87,5), Opus 4.8 için 8 iğneli 256k %83,2 gösteriyor; son kaynağın dört satırı aynı Qwen model kartına bağlı, güvenilirliği şüpheli. Hiçbirinde Opus 5.5, Fable 5.1 ya da Sonnet 5.5 yok.
- **F [39]:** Bir GitHub issue'su Opus 4.6 için "256k'da %93, 1M'de %76–78" diyor ve bunu Anthropic'e atfediyor, ama tabloyu üçüncü taraf sitelere dayandırıyor. İkincil.
- Fiction.LiveBench ve OpenAI-MRCR: Opus 5 satırı olduğunu gördüm ama uzunluk bazlı değer çıkaramadım (arama özetinde yalnız 16k skoru kullanıldığı yazıyor). Kullanılabilir sayı yok.

Okuma: bir sonraki nesil retrieval'da belirgin daha iyi (Sonnet 4.5 → Opus 4.6 sıçraması), ama (a) 1M'de 256k'dan hâlâ aşağıda olduğu söyleniyor (anekdot düzeyinde), (b) bu skorlar kural uyumunu ölçmüyor.

### Bulgu 3. Talimata uyum ve "kuralları unutma": ölçülen yalnız dolaylı; yön tutarlı

Kanıt gücü: yön **Orta** (R + P), büyüklük **Zayıf/Yok**.

- **Çok turlu kayıp, Laban ve ark. 2025 (R) [6].** 15 model (Claude 3.7 Sonnet dahil), 200.000+ simüle konuşma: tek seferde verilen görev parçalı verildiğinde ortalama %39 düşüş. Ayrıştırma: yetenek yalnız ~%16 düşüyor, güvenilirsizlik ~%112 artıyor. Model erken varsayım yapıyor, sonra ona aşırı yaslanıyor; "yanlış dönemece girdi mi toparlayamıyor". Claude 3.7 Sonnet yaklaşık %34 (okunması zor tablo, yaklaşık). Çare olarak yazarlar "yeni konuşma aç ve ana bilgiyi bir araya getirip yapıştır" diyor; özet/yineleme (recap) kısmen yardım ediyor, açığı kapatmıyor. Bu bağlam uzunluğu değil tur sayısı etkisi; ama uzun lead oturumu tam olarak çok turlu.
- **Talimat sapması, Li ve ark. 2024 (R) [9].** LLaMA2-chat-70B ve GPT-3.5 ile iki sohbet botu birbiriyle konuşturuldu: sistem isteminden sapma 8 turda belirgin; dikkat azalması nedeni olarak gösteriliyor. Eski modeller. (Özet düzeyinde okundu.)
- **IFScale (R) [8].** 500 talimata kadar yoğunluk: en iyi modeller bile 500'de %68; Claude Sonnet 4 "doğrusal düşüş" kalıbı, erken talimatlara önyargı. Bu talimat sayısı, uzunluk değil; yine de "çok kural + uzun oturum" birleşiminin kitin durumu olduğunu gösteriyor. (Özet düzeyinde okundu.)
- **Anthropic (P) [14].** "Bağlam penceresi dolarken Claude önceki talimatları 'unutmaya' ya da daha çok hata yapmaya başlayabilir." Sayı yok. Ayrıca "iki kez düzelttin ve hâlâ yanlışsa bağlam başarısız denemelerle kirlenmiştir: `/clear` yap ve daha iyi bir istemle başla" [14].
- **F [39].** Bir kullanıcı issue'sunda öznel tablo: bağlamın %0–20'si güvenilir, %20–40 bozulma, %40–60 "kendinden emin yanlış sonuçlar", %60–80 "%20'de okunan olgulara erişim yok". Ölçüm yöntemi yok, kendisi de "tahmin" diyor.

Sonuç: "çok turlu + uzun" oturumun güvenilirliği düşürdüğüne dair iyi kanıt var (eski modellerde); güncel modellerde ne kadar azaldığı ölçülmemiş.

### Bulgu 4. Anthropic eşik vermiyor ("~300–400k" atfı doğrulanamadı); varsayılan sıkıştırma çok geç

Kanıt gücü: **Orta** (P, ama tek sayı ikinci elden ve model nesli eski).

- **P [12][14][11]:** "Doğruluk ve hatırlama token sayısıyla düşer (bağlam çürümesi)", "daha fazla bağlam otomatik olarak daha iyi değil", "bağlam penceresi en önemli kaynak". Bağlam mühendisliği yazısı "dikkat bütçesi" benzetmesini kullanır, ama sıkıştırma için token eşiği vermez [11].
- **P/S [29][43]:** Claude Code ekibinden Thariq'in 2026-04-15 yazısı: "bağlam çürümesi ~300–400k token civarında bir miktar oluyor; bu göreve çok bağlı, hızlı bir kural değil". claude.com sayfasını çektiğimde bu cümleyi göremedim; sayıyı aynı yazının X makalesi olarak yayımlanmış bir kopyasında (YouMind) gördüm. Yani sayı ya sayfanın başka bir sürümünde ya da yalnız X metninde; birinci elden doğrulayamadım. O tarihte 1M'li modeller Opus 4.6/4.7 idi. **Doğrulama (2026-10-14):** sayfa yeniden çekildi, sayı yok; web aramasında sayı yalnız Mejba'nın blogunda [33], yazarın kendi Opus 4.7 denemesi olarak geçiyor. Bu rapor sayıyı Anthropic'e atfetmez.
- **P [29]:** "Kötü sıkıştırma, model işinin gideceği yönü tahmin edemediğinde olur"; "model sıkıştırırken en az zeki olduğu noktadadır"; öneri: "1M bağlamla `/compact`'ı önceden, ne yapacağını anlatarak çalıştırmak için daha çok vaktin var" ve yeni görev = yeni oturum.
- **P [17]:** Otomatik sıkıştırma varsayılanı: 1M-yerel modellerde (Fable, Sonnet 5+, Opus 4.7+) ~967k; `CLAUDE_CODE_DISABLE_1M_CONTEXT=1` ile 200k; pencere `autoCompactWindow`, `--autocompact` ya da `CLAUDE_CODE_AUTO_COMPACT_WINDOW` ile 100k–1M arası ayarlanır.
- **F [40]:** Bir issue Opus'ta sıkıştırmanın ~420k'da tetiklendiğini bildirdi (varsayılan o sürümde farklıydı); bot "not planned" kapattı. Varsayılanların sürümler arasında kaydığını gösteriyor: bugünkü 967k'ya güvenmek kırılgan.

### Bulgu 5. Pratisyen eşikleri 120k–400k arasında; hiçbiri ölçüm değil

Kanıt gücü: **Zayıf** (anekdot).

| Kaynak | Eşik | Dayanak | Etiket |
|---|---|---|---|
| Matt Pocock, dotzlaw yazısında aktarılmış [34] | ~120k "aptal bölge" hissi | öznel; yazar da "ölçüm değil" diyor | B |
| Sikkema [35] | pencereyi 200k'ya düşürmüş, %70'te (~140k) otomatik sıkıştırma | alıntılanan makaleler + tek olay (sıkıştırmadan sonra sormadan commit) | B |
| GitHub issue #35296 [39] | "güvenilir aralık ~200–256k" | öznel tablo; Anthropic yanıtlamadı, "not planned" | F |
| Mejba [33] | 300–400k ilk kontrol noktası, elle sıkıştır | "aylar süren uzun oturumlar", tek olay | B |
| Horthy "dumb zone" [44] | ~%40 | ikincil aktarım; 200k çağında formüle edilmiş, 1M'e doğrudan taşınamaz | S |
| Cursor saha mühendisi sözü [37] | %50–60'tan sonra hafif düşüş | ikincil aktarım | S |
| Aider (Gauthier) sözü [35] | ~25–30k'dan sonra karışıyor | birincil kaynak bulunamadı; yalnız bir blog aktarıyor | B |

Yakınsama yok. Kalite öncelikli ve temkinli olanlar 120–256k, Mejba 300–400k diyor (aynı sayının Anthropic atfı doğrulanamadı). Kitin 200k'sı bu aralığın alt-ortasında. (Yargı.)

### Bulgu 6. Maliyet mekaniği (resmi fiyatlar) kitin varsaydığından farklı

Kanıt gücü: **Güçlü** (P, güncel). Hesap kısmı çıkarım.

- **Cache okuma çarpanı model başına değişiyor [20][21]:** Opus 5.5 ve Sonnet 5.5: girdi fiyatının **0,05**'i ($0,20 ve $0,10 / MTok); Fable 5.1: **0,025**'i ($0,25 / MTok); diğer modeller 0,1. Yazma: 5 dk cache 1,25x, 1 saat cache 2x. Fiyatlar (girdi / 1 saat yazma / okuma / çıktı, $/MTok): Opus 5.5 4 / 8 / 0,20 / 20; Fable 5.1 10 / 20 / 0,25 / 50; Sonnet 5.5 2 / 4 / 0,10 / 10.
- **1M uzun-bağlam ek ücreti yok [20][12]:** Claude 4.6 ve sonrası (Haiku 5.5 hariç) 1M pencereyi standart fiyatla veriyor; 900k'lık istek 9k'lık istekle aynı token fiyatı. (Opus 4.6'nın ilk duyurusunda 200k üstü $10/$37,50'ydi [27]; kalktı.) Yani 200k üstüne maliyet basamağı yok; OpenAI'de tersine 272k üstü girdi 2x (tek kaynaktan, B [36]).
- **TTL [18][19][21]:** Cache her okumada tazelenir, 5 dakika boşta kalırsa düşer. Claude Code ana konuşma için abonelikte 1 saat, API anahtarı/kredi/bulutta 5 dakika (`promptCacheTtl=1h` ile değişir). Alt-ajanlar ve sıkıştırma isteği "her şey diğer" kovasında: 5 dakika. Mola sonrası soğuk cache'de `/compact` tüm geçmişi tam fiyat okur [18].
- **Sıkıştırma maliyeti [18]:** Cache sıcakken sıkıştırma isteği ön eki cache'ten okur; asıl maliyet özet çıktısı; sonra yeni kısa bağlamın cache yazımı.
- **Tokenizer [20]:** Claude 4.7 ve sonrası aynı metin için ~%30 daha çok token üretiyor. Eski makalelerdeki token eşikleri bugünkü sayılarla birebir kıyaslanamaz: bugünkü 200k, eski tokenizer'da yaklaşık 150k'ya denk (çıkarım).
- **Büyüme:** Bu modellerde önceki düşünce blokları varsayılan olarak bağlamda tutuluyor [12]; bağlam her istekte bir miktar daha hızlı büyüyor (kitin "istek başı ~2k" ölçümüyle uyumlu).

### Bulgu 7. Sıkıştırma kayıplı; hand-off ile kıyas: Anthropic bazı durumlarda taze pencereyi öneriyor

Kanıt gücü: **Orta**.

- **P [29][22]:** Sıkıştırma "kayıplı"; Anthropic'in istem rehberi: bağlam temizlendiğinde "sıkıştırma yerine yepyeni bir bağlam penceresiyle başlamayı düşün; modeller durumu yerel dosya sisteminden keşfetmekte çok iyi" ve devralan oturuma `pwd`, `progress.txt`, `tests.json`, `git log` okutmayı öneriyor [22].
- **P [16] Sıkıştırmadan ne sağ çıkar:** sistem istemi, çıktı stili, **proje kökündeki CLAUDE.md ve kapsamsız kurallar (diskten yeniden eklenir)**, otomatik hafıza, plan modu planı; en son değişen **en çok 5 dosya** yeniden okunur (5.000 tokenı aşanlar yalnız yol olarak); çağrılan skill gövdeleri skill başına 5.000, toplam 25.000 token ile kırpılarak. **Yol-kapsamlı kurallar, iç içe CLAUDE.md'ler ve hook'ların eklediği bağlam özetlenip kaybolur.** Arka plan komutları ve arka plan alt-ajanlar çalışmaya devam eder.
- **P [15]:** "Otomatik sıkıştırmada oturumun başındaki ayrıntılı talimatlar kaybolabilir; kalıcı kuralları CLAUDE.md'ye koy."
- **F [41] ve eş issue'lar:** 2025'te çok sayıda kullanıcı `/compact` sonrası CLAUDE.md'nin yok sayıldığını bildirdi (#4017, #4517, #11545, #24460 …). Güncel doküman kök CLAUDE.md'nin yeniden eklendiğini söylüyor [16]; düzeltildiğini ben doğrulamadım.
- **B (vendor-run) [32]:** Factory'nin 36.611 mesajlık üretim oturumlarında, GPT-5.2 yargıçlı karşılaştırması (0–5): yapılandırılmış özet 3,70; Anthropic'in SDK sıkıştırması 3,44; OpenAI `/responses/compact` 3,35. Boyutlarda: doğruluk 4,04/3,74/3,43; **artifact izi (hangi dosya değişti) 2,45/2,33/2,19, hepsinde en zayıf**; **talimata uyum 4,99/4,95/4,92 (hepsinde yüksek)**; sıkıştırma oranı %98,6–99,3. Anthropic yöntemi her sıkıştırmada özeti baştan üretiyor; tekrarlı sıkıştırmada ayrıntı kayabilir (tek örnek: `/api/auth/login` yolu kayboldu). Ölçümü ürünü satan firma yaptı, varyans verilmemiş. Çıkarım: açık talimatlar sıkıştırmadan iyi geçiyor, **durum bilgisi (dosya yolları, ne değişti) en çok kaybolan şey**.
- **R [10] JetBrains, NeurIPS 2025 workshop:** SWE-agent'ta, SWE-bench Verified (500 görev), beş model kurulumu: sade "gözlem maskeleme" (eski araç çıktılarını yer tutucuyla değiştirme) LLM özetlemesiyle aynı etkililikte, beş kurulumdan dördünde daha ucuz, bağlam yönetimsiz duruma göre maliyeti %50'den fazla düşürüyor; özetleme ajanı %13–15 daha uzun koşturuyor; özet çağrıları maliyetin %7'sini aşabiliyor; hibrit %7–11 daha ucuz. Yani **eski araç çıktılarını atmak çoğu zaman özetlemekten iyi ya da eşit**.
- **P [11]:** "Araç sonucu temizleme" sıkıştırmanın en hafif biçimi; alt-ajan 1.000–2.000 tokenlık özet döner.

### Bulgu 8. Alt-ajanlar lead bağlamını korumanın resmi yolu

Kanıt gücü: yön **Güçlü** (P), kazanç büyüklüğü **Yok** (Anthropic sayı vermiyor).

Anthropic: "bağlam senin temel kısıtın; araştırmayı alt-ajanlara ver, ana konuşma temiz kalsın" [14]; alt-ajanın araç çağrıları lead bağlamına girmiyor, lead özet alıyor [15]. Kit zaten bunu yapıyor (WORKFLOW "Worker cost", 7. ve 8. kural). Ek: alt-ajan çıktısının kendisi de bağlama girer; kitin "rapor ~350 kelime" kuralı bunu yönetiyor.

### Bulgu 9. Diğer araçların varsayılanları pencereye oransal; kalite temelli değil

Kanıt gücü: **Zayıf** (çoğu arama özeti düzeyinde).

- **Codex [30][36]:** `model_auto_compact_token_limit` ayarlanmamışsa model varsayılanı; örnek değer 64.000; bir üçüncü taraf varsayılanı pencerenin ~%85–90'ı olarak aktarıyor (doğrulanmadı); kullanıcı yüksek değer girerse pencerenin %90'ında kısılıyor. Codex'in 1M örneği 900k; 272k üstü istek API'de girdi 2x [36].
- **Cline [31]:** otomatik sıkıştırma ~%80'de (P, arama özeti).
- **Cursor [37][42]:** resmi eşik bulunamadı; kullanıcılar birkaç tur sonra yeni pencere gerektiğini anlatıyor (F).
- **Windsurf, Aider:** kullanılabilir resmi eşik bulamadım.

### Bulgu 10. Kit için pratik sonuçlar (Bulgu 4, 6, 7'den)

- Kitin lead'i kuralları çoğu zaman oturum içinde `docs/WORKFLOW.md` gibi dosyalardan **okuyor** (AGENTS.md "Read only when needed … WORKFLOW 'Worker cost'"). Bu okumalar bağlam geçmişine giriyor; sıkıştırmada yalnız son 5 dosya ve ≤5k token yeniden okunuyor, gerisi özetleniyor [16]. Kök AGENTS.md (CLAUDE.md olarak yükleniyorsa) diskten geri geliyor. Yani **lead'in bağlayıcı kuralları ya kök dosyada ya da compact sonrası çalışan bir SessionStart hook'unda olmalı** (hook'lar `compact` kaynağına eşleştirilebiliyor [16]).
- Sıkıştırma arka plan işlerini öldürmüyor [16]; kitin kuralı "oturum sonu arka plan işleri öldürür" [WORKFLOW 8. kural] hand-off/`/clear` için geçerli. Uçuştaki iş varken `/compact` daha güvenli (çıkarım, kit kuralı + [16]).

---

## 3) Kendi sayılarımız (52k–449k, 248 istek)

Kitin kendi ölçümü (WORKFLOW 8. kural metni): bir lead 248 istek boyunca 52k–449k bağlamda, istek başına ortalama ~250k yeniden okudu; taze oturum (~60k, cache yazımı girdi fiyatının en çok 2 katı) 200k'dan "10 turdan az"da kendini ödüyor.

Ne söylüyor, ne söylemiyor:

1. **Ölçüm bağlamın büyüdüğünü ve çoğu isteğin 200k'nın üstünde geçtiğini gösteriyor.** Doğru ve işe yarar.
2. **Kalite hakkında hiçbir şey söylemiyor.** O oturumda kural ihlali ya da düzeltme sayısı işaretlenmemiş.
3. **Ödeme süresi güncel fiyatlarla yeniden hesaplandı (çıkarım).** Varsayımlar: sıfırlama sonrası bağlam 70k (60k taze + özet); özet çıktısı 4k token; 1 saat cache yazımı; yalnız cache okuma farkı sayıldı (çıktı ve cache'siz girdi aynı kabul edildi; her istekte bağlamın ~2k büyümesi sıfırlamayı biraz lehine çevirir, hesaba katılmadı).

| Model | Sıfırlama maliyeti | Tasarruf/istek 200k'dan | Ödeme: 200k | 300k | 400k |
|---|---|---|---|---|---|
| Opus 5.5 | ~$0,64 | ~$0,026 | ~25 istek | ~14 | ~10 |
| Sonnet 5.5 | ~$0,32 | ~$0,013 | ~25 | ~14 | ~10 |
| Fable 5.1 | ~$1,60 | ~$0,033 | ~49 | ~28 | ~19 |

Karşılaştırma: kitin cümlesi 0,1x okuma çarpanında (ör. Opus 5: okuma $0,50, yazma $10) kabaca 12 istek çıkarıyor, "on tur civarı" doğru. 0,05x ve 0,025x çarpanları ödeme süresini iki-dört katına çıkardı. Cümle artık yanlış.

4. **Ölçeği kavramak için:** 248 isteğin ~250k ortalamayla cache okuması bugün Opus 5.5'te ~$12,4, Fable 5.1'de ~$15,5, Sonnet 5.5'te ~$6,2 eder. Ortalama 120k tutulsaydı yaklaşık yarısı: ~$6, ~$7,4, ~$3. Kazanç oturum başına 3–8 dolar. Aynı kaynaktaki toplam: 11 saatte 336 dolar, %87'si worker'lar. Yani **lead'in bağlam maliyeti ana kaldıraç değil**; 200k çizgisini savunan şey para değil, kalite olmak zorunda (ya da hiç savunulmamalı).
5. **Çekince:** ölçümün hangi modelde ve hangi fiyatta alındığını kural metni söylemiyor. Abonelik planında sınırların cache okumaya nasıl ağırlık verdiği bilinmiyor (açık soru).

---

## 4) Çıkarım: bu kanıtlar ne ölçüde tek bir sayıyı destekliyor?

- **Alt sınır adayları:** 120k (öznel pratisyen), 140k–200k (pratisyen), 200–256k (issue). Maliyet alt sınırı: 200k civarı, ödeme ~25 istek (Opus/Sonnet).
- **Üst sınır adayları:** 300–400k (Mejba; Anthropic atfı doğrulanamadı); ödeme ≤14 istek. 967k (varsayılan) kalite temelli değil.
- Hiçbir kaynak 200k'da bir uçurum göstermiyor; hiçbir kaynak 400k'a kadar güvenli de demiyor. Anthropic'in "göreve bağlı, hızlı kural değil" uyarısı tek bir sayının neden yanıltıcı olacağını açıklıyor.
- **Sık kesmenin de kalite bedeli var:** her kesme, dosyaya yazılmamış her şeyi kaybettirir (Bulgu 7: durum bilgisi en çok kaybolan şey; Factory), soğuk başlangıç 60k okumadır. Bu yüzden "çok erken" kesmek de savunulamaz.
- Sonuç (yargı): tek çizgi yerine **bant**, ve bantın iki ucu Bulgu 4'teki Anthropic sayısı ile Bulgu 5'teki temkinli pratisyen sayılarının kesişiminden, ödeme hesabıyla sınanarak seçilir.

---

## 5) Kit için ÖNERİ

Her öneri bulgu numarası ve kaynakla bağlı. Kanıt boşluğunu yargıyla doldurduğu yerde bunu açıkça yazıyorum.

**Öneri 1. Tek çizgi yerine üç basamaklı bant; üç model için aynı.**

| Basamak | Bağlam | Anlamı | Hook davranışı |
|---|---|---|---|
| Sarı | 200k | Kesmeyi planla. Yeni tur başlatma, çalışan seti bitir, commit et, STATE ve hand-off notunu hazırla. | Bugünkü ilk uyarı (200k); metin: "kesme zamanı yaklaşıyor, sebep: bağlam çürümesi + maliyet". |
| Kırmızı | 300k | Bir sonraki temiz durakta kes; kararı sahip verir. Yeni tur yok. | Her 50k'da bugünkü sıklıkla, metin sertleşir. |
| Tavan | 400k | Temiz durak beklemeden dur: işi güvene al, hand-off ya da `/compact` öner. | Tek mesaj + arka plan emniyeti için öneri 3. |

Dayanak: alt uç 200k = Bulgu 5 (120–256k anekdotları) + Bulgu 6 ödeme (~25 istek); üst uç 400k = Bulgu 5 (Mejba ~300–400k) + Bulgu 4 (Anthropic: sıkıştırma kayıplı, sayı yok) + Bulgu 6 (ödeme ≤10–19 istek). Kaynaklar [29][43][33][34][39][20]. **Bu üç sayı yargıdır:** kanıt bir aralık veriyor, nokta vermiyor. Kitin mevcut 200k sayısı korunuyor; değişen gerekçe ve basamaklar. 150k'ya inmeyi kanıt desteklemiyor (öznel tek kaynak [34], artı Bulgu 4'teki "sık kesmenin bedeli").

**Öneri 2. Model başına fark koyma (kanıt yok); tek istisna zayıf: Sonnet 5.5 lead'de alt uçta kes.**
Kalite kanıtı üç modeli ayırmıyor (Bulgu 2). Maliyet farkı var (Fable'da sıfırlama $1,60, Opus'ta $0,64) ve 3. bölümdeki ödeme tablosu Fable için çizgiyi 300k'ya doğru iter; ama fark mutlak olarak küçük ve 300k zaten bantın içinde. Tek bant daha basit. Sonnet 5.5 için Anthropic "en zor uzun-ufuk iş için Opus daha iyi seçim" diyor [25][26]; Sonnet bir lead olarak kullanılırsa kırmızı basamağı beklemeden sarıda kesmek makul. Bu tek cümlelik vendor beyanına dayanıyor, zayıf. Kanıtla ayrılmayan şeyi hook'ta ayırma.

**Öneri 3. Otomatik sıkıştırmayı kesici olarak bırakma; yalnız emniyet supabı yap.**
Varsayılan ~967k [17] ve model "sıkıştırırken en az zeki noktada" [29]. Öneri: `autoCompactWindow` (ya da overlay `settings.json` `env`'inde `CLAUDE_CODE_AUTO_COMPACT_WINDOW`) 450k civarına çekilsin; böylece sahip yokken oturum 967k'ya sürüklenmez. Bu, sahibin "oturumu bitirme / karar sahibin" kuralına dokunur (otomatik tetikler); bu yüzden "öneri, sahip onayı bekliyor". Sayı yargı, kaynak: Bulgu 4 [17][29]. Riskler: otomatik sıkıştırma iş ortasında olur ("kötü sıkıştırma" riski [29]); bu sebeple 450k bantın dışında, en son çare.

**Öneri 4. Boyuttan bağımsız belirti tetikleyicisi: kural düzeltmesi iki kez tekrarlarsa ya da `guard_worker_route` iki kez reddederse, boyuta bakmadan kes.**
Dayanak: Anthropic "aynı konuda iki kereden fazla düzelttiysen `/clear`" [14]; lead'in model/effort vermeyi unutması kitte zaten ölçülebilir bir hook reddi (WORKFLOW 5. kural). Bu, boyut sayısından daha doğrudan bir kalite belirtisi; ölçümü öneri 7'de. Kanıt gücü: P yön, kit içi sensör çıkarım. Başka belirtiler (yalnız gözlem, eşik yok): lead daha önce okuduğunu yeniden okuyor, birbirine zıt durum anlatıyor, bayat dosya durumu üzerinde çalışıyor [39].

**Öneri 5. Sıkıştır mı, hand-off mu: bugünkü kuralı koru, dört şey ekle.**
Bugünkü kural (WORKFLOW 8) doğru çatıda: iş sürüyor ve STATE/operasyon dosyaları taşıyorsa `/compact`; yön değişti ya da set kapandıysa hand-off. Bulgu 7 bununla uyumlu (Anthropic: yeni görev = yeni oturum; iş ortasında sıkıştır [29]). Eklemeler:
 (a) **Sıkıştırmaya komut ver, varsayılana bırakma:** kitin kuralları, açık kararlar ve "kullanıcının sözleri aynen" için Anthropic'in altı maddelik özet istemini temel al [26][29]; `/compact` metnini kit tek satırda sabitlesin.
 (b) **Aynı oturumda ikinci sıkıştırma yerine hand-off:** her seferinde baştan üretilen özet tekrarlı sıkıştırmada ayrıntı kaydırıyor [32] (vendor-run, tek örnek; zayıf-orta). Kural: ilk sıkıştırma tamam, ikincisinde hand-off.
 (c) **Compact sonrası yeniden enjekte et:** bağlayıcı lead kurallarını (model+effort verme, push yalnız istekle, dil, etiketleri açma vb. ~10 madde) `compact` kaynaklı SessionStart hook'u yazdırsın ya da kök AGENTS.md'de dursun. Gerekçe Bulgu 10 [16]. Bu, hook eklemek olduğu için sahibin hook kuralı gözetilmeli: bu hook yalnız bağlama bilgi yazar, kimseyi sormaz/bloklamaz.
 (d) **Soğuk cache kuralı korunsun:** bir saatten uzun molada `/compact` tüm geçmişi tam fiyat okur [18]; kitin mevcut cümlesi (önce özeti hand-off'a yaz) doğru.

**Öneri 6. WORKFLOW 8. kuraldaki gerekçeyi düzelt.**
"10 turdan az" cümlesi bugünkü fiyatlarla yanlış (Opus/Sonnet ~25, Fable ~49 istek; Bulgu 6, 3. bölüm). Yeni gerekçe: "200k, kalite ve maliyet kesişiminden seçilmiş bir yargıdır: maliyet tek başına çizgiyi ~25–50 istekte öder; kalite için bu üç modelde ölçüm yoktur, Anthropic sayı vermez, pratisyenler 120k–400k arasında keser; sınır dogfood ölçümüyle sınanacaktır". Dayanak [20][29]. Codex lead için 200k–250k kalabilir: OpenAI 272k üstünde girdi fiyatını ikiye katlıyor [36] (tek B kaynak) ve kalite kanıtı model ayırmıyor.

**Öneri 7. Dogfood gününde ne ölçülecek (tek gün, gözlemsel; kapsam sabit, yeni inceleme döngüsü açılmaz).**
Amaç yalnız üç sayıyı (200k/300k/400k) doğrulamak ya da kaydırmak. Bağlam kovaları: 0–100k, 100–200k, 200–300k, 300–400k, 400k+. Bağlam boyutu transcript'ten hook'un kullandığı aynı yolla (son istekte girdi + cache okuma + cache yazma) okunur.
 1. **Lead'in kendi hataları, kovaya göre, 100 asistan mesajı başına:** (i) `guard_worker_route` reddi (model/effort unutuldu); (ii) `commit-msg` hook'unun AI atıf reddi; (iii) sahibin açıkça yazdığı düzeltme sayısı (elle işaretlenir: "hayır", "bunu söylemiştim"); (iv) komut dosyasıyla taranabilen mevcut kurallar: sohbet dili Türkçe mi, tanımlayıcılar backtick içinde mi, tek başına oturum etiketi (D-1 tipi) geçiyor mu, istek dışı push/yeni tur var mı. Bunlar zaten yazılı kural olduğundan ek kanarya yazmaya gerek yok.
 2. **Sıkıştırma öncesi/sonrası:** sıkıştırmadan önceki 20 mesaj ile sonraki 20 mesajda aynı sayaçlar. İkinci sıkıştırma olursa ayrıca işaretle.
 3. **Maliyet:** `scripts/agent_cost.py --latest` ve Claude Code `/usage` "Prompt cache (main)" satırı [19]: cache isabet oranı, kovaya göre istek başı maliyet, sıkıştırma ve hand-off gerçek maliyeti.
 4. **Gözlem:** hangi kovada ve hangi belirtiyle (tekrar okuma, çelişkili durum) sahip lead'i kesmek istedi, not.
 5. **Karar kuralı (önceden yazılı):** 200–300k kovasında hata oranı 0–100k kovasının en az iki katıysa (ve en az birkaç olay varsa) sarıyı 150k'ya çek; 300–400k kovasında da fark yoksa kırmızıyı 400k'ya, tavanı 500k'ya kaydır; fark yoksa bantı değiştirme. Tek günün olay sayısı küçük olacak: sonuç kanıt değil işaret sayılır, "bantı koruma" ya da "bir basamak kaydır"dan fazlasına yetmez.
 6. **Bedava başlangıç:** kurucu projenin 248 istekli transcript'i hâlâ varsa aynı sayaçlar geriye dönük çıkarılabilir; bu, dogfood gününden önce kovaları dolduran ilk veridir (kalite bilgisi hiç yoktu).

---

## 6) Açık sorular ve kanıtın ince olduğu yerler

1. **Hedef modeller için ölçüm yok.** Opus 5.5, Fable 5.1, Sonnet 5.5 için MRCR/uzun-bağlam skoru ya da kural uyumu ölçümü bulamadım (P duyuruları sayısız, S toplayıcılar farklı modeller). Anthropic modelin system card'ında olabilir; ben erişemedim.
2. **Thariq'in 300–400k sayısı** Opus 4.6/4.7 döneminden ve ikinci elden bir kopyadan; 5.x modellerde geçerli mi bilinmiyor; claude.com sayfasında görmedim. Doğrulandı (2026-10-14): sayfada yok; Anthropic'e atfedilmez.
3. **Retrieval skoru ≠ kural uyumu.** Bütün R kaynakları bulma/akıl yürütme ölçüyor. 100+ istekli kodlama oturumunda kural unutmayı ölçen yayımlanmış bir çalışma bulamadım. Bu raporun "bağlam çürümesi kural unutmayı artırır" çıkarımı yargıdır; P belgeleri ve F anekdotları aynı yönde, sayısız.
4. **Abonelik planı muhasebesi:** Max/Team planında cache okumanın kullanım sınırına nasıl yansıdığı doküman düzeyinde belirsiz [19]; ödeme hesabı API fiyatlarıyla yapıldı.
5. **Düşünce blokları:** bu modellerde önceki düşünce blokları bağlamda kalıyor [12]; bunun çürümeye katkısı (eski akıl yürütme bayatlıyor mu) bilinmiyor.
6. **Tokenizer farkı:** 4.7+ ~%30 fazla token [20]; eski makalelerdeki token eşikleri bugüne doğrudan taşınamaz.
7. **Okunmadı / bulunamadı:** Fiction.LiveBench uzunluk bazlı skorları, OpenAI-MRCR, Windsurf ve Aider'in resmi eşikleri, Hacker News tartışmaları, Reddit başlıklarının kendisi (yalnız blog ve arama özetleri üzerinden dolaylı), X'te Thariq dışında gönderiler. RULER, Lost in the Middle, LongBench v2, IFScale, Li ve ark. (instruction stability), Cline ve Codex için yalnız arama özeti okundu; sayılar özetlerden.
8. **Factory ve Mejba gibi B kaynakları** çıkar çatışması ya da tek kişi deneyimi taşıyor; sayılar yön göstergesi, kanıt değil.

---

## 7) Kaynaklar

Biçim: [n] Başlık — URL — tarih — etiket — okuma düzeyi (tam / özet).

**R (araştırma, makale, benchmark)**
1. Chroma — Context Rot: How Increasing Input Tokens Impacts LLM Performance — https://www.trychroma.com/research/context-rot — 2025-07-14 — R — tam
2. Modarressi ve ark. — NoLiMa: Long-Context Evaluation Beyond Literal Matching (ICML 2025) — https://arxiv.org/abs/2502.05167 — 2025 — R — tam (HTML tablolar)
3. Hsieh ve ark. — RULER: What's the Real Context Size of Your Long-Context Language Models? — https://arxiv.org/abs/2404.06654 — 2024 — R — özet
4. Liu ve ark. — Lost in the Middle: How Language Models Use Long Contexts (TACL 2024) — https://arxiv.org/abs/2307.03172 — 2023/2024 — R — özet
5. Bai ve ark. — LongBench v2 — https://arxiv.org/abs/2412.15204 — 2024-12 — R — özet
6. Laban ve ark. — LLMs Get Lost In Multi-Turn Conversation — https://arxiv.org/abs/2505.06120 — 2025-05 — R — tam (ilk yarısı)
7. Du ve ark. — Context Length Alone Hurts LLM Performance Despite Perfect Retrieval — https://arxiv.org/abs/2510.05381 — 2025-10 — R — tam
8. Jaroslawicz ve ark. — How Many Instructions Can LLMs Follow at Once? (IFScale) — https://arxiv.org/abs/2507.11538 — 2025-07 — R — özet
9. Li ve ark. — Measuring and Controlling Instruction (In)Stability in Language Model Dialogs — https://arxiv.org/abs/2402.10962 — 2024 — R — özet
10. Lindenbauer ve ark. (JetBrains Research) — The Complexity Trap — https://arxiv.org/abs/2508.21433 ; blog: https://blog.jetbrains.com/research/2025/12/efficient-context-management/ — 2025-12 — R — blog tam, makale özet

**P (vendor birincil doküman)**
11. Anthropic — Effective context engineering for AI agents — https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents — 2025 — P — tam
12. Claude API — Context windows — https://platform.claude.com/docs/en/build-with-claude/context-windows — 2026 — P — tam
13. Claude API — Compaction overview — https://platform.claude.com/docs/en/build-with-claude/compaction — 2026 — P — tam
14. Claude Code — Best practices — https://code.claude.com/docs/en/best-practices — 2026 — P — tam
15. Claude Code — How Claude Code works — https://code.claude.com/docs/en/how-claude-code-works — 2026 — P — tam
16. Claude Code — Explore the context window (What survives compaction) — https://code.claude.com/docs/en/context-window — 2026 — P — ilgili bölüm
17. Claude Code — Model configuration (auto-compact window, extended context) — https://code.claude.com/docs/en/model-config — 2026 — P — ilk 100k karakter (kalan 16k okunmadı)
18. Claude Code — How Claude Code uses prompt caching — https://code.claude.com/docs/en/prompt-caching — 2026 — P — tam
19. Claude Code — Manage costs effectively — https://code.claude.com/docs/en/costs — 2026 — P — tam
20. Anthropic — Pricing — https://platform.claude.com/docs/en/about-claude/pricing — 2026 — P — ilgili bölümler
21. Claude API — Prompt caching — https://platform.claude.com/docs/en/build-with-claude/prompt-caching — 2026 — P — ilk 100k karakter
22. Claude API — Prompting best practices (multiwindow, "starting fresh versus compacting") — https://platform.claude.com/docs/en/build-with-claude/prompt-engineering/claude-prompting-best-practices — 2026 — P — ilgili bölümler
23. Claude API — What's new in Claude Opus 5.5 — https://platform.claude.com/docs/en/models/opus-5-5/whats-new-opus-5-5 — 2026 — P — tam
24. Claude API — What's new in Claude Fable 5.1 — https://platform.claude.com/docs/en/models/fable-5-1/whats-new-fable-5-1 — 2026 — P — tam
25. Claude API — What's new in Claude Sonnet 5.5 — https://platform.claude.com/docs/en/models/sonnet-5-5/whats-new-sonnet-5-5 — 2026 — P — tam
26. Claude API — Prompting Claude Fable 5.1 (sıkıştırma özet istemi) ; Opus 5.5 ve Sonnet 5.5 eş sayfaları — https://platform.claude.com/docs/en/build-with-claude/prompt-engineering/prompting-claude-fable-5-1 — 2026 — P — ilgili bölümler
27. Anthropic — Introducing Claude Opus 4.6 — https://www.anthropic.com/news/claude-opus-4-6 — 2026-02 — P — tam (grafikler görüntü, okunmadı)
28. Anthropic — Introducing Claude Opus 5.5 — https://www.anthropic.com/news/claude-opus-5-5 — 2026-09-22 — P — tam (uzun-bağlam sayısı yok)
29. Claude Code ekibi (Thariq) — Using Claude Code: session management and 1M context — https://claude.com/blog/using-claude-code-session-management-and-1m-context — 2026-04-15 — P — tam (300–400k cümlesi bu sayfada görünmedi, bkz. [43])
30. OpenAI — Codex sample configuration — https://developers.openai.com/codex/config-sample — 2026 — P — arama özeti
31. Cline — Understanding context management — https://docs.cline.bot/prompting/understanding-context-management — 2026 — P — arama özeti

**B (blog, pratisyen yazısı, vendor-run ölçüm)**
32. Factory — Evaluating context compression for AI agents — https://factory.com/news/evaluating-compression — 2025-12 — B — tam (vendor-run)
33. Mejba — Claude Code 1M Context: Stop Context Rot at 300K — https://www.mejba.me/blog/claude-code-1m-context-management — 2026 — B — tam
34. Dotzlaw — Your 1M-Token Context Window Is a Lie After 120K — https://dotzlaw.com/insights/claude-code-14-context-lifecycle/ — 2026 — B — tam
35. Sikkema — Why I Shrunk Claude Code's Context Window Back to 200k — https://www.albertsikkema.com/ai/development/tools/2026/04/23/smaller-context-window-better-claude-code.html — 2026-04-23 — B — tam
36. SmartScope — Before Enabling Codex's 1M Context for GPT-5.6 Sol — https://smartscope.blog/en/blog/codex-gpt-5-6-sol-1m-context-2026/ — 2026 — B — tam
37. learncursor.dev — Cursor forgets context — https://www.learncursor.dev/fix/cursor-forgets-context — 2026 — B — arama özeti
38. Drew Breunig — How to Fix Your Context — https://www.dbreunig.com/2025/06/26/how-to-fix-your-context.html — 2025-06 — B — arama özeti

**F (forum, issue)**
39. anthropics/claude-code #35296 — 1M context window does not work as marketed — https://github.com/anthropics/claude-code/issues/35296 — 2026-03 — F — tam
40. anthropics/claude-code #40757 — Auto-compact triggers at ~420K — https://github.com/anthropics/claude-code/issues/40757 — 2026-03-30 — F — tam
41. anthropics/claude-code #24460 ve eş issue'lar (#4017, #4517, #11545 …) — CLAUDE.md compact sonrası kayboluyor — https://github.com/anthropics/claude-code/issues/24460 — 2025-2026 — F — arama özeti
42. Cursor forum — Poor context management, new window required every few turns — https://forum.cursor.com/t/poor-context-management-new-window-required-every-few-turns/162416 — 2026 — F — arama özeti

**S (ikincil)**
43. YouMind kopyası, Thariq'in X makalesi (300–400k cümlesi) — https://youmind.com/landing/x-viral-articles/claude-code-session-context-management — 2026-04-15 — S — ilgili cümle
44. pi-context-zone README (Horthy "dumb zone" ~%40 aktarımı) — https://cdn.jsdelivr.net/gh/arpagon/pi-context-zone@main/README.md — 2026 — S — arama özeti
45. BenchLM — MRCR v2 128K–256K — https://benchlm.ai/benchmarks/mrcr-v2-128k-256k — 2026-10-14 — S — tam
46. benchmarklist — MRCR 1M — https://benchmarklist.com/benchmarks/mrcr_1m/ — 2026-07 — S — tam
47. benchmarklist — MRCR v2 8-needle 256K — https://benchmarklist.com/benchmarks/mrcr_v2_8_needle_256k/ — 2026-08-12 — S — tam (kaynak zinciri şüpheli)
