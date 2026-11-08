# Video Kaydet — iPhone için Instagram/X video indirici

X (Twitter) ve Instagram videolarını **Paylaş** menüsünden tek dokunuşla galeriye kaydeder.
YouTube şimdilik deneyseldir (aşağıya bakın).

## Nasıl çalışıyor, neden güncel kalıyor?

```
Paylaş ▸ "Video Kaydet" kısayolu (Instagram/X'ten çıkmadan çalışır)
   └─ a-Shell (iPhone'da yerel Python)
        └─ indir.py
             ├─ her gece (otomasyon): yt-dlp'nin en yeni sürümünü GitHub'dan al (SHA-256 doğrulamalı)
             ├─ en yüksek çözünürlükte indir, 15 sn'lik adımlarla (iOS süre sınırı)
             │     └─ hata verirse: yeniden dene, gerekirse yt-dlp'yi güncelle (en fazla 3 deneme)
             ├─ video tarihini bugüne çek, videoindir/hazir klasörüne koy
             └─ VP9/AV1 gelirse aynı çözünürlükte H.264'e çevir (telefonun donanımıyla)
   └─ aynı kısayol, paylaş menüsünden çıkmadan: teslim ▸ Photos ▸ teslim'i boşalt
```

İndirme işini **yt-dlp** yapar. Açık kaynaklıdır, binlerce gönüllü geliştiricisi vardır.
Bir site değiştiğinde düzeltme çoğu zaman aynı gün "nightly" sürümüne gelir. Betik bu
sürümü kendisi indirir; siz hiçbir şey güncellemezsiniz. Bugün çalışan bağlantının
iki gün sonra bozulması sorununu bu sağlar.

## Kurulum (bir kerelik, ~10 dk)

### 1. a-Shell'i kurun
App Store'dan **a-Shell** uygulamasını indirin (ücretsiz ve açık kaynak).
*"a-Shell mini" sürümünü değil*, tam sürümü kurun; Python yalnızca tam sürümde var.

### 2. Klasörü oluşturun
a-Shell'i açıp şunu yazın:
```
mkdir -p ~/Documents/videoindir
```

