#!/usr/bin/env python3
"""
Video İndirici — iPhone'da a-Shell içinde çalışan yt-dlp sarmalayıcısı.

Kullanım (a-Shell içinde, bu dosyanın bulunduğu klasörde):
    python3 indir.py --kur              # yt-dlp'yi ilk kez indir / zorla güncelle
                                        # (her gece otomasyonla çalıştırılır)
    python3 indir.py "URL"              # yeni indirme başlatır (en fazla ~15 sn çalışır)
    python3 indir.py --devam "URL"      # yarım kaldıysa sürdürür; hata verdiyse yt-dlp'yi
                                        # zorla güncelleyip bir kez yeniden dener
  Kısayol ek olarak "--is <numara> --aktar $SHORTCUTS" verir: her çalıştırma ayrı
  klasör kullanır ve videolar <numara>_1.mp4 adıyla paylaşım klasörüne taşınır.

Güvenlik ilkeleri:
  * yt-dlp yalnızca resmi GitHub sürümlerinden, HTTPS ile indirilir ve
    SHA-256 özeti doğrulanmadan kullanılmaz. HTTPS dışı yönlendirme reddedilir.
  * Sadece izin verilen sitelerin bağlantıları kabul edilir; bağlantı katı bir
    karakter listesiyle denetlenir (komut enjeksiyonuna karşı).
  * Başka hiçbir sunucuya veri gönderilmez; indirme cihazın kendisinde yapılır.
"""
import hashlib
import json
import os
import re
import shutil
import struct
import sys
import time
import urllib.error
import urllib.request
import zipfile
from urllib.parse import urlsplit

# ---- Ayarlar ---------------------------------------------------------------
# "nightly": site değişikliklerine karşı düzeltmeler genelde aynı gün gelir
#            (yt-dlp geliştiricilerinin de önerdiği kanal).
# "stable" : daha seyrek ama daha uzun süre test edilmiş sürümler.
KANAL = "nightly"
DEPOLAR = {"stable": "yt-dlp/yt-dlp", "nightly": "yt-dlp/yt-dlp-nightly-builds"}
# Asıl güncelleme her gece "--kur" ile (Kısayollar otomasyonu) yapılır; iOS arka plan
# komutlarına kısa süre tanıdığı için indirme sırasında yalnızca sürüm çok eskiyse
# güncellenir. Başarısızlıkta (--tekrar) bu beklenmeden güncellenir.
GUNCELLEME_ARALIGI = 3 * 24 * 3600  # saniye
PARALEL_PARCA = 4                   # HLS parçalarını aynı anda indir (X videoları)
AZAMI_DOSYA = "2G"              # tek videoda üst sınır
# Çoklu gönderide (galeri/birden fazla video) yalnızca ilk video indirilir.

IZINLI_ALANLAR = {
    # YouTube deneysel: artık bir JavaScript motoru (deno) istiyor, iPhone'da yok.
    "youtube.com", "www.youtube.com", "m.youtube.com", "youtu.be",
    "x.com", "www.x.com", "mobile.x.com",
    "twitter.com", "www.twitter.com", "mobile.twitter.com",
    "instagram.com", "www.instagram.com",
}
GUVENLI_KARAKTER = re.compile(r"^[A-Za-z0-9\-._~/?=&%:+]+$")
VIDEO_UZANTILARI = (".mp4", ".mov", ".m4v")

KOK = os.path.dirname(os.path.abspath(__file__))
YTDLP = os.path.join(KOK, "yt-dlp")          # resmi yt-dlp zipapp dosyası
SURUM = os.path.join(KOK, "surum.txt")
CIKTI = os.path.join(KOK, "cikti")
SONUC = os.path.join(KOK, "sonuc.txt")
SAYI = os.path.join(KOK, "sayi.txt")         # kısayolun okuduğu video sayısı
COOKIES = os.path.join(KOK, "cookies.txt")   # isteğe bağlı, bkz. KURULUM.md
ONBELLEK = os.path.join(KOK, ".onbellek")


