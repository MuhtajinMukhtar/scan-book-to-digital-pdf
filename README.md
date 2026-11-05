# Scan Book to Digital PDF

Ubah PDF hasil scan menjadi **buku digital yang teksnya bisa dipilih, disalin, dan dicari**. Buku sumber tidak diubah.

## Untuk pengguna ChatGPT Work (tanpa pengetahuan teknis)

**Cukup unggah PDF dan kirim link repo ini:**
https://github.com/MuhtajinMukhtar/scan-book-to-digital-pdf

AI akan mengikuti `SKILL.md`, membuat **pilot dua halaman** terlebih dahulu, lalu meminta persetujuan sebelum memproses seluruh buku. Jika ada komponen yang perlu dipasang di Mac, AI meminta izin dalam bahasa sederhana. Pengguna tidak harus memilih mesin OCR atau mengetik perintah.

**Jangan menyetujui pilot yang hanya menampilkan scan asli dengan teks tersembunyi.** Harus ada contoh dengan teks digital yang benar-benar terlihat dan tata letak yang diperiksa.

## Perubahan penting: hemat sumber daya

Pengujian pada Mac menunjukkan **PP-StructureV3 (PaddleOCR) menghabiskan memori besar dan mengalami segmentation fault**. Karena itu versi terbaru tidak lagi menjalankan PP-StructureV3 secara otomatis.

**Alur aman sekarang: Apple Vision + Tesseract** pada Mac. Tesseract adalah pembanding OCR yang lebih sederhana; **kualitasnya belum terbukti setara dengan hasil Apple Vision + PaddleOCR sebelumnya**. Halaman dengan perbedaan teks atau tata letak sulit tetap perlu diperiksa terhadap gambar scan.

Pekerjaan utama dijalankan skrip lokal, **tidak perlu model High** untuk setiap halaman. Jika mesin OCR yang aman tidak tersedia, AI harus berhenti tanpa mengulang metode yang sudah crash atau memindahkan pekerjaan ke Ubuntu yang lebih sempit memorinya.

## Untuk AI Agent / pengguna teknis

Baca [SKILL.md](SKILL.md) dan [setup Mac](references/mac-setup.md). Perintah dasar:

```sh
python scripts/run_book.py pilot --source "/path/to/scan-buku.pdf" --work-dir ./work
```

Output pilot: `work/pilot/Book_Pilot_REVIEW.pdf` dan `work/pilot/Book_Pilot_Comparison.pdf`. OCR akan disimpan pada `work/ocr/` (Apple Vision), `work/tesseract/`, dan `work/fusion_safe/` (perbandingan). Untuk menyusun ulang PDF contoh tanpa OCR ulang:

```sh
python scripts/run_book.py pilot --source "/path/to/scan-buku.pdf" --work-dir ./work --skip-ocr
```

**Hanya setelah user menyetujui PDF pilot yang nyata:**

```sh
python scripts/run_book.py approve --source "/path/to/scan-buku.pdf" --work-dir ./work --confirm APPROVE_PILOT
python scripts/run_book.py full --source "/path/to/scan-buku.pdf" --work-dir ./work
```

Versi sekarang adalah **mesin otomatis tahap awal**. Teks normal dapat ditata ulang dengan font konsisten; halaman bergambar, tabel, tipografi rumit, atau OCR yang tidak pasti mungkin tetap memakai scan asli dengan lapisan teks untuk dicari, diberi label `searchable_scan_fallback`. Mesin belum otomatis meniru semua cetak miring, indentasi dan elemen dekoratif seperti contoh hasil editorial manual sebelumnya.

**Aturan mutu:** jumlah halaman harus identik; halaman sumber N harus tetap menjadi halaman hasil N tanpa isi hilang atau meluber. Laporan mesin bukan bukti mutlak: verifikasi tiap halaman, periksa sumber, dan terapkan [audit page fidelity](references/page-fidelity.md).

## Pengujian

```sh
pip install -r requirements.txt
python -m unittest discover -s tests -v
```

Tes otomatis memakai data sintetis, bukan uji nyata Apple Silicon. Sampai uji Mac berhasil, jangan menjanjikan pemrosesan 220 halaman otomatis atau penghematan kuota yang terukur.

**Privasi dan hak cipta:** jangan unggah scan buku, cache OCR, foto pribadi, atau font berlisensi ke repository publik. Lisensi kode: [MIT](LICENSE).
