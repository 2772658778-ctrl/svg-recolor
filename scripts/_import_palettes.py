# -*- coding: utf-8 -*-
"""主线1：从成熟开源源导入更多配色到 palettes/（一次性脚本，可缓存）。

来源：
- Crameri Scientific Colour Maps（cmcrameri，MIT）—— 科研色图金标准，31 个
- cmocean（matplotlib/cmocean，MIT）—— 22 个
- ColorBrewer 补全（Apache-2.0）—— 内嵌标准 hex
- Tailwind CSS v3.4 全色相（MIT）—— 22 个色相 ramp

运行：python scripts/_import_palettes.py
"""
from __future__ import annotations

import json
import os
import re
import sys
import time
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import palette_kit as PK

CACHE = Path(__file__).resolve().parent / "_data_cache"
CACHE.mkdir(exist_ok=True)


def fetch(url: str, name: str, retries: int = 4) -> str:
    cache = CACHE / name
    if cache.exists():
        return cache.read_text(encoding="utf-8")
    for i in range(retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            data = urllib.request.urlopen(req, timeout=30).read().decode("utf-8", "replace")
            cache.write_text(data, encoding="utf-8")
            return data
        except Exception as e:  # noqa: BLE001
            print(f"  [retry {i + 1}] {url}  {e}")
            time.sleep(1.5 * (i + 1))
    raise RuntimeError(f"获取失败: {url}")


# ---------------------------------------------------------------- 解析
def parse_rgb_table(text: str, levels: int = 11) -> list[str]:
    """解析每行 'R G B'（0-1 浮点）的色表，等距采样 levels 级。"""
    rows = []
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or line.startswith("B"):
            continue
        parts = re.split(r"\s+", line)
        if len(parts) >= 3:
            try:
                r, g, b = float(parts[0]), float(parts[1]), float(parts[2])
                if all(0 <= v <= 1 for v in (r, g, b)):
                    rows.append((r, g, b))
            except ValueError:
                continue
    if not rows:
        raise ValueError("无有效 RGB 行")
    idx = [round(i * (len(rows) - 1) / (levels - 1)) for i in range(levels)]
    return [PK.rgb_to_hex(*(int(round(v * 255)) for v in rows[i])) for i in idx]


def parse_tailwind_js(text: str) -> dict[str, dict[str, str]]:
    """解析 Tailwind colors.js：{ hue: { '50': '#..', ..., '950': '#..' } }"""
    out = {}
    for m in re.finditer(r"(\w+)\s*:\s*\{([^}]*)\}", text):
        hue, body = m.group(1), m.group(2)
        shades = dict(re.findall(r"(\d+)\s*:\s*'([^']+)'", body))
        if len(shades) >= 5:
            out[hue] = shades
    return out


# ---------------------------------------------------------------- ColorBrewer（内嵌标准 hex）
COLORBREWER = {
    "categorical": {
        "colorbrewer_set1": ("Set1", ["#e41a1c", "#377eb8", "#4daf4a", "#984ea3", "#ff7f00", "#ffff33", "#a65628", "#f781bf", "#999999"]),
        "colorbrewer_set3": ("Set3", ["#8dd3c7", "#ffffb3", "#bebada", "#fb8072", "#80b1d3", "#fdb462", "#b3de69", "#fccde5", "#d9d9d9", "#bc80bd", "#ccebc5", "#ffed6f"]),
        "colorbrewer_dark2": ("Dark2", ["#1b9e77", "#d95f02", "#7570b3", "#e7298a", "#66a61e", "#e6ab02", "#a6761d", "#666666"]),
        "colorbrewer_paired": ("Paired", ["#a6cee3", "#1f78b4", "#b2df8a", "#33a02c", "#fb9a99", "#e31a1c", "#fdbf6f", "#ff7f00", "#cab2d6", "#6a3d9a", "#ffff99", "#b15928"]),
        "colorbrewer_accent": ("Accent", ["#7fc97f", "#beaed4", "#fdc086", "#ffff99", "#386cb0", "#f0027f", "#bf5b17", "#666666"]),
        "colorbrewer_pastel1": ("Pastel1", ["#fbb4ae", "#b3cde3", "#ccebc5", "#decbe4", "#fed9a6", "#ffffcc", "#e5d8bd", "#fddaec", "#f2f2f2"]),
        "colorbrewer_pastel2": ("Pastel2", ["#b3e2cd", "#fdcdac", "#cbd5e8", "#f4cae4", "#e6f5c9", "#fff2ae", "#f1e2cc", "#cccccc"]),
    },
    "sequential": {
        "colorbrewer_bugn_9": ("BuGn", ["#f7fcfd", "#e5f5f9", "#ccece6", "#99d8c9", "#66c2a4", "#41ae76", "#238b45", "#006d2c", "#00441b"]),
        "colorbrewer_bupu_9": ("BuPu", ["#f7fcfd", "#e0ecf4", "#bfd3e6", "#9ebcda", "#8c96c6", "#8c6bb1", "#88419d", "#810f7c", "#4d004b"]),
        "colorbrewer_gnbu_9": ("GnBu", ["#f7fcf0", "#e0f3db", "#ccebc5", "#a8ddb5", "#7bccc4", "#4eb3d3", "#2b8cbe", "#0868ac", "#084081"]),
        "colorbrewer_greens_9": ("Greens", ["#f7fcf5", "#e5f5e0", "#c7e9c0", "#a1d99b", "#74c476", "#41ab5d", "#238b45", "#006d2c", "#00441b"]),
        "colorbrewer_greys_9": ("Greys", ["#ffffff", "#f0f0f0", "#d9d9d9", "#bdbdbd", "#969696", "#737373", "#525252", "#252525", "#000000"]),
        "colorbrewer_ord_9": ("OrRd", ["#fff7ec", "#fee8c8", "#fdd49e", "#fdbb84", "#fc8d59", "#ef6548", "#d7301f", "#b30000", "#7f0000"]),
        "colorbrewer_pubu_9": ("PuBu", ["#fff7fb", "#ece7f2", "#d0d1e6", "#a6bddb", "#74a9cf", "#3690c0", "#0570b0", "#045a8d", "#023858"]),
        "colorbrewer_pubugn_9": ("PuBuGn", ["#fff7fb", "#ece2f0", "#d0d1e6", "#a6bddb", "#67a9cf", "#3690c0", "#02818a", "#016c59", "#014636"]),
        "colorbrewer_purd_9": ("PuRd", ["#f7f4f9", "#e7e1ef", "#d4b9da", "#c994c7", "#df65b0", "#e7298a", "#ce1256", "#980043", "#67001f"]),
        "colorbrewer_purples_9": ("Purples", ["#fcfbfd", "#efedf5", "#dadaeb", "#bcbddc", "#9e9ac8", "#807dba", "#6a51a3", "#54278f", "#3f007d"]),
        "colorbrewer_rdpu_9": ("RdPu", ["#fff7f3", "#fde0dd", "#fcc5c0", "#fa9fb5", "#f768a1", "#dd3497", "#ae017e", "#7a0177", "#49006a"]),
        "colorbrewer_reds_9": ("Reds", ["#fff5f0", "#fee0d2", "#fcbba1", "#fc9272", "#fb6a4a", "#ef3b2c", "#cb181d", "#a50f15", "#67000d"]),
        "colorbrewer_ylgn_9": ("YlGn", ["#ffffe5", "#f7fcb9", "#d9f0a3", "#addd8e", "#78c679", "#41ab5d", "#238443", "#006837", "#004529"]),
        "colorbrewer_ylorbr_9": ("YlOrBr", ["#ffffe5", "#fff7bc", "#fee391", "#fec44f", "#fe9929", "#ec7014", "#cc4c02", "#993404", "#662506"]),
        "colorbrewer_ylorrd_9": ("YlOrRd", ["#ffffcc", "#ffeda0", "#fed976", "#feb24c", "#fd8d3c", "#fc4e2a", "#e31a1c", "#bd0026", "#800026"]),
    },
    "diverging": {
        "colorbrewer_puor_11": ("PuOr", ["#7f3b08", "#b35806", "#e08214", "#fdb863", "#fee0b6", "#f7f7f7", "#d8daeb", "#b2abd2", "#8073ac", "#542788", "#2d004b"]),
        "colorbrewer_prgn_11": ("PRGn", ["#40004b", "#762a83", "#9970ab", "#c2a5cf", "#e7d4e8", "#f7f7f7", "#d9f0d3", "#a6dba0", "#5aae61", "#1b7837", "#00441b"]),
        "colorbrewer_rdgy_11": ("RdGy", ["#67001f", "#b2182b", "#d6604d", "#f4a582", "#fddbc7", "#ffffff", "#e0e0e0", "#bababa", "#878787", "#4d4d4d", "#1a1a1a"]),
        "colorbrewer_rdylgn_11": ("RdYlGn", ["#a50026", "#d73027", "#f46d43", "#fdae61", "#fee08b", "#ffffbf", "#d9ef8b", "#a6d96a", "#66bd63", "#1a9850", "#006837"]),
    },
}


def roles_for(n: int, category: str) -> dict:
    if category == "categorical":
        return {"primary": 0, "accent": min(1, n - 1), "support": min(2, n - 1)}
    if category == "diverging":
        return {"primary": 0, "accent": n - 1, "support": n // 2}
    if category == "cyclic":
        return {"primary": 0, "accent": round(n * 0.25), "support": n // 2}
    if category == "neutral":
        return {"primary": max(0, n - 3), "accent": max(0, n - 6), "support": 2}
    # sequential
    return {"primary": round(n * 0.45), "accent": n - 1, "support": max(1, round(n * 0.15))}


def emit(palette: dict):
    try:
        PK.load_palette(palette["id"])
        return  # 已存在
    except FileNotFoundError:
        pass
    PK.save_palette(palette)
    print(f"  + {palette['id']} ({len(palette['colors'])}色, {palette['category']})")


def main():
    added = 0
    # 1) Crameri
    crameri_seq = ["batlow", "oslo", "tokyo", "hawaii", "lajolla", "bilbao", "devon", "grayC",
                   "lapaz", "nuuk", "davos", "bamako", "acton", "turku", "lipari", "navia",
                   "imola", "bukavu", "buda", "fes", "managua", "tofino", "vanimo", "glasgow"]
    crameri_div = ["vik", "roma", "berlin", "broc", "cork", "lisbon", "oleron"]
    base = "https://raw.githubusercontent.com/callumrollo/cmcrameri/main/cmcrameri/cmaps/"
    for name in crameri_seq + crameri_div:
        cat = "diverging" if name in crameri_div else "sequential"
        txt = fetch(base + name + ".txt", f"crameri_{name}.txt")
        try:
            colors = parse_rgb_table(txt)
        except ValueError as e:
            print(f"  跳过 {name}: {e}")
            continue
        emit(PK.build_palette(
            colors, f"crameri_{name.lower()}", f"Crameri {name}", cat,
            tags=["crameri", "perceptually-uniform", "colorblind-safe", cat],
            source={"name": "Fabio Crameri, Scientific Colour Maps", "license": "MIT",
                    "url": "https://www.fabiocrameri.ch/colourmaps/"},
            roles=roles_for(len(colors), cat), note="科研色图，CVD 友好。"))
        added += 1

    # 2) cmocean
    cmo_seq = ["algae", "amp", "deep", "dense", "gray", "haline", "ice", "matter", "oxy",
               "rain", "solar", "speed", "tempo", "thermal", "topo", "turbid"]
    cmo_div = ["balance", "curl", "delta", "diff", "tarn"]
    cmo_cyc = ["phase"]
    base2 = "https://raw.githubusercontent.com/matplotlib/cmocean/master/cmocean/rgb/"
    for name in cmo_seq + cmo_div + cmo_cyc:
        cat = "diverging" if name in cmo_div else ("cyclic" if name in cmo_cyc else "sequential")
        txt = fetch(base2 + name + "-rgb.txt", f"cmocean_{name}.txt")
        try:
            colors = parse_rgb_table(txt)
        except ValueError as e:
            print(f"  跳过 {name}: {e}")
            continue
        emit(PK.build_palette(
            colors, f"cmocean_{name}", f"cmocean {name}", cat,
            tags=["cmocean", "perceptually-uniform", cat],
            source={"name": "Kristen Thyng, cmocean", "license": "MIT", "url": "https://matplotlib.org/cmocean/"},
            roles=roles_for(len(colors), cat), note="海洋学色图，通用性好。"))
        added += 1

    # 3) ColorBrewer 补全
    for cat, group in COLORBREWER.items():
        for pid, (display, colors) in group.items():
            emit(PK.build_palette(
                colors, pid, f"ColorBrewer {display}", cat,
                tags=["colorbrewer", cat, "scientific"],
                source={"name": "ColorBrewer (Cynthia Brewer)", "license": "Apache-2.0", "url": "https://colorbrewer2.org/"},
                roles=roles_for(len(colors), cat), note="ColorBrewer 补全。"))
            added += 1

    # 4) Tailwind 全色相
    tw = parse_tailwind_js(fetch(
        "https://raw.githubusercontent.com/tailwindlabs/tailwindcss/v3.4.0/src/public/colors.js",
        "tailwind_colors.js"))
    neutral_hues = {"slate", "gray", "zinc", "neutral", "stone"}
    for hue, shades in tw.items():
        colors = [shades[k] for k in ("50", "100", "200", "300", "400", "500", "600", "700", "800", "900", "950")]
        cat = "neutral" if hue in neutral_hues else "ui_theme"
        emit(PK.build_palette(
            colors, f"tailwind_{hue}", f"Tailwind {hue}", cat,
            tags=["tailwind", "ramp", hue, cat],
            source={"name": "Tailwind CSS v3.4", "license": "MIT", "url": "https://tailwindcss.com/docs/customizing-colors"},
            roles=roles_for(len(colors), cat), note="单色相 50-950 色阶。"))
        added += 1

    PK.refresh_index()
    print(f"\n新增 {added} 套配色，当前索引: {len(PK.list_all()['palettes'])} 套")


if __name__ == "__main__":
    main()
