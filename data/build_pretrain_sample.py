#!/usr/bin/env python3
"""Sample the BabyVLM pretraining corpus into data/pretrain_sample/.

Six directories — {saycam, babyview} x {single_image, video_clip, multi_turn} —
each holding a data.json in the same shape the toolbox samples use, the media it
references, and a MANIFEST.json recording provenance.

The upstream files are 100-470MB of pretty-printed JSON, so they are streamed
object-by-object rather than loaded whole, and sampled with a reservoir.

Usage:  python3 data/build_pretrain_sample.py
"""

import json
import os
import random
import re
import shutil
import subprocess

SEED = 42
N_ITEMS = 3          # published per source x format
POOL = 900           # reservoir size to screen down from
MAX_EDGE = 800       # BabyView ships 1080x1920 stills; that's far more than a
QUALITY = 82         # web grid needs, so copies are downscaled on the way in.

HERE = os.path.dirname(os.path.abspath(__file__))
OUT_ROOT = os.path.join(HERE, "pretrain_sample")

PRETRAIN = "/projectnb/ivc-ml/wsashawn/LLaVA/playground/data"
CLIP_JSON = ("/projectnb/ivc-ml/maxwh/code/senses/touch/public_repo/data/jsons/"
             "filtered_speech.json")
SAYCAM_FRAMES = ("/projectnb/ivc-ml/ac25/BabyFM/SAYCam_Dataset/"
                 "pretraining_dataset_raw/image")

# source -> format -> upstream file. SAYCam video clips come from the mp4 set
# (real 2s/640x480 video); BabyView has no mp4s, so its clips are the 4-frame
# multi_image windows played through the frame scrubber.
SOURCES = {
    "saycam": {
        "single_image": f"{PRETRAIN}/SAYCam_pretrain/single_image.json",
        "video_clip":   CLIP_JSON,
        "multi_turn":   f"{PRETRAIN}/SAYCam_pretrain/interleaved.json",
    },
    "babyview": {
        "single_image": f"{PRETRAIN}/BabyView_pretrain/single_image.json",
        "video_clip":   f"{PRETRAIN}/BabyView_pretrain/multi_image.json",
        "multi_turn":   f"{PRETRAIN}/BabyView_pretrain/interleaved.json",
    },
}

# Frame/clip stems:
#   SAYCam    A_20130531_0818_01_76680_77720_frame_1
#   BabyView  S00220001_2024-03-19_1_rec5Xau..._354743_372111_frame_1
SAYCAM_RE = re.compile(r"^([SAY])_(\d{4})(\d{2})(\d{2})_(\d+_\d+)_(\d+_\d+)_frame")
BABYVIEW_RE = re.compile(r"^(\w+?)_(\d{4}-\d{2}-\d{2})_")

# These are home recordings, so published stills are screened for faces. The
# blocklist holds specific media rejected on visual review; see README.
BLOCKED = set()

# Hand-curated finals. Each entry is the upstream item's identity — the record
# `id` for the pretrain JSONs, the clip stem for filtered_speech.json. Every
# frame behind these was run through four face cascades AND reviewed by eye.
# Empty list => fall back to seeded sampling.
PICKS = {
    "saycam/single_image": [
        "647645",
        "311577",
        "370761",
    ],
    "saycam/video_clip": [
        "Y_20200118_2304_02_816320_816880_frame2",
        "Y_20181218_1004_01_226340_229700_frame2",
        "Y_20190208_1125_03_317400_326920_frame4",
    ],
    "saycam/multi_turn": [
        "1007966",
        "975069",
        "983482",
    ],
    "babyview/single_image": [
        "353689",
        "321694",
        "1005699",
    ],
    "babyview/video_clip": [
        "52918",
        "66809",
        "160535",
    ],
    "babyview/multi_turn": [
        "1429110",
        "1409274",
        "1400252",
    ],
}


def item_key(item, stem, is_clip_json):
    """Stable identity for an upstream record, used by PICKS."""
    return stem if is_clip_json else str(item.get("id"))


