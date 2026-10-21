"""Phase 19: one image from the final review (off by default, --image-from-review).

Only the review may call make_image(); routed steps are text only. One image per run (MAX_IMAGES_PER_RUN, a
constant). The key comes from the environment only. The image is saved in the private run folder, plus a copy
stamped with the owner's mark. Marks live OUTSIDE the V1rG0 folder (/workspace/V1rG0_assets, or V1RG0_MARK_DIR) so they
never ship: the pair deux_symbol_black.png / deux_symbol_white.png, picked per image by the corner's
brightness. V1RG0_MARK_FILE forces one file. The mark is only shrunk: no smoothing, sharpening or cleanup.
Every description gets SAFETY_LINE appended in code, so no system can drop it."""
import base64
import hashlib
import json
import os
import re
from urllib.parse import urlparse

import requests

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
IMAGE_PROVIDERS_FILE = os.path.join(ROOT, "V1rG0_specific", "v1rg0_image_providers.json")
MARK_DIR = os.path.join(os.path.dirname(ROOT), "V1rG0_assets")
MARK_BLACK, MARK_WHITE = "deux_symbol_black.png", "deux_symbol_white.png"
SAFETY_LINE = ("Original artwork only: no real artist's style by name, no brands or logos, "
               "no known or trademarked characters, no real people.")
MAX_IMAGES_PER_RUN = 1
_BLOCK_RE = re.compile(r"IMAGE_DESCRIPTION\W*\n(.*?)\n[\W_]*END_IMAGE", re.S)

IMAGE_ASK = ("After your answer, describe ONE image to make, in plain words, in exactly this block:\n"
             "IMAGE_DESCRIPTION:\n<one paragraph, at most {max_chars} characters>\nEND_IMAGE\n"
             "Never name real brands, logos, trademarked characters, real people, or any artist or their style. "
             "Do not ask for text, signatures or watermarks in the image.")


class ImageStepError(Exception):
    pass


def load_image_providers(path=None):
    with open(path or os.environ.get("V1RG0_IMAGE_PROVIDERS_FILE", IMAGE_PROVIDERS_FILE), "r", encoding="utf-8") as f:
        return json.load(f)


def parse_image_block(text):
    """Exactly one IMAGE_DESCRIPTION block -> (description, None), else (None, reason)."""
    found = _BLOCK_RE.findall(str(text or ""))
    if not found:
        return None, "no IMAGE_DESCRIPTION block"
    if len(found) > 1:
        return None, f"{len(found)} IMAGE_DESCRIPTION blocks (exactly one allowed)"
    desc = " ".join(found[0].split())
    if not desc:
        return None, "empty IMAGE_DESCRIPTION block"
    return desc, None


def desc_limit(cfg):
    """Room left for the review's description once SAFETY_LINE is added."""
    return int(cfg.get("max_prompt_chars", 1000)) - len(SAFETY_LINE) - 1


def full_prompt(desc):
    return f"{desc} {SAFETY_LINE}"


def check_description(desc, cfg, blocked_terms):
    limit = desc_limit(cfg)
    if len(desc) > limit:
        return f"description is {len(desc)} characters (limit {limit})"
    low = desc.lower()
    hits = [t for t in blocked_terms if re.search(r"\b" + re.escape(t.lower()) + r"\b", low)]   # whole words only
    if hits:
        return f"description names blocked term(s) {hits}"
    return None


def _kind_of(data):
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "png"
    if data[:3] == b"\xff\xd8\xff":
        return "jpg"
    return None


def _host_ok(url, hosts):
    u = urlparse(url)
    h = (u.hostname or "").lower()
    return u.scheme == "https" and any(h == x or h.endswith("." + x) for x in hosts)


