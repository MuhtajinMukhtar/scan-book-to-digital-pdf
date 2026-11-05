# Scan Book to Digital PDF

Ubah PDF buku hasil scan menjadi **PDF digital dengan teks nyata yang dapat dipilih, dicari, dan disalin**. Tetap jaga ilustrasi, tabel, ejaan, dan isi **pada halaman sumber masing-masing**.

## Untuk orang nonteknis

**Cukup unggah file PDF dan berikan link repo ini ke ChatGPT Work / Codex:**

https://github.com/MuhtajinMukhtar/scan-book-to-digital-pdf

AI akan membuat **contoh dua halaman terlebih dahulu**, menunjukkan perbandingannya dengan scan, lalu meminta persetujuan sebelum mengerjakan semua halaman. Anda tidak perlu memahami istilah OCR, font embedding atau command line.

## Alur utama sekarang

**Apple Vision menjadi pembaca teks utama.** Ini mengadopsi langkah yang berhasil pada eksperimen buku pertama di Mac. Hasil disimpan per halaman agar tidak perlu diproses ulang.

**PaddleOCR PP-OCRv5 Mobile hanya menjadi pemeriksa tambahan pada halaman yang terindikasi meragukan**, bukan pembaca kedua untuk seluruh buku. Jika model Mobile belum ada dan memang dibutuhkan, AI meminta izin terlebih dahulu untuk pemasangan/unduhannya.

- **Tidak menggunakan PP-StructureV3 otomatis.** PP-StructureV3 pernah menghabiskan memori besar dan crash dalam uji Work.
- **Tidak memakai Tesseract sebagai default.** Skrip historisnya tetap tersedia tetapi bukan alur utama.
- **Prioritas Mac 8 GB dan 16 GB:** pekerjaan bertahap, maksimum satu halaman Mobile per batch awal, pembatasan RAM/waktu, dan cache OCR. **Belum ada klaim bahwa semua Mac 8 GB pasti bisa menjalankan Mobile.**
- **Model ChatGPT ringan boleh dipakai** untuk mengoperasikan skrip. Tidak ada kebutuhan model High untuk membaca setiap halaman.

## Pengguna teknis / AI Agent

Baca [SKILL.md](SKILL.md) dan [panduan Mac](references/mac-setup.md). Sesudah setup dasar, jalankan:

```sh
python scripts/run_book.py pilot --source "/path/to/book.pdf" --work-dir ./work
```

Hasil awal: `work/pilot/Book_Pilot_REVIEW.pdf`, `Book_Pilot_Comparison.pdf`, `pilot-status.json`. Jika skor Apple Vision menyarankan pemeriksaan tambahan, lakukan itu **hanya setelah persetujuan untuk Mobile/install/model download**:

```sh
python scripts/run_book.py pilot --source "/path/to/book.pdf" --work-dir ./work --reuse-apple --enable-mobile --allow-model-download
```

Opsi `--reuse-apple` **tidak menjalankan ulang** halaman yang sudah dibaca Apple Vision. Jika model Mobile sudah di-cache, hapus opsi `--allow-model-download`.

Untuk perbaikan layout/font saja, tanpa OCR ulang sama sekali:

```sh
python scripts/run_book.py pilot --source "/path/to/book.pdf" --work-dir ./work --skip-ocr
```

**Hanya setelah contoh digital disetujui pengguna:**

```sh
python scripts/run_book.py approve --source "/path/to/book.pdf" --work-dir ./work --confirm APPROVE_PILOT
python scripts/run_book.py full --source "/path/to/book.pdf" --work-dir ./work
```

## Penyempurnaan tipografi pilot

Mesin PDF sekarang merapikan **jarak antarbaris dalam paragraf**, menstabilkan posisi kiri baris lanjutan sambil menghormati margin bolak-balik buku, dan mencoba menjadikan **nomor halaman** sebagai teks digital yang dapat dipilih.

**Cetak miring tidak dapat dipastikan hanya dari OCR Apple Vision.** Agen harus membandingkan scan asli dengan PDF contoh, lalu mencatat frasa miring yang benar-benar terlihat di sumber dalam `work/style-annotations.json`. Contoh dan aturannya ada di [review tipografi](references/typography-and-style-review.md). Perbaikannya dirender ulang memakai cache dengan `--skip-ocr`, **bukan** mengulang OCR atau memanggil PaddleOCR lagi.

Jika buku memuat tabel maupun ilustrasi, tampilkan masing-masing contoh sebelum approval buku penuh. **Halaman yang masih berupa scan fallback wajib diberi tahu**, bukan diklaim sebagai halaman digital yang telah ditata ulang.

## Kualitas dan keterbatasan

Skrip otomatis saat ini menata ulang **teks biasa** dengan tipografi terkontrol. Halaman bergambar, tabel, banyak cetak miring, atau teks yang belum terverifikasi **bisa tetap memakai scan asli yang searchable** dan harus ditandai untuk review. Hasil belum tentu setara dengan pilot manual yang dulu dipoles oleh agen High.

**Aturan wajib:** PDF sumber dan hasil mempunyai jumlah serta ukuran halaman yang sama. Tidak boleh ada paragraf atau gambar yang diam-diam meluber ke halaman berikut. Untuk buku penuh, setiap halaman harus diverifikasi terhadap sumber menggunakan [audit per halaman](references/page-fidelity.md). Laporan otomatis bukan jaminan karakter demi karakter.

## Tes

```sh
pip install -r requirements.txt
python -m unittest discover -s tests -v
```

CI menjalankan **tes sintetis** tanpa mengunduh model Paddle dan tanpa memakai data buku pengguna. Sebelum menyatakan siap dipakai luas, uji langsung **Apple Vision + PaddleOCR Mobile pada Mac M2 8 GB** beserta RAM, waktu, dan mutu halaman.

Repository tidak berisi file buku berhak cipta, cache OCR pengguna, atau font berlisensi. Lisensi kode: [MIT](LICENSE).
