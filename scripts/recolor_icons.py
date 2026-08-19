# -*- coding: utf-8 -*-
"""图标着色引擎（确定性，不修改任何原始 SVG）。

用法：
  python scripts/recolor_icons.py --icon 某个.svg --palette okabe_ito --skin duotone
  python scripts/recolor_icons.py --icon 某个目录 --palette all --skin duotone --gallery gallery.html
  python scripts/recolor_icons.py --icon 某个.svg --palette ocean --skin duotone --role "眼睛=accent"
  python scripts/recolor_icons.py --icon 某个.svg --ai "暖色双色调学术风格"

角色规则（确定性，可用 --role 覆盖）：
  primary : 默认
  accent  : 闭合且面积小的形状（点/核心/小环），或 fill/stroke 含 var(--accent) 的元素
  support : 包裹所有元素的“外框”（tritone 用）

支持：嵌套 <g>、祖先链继承的 currentColor、var(--accent, currentColor)。
输出到 recolored_icons/<图标>__<配色>__<皮肤>.svg
"""
from __future__ import annotations

import argparse
import math
import os
import re
import sys
from pathlib import Path
from urllib.parse import quote

sys.path.insert(0, str(Path(__file__).resolve().parent))
import palette_kit as PK
from lxml import etree

SHAPES = {"path", "circle", "rect", "line", "ellipse", "polygon", "polyline"}
ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = ROOT / "recolored_icons"
ACCENT_AREA_RATIO = 0.02
ACCENT_AREA_MIN = 2.0

try:
    import svgpathtools
    _HAS_SPT = True
except Exception:
    _HAS_SPT = False


# ---------------------------------------------------------------- 几何
def _num(el, key, default=0.0):
    v = el.get(key)
    return float(v) if v not in (None, "") else default


def _viewbox(root) -> tuple[float, float, float, float]:
    """解析根 viewBox，返回 (x0, y0, w, h)；缺省 0,0,24,24。"""
    parts = (root.get("viewBox") or "0 0 24 24").split()
    if len(parts) == 4:
        try:
            x0, y0, w, h = map(float, parts)
            if w > 0 and h > 0:
                return x0, y0, w, h
        except ValueError:
            pass
    return 0.0, 0.0, 24.0, 24.0


def _fmt(v: float) -> str:
    return ("%g" % v) if abs(v - round(v)) < 1e-9 else f"{v:.4f}"


def element_geometry(el) -> dict:
    """本地坐标下的 {bbox, closed, area}（transform 近似忽略，够启发式用）。"""
    tag = etree.QName(el).localname
    if tag == "circle":
        cx, cy, r = _num(el, "cx"), _num(el, "cy"), _num(el, "r")
        return dict(bbox=(cx - r, cy - r, cx + r, cy + r), closed=True, area=math.pi * r * r)
    if tag == "ellipse":
        cx, cy, rx, ry = _num(el, "cx"), _num(el, "cy"), _num(el, "rx"), _num(el, "ry")
        return dict(bbox=(cx - rx, cy - ry, cx + rx, cy + ry), closed=True, area=math.pi * rx * ry)
    if tag == "rect":
        x, y, w, h = _num(el, "x"), _num(el, "y"), _num(el, "width"), _num(el, "height")
        return dict(bbox=(x, y, x + w, y + h), closed=True, area=w * h)
    if tag == "line":
        x1, y1 = _num(el, "x1"), _num(el, "y1")
        x2, y2 = _num(el, "x2"), _num(el, "y2")
        return dict(bbox=(min(x1, x2), min(y1, y2), max(x1, x2), max(y1, y2)), closed=False, area=0.0)
    if tag in ("polygon", "polyline"):
        pts = [float(v) for v in re.split(r"[,\s]+", el.get("points", "").strip()) if v]
        xs, ys = pts[0::2], pts[1::2]
        bbox = (min(xs), min(ys), max(xs), max(ys))
        return dict(bbox=bbox, closed=(tag == "polygon"), area=(max(xs) - min(xs)) * (max(ys) - min(ys)))
    if tag == "path" and _HAS_SPT:
        try:
            pp = svgpathtools.parse_path(el.get("d", ""))
            xs, ys = [], []
            first, last = None, None
            for seg in pp:
                p0, p1 = seg.point(0), seg.point(1)
                if first is None:
                    first = p0
                last = p1
                for i in range(16):
                    z = seg.point(i / 15)
                    xs.append(z.real)
                    ys.append(z.imag)
            closed = first is not None and abs((first - last).real) < 0.01 and abs((first - last).imag) < 0.01
            bbox = (min(xs), min(ys), max(xs), max(ys))
            return dict(bbox=bbox, closed=closed, area=(max(xs) - min(xs)) * (max(ys) - min(ys)))
        except Exception:
            pass
    return dict(bbox=(0, 0, 24, 24), closed=False, area=0.0)


