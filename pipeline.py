#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
pipeline.py — JORADP Legal Act Structuring Pipeline
====================================================
Single-file, stdlib-only (Python 3.8+).
All four stages are inlined here; no other project files are needed.

QUICK START
-----------
  python pipeline.py run JO-1968-094/ --key gsk_YOUR_KEY
  python pipeline.py run --all        --key gsk_YOUR_KEY

INDIVIDUAL STAGES
-----------------
  python pipeline.py structure JO-1968-094/
  python pipeline.py enhance   JO-1968-094/ --key gsk_…
  python pipeline.py infer     JO-1968-094/
  python pipeline.py view      JO-1968-094/

TEST (no API key needed)
------------------------
  python pipeline.py test JO-1968-094/
"""

import os, sys, re, json, glob, time, html, argparse, urllib.request, urllib.error

if sys.stdout.encoding != "utf-8":
    try: sys.stdout.reconfigure(encoding="utf-8")
    except AttributeError: pass

# ============================================================
#  STAGE 1 — DETERMINISTIC LOSSLESS STRUCTURER
# ============================================================

AR, FA = "٠١٢٣٤٥٦٧٨٩", "۰۱۲۳۴۵۶۷۸۹"
_TR = {ord(c): str(i) for i, c in enumerate(AR)}
_TR.update({ord(c): str(i) for i, c in enumerate(FA)})
_norm = lambda s: s.translate(_TR)

_DIG  = r"[\d٠-٩۰-۹]"
_TYPE = r"(?:مرسوم|أمر|امر|قانون|قرار)"
_DATED = r"مؤرخ(?:ة|ان|تان|ات|تين)?"

_HIJRI_MONTHS = ["محرم","صفر","ربيع الأول","ربيع الاول","ربيع الثاني","ربيع الثانى",
    "جمادى الأولى","جمادى الاولى","جمادى الثانية","جمادى الآخرة","جمادى الاخرة",
    "رجب","شعبان","رمضان","شوال","ذو القعدة","ذي القعدة","ذو الحجة","ذي الحجة"]
_GREG_MONTHS = ["يناير","فبراير","مارس","ابريل","أبريل","مايو","يونيو","يونيه",
    "يوليو","يوليه","غشت","أغسطس","اغسطس","سبتمبر","شتنبر","اكتوبر","أكتوبر",
    "نوفمبر","ديسمبر","جانفي","فيفري"]

_RE_MASTHEAD = re.compile(r"الجريدة\s+الرسمية|^\s*(?:الجمعة|السبت|الأحد|الاحد|الإثنين|الاثنين|الثلاثاء|الأربعاء|الاربعاء|الخميس)\b.*عام")
_RE_FOLIO    = re.compile(rf"^\s*[«»•\-\*\.\(\)]*\s*{_DIG}{{2,4}}\s*[«»•\-\*\.\(\)]*\s*$")
_RE_MINISTRY = re.compile(r"^\s*(?:وزارة|رئاسة|الأمانة العامة|كتابة الدولة|الوزارة)\b.{0,45}$")
_RE_SECTION  = re.compile(r"^\s*(?:مراسيم|قرارات|مقررات|قرار|آراء|اراء|تعليمات|بلاغات|اعلانات|إعلانات)[\s،,و]*$")
_RE_HEAD = re.compile(
    rf"^\s*(?:و\s*)?(?P<type>{_TYPE})(?:ان|ين|ات|تان|مان)?\s*"
    rf"(?P<joint>وزاري\s+مشترك\s+)?"
    rf"(?:رقم\s*(?P<n1>{_DIG}{{1,4}})\s*[-ـ–—]?\s*(?P<n2>{_DIG}{{1,4}})\s*)?"
    rf"{_DATED}\b")
_RE_MEASURE  = re.compile(rf"^\s*(?:بموجب|موجب|بمقنضى)\s+(?:ال)?{_TYPE}")
_RE_CITATION = re.compile(r"^\s*(?:و\s*)?(?:بمقتضى|بناء\s+على|إن\s+|ان\s+|نظرا|باقتراح|وبعد|وبموجب\s+الامر|وبمقتضى)")
_RE_ENACT    = re.compile(r"^\s*(?:يرسم|يقرر|يقرران|يأمر|نقرر|يقررون)\s*(?:ما\s*يلي|ما\s*يأتي|:)?\s*$")
_RE_ARTICLE  = re.compile(rf"^\s*المادة\s+(?P<n>الأولى|الاولى|{_DIG}+)")
_RE_ANNEX    = re.compile(r"^\s*ملحق\b")
_RE_CLOSING  = re.compile(r"^\s*(?:و\s*)?حرر\s+ب|وحرر\s+بالجزائر")
_RE_SUBJECT_CUT = re.compile(r"^(?:و\s*)?(?:يتضمن|تتضمن|تنضمن|المتضمن|يتعلق|المتعلق|باكتساب|بتحديد|بانشاء|بإنشاء|الرامي|يرمي|المعدل|يعدل|المحدد|يحدد|بشأن|بمنح)\s*")
_RE_TITLE_END = re.compile(r"\s(?:بموجب|موجب|بمقتضى|بناء\s+على|ان\s+رئيس|ان\s+وزير|إن\s+رئيس|إن\s+وزير|يقرر|يقرران|يرسم|نقرر|المادة)\b")


def _parse_date(text, hijri):
    text = _norm(text or "")
    months = _HIJRI_MONTHS if hijri else _GREG_MONTHS
    anchor = "عام" if hijri else "سنة"
    day = None
    md = re.search(r"\b(\d{1,2})\b", text)
    if md: day = int(md.group(1))
    month = next((m for m in months if m in text), None)
    year = None
    my = re.search(rf"{anchor}\s*(\d{{3,4}})", text) or re.search(r"(\d{3,4})", text)
    if my: year = int(my.group(1))
    return {"day": day, "month": month, "year": year, "text": text.strip()} if (day or month or year) else None


def _heading_dates(block):
    b = _norm(block)
    m = re.search(r"(?:في|فى)\s+(?P<h>.*?عام\s*\d{3,4})\s*(?:هـ)?\s*الموافق\s+(?P<g>.*?سنة\s*\d{3,4})", b, re.S)
    if not m:
        m2 = re.search(r"(?:في|فى)\s+(?P<h>.*?عام\s*\d{3,4})", b, re.S)
        return (_parse_date(m2.group("h"), True) if m2 else None), None
    return _parse_date(m.group("h"), True), _parse_date(m.group("g"), False)


def _heading_title(block, jyear=None):
    b = re.sub(r"\s+", " ", _norm(block)).strip()
    cands = list(re.finditer(r"سنة\s*(\d{3,4})", b))
    tail = None
    if cands:
        in_range = [c for c in cands if jyear and abs(int(c.group(1)) - jyear) <= 2]
        c = (in_range or cands)[-1]
        tail = b[c.end():].strip() or None
    if not tail:
        sm = re.search(r"(يتضمن|تتضمن|تنضمن|المتضمن|يتعلق|المتعلق|باكتساب).*$", b)
        tail = sm.group(0).strip() if sm else None
    if not tail:
        return None
    tail = _RE_TITLE_END.split(tail)[0]
    tail = re.split(r"\s[.•◆]\s|\s-\s[تب]\b", tail)[0]
    tail = _RE_SUBJECT_CUT.sub("", tail).strip(" .،:-«»")
    return tail[:200] or None


def _load_pages(folder):
    out = []
    for f in sorted(glob.glob(os.path.join(folder, "page_*.txt"))):
        pno = int(re.search(r"page_(\d+)\.txt$", f).group(1))
        for ln in open(f, encoding="utf-8"):
            t = re.sub(r"^\d+\t", "", ln).rstrip("\n").strip()
            if t:
                out.append((pno, t))
    return out


def _classify(line):
    if _RE_MASTHEAD.search(line): return "MAST"
    if _RE_MINISTRY.match(line):  return "MIN"
    if _RE_ENACT.match(line):     return "ENACT"
    if _RE_ARTICLE.match(line):   return "ART"
    if _RE_ANNEX.match(line):     return "ANNEX"
    if _RE_CLOSING.match(line):   return "CLOSE"
    if _RE_MEASURE.match(line):   return "MEAS"
    if _RE_HEAD.match(line):      return "HEAD"
    if _RE_CITATION.match(line):  return "CITE"
    if _RE_FOLIO.match(line):     return "FOLIO"
    if _RE_SECTION.match(line):   return "SEC"
    return "OTHER"


def do_structure(folder):
    """Stage 1: parse OCR page files → structure_A.json"""
    jid = os.path.basename(folder.rstrip("/\\"))
    ym = re.match(r"JO-(\d{4})-(\d+)", jid)
    jyear = int(ym.group(1)) if ym else None
    toks = _load_pages(folder)
    if not toks:
        raise FileNotFoundError(f"No page_*.txt files found in {folder}")
    N = len(toks)
    tags = [_classify(t) for _, t in toks]

    acts, index, stripped, front, unplaced = [], [], [], [], []
    counted = 0
    ministry = [None]

    def new_act(pno, atype, joint, num):
        return {"id": f"{jid}-act-{len(acts)+1:03d}",
                "type": atype, "joint": bool(joint), "number": num,
                "ministry": ministry[0], "title": None,
                "date_hijri": None, "date_gregorian": None,
                "preamble": [], "measures": [], "articles": [],
                "annex": None, "signature": None, "body": [],
                "kind": None, "source_pages": [], "lines": []}

    cur = None
    target = None
    i = 0
    while i < N:
        pno, line = toks[i]
        tag = tags[i]

        if tag in ("MAST", "FOLIO"):
            stripped.append({"page": pno, "text": line}); counted += 1; i += 1; continue
        if tag == "MIN":
            ministry[0] = line
            if cur: cur["lines"].append({"page": pno, "text": line})
            counted += 1; i += 1; continue
        if tag == "SEC":
            (cur["lines"].append({"page": pno, "text": line}) if cur else front.append({"page": pno, "text": line}))
            counted += 1; i += 1; continue

        if tag == "HEAD":
            j = i + 1
            block = [line]
            while j < N and tags[j] == "OTHER" and (j - i) <= 4:
                block.append(toks[j][1]); j += 1
            block_txt = " ".join(block)
            k = j
            is_toc = (k < N and tags[k] == "FOLIO")
            if is_toc:
                m = _RE_HEAD.match(line)
                index.append({"type": (m.group("type") if m else None),
                              "title": _heading_title(block_txt, jyear),
                              "page_ref": _norm(toks[k][1]).strip("«»•-*.() "),
                              "src_page": pno})
                counted += (k - i + 1); i = k + 1; continue
            m = _RE_HEAD.match(line)
            num = f"{_norm(m.group('n1'))}-{_norm(m.group('n2'))}" if m and m.group("n1") else None
            cur = new_act(pno, m.group("type"), m.group("joint"), num)
            dh, dg = _heading_dates(block_txt)
            cur["title"], cur["date_hijri"], cur["date_gregorian"] = _heading_title(block_txt, jyear), dh, dg
            for p_, t_ in toks[i:j]:
                cur["lines"].append({"page": p_, "text": t_})
                if p_ not in cur["source_pages"]: cur["source_pages"].append(p_)
            acts.append(cur); target = None
            counted += (j - i); i = j; continue

        if cur is None:
            front.append({"page": pno, "text": line}); counted += 1; i += 1; continue

        cur["lines"].append({"page": pno, "text": line})
        if pno not in cur["source_pages"]: cur["source_pages"].append(pno)

        if tag == "MEAS":
            cur["measures"].append({"date_hijri": None, "date_gregorian": None, "text": line})
            dh, dg = _heading_dates(line)
            cur["measures"][-1]["date_hijri"], cur["measures"][-1]["date_gregorian"] = dh, dg
            target = ("measure", len(cur["measures"]) - 1)
        elif tag == "ART":
            am = _RE_ARTICLE.match(line)
            body = line.split(":", 1)[1].strip() if ":" in line else ""
            store = cur["annex"]["articles"] if cur["annex"] is not None else cur["articles"]
            num_raw = _norm(am.group("n"))
            art_seq = len(cur["articles"]) + (len(cur["annex"]["articles"]) if cur["annex"] else 0) + 1
            art_id = f"{cur['id']}-art-{art_seq:03d}"
            store.append({"id": art_id, "num": num_raw, "num_ar": am.group("n"),
                          "text": body, "cross_references": []})
            target = ("article", store)
        elif tag == "ANNEX":
            cur["annex"] = {"title": line, "articles": []}
            target = ("annex_title",)
        elif tag == "CITE":
            cur["preamble"].append(line); target = ("preamble",)
        elif tag == "ENACT":
            target = ("enact",)
        elif tag == "CLOSE":
            cur["signature"] = {"date_text": line, "block": []}
            target = ("sign",)
        else:
            if target and target[0] == "measure":
                cur["measures"][target[1]]["text"] += " " + line
            elif target and target[0] == "article":
                target[1][-1]["text"] = (target[1][-1]["text"] + " " + line).strip()
            elif target and target[0] == "annex_title":
                cur["annex"]["title"] += " " + line
            elif target and target[0] == "preamble":
                cur["preamble"][-1] += " " + line
            elif target and target[0] == "sign":
                cur["signature"]["block"].append(line)
            else:
                cur["body"].append(line)
        counted += 1; i += 1

    for a in acts:
        if not a["title"]:
            j = " ".join(l["text"] for l in a["lines"])
            sm = re.search(r"(?:يتضمن|تتضمن|تنضمن|المتضمن|يتعلق|المتعلق|باكتساب)\s+(.*)", _norm(j))
            if sm:
                t = _RE_TITLE_END.split(sm.group(1))[0]
                t = re.split(r"\s[.•◆]\s", t)[0].strip(" .،:-«»")
                a["title"] = (t[:160] + " ⟨مُستخرج⟩") if t else None
        a["kind"] = ("legislative" if (a["articles"] or a["annex"]) else
                     "administrative" if a["measures"] else "other")
        if a["signature"]:
            blk = a["signature"]["block"]
            a["signature"]["signatory"] = next((b for b in reversed(blk)
                if 2 <= len(b) <= 35 and not re.search(r"\d|سنة|عام|الموافق|وزير|الكاتب|العام", b)), None)
        a["raw_text"] = "\n".join(l["text"] for l in a["lines"])

    assert counted == N, f"LINE LOSS: counted={counted} != input={N}"

    empty = [a for a in acts if not a["title"] and not a["measures"] and not a["articles"]]
    result = {"journal": {"id": jid,
                          "year": int(ym.group(1)) if ym else None,
                          "issue": int(ym.group(2)) if ym else None},
              "act_count": len(acts),
              "stats": {"input_lines": N, "acts": len(acts), "index_entries": len(index),
                        "stripped": len(stripped), "front_matter": len(front),
                        "unplaced": len(unplaced), "empty_acts": len(empty),
                        "legislative": sum(a["kind"] == "legislative" for a in acts),
                        "administrative": sum(a["kind"] == "administrative" for a in acts),
                        "lossless": True},
              "index": index, "front_matter": front, "stripped": stripped,
              "unplaced": unplaced, "acts": acts}
    dest = os.path.join(folder, "structure_A.json")
    json.dump(result, open(dest, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    s = result["stats"]
    print(f"[structure] {jid}: {s['acts']} acts (leg {s['legislative']} / adm {s['administrative']}) "
          f"| index {s['index_entries']} | lines {s['input_lines']} [LOSSLESS]")
    return result


# ============================================================
#  STAGE 2 — GROQ LLM CLIENT
# ============================================================

_GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
_GROQ_DEFAULT_MODEL = "openai/gpt-oss-120b"
_THINKING_MODELS = {"qwen/qwen3-32b", "qwen/qwen3.6-27b"}
_groq_model = _GROQ_DEFAULT_MODEL   # overridden by CLI --model


def _groq_key(cli_key=None):
    if cli_key:
        return cli_key
    if os.environ.get("GROQ_API_KEY"):
        return os.environ["GROQ_API_KEY"]
    kf = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".groq_key")
    if os.path.exists(kf):
        return open(kf, encoding="utf-8").read().strip()
    return ""


def _strip_think(text):
    return re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()


def groq_generate(prompt, system=None, as_json=True, api_key=None,
                  max_retries=5, timeout=180, max_output_tokens=4000):
    model = _groq_model
    thinking = model in _THINKING_MODELS
    msgs = ([{"role": "system", "content": system}] if system else []) + \
           [{"role": "user", "content": prompt}]
    payload = {"model": model, "messages": msgs,
               "temperature": 0.6 if thinking else 0.0,
               "max_tokens": max_output_tokens + (2000 if thinking else 0)}
    if as_json and not thinking:
        payload["response_format"] = {"type": "json_object"}
    data = json.dumps(payload).encode()
    key = _groq_key(api_key)
    if not key:
        raise RuntimeError("No Groq API key found. Pass --key gsk_… or set GROQ_API_KEY env var.")
    headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json",
               "User-Agent": "Mozilla/5.0"}
    for attempt in range(max_retries):
        req = urllib.request.Request(_GROQ_URL, data=data, headers=headers)
        try:
            r = urllib.request.urlopen(req, timeout=timeout)
            d = json.load(r)
            txt = d["choices"][0]["message"]["content"]
            if thinking:
                txt = _strip_think(txt)
            if not as_json:
                return txt
            t = txt.strip()
            if t.startswith("```"):
                t = t.split("```", 2)[1].lstrip("json").strip()
            t = "".join(c for c in t if c >= " " or c in "\t\n\r")
            return json.loads(t)
        except urllib.error.HTTPError as e:
            body = e.read().decode()[:300]
            if e.code in (429, 500, 502, 503) and attempt < max_retries - 1:
                time.sleep(min(2 ** attempt * 3, 60)); continue
            raise RuntimeError(f"Groq HTTP {e.code}: {body}")
        except (json.JSONDecodeError, KeyError) as e:
            if attempt < max_retries - 1:
                time.sleep(3); continue
            raise RuntimeError(f"Groq bad response: {e}")


# ============================================================
#  STAGE 2 — LLM ENHANCER
# ============================================================

_SYSTEM_FULL = """You clean and normalize ONE act from the Algerian Official Journal
(الجريدة الرسمية / JORADP). The source is OCR from a 2-3 column Arabic layout,
so reading order may be interleaved between adjacent columns.

