# Catlion v2 scraper fix

Replace the existing `scraper.py` and `requirements.txt` in the Catlion repository with the files in this package.

Changes:
- Dcard: use the public forum-post JSON endpoint instead of HTML scraping.
- PTT: try official PTT first; if GitHub Actions receives HTTP 403, fall back to PTTWeb's public Stock-board mirror.
- Failure protection: if both PTT and Dcard return no usable data, the previous `data.json` is preserved instead of being overwritten with zero items.
- Gemini remains controlled by the existing `GEMINI_API_KEY` GitHub Secret.
- `data.json` now records source status and collection counts.

After uploading, run:
GitHub -> Actions -> Catlion Daily Update -> Run workflow