def union_bbox(geoms):
    xs0 = [g["bbox"][0] for g in geoms]
    ys0 = [g["bbox"][1] for g in geoms]
    xs1 = [g["bbox"][2] for g in geoms]
    ys1 = [g["bbox"][3] for g in geoms]
    return (min(xs0), min(ys0), max(xs1), max(ys1))


def contains(a, b, tol=0.25):
    return a[0] - tol <= b[0] and a[1] - tol <= b[1] and a[2] + tol >= b[2] and a[3] + tol >= b[3]


def _inherited(el, name):
    while el is not None:
        v = el.get(name)
        if v not in (None, ""):
            return v
        el = el.getparent()
    return None


def _is_shape(el):
    return isinstance(el.tag, str) and etree.QName(el).localname in SHAPES


# ---------------------------------------------------------------- 角色
def assign_roles(nodes) -> None:
    geoms = [n["geom"] for n in nodes]
    ub = union_bbox(geoms)
    icon_area = max(1.0, (ub[2] - ub[0]) * (ub[3] - ub[1]))
    closed = [(n, g) for n, g in zip(nodes, geoms) if g["closed"] and g["area"] > 0]
    n_closed = len(closed)
    for n in nodes:
        n["role"] = "primary"
    # accent：点/核心——面积≤2 的微点必强调；有≥2个闭合时，取面积最小的 40%（至少1个）
    if n_closed >= 2:
        areas = sorted(g["area"] for _, g in closed)
        k = max(1, int(round(0.4 * n_closed)))
        cutoff = areas[min(k, n_closed) - 1]
        for n, g in closed:
            if g["area"] <= cutoff or g["area"] <= ACCENT_AREA_MIN:
                n["role"] = "accent"
    elif n_closed == 1 and closed[0][1]["area"] <= ACCENT_AREA_MIN:
        closed[0][0]["role"] = "accent"
    # support：包裹所有元素的外框（仅当图标有多个元素，避免单元素图标误判）
    if len(nodes) > 1:
        for n, g in zip(nodes, geoms):
            if contains(g["bbox"], ub):
                n["role"] = "support"
                break
    # 低透明度元素（duotone 底/阴影）→ 强调色
    for n in nodes:
        op = n["el"].get("opacity")
        if op:
            try:
                if float(op) < 0.5:
                    n["role"] = "accent"
            except ValueError:
                pass
    # var(--accent) 语义
    for n in nodes:
        for attr in ("fill", "stroke"):
            v = _inherited(n["el"], attr) or ""
            if "accent" in v.lower():
                n["role"] = "accent"


def apply_overrides(nodes, overrides):
    for label, role in overrides.items():
        for n in nodes:
            if label in n["comment"]:
                n["role"] = role


def effective_color(palette, skin, icon_role):
    pal_roles = PK.palette_roles_colors(palette)
    target = skin.get("apply", {}).get("roles", {}).get(icon_role, "primary")
    return pal_roles.get(target) or pal_roles.get("primary") or palette["colors"][0]


# ---------------------------------------------------------------- 实色重映射
DUOTONE_BASE_ALPHA = 0.5  # duotone 底色：源透明度 <0.5 时提升为可见浅色