RULES:
1. RECONSTRUCT reading order: if lines from two different acts/columns are
   interleaved, separate them.
2. FAITHFUL: never invent content; fix only obvious OCR typos and join
   broken/hyphenated words. Do NOT summarize or shorten article/measure text.
3. NUMERALS: convert ALL Arabic-Indic (٠١٢…) and Eastern numerals to ASCII digits.
4. DATES: always use Arabic month names (يناير فبراير مارس أبريل مايو يونيو
   يوليو أغسطس سبتمبر أكتوبر نوفمبر ديسمبر). Compute iso="YYYY-MM-DD" when
   day+month+year are all present, else null.
5. SIGNATORY: look for وحرر or صدر or الممضي أدناه near the end.
6. PRESERVE all measures and articles — same count as input unless you detect
   a clear merge error.
7. CROSS-REFERENCES — every cited act/law/decree must be a structured entity:
   - ref_id: canonical key = "{normalized_type}-{number}" e.g. "مرسوم-66-133"
   - relation: "cites"=بناء على; "amends"=يعدل; "abrogates"=يلغي/إلغاء;
     "supplements"=يتمم; "amends_supplements"=يعدل ويتمم;
     "implements"=تطبيقاً لـ; "replaces"=يستبدل
   - context: verbatim Arabic phrase that mentions this act (≤ 120 chars)
   - location: "preamble"|"article"|"measure"|"body"
   - target_article: article number being modified if relation is article-level, else null
