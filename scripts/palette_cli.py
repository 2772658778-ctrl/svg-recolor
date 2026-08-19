# -*- coding: utf-8 -*-
"""色彩库 CLI：生成/取色/刷新索引/预览。

用法：
  python scripts/palette_cli.py list                          # 列出全部配色与皮肤
  python scripts/palette_cli.py generate --seed #0ea5e9 --rule triadic --name 我的方案
  python scripts/palette_cli.py ramp --seed #0ea5e9           # 打印 50-950 色阶
  python scripts/palette_cli.py extract --image fig.png --n 6 --name 论文配色
  python scripts/palette_cli.py refresh                       # 重建 _index.json
  python scripts/palette_cli.py preview --out preview.html    # 生成配色预览 HTML
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import palette_kit as PK


def cmd_list(args):
    idx = PK.list_all()
    print(f"配色 {len(idx['palettes'])} 套 / 皮肤 {len(idx['skins'])} 个")
    cur = None
    for p in idx["palettes"]:
        if p["category"] != cur:
            cur = p["category"]
            print(f"\n[{cur}]")
        tags = ",".join(p["tags"][:3])
        print(f"  {p['id']:<24} {p['name']}  ({p['colors']}色, {p['license']}, {tags})")
    print("\n[style]")
    for s in idx["skins"]:
        print(f"  {s['id']:<24} {s['name']}")


def cmd_generate(args):
    p = PK.generate_palette(args.seed, args.rule, name=args.name)
    print(f"已生成 -> {p['id']}: {p['colors']}")
    print("刷新索引后生效: python scripts/palette_cli.py refresh")


def cmd_ramp(args):
    ramp = PK.make_ramp(args.seed)
    for k in PK._RAMP_KEYS:
        print(f"  {k}: {ramp[k]}")
    print(json.dumps(ramp, ensure_ascii=False, indent=2))


def cmd_extract(args):
    cols = PK.extract_from_image(args.image, args.n)
    for c in cols:
        print(f"  {c['hex']}  freq={c['freq']}")
    if args.name:
        palette = PK.build_palette(
            [c["hex"] for c in cols], args.name.strip().lower().replace(" ", "_"),
            args.name, "generated",
            tags=["extracted"], note=f"来源图片 {Path(args.image).name}",
        )
        path = PK.save_palette(palette)
        print(f"已保存 -> {path}")


def cmd_refresh(args):
    p = PK.refresh_index()
    print(f"已刷新索引 -> {p}")


def cmd_preview(args):
    idx = PK.list_all()
    html = ["<!DOCTYPE html><html lang='zh-CN'><head><meta charset='utf-8'>",
            "<title>科研绘图配色库</title><style>",
            "body{font-family:system-ui,sans-serif;background:#f5f7fa;margin:24px;color:#1f2937}",
            "h1{font-size:18px}h2{font-size:14px;color:#374151;margin:26px 0 8px}",
            ".p{border:1px solid #e5e7eb;border-radius:10px;padding:10px;margin:8px 0;background:#fff}",
            ".sw{display:flex;border-radius:6px;overflow:hidden;height:34px}",
            ".sw span{flex:1;height:100%}",
            ".meta{font-size:11px;color:#6b7280;margin-top:6px}",
            "</style></head><body><h1>科研绘图 · 配色库</h1>"]
    cur = None
    for p in idx["palettes"]:
        if p["category"] != cur:
            cur = p["category"]
            html.append(f"<h2>{cur}</h2>")
        d = PK.load_palette(p["id"])
        sw = "".join(f"<span style='background:{c}' title='{c}'></span>" for c in d["colors"])
        html.append(f"<div class='p'><div class='sw'>{sw}</div>"
                    f"<div class='meta'>{d['name']} · {d['id']} · {len(d['colors'])}色 · {d['source'].get('license','')}</div></div>")
    out = args.out or (PK.PALETTES_DIR / "preview.html")
    Path(out).write_text("".join(html), encoding="utf-8")
    print(f"预览已生成 -> {out}")


def main():
    ap = argparse.ArgumentParser(description="科研绘图色彩库工具")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("list")
    g = sub.add_parser("generate")
    g.add_argument("--seed", required=True, help="种子色 #RRGGBB")
    g.add_argument("--rule", default="triadic",
                   choices=["analogous", "complementary", "split-complementary", "triadic", "tetradic", "monochromatic"])
    g.add_argument("--name", default="", help="方案名（空则自动）")
    r = sub.add_parser("ramp")
    r.add_argument("--seed", required=True)
    e = sub.add_parser("extract")
    e.add_argument("--image", required=True, help="图片路径")
    e.add_argument("--n", type=int, default=6)
    e.add_argument("--name", default="")
    sub.add_parser("refresh")
    p = sub.add_parser("preview")
    p.add_argument("--out", default="")
    args = ap.parse_args()
    {"list": cmd_list, "generate": cmd_generate, "ramp": cmd_ramp,
     "extract": cmd_extract, "refresh": cmd_refresh, "preview": cmd_preview}[args.cmd](args)


if __name__ == "__main__":
    main()