def _composite_over_white(hex_color: str, alpha: float) -> str:
    """把颜色按 alpha 合成到白底 → 实色浅色块（背景无关）。"""
    r, g, b = PK.hex_to_rgb(hex_color)
    return PK.rgb_to_hex(*(round(v * alpha + 255 * (1 - alpha)) for v in (r, g, b)))


def _normalize_hex(v: str) -> str | None:
    h = (v or "").strip().lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    if re.fullmatch(r"[0-9a-fA-F]{6}", h):
        return "#" + h.lower()
    return None


def _remap_target_colors(palette, skin) -> list[str]:
    """皮肤用到的 palette 角色对应的颜色（按亮度升序）。"""
    skin_roles = skin.get("apply", {}).get("roles", {"primary": "primary"})
    pal_roles = PK.palette_roles_colors(palette)
    seen, out = set(), []
    for r in skin_roles.values():
        c = pal_roles.get(r) or palette["colors"][0]
        if c not in seen:
            seen.add(c)
            out.append(c)
    return sorted(out, key=lambda c: PK.relative_luminance(c))


def _build_remap(source_colors: dict, target_colors: list[str]) -> dict:
    """源色 → 目标色的映射：
    - 近白保留；近黑 → 最暗目标色；
    - 其余按亮度序等距分桶到目标色（避免混色发灰）。
    """
    if not target_colors:
        return {}
    tgt = sorted(set(target_colors), key=lambda c: PK.relative_luminance(c))
    white, black, chroma = [], [], []
    for c in source_colors:
        L = PK.relative_luminance(c)
        if L > 0.92:
            white.append(c)
        elif L < 0.05:
            black.append(c)
        else:
            chroma.append(c)
    mapping = {c: c for c in white}
    for c in black:
        mapping[c] = tgt[0]
    if chroma:
        chroma = sorted(chroma, key=lambda c: PK.relative_luminance(c))
        n, m = len(chroma), len(tgt)
        for i, c in enumerate(chroma):
            j = round(i * (m - 1) / (n - 1)) if n > 1 else 0
            mapping[c] = tgt[j]
    return mapping