8. ARTICLES — each article is its own entity with a stable id and its own cross_references.
   Preserve the id values from the rough parse; keep num_ar as the original Arabic ordinal.
Return ONLY this JSON object (no markdown, no explanation):
{
 "title": "concise faithful subject of the act",
 "type": "مرسوم|أمر|قانون|قرار|قرار وزاري مشترك",
 "joint_ministerial": bool,
 "ministry": "string|null",
 "date_hijri": {"day":int|null,"month":"arabic hijri month name|null","year":int|null},
 "date_gregorian": {"day":int|null,"month":"arabic month name|null","year":int|null,"iso":"YYYY-MM-DD|null"},
 "preamble": ["citation strings"],
 "articles": [{"id":"act_id-art-001","num":"1","num_ar":"الأولى","text":"faithful cleaned text",
               "cross_references":[]}],
 "measures": [{"text":"faithful cleaned text","person":"name|null","action":"string|null",
               "role":"string|null","effective_date_iso":"YYYY-MM-DD|null"}],
 "annex": {"title":"string|null","articles":[{"id":"...","num":"...","num_ar":"...","text":"...","cross_references":[]}]} | null,
 "signatory": "person name|null",
 "signatory_role": "string|null",
 "cross_references": [{"ref_id":"مرسوم-66-133","act_type":"مرسوم|أمر|قانون|قرار",
   "number":"66-133|null","date_iso":"YYYY-MM-DD|null",
   "relation":"cites|amends|abrogates|supplements|amends_supplements|implements|replaces",
   "context":"verbatim Arabic phrase ≤120 chars","location":"preamble|article|measure|body",
   "target_article":"article num or null"}]
}"""

_SYSTEM_LIGHT = """You extract METADATA for ONE act from the Algerian Official
Journal (الجريدة الرسمية / JORADP). Do NOT reproduce its body — only return clean metadata.
Rules: convert numerals to ASCII; use Arabic month names; compute iso="YYYY-MM-DD" when
day+month+year all present, else null; use null when a field is absent.
Return ONLY this JSON (no markdown):
{
 "title": "concise faithful subject",
 "type": "مرسوم|أمر|قانون|قرار|قرار وزاري مشترك",
 "joint_ministerial": bool,
 "ministry": "string|null",
 "date_hijri": {"day":int|null,"month":"arabic hijri month|null","year":int|null},
 "date_gregorian": {"day":int|null,"month":"arabic month|null","year":int|null,"iso":"YYYY-MM-DD|null"},
 "signatory": "name|null", "signatory_role": "string|null",
 "cross_references": [{"ref_id":"مرسوم-66-133","act_type":"مرسوم|أمر|قانون|قرار",
   "number":"66-133|null","date_iso":"YYYY-MM-DD|null",
   "relation":"cites|amends|abrogates|supplements|amends_supplements|implements|replaces",
   "context":"verbatim Arabic phrase ≤120 chars","location":"preamble|article|measure|body",
   "target_article":null}],
 "n_persons_estimate": int
}"""

_LIGHT_CHARS    = 4500
_LIGHT_MEASURES = 8


def _enhance_one(act, api_key=None):
    rough = {k: act.get(k) for k in ("type", "number", "joint", "ministry",
             "title", "date_hijri", "date_gregorian")}
    rough["n_articles"] = len(act.get("articles", []))
    rough["n_measures"] = len(act.get("measures", []))
    rough["article_ids"] = [{"id": a.get("id"), "num": a.get("num"), "num_ar": a.get("num_ar")}
                             for a in act.get("articles", [])]
    light = len(act["raw_text"]) > _LIGHT_CHARS or rough["n_measures"] > _LIGHT_MEASURES
    raw = act["raw_text"] if not light else act["raw_text"][:6000]
    prompt = (f"ROUGH PARSE (may be wrong):\n{json.dumps(rough, ensure_ascii=False)}\n\n"
              f"RAW OCR TEXT OF THE ACT:\n\"\"\"\n{raw}\n\"\"\"\n\n"
              "IMPORTANT: reproduce measure/article text VERBATIM (cleaned OCR only). "
              "Do NOT paraphrase or summarize body content.\n"
              "Return the cleaned JSON now.")
    try:
        enh = groq_generate(prompt, system=(_SYSTEM_LIGHT if light else _SYSTEM_FULL),
                            as_json=True, api_key=api_key)
        enh["_mode"] = "light" if light else "full"
        enh["_model"] = _groq_model
        return enh
    except RuntimeError:
        if light: raise
        enh = groq_generate(prompt, system=_SYSTEM_LIGHT, as_json=True, api_key=api_key)
        enh["_mode"] = "light"; enh["_fallback"] = "full_failed"
        enh["_model"] = _groq_model
        return enh


def _reconcile(act, enh):
    w = []
    if enh.get("_mode") == "light":
        return w
    na, ma = len(act.get("articles", [])), len(enh.get("articles") or [])
    nm, mm = len(act.get("measures", [])), len(enh.get("measures") or [])
    if ma < na: w.append(f"articles {na}->{ma} (fewer)")
    if mm < nm: w.append(f"measures {nm}->{mm} (fewer)")
    raw_words = set(re.findall(r"[؀-ۿ]{4,}", act["raw_text"]))
    enh_words = set(re.findall(r"[؀-ۿ]{4,}", json.dumps(enh, ensure_ascii=False)))
    missing = raw_words - enh_words
    if len(missing) > max(8, 0.25 * len(raw_words)):
        w.append(f"{len(missing)}/{len(raw_words)} long words absent")
    return w


def do_enhance(folder, limit=None, force=False, delay=1.0, api_key=None):
    """Stage 2: send each act to the LLM → structure_A.enhanced.json"""
    dest = os.path.join(folder, "structure_A.enhanced.json")
    src  = dest if (os.path.exists(dest) and not force) else os.path.join(folder, "structure_A.json")
    if not os.path.exists(src):
        raise FileNotFoundError(f"Run 'structure' first — {src} not found")
    data = json.load(open(src, encoding="utf-8"))
    acts = data["acts"]
    todo = acts[:limit] if limit else acts
    ok = err = skip = 0
    for i, act in enumerate(todo, 1):
        prev = act.get("enhanced")
        if prev and "_error" not in prev and not force:
            skip += 1; continue
        try:
            enh = _enhance_one(act, api_key=api_key)
            enh["_warnings"] = _reconcile(act, enh)
            act["enhanced"] = enh
            flag = "[!] " + "; ".join(enh["_warnings"]) if enh["_warnings"] else "clean"
            print(f"  [{i}/{len(todo)}] {act['id']}: {flag}", flush=True)
            ok += 1
            if delay > 0 and i < len(todo):
                time.sleep(delay)
        except Exception as e:
            act["enhanced"] = {"_error": str(e)}
            print(f"  [{i}/{len(todo)}] {act['id']}: ERROR {e}", flush=True)
            err += 1
            if delay > 0 and i < len(todo):
                time.sleep(delay)
    if skip: print(f"  (skipped {skip} already-enhanced acts)", flush=True)
    data["enhanced_with"] = _groq_model
    data["enhanced_stats"] = {"ok": ok, "error": err, "skipped": skip, "total": len(todo)}
    json.dump(data, open(dest, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    jid = data["journal"]["id"]
    print(f"[enhance] {jid}: enhanced {ok} / err {err} / skip {skip} → {dest}")
    return data


# ============================================================
#  STAGE 3 — DETERMINISTIC CROSS-REFERENCE POST-PROCESSOR
# ============================================================

_AR_DIGITS_TR = str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789")

def _norm_digits(s):
    return s.translate(_AR_DIGITS_TR) if s else s

def _norm_number(n):
    if not n: return n
    n = _norm_digits(n).strip()
    n = re.sub(r"[/\\]", "-", n)
    n = re.sub(r"\s+", "-", n)
    n = re.sub(r"-{2,}", "-", n)
    return n.strip("-")

_TYPE_NORM_MAP = {"امر": "أمر", "قرار وزاري مشترك": "قرار"}

def _norm_type(t):
    return _TYPE_NORM_MAP.get(t, t) if t else t

def _make_ref_id(act_type, number):
    t = _norm_type(act_type or "")
    n = _norm_number(number or "")
    if t and n: return f"{t}-{n}"
    if t: return t
    return None

_RELATION_PATTERNS = [
    (re.compile(r"إلغاء|يلغي|أُلغي|ألغي|يُلغى|ملغى", re.UNICODE),           "abrogates"),
    (re.compile(r"يستبدل|استبدال", re.UNICODE),                               "replaces"),
    (re.compile(r"يعدل\s+و\s*يتمم|يعدلان\s+و\s*يتممان", re.UNICODE),         "amends_supplements"),
    (re.compile(r"يتمم|يُتمم|تتمم|تتميم", re.UNICODE),                       "supplements"),
    (re.compile(r"يعدل|يُعدل|تعديل", re.UNICODE),                            "amends"),
    (re.compile(r"تطبيقاً\s+لـ|تطبيق\s+أحكام|تنفيذاً\s+لـ", re.UNICODE),    "implements"),
    (re.compile(r"بناء\s+على|بمقتضى|بموجب|استناداً|وفق", re.UNICODE),        "cites"),
]

def _extract_context(number, raw_text, window=150):
    if not number or not raw_text: return None
    norm_raw = _norm_digits(raw_text)
    norm_n = _norm_number(number) or ""
    candidates = [norm_n]
    if "-" in norm_n:
        yr, seq = norm_n.split("-", 1)
        candidates += [f"{yr} - {seq}", f"{yr}/{seq}"]
    idx = -1; match_len = len(norm_n)
    for cand in candidates:
        p = norm_raw.find(cand)
        if p != -1:
            idx = p; match_len = len(cand); break
    if idx == -1:
        idx = raw_text.find(number); match_len = len(number)
    if idx == -1: return None
    start = max(0, idx - 80)
    end = min(len(raw_text), idx + match_len + 40)
    return raw_text[start:end].replace("\n", " ").strip()[:window]

def _infer_relation(context_text, preamble_list):
    haystack = (context_text or "") + " " + " ".join(preamble_list or [])
    for pattern, rel in _RELATION_PATTERNS:
        if pattern.search(haystack): return rel
    return "cites"

def _infer_location(number, raw_text, preamble_list):
    preamble_joined = " ".join(preamble_list or [])
    if number and number in preamble_joined: return "preamble"
    if number:
        norm_raw = _norm_digits(raw_text or "")
        art_pos = min((norm_raw.find(k) for k in ["المادة", "يقرر", "يرسم"] if k in norm_raw), default=-1)
        n_pos = norm_raw.find(_norm_number(number) or "")
        if n_pos != -1 and art_pos != -1:
            return "preamble" if n_pos < art_pos else "article"
    return "preamble"

def _migrate_xref(xr, raw_text, preamble_list):
    number   = _norm_number(xr.get("number") or xr.get("act_number"))
    act_type = xr.get("act_type") or xr.get("type")
    ref_id   = _make_ref_id(act_type, number)
    context  = _extract_context(number, raw_text)
    relation = xr.get("relation") or ""
    if not relation or relation == "?":
        ctx = (context or "") + " " + " ".join(preamble_list or [])
        relation = _infer_relation(ctx, preamble_list)
    location = xr.get("location") or _infer_location(number, raw_text, preamble_list)
    return {"ref_id": ref_id, "act_type": act_type, "number": number,
            "date_iso": xr.get("date_iso"), "relation": relation,
            "context": xr.get("context") or context,
            "location": location, "target_article": xr.get("target_article")}


def do_infer(folder):
    """Stage 3: fill/fix cross-reference fields deterministically"""
    ef = os.path.join(folder, "structure_A.enhanced.json")
    if not os.path.exists(ef):
        raise FileNotFoundError(f"Run 'enhance' first — {ef} not found")
    data = json.load(open(ef, encoding="utf-8"))
    migrated = filled = already = 0
    for act in data["acts"]:
        enh = act.get("enhanced")
        if not enh or "_error" in enh: continue
        preamble = enh.get("preamble") or []
        raw = act.get("raw_text", "")
        new_xrefs = []
        for xr in (enh.get("cross_references") or []):
            if "ref_id" in xr:
                if not xr.get("context"):
                    xr["context"] = _extract_context(xr.get("number"), raw)
                if not xr.get("location"):
                    xr["location"] = _infer_location(xr.get("number"), raw, preamble)
                if not xr.get("ref_id"):
                    xr["ref_id"] = _make_ref_id(xr.get("act_type"), xr.get("number"))
                new_xrefs.append(xr); already += 1
            else:
                new_xrefs.append(_migrate_xref(xr, raw, preamble)); migrated += 1
        enh["cross_references"] = new_xrefs
        for art in (enh.get("articles") or []):
            if not isinstance(art, dict): continue
            new_art_xrefs = []
            for xr in (art.get("cross_references") or []):
                if not isinstance(xr, dict): continue
                if "ref_id" in xr:
                    new_art_xrefs.append(xr); already += 1
                else:
                    new_art_xrefs.append(_migrate_xref(xr, raw, preamble)); migrated += 1
            art["cross_references"] = new_art_xrefs
        plan_a_arts = act.get("articles", [])
        for i, art in enumerate(enh.get("articles") or []):
            if not isinstance(art, dict): continue
            if not art.get("id") and i < len(plan_a_arts):
                art["id"] = plan_a_arts[i].get("id", f"{act['id']}-art-{i+1:03d}")
            if not art.get("num_ar") and i < len(plan_a_arts):
                art["num_ar"] = plan_a_arts[i].get("num_ar", art.get("num"))
    json.dump(data, open(ef, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    jid = data["journal"]["id"]
    print(f"[infer] {jid}: migrated={migrated}  already_new={already}")


# ============================================================
#  STAGE 4 — HTML VIEWER GENERATOR
# ============================================================

_VIEWER_TEMPLATE = r"""<!DOCTYPE html>
<html lang="ar" dir="rtl">
<head>
<meta charset="utf-8">
<title>__JID__</title>
<style>
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:'Segoe UI',Tahoma,Arial,sans-serif;background:#0f1117;color:#d8dce6;min-height:100vh}
header{position:sticky;top:0;z-index:100;background:#161b27;border-bottom:1px solid #262d3d;padding:12px 20px;box-shadow:0 2px 12px rgba(0,0,0,.5)}
.hrow1{display:flex;align-items:center;gap:14px;flex-wrap:wrap}
h1{font-size:1.15rem;color:#7aadff;font-weight:600}
.banner{font-size:.76rem;color:#556;margin-top:6px}.banner b{color:#4caf7d}
.hcontrols{display:flex;gap:8px;align-items:center;margin-top:8px;flex-wrap:wrap}
#q{flex:1;min-width:220px;padding:7px 12px;border-radius:6px;border:1px solid #2a3348;background:#0f1117;color:#d8dce6;font:inherit;font-size:.85rem}
#q:focus{outline:none;border-color:#4a6fa5}
.btn{font:inherit;font-size:.78rem;padding:6px 14px;border-radius:6px;border:1px solid #2a3348;background:#1a2236;color:#8a9bb5;cursor:pointer}
.btn:hover{background:#232d42;color:#aabdd4}
.wrap{max-width:980px;margin:18px auto;padding:0 16px 60px}
.act{background:#161b27;border-radius:10px;margin-bottom:14px;border:1px solid #1e2840;overflow:hidden;transition:border-color .15s}
.act:hover{border-color:#2e3f5c}.act.open{border-color:#3a5280}
.act{border-right:4px solid #3a5280}.act.administrative{border-right-color:#7a5c1e}.act.other{border-right-color:#3a5a3a}
.ahead{display:flex;align-items:flex-start;gap:14px;padding:13px 16px;cursor:pointer;user-select:none}
.ahead:hover{background:rgba(255,255,255,.02)}
.serial{flex-shrink:0;display:flex;flex-direction:column;align-items:center;justify-content:center;min-width:72px;padding:6px 10px;border-radius:8px;background:#0d1520;border:1px solid #2a3a56;text-align:center}
.serial-num{font-family:monospace;font-size:1.05rem;font-weight:700;color:#7aadff;letter-spacing:.5px;white-space:nowrap}
.serial-type{font-size:.63rem;color:#556;margin-top:2px}
.atitle-block{flex:1;min-width:0}
.atitle{font-size:.95rem;font-weight:600;color:#c8d4e8;line-height:1.45}
.ameta{display:flex;gap:8px;flex-wrap:wrap;margin-top:5px;align-items:center}
.chip{display:inline-flex;align-items:center;gap:4px;font-size:.7rem;padding:2px 8px;border-radius:10px;white-space:nowrap}
.chip-type{background:#1a2e4a;color:#5a9ade;border:1px solid #2a4060}
.chip-joint{background:#2a1e3a;color:#9a7adf;border:1px solid #3a2850}
.chip-date{background:#101820;color:#5a8aae;border:1px solid #1e3050}
.chip-page{background:#0f1a10;color:#4a8a5a;border:1px solid #1e3a20}
.chip-ministry{background:#1a1a0f;color:#9a8a4a;border:1px solid #3a320f;max-width:220px;overflow:hidden;text-overflow:ellipsis}
.enh-badge{font-size:.68rem;padding:2px 7px;border-radius:10px;background:#1a2e1a;color:#4caf7d;border:1px solid #2a4a2a}
.warn-badge{font-size:.68rem;padding:2px 7px;border-radius:10px;background:#2a1a0a;color:#c87a2a;border:1px solid #4a2a0a}
.toggle-icon{flex-shrink:0;color:#3a4f6a;font-size:.9rem;padding-top:4px;transition:transform .2s}
.act.open .toggle-icon{transform:rotate(90deg)}
.body{display:none;border-top:1px solid #1e2840;padding:14px 16px}
.act.open .body{display:block}
.sec{margin-top:14px}.sec:first-child{margin-top:0}
.sec-head{font-size:.75rem;font-weight:700;color:#4a6fa5;letter-spacing:.6px;text-transform:uppercase;margin-bottom:8px;padding-bottom:4px;border-bottom:1px solid #1e2840}
.art-item{padding:8px 12px;margin:5px 0;background:#0d1520;border-radius:6px;border-right:3px solid #2a4060;line-height:1.8;font-size:.85rem}
.art-id{font-family:monospace;font-size:.62rem;color:#2a4060;float:left;margin-left:8px;padding:1px 5px;background:#0a1018;border-radius:3px;direction:ltr}
.art-num{font-weight:700;color:#5a9ade;margin-left:8px}
.art-text{color:#c0ccd8}
.meas-item{padding:7px 12px;margin:5px 0;background:#12110a;border-radius:6px;border-right:3px solid #4a3a1a;line-height:1.8;font-size:.85rem}
.meas-person{font-weight:600;color:#d4a44a}.meas-role{color:#8a7a4a;font-size:.8rem}.meas-date{color:#6a5a2a;font-size:.75rem}
.pre-item{padding:5px 10px;font-size:.82rem;color:#6a7a8a;border-right:2px solid #2a3040;margin:3px 0;line-height:1.7}
.xref-list{display:flex;flex-wrap:wrap;gap:6px;margin-top:4px}
.xref-chip{display:inline-flex;align-items:center;gap:5px;padding:4px 10px;border-radius:8px;font-size:.75rem;cursor:pointer;transition:all .15s;border:1px solid #2a3a56;background:#0d1520;color:#6a9ade}
.xref-chip:hover{background:#1a2a3a;border-color:#4a6a9a;color:#8abcff}
.xref-chip.local{border-color:#1e3a2e;color:#4aaf7a;background:#0a1510}
.xref-chip.local:hover{background:#0f1e18;border-color:#2a6a4a;color:#6ad49a}
.xref-rel{font-size:.65rem;padding:1px 5px;border-radius:6px;background:#1a2030;color:#445}
.xref-chip.local .xref-rel{background:#0f1e12;color:#2a5a3a}
.rel-amends{color:#df8a3a!important;background:#2a1a0a!important}
.rel-abrogates{color:#df4a4a!important;background:#2a0a0a!important}
.rel-supplements{color:#4a9adf!important;background:#0a1a2a!important}
.rel-implements{color:#9a6adf!important;background:#1a0a2a!important}
.rel-replaces{color:#df5a2a!important;background:#2a1508!important}
.sign-box{font-style:italic;color:#8a9aaa;background:#0d1520;border:1px dashed #2a3a50;padding:8px 12px;border-radius:6px;font-size:.85rem}
.annex-box{background:#0a1510;border:1px solid #1e3a24;border-radius:8px;padding:10px 14px;margin-top:8px}
.annex-title{font-size:.78rem;font-weight:700;color:#4aaf7a;margin-bottom:8px}
.raw-btn{font:inherit;font-size:.72rem;padding:4px 10px;border-radius:5px;border:1px solid #2a3040;background:#0d1520;color:#4a5a6a;cursor:pointer;margin-top:10px}
.raw-btn:hover{background:#1a2030;color:#6a7a8a}
.raw{display:none;white-space:pre-wrap;font-size:.78rem;background:#080c12;color:#8a9aaa;padding:12px;border-radius:6px;max-height:320px;overflow:auto;line-height:1.7;margin-top:8px;font-family:monospace;direction:ltr;text-align:left}
.raw.show{display:block}
#refPanel{display:none;position:fixed;bottom:20px;left:50%;transform:translateX(-50%);background:#1a2236;border:1px solid #3a5280;border-radius:12px;padding:16px 22px;min-width:300px;max-width:520px;box-shadow:0 8px 32px rgba(0,0,0,.7);z-index:200}
#refPanel.show{display:block}
#refPanel h4{font-size:.85rem;color:#7aadff;margin-bottom:10px}
#refPanelClose{float:left;font:inherit;font-size:.75rem;padding:4px 10px;border-radius:5px;border:1px solid #2a3a56;background:#0f1520;color:#5a6a7a;cursor:pointer;margin-top:4px}
@keyframes flashAct{0%,100%{border-color:inherit}50%{border-color:#7aadff;box-shadow:0 0 18px rgba(122,173,255,.3)}}
.act.flash{animation:flashAct 1.2s ease}
.special{background:#0d1520;border:1px solid #2a3a56;border-radius:8px;padding:10px 14px;margin-bottom:14px}
.special-head{font-size:.78rem;font-weight:700;color:#4a6fa5;margin-bottom:8px}
.special-item{font-size:.82rem;padding:4px 0;color:#7a8a9a;border-bottom:1px solid #151d2a}
</style>
</head>
<body>
<header>
  <div class="hrow1">
    <h1>__JID__</h1>
    <span id="enh-count" style="font-size:.75rem;color:#4caf7d"></span>
  </div>
  <div class="banner" id="banner"></div>
  <div class="hcontrols">
    <input id="q" placeholder="بحث في النصوص…" autocomplete="off">
    <button class="btn" id="foldAll">طي الكل</button>
    <button class="btn" id="expandAll">فتح الكل</button>
  </div>
</header>
<div class="wrap" id="wrap"></div>
<div id="refPanel">
  <h4 id="refPanelTitle">مرجع قانوني</h4>
  <div id="refPanelBody"></div>
  <button id="refPanelClose">✕ إغلاق</button>
</div>
<script>
const DATA=__DATA__;
let ACT_BY_NUMBER={},ACT_BY_REFID={};
function buildIndex(acts){ACT_BY_NUMBER={};ACT_BY_REFID={};(acts||[]).forEach((act,i)=>{const domId=`act-card-${String(i+1).padStart(3,'0')}`;const n=(act.enhanced?.number||act.number||'').trim();const t=(act.enhanced?.type||act.type||'').trim();if(n){ACT_BY_NUMBER[n]=domId;if(t)ACT_BY_REFID[`${t}-${n}`]=domId;}});}
function esc(s){return(s==null?'':String(s)).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));}
function dstr(d){if(!d)return'';return[d.day,d.month,d.year].filter(Boolean).join(' ');}
const REL_LABELS={cites:'يستند إلى',amends:'يعدّل',abrogates:'يُلغي',supplements:'يُتمّم',amends_supplements:'يعدّل ويتمّم',implements:'يُطبّق',replaces:'يستبدل'};
function serialBadge(act){const e=act.enhanced&&!act.enhanced._error?act.enhanced:null;const num=(e?.number||act.number||'').trim();const type=(e?.type||act.type||'').trim();const iso=e?.date_gregorian?.iso||'';let numDisplay=num?esc(num):(iso?esc(iso):'—');return`<div class="serial"><div class="serial-num">${numDisplay}</div><div class="serial-type">${esc(type)}</div></div>`;}
function xrefChip(x){if(!x||typeof x!=='object')return'';const refId=x.ref_id||'';const num=x.number||'';const type=x.act_type||x.type||'';const rel=x.relation||'cites';const date=x.date_iso||'';const ctx=x.context||'';const loc=x.location||'';const relLabel=REL_LABELS[rel]||rel;const relClass=`rel-${rel}`;const domId=ACT_BY_NUMBER[num]||ACT_BY_REFID[refId]||'';const isLocal=!!domId;const dataAttrs=`data-refid="${esc(refId)}" data-num="${esc(num)}" data-type="${esc(type)}" data-rel="${esc(rel)}" data-date="${esc(date)}" data-ctx="${esc(ctx)}" data-loc="${esc(loc)}" data-domid="${esc(domId)}"`;return`<span class="xref-chip ${isLocal?'local':''}" ${dataAttrs}><span class="xref-rel ${relClass}">${esc(relLabel)}</span> ${esc(type)} ${esc(num)}${date?' · '+esc(date):''}${isLocal?' 🔗':''}</span>`;}
function artItem(a,idx){if(typeof a!=='object'||!a)return'';const id=a.id||'';const num=a.num||a.num_ar||String(idx+1);const txt=a.text||'';const xrefs=(a.cross_references||[]).filter(x=>x&&typeof x==='object');const artXrefs=xrefs.length?`<div class="xref-list" style="margin-top:6px">${xrefs.map(xrefChip).join('')}</div>`:'';return`<div class="art-item">${id?`<span class="art-id">${esc(id)}</span>`:''}<span class="art-num">م ${esc(num)}</span> <span class="art-text">${esc(txt)}</span>${artXrefs}</div>`;}
function measItem(m,idx){if(!m)return'';const person=m.person?`<span class="meas-person">${esc(m.person)}</span>`:'';const role=m.role?`<span class="meas-role"> — ${esc(m.role)}</span>`:'';const dt=m.effective_date_iso||m.date_gregorian_iso||dstr(m.date_gregorian)||'';const date=dt?`<span class="meas-date"> 📅 ${esc(dt)}</span>`:'';return`<div class="meas-item"><span class="art-num" style="color:#8a7a4a">${idx+1}</span>${person}${role}${date} <span class="art-text">${esc(m.text||'')}</span></div>`;}
function actCard(act,i){const e=act.enhanced&&!act.enhanced._error?act.enhanced:null;const kind=act.kind||'legislative';const enhanced=!!e;let title=(e?.title||act.title||'(بدون عنوان)').replace('⟨مُستخرج⟩','').trim();const type=e?.type||act.type||'';const joint=act.joint||e?.joint_ministerial;const ministry=e?.ministry||act.ministry||'';const dgIso=e?.date_gregorian?.iso||'';const dg=dgIso||dstr(act.date_gregorian);const dh=dstr(act.date_hijri);const pages=(act.source_pages||[]).join('، ');let chips=`<span class="chip chip-type">${esc(type||kind)}</span>`;if(joint)chips+=`<span class="chip chip-joint">وزاري مشترك</span>`;if(dg)chips+=`<span class="chip chip-date">📅 ${esc(dg)}</span>`;if(dh)chips+=`<span class="chip chip-date">${esc(dh)} هـ</span>`;if(ministry)chips+=`<span class="chip chip-ministry" title="${esc(ministry)}">🏛 ${esc(ministry)}</span>`;if(pages)chips+=`<span class="chip chip-page">📄 ص ${esc(pages)}</span>`;if(enhanced)chips+=`<span class="enh-badge">✨ ${esc(e._model||'LLM')}</span>`;const warns=e?._warnings?.length?`<span class="warn-badge" title="${e._warnings.map(esc).join('\n')}">⚠ ${e._warnings.length} تحذير</span>`:'';const actXrefs=(e?.cross_references||[]).filter(x=>x&&typeof x==='object');const xrefSec=actXrefs.length?`<div class="sec"><div class="sec-head">المراجع (${actXrefs.length})</div><div class="xref-list">${actXrefs.map(xrefChip).join('')}</div></div>`:'';const preItems=(act.preamble||[]);const preSec=preItems.length?`<div class="sec"><div class="sec-head">الديباجة (${preItems.length})</div>${preItems.map(p=>`<div class="pre-item">${esc(p)}</div>`).join('')}</div>`:'';const arts0=(e?._mode==='full'&&e?.articles?.length)?e.articles:act.articles;const artSec=(arts0||[]).length?`<div class="sec"><div class="sec-head">المواد (${arts0.length})</div>${arts0.map((a,i)=>artItem(a,i)).join('')}</div>`:'';const meas0=(e?._mode==='full'&&e?.measures?.length)?e.measures:act.measures;const measSec=(meas0||[]).length?`<div class="sec"><div class="sec-head">الإجراءات (${meas0.length})</div>${meas0.map((m,i)=>measItem(m,i)).join('')}</div>`:'';const annexObj=e?.annex||act.annex;const annexSec=(annexObj&&(annexObj.title||annexObj.articles?.length))?`<div class="annex-box"><div class="annex-title">ملحق — ${esc(annexObj.title||'')}</div>${(annexObj.articles||[]).map((a,i)=>artItem(a,i)).join('')}</div>`:'';const who=e?.signatory||act.signature?.signatory||'';const role2=e?.signatory_role||'';const signSec=who?`<div class="sec"><div class="sec-head">التوقيع</div><div class="sign-box">${esc(who)}${role2?' — '+esc(role2):''}</div></div>`:'';const raw=act.raw_text||(act.lines||[]).map(l=>l.text).join('\n');const domId=`act-card-${String(i+1).padStart(3,'0')}`;return`<div class="act ${kind}${enhanced?' open':''}" id="${domId}" data-i="${i}"><div class="ahead">${serialBadge(act)}<div class="atitle-block"><div class="atitle">${esc(title)}</div><div class="ameta">${chips}${warns}</div></div><span class="toggle-icon">▶</span></div><div class="body">${xrefSec}${preSec}${measSec}${artSec}${annexSec}${signSec}<button class="raw-btn">النص الخام ↕</button><pre class="raw">${esc(raw)}</pre></div></div>`;}
function indexBlock(idx){if(!idx?.length)return'';return`<div class="special"><div class="special-head">الفهرس — ${idx.length} مدخلاً</div>${idx.map(e=>`<div class="special-item"><span style="color:#4a6fa5">${esc(e.type||'')}</span> ${esc(e.title||'—')}</div>`).join('')}</div>`;}
function render(){const acts=DATA.acts||[];buildIndex(acts);const s=DATA.stats||{};document.getElementById('banner').innerHTML=`الأعمال: <b>${acts.length}</b> · تشريعية ${s.legislative||0} · إدارية ${s.administrative||0} · الفهرس: ${s.index_entries||0} · أسطر: ${s.input_lines||0} · <b>بدون فقدان ✓</b>`;const enhCount=acts.filter(a=>a.enhanced&&!a.enhanced._error).length;document.getElementById('enh-count').textContent=`✨ ${enhCount}/${acts.length} مُحسَّن`;const wrap=document.getElementById('wrap');wrap.innerHTML=indexBlock(DATA.index)+acts.map(actCard).join('');attachEvents();}
function attachEvents(){document.querySelectorAll('.ahead').forEach(h=>{h.addEventListener('click',()=>h.closest('.act').classList.toggle('open'));});document.querySelectorAll('.raw-btn').forEach(b=>{b.addEventListener('click',e=>{e.stopPropagation();b.nextElementSibling.classList.toggle('show');});});document.querySelectorAll('.xref-chip').forEach(chip=>{chip.addEventListener('click',e=>{e.stopPropagation();const domId=chip.dataset.domid;if(domId){const el=document.getElementById(domId);if(el){el.classList.add('open');el.scrollIntoView({behavior:'smooth',block:'center'});el.classList.remove('flash');void el.offsetWidth;el.classList.add('flash');setTimeout(()=>el.classList.remove('flash'),1300);return;}}showRefPanel(chip.dataset);});});}
function showRefPanel(d){const panel=document.getElementById('refPanel');const rel=d.rel||'';const relLabel=({cites:'يستند إلى',amends:'يعدّل',abrogates:'يُلغي',supplements:'يُتمّم',amends_supplements:'يعدّل ويتمّم',implements:'يُطبّق',replaces:'يستبدل'}[rel])||rel;document.getElementById('refPanelTitle').textContent=d.refid||'مرجع قانوني';document.getElementById('refPanelBody').innerHTML=`<div>${row('المعرّف',d.refid)}${row('النوع',d.type)}${row('الرقم',d.num)}${row('التاريخ',d.date)}${row('العلاقة',relLabel)}${row('السياق',d.ctx?`<em style="color:#6a8aaa">${esc(d.ctx)}</em>`:null)}<div style="margin-top:6px;font-size:.72rem;color:#3a4a5a">هذا الإجراء في إصدار جريدة رسمية آخر.</div></div>`;panel.classList.add('show');}
function row(k,v){return v?`<div style="display:flex;gap:8px;padding:3px 0;border-bottom:1px solid #1e2840"><span style="font-size:.7rem;color:#3a4a5a;min-width:70px">${esc(k)}</span><span style="font-size:.78rem;color:#8a9bb5">${v}</span></div>`:''}
document.getElementById('refPanelClose').addEventListener('click',()=>document.getElementById('refPanel').classList.remove('show'));
document.getElementById('q').addEventListener('input',()=>{const q=document.getElementById('q').value.trim();document.querySelectorAll('.act').forEach(card=>{card.style.display=(!q||card.textContent.includes(q))?'':'none';});});
document.getElementById('foldAll').addEventListener('click',()=>document.querySelectorAll('.act').forEach(c=>c.classList.remove('open')));
document.getElementById('expandAll').addEventListener('click',()=>document.querySelectorAll('.act').forEach(c=>c.classList.add('open')));
render();
</script>
</body></html>"""


def do_view(folder):
    """Stage 4: generate viewer2.html"""
    jid = os.path.basename(folder.rstrip("/\\"))
    ef = os.path.join(folder, "structure_A.enhanced.json")
    af = os.path.join(folder, "structure_A.json")
    data_file = ef if os.path.exists(ef) else af
    if not os.path.exists(data_file):
        raise FileNotFoundError(f"Run 'structure' first — no JSON found in {folder}")
    data = json.load(open(data_file, encoding="utf-8"))
    payload = json.dumps(data, ensure_ascii=False)
    page = _VIEWER_TEMPLATE.replace("__JID__", html.escape(jid)).replace("__DATA__", payload)
    dest = os.path.join(folder, "viewer2.html")
    open(dest, "w", encoding="utf-8").write(page)
    print(f"[view] {jid}: viewer → {dest}")
    return dest


# ============================================================
#  CLI
# ============================================================

def _resolve_folders(args_folders, all_flag):
    if all_flag:
        folders = sorted(f for f in glob.glob("JO-*/") if os.path.isdir(f))
        if not folders:
            raise FileNotFoundError("No JO-*/ directories found. Run from the project root.")
        return folders
    if not args_folders:
        raise ValueError("Provide a folder path or use --all")
    return args_folders


def cmd_structure(args):
    folders = _resolve_folders(args.folder, args.all)
    for f in folders:
        do_structure(f)


def cmd_enhance(args):
    global _groq_model
    if args.model:
        _groq_model = args.model
    folders = _resolve_folders(args.folder, args.all)
    for f in folders:
        do_enhance(f, limit=args.limit, force=args.force,
                   delay=args.delay, api_key=args.key)


def cmd_infer(args):
    folders = _resolve_folders(args.folder, args.all)
    for f in folders:
        do_infer(f)


def cmd_view(args):
    folders = _resolve_folders(args.folder, args.all)
    for f in folders:
        do_view(f)


def cmd_run(args):
    """Full pipeline: structure → enhance → infer → view"""
    global _groq_model
    if args.model:
        _groq_model = args.model
    folders = _resolve_folders(args.folder, args.all)
    print(f"Running full pipeline on {len(folders)} folder(s).")
    for f in folders:
        print(f"\n{'─'*50}\n{f.rstrip('/')}\n{'─'*50}")
        do_structure(f)
        do_enhance(f, limit=args.limit, force=args.force,
                   delay=args.delay, api_key=args.key)
        do_infer(f)
        do_view(f)
    print("\nDone.")


def cmd_test(args):
    """
    Smoke test — no API key needed.
    Runs structure + view only; checks losslessness and HTML output.
    """
    folders = _resolve_folders(args.folder, getattr(args, "all", False))
    ok = fail = 0
    for f in folders:
        jid = os.path.basename(f.rstrip("/\\"))
        try:
            result = do_structure(f)
            assert result["stats"]["lossless"], "lossless check failed"
            dest = do_view(f)
            size = os.path.getsize(dest)
            assert size > 5000, f"viewer too small ({size} bytes)"
            print(f"  PASS  {jid}  ({result['stats']['acts']} acts, viewer {size//1024}KB)")
            ok += 1
        except Exception as e:
            print(f"  FAIL  {jid}: {e}")
            fail += 1
    print(f"\nTest result: {ok} passed, {fail} failed")
    if fail:
        sys.exit(1)


def main():
    p = argparse.ArgumentParser(
        prog="pipeline.py",
        description="JORADP Legal Act Structuring Pipeline",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
examples:
  python pipeline.py run   JO-1968-094/ --key gsk_YOUR_KEY
  python pipeline.py run   --all        --key gsk_YOUR_KEY
  python pipeline.py structure JO-1968-094/
  python pipeline.py enhance   JO-1968-094/ --key gsk_…
  python pipeline.py infer     --all
  python pipeline.py view      --all
  python pipeline.py test      JO-1968-094/
        """)

    sub = p.add_subparsers(dest="cmd", required=True)

    def add_folder_args(sp):
        sp.add_argument("folder", nargs="*", help="JO-YYYY-NNN/ folder(s)")
        sp.add_argument("--all", action="store_true", help="Process all JO-*/ folders")

    def add_llm_args(sp):
        sp.add_argument("--key",   help="Groq API key (or set GROQ_API_KEY env var)")
        sp.add_argument("--model", default=None,
                        help=f"Groq model (default: {_GROQ_DEFAULT_MODEL})")
        sp.add_argument("--delay", type=float, default=1.0,
                        help="Seconds between LLM calls (default: 1.0)")
        sp.add_argument("--force", action="store_true",
                        help="Re-enhance even already-processed acts")
        sp.add_argument("--limit", type=int, default=None,
                        help="Only process first N acts (smoke test)")

    # structure
    sp = sub.add_parser("structure", help="Stage 1: parse OCR → structure_A.json")
    add_folder_args(sp)
    sp.set_defaults(func=cmd_structure)

    # enhance
    sp = sub.add_parser("enhance", help="Stage 2: LLM cleanup → structure_A.enhanced.json")
    add_folder_args(sp)
    add_llm_args(sp)
    sp.set_defaults(func=cmd_enhance)

    # infer
    sp = sub.add_parser("infer", help="Stage 3: deterministic cross-reference post-processing")
    add_folder_args(sp)
    sp.set_defaults(func=cmd_infer)

    # view
    sp = sub.add_parser("view", help="Stage 4: generate viewer2.html")
    add_folder_args(sp)
    sp.set_defaults(func=cmd_view)

    # run (full pipeline)
    sp = sub.add_parser("run", help="Full pipeline: structure → enhance → infer → view")
    add_folder_args(sp)
    add_llm_args(sp)
    sp.set_defaults(func=cmd_run)

    # test
    sp = sub.add_parser("test", help="Smoke test (no API key needed)")
    add_folder_args(sp)
    sp.set_defaults(func=cmd_test)

    args = p.parse_args()
    try:
        args.func(args)
    except (FileNotFoundError, ValueError) as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
