# G01 PowerPoint/WPS manual QA

Open every deck below once in Microsoft PowerPoint 16.0 build 20228 and once in WPS Presentation 12.1.0.28043. Each deck contains three slides.

| Case                 | Manual focus                                    | Deck                                                                            |
| -------------------- | ----------------------------------------------- | ------------------------------------------------------------------------------- |
| 01 Chinese overview  | Chinese glyphs and basic layout                 | [deck.pptx](../../tests/golden/01-zh-overview/generated/render/deck.pptx)       |
| 02 English market    | English layout and spacing                      | [deck.pptx](../../tests/golden/02-en-market/generated/render/deck.pptx)         |
| 03 Long title        | Title wrapping, clipping and editability        | [deck.pptx](../../tests/golden/03-long-title/generated/render/deck.pptx)        |
| 04 Table source      | Parsed table case renders normally              | [deck.pptx](../../tests/golden/04-table-docx/generated/render/deck.pptx)        |
| 05 Chart source      | Native geometric-shape editability              | [deck.pptx](../../tests/golden/05-chart-pptx/generated/render/deck.pptx)        |
| 06 Mixed fonts       | Chinese/Latin fallback and substitution prompts | [deck.pptx](../../tests/golden/06-mixed-fonts/generated/render/deck.pptx)       |
| 07 Template brand    | Brand colors and template presentation          | [deck.pptx](../../tests/golden/07-template-brand/generated/render/deck.pptx)    |
| 08 Dense content     | Six bullets, overflow and clipping              | [deck.pptx](../../tests/golden/08-dense-docx/generated/render/deck.pptx)        |
| 09 PDF baseline      | PDF-derived text presentation                   | [deck.pptx](../../tests/golden/09-pdf-baseline/generated/render/deck.pptx)      |
| 10 Multilingual PPTX | Chinese/English mixed source and glyphs         | [deck.pptx](../../tests/golden/10-multilingual-pptx/generated/render/deck.pptx) |

## Pass criteria

1. Neither application displays a repair, recovery, unsafe-link or font-substitution prompt for any deck.
2. All 30 slides display without missing text, clipping, overflow or unexpected full-slide bitmap fallback.
3. In case 03, edit the title; in case 08, edit one body line; in case 05, recolor or resize one geometric shape.
4. Save edited copies under `.tmp/qa-manual/<application>/`, close them, reopen them, and confirm the edits remain.
5. Confirm the overall result to Codex. Do not overwrite the generated golden decks.

Suggested sign-off statement:

> PowerPoint 16.0 build 20228 and WPS 12.1.0.28043 both passed all ten decks: no repair, recovery, unsafe-link or font-substitution prompt; all slides rendered correctly; title, body and native-shape edits survived save and reopen.