# ---------------------------------------------------------------- 主流程
def recolor_one(svg_path: Path, palette: dict, skin: dict, overrides: dict, out_dir: Path,
                target_vb: tuple[int, int] | None = None) -> Path:
    tree = etree.parse(str(svg_path))
    root = tree.getroot()
    ns = etree.QName(root).namespace or "http://www.w3.org/2000/svg"
    nsmap = {None: ns}
    apply = skin.get("apply", {})
    skin_roles = apply.get("roles", {"primary": "primary"})
    opacity_map = apply.get("opacity", {})
    sw_mult = apply.get("stroke_width")
    grad_on = bool(apply.get("gradient"))
    bg = apply.get("background")
    vx, vy, vw, vh = _viewbox(root)

    # 收集 shape 节点（含嵌套）与前一条注释
    nodes = []
    last_comment = ""
    has_cc = False
    for el in root.iter():
        if not isinstance(el.tag, str):
            continue
        if el.tag == etree.Comment:
            last_comment = (el.text or "").strip()
        elif _is_shape(el):
            es = _inherited(el, "stroke") or ""
            ef = _inherited(el, "fill") or ""
            if "currentColor" in es or "currentColor" in ef:
                has_cc = True
            nodes.append({"el": el, "comment": last_comment,
                          "eff_stroke": es, "eff_fill": ef})
            last_comment = ""

    # 注入背景
    if bg:
        bg_rect = etree.Element(etree.QName(ns, "rect"), nsmap=nsmap)
        bg_rect.set("x", _fmt(vx))
        bg_rect.set("y", _fmt(vy))
        bg_rect.set("width", _fmt(vw))
        bg_rect.set("height", _fmt(vh))
        bg_rect.set("fill", bg)
        bg_rect.set("stroke", "none")
        root.insert(0, bg_rect)

    if has_cc:
        # ---- currentColor 线性图标：按角色着色 ----
        for n in nodes:
            n["geom"] = element_geometry(n["el"])
        assign_roles(nodes)
        apply_overrides(nodes, overrides)

        if grad_on:
            pal_roles = PK.palette_roles_colors(palette)
            c1 = pal_roles.get("primary", palette["colors"][0])
            c2 = pal_roles.get("accent", palette["colors"][-1])
            defs = etree.SubElement(root, etree.QName(ns, "defs"), nsmap=nsmap)
            lg = etree.SubElement(defs, etree.QName(ns, "linearGradient"), nsmap=nsmap)
            lg.set("id", "pk-g")
            lg.set("gradientUnits", "userSpaceOnUse")
            lg.set("x1", _fmt(vx + 2))
            lg.set("y1", _fmt(vy + 2))
            lg.set("x2", _fmt(vx + vw - 2))
            lg.set("y2", _fmt(vy + vh - 2))
            for off, col in (("0%", c1), ("100%", c2)):
                st = etree.SubElement(lg, etree.QName(ns, "stop"), nsmap=nsmap)
                st.set("offset", off)
                st.set("stop-color", col)

        for n in nodes:
            el, role = n["el"], n["role"]
            color = effective_color(palette, skin, role)
            pal_role = skin_roles.get(role, "primary")
            if "currentColor" in n["eff_stroke"]:
                el.set("stroke", "url(#pk-g)" if (grad_on and role == "primary") else color)
            if "currentColor" in n["eff_fill"]:
                el.set("fill", "url(#pk-g)" if (grad_on and role == "primary") else color)
            # duotone 底色（源 opacity<0.5）：提升为可见浅色实色块，消除“部分填充/阴影”观感
            own_op = el.get("opacity")
            if own_op:
                try:
                    if 0 < float(own_op) < 0.5:
                        for attr in ("fill", "stroke"):
                            v = el.get(attr)
                            if v and v.startswith("#"):
                                el.set(attr, _composite_over_white(v, DUOTONE_BASE_ALPHA))
                        del el.attrib["opacity"]
                except ValueError:
                    pass
            if sw_mult:
                cur = float(el.get("stroke-width") or _inherited(el, "stroke-width") or 2)
                el.set("stroke-width", f"{cur * sw_mult:.2f}")
            op = opacity_map.get(pal_role)
            if op and op < 1.0:
                el.set("opacity", f"{op:.2f}")
    else:
        # ---- 实色填充插画：按亮度序重映射到目标色 ----
        tgt = _remap_target_colors(palette, skin)
        from collections import Counter
        colors = Counter()
        for n in nodes:
            for attr in ("eff_fill", "eff_stroke"):
                h = _normalize_hex(n[attr])
                if h:
                    colors[h] += 1
        if colors:
            mapping = _build_remap(colors, tgt)
            for n in nodes:
                el = n["el"]
                for attr in ("fill", "stroke"):
                    h = _normalize_hex(_inherited(el, attr) or "")
                    if h and h in mapping and mapping[h] != h:
                        el.set(attr, mapping[h])
                if sw_mult:
                    cur = float(el.get("stroke-width") or _inherited(el, "stroke-width") or 2)
                    el.set("stroke-width", f"{cur * sw_mult:.2f}")
                op = next(iter(opacity_map.values()), None)
                if op and op < 1.0:
                    el.set("opacity", f"{op:.2f}")

    # 根兜底（仅当原根本就带 stroke，如 currentColor 线性图标）
    if root.get("stroke") is not None:
        root.set("stroke", PK.palette_roles_colors(palette).get("primary", palette["colors"][0]))

    # 输出尺寸归一化：等比缩放居中到目标画布（默认保留原 viewBox）
    if target_vb:
        tw, th = target_vb
        s = min(tw / vw, th / vh)
        tx = (tw - vw * s) / 2 - vx * s
        ty = (th - vh * s) / 2 - vy * s
        g = etree.Element(etree.QName(ns, "g"), nsmap=nsmap)
        g.set("transform", f"translate({tx:.3f} {ty:.3f}) scale({s:.5f})")
        for child in list(root):
            root.remove(child)
            g.append(child)
        root.append(g)
        root.set("viewBox", f"0 0 {tw:g} {th:g}")
        root.set("width", f"{tw:g}")
        root.set("height", f"{th:g}")

    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / f"{svg_path.stem}__{palette['id']}__{skin['id']}.svg"
    tree.write(str(out), encoding="utf-8", xml_declaration=False, pretty_print=True)
    etree.parse(str(out))  # 合法校验
    return out


