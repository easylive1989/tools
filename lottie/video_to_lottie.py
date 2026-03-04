#!/usr/bin/env python3

import argparse
import base64
import io
import json
import math
import os
import sys

import cv2
from PIL import Image


def extract_frames(cap, times, output_scale, quality):
    frames = []
    for t in times:
        cap.set(cv2.CAP_PROP_POS_MSEC, t * 1000)
        ret, frame = cap.read()
        if not ret:
            continue
        img = Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
        w = int(img.width * output_scale)
        h = int(img.height * output_scale)
        img = img.resize((w, h), Image.LANCZOS)
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=quality)
        b64 = base64.b64encode(buf.getvalue()).decode()
        frames.append((w, h, f"data:image/jpeg;base64,{b64}"))
    return frames


def build_lottie(frames, frame_rate, name):
    if not frames:
        return {}
    w, h, _ = frames[0]
    w2 = w // 2
    h2 = h // 2
    num_frames = len(frames)

    assets = []
    layers = []
    for i, (_, _, data_url) in enumerate(frames):
        fid = f"fr_{i}"
        assets.append({"id": fid, "w": w, "h": h, "u": "", "p": data_url, "e": 1})
        layers.append({
            "ddd": 0, "ind": i + 1, "ty": 2, "nm": f"{fid}.jpg",
            "cl": "jpg", "refId": fid, "sr": 1,
            "ks": {
                "o": {"a": 0, "k": 100, "ix": 11},
                "r": {"a": 0, "k": 0, "ix": 10},
                "p": {"a": 0, "k": [w2, h2, 0], "ix": 2},
                "a": {"a": 0, "k": [w2, h2, 0], "ix": 1},
                "s": {"a": 0, "k": [100, 100, 100], "ix": 6},
            },
            "ao": 0, "ip": i, "op": i + 1, "st": i, "bm": 0,
        })

    return {
        "v": "5.5.2", "fr": frame_rate, "ip": 0, "op": num_frames,
        "w": w, "h": h, "nm": name, "ddd": 0,
        "assets": assets, "layers": layers, "markers": [],
    }


def main():
    parser = argparse.ArgumentParser(description="Convert video to Lottie JSON animation.")
    parser.add_argument("input", help="Input video file")
    parser.add_argument("-o", "--output", help="Output .lottie.json path")
    parser.add_argument("--frames", type=int, default=30)
    parser.add_argument("--scale", type=float, default=0.5)
    parser.add_argument("--quality", type=int, default=80)
    parser.add_argument("--start", type=float, default=0.0)
    parser.add_argument("--end", type=float, default=None)
    parser.add_argument("--fps", type=int, default=None, help="Output frame rate (default: auto from frames/duration)")
    args = parser.parse_args()

    cap = cv2.VideoCapture(args.input)
    if not cap.isOpened():
        sys.exit(f"Cannot open video: {args.input}")

    fps = cap.get(cv2.CAP_PROP_FPS)
    total_frames = cap.get(cv2.CAP_PROP_FRAME_COUNT)
    duration = total_frames / fps if fps else 0

    clip_start = args.start
    clip_end = args.end if args.end is not None else duration
    if clip_end <= clip_start:
        sys.exit("--end must be greater than --start")

    clip_duration = clip_end - clip_start
    num_frames = args.frames
    times = [
        i * (clip_duration / (max(2, num_frames) - 1)) + clip_start
        for i in range(num_frames)
    ]

    print(f"Extracting {num_frames} frames ({clip_start:.1f}s - {clip_end:.1f}s), scale={args.scale}")
    frames = extract_frames(cap, times, args.scale, args.quality)
    cap.release()

    if not frames:
        sys.exit("No frames extracted")

    frame_rate = args.fps or max(1, math.floor(num_frames / clip_duration))
    stem = os.path.splitext(os.path.basename(args.input))[0]
    lottie = build_lottie(frames, frame_rate, stem)

    output = args.output or os.path.splitext(args.input)[0] + ".lottie.json"
    with open(output, "w") as f:
        json.dump(lottie, f)
    print(f"Saved {output} ({len(frames)} frames, {os.path.getsize(output) / 1024:.0f} KB)")


if __name__ == "__main__":
    main()
