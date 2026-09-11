---
name: thetaio-image-generation
description: 通过 ThetaIO 网关生成、编辑、批量处理和按需压缩图片。把用户的视觉需求、风格方向、参考图或批量计划转成提示词,再执行内置脚本生成图片。适用于文生图、图生图、局部编辑、批量变体、封面、海报、知识卡、小红书风格图、产品/教程图、参考图风格迁移和按需图片压缩。默认使用 gpt-image-2,支持 gpt-image-2.5,分辨率支持 1K/2K/4K,默认 2K。
compatibility: Requires Python 3, network access, and THETAIO_API_KEY. Default endpoint: https://api.thetaio.tech/v1. 压缩功能需要 Pillow。
---

# ThetaIO 图片生成器

这个技能是**脚本型生图技能**: 不依赖原生 tool,默认执行本目录里的脚本,并把流程整理成可复现的工作流。

- **单张模式**: 执行 `scripts/generate_image.py`。
- **参考图模式**: 执行 `scripts/generate_image.py --image <参考图>`。
- **局部编辑模式**: 执行 `scripts/generate_image.py --image <原图> --mask <蒙版>`。
- **批量模式**: 先写 `tasks.json`,再执行 `scripts/batch_generate.py`。
- **压缩模式**: 用户明确要求压缩、瘦身、转格式、发布包或上传前处理时,执行 `scripts/compress_image.py`。
- **仅规划模式**: 用户只要提示词/风格方案时,只写 `style-plan.md` 和 `prompts/*.md`,不执行脚本。

不要把这个技能写成发布工具、运营工具或固定业务工具。它只负责把视觉需求变成图片文件。

## 什么时候使用

- 用户要求生成图片、插画、封面、海报、知识卡、社媒图、小红书图、产品图、教程图、头像、背景图。
- 用户提供参考图,希望保留风格、构图、主体或氛围。
- 用户要求修改或局部编辑已有图片。
- 用户要求同一风格下生成多张图、多套变体或一组连续图片。
- 用户要求先整理生图提示词,再调用模型生成图片。
- 用户要求对已生成图片压缩、转 WebP/JPEG/PNG、生成轻量发布图。

## 什么时候不要使用

- 用户只想写文案、发布小红书、排版 Markdown,不需要生成或处理图片。
- 图形更适合用 SVG、HTML/CSS、Canvas 或代码确定性生成。
- 用户要求修改已有工程里的矢量图标系统,而不是生成位图素材。

## 决策树

先判断四件事:

1. **意图**: 新图生成 / 参考图改图 / 局部编辑 / 批量变体 / 图片压缩 / 只要提示词。
2. **输入**: 是否有参考图、源文本、品牌限制、必须出现的文字。
3. **用途**: 小红书、封面、知识卡、海报、产品图、教程图、纯插画。
4. **输出**: 单张还是多张,保存到哪里,分辨率档位是 1K/2K/4K,画幅比例是多少。

执行选择:

- 没有参考图、只要一张图 -> 单张文生图。
- 有参考图且要继承风格/主体/构图 -> 图生图。
- 有原图且只修改局部 -> 局部编辑模式(加 `--mask`)。
- 多张图或多变体 -> 批量模式。
- 用户只要求压缩、瘦身或转格式 -> 压缩模式,不调用生图接口。
- 用户说"先给提示词/方案" -> 仅规划模式,不要调用脚本。

## 首次安装

第一次使用本技能时,先运行安装脚本,把 `base_url` 和 `api_key` 写入技能外部的 `scripts/config.local`。**只需安装一次**,之后脚本会自动读取该文件,无需重复安装。

交给 agent 调用时,用非交互式参数直接写入:

```bash
python <技能目录>/scripts/setup.py \
  --base-url "https://api.thetaio.tech/v1" \
  --api-key "<用户的密钥>"
```

用户在终端手动运行时可省略参数,脚本会逐项提问:

```bash
python <技能目录>/scripts/setup.py
```

安装脚本是幂等的:

- 检测到已有 `api_key` 时直接打印"已配置,跳过安装"并退出,不会覆盖。
- 需要修改配置时加 `--force`。
- 配置只写到 `scripts/config.local`,该文件已被 `.gitignore` 忽略。

运行生图脚本前,如果缺少 API Key,应先引导用户执行上述安装步骤,不要自行编造密钥。

## 配置

默认从 `scripts/config.local` 读取密钥(由安装脚本生成)。也支持环境变量,优先级高于文件。不要把 API Key 写进源文件、提示词、日志或最终回复。

配置读取优先级:

```text
1. 环境变量: THETAIO_BASE_URL / THETAIO_API_KEY / THETAIO_MODEL
2. 兼容变量: IMAGE_BASE_URL / IMAGE_API_KEY / IMAGE_MODEL / OPENAI_API_KEY
3. scripts/config.local
4. scripts/config
5. 默认值: https://api.thetaio.tech/v1, gpt-image-2
```

环境变量写法:

```text
THETAIO_API_KEY       必填
THETAIO_BASE_URL      可选,默认 https://api.thetaio.tech/v1
THETAIO_MODEL         可选,默认 gpt-image-2
```

模型只允许 `gpt-image-2` 或 `gpt-image-2.5`,默认 `gpt-image-2`。不要静默替换模型 ID。

分辨率通过 `--size` 指定,支持 `1K`、`2K`、`4K`,默认 `2K`。画幅比例(3:4、1:1、16:9 等)写在提示词里,不由 `--size` 控制。

