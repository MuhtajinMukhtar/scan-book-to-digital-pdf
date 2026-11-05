# Scan Book to Digital PDF

Ubah **PDF buku hasil scan** menjadi buku digital yang lebih nyaman dibaca. Teks bisa dicari dan disalin; foto, tabel, dan gambar tetap diperhatikan.

## Cara pakai di ChatGPT Work

**1.** Lampirkan PDF buku Anda.

**2.** Salin kalimat ini:

> **Tolong ubah PDF buku ini menjadi buku digital yang nyaman dibaca. Ikuti panduan https://github.com/MuhtajinMukhtar/scan-book-to-digital-pdf dan bimbing saya dengan pilihan sederhana.**

**3.** AI membuat **contoh 5–8 halaman** dengan berbagai bentuk halaman dalam buku, dengan jenis, ukuran, dan gaya tulisan semirip mungkin dengan sumber. Anda boleh menjawab **"ikuti aslinya saja"** untuk pengaturan huruf.

**4.** Lihat PDF contoh dan jawab **"Cocok, lanjutkan"** atau **"Perbaiki bagian ini"**. **AI baru mengerjakan seluruh halaman setelah contoh disetujui.**

Anda tidak perlu memahami istilah OCR, PaddleOCR, program, atau terminal.

## Bagaimana AI memproses buku?

Di Mac, alur yang disarankan memakai **Apple Vision + PaddleOCR PP-StructureV3**. Keduanya membaca halaman yang sama, kemudian AI membandingkan hasilnya dengan gambar asli dan memeriksa bagian yang hilang atau salah. Hasil perbandingan tidak otomatis dianggap benar: nama orang, kata sulit, tabel dan halaman bergambar tetap harus diperiksa. PDF asli tidak boleh ditimpa.

**Aturan wajib:** jika sumber punya 197 halaman, hasil juga harus **197 halaman**. Isi dari halaman 27 harus tetap di halaman 27, tidak boleh hilang atau meluber ke halaman 28. AI memeriksa pasangan halaman satu per satu; bila ada halaman yang tidak muat dalam format yang disetujui, halaman itu dipertahankan sebagai scan asli yang tetap bisa dicari/disalin, ditandai untuk review, **bukan** memindahkan isi ke halaman berikutnya. Pemeriksaan otomatis tetap memerlukan pengecekan visual karena OCR bisa salah. Lihat [aturan kesetiaan setiap halaman](references/page-fidelity.md).

**Tahap wajib:** pilih beberapa halaman dari bagian berbeda, bangun aturan huruf/ukuran/spasi/indentasi yang konsisten, buat PDF contoh, minta persetujuan, lalu gunakan aturan yang sudah disepakati untuk seluruh buku. Hasilnya tetap diperiksa halaman demi halaman. Panduan detail: [pilot dan konsistensi gaya](references/pilot-and-style-lock.md).

Program dalam repo menyiapkan OCR gabungan dan laporan pemeriksaan; **menata ulang setiap jenis halaman buku masih membutuhkan kerja editorial oleh AI**. Jadi kualitas setara sebuah hasil buku yang pernah dikerjakan tetap harus diuji pada buku baru, bukan dijanjikan tanpa pemeriksaan.

## Untuk AI agent / pengguna teknis

Mulai dari [`SKILL.md`](SKILL.md). Setup yang aman untuk Mac ada di [`references/mac-setup.md`](references/mac-setup.md). Jalankan OCR gabungan **hanya untuk halaman percontohan terlebih dahulu** sesudah instalasi di lingkungan terpisah (halaman berikut hanya contoh; AI memilih sendiri yang paling mewakili isi buku):

```sh
python scripts/mac_hybrid_ocr.py /path/to/book.pdf --work-dir ./work --start-page 1 --end-page 5
```

Hasil utama ada di `work/ocr/` (Apple Vision), `work/paddle/` (hasil mentah dan Markdown PaddleOCR), dan `work/fusion/OCR_REVIEW.json` (bagian yang perlu diverifikasi). Proses dapat dilanjutkan per halaman; tidak perlu mengulang cache yang sudah valid.

Untuk memeriksa hasil yang ada tanpa menjalankan ulang OCR:

```sh
python scripts/mac_hybrid_ocr.py --work-dir ./work --compare-only
```

**Jangan menjalankan seluruh buku sebelum pengguna menyetujui contoh PDF.** Sesudah persetujuan, agen melanjutkan OCR dan rekontruksi seluruh halaman dengan gaya tulisan yang dikunci dari pilot. Setelah agen merekonstruksi dan menghasilkan PDF digital, **wajib** gunakan `scripts/page_fidelity_audit.py` untuk membandingkan **setiap halaman sumber dengan halaman hasil bernomor sama**, berdasarkan teks referensi yang sudah dicek terhadap Apple Vision, PaddleOCR, dan scan asli, lalu `scripts/pdf_audit.py`, pemeriksaan visual terhadap scan, serta manifest per halaman. File PDF hasil tetap berstatus **REVIEW** sampai disetujui.

**Tanggung jawab:** Pastikan Anda berhak memproses buku. Jangan mengunggah salinan buku berhak cipta, dokumen pribadi, cache OCR buku, atau berkas font berlisensi ke repo publik. Repo ini menyediakan kode dan panduan, bukan berkas buku.

## Pengujian

```sh
python -m unittest discover -s tests -v
```

Uji otomatis memakai data sintetis untuk logika penggabungan OCR. **Pengujian OCR aktual pada Mac M1/PP-StructureV3 serta kualitas PDF buku lain masih perlu dilakukan.**

Lisensi kode: [MIT](LICENSE).
