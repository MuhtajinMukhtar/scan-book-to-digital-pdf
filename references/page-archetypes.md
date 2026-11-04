# Page archetypes and source-aware styling

Use these patterns after checking the actual source-page raster at a readable zoom. Physical PDF page number is **not** the page number printed in the book's footer.

| Archetype | Digital treatment | Preserve from image |
|---|---|---|
| Cover / title page | Digitize readable large text at source-like sizes if user requests; otherwise original searchable scan, explicitly logged | Cover design, original illustrations |
| Body | Serif 13–14pt by user preference, 18–21pt leading, justified with last line left, accurate paragraph breaks and indents | Photos and diagrams only |
| Heading / subheading | One semantic heading even if source wraps over 2–3 physical lines; size/weight/source serif-vs-sans | Decorative images |
| Chapter opener | Digital label and large heading, controlled vertical placement; insert isolated transparent logo crop | Original brand/logo artwork |
| Quotations / takeaways | Digital serif italic or source-style sans; maintain background tint, centered alignment where sourced and decorative opening quote as Unicode/vector | Artwork/photos only; avoid scanning text |
| Reflection | Title + one uninterrupted italic quote box; confirm the last line is **inside** that box | Quotation ornament where source-faithful |
| TOC / bibliography | Selectable lines, indentation and page reference alignment, correct section titles | Small embellishments if needed |
| Checklist / diagnostic | Vector checkboxes and labels with generous spacing, visible scoring instructions; mark as non-interactive unless actual PDF fields created | Diagrams/photos |
| TRUST / other acronym diagram | Render letters and descriptions as text in appropriate lanes and colors | Branding or truly non-text visuals |
| Photo testimonial | Keep original photo and crop/transparent mask; place all testimonial text digitally | Full photo content, subject's headroom |
| Contact/social | One digital line per account/address, correct punctuation and spacing | Logos/icons if sourced |
| Full-bleed complex graphic | Retain original scan with hidden selectable OCR only if digital reconstruction is unsafe; log fallback | Entire diagram/graphic |

## OCR/layout pitfalls from past scanned-book work

1. A large source quotation glyph can be read as `66`, `99`, or stray Arabic digits. Inspect the source before changing text. Replace *only* a source-verified glyph, not legitimate numerals.
2. A page's hidden footer may be counted by a naïve HTML text-coverage extractor. Exclude **only** verified hidden/duplicated footer layers from QA; never exempt body content.
3. Wrapped chapter titles may appear as unrelated OCR paragraphs; combine into a single styled heading without deleting words.
4. A reflection's last line may be detached from its italic quotation; reconstruct from the source line order and verify quote continuity, punctuation and original wording.
5. Original italic English terms need source visual confirmation. Do not italicize every English phrase automatically.
6. Mac font fallback for `→` may be a different font even when body letters use embedded Georgia; whitelist **exact glyphs and exact pages**, not all substitutions. A Cyrillic/Arabic fallback for supposed Latin title digits is probably an OCR error requiring source inspection.
7. Page images sometimes hide logos, arrows, photos and form boxes. Identify/crop from source before deleting the scanned background.
8. OCR text may contain nonsense page numbers, `×vii`, fictitious footer words, and misread quotation marks. Preserve a change log and require source evidence per correction.

## Image extraction notes

- A scanned PDF may contain one large full-page raster rather than isolated photo objects. Reconstruct source imagery by cropping the original page image **at original effective resolution**, never by screenshot of the digital result.
- When separating a monochrome/logo graphic from paper, validate alpha transparency and glyph edges; avoid grey halos, distortion or changing artwork.
- Do not upscale low-resolution images merely to fill the page. Test selected pages at the reader's likely zoom level.
- Preserve semantic image count and visual presence, not necessarily the same PDF object count (cropped logos can legitimately become separate objects).

## Practical source-to-output sample

For each unusual page: `original_page.png`, `ocr/page_###.json`, `page_###.html`, `page_###.pdf`, side-by-side render (source/new), and a manifest record with `status`, `source_verified_corrections`, `font_assertions`, `qa_pass`. Keep all assets under the active project, not in the shared skill bundle.
