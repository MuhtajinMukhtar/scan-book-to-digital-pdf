# Scan Book to Digital PDF

## Mulai dari chat Work baru — jangan terjebak laporan lama

**Jika pengguna hanya mengirim PDF + link repo ini, gunakan aturan terkini di [SKILL.md](SKILL.md), bukan menganggap catatan proses lama sebagai kondisi saat ini.** Periksa versi `main` dan SHA PDF sumber. Laporan `PILOT_INCOMPLETE` dari percobaan terdahulu adalah riwayat, bukan bukti bahwa alur Apple Vision saat ini gagal. Untuk uji blind, jangan membuka hasil pilot, percakapan, atau checkpoint editorial lama.

**Alur default langsung:** di **Mac** yang tersedia, gunakan Apple Vision untuk **smoke test internal 2 halaman**, lanjutkan pilot **6–8 halaman dengan jenis layout berbeda**, lalu minta persetujuan. Gunakan cache OCR lama **hanya jika benar-benar ada dan SHA sumber cocok**. Jika cache lama tidak cocok, ulang **hanya halaman pilot** menggunakan Apple Vision — bukan PP-StructureV3. PaddleOCR Mobile opsional untuk halaman meragukan, dengan izin instalasi/unduhan.

**Jangan menawarkan Ubuntu sebagai alternatif untuk Apple Vision**, jangan mengulang PP-StructureV3 yang pernah crash, dan jangan meminta pilihan teknis seperti "OCR di Ubuntu atau Apple saja?" bila Mac tersedia. Berhenti dan jelaskan kendala hanya jika pemeriksaan **lingkungan Mac saat ini** menunjukkan masalah nyata. Riwayat crash di proses lama tidak otomatis berarti lingkungan Mac sekarang tidak layak.

Mesin tipografi menggunakan versi saat ini di `main`. **Nilai hasil pilot baru berdasarkan PDF sumber terlebih dahulu**, tanpa mencari acuan hasil lama saat uji blind.

Ubah PDF buku hasil scan menjadi **PDF digital dengan teks nyata yang dapat dipilih, dicari, dan disalin**. Tetap jaga ilustrasi, tabel, ejaan, dan isi **pada halaman sumber masing-masing**.

## Uji blind adalah alur default

**Cukup berikan PDF sumber dan tautan repo.** Agen harus memilih halaman contoh, font, margin, dan tipografi dari **PDF sumber itu sendiri**, bukan dari pilot pekerjaan sebelumnya. Tidak perlu melampirkan PDF hasil lama, meminta pengguna mengingat setelan teknis, atau membaca catatan dari chat sebelumnya.

Pengujian tetap berjalan bertahap: **2 halaman uji teknis internal → pilot 6–8 halaman yang benar-benar beragam → persetujuan pengguna**. Cache OCR mentah hanya boleh dipakai bila checksum sumbernya identik. Agen tidak boleh melihat versi/benchmark historis atau cabang arsip demi meniru hasil lama saat uji blind.

Setelah hasil blind selesai, jika pengguna ingin mengukur kemunduran kualitas terhadap pilot yang pernah disukai, `scripts/visual_regression_gate.py` tersedia sebagai **alat evaluasi opsional** menggunakan baseline yang secara terpisah diberikan pengguna. Perbandingan ini tidak dilakukan otomatis.

## Untuk orang nonteknis

**Cukup unggah file PDF dan berikan link repo ini ke ChatGPT Work / Codex:**

https://github.com/MuhtajinMukhtar/scan-book-to-digital-pdf

AI melakukan **uji internal 2 halaman**, lalu menyiapkan **pilot 6–8 halaman yang berbeda karakter** dari bagian buku yang berlainan, baru meminta persetujuan untuk seluruh buku. Contoh dapat mencakup teks biasa, judul bab, kutipan/cetak miring, foto/ilustrasi, tabel/formulir, dan profil—**jika memang ada pada sumber**. Pengguna tidak perlu memilih halaman atau memahami OCR.

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