# ---------------------------------------------------------------- AI 推荐
def ai_recommend(description: str, default_palette: str, default_skin: str) -> tuple[str, str, str]:
    try:
        import llm_utils
        idx = PK.list_all()
        pal_lines = "\n".join(f"- {p['id']}: {p['name']} [{p['category']}] 标签={p['tags']}" for p in idx["palettes"])
        skin_lines = "\n".join(f"- {s['id']}: {s['name']}" for s in idx["skins"])
        system = "你是科研绘图配色专家。根据用户描述，从给定清单里选最合适的配色(palette)与皮肤(skin)。只输出 JSON。"
        user = f"可用配色：\n{pal_lines}\n\n可用皮肤：\n{skin_lines}\n\n需求：{description}\n输出 {{\"palette\": \"id\", \"skin\": \"id\", \"reason\": \"一句话\"}}"
        raw = llm_utils.ask_deepseek(system, user, max_tokens=500, temperature=0.2)
        data = llm_utils.extract_json(raw)
        return str(data.get("palette") or default_palette), str(data.get("skin") or default_skin), str(data.get("reason", ""))
    except SystemExit:
        print("[ai] 未配置 DEEPSEEK_API_KEY，退回规则模式")
        return default_palette, default_skin, ""
    except Exception as e:  # noqa: BLE001
        print(f"[ai] 推荐失败({e})，退回规则模式")
        return default_palette, default_skin, ""


# ---------------------------------------------------------------- 入口
def resolve_items(arg: str, kind: str):
    if arg == "all":
        return [d["id"] for d in PK.list_all()[kind + "s"]]
    return [x.strip() for x in arg.split(",") if x.strip()]


def main():
    ap = argparse.ArgumentParser(description="科研绘图图标着色引擎")
    ap.add_argument("--icon", required=True, help="单个 svg 路径或目录")
    ap.add_argument("--palette", default="okabe_ito", help="配色 id 或 all")
    ap.add_argument("--skin", default="duotone", help="皮肤 id 或 all")
    ap.add_argument("--out", default=str(OUT_DIR), help="输出目录")
    ap.add_argument("--role", action="append", default=[], help="角色覆盖，如 眼睛=accent（可多次）")
    ap.add_argument("--ai", default="", help="智能推荐：一段需求描述")
    ap.add_argument("--gallery", default="", help="可选：完成后生成预览 HTML 路径")
    ap.add_argument("--viewbox", default="", help="可选：输出尺寸归一化，如 '24 24'（等比缩放居中到该画布）")
    args = ap.parse_args()

    overrides = {}
    for r in args.role:
        if "=" in r:
            k, _, v = r.partition("=")
            overrides[k.strip()] = v.strip()

    palette_id, skin_id, reason = args.palette, args.skin, ""
    if args.ai:
        palette_id, skin_id, reason = ai_recommend(args.ai, palette_id, skin_id)
        print(f"[ai] 推荐 palette={palette_id} skin={skin_id}  ({reason})")

    palettes = [PK.load_palette(pid) for pid in resolve_items(palette_id, "palette")]
    skins = [PK.load_skin(sid) for sid in resolve_items(skin_id, "skin")]

    if "," in args.icon:
        icon_path = None
        icons = []
        for part in args.icon.split(","):
            p = Path(part.strip())
            if p.is_dir():
                icons.extend(sorted(p.rglob("*.svg")))
            else:
                icons.append(p)
        bad = [p for p in icons if not p.is_file()]
        if bad:
            sys.exit(f"找不到 svg: {bad}")
    else:
        icon_path = Path(args.icon)
        icons = [icon_path] if icon_path.is_file() else sorted(icon_path.rglob("*.svg"))
    if not icons:
        sys.exit(f"没有找到 svg: {args.icon}")

    target_vb = None
    if args.viewbox:
        parts = args.viewbox.split()
        if len(parts) == 2:
            target_vb = (int(float(parts[0])), int(float(parts[1])))
        else:
            sys.exit("--viewbox 需为 'W H'，如 '24 24'")

    out_dir = Path(args.out)
    results = []
    for svg in icons:
        sub = svg.relative_to(icon_path).parent if (icon_path is not None and icon_path.is_dir()) else Path("")
        target_dir = out_dir / sub
        for pal in palettes:
            for sk in skins:
                out = recolor_one(svg, pal, sk, overrides, target_dir, target_vb)
                results.append((svg.name, pal["id"], sk["id"], out))
    print(f"完成 {len(results)} 个输出 -> {out_dir}")
    for name, pid, sid, out in results:
        print(f"  {name}  x {pid} x {sid} -> {out.name}")

    if args.gallery:
        build_gallery(results, Path(args.gallery), out_dir)


