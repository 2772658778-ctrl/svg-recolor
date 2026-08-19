# -*- coding: utf-8 -*-
"""色彩引擎（独立于 SVG，供产品/AI/工具共同消费）。

能力：
- OKLab/OKLCH ↔ sRGB 换算（Björn Ottosson 公开公式，无第三方依赖）
- 和谐配色生成（近似/互补/分裂互补/三角/四色/单色，OKLCH 空间旋转色相）
- Tailwind 风格 11 级色阶 ramp（50-950，亮度锚点移植）
- 图片取色（KMeans，Pillow + numpy）
- palette/skin 统一 schema 读写与 _index 索引刷新
"""
from __future__ import annotations

import json
import math
import random
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PALETTES_DIR = ROOT / "palettes"
SKINS_DIR = ROOT / "skins"
GENERATED_DIR = PALETTES_DIR / "generated"

HEX_RE = re.compile(r"^#?[0-9a-fA-F]{6}$")


# ---------------------------------------------------------------- OKLab/OKLCH
def _srgb_to_linear(c: float) -> float:
    c = c / 255.0
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def _linear_to_srgb(c: float) -> float:
    c = max(0.0, min(1.0, c))
    v = 12.92 * c if c <= 0.0031308 else 1.055 * (c ** (1 / 2.4)) - 0.055
    return v


def _cbrt(x: float) -> float:
    return math.copysign(abs(x) ** (1 / 3), x)


def hex_to_rgb(h: str) -> tuple[int, int, int]:
    h = h.strip().lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))  # type: ignore[return-value]


def rgb_to_hex(r, g, b) -> str:
    return "#{:02x}{:02x}{:02x}".format(
        int(round(max(0, min(255, r)))), int(round(max(0, min(255, g)))), int(round(max(0, min(255, b))))
    )


def srgb_to_oklab(r, g, b) -> tuple[float, float, float]:
    r, g, b = _srgb_to_linear(r), _srgb_to_linear(g), _srgb_to_linear(b)
    l = 0.4122214708 * r + 0.5363325363 * g + 0.0514459929 * b
    m = 0.2119034982 * r + 0.6806995451 * g + 0.1073969566 * b
    s = 0.0883024619 * r + 0.2817188376 * g + 0.6299787005 * b
    l_, m_, s_ = _cbrt(l), _cbrt(m), _cbrt(s)
    L = 0.2104542553 * l_ + 0.7936177850 * m_ - 0.0040720468 * s_
    a = 1.9779984951 * l_ - 2.4285922050 * m_ + 0.4505937099 * s_
    b_ = 0.0259040371 * l_ + 0.7827717662 * m_ - 0.8086757660 * s_
    return L, a, b_


def oklab_to_srgb(L, a, b):
    l_ = L + 0.3963377774 * a + 0.2158037573 * b
    m_ = L - 0.1055613458 * a - 0.0638541728 * b
    s_ = L - 0.0894841775 * a - 1.2914855480 * b
    l, m, s = l_ ** 3, m_ ** 3, s_ ** 3
    r = 4.0767416621 * l - 3.3077115913 * m + 0.2309699292 * s
    g = -1.2684380046 * l + 2.6097574011 * m - 0.3413193965 * s
    b_ = -0.0041960863 * l - 0.7034186147 * m + 1.7076147010 * s
    return (_linear_to_srgb(r) * 255, _linear_to_srgb(g) * 255, _linear_to_srgb(b_) * 255)


def hex_to_oklch(h: str) -> tuple[float, float, float]:
    r, g, b = hex_to_rgb(h)
    L, a, b_ = srgb_to_oklab(r, g, b)
    C = math.hypot(a, b_)
    H = math.degrees(math.atan2(b_, a)) % 360
    return L, C, H


def oklch_to_hex(L: float, C: float, H: float) -> str:
    a = C * math.cos(math.radians(H))
    b = C * math.sin(math.radians(H))
    r, g, b_ = oklab_to_srgb(L, a, b)
    return rgb_to_hex(r, g, b_)


def relative_luminance(h: str) -> float:
    r, g, b = (_srgb_to_linear(v) for v in hex_to_rgb(h))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def wcag_contrast(h1: str, h2: str) -> float:
    """WCAG 对比度（1..21）。"""
    l1, l2 = relative_luminance(h1), relative_luminance(h2)
    if l1 < l2:
        l1, l2 = l2, l1
    return (l1 + 0.05) / (l2 + 0.05)


def delta_e_ok(h1: str, h2: str) -> float:
    """OKLab 空间欧氏距离（近似 ΔE_ok，0=相同）。"""
    a = srgb_to_oklab(*hex_to_rgb(h1))
    b = srgb_to_oklab(*hex_to_rgb(h2))
    return math.dist(a, b)