Hasil ini **hanya smoke test internal**, bukan pilot yang boleh di-approve. Agen kemudian memilih dan memproses sumber yang lebih beragam secara bertahap:

```sh
python scripts/run_book.py pilot --stage review --source "/path/to/book.pdf" --work-dir ./work
```

Lihat `work/pilot/Source_Review_Candidates.pdf` dan `review-selection.json`, periksa bahwa **jenis halaman memang berbeda dan mewakili pola yang berulang**. Kategori yang diprediksi dari thumbnail adalah kandidat, bukan bukti; agen harus memeriksa gambarnya. Jika kurang tepat, agen dapat mengganti dengan `--pages` berisi nomor halaman fisik PDF. OCR yang sudah disimpan tidak diproses ulang.

Hasil yang ditinjau: `work/pilot/Book_Pilot_REVIEW.pdf`, `Book_Pilot_Comparison.pdf`, `pilot-status.json`. Jika skor Apple Vision menyarankan pemeriksaan tambahan, lakukan itu **hanya setelah persetujuan untuk Mobile/install/model download**:

```sh
python scripts/run_book.py pilot --source "/path/to/book.pdf" --work-dir ./work --reuse-apple --enable-mobile --allow-model-download
```

Opsi `--reuse-apple` **tidak menjalankan ulang** halaman yang sudah dibaca Apple Vision. Jika model Mobile sudah di-cache, hapus opsi `--allow-model-download`.

Untuk memperbaiki layout/font **tanpa mengulang OCR**, gunakan cache yang valid. **Nomor halaman berikut hanya contoh sintaks, jangan digunakan sebagai pilihan otomatis dalam uji blind:**

```sh
python scripts/run_book.py pilot --stage review --pages 5,19,32,47,63,80,95 --source "/path/to/book.pdf" --work-dir ./work --skip-ocr
```

Pastikan cache Apple Vision untuk halaman tersebut benar-benar ada dan cocok dengan SHA-256 PDF sumber. Jika buku atau nomor sampelnya berbeda, sesuaikan `--pages`. **Persetujuan pilot dari versi layout sebelumnya harus diperbarui**, jangan otomatis memproses seluruh buku.

**Hanya setelah pilot 6–8 halaman yang mewakili berbagai jenis layout disetujui pengguna:**

```sh
python scripts/run_book.py approve --source "/path/to/book.pdf" --work-dir ./work --confirm APPROVE_PILOT
python scripts/run_book.py full --source "/path/to/book.pdf" --work-dir ./work
```

## Tipografi pilot dan rollback kualitas visual

**Baseline saat ini adalah mesin tipografi sebelum percobaan perataan dan jarak baris global 6 November 2026.** Percobaan tersebut di-rollback karena hasil PDF pilot terbaru justru memburuk. Mesin tetap mencoba merapikan jarak baris **di dalam masing-masing paragraf**, mempertahankan margin sumber, dan menjadikan nomor halaman sebagai teks digital bila memungkinkan. **Bukan berarti masalah jarak baris/indentasi sudah tuntas pada semua buku.**

**Aturan terpenting untuk revisi setelah uji blind:** bila pengguna secara eksplisit memilih pilot yang lebih bagus, gunakan pilot pilihan itu sebagai acuan visual. Jangan mengecilkan huruf, memadatkan paragraf, menggeser ilustrasi, atau merancang ulang seluruh halaman hanya untuk memperbaiki satu baris. Ubah hanya elemen yang terbukti salah; periksa perbandingan sebelum/sesudah, dan tolak revisi jika hasil visual menurun.

**Rollback kode GitHub tidak otomatis mengembalikan PDF yang telah dibuat di sesi ChatGPT Work.** Simpan/rujuk versi PDF pilot yang lebih disukai, lalu render ulang hanya halaman terkait dengan cache OCR yang masih tersedia. Jika cache tidak tersedia di sesi baru, jangan mengaku cache telah digunakan.

