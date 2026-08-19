# SVG Recolor

**给科研绘图图标换配色的工具箱。**

内置 **129 套成熟配色** 与 **7 种上色风格**，一条命令给任意 SVG 图标上色；也可以把"想要的感觉"用一句话告诉 AI，让它替你挑。所有输出**不改动原文件**，配色与渲染完全分离，可复现、可批量、可交给产品调用。

> 你只需要：一个 SVG 图标 + 一条命令 → 得到一批好看的彩色图标。

---

## 它解决什么问题

科研绘图里，图标配色常常是"拍脑袋"：

- 同一个概念，不同图里颜色不统一；
- 想换配色，只能一张张手动改；
- 配色好不好看、色盲安不安全，全凭感觉。

**这个工具把这件事变成：**

- **配色开箱即用** —— 129 套配色来自 Okabe-Ito、Paul Tol、ColorBrewer、Crameri 科研色图、cmocean、Tailwind、Catppuccin 等成熟开源方案，带许可来源，直接拿来用。
- **上色风格一条命令切换** —— 单色、双色、三色、渐变、柔和、鲜艳、深底。
- **AI 帮你挑** —— 说一句"暖色双色调学术风格"，它自动从库里选配色和风格。
- **批量且可复现** —— 一个文件夹的图标 × 全部配色，一次跑完，自动生成可浏览的预览画廊；同输入永远同输出。

---

## 看一眼

源图标：[demo/source.svg](demo/source.svg)（Lucide `headphones`，线性图标）。下面是用这个工具给同一副耳机上色的效果。

### 3 种配色（单色）

| 蓝 · Okabe-Ito<br>色盲安全 | 橄榄绿 · Crameri<br>科研色图 | 紫罗兰 · Royal |
|---|---|---|
| <img src="demo/okabe_ito_mono.svg" width="80"> | <img src="demo/crameri_batlow_mono.svg" width="80"> | <img src="demo/royal_mono.svg" width="80"> |

### 2 种上色风格（紫罗兰配色）

| 渐变 | 柔和 |
|---|---|
| <img src="demo/royal_gradient.svg" width="80"> | <img src="demo/royal_pastel.svg" width="80"> |

---

## 快速上手

下面是一步一步的完整操作，跟着做就能跑通。

### 第 1 步：安装依赖

```bash
pip install -r requirements.txt
```

### 第 2 步：跑一条最简单的上色命令

```bash
python scripts/recolor_icons.py --icon demo/source.svg --palette okabe_ito --skin duotone
```

命令意思是：**把 `demo/source.svg` 这副耳机，用 `okabe_ito` 这套配色、`duotone` 双色风格上色。**

运行后，打开 `recolored_icons/` 文件夹，会看到一个新文件 `source__okabe_ito__duotone.svg`——那就是结果。原文件没有被改动。

### 第 3 步：理解两个关键参数

命令的套路永远是：`--icon 图标路径 --palette 配色名 --skin 风格名`。

- `--palette`：配色，共 129 套，如 `okabe_ito`（色盲安全）、`viridis_10`（科研色图）、`ocean`（海洋双色）、`catppuccin_mocha`（现代主题）。
- `--skin`：上色风格，共 7 种，如 `mono`（单色）、`duotone`（双色）、`tritone`（三色）、`gradient`（渐变）、`pastel`（柔和）。

把这两个参数换成别的组合，就会得到别的效果：

```bash
python scripts/recolor_icons.py --icon demo/source.svg --palette ocean   --skin gradient   # 海洋渐变
python scripts/recolor_icons.py --icon demo/source.svg --palette viridis_10 --skin mono    # 科研色单色
```

### 第 4 步：看看库里都有什么

```bash
python scripts/palette_cli.py list
```

会打印全部 129 套配色和 7 种风格的名字，照着名字填进 `--palette` / `--skin` 即可。

### 第 5 步：换成你自己的图标

```bash
python scripts/recolor_icons.py --icon 你的图标.svg --palette ocean --skin gradient
```

- `--icon` 填单个 SVG 文件路径即可；填一个文件夹路径会**批量处理里面所有 SVG**。
- 想要输出统一尺寸（如 24×24），加一个参数 `--viewbox "24 24"`。
- 想让 AI 帮你挑配色，加 `--ai "暖色双色调学术风格"`（需配置 DeepSeek key，见下文）。

---

## 功能

**配色库（129 套 / 8 类）**
分类、顺序、发散、中性灰阶、UI 主题、双色、循环色 + 算法生成。每套标好许可与来源，带"主色/强调色/辅助色"默认角色，产品与 AI 读同一份索引。

**配色生成**
- 给一个种子色，自动生成一套和谐配色（近似、互补、三角……）；
- 生成单色相 50–950 色阶；
- 从参考图里提取主色，存成新配色。

**上色引擎**
- **线性图标**：按元素语义上色——主体用主色，点/核心/底色用强调色，外框用辅助色，也能手动指定（如"眼睛用强调色"）；
- **实色插画**：自动把图里颜色按明暗映射到目标配色，整张图换一个色彩体系；
- **渐变**：描边和填充都支持；
- **尺寸无关**：任何画布大小的图标都能处理，也可统一缩放到 24×24。

**AI 推荐**（可选）
配置 DeepSeek key 后，用自然语言描述想要的效果即可自动选配；没配 key 自动退回规则模式。

**批量与画廊**
目录递归、多路径、多配色多风格一次跑完，自动生成按配色分组的预览网页。

---

## 它怎么工作（简单版）

1. **配色与渲染分离**。`palettes/` 只回答"用什么颜色"，`skins/` 只回答"怎么上色"，二者通过统一 JSON 契约对接。改配色不影响渲染，改渲染不影响配色。
2. **线性图标按角色上色**。解析每个元素的颜色与几何：主体→主色；点状/核心/低透明度底色→强调色；外框→辅助色。规则确定、可覆盖。
3. **实色插画按明暗重映射**。没有 `currentColor` 的图，把颜色按亮度重新映射到目标配色（近白保留、深色替换），视觉上整张图换血。
4. **感知均匀的色彩科学**。配色生成与渐变插值都在 OKLCH 色彩空间完成（Björn Ottosson 公开公式），避免普通色相空间"中间发灰"。

---

## 配色从哪来

129 套配色全部来自成熟开源方案，各自的许可与出处详见 **[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)**（Okabe-Ito、Paul Tol、ColorBrewer、Crameri Scientific Colour Maps、cmocean、Tailwind CSS、Catppuccin / Dracula / Tokyo Night / Nord / Gruvbox、D3、Matplotlib；演示图标来自 Lucide）。色彩空间算法参考 Björn Ottosson 的 OKLab 论文与公开实现。

## License

工具代码：[MIT](LICENSE)。配色数据各自许可见 THIRD_PARTY_NOTICES.md。
