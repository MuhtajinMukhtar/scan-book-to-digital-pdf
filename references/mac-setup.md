# Setup Mac yang ringan (untuk AI Agent, bukan pengguna nonteknis)

## Tujuan

Menggunakan **Apple Vision + Tesseract** untuk membandingkan hasil pengenalan teks tanpa PP-StructureV3. Pipeline yang lama berhasil pada eksperimen lain tetapi pernah mencapai penggunaan RAM sekitar 15 GB dan mengalami **segmentation fault** saat dicoba kembali di Mac. Jangan mengulang crash atau memindahkan beban berat itu ke Ubuntu kecil.

## Prasyarat

- macOS dan `swiftc` (Xcode Command Line Tools) untuk Apple Vision.
- Python 3.10+ di virtual environment yang diizinkan. `pip install -r requirements.txt` berisi PyMuPDF dan Pillow saja.
- `tesseract` CLI, serta paket bahasa `eng` dan `ind`. Periksa `tesseract --list-langs`. Tidak boleh diam-diam memakai bahasa Inggris saja untuk buku Bahasa Indonesia.
- Jika perlu instalasi, **minta izin pengguna terlebih dahulu**. Untuk Mac yang memakai Homebrew, paket resminya tersedia melalui `brew install tesseract tesseract-lang`. Jangan mengubah global Python atau memasang model PaddlePaddle demi menjalankan pilot aman.

Referensi:
- https://formulae.brew.sh/formula/tesseract
- https://formulae.brew.sh/formula/tesseract-lang
- https://tesseract-ocr.github.io/tessdoc/Installation.html

## Penggunaan

Cek dulu bahwa PDF sumber, Mac, ruang disk, RAM, dan versi Python sesuai. Setelah dependensi tersedia:

```sh
python scripts/run_book.py pilot --source "buku.pdf" --work-dir ./work
```

Program memilih dua halaman teks dari thumbnail, menggunakan Apple Vision dan Tesseract di halaman itu saja, memakai cache untuk menghindari pemrosesan ulang, dan membuat contoh PDF digital. Secara default DPI dibatasi 180 dan jumlah thread library OCR 2 (tidak mengubah pengaturan sistem).

Jika cache Apple Vision dari sesi sebelumnya tersedia pada folder `work/ocr`, **jangan hapus**. Pembanding Tesseract disimpan terpisah pada `work/tesseract`; perbandingan berada di `work/fusion_safe`. Berkas lawas PaddleOCR tidak ditimpa.

**Hanya setelah menyetujui contoh** agen boleh mencatat persetujuan lalu memulai seluruh buku. Kecepatan/kualitas masih harus diuji pada Mac nyata. Keluaran tetap REVIEW, bukan FINAL.

## Jika mesin tidak tersedia atau gagal

- `tesseract` tidak tersedia / bahasa `ind` belum terpasang: berhenti aman, tampilkan satu langkah meminta izin instalasi; jangan memaksa Apple Vision saja sambil melabeli hasil "dual OCR".
- `swiftc` tidak tersedia: minta izin menyiapkan Apple Command Line Tools atau laporkan batasan; jangan mengaku memakai Apple Vision di Linux.
- Mac mulai panas/lambat, atau Work/Codex kuota terkuras: hentikan batch, simpan cache, jangan ulang OCR.
- Segmentation fault atau penggunaan RAM besar oleh PaddlePaddle: **jangan coba lagi pipeline tersebut**. PP-StructureV3 hanya eksperimen opsional, dengan `--ack-heavy-ppstructure` untuk lingkungan yang sudah diuji terpisah. Kinerja PaddleOCR tidak dapat diasumsikan sama dengan Tesseract.

Skrip dan status hasil harus memberi bukti mesin yang benar-benar digunakan; jangan mengarang proses yang tidak dijalankan.