**Cetak miring tidak dapat dipastikan hanya dari OCR Apple Vision.** Agen harus membandingkan scan asli dengan PDF contoh, lalu mencatat frasa miring yang benar-benar terlihat di sumber dalam `work/style-annotations.json`. Contoh dan aturannya ada di [review tipografi](references/typography-and-style-review.md). Perbaikannya dirender ulang memakai cache dengan `--skip-ocr`, **bukan** mengulang OCR atau memanggil PaddleOCR lagi.

Jika buku memuat tabel maupun ilustrasi, tampilkan masing-masing contoh sebelum approval buku penuh. **Halaman yang masih berupa scan fallback wajib diberi tahu**, bukan diklaim sebagai halaman digital yang telah ditata ulang.

## Kebijakan: semua halaman teks wajib digital, kecuali cover

**Semua halaman yang mengandung teks wajib ditata ulang menjadi teks PDF yang benar-benar digital.** Termasuk teks di dalam tabel, kutipan, judul bab, footer, dan teks di samping ilustrasi. Foto, gambar dan ornamen boleh dipertahankan sebagai aset visual, bukan sebagai scan seluruh halaman.

**Hanya cover depan/belakang yang telah diperiksa dari sumber asli** boleh tetap gambar satu halaman penuh. AI mencatat pengecualiannya di `work/cover-evidence.json` tanpa meminta pengguna mengetik konfigurasi teknis. Jika tidak ada bukti pemeriksaan cover, halaman tersebut tidak otomatis dikecualikan.

Setelah pemrosesan, program menjalankan pemeriksaan di [aturan digitalisasi wajib](references/digital-text-policy.md). Bila ada halaman non-cover yang masih berupa scan, status hasil adalah **`INCOMPLETE_DIGITAL_PAGES`**, dengan daftar nomor halaman yang perlu diperbaiki. Buku **belum dianggap selesai**, meskipun dokumen review tetap disimpan.

**Catatan:** pengamanan ini belum berarti mesin sudah mampu merekonstruksi semua tabel dan layout bergambar secara otomatis. Kualitas itu harus dibuktikan melalui pilot dan pemeriksaan sumber, bukan dijanjikan hanya karena aturan dibuat.

## Kualitas dan keterbatasan

Skrip otomatis saat ini menata ulang **teks biasa** dengan tipografi terkontrol. Halaman bergambar, tabel, banyak cetak miring, atau teks yang belum terverifikasi **bisa tetap memakai scan asli yang searchable** dan harus ditandai untuk review. **Scan fallback adalah hasil sementara, bukan contoh digital yang boleh disetujui sebagai dasar konversi seluruh buku.** Jika satu saja halaman pilot masih fallback, statusnya `PILOT_NEEDS_LAYOUT_WORK` dan `approve` ditolak. Gambar/foto sumber boleh tetap berupa gambar, tetapi teks di sekitarnya dan sel tabel harus direkonstruksi secara digital sebelum approval. Hasil belum tentu setara dengan pilot manual yang dulu dipoles oleh agen High.

**Aturan wajib:** PDF sumber dan hasil mempunyai jumlah serta ukuran halaman yang sama. Tidak boleh ada paragraf atau gambar yang diam-diam meluber ke halaman berikut. Untuk buku penuh, setiap halaman harus diverifikasi terhadap sumber menggunakan [audit per halaman](references/page-fidelity.md). Laporan otomatis bukan jaminan karakter demi karakter.

## Tes

```sh
pip install -r requirements.txt
python -m unittest discover -s tests -v
```

CI menjalankan **tes sintetis** tanpa mengunduh model Paddle dan tanpa memakai data buku pengguna. Sebelum menyatakan siap dipakai luas, uji langsung **Apple Vision + PaddleOCR Mobile pada Mac M2 8 GB** beserta RAM, waktu, dan mutu halaman.

Repository tidak berisi file buku berhak cipta, cache OCR pengguna, atau font berlisensi. Lisensi kode: [MIT](LICENSE).
