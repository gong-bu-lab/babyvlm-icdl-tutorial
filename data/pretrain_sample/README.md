# Pretraining sample data

Feeds the **Pretraining Data** section of `dataset.html`. One directory per
data source × format:

```
pretrain_sample/<source>/<format>/
  data.json
  media/
  MANIFEST.json      # provenance — which upstream file each item came from
```

`<source>` is `saycam` or `babyview`; `<format>` is `single_image`,
`video_clip`, or `multi_turn`. All six hold 3 hand-picked items each.

## Upstream sources

| | single_image | video_clip | multi_turn |
|---|---|---|---|
| **saycam**   | `SAYCam_pretrain/single_image.json` | `filtered_speech.json` (real mp4) | `SAYCam_pretrain/interleaved.json` |
| **babyview** | `BabyView_pretrain/single_image.json` | `BabyView_pretrain/multi_image.json` (8 frames) | `BabyView_pretrain/interleaved.json` |

Roots:
`/projectnb/ivc-ml/wsashawn/LLaVA/playground/data/` and
`/projectnb/ivc-ml/maxwh/code/senses/touch/public_repo/data/jsons/filtered_speech.json`.

SAYCam video clips are genuine 2s / 640×480 mp4s, so they play as video.
BabyView has no mp4 set, so its clips are the 8-frame windows shown through the
frame scrubber. Both are labelled "Video clips" in the UI.

The paired language throughout is **transcribed speech from the recordings** —
not templated captions.

## data.json

Same shape as the toolbox samples, so the explorer's renderers are shared:

```jsonc
{
  "id": "saycam_clip_0",
  "image": ["media/clip_0000.jpg"],   // relative to this directory
  "video": "media/clip_0000.mp4",     // optional; real mp4 → <video> player
  "conversations": [
    { "from": "human", "value": "<image>" },
    { "from": "gpt", "value": "which the two letters are still in the puzzle" }
  ],
  "meta": { "subject": "A", "recorded": "2014-12-13", "clip": "A_20141213_..." }
}
```

The renderer picks its layout from the data:

- **`video` present** → an inline `<video>` player, poster from `image[0]`.
- **one image, no video** → image left, paired language right.
- **several images** → the scrubbing frame player.
- **more than one `human` turn** → turns stacked in order, images interleaved
  at their `<image>` tokens.

`meta` is optional; whichever of `subject` / `recorded` / `frame` / `clip` are
present become the provenance strip at the foot of the modal.

## Adding a format

1. Write the directory above.
2. Add its `"<source>/<format>"` key to `PT_READY` in `dataset.html`.

Until that key is added the grid shows an "awaiting data" placeholder instead of
a failed fetch.

## Rebuilding

```
python3 data/build_pretrain_sample.py
```

The upstream files are 100–470MB of pretty-printed JSON, so they are streamed
record-by-record and sampled with a reservoir — seeded per source×format, so
SAYCam's single-image and video-clip picks don't collide. One item per
recording, so a grid isn't nine views of one afternoon. Stills are downscaled to
fit 800px (BabyView ships 1080×1920, ~470KB each).

## Curation & face screening

The published 18 items are **hand-picked**, not sampled. Selection ran in two
stages:

1. **Automated pre-filter.** A wide reservoir (2,500 records per combination)
   was screened with four Haar cascades (frontal-default / alt / alt2 / profile,
   each also run mirrored, tuned deliberately sensitive). Any item where *any*
   frame tripped a detector was dropped. Rejection ran 70–99%.
2. **Manual review — the actual gate.** Every surviving frame was inspected by
   eye, including decoding each candidate mp4 frame-by-frame, because the poster
   still is not representative of the whole clip.

**The cascades are not sufficient on their own.** They cleared several frames
containing plainly visible faces — in the worst case a clip scoring *zero*
detections across every sampled frame showed an adult face throughout. They also
flag heavily on texture, toys and TV content. Treat detection as a way to narrow
the field, never as the decision.

Picks are pinned by upstream record id in `PICKS` in
`data/build_pretrain_sample.py`, so a rebuild reproduces them exactly and
hard-errors if a record can't be found rather than silently drifting.

**If you add or swap items, screen them the same way**, and record any rejected
media in `BLOCKED`.

## Publication status

Face screening is done, but the underlying question is not: confirm the SAYCam
(Databrary) and BabyView data use agreements permit publishing frames on a
public site before this section goes live.