# ---- Güvenli ağ erişimi ----------------------------------------------------
class _SadeceHTTPS(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if not newurl.lower().startswith("https://"):
            raise urllib.error.URLError("HTTPS olmayan yönlendirme reddedildi: " + newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


_ACICI = urllib.request.build_opener(_SadeceHTTPS)


def _getir(url, sinir):
    istek = urllib.request.Request(url, headers={"User-Agent": "videoindir-ashell"})
    with _ACICI.open(istek, timeout=60) as yanit:
        veri = yanit.read(sinir + 1)
    if len(veri) > sinir:
        raise ValueError("Beklenenden büyük yanıt: " + url)
    return veri


# ---- yt-dlp güncelleme -----------------------------------------------------
def guncelle(zorla=False):
    var = os.path.isfile(YTDLP) and os.path.isfile(SURUM)
    if var and not zorla and time.time() - os.path.getmtime(SURUM) < GUNCELLEME_ARALIGI:
        return "Güncelleme denetimi atlandı (yakın zamanda yapıldı)."

    depo = DEPOLAR[KANAL]
    bilgi = json.loads(_getir(f"https://api.github.com/repos/{depo}/releases/latest", 2_000_000))
    etiket = str(bilgi.get("tag_name", ""))
    if not re.fullmatch(r"[0-9A-Za-z._\-]{1,64}", etiket):
        raise ValueError("Geçersiz sürüm etiketi: " + etiket)

    mevcut = open(SURUM, encoding="utf-8").read().strip() if var else ""
    if var and etiket == mevcut:
        os.utime(SURUM)  # denetim zamanını yenile
        return f"yt-dlp güncel ({etiket})."

    taban = f"https://github.com/{depo}/releases/download/{etiket}/"
    beklenen = None
    for satir in _getir(taban + "SHA2-256SUMS", 200_000).decode("utf-8").splitlines():
        parcalar = satir.split()
        if len(parcalar) == 2 and parcalar[1].lstrip("*") == "yt-dlp":
            beklenen = parcalar[0].lower()
    if not beklenen or not re.fullmatch(r"[0-9a-f]{64}", beklenen):
        raise ValueError("SHA-256 özeti bulunamadı.")

    ikili = _getir(taban + "yt-dlp", 60_000_000)
    if hashlib.sha256(ikili).hexdigest() != beklenen:
        raise ValueError("SHA-256 UYUŞMUYOR — dosya kullanılmadı!")

    gecici = f"{YTDLP}.{os.getpid()}.yeni"  # aynı anda iki güncelleme çakışmasın
    with open(gecici, "wb") as f:
        f.write(ikili)
    if not zipfile.is_zipfile(gecici):
        os.remove(gecici)
        raise ValueError("İndirilen dosya geçerli bir yt-dlp paketi değil.")
    os.replace(gecici, YTDLP)
    with open(SURUM, "w", encoding="utf-8") as f:
        f.write(etiket)
    return f"yt-dlp güncellendi: {mevcut or '(yok)'} -> {etiket}"


# ---- Bağlantı denetimi -----------------------------------------------------
def dogrula(url):
    url = url.strip()
    if len(url) > 500 or not GUVENLI_KARAKTER.match(url):
        raise ValueError("Bağlantı izin verilmeyen karakterler içeriyor.")
    p = urlsplit(url)
    if p.scheme != "https" or p.username or p.password or p.port:
        raise ValueError("Sadece düz https bağlantıları kabul edilir.")
    if (p.hostname or "").lower() not in IZINLI_ALANLAR:
        raise ValueError("Desteklenmeyen site: " + str(p.hostname))
    return url


# ---- İndirme ---------------------------------------------------------------
# iOS, Kısayollar'dan arka planda çalışan komutları yaklaşık yarım dakika sonra
# durdurur. Bu yüzden betik süresi dolmadan kendini durdurur, yarım dosyayı (.part)
# saklar; "--devam" ile çalışan sonraki adım indirmeyi kaldığı yerden sürdürür.
BASLANGIC = time.time()
SURE_BUTCESI = 15  # saniye; bir adımda en fazla bu kadar indir, sonra devretmek için dur
EN_AZ_INDIRME = 5  # saniye; adres bulma uzun sürse bile her adımda en az bu kadar indir
DONUSUM_SINIRI = 12  # saniye; bundan geç biten indirmenin H.264 çevirisi sonraki adıma kalır


def _cikti_temizle():
    shutil.rmtree(CIKTI, ignore_errors=True)
    os.makedirs(CIKTI, exist_ok=True)


OYNATILABILIR = "[vcodec~='^(avc|h26[45]|hev|hvc)']"


# Fotoğraflar'ın kabul ettiği görüntü codec'leri. Instagram codec'ini bildirmediği tek
# parça dosyaları bazen VP9 olarak veriyor; Fotoğraflar bunu kaydedemiyor ve kısayol
# yalnızca "There was a problem running the shortcut" diyerek duruyordu.
OYNAYAN = {b"avc1", b"avc3", b"hvc1"}


def _kutular(veri):
    p = 0
    while p + 8 <= len(veri):
        boyut, tip = struct.unpack(">I4s", veri[p:p + 8])
        bas = 8
        if boyut == 1:
            boyut, bas = struct.unpack(">Q", veri[p + 8:p + 16])[0], 16
        elif boyut == 0:
            boyut = len(veri) - p
        if boyut < bas or p + boyut > len(veri):
            return
        yield tip, veri[p + bas:p + boyut]
        p += boyut


def _kutu_bul(veri, *yol):
    for tip, ic in _kutular(veri):
        if tip == yol[0]:
            return ic if len(yol) == 1 else _kutu_bul(ic, *yol[1:])
    return None


def _izler(yol):
    """mp4'teki izler: [(tür, codec, yükseklik)], ör. (b"vide", b"avc1", 1280)."""
    try:
        boyut = os.path.getsize(yol)
        with open(yol, "rb") as f:
            moov, konum = None, 0
            while konum + 8 <= boyut:  # moov dosyanın başında ya da sonunda olabilir
                f.seek(konum)
                kutu, tip = struct.unpack(">I4s", f.read(8))
                bas = 8
                if kutu == 1:
                    kutu, bas = struct.unpack(">Q", f.read(8))[0], 16
                elif kutu == 0:
                    kutu = boyut - konum
                if kutu < bas:
                    break
                if tip == b"moov":
                    f.seek(konum + bas)
                    moov = f.read(min(kutu - bas, 64 << 20))
                    break
                konum += kutu
    except (OSError, struct.error):
        return []
    izler = []
    for tip, trak in _kutular(moov or b""):
        hdlr = _kutu_bul(trak, b"mdia", b"hdlr")
        stsd = _kutu_bul(trak, b"mdia", b"minf", b"stbl", b"stsd")
        tkhd = _kutu_bul(trak, b"tkhd")
        if tip != b"trak" or not hdlr or not stsd or len(hdlr) < 12 or len(stsd) < 16:
            continue
        yukseklik = struct.unpack(">I", tkhd[-4:])[0] >> 16 if tkhd and len(tkhd) >= 80 else 0
        izler.append((hdlr[8:12], stsd[12:16], yukseklik))
    return izler


def _oynatilabilir_yap(yol):
    """Görüntü H.264/HEVC değilse (VP9/AV1) aynı çözünürlükte H.264'e çevirir.

    Dönüş: True (dosya Fotoğraflar'a kaydedilebilir) | False (görüntü yok ya da çevrilemedi).
    Çeviri telefonun donanım kodlayıcısıyla (VideoToolbox) yapılır, saniyeler sürer.
    """
    izler = _izler(yol)
    goruntu = [i for i in izler if i[0] == b"vide"]
    if not goruntu:
        print("UYARI: görüntü izi yok, atlandı:", os.path.basename(yol))
        return False
    if all(codec in OYNAYAN for _, codec, _ in goruntu):
        return True
    _, codec, yukseklik = goruntu[0]
    print(f"Görüntü {codec.decode('latin1')}: iPhone kaydedemez, H.264'e çevriliyor ({yukseklik}p).")
    ses_kopya = all(c == b"mp4a" for t, c, _ in izler if t == b"soun")
    hiz = "6M" if yukseklik <= 720 else "10M" if yukseklik <= 1080 else "20M"
    gecici = yol + ".h264.mp4"
    try:
        sys.path.insert(0, YTDLP)
        from yt_dlp.postprocessor.ffmpeg import FFmpegPostProcessor
        FFmpegPostProcessor().real_run_ffmpeg([(yol, [])], [(gecici, [
            "-map", "0:v:0", "-map", "0:a:0?",
            "-c:v", "h264_videotoolbox", "-allow_sw", "1", "-b:v", hiz, "-tag:v", "avc1",
            "-c:a", "copy" if ses_kopya else "aac"])])
        yeni = [c for t, c, _ in _izler(gecici) if t == b"vide"]
        if not yeni or not all(c in OYNAYAN for c in yeni):
            raise ValueError("çıktı yine oynatılamıyor")
    except Exception as e:
        print("HATA: H.264'e çevrilemedi:", e)
        if os.path.exists(gecici):
            os.remove(gecici)
        return False
    os.replace(gecici, yol)
    _tarih_duzelt(yol)  # ffmpeg eski tarihi kopyalar; video galerinin en altına gelsin
    return True


def indir(url, temizle=True):
    """Dönüş: ("tamam", videolar) | ("devam", []) | ("hata", [])"""
    if temizle:
        _cikti_temizle()
        if os.path.exists(BILGI):
            os.remove(BILGI)
    os.makedirs(CIKTI, exist_ok=True)
    sys.path.insert(0, YTDLP)
    import yt_dlp  # zipapp içinden; güncellemeden SONRA içe aktarılmalı

    argumanlar = [
        "--ignore-config",                 # başka yapılandırma dosyası yüklenmesin
        "--no-playlist", "-I", "1",        # çoklu gönderide yalnızca ilk video
        # Çözünürlük asla düşürülmez: önce en yüksek çözünürlük, eşitse H.264 + AAC
        "-S", "res,vcodec:h264,acodec:m4a",
        "--merge-output-format", "mp4",
        "--max-filesize", AZAMI_DOSYA,
        "--retries", "3", "--socket-timeout", "30",
        "--concurrent-fragments", str(PARALEL_PARCA),
        "--no-mtime", "--no-progress", "--continue", "--color", "never",
        "--cache-dir", ONBELLEK,
        "-o", os.path.join(CIKTI, "%(autonumber)02d_%(id).40s.%(ext)s"),
    ]
    # Yalnızca iPhone'un oynatabildiği görüntü (H.264/HEVC); VP9/AV1 seçilirse Fotoğraflar'da
    # yalnızca ses çalar. Bu sınır içinde her zaman en yüksek çözünürlük seçilir.
    from yt_dlp.postprocessor.ffmpeg import FFmpegPostProcessor
    if FFmpegPostProcessor().available:
        bicim = (f"bv*{OYNATILABILIR}+ba/b{OYNATILABILIR}[acodec!=?none]"
                 f"/b[vcodec!=?none][acodec!=?none]/bv*{OYNATILABILIR}/b[vcodec!=?none]")
    else:  # ffmpeg yoksa ayrı ses/görüntü birleştirilemez; sesli tek dosya seç
        print("UYARI: ffmpeg bulunamadı; ses+görüntü birleşik format seçiliyor.")
        bicim = (f"b{OYNATILABILIR}[acodec!=?none]/b[vcodec!=?none][acodec!=?none]"
                 f"/b{OYNATILABILIR}/b[vcodec!=?none]")  # sonuncular: sesi olmayan videolar
    argumanlar += ["-f", bicim]
    if os.path.isfile(COOKIES):
        argumanlar += ["--cookies", COOKIES]

    ayar = yt_dlp.parse_options(argumanlar).ydl_opts
    ayar["ignoreerrors"] = False
    sure_doldu = []
    ilk_indirme = []

    def kanca(d):
        if d.get("status") != "downloading":
            return
        simdi = time.time()
        if not ilk_indirme:
            ilk_indirme.append(simdi)
        # Her adım en az EN_AZ_INDIRME sn indirir; yoksa yavaş başlangıçta hiç ilerlenemez
        if simdi - BASLANGIC > SURE_BUTCESI and simdi - ilk_indirme[0] > EN_AZ_INDIRME:
            sure_doldu.append(True)
            raise KeyboardInterrupt  # yt-dlp bunu yutmaz; .part dosyası yerinde kalır

    ayar["progress_hooks"] = [kanca]
    try:
        with yt_dlp.YoutubeDL(ayar) as ydl:
            # Bağlantı yalnızca ilk adımda çözülür; bilgi saklanır ve sonraki adımlar
            # doğrudan indirmeye geçer. Her adımda Instagram'a yeniden sormak hem zaman
            # kaybettiriyor hem de geçici engele (rate limit) yol açabiliyordu.
            if not os.path.isfile(BILGI):
                bilgi = ydl.sanitize_info(ydl.extract_info(url, download=False))
                if not bilgi:
                    raise ValueError("no video in this post")
                if bilgi.get("_type") == "playlist":  # galeri: yalnızca ilk video
                    girdiler = [g for g in (bilgi.get("entries") or []) if g]
                    if not girdiler:
                        raise ValueError("no video in this post")
                    bilgi = girdiler[0]
                with open(BILGI + ".yeni", "w", encoding="utf-8") as f:
                    json.dump(bilgi, f)
                os.replace(BILGI + ".yeni", BILGI)
            try:
                kod = ydl.download_with_info_file(BILGI)
            except yt_dlp.utils.DownloadError as e:
                if not re.search(r"HTTP Error 4(03|10)|expired", str(e)):
                    raise
                print("Saklanan adresin süresi dolmuş; bağlantı yeniden çözülüyor.")
                os.remove(BILGI)
                return "devam", []
    except KeyboardInterrupt:
        if sure_doldu:
            print(f"Süre doldu ({SURE_BUTCESI} sn); indirme sonraki adımda sürecek.")
            return "devam", []
        raise
    except Exception as e:
        print("HATA:", e)
        _sebep_yaz(_sebep_cevir(str(e)))
        return "hata", []

    # ".f137.mp4", ".fdash-123a.mp4" gibi adlar birleştirilmemiş (sessiz/görüntüsüz) parçalardır
    adaylar = [ad for ad in sorted(os.listdir(CIKTI))
               if ad.lower().endswith(VIDEO_UZANTILARI) and not re.search(r"\.f[^.]+\.\w+$", ad)
               and not ad.endswith(".h264.mp4")]
    cevrilecek = any(c not in OYNAYAN for ad in adaylar
                     for t, c, _ in _izler(os.path.join(CIKTI, ad)) if t == b"vide")
    if cevrilecek and time.time() - BASLANGIC > DONUSUM_SINIRI:
        print("İndirme bitti; H.264'e çevirme sonraki adımda yapılacak.")
        return "devam", []
    videolar = []
    for ad in sorted(os.listdir(CIKTI)):
        yol = os.path.join(CIKTI, ad)
        # görüntüsü olmayan ya da H.264'e çevrilemeyen dosya galeriye gönderilmez
        if ad in adaylar and _oynatilabilir_yap(yol):
            videolar.append(ad)
        elif os.path.isfile(yol):
            os.remove(yol)  # yarım kalan/ara dosyalar galeriye gitmesin
    if kod or not videolar:
        _sebep_yaz("Videonun görüntüsü kaydedilebilir biçimde alınamadı.")
        return "hata", []
    # Kısayol dosyaları a-Shell'in "Get file" eylemiyle 1.mp4, 2.mp4… adıyla alır
    for i, ad in enumerate(videolar, 1):
        os.replace(os.path.join(CIKTI, ad), os.path.join(CIKTI, f"{i}.mp4"))
    return "tamam", videolar


# ---- Ana akış --------------------------------------------------------------
# Kısayol art arda çalıştırılınca her çalıştırma kendi "iş numarasıyla" (--is)
# ayrı bir klasör kullanır; böylece aynı anda inen videolar birbirini silmez.
ESKI_DOSYA = 6 * 3600  # saniye; bundan eski iş klasörleri ve kayıtlar silinir
AKTAR = None       # --aktar ile verilen paylaşım klasörü ($SHORTCUTS)
IS_NO = None
DURUM = os.path.join(KOK, ".durum")          # calisiyor | devam | hata | tamam
GUNCELLENDI = os.path.join(KOK, ".guncellendi")
BILGI = os.path.join(KOK, "bilgi.json")      # ilk adımda çözülen video bilgisi
KAYIT = os.path.join(KOK, "kayit")           # <iş no>.txt: o paylaşımın başarısızlık sebebi
GUNLUK = os.path.join(KOK, "gunluk.txt")     # bütün çalıştırmaların çıktısı (sorun giderme)


def _is_anahtari(url):
    """Aynı video için hep aynı klasör: yeniden paylaşınca indirme kaldığı yerden sürer.
    Paylaşım izleme parametreleri (?igsh=, ?s=) farklı olsa da anahtar değişmez."""
    p = urlsplit(url)
    host = re.sub(r"^(www|m|mobile)\.", "", p.hostname.lower())
    host = {"twitter.com": "x.com"}.get(host, host)
    yol = p.path.rstrip("/")
    if host == "youtu.be" or p.path.startswith("/watch"):
        yol += "?" + p.query  # YouTube'da video kimliği sorgudadır
    return hashlib.sha1((host + yol).encode()).hexdigest()[:16]


def _is_kur(is_no, url):
    global CIKTI, SAYI, DURUM, GUNCELLENDI, IS_NO, BILGI
    IS_NO = is_no
    isler = os.path.join(KOK, "isler")
    os.makedirs(isler, exist_ok=True)
    anahtar = _is_anahtari(url)
    for ad in os.listdir(isler):  # yarım kalmış eski işleri temizle
        yol = os.path.join(isler, ad)
        if ad != anahtar and time.time() - os.path.getmtime(yol) > ESKI_DOSYA:
            shutil.rmtree(yol, ignore_errors=True)
    klasor = os.path.join(isler, anahtar)
    os.makedirs(klasor, exist_ok=True)
    CIKTI = os.path.join(klasor, "cikti")
    SAYI = os.path.join(klasor, "sayi.txt")
    DURUM = os.path.join(klasor, ".durum")
    GUNCELLENDI = os.path.join(klasor, ".guncellendi")
    BILGI = os.path.join(klasor, "bilgi.json")


# ---- Başarısızlık sebebi ---------------------------------------------------
# Video Kaydet, kaydedecek video bulamazsa teslim/.sebep.txt dosyasını bildirimde
# gösterir. Böylece "neden olmadı" sorusunun cevabı telefonda görünür.
SEBEPLER = [
    (r"login|log in|rate.?limit|not available|empty media|401|cookies|private|sensitive"
     r"|age.?restricted|NSFW|authenticat",
     "Site bu içeriği girişsiz vermedi (gizli/yaş sınırlı hesap ya da geçici engel). "
     "Birkaç dakika sonra tekrar paylaşın."),
    (r"no video|there's no video|does not contain|no media|No formats? found|"
     r"Requested format is not available",
     "Bu gönderide indirilebilir video yok (yalnızca fotoğraf olabilir)."),
    (r"Unsupported URL", "Bu bağlantı türü desteklenmiyor."),
    (r"larger than max-filesize", "Video 2 GB sınırını aşıyor."),
    (r"deno|JavaScript|n challenge|PO Token", "YouTube şu an telefonda indirilemiyor."),
    (r"timed out|Network|URLError|getaddrinfo|Connection|SSL|Temporary failure",
     "İnternet bağlantısı sorunu; tekrar paylaşın."),
]


def _sebep_cevir(hata):
    hata = re.sub(r"\x1b\[[0-9;]*m", "", hata)  # renk kodları
    for desen, metin in SEBEPLER:
        if re.search(desen, hata, re.I):
            return metin
    return "İndirilemedi: " + re.sub(r"^ERROR:\s*(\[[^\]]+\]\s*)?", "", hata).strip()[:120]


def _sebep_yaz(metin):
    if not IS_NO:
        return
    os.makedirs(KAYIT, exist_ok=True)
    for ad in os.listdir(KAYIT):
        yol = os.path.join(KAYIT, ad)
        if time.time() - os.path.getmtime(yol) > ESKI_DOSYA:
            os.remove(yol)
    with open(os.path.join(KAYIT, IS_NO + ".txt"), "w", encoding="utf-8") as f:
        f.write(metin)


def _sebep_oku(is_no):
    try:
        with open(os.path.join(KAYIT, is_no + ".txt"), encoding="utf-8") as f:
            return f.read().strip()
    except OSError:
        return ""


# ---- Günlük ----------------------------------------------------------------
class _Tee:
    """Çıktıyı hem ekrana hem gunluk.txt'ye yazar (kısayol çıktıyı göstermiyor)."""

    def __init__(self, akis, dosya):
        self.akis, self.dosya = akis, dosya

    def write(self, s):
        for hedef in (self.akis, self.dosya):
            try:
                hedef.write(s)
            except Exception:
                pass
        return len(s)

    def flush(self):
        for hedef in (self.akis, self.dosya):
            try:
                hedef.flush()
            except Exception:
                pass

    def __getattr__(self, ad):
        return getattr(self.akis, ad)


def _gunluk_ac():
    try:
        if os.path.getsize(GUNLUK) > 400_000:  # büyümesin: son 200 KB kalsın
            with open(GUNLUK, "rb") as f:
                f.seek(-200_000, 2)
                son = f.read()
            with open(GUNLUK, "wb") as f:
                f.write(son)
    except OSError:
        pass
    try:
        dosya = open(GUNLUK, "a", encoding="utf-8", buffering=1)
    except OSError:
        return
    dosya.write(f"\n=== {time.strftime('%Y-%m-%d %H:%M:%S')} {' '.join(sys.argv[1:])}\n")
    sys.stdout = _Tee(sys.stdout, dosya)
    sys.stderr = _Tee(sys.stderr, dosya)


def _durum_oku():
    try:
        with open(DURUM, encoding="utf-8") as f:
            return f.read().strip()
    except OSError:
        return ""


def _durum_yaz(durum):
    with open(DURUM, "w", encoding="utf-8") as f:
        f.write(durum)


def _sayi_yaz(sayi):
    with open(SAYI, "w", encoding="utf-8") as f:
        f.write(str(sayi))
    if AKTAR and IS_NO:
        with open(os.path.join(AKTAR, f"{IS_NO}_sayi.txt"), "w", encoding="utf-8") as f:
            f.write(str(sayi))


# Biten videolar "hazir" klasörüne konur. GaleriyeKaydet (Shortcuts uygulamasının içinde
# çalışır) önce "--teslim" ile bunları "teslim" klasörüne aldırır, sonra o klasörü
# doğrudan okuyup Fotoğraflar'a kaydeder. Bir sonraki "--teslim" kaydedilmişleri siler.
HAZIR = os.path.join(KOK, "hazir")
TESLIM = os.path.join(KOK, "teslim")
BOZUK = os.path.join(KOK, "bozuk")
MP4_DONEMI = 2082844800  # 1904-01-01 ile 1970-01-01 arası saniye (mp4 zaman başlangıcı)


def _tarih_duzelt(yol):
    """mp4 içindeki oluşturma tarihini şimdiye çeker; Fotoğraflar videoyu en alta koyar.

    Platformlar dosyaya eski ya da boş (1904/1970) tarih yazabiliyor; Fotoğraflar
    videoyu o tarihe yerleştirdiği için kaydedilen video "yok" gibi görünüyordu.
    Yalnızca sabit boyutlu tarih alanları yerinde değiştirilir; görüntüye dokunulmaz.
    """
    simdi = int(time.time()) + MP4_DONEMI

    def gez(f, bas, son):
        konum = bas
        while konum + 8 <= son:
            f.seek(konum)
            boyut, tip = struct.unpack(">I4s", f.read(8))
            veri = konum + 8
            if boyut == 1:
                boyut = struct.unpack(">Q", f.read(8))[0]
                veri = konum + 16
            elif boyut == 0:
                boyut = son - konum
            if boyut < 8:
                return
            if tip in (b"moov", b"trak", b"mdia"):
                gez(f, veri, konum + boyut)
            elif tip in (b"mvhd", b"tkhd", b"mdhd"):
                f.seek(veri)
                surum = f.read(1)[0]
                f.seek(veri + 4)  # sürüm (1) + bayraklar (3)
                if surum == 1:
                    f.write(struct.pack(">QQ", simdi, simdi))
                else:
                    f.write(struct.pack(">II", simdi & 0xFFFFFFFF, simdi & 0xFFFFFFFF))
            konum += boyut

    try:
        with open(yol, "r+b") as f:
            gez(f, 0, os.path.getsize(yol))
    except Exception as e:  # tarih düzeltilemese de video kaydedilsin
        print("UYARI: video tarihi düzeltilemedi:", e)


def _aktar(sayi):
    """Biten videoları GaleriyeKaydet'in alacağı "hazir" klasörüne taşır."""
    if not IS_NO:
        return
    os.makedirs(HAZIR, exist_ok=True)
    for i in range(1, sayi + 1):
        video = os.path.join(CIKTI, f"{i}.mp4")
        _tarih_duzelt(video)
        os.replace(video, os.path.join(HAZIR, f"{IS_NO}_{i}.mp4"))


def _sonuc(metin, sayi=0):
    print(metin)
    with open(SONUC, "w", encoding="utf-8") as f:
        f.write(metin + "\n")
    _aktar(sayi)
    _sayi_yaz(sayi)


SEBEP_DOSYASI = os.path.join(TESLIM, ".sebep.txt")  # nokta: klasör içeriğinde görünmez


def teslim(is_no=None):
    """Hazır videoları "teslim"e taşır. Önceki kaydetme yarıda kaldıysa o dosyalar
    silinmez, "teslim"de bekler ve bu sefer onlar da kaydedilir.

    Kaydedilecek video kalmadıysa sebebi teslim/.sebep.txt'ye yazar; kısayol bunu
    bildirimde gösterir."""
    os.makedirs(HAZIR, exist_ok=True)
    os.makedirs(TESLIM, exist_ok=True)
    if os.path.exists(SEBEP_DOSYASI):
        os.remove(SEBEP_DOSYASI)
    sayi = 0
    for ad in sorted(os.listdir(HAZIR)):
        if ad.endswith(".mp4"):
            os.replace(os.path.join(HAZIR, ad), os.path.join(TESLIM, ad))
            sayi += 1
    # Fotoğraflar'ın kaydedemeyeceği tek bir dosya bile GaleriyeKaydet'i her seferinde
    # hata verdirir; böyle dosyalar çevrilir, çevrilemezse "bozuk" klasörüne ayrılır.
    for ad in sorted(os.listdir(TESLIM)):
        yol = os.path.join(TESLIM, ad)
        if os.path.isfile(yol) and not (ad.endswith(".mp4") and _oynatilabilir_yap(yol)):
            os.makedirs(BOZUK, exist_ok=True)
            os.replace(yol, os.path.join(BOZUK, ad))
            print("UYARI: kaydedilemeyecek dosya ayrıldı:", ad)
    if not any(ad.endswith(".mp4") for ad in os.listdir(TESLIM)):
        sebep = (_sebep_oku(is_no) if is_no else "") or (
            "İndirme bu sürede bitmedi. Aynı videoyu tekrar paylaşın; kaldığı yerden sürer.")
        with open(SEBEP_DOSYASI, "w", encoding="utf-8") as f:
            f.write(sebep)
        print("Sebep:", sebep)
    print(f"Teslim: {sayi} video")


def kaydedildi():
    """GaleriyeKaydet videoları Fotoğraflar'a kaydettikten sonra "teslim"i boşaltır."""
    os.makedirs(TESLIM, exist_ok=True)
    for ad in os.listdir(TESLIM):
        yol = os.path.join(TESLIM, ad)
        if os.path.isfile(yol):
            os.remove(yol)
    print("Teslim klasörü boşaltıldı.")


def _secenek(argv, ad):
    if ad in argv:
        i = argv.index(ad)
        if i + 1 < len(argv):
            deger = argv[i + 1]
            del argv[i:i + 2]
            return deger
        del argv[i]
    return None


def main():
    _gunluk_ac()
    try:
        _main()
    except Exception as e:  # beklenmeyen hata: günlüğe yaz, işi "hata" olarak bırak
        import traceback
        traceback.print_exc()
        try:
            _sebep_yaz("Beklenmeyen hata: " + str(e)[:120])
            if IS_NO:
                _durum_yaz("hata")
        except Exception:
            pass


def _main():
    global AKTAR, IS_NO
    argv = sys.argv[1:]
    is_no = _secenek(argv, "--is")
    aktar = _secenek(argv, "--aktar")
    devam = "--devam" in argv or "--tekrar" in argv
    urller = [a for a in argv if not a.startswith("--")]

    if is_no is not None and not re.fullmatch(r"\d{1,12}", is_no):
        print("HATA: geçersiz iş numarası")
        return

    if "--kur" in argv:
        print(guncelle(zorla=True))
        return

    if "--teslim" in argv:
        teslim(is_no)
        return
    if "--kaydedildi" in argv:
        kaydedildi()
        return

    if aktar is not None:
        if not os.path.isdir(aktar):
            print("HATA: aktarma klasörü bulunamadı:", aktar)
            return
        AKTAR = aktar

    try:
        if len(urller) != 1:
            raise ValueError("Tam olarak bir bağlantı verilmeli.")
        url = dogrula(urller[0])
    except ValueError as e:
        if not devam:
            IS_NO = is_no
            _sebep_yaz(str(e))
            print("HATA:", e)
        return

    if is_no is not None:
        _is_kur(is_no, url)

    if not devam:
        onceki = _durum_oku()
        yarim = (onceki in ("calisiyor", "devam") and os.path.exists(DURUM)
                 and time.time() - os.path.getmtime(DURUM) < ESKI_DOSYA)
        # İlk adım: yeni iş. "calisiyor" kalırsa (iOS süreci öldürdüyse) sonraki adım sürdürür.
        _durum_yaz("calisiyor")
        _sayi_yaz(0)
        if os.path.exists(GUNCELLENDI):
            os.remove(GUNCELLENDI)
        try:
            print(guncelle())
        except Exception as e:  # ağ yoksa eldeki sürümle devam et
            print("UYARI: güncelleme yapılamadı:", e)
        # Aynı video daha önce yarım kaldıysa baştan değil, kaldığı yerden sürdürülür
        temizle = not yarim
        if yarim:
            print("Bu video daha önce yarım kalmış; kaldığı yerden sürdürülüyor.")
    else:
        durum = _durum_oku()
        if durum in ("", "tamam"):
            return  # iş bitti; bu adımda yapılacak bir şey yok
        if durum == "hata":
            # Hatalar çoğu zaman geçicidir (Instagram'ın girişsiz isteğe boş yanıt vermesi,
            # ağ kopması). Önce doğrudan yeniden denenir; ikinci başarısızlıkta yt-dlp
            # zorla güncellenir (site değiştiyse düzeltme yeni sürümdedir); en fazla 3 deneme.
            try:
                with open(GUNCELLENDI, encoding="utf-8") as f:
                    deneme = int(f.read().strip() or 0)
            except (OSError, ValueError):
                deneme = 0
            if deneme >= 3:
                return  # yeterince denendi; sebep kayıtlı, kısayol bildirimde gösterir
            with open(GUNCELLENDI, "w", encoding="utf-8") as f:
                f.write(str(deneme + 1))
            if deneme == 1:
                print("İndirme yine başarısız; yt-dlp zorla güncellenip yeniden denenecek.")
                try:
                    print(guncelle(zorla=True))
                except Exception as e:
                    print("UYARI: güncelleme yapılamadı:", e)
            else:
                print(f"İndirme başarısız oldu; yeniden deneniyor ({deneme + 1}/3).")
                time.sleep(2)
            temizle = True
        else:
            print("Yarım kalan indirme sürdürülüyor.")
            temizle = False

    if not os.path.isfile(YTDLP):
        _durum_yaz("tamam")
        _sonuc("HATA: yt-dlp kurulu değil.")
        return

    durum, videolar = indir(url, temizle=temizle)
    _durum_yaz(durum)
    if durum == "tamam":
        _sonuc(f"BASARILI: {len(videolar)} video", len(videolar))
    elif durum == "hata":
        _sonuc("HATA: video indirilemedi (ayrıntılar yukarıda).")
    else:
        print("DEVAM: indirme sonraki adımda sürecek.")


if __name__ == "__main__":
    main()