def make_image(label, desc, cfg, images_made):
    """One HTTP call. Returns (bytes, ext, returned_model). Refuses anything but the review."""
    if label != "review":
        raise ImageStepError(f"image call refused: only the final review may make an image (got {label!r})")
    if images_made >= MAX_IMAGES_PER_RUN:
        raise ImageStepError(f"image call refused: {MAX_IMAGES_PER_RUN} image per run already made")
    key = os.environ.get(cfg["env_key"])
    if not key:
        raise ImageStepError(f"{cfg['env_key']} is not set")
    r = requests.post(cfg["url"], headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
                      json={"model": cfg["model"], "prompt": full_prompt(desc), "n": 1}, timeout=120)
    r.raise_for_status()
    body = r.json()
    item = ((body or {}).get("data") or [None])[0] or {}
    max_bytes = int(cfg.get("max_bytes", 20_000_000))
    if item.get("b64_json"):
        data = base64.b64decode(item["b64_json"])
    elif item.get("url"):
        if not _host_ok(item["url"], cfg.get("download_hosts", [])):
            raise ImageStepError("image link refused: not an https link on an allowed host")
        g = requests.get(item["url"], timeout=120, stream=True, allow_redirects=False)   # a redirect can't leave x.ai
        if getattr(g, "status_code", 200) != 200:
            raise ImageStepError(f"image link refused: download answered {g.status_code}, not 200 (redirects not followed)")
        g.raise_for_status()
        chunks, size = [], 0
        for c in g.iter_content(65536):
            size += len(c)
            if size > max_bytes:
                raise ImageStepError(f"image larger than {max_bytes} bytes")
            chunks.append(c)
        data = b"".join(chunks)
    else:
        raise ImageStepError("provider returned no image")
    if len(data) > max_bytes:
        raise ImageStepError(f"image larger than {max_bytes} bytes")
    ext = _kind_of(data)
    if not ext:
        raise ImageStepError("returned file is not a PNG or JPEG")
    rm = body.get("model") if isinstance(body.get("model"), str) else None
    return data, ext, rm


def _write_new_bytes(path, data):
    with open(path, "xb") as f:                     # never overwrite
        f.write(data)


def _box(base, mark_size, width_frac, margin_frac):
    w = max(16, int(base.width * width_frac))
    h = max(1, int(mark_size[1] * w / mark_size[0]))
    m = int(base.width * margin_frac)
    return w, h, m


def pick_mark(image_path, width_frac=0.08, margin_frac=0.02):
    """Forced file (V1RG0_MARK_FILE) if set; else black on a light corner, white on a dark one. None if missing."""
    forced = os.environ.get("V1RG0_MARK_FILE")
    if forced:
        return forced if os.path.isfile(forced) else None
    d = os.environ.get("V1RG0_MARK_DIR", MARK_DIR)
    black, white = os.path.join(d, MARK_BLACK), os.path.join(d, MARK_WHITE)
    if not (os.path.isfile(black) and os.path.isfile(white)):
        return None
    from PIL import Image, ImageStat
    with Image.open(black) as mk:
        size = mk.size
    with Image.open(image_path) as base:
        w, h, m = _box(base, size, width_frac, margin_frac)
        corner = base.convert("L").crop((base.width - w - m, base.height - h - m, base.width - m, base.height - m))
        light = ImageStat.Stat(corner).mean[0] >= 128
    return black if light else white


def stamp(image_path, mark_path, out_path, width_frac=0.08, margin_frac=0.02):
    """Paste the owner's mark small in the bottom-right corner, same size and spot every time.
    The mark is only shrunk (plain area-average resize): no smoothing, sharpening or cleanup."""
    from PIL import Image
    with Image.open(image_path) as base, Image.open(mark_path) as mark:
        base = base.convert("RGBA")
        mark = mark.convert("RGBA")
        w, h, m = _box(base, mark.size, width_frac, margin_frac)
        mark = mark.resize((w, h), Image.Resampling.BOX)
        base.alpha_composite(mark, (base.width - w - m, base.height - h - m))
        if os.path.exists(out_path):
            raise FileExistsError(out_path)
        base.convert("RGB").save(out_path, "PNG")


# ---- Phase 20: exact card text added by code (image models misspell words) ----
FONT_FILE = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"     # free DejaVu licence; V1RG0_FONT_FILE overrides
MAX_TEXT_CHARS = 120
TEXT_NOTE = ("Card text is added afterward by code, above and below the picture. Do not put any words, letters "
             "or numbers in the image itself.")


def load_card_text(path):
    """File with 'TOP: ...' and/or 'BOTTOM: ...' lines -> {"top": str, "bottom": str}. Raises ImageStepError."""
    out = {}
    with open(path, "r", encoding="utf-8") as f:
        for n, raw in enumerate(f, 1):
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            m = re.match(r"^(TOP|BOTTOM)\s*:\s*(.+)$", line)
            if not m:
                raise ImageStepError(f"card text line {n}: must start with TOP: or BOTTOM:")
            key, val = m.group(1).lower(), m.group(2).strip()
            if key in out:
                raise ImageStepError(f"card text: {m.group(1)} given twice")
            if len(val) > MAX_TEXT_CHARS:
                raise ImageStepError(f"card text {m.group(1)} is {len(val)} characters (limit {MAX_TEXT_CHARS})")
            if any(ord(c) < 32 for c in val):
                raise ImageStepError(f"card text {m.group(1)} has control characters")
            out[key] = val
    if not out:
        raise ImageStepError("card text file has no TOP: or BOTTOM: line")
    return out


