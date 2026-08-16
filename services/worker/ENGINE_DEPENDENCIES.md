# Engine dependency boundary

G01 installs only the dependencies required by the P1 source and native-PPTX paths, all pinned in `services/worker/pyproject.toml` and `uv.lock`.

- `python-pptx`, `XlsxWriter`, `skia-pathops`, and `uharfbuzz` support canonical SVG to editable DrawingML/PPTX.
- `mammoth`, `markdownify`, `beautifulsoup4`, and `python-pptx` cover the DOCX, HTML, and PPTX source paths.
- `pypdf` is the permissive text-oriented PDF baseline under ADR-003. The upstream PyMuPDF route is not installed or invoked.
- EPUB remains disabled; `ebooklib` is intentionally absent.
- Web fetching, AI image generation, narration, Notebook/Excel/legacy document conversion, and the local Flask editor are outside P1 G01 and their optional upstream dependencies are intentionally absent.

The upstream `requirements.txt` is retained unchanged inside `vendor/ppt-master` for attribution and audit, but is not used as an install command because it contains floating optional dependencies and license-sensitive routes.
