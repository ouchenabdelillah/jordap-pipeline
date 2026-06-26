# JORADP Legal Act Pipeline

Converts raw OCR text from the Algerian Official Journal (الجريدة الرسمية) into
structured JSON legal acts with cross-reference entities and an interactive HTML viewer.

Everything lives in **one file**: `pipeline.py`  
**No external packages needed** — standard library only (Python 3.8+).

---

## Prerequisites

| Requirement | Notes |
|-------------|-------|
| Python 3.8+ | `python --version` to check |
| Groq API key | Free at [console.groq.com](https://console.groq.com) → API Keys |
| OCR text files | One `JO-*/` folder per journal issue, `page_*.txt` per page |

---

## Folder structure expected

```
your-project/
├── pipeline.py               ← the whole pipeline
├── JO-1968-094/
│   ├── page_01.txt
│   ├── page_02.txt
│   └── ...
├── JO-1969-068/
│   └── ...
└── ...
```

Each `page_*.txt` file holds the OCR lines for one journal page, one line of text per line.

---

## Quick start

### 1 — Test without an API key (structure + viewer only)

```bash
python pipeline.py test JO-1968-094/
```

This parses the OCR and generates the HTML viewer.  
Open `JO-1968-094/viewer2.html` in any browser.  
Expected output:
```
[structure] JO-1968-094: 21 acts (leg 14 / adm 7) | lines 847 [LOSSLESS]
[view] JO-1968-094: viewer → JO-1968-094/viewer2.html
  PASS  JO-1968-094  (21 acts, viewer 312KB)
Test result: 1 passed, 0 failed
```

### 2 — Full pipeline (all 4 stages including LLM)

```bash
python pipeline.py run JO-1968-094/ --key gsk_YOUR_KEY_HERE
```

Or process all `JO-*/` folders at once:

```bash
python pipeline.py run --all --key gsk_YOUR_KEY_HERE
```

When it's done, open `JO-1968-094/viewer2.html` in your browser.

---

## Commands

### `structure` — Stage 1 (no API key needed)
Parses OCR page files into `structure_A.json`. Deterministic, zero network calls.

```bash
python pipeline.py structure JO-1968-094/
python pipeline.py structure --all
```

Output: `JO-1968-094/structure_A.json`

---

### `enhance` — Stage 2 (requires Groq API key)
Sends each act to the LLM for cleanup: OCR repair, date normalization,
cross-reference extraction, article splitting.

```bash
python pipeline.py enhance JO-1968-094/ --key gsk_YOUR_KEY
python pipeline.py enhance --all         --key gsk_YOUR_KEY
```

**Resumable** — re-running skips already-processed acts. Use `--force` to redo everything.

```bash
# options
--key   gsk_…          Groq API key
--model openai/gpt-oss-120b   LLM model (default)
--delay 1.0            Seconds between calls (default 1.0 — stays within free quota)
--force                Re-process all acts even if already done
--limit 3              Only process first 3 acts (useful for smoke-testing)
```

Output: `JO-1968-094/structure_A.enhanced.json`

> **Free tier quota:** Groq gives 200,000 tokens/day rolling.  
> One full-pass of 21 acts ≈ 80,000 tokens.  
> If you hit the limit, wait and re-run — it will resume where it stopped.

---

### `infer` — Stage 3 (no API key needed)
Deterministic post-processing: fills `ref_id`, `relation`, `context`, `location`
for all cross-references using Arabic keyword patterns on the raw text.

```bash
python pipeline.py infer JO-1968-094/
python pipeline.py infer --all
```

Updates `structure_A.enhanced.json` in-place.

---

### `view` — Stage 4 (no API key needed)
Generates the self-contained HTML viewer. Uses enhanced data if available,
falls back to Plan A parse.

```bash
python pipeline.py view JO-1968-094/
python pipeline.py view --all
```

Output: `JO-1968-094/viewer2.html` — open directly in any browser, no server needed.

---

### `run` — Full pipeline
Runs all 4 stages in order for each folder.

```bash
python pipeline.py run JO-1968-094/ --key gsk_…
python pipeline.py run --all         --key gsk_…
```

---

### `test` — Smoke test (no API key needed)
Runs structure + view, checks losslessness, confirms HTML output.

```bash
python pipeline.py test JO-1968-094/
python pipeline.py test --all
```

---

## Providing your API key

Three ways (in priority order):

**1. Command-line flag** (quickest):
```bash
python pipeline.py run JO-1968-094/ --key gsk_YOUR_KEY
```

**2. Environment variable** (recommended for repeated use):
```bash
# Linux / macOS
export GROQ_API_KEY=gsk_YOUR_KEY
python pipeline.py run JO-1968-094/

# Windows CMD
set GROQ_API_KEY=gsk_YOUR_KEY
python pipeline.py run JO-1968-094/

# Windows PowerShell
$env:GROQ_API_KEY = "gsk_YOUR_KEY"
python pipeline.py run JO-1968-094/
```

**3. Key file** — create `.groq_key` in the same directory as `pipeline.py`:
```
gsk_YOUR_KEY_HERE
```
The script reads it automatically.

---

## What the viewer shows

Open `viewer2.html` in your browser after running the pipeline.

- **Serial number badge** on each act (e.g. `68-82`) — the official act number
- **Clickable cross-reference chips** — colored by relation type:
  - Green chip + 🔗 = act exists in this file → click to scroll to it
  - Blue chip = act is in a different journal issue → click to see its metadata
- **Arabic full-text search** — type in the search box to filter acts
- **Fold/expand all** buttons
- **Raw OCR text** toggle on each act

---

## Output files explained

| File | Stage | Description |
|------|-------|-------------|
| `structure_A.json` | 1 | Lossless deterministic parse of all OCR acts |
| `structure_A.enhanced.json` | 2+3 | Same structure + LLM-cleaned `enhanced` sub-object per act |
| `viewer2.html` | 4 | Self-contained HTML viewer, embeds all data inline |

---

## Typical workflow for a new journal issue

```bash
# 1. Place your page files
mkdir JO-1970-012
# copy page_01.txt page_02.txt … into JO-1970-012/

# 2. Quick sanity check (no API key)
python pipeline.py test JO-1970-012/

# 3. Full run
python pipeline.py run JO-1970-012/ --key gsk_YOUR_KEY

# 4. Open the viewer
# → JO-1970-012/viewer2.html
```

---

## Troubleshooting

**`No page_*.txt files found`**  
Your folder is empty or misnamed. Files must be named `page_01.txt`, `page_02.txt`, etc.

**`Run 'structure' first`**  
You tried `enhance` or `view` before `structure`. Run `structure` (or `run`) first.

**`Groq HTTP 429`**  
Daily token quota hit. Wait a few hours and re-run — it resumes automatically.

**`No Groq API key found`**  
Pass `--key gsk_…`, set `GROQ_API_KEY` env var, or create a `.groq_key` file.

**`LINE LOSS: counted=X != input=Y`**  
The OCR file has an unexpected format. Check `page_*.txt` files for encoding issues
(must be UTF-8) or lines with only whitespace.