def _font_path():
    f = os.environ.get("V1RG0_FONT_FILE", FONT_FILE)
    if not os.path.isfile(f):
        raise ImageStepError(f"font file not found: {f}")
    return f


def _wrap(draw, text, font, max_w):
    lines, cur = [], ""
    for word in text.split():
        trial = (cur + " " + word).strip()
        if cur and draw.textlength(trial, font=font) > max_w:
            lines.append(cur); cur = word
        else:
            cur = trial
    lines.append(cur)
    return lines


def add_card_text(image_path, texts, out_path, band="black", ink="white"):
    """New canvas: band with TOP text, the picture untouched, band with BOTTOM text. Exact wording, plain font."""
    from PIL import Image, ImageDraw, ImageFont
    with Image.open(image_path) as im:
        im = im.convert("RGB")
        W, H = im.size
        font = ImageFont.truetype(_font_path(), max(14, int(W * 0.042)))
        probe = ImageDraw.Draw(Image.new("RGB", (1, 1)))
        max_w, pad = int(W * 0.80), int(W * 0.035)
        line_h = int(font.size * 1.3)
        blocks = {k: _wrap(probe, texts[k], font, max_w) for k in ("top", "bottom") if texts.get(k)}
        band_h = {k: pad * 2 + line_h * len(v) for k, v in blocks.items()}
        top_h, bot_h = band_h.get("top", 0), band_h.get("bottom", 0)
        canvas = Image.new("RGB", (W, top_h + H + bot_h), band)
        canvas.paste(im, (0, top_h))
        d = ImageDraw.Draw(canvas)
        for k, y0 in (("top", 0), ("bottom", top_h + H)):
            for i, ln in enumerate(blocks.get(k, [])):
                d.text((W / 2, y0 + pad + line_h * i + line_h / 2), ln, font=font, fill=ink, anchor="mm")
        if os.path.exists(out_path):
            raise FileExistsError(out_path)
        canvas.save(out_path, "PNG")


def run_image_step(review_text, run_dir, tag, provider_name, images_made, card_text=None):
    """Called once, from the review branch only. Returns the summary entry (never raises for normal refusals)."""
    entry = {"provider": provider_name, "made": False}
    try:
        conf = load_image_providers()
        cfg = conf["providers"][provider_name]
        entry.update({"model": cfg["model"], "price_per_image": cfg.get("price_per_image")})
        desc, why = parse_image_block(review_text)
        if why:
            entry["refused"] = why
            return entry
        why = check_description(desc, cfg, conf.get("blocked_terms", []))
        entry["description"] = desc
        entry["safety_line_added"] = True
        if why:
            entry["refused"] = why
            return entry
        data, ext, rm = make_image("review", desc, cfg, images_made)
        path = os.path.join(run_dir, f"image_{tag}.{ext}")
        _write_new_bytes(path, data)
        entry.update({"made": True, "file": path, "sha256": hashlib.sha256(data).hexdigest(), "returned_model": rm})
        mark = pick_mark(path)
        if mark:
            entry["mark_used"] = os.path.basename(mark)
            spath = os.path.join(run_dir, f"image_{tag}_marked.png")
            stamp(path, mark, spath)
            entry.update({"marked_file": spath, "marked_sha256": hashlib.sha256(open(spath, "rb").read()).hexdigest()})
        else:
            entry["marked_file"] = None
            entry["mark_note"] = "no mark file, so no stamped copy"
        if card_text:                                          # Phase 20: text copies, the clean image stays untouched
            tpath = os.path.join(run_dir, f"image_{tag}_text.png")
            add_card_text(path, card_text, tpath)
            entry.update({"card_text": card_text, "text_file": tpath,
                          "text_sha256": hashlib.sha256(open(tpath, "rb").read()).hexdigest()})
            if entry.get("marked_file"):                       # mark stays on the picture's corner, clear of the text
                tm = os.path.join(run_dir, f"image_{tag}_text_marked.png")
                add_card_text(entry["marked_file"], card_text, tm)
                entry.update({"text_marked_file": tm,
                              "text_marked_sha256": hashlib.sha256(open(tm, "rb").read()).hexdigest()})
    except (ImageStepError, requests.RequestException, KeyError, ValueError, OSError) as e:
        entry["error"] = f"{type(e).__name__}: {e}"
    return entry