def copy_image(src, dst):
    """Copy a still, downscaled to fit MAX_EDGE. Falls back to a plain copy if
    ImageMagick isn't on PATH, so the sample still builds (just heavier)."""
    try:
        subprocess.run(["convert", src, "-resize", f"{MAX_EDGE}x{MAX_EDGE}>",
                        "-quality", str(QUALITY), dst], check=True,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except (FileNotFoundError, subprocess.CalledProcessError):
        shutil.copyfile(src, dst)


def stream_objects(path):
    """Yield top-level objects from a pretty-printed JSON array of objects.

    The upstream files are all written with json.dump(indent=2|4), so a
    top-level record opens on a line that is only '{' at the first indent and
    closes on the matching '}'. Falls back to a hard error if that shape breaks,
    rather than silently yielding nothing.
    """
    buf, depth, seen = [], 0, 0
    with open(path, "r", errors="replace") as fh:
        first = fh.readline()
        if not first.lstrip().startswith("["):
            raise SystemExit(f"{path}: expected a JSON array")
        for line in fh:
            s = line.strip()
            if not buf:
                if not s.startswith("{"):
                    continue
                buf = [line]
                depth = s.count("{") - s.count("}")
                if depth == 0:
                    seen += 1
                    yield json.loads(s.rstrip(","))
                    buf = []
                continue
            buf.append(line)
            depth += s.count("{") - s.count("}")
            if depth <= 0:
                text = "".join(buf).strip().rstrip(",")
                seen += 1
                yield json.loads(text)
                buf = []
    if not seen:
        raise SystemExit(f"{path}: streamed 0 records — format changed?")


def reservoir(iterable, k, rng):
    out = []
    for i, item in enumerate(iterable):
        if i < k:
            out.append(item)
        else:
            j = rng.randrange(i + 1)
            if j < k:
                out[j] = item
    return out


def clip_to_frame(video_path):
    """clips/..._frame1.mp4  ->  the matching SAYCam still ..._frame_1.jpg"""
    stem = os.path.basename(video_path)[:-4]
    m = re.match(r"^(.*)frame(\d+)$", stem)
    if not m:
        return None
    return os.path.join(SAYCAM_FRAMES, f"{m.group(1)}frame_{m.group(2)}.jpg")


def meta_for(source, stem):
    if source == "saycam":
        m = SAYCAM_RE.match(stem)
        if m:
            subj, y, mo, d, sess, _win = m.groups()
            return {"subject": subj, "recorded": f"{y}-{mo}-{d}",
                    "recording": f"{subj}_{y}{mo}{d}_{sess}"}
    else:
        m = BABYVIEW_RE.match(stem)
        if m:
            return {"subject": m.group(1), "recorded": m.group(2)}
    return {}


def group_key(source, stem):
    """One item per recording, so a grid isn't nine views of one afternoon."""
    md = meta_for(source, stem)
    return md.get("recording") or (md.get("subject", "") + md.get("recorded", ""))


def utterance_of(item):
    turns = [c["value"].strip() for c in item.get("conversations", [])
             if c.get("from") == "gpt" and c.get("value", "").strip()]
    return turns[0] if turns else ""


def usable_text(t):
    return 12 <= len(t) <= 220 and len(t.split()) >= 3


def build(source, fmt, src_path):
    rng = random.Random(f"{SEED}-{source}-{fmt}")
    out_dir = os.path.join(OUT_ROOT, source, fmt)
    media_dir = os.path.join(out_dir, "media")
    is_clip_json = src_path == CLIP_JSON

    wanted = PICKS.get(f"{source}/{fmt}") or []
    if wanted:
        # Curated: scan for exactly these records, keep the curator's order.
        found = {}
        for item in stream_objects(src_path):
            if is_clip_json:
                stem = os.path.basename(item.get("video_path", ""))[:-4]
                assets = [item.get("video_path", "")]
                still = clip_to_frame(item.get("video_path", ""))
                if still:
                    assets.append(still)
            else:
                imgs = item.get("image") or []
                stem = os.path.basename(imgs[0])[:-4] if imgs else ""
                assets = list(imgs)
            key = item_key(item, stem, is_clip_json)
            if key in wanted and key not in found:
                found[key] = (item, stem, assets)
                if len(found) == len(wanted):
                    break
        missing = [k for k in wanted if k not in found]
        if missing:
            raise SystemExit(f"{source}/{fmt}: PICKS not found upstream: {missing}")
        picked = [found[k] for k in wanted]
        return write_out(source, fmt, src_path, is_clip_json, picked)

    pool = reservoir(stream_objects(src_path), POOL, rng)

    picked, seen_groups, seen_text = [], set(), set()
    for item in pool:
        if is_clip_json:
            vid = item.get("video_path", "")
            text = (item.get("audio_caption") or "").strip()
            stem = os.path.basename(vid)[:-4]
            still = clip_to_frame(vid)
            assets = [vid] + ([still] if still else [])
            texts = [text]
        else:
            imgs = item.get("image") or []
            texts = [c["value"].strip() for c in item.get("conversations", [])
                     if c.get("from") == "gpt"]
            text = utterance_of(item)
            stem = os.path.basename(imgs[0])[:-4] if imgs else ""
            assets = list(imgs)

        if not stem or not text or not usable_text(text):
            continue
        if any(os.path.basename(a) in BLOCKED for a in assets if a):
            continue
        if not all(a and os.path.exists(a) for a in assets):
            continue
        gk = group_key(source, stem)
        if gk in seen_groups or text in seen_text:
            continue
        # multi-turn should actually show several turns
        if fmt == "multi_turn":
            if len([t for t in texts if t]) < 3:
                continue
            if not all(usable_text(t) for t in texts if t):
                continue
        seen_groups.add(gk)
        seen_text.add(text)
        picked.append((item, stem, assets))
        if len(picked) >= N_ITEMS:
            break

    if len(picked) < N_ITEMS:
        print(f"  !! only {len(picked)}/{N_ITEMS} for {source}/{fmt}")

    return write_out(source, fmt, src_path, is_clip_json, picked)


def write_out(source, fmt, src_path, is_clip_json, picked):
    out_dir = os.path.join(OUT_ROOT, source, fmt)
    media_dir = os.path.join(out_dir, "media")
    if os.path.isdir(out_dir):
        shutil.rmtree(out_dir)
    os.makedirs(media_dir)

    items, manifest = [], []
    for n, (item, stem, assets) in enumerate(picked):
        md = meta_for(source, stem)
        md["clip" if is_clip_json else "frame"] = stem

        if is_clip_json:
            vid, still = assets[0], assets[1]
            vrel = f"media/clip_{n:04d}.mp4"
            irel = f"media/clip_{n:04d}.jpg"
            shutil.copyfile(vid, os.path.join(out_dir, vrel))
            copy_image(still, os.path.join(out_dir, irel))
            rec = {"id": f"{source}_clip_{n}", "image": [irel], "video": vrel,
                   "conversations": [{"from": "human", "value": "<image>"},
                                     {"from": "gpt",
                                      "value": item["audio_caption"].strip()}],
                   "meta": md}
            manifest.append({"source_video": vid, "source_still": still})
        else:
            rels = []
            for k, src in enumerate(assets):
                ext = os.path.splitext(src)[1] or ".jpg"
                rel = f"media/{fmt}_{n:04d}_{k}{ext}"
                copy_image(src, os.path.join(out_dir, rel))
                rels.append(rel)
            rec = {"id": str(item.get("id", n)), "image": rels,
                   "conversations": item["conversations"], "meta": md}
            manifest.append({"id": item.get("id"), "source_images": assets})

        items.append(rec)

    with open(os.path.join(out_dir, "data.json"), "w") as f:
        json.dump(items, f, indent=1)
    with open(os.path.join(out_dir, "MANIFEST.json"), "w") as f:
        json.dump({"source_file": src_path,
                   "seed": f"{SEED}-{source}-{fmt}", "pool": POOL,
                   "data_source": source, "format": fmt,
                   "n_items": len(items), "entries": manifest}, f, indent=2)
    print(f"  {source}/{fmt}: {len(items)} items")
    return len(items)


def main():
    total = 0
    for source, formats in SOURCES.items():
        for fmt, path in formats.items():
            print(f"streaming {os.path.basename(path)} for {source}/{fmt} …",
                  flush=True)
            total += build(source, fmt, path)
    print(f"done — {total} items across {OUT_ROOT}")


if __name__ == "__main__":
    main()