def build_gallery(results, out_path: Path, out_dir: Path):
    """按配色分组的画廊：`<img src>` 引用 SVG（HTML 轻量），色块头 + 尺寸自适应。"""
    base = out_path.parent
    groups: dict[str, list] = {}
    order = []
    for name, pid, sid, out in results:
        groups.setdefault(pid, []).append((name, out))
        if pid not in order:
            order.append(pid)
    css = [
        "<style>",
        "body{font-family:system-ui,'Microsoft YaHei',sans-serif;background:#f5f7fa;margin:24px;color:#1f2937}",
        "h1{font-size:18px}",
        ".pgroup{margin:30px 0 6px;display:flex;align-items:center;gap:10px;flex-wrap:wrap}",
        ".pgroup b{font-size:14px}",
        ".pgroup .id{font-size:11px;color:#6b7280}",
        ".sw{display:inline-flex;border-radius:6px;overflow:hidden;height:18px;border:1px solid #e5e7eb}",
        ".sw span{width:22px;height:100%}",
        ".grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(118px,1fr));gap:10px}",
        ".card{background:#fff;border:1px solid #e5e7eb;border-radius:10px;padding:10px 6px;text-align:center}",
        ".iconbox{height:96px;display:flex;align-items:center;justify-content:center;overflow:hidden}",
        ".card img{max-width:88px;max-height:88px;width:auto;height:auto}",
        ".t{font-size:10px;color:#6b7280;margin-top:4px;word-break:break-all;line-height:1.4}",
        "</style>",
    ]
    html = ["<!DOCTYPE html><html lang='zh-CN'><head><meta charset='utf-8'>",
            "<title>图标着色结果 · 全部配色</title>"] + css + ["</head><body>",
            "<h1>图标着色结果 · 全部配色</h1><p style='font-size:12px;color:#6b7280'>"
            "共 {} 张 · 按配色分组 · 白底只换 fill/stroke · 尺寸自适应</p>".format(len(results))]
    for pid in order:
        pal = PK.load_palette(pid)
        sw = "".join(f"<span style='background:{c}' title='{c}'></span>" for c in pal["colors"])
        html.append(f"<div class='pgroup'><b>{pal.get('name', pid)}</b>"
                    f"<span class='id'>{pid} · {len(pal['colors'])}色 · {pal.get('category','')}</span>"
                    f"<span class='sw'>{sw}</span></div>")
        html.append("<div class='grid'>")
        for name, out in groups[pid]:
            rel = os.path.relpath(out, base).replace("\\", "/")
            src = quote(rel)
            html.append(f"<div class='card'><div class='iconbox'>"
                        f"<img loading='lazy' src='{src}' alt='{name}'></div>"
                        f"<div class='t'>{name}<br>{pid}</div></div>")
        html.append("</div>")
    html.append("</body></html>")
    out_path.write_text("".join(html), encoding="utf-8")
    print(f"预览 -> {out_path}")


if __name__ == "__main__":
    main()