### 3. `indir.py` dosyasını telefona indirin
a-Shell'de:
```
cd ~/Documents/videoindir
curl -L -o indir.py https://raw.githubusercontent.com/Fawloss/video-kaydet/main/indir.py
```
(Ya da bu sayfadaki `indir.py` dosyasını indirip **Dosyalar** uygulamasıyla
**iPhone'umda ▸ a-Shell ▸ videoindir** klasörüne taşıyın.)

### 4. İlk kurulumu çalıştırın
a-Shell'de:
```
cd ~/Documents/videoindir
python3 indir.py --kur
```
`yt-dlp güncellendi: (yok) -> 2026.xx.xx` yazısını görmelisiniz.

Test için:
```
python3 indir.py "https://www.instagram.com/reel/Chunk8-jurw/"
```
Sonunda `BASARILI: 1 video` yazmalı.

### 5. Kısayolları kurun (hazır dosyadan, elle kart eklemeden)

İmzalı kısayol dosyaları bu depodaki [`kisayollar`](kisayollar) klasöründe:
`Video Kaydet.shortcut` ve `GaleriyeKaydet.shortcut`. iPhone'da Safari ile dosyanın
sayfasını açın ▸ **Download raw file** (⋯ menüsünde) ▸ indirilen dosyaya dokunun ▸
**Add Shortcut** ▸ (eskisi varsa) **Replace**.

İçe aktarırken kısayol **teslim klasörünü** sorar (Video Kaydet iki kez sorar, ikisinde de
aynı klasörü seçin): **iPhone'umda ▸ a-Shell ▸
videoindir ▸ teslim** klasörünü seçin (önce aşağıdaki `mkdir` komutunu çalıştırın).

> **Replace sonrası kontrol:** iOS bazen eski sürümü "Video Kaydet 2" gibi bir adla
> bırakıyor. Kısayollar listesinde ikinci bir kopya görürseniz, adında "2" olanı silin.

Önce a-Shell'de klasörleri oluşturun (bir kez):
```
mkdir -p ~/Documents/videoindir/hazir ~/Documents/videoindir/teslim
```

#### A) Video Kaydet (asıl kısayol, her şeyi yapar)
Paylaş menüsünde çalışır; **Instagram/X'ten çıkmadan** indirir ve Fotoğraflar'a kaydeder.
```
Receive Text and URLs from Share Sheet — If there's no input: Get Clipboard
Match [desen] in Shortcut Input
If Matches does not have any value → Show Notification "Desteklenmeyen bağlantı" + Stop
Get First Item from Matches
Random Number between 100000 and 999999
Execute Command ① cd ~/Documents/videoindir
                  python3 indir.py --is [Random Number] --aktar $SHORTCUTS "[Item from List]"
Execute Command ②–⑦ (aynısı, "--devam" ekli; 6 kart)
Execute Command ⑧ python3 indir.py --is [Random Number] --teslim
Get File  teslim ▸ ".sebep.txt"  (Show Document Picker kapalı, Error If Not Found kapalı)
If File has any value → Get Text from File ▸ Show Notification "Video kaydedilemedi: [Text]" + Stop
Get Contents of Folder  teslim            (On My iPhone ▸ a-Shell ▸ videoindir ▸ teslim)
If Folder Contents does not have any value → Show Notification "Kaydedilecek video yok" + Stop
Save Folder Contents to Recents          (Save to Photo Album)
Execute Command ⑨ python3 indir.py --kaydedildi
Show Notification "Video kaydedildi ✅"
```
Bütün Execute Command kartlarında **no (run in extension)** ve **Show When Run kapalı**.

Neden böyle:
- iOS arka planda çalışan bir komutu ~30 sn sonra keser. Betik her adımda en fazla ~15 sn
  indirir, yarım dosyayı saklar; sonraki kart kaldığı yerden sürdürür. Çözünürlük hiç
  düşürülmez. İş erken biterse kalan kartlar bir saniyeden kısa sürede geçer.
- **Bağlantı yalnızca ilk adımda çözülür.** Video bilgisi `isler/<kod>/bilgi.json`'a
  kaydedilir; sonraki adımlar doğrudan indirmeye geçer. Eskiden her adım Instagram'a
  yeniden soruyordu; bu hem zaman kaybettiriyor hem de Instagram'ın geçici engeline
  ("empty media response") yol açabiliyordu.
- **Yeniden paylaşınca kaldığı yerden sürer.** İş klasörü bağlantıya göre adlandırılır
  (`?igsh=`, `?s=` gibi izleme parametreleri yok sayılır). Çok büyük bir video 7 adımda
  bitmezse aynı videoyu tekrar paylaşmak indirmeyi baştan değil, kaldığı yerden sürdürür.
- **Çoklu gönderide yalnızca ilk video** indirilir (galeri/birden fazla videolu gönderi).
- **Hata olursa:** önce doğrudan yeniden denenir (Instagram'ın boş yanıtları çoğu zaman
  geçicidir), ikinci başarısızlıkta yt-dlp zorla güncellenip denenir; en fazla 3 deneme.
- **Kaydedilecek video yoksa sebep bildirimde yazar** (ör. "Bu gönderide indirilebilir video
  yok", "Site bu içeriği girişsiz vermedi…", "İndirme bu sürede bitmedi…"). Betik sebebi
  `teslim/.sebep.txt`'ye yazar; bu dosya yalnızca teslim'de hiç video yokken bulunur.
- `--teslim` biten videoları `hazir`'den `teslim`'e alır. Fotoğraflar'ın kaydedemeyeceği bir
  dosya varsa önce H.264'e çevirir; çevrilemezse `videoindir/bozuk` klasörüne ayırır.
  Böylece tek bir bozuk dosya sonraki bütün kayıtları kilitleyemez.
- `--kaydedildi` yalnızca kaydetme başarıyla bittikten sonra `teslim`'i boşaltır. Kaydetme
  yarıda kalırsa dosyalar silinmez; bir sonraki paylaşımda onlar da kaydedilir.

**Match** deseni:
```
https://(www\.|m\.|mobile\.)?(youtube\.com|youtu\.be|x\.com|twitter\.com|instagram\.com)/[A-Za-z0-9\-._~/?=&%:+]+
```

**İlk kullanımda bir kerelik izinler** (her kaynak uygulama için ayrı, Instagram'da bir kez,
X'te bir kez, panodan çalıştırınca bir kez): "Allow Video Kaydet to share 1 … item with
a-Shell?" sorusu her a-Shell kartı için ayrı ayrı gelir ▸ hepsine **Always Allow**. Ardından `teslim` klasörü ▸ **OK**,
Fotoğraflar ▸ **Always Allow**, bildirimler ▸ **Allow**. Sonraki paylaşımlarda hiçbir şey
sorulmaz. (Kısayol yeniden içe aktarılırsa bu izinler bir kez daha sorulur.)

#### B) GaleriyeKaydet (yedek, normalde gerekmez)
`teslim` klasöründe kalmış videoları elle kaydetmek içindir. Shortcuts'ta dokunarak çalıştırın.
```
Get File teslim ▸ .sebep.txt → varsa sebebi bildir + Stop   (Video Kaydet'teki gibi)
Get Contents of Folder  teslim
If Folder Contents does not have any value → Show Notification "Kaydedilecek video yok" + Stop
Save Folder Contents to Recents
Execute Command  python3 indir.py --kaydedildi
Show Notification "Video kaydedildi ✅"
```

#### Neden VP9 kontrolü var?
Instagram bazı Reels'leri codec'ini bildirmediği tek parça dosya olarak veriyor ve bu dosya
bazen **VP9** çıkıyor. Fotoğraflar VP9'u kaydedemiyor; Shortcuts bunu yalnızca "There was a
problem running the shortcut" diye bildiriyor. Betik codec'i MP4 kutularından okuyor; VP9/AV1
gelirse aynı çözünürlükte H.264'e çeviriyor (telefonun donanım kodlayıcısı,
`h264_videotoolbox`) ve tarihini düzeltiyor.

#### C) Gece güncelleme otomasyonu
yt-dlp indirme sırasında değil, her gece otomatik güncellenir. Böylece indirme hızlı kalır.
1. Shortcuts ▸ alttaki **Automation** ▸ **+** (ya da **New Automation**) ▸ **Time of Day**.
2. Saat olarak örneğin **04:00** girin, **Daily** seçin ve **Run Immediately**'i işaretleyin.
   **Notify When Run** kapalı olsun. ▸ **Next**.
3. **New Blank Automation** ▸ a-Shell **Execute Command** ekleyin:
   ```
   cd ~/Documents/videoindir
   python3 indir.py --kur
   ```
   **›** ▸ **no (run in extension)**, **Show When Run** kapalı ▸ **Done**.

Otomasyon bir sebeple çalışmazsa betik, sürüm 3 günden eskiyse indirme sırasında kendisi
günceller. Bir indirme başarısız olursa sonraki adımlar önce doğrudan yeniden dener,
ikinci başarısızlıkta yt-dlp'yi zorla güncelleyip dener.

iOS büyük video için
onay isterse: **Settings ▸ Apps ▸ Shortcuts ▸ Advanced ▸ Allow Sharing Large Amounts of Data**
seçeneğini açın.

## Kullanım
- **X:** paylaş simgesi ▸ **Share via…** ▸ **Video Kaydet**
- **Instagram:** kâğıt uçak simgesi ▸ **Share** ▸ **Video Kaydet**
- **Alternatif:** bağlantıyı kopyalayın ve Shortcuts'ta **Video Kaydet**'e dokunun.

Birkaç saniye sonra "Video kaydedildi ✅" bildirimi gelir.

## Güvenlik önlemleri

| Risk | Önlem |
|---|---|
| Reklamlı/zararlı "video indirme siteleri", bağlantı takibi | Hiç kullanılmıyor. İndirme tamamen telefonda yapılıyor; bağlantılarınız aracı bir sunucuya gitmiyor. |
| Sahte ya da değiştirilmiş yt-dlp | Yalnızca `github.com/yt-dlp` resmi sürümleri kullanılıyor. Bağlantı yalnızca HTTPS ile kuruluyor, HTTPS dışı yönlendirme reddediliyor ve **SHA-256 özeti tutmayan dosya kullanılmıyor**. |
| Kötü niyetli bağlantıyla komut çalıştırma | Bağlantı iki kez denetleniyor: önce kısayoldaki desenle, sonra Python'da site listesi ve karakter listesiyle. Tırnak, `$`, `;`, boşluk gibi karakterler reddediliyor. |
| Beklenmedik ayarlar | `--ignore-config` kullanılıyor; dışarıdan yapılandırma dosyası yüklenmiyor ve komut çalıştırma seçenekleri kapalı. |
| Yanlışlıkla dev indirme | Video başına en fazla 2 GB, bağlantı başına tek video. |
| Şifre ve hesap | Şifre hiçbir yere girilmiyor. |

**Kalan riskler (dürüstçe):**
- yt-dlp projesinin kendisi ele geçirilirse (tedarik zinciri saldırısı) SHA-256 kontrolü
  bunu yakalayamaz, çünkü özet de aynı yerden geliyor. Daha temkinli olmak isterseniz
  `indir.py` dosyasında `KANAL = "stable"` yapın; stable sürümler daha uzun süre test edilir.
- Telefondaki Python ortamını a-Shell uygulaması sağlıyor; bu uygulamaya güvenmek gerekiyor.

## Instagram/X giriş isterse (isteğe bağlı)
Bazı içerikler giriş yapmadan indirilemez; bildirimde "Site bu içeriği girişsiz vermedi"
yazar. Gizli hesaplar ve yaş sınırlı içerikler hep böyledir; normal Reels'lerde bu genelde
geçicidir, birkaç dakika sonra tekrar paylaşmak yeter. Sık oluyorsa tarayıcıdan dışa
aktarılmış bir `cookies.txt` dosyasını `videoindir` klasörüne koyarsanız betik onu kullanır.
**Ana hesabınızın çerezlerini kullanmayın**: bu dosya hesabınıza erişim sağlar. Bunun
için ayrı, ikincil bir hesap açın.

## YouTube (deneysel)
YouTube artık videoları indirebilmek için bir JavaScript motoru (deno) istiyor ve
iPhone'da bu motor yok. Bu yüzden YouTube indirmeleri çoğu zaman başarısız olacak. İleride
yt-dlp bu sorunu çözerse betik kendini güncellediği için YouTube kendiliğinden çalışmaya
başlayabilir. Çözüm gerekirse ayrı olarak eklenebilir.

## Sorun giderme
- **Bildirimdeki sebep** çoğu zaman yeterlidir. Ayrıntı için Dosyalar ▸ iPhone'umda ▸
  a-Shell ▸ videoindir ▸ **gunluk.txt**: her adımın tam çıktısı (yt-dlp hataları dahil)
  tarih sırasıyla burada. Dosya kendiliğinden ~200 KB'ta tutulur.
- a-Shell'de `cat ~/Documents/videoindir/sonuc.txt` komutu son sonucu gösterir.
- `python3 indir.py --kur` yt-dlp'yi hemen günceller.
- Bir video kaydedilmediyse Shortcuts'ta **GaleriyeKaydet**'e dokunun; `teslim`'de kalanları kaydeder.
- `videoindir/bozuk` klasöründe dosya varsa Fotoğraflar'a kaydedilemeyen ve çevrilemeyen videolardır.
- Sesi olmayan video gelirse ffmpeg bulunamamış demektir. Betik bu durumda sesli tek
  dosya formatını seçer; kalite biraz düşebilir.

## Yasal not
İndirdiğiniz videoları yalnızca kişisel kullanım için saklayın. Telif hakkı içerik
sahibine aittir. Platformların kullanım koşulları indirmeyi kısıtlayabilir.

## Lisans
© 2026 [Fawloss](https://github.com/Fawloss). Tüm hakları saklıdır.

Bu depo herkese açıktır: dosyaları görüntüleyebilir, indirip kendi telefonunuza
kişisel kullanım için kurabilirsiniz. Depodaki dosyaları yalnızca sahibi değiştirebilir;
değiştirilmiş sürümlerin yeniden yayımlanmasına izin verilmez.
