---
name: recolor
description: 科研绘图图标换色与配色库。用 palette+skin 生成彩色 SVG（含智能推荐），也可生成/查看配色方案。适用于"给图标配色、换色、生成配色方案、查看配色库"。
---

# 图标换色 / 配色库

科研绘图项目的色彩库与图标着色工具。**绝不修改任何原始 SVG**，一律输出到 `recolored_icons/`。

## 位置
- 色彩库：`palettes/`（7 类 30+ 套，含 `_index.json` 检索入口）
- 风格皮肤：`skins/`（mono/duotone/tritone/gradient/pastel/vivid/dark）
- 工具：`scripts/palette_kit.py`、`scripts/palette_cli.py`、`scripts/recolor_icons.py`

## 常用命令

查看可用配色与皮肤：
```bash
python scripts/palette_cli.py list
```

给图标着色（确定性，核心用法）：
```bash
python scripts/recolor_icons.py --icon 某.svg --palette okabe_ito --skin duotone
# 批量：--icon 某目录 --palette all --skin duotone --gallery gallery.html
# 尺寸归一化到任意画布：--viewbox "24 24"
# 角色微调：--role "眼睛=accent"
```

智能推荐（可选，读 .env 的 DeepSeek key）：
```bash
python scripts/recolor_icons.py --icon 某.svg --ai "暖色双色调学术风格"
```

生成新配色：
```bash
python scripts/palette_cli.py generate --seed #0ea5e9 --rule triadic --name 方案名
python scripts/palette_cli.py refresh   # 生成后刷新索引
```

## 两种着色模式（自动判断）
- **currentColor 线性图标**：按角色着色（primary/accent/support，可 `--role` 覆盖）。
- **实色填充插画**（无 currentColor）：自动走亮度序重映射——近白保留、近黑→最暗目标色、其余按亮度映射到配色。
- 尺寸：工具对任意 viewBox 自适应；`--viewbox "W H"` 可把输出归一化到指定画布（等比缩放居中）。

## 约定
1. **不改背景**：所有输出白底，只换 fill/stroke 颜色（dark 皮肤的背景功能当前关闭）。
2. 输出始终进 `recolored_icons/`，原图只读。
3. 画廊用 `<img src>` 引用 SVG，HTML 轻量；按配色分组展示。
4. 用户对配色有偏好描述时，优先用 `--ai` 走智能推荐；无 key 自动退化为规则模式。
