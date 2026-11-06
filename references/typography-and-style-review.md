# Source-faithful pilot typography: margins, paragraph rhythm, italics and footer

For the AI agent. The user should only see the PDF pilot and approve or request revisions.

## What the engine can do now

- Keep all text on the **same physical source page** with source page dimensions unchanged.
- Group consecutive OCR lines into paragraphs and regularize baseline spacing within a paragraph instead of repeating OCR y-coordinate jitter.
- Stabilize continuation lines' left edge while preserving intentional **mirrored gutters** on facing pages.
- Detect **left-aligned/ragged right versus justified** body text from source OCR geometry and visually verify in the scan. Apply justify **only** for source-justified prose; cap word-space stretching and keep paragraph-final lines natural. If detection is uncertain, use natural spacing until verified. Never silently shrink or overflow text.
- Attempt an unambiguous **printed page number** as visible/selectable text. Preserve footer ornament from the source and flag `footer_number_still_raster_review_needed` when replacing the number is unsafe.
- Render **source-verified bold and italic spans**. OCR confidence alone does not reliably identify typeface weight/style; verify these details visually from the scan instead of guessing.
- Keep word spaces normal (including accidental multi-space OCR artifacts), stabilize ordinary body margins from several source pages, and normalize only small baseline/paragraph-gap jitter. Preserve genuine indentations, centered quotations and decorative layouts.
- **Default background:** uniform very pale warm cream on normal digital pages. Preserve special page artwork and panel colors. An optional white-paper version is offered only **after** the main book has been produced and checked, not during pilot selection.

## Konsistensi mengikuti buku sumber, bukan contoh buku tertentu

Gaya isi buku diperkirakan dari beberapa **halaman paragraf biasa** dan dikunci di `work/pilot/style-profile.json` bersama SHA-256 PDF sumber. Jika buku sumber rata kiri, baris akhir tidak dipaksa menjadi rata kanan. Jika sumber justify, tambahkan spasi hanya secukupnya agar tetap nyaman dibaca; jangan memaksakan pelebaran berlebihan untuk mencapai margin kanan.

Margin kiri/kanan, leading dan jarak antarparagraf mengikuti pola dominan halaman biasa, tetapi tidak mengubah desain khusus. Normalisasi posisi dibatasi kecil untuk menghindari kemunduran visual akibat pemadatan global. **Pemrosesan tetap tidak boleh memindahkan isi ke halaman berikutnya.**

Jika geometri OCR tidak cukup untuk menyimpulkan gaya (profil bertanda `source_uncertain`), agen memeriksa PDF sumber dan boleh mencatat pilihan terverifikasi di `work/book-style-override.json`:

~~~json
{
  "source_sha256": "<actual SHA-256 of current source>",
  "source_scan_verified": true,
  "alignment": "justify"
}
~~~

Nilai `alignment` bisa `left` atau `justify` sesuai buku. Margin/spasi juga dapat dikunci secara opsional setelah pemeriksaan visual. **Jangan membuat override berdasarkan kebiasaan model atau gaya buku sebelumnya.** Render ulang pilot dengan `--skip-ocr`, kemudian minta approval atas PDF hasil baru. Setelah disetujui, perubahan override membatalkan izin pemrosesan buku penuh.

Versi putih bersih adalah **varian opsional setelah buku krem berhasil dan lolos QA**, hanya jika pengguna memilihnya. Jalur agen: `python scripts/run_book.py full --source BOOK.pdf --work-dir ./work --skip-ocr --white-variant`. Teks dan geometry harus tetap sama; periksa kembali footer sumber karena ornamen raster bisa masih berwarna krem. Jangan jalankan dua OCR atau mengubah layout hanya untuk berganti warna.

## Source-verified bold and italic spans

Only after comparing the actual source scan with the pilot, create `work/style-annotations.json`, if necessary:

~~~json
{
  "source_sha256": "<actual SHA-256 of original scanned PDF>",
  "pages": {
    "12": {
      "italic_spans": [
        {"text": "Example emphasized phrase", "source_scan_verified": true}
      ],
      "bold_spans": [
        {"text": "Example chapter heading", "source_scan_verified": true}
      ]
    }
  }
}
~~~

Page 12 and the sample phrase are fictional syntax examples. **Never copy these annotations into a real book without inspecting its source.** The exact phrase must appear in the OCR of that physical page. The agent should identify formatting from the source sample, add entries only when supported, and seek review if ambiguous.

Rerender without OCR:

~~~sh
python scripts/run_book.py pilot --stage review --source BOOK.pdf --work-dir ./work --skip-ocr
~~~

The pilot profile locks the annotation file SHA. Changing annotations after approval blocks full-book processing until a revised pilot is approved. If a matching local italic font isn't available, report the exception instead of silently stripping emphasis.

## Images, tables, and footer examples

The deterministic engine **still cannot fully reconstruct complex tables and illustration pages**. It can preserve a page as a searchable original scan while retaining its page identity; this is a disclosed exception, not a fully digital page. If the source includes tables or illustrations, show representative pages of each category in the pilot before seeking all-book approval.

For page numbers, review odd/even positioning, the original paper color and footer ornament. If the QA report flags a footer still raster, report it. Do not claim the whole footer is digital merely because the body is selectable.

## Editorial acceptance

Inspect actual PDF output and source side-by-side:
- Uniform leading within the same paragraph; correct gap between paragraphs
- Source-like mirrored margins, no text shift to a neighboring page
- Printed italic and other emphasis present when source supports it
- Numeric footer text reconstructed or flagged; graphics and tables preserved/rebuilt transparently
- Identical physical page count, order, dimensions and same-page text

A code test is not a substitute for reviewing the actual book scan.