# ---------------------------------------------------------------- 和谐生成
def _from_hex(h: str) -> tuple[float, float, float]:
    return hex_to_oklch(h)


def _rotate_hue(L, C, h, delta: float) -> str:
    return oklch_to_hex(L, C, (h + delta) % 360)


def harmonize(seed: str, rule: str = "triadic", n: int | None = None) -> list[str]:
    """从种子色生成一组和谐色（OKLCH 色相旋转）。seed 永远在第一位。"""
    L, C, h = _from_hex(seed)
    rules = {
        "analogous": [0, 30, 60, -30],
        "complementary": [0, 180],
        "split-complementary": [0, 150, 210],
        "triadic": [0, 120, 240],
        "tetradic": [0, 90, 180, 270],
        "monochromatic": [0, 0, 0, 0, 0],
    }
    if rule not in rules:
        raise ValueError(f"未知和谐规则: {rule}，可选 {list(rules)}")
    deltas = rules[rule]
    if rule == "monochromatic":
        # 同色相，改亮度 + 轻微改色度
        return [oklch_to_hex(max(0.05, min(0.98, L + d)), max(0.02, C * (1 - abs(d) * 0.8)), h)
                for d in (0, 0.12, -0.12, 0.24, -0.24)]
    out = [_rotate_hue(L, C, h, d) for d in deltas]
    if n and n > len(out):
        # 不足时在相邻色相间插值补充
        extra = []
        base = len(out)
        for i in range(n - len(out)):
            a = out[i % base]
            b = out[(i + 1) % base]
            t = (i // base + 1) / (base)
            extra.append(mix_oklab(a, b, t))
        out.extend(extra)
    return out[:n] if n else out


def mix_oklab(h1: str, h2: str, t: float = 0.5) -> str:
    """OKLab 感知插值（避免渐变中间发灰）。"""
    a = srgb_to_oklab(*hex_to_rgb(h1))
    b = srgb_to_oklab(*hex_to_rgb(h2))
    m = tuple(x + (y - x) * t for x, y in zip(a, b))
    return rgb_to_hex(*oklab_to_srgb(*m))


# ---------------------------------------------------------------- 色阶 ramp
# Tailwind v4 亮度锚点（OKLCH L 近似值）
_RAMP_ANCHORS = [0.985, 0.96, 0.89, 0.81, 0.71, 0.60, 0.51, 0.44, 0.38, 0.33, 0.25]
_RAMP_KEYS = ["50", "100", "200", "300", "400", "500", "600", "700", "800", "900", "950"]


def make_ramp(seed: str) -> dict[str, str]:
    """从种子色生成 50-950 的 11 级色阶（色相不变，色度随亮度起伏）。"""
    L, C, h = _from_hex(seed)
    out = {}
    for key, lv in zip(_RAMP_KEYS, _RAMP_ANCHORS):
        cm = math.sin(math.pi * min(0.995, max(0.005, lv)))  # 中间色度最高
        out[key] = oklch_to_hex(lv, max(0.015, C * cm * 1.15), h)
    return out


# ---------------------------------------------------------------- 图片取色
def extract_from_image(image_path: str, n: int = 6) -> list[dict]:
    """从图片提取 n 个主色（KMeans，Pillow + numpy），按亮度降序返回。"""
    import numpy as np
    from PIL import Image

    img = Image.open(image_path).convert("RGB")
    img.thumbnail((96, 96))
    px = np.asarray(img).reshape(-1, 3).astype(np.float64)
    # 丢弃接近纯白的像素（图通常有白底）
    px = px[~np.all(px > 248, axis=1)]
    if len(px) == 0:
        px = np.asarray(img).reshape(-1, 3).astype(np.float64)
    # 简单 KMeans
    rng = np.random.default_rng(42)
    idx = rng.choice(len(px), size=min(n, len(px)), replace=False)
    centers = px[idx].copy()
    for _ in range(12):
        d = np.linalg.norm(px[:, None, :] - centers[None, :, :], axis=2)
        assign = d.argmin(axis=1)
        new = np.array([px[assign == k].mean(axis=0) if np.any(assign == k) else centers[k]
                        for k in range(n)])
        if np.allclose(new, centers, atol=0.5):
            centers = new
            break
        centers = new
    freqs = np.bincount(assign, minlength=n) / len(assign)
    out = []
    for k in range(n):
        h = rgb_to_hex(*centers[k])
        out.append({"hex": h, "freq": round(float(freqs[k]), 3)})
    out.sort(key=lambda c: -relative_luminance(c["hex"]))
    return out


# ---------------------------------------------------------------- schema IO
def _iter_palette_files():
    for p in sorted(PALETTES_DIR.rglob("*.json")):
        if p.name.startswith("_"):
            continue
        yield p


def _iter_skin_files():
    for p in sorted(SKINS_DIR.rglob("*.json")):
        if p.name.startswith("_"):
            continue
        yield p


def load_palette(palette_id: str) -> dict:
    for p in _iter_palette_files():
        if p.stem == palette_id:
            return json.loads(p.read_text(encoding="utf-8"))
    raise FileNotFoundError(f"未找到配色: {palette_id}")


def load_skin(skin_id: str) -> dict:
    for p in _iter_skin_files():
        if p.stem == skin_id:
            return json.loads(p.read_text(encoding="utf-8"))
    raise FileNotFoundError(f"未找到皮肤: {skin_id}")


def palette_roles_colors(palette: dict) -> dict:
    """把 palette.roles 解析为 {role: hex}。"""
    colors = palette["colors"]
    roles = palette.get("roles", {})
    return {role: colors[idx] for role, idx in roles.items() if isinstance(idx, int) and 0 <= idx < len(colors)}


def generate_palette(seed: str, rule: str = "triadic", name: str = "") -> dict:
    """算法生成一套配色并存盘到 palettes/generated/。返回 palette dict。"""
    colors = harmonize(seed, rule)
    pid = re.sub(r"[^0-9a-z一-鿿]+", "_", name.strip().lower() or "").strip("_")
    if not pid:
        pid = f"gen_{seed.lstrip('#')}_{rule}"
    palette = {
        "id": pid,
        "name": name or f"生成·{rule}·{seed}",
        "category": "generated",
        "tags": ["generated", rule],
        "source": {"name": "palette_kit 算法生成", "license": "自研", "url": ""},
        "colors": colors,
        "roles": {"primary": 0, "accent": min(1, len(colors) - 1), "support": min(2, len(colors) - 1)},
        "note": f"种子 {seed}，规则 {rule}",
    }
    save_palette(palette)
    return palette


def save_palette(palette: dict) -> Path:
    GENERATED_DIR.mkdir(parents=True, exist_ok=True)
    if palette.get("category") in ("categorical", "sequential", "diverging", "neutral", "ui_theme", "duotone", "cyclic"):
        d = PALETTES_DIR / palette["category"]
    else:
        d = GENERATED_DIR
    d.mkdir(parents=True, exist_ok=True)
    out = d / f"{palette['id']}.json"
    out.write_text(json.dumps(palette, ensure_ascii=False, indent=2), encoding="utf-8")
    return out


def refresh_index() -> Path:
    """重建 palettes/_index.json（产品/AI/工具 的检索入口）。"""
    idx = {"palettes": [], "skins": []}
    for p in _iter_palette_files():
        d = json.loads(p.read_text(encoding="utf-8"))
        idx["palettes"].append({
            "id": d["id"], "name": d.get("name", d["id"]), "category": d.get("category", ""),
            "tags": d.get("tags", []), "colors": len(d.get("colors", [])),
            "license": d.get("source", {}).get("license", ""),
            "file": str(p.relative_to(ROOT)),
        })
    for p in _iter_skin_files():
        d = json.loads(p.read_text(encoding="utf-8"))
        idx["skins"].append({"id": d["id"], "name": d.get("name", d["id"]), "file": str(p.relative_to(ROOT))})
    out = PALETTES_DIR / "_index.json"
    out.write_text(json.dumps(idx, ensure_ascii=False, indent=2), encoding="utf-8")
    return out


def list_all() -> dict:
    idx = PALETTES_DIR / "_index.json"
    if not idx.exists():
        refresh_index()
    return json.loads(idx.read_text(encoding="utf-8"))


def build_palette(colors: list[str], pid: str, name: str, category: str, tags=None,
                  source=None, roles=None, note="") -> dict:
    return {
        "id": pid, "name": name, "category": category,
        "tags": tags or [], "source": source or {"name": "", "license": "", "url": ""},
        "colors": [normalize_hex(c) for c in colors],
        "roles": roles or {"primary": 0, "accent": 1, "support": 2},
        "note": note,
    }


def normalize_hex(h: str) -> str:
    h = h.strip()
    if not HEX_RE.match(h):
        raise ValueError(f"非法 hex: {h}")
    return h if h.startswith("#") else "#" + h


if __name__ == "__main__":
    print("palette_kit OK")
    print("seed #0ea5e9 triadic:", harmonize("#0ea5e9", "triadic"))