运行依赖: 生图脚本零依赖(仅标准库);压缩脚本需要 `Pillow`:

```bash
python -m pip install Pillow
```

## 工作流

1. 读取用户需求和输入文件。
2. 判断执行模式和输出目录。未指定目录时,默认创建 `<工作目录>/image-output/`。
3. 按需读取参考文件:
   - 通用风格选择: `references/general-styles.md`
   - 小红书风格: `references/xiaohongshu-styles.md`
   - 参考图处理: `references/reference-images.md`
   - 提示词模板: `references/prompt-template.md`
   - 模型和脚本调用: `references/model-integration.md`
   - 生成后处理: `references/post-processing.md`
   - 常见任务配方: `references/task-recipes.md`
   - 风格指挥: `references/style-director.md`
4. 写 `brief.md`: 保留用户原始需求、源文本摘要和关键限制。
5. 写 `style-plan.md`: 明确用途、尺寸档位、画幅、主体、构图、风格、色彩、文字、禁止项、是否使用参考图。
6. 写 `prompts/NN.md`: 每张图一份提示词。
7. 需要真实生图时,写 `tasks.json` 并执行对应脚本。
8. 用户要求压缩、发布包或上传前处理时,按 `references/post-processing.md` 保留 `raw/` 原图并输出 `compressed/`。
9. 检查输出结果、`batch_result.json` 和后处理产物。失败时报告具体错误,不要伪造成功。

## 输出结构

```text
<输出目录>/
  brief.md
  style-plan.md
  prompts/
    01.md
    02.md
  tasks.json
  batch_result.json
  raw/
    01.png
    02.png
  compressed/  # 可选,仅执行后处理时生成
    01.webp
    02.webp
```

## 脚本调用

单张文生图:

```bash
python <技能目录>/scripts/generate_image.py \
  --prompt "<提示词>" \
  --output "<输出目录>/raw/01.png" \
  --size 2K
```

单张图生图:

```bash
python <技能目录>/scripts/generate_image.py \
  --prompt "<提示词>" \
  --image "<参考图>" \
  --output "<输出目录>/raw/01.png" \
  --size 2K
```

局部编辑(透明 PNG 蒙版,透明像素标记可编辑区域):

```bash
python <技能目录>/scripts/generate_image.py \
  --image "<原图>" \
  --mask "<蒙版.png>" \
  --prompt "<修改说明>" \
  --output "<输出目录>/raw/01.png"
```

批量生图:

```bash
python <技能目录>/scripts/batch_generate.py \
  --batch "<输出目录>/tasks.json" \
  --workers 2 \
  --result "<输出目录>/batch_result.json"
```

生成后压缩:

```bash
python <技能目录>/scripts/compress_image.py \
  "<输出目录>/raw" \
  --output "<输出目录>/compressed" \
  --format webp \
  --quality 80
```

## tasks.json 字段

```json
[
  {
    "prompt_file": "prompts/01.md",
    "output": "raw/01.png",
    "size": "2K",
    "model": "gpt-image-2"
  },
  {
    "prompt_file": "prompts/02.md",
    "output": "raw/02.png",
    "ref": "raw/01.png",
    "size": "2K"
  }
]
```

- 必填: `output`,以及 `prompt` 或 `prompt_file` 二选一。
- 可选: `size`(1K/2K/4K,默认 2K)、`model`、`ref`(存在时走图生图)、`negative_prompt`(追加到提示词末尾)。
- 路径可写绝对路径,也可写相对 `tasks.json` 所在目录的路径。
- 批量默认两阶段: 无 `ref` 的任务先生成作为视觉锚,带 `ref` 的任务再基于锚图生成,保证同组风格一致。

## 硬性规则

- 不要编造用户没有提供的事实性文字。图片内文字要短,并且能从用户需求确认。
- 提示词必须明确主体、构图、色彩、渲染风格、光线、画幅比例、分辨率档位和限制。
- 批量图片默认保持同一套风格系统,除非用户明确要求多风格探索。
- 使用参考图作为风格锚点时,必须在 `tasks.json` 里设置 `ref`; 不要静默改成文生图。
- 小红书图必须读取 `references/xiaohongshu-styles.md`,并明确画幅、安全区、版式密度、字体层级和装饰策略。
- 默认不要自动压缩。只有用户明确要求压缩、发布包、上传前处理或转格式时,才执行 `scripts/compress_image.py`。
- 后处理不得覆盖 `raw/` 原图。压缩图必须输出到 `compressed/` 或用户指定目录,除非用户显式要求覆盖。
- 避免受保护 IP、明星肖像、真实品牌标志、精确复刻教材封面、二维码和大段不可读文字,除非用户明确提供权利并要求这样做。
- 缺少 API 密钥或模型接口失败时,停止并报告脚本返回的准确错误。不要静默切换服务商、模型或密钥。
- 任何错误输出都不要暴露 `Authorization` 头或 API Key。

## 完成报告

回复用户时使用:

```text
图片已生成
模式: <单张/参考图/局部编辑/批量/仅规划>
模型: <gpt-image-2/gpt-image-2.5>
尺寸: <1K/2K/4K>
画幅: <比例>
风格: <风格>
数量: <数量>
输出目录: <输出目录>
关键文件:
  - brief.md
  - style-plan.md
  - prompts/*.md
  - tasks.json
  - batch_result.json
  - raw/*.png
  - compressed/*.<格式,如有>
```
