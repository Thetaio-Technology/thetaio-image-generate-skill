# ThetaIO 图片生成器 Skill

一个接入 [ThetaIO](https://api.thetaio.tech) 中转站的通用图片生成 Skill。把「视觉需求 → 风格判断 → 提示词 → 生图 → 批量一致性 → 按需压缩」整理成一套可复用流程，适合接入 Codex、Claude、OpenClaw 或其他能读取 `SKILL.md` 的 agent。

默认走 ThetaIO 中转站，**用户使用自己的 API Key**。仓库只内嵌中转站地址，不含任何密钥。

## 核心能力

- **文生图**：根据文字需求生成封面、海报、知识卡、产品图、教程图等。
- **图生图**：使用参考图保留主体、构图、风格或氛围。
- **局部编辑**：用透明 PNG 蒙版指定可编辑区域。
- **批量生图**：用 `tasks.json` 管理多张图，支持风格锚点保持一致性。
- **按需压缩**：用户明确要求时，用内置脚本输出 WebP/JPEG/PNG 轻量图。
- **多分辨率**：支持 `1K` / `2K` / `4K`，默认 `2K`。
- **多模型**：支持 `gpt-image-2`（默认）和 `gpt-image-2.5`。
- **中文可用**：文档、CLI 帮助和错误提示都面向中文用户。

## 目录结构

```text
thetaio-image-generation/
  SKILL.md                    # 技能主文档，agent 读取入口
  README.md
  LICENSE
  requirements.txt            # 仅压缩功能需要 Pillow
  agents/openai.yaml          # agent 接口定义
  references/                 # 风格库与控制文档
    general-styles.md
    xiaohongshu-styles.md
    reference-images.md
    prompt-template.md
    model-integration.md
    post-processing.md
    task-recipes.md
    style-director.md
  scripts/
    setup.py                  # 首次安装与配置
    generate_image.py         # 单张/图生图/局部编辑
    batch_generate.py         # 批量生图
    compress_image.py         # 图片压缩
    config.example            # 配置模板
```

## 快速开始

### 1. 环境要求

- Python 3
- 生图脚本零依赖（仅用标准库）
- 压缩脚本需要 `Pillow`

```bash
python -m pip install Pillow
```

### 2. 配置 API Key（只需一次）

本技能默认使用 ThetaIO 中转站 `https://api.thetaio.tech/v1`。请到中转站申领你自己的 API Key，然后运行安装脚本写入本地配置：

```bash
python scripts/setup.py --api-key "你的密钥"
```

脚本会把 `base_url` 和 `api_key` 写入 `scripts/config.local`。该文件已被 `.gitignore` 忽略，不会被提交。

安装脚本是幂等的：检测到已有配置会直接跳过，不会重复安装；需要修改时加 `--force`。

也可以省略所有参数，交互式填写：

```bash
python scripts/setup.py
```

或使用环境变量（优先级高于 `config.local`）：

```bash
export THETAIO_API_KEY="你的密钥"
export THETAIO_BASE_URL="https://api.thetaio.tech/v1"   # 可选
export THETAIO_MODEL="gpt-image-2"                     # 可选
```

### 3. 生成图片

单张文生图：

```bash
python scripts/generate_image.py \
  --prompt "一张小红书风格的英语学习卡片,水彩手绘,奶油底色,标题为「每天 5 分钟背单词」" \
  --output ./image-output/raw/01.png \
  --size 2K
```

图生图：

```bash
python scripts/generate_image.py \
  --prompt "参考图片的构图和温柔手绘质感,改成小红书英语学习知识卡" \
  --image ./reference.png \
  --output ./image-output/raw/01.png \
  --size 2K
```

## 批量生图

创建 `tasks.json`：

```json
[
  {
    "prompt": "小红书封面图,主题是英语自然拼读,水彩手绘,奶油底色",
    "output": "raw/01.png",
    "size": "2K"
  },
  {
    "prompt": "同一风格的知识卡,展示 3 个短元音例子",
    "output": "raw/02.png",
    "ref": "raw/01.png",
    "size": "2K"
  }
]
```

执行：

```bash
python scripts/batch_generate.py \
  --batch ./image-output/tasks.json \
  --workers 2 \
  --result ./image-output/batch_result.json
```

无 `ref` 的任务会先生成作为视觉锚，带 `ref` 的任务再基于锚图生成，保证同组风格一致。

## 按需压缩

压缩默认不自动执行，只有用户明确要求「压缩、发布包、上传前处理、转 WebP/JPEG/PNG」时才使用。压缩不需要 API Key：

```bash
python scripts/compress_image.py \
  ./image-output/raw \
  --output ./image-output/compressed \
  --format webp \
  --quality 80
```

## 接入 agent

把本目录作为 skill 提供给 agent，让 agent 读取 `SKILL.md`。当用户要求生成图片时，agent 会按需读取 `references/` 中的风格和脚本说明，再执行 `scripts/` 中的脚本。

推荐这样描述需求：

```text
使用 thetaio-image-generation 生成一张小红书英语学习封面。
主题: 自然拼读入门
风格: 水彩手绘,奶油底色,手账贴纸
尺寸: 2K
要求: 生成后再压缩成 WebP 发布图
```

## 配置优先级

1. 环境变量：`THETAIO_BASE_URL` / `THETAIO_API_KEY` / `THETAIO_MODEL`
2. 兼容变量：`IMAGE_BASE_URL` / `IMAGE_API_KEY` / `IMAGE_MODEL` / `OPENAI_API_KEY`
3. `scripts/config.local`
4. `scripts/config`
5. 默认值：`https://api.thetaio.tech/v1`，`gpt-image-2`

## 安全说明

- 本仓库**不含任何 API Key**，默认地址只是中转站入口。
- 请使用你自己的 Key，不要把他人的 Key 提交到仓库。
- `scripts/config.local`、生成结果和压缩结果默认不提交。
- 任何错误输出都不会暴露 `Authorization` 头或 API Key。

## 注意事项

- 默认模型是 `gpt-image-2`，可选 `gpt-image-2.5`。
- 分辨率通过 `--size` 指定，支持 `1K`/`2K`/`4K`；画幅比例（3:4、1:1、16:9）写在提示词里。
- 图片内中文建议保持短标题和关键词，长说明放到外部文案。

## License

Copyright (C) 2026 ThetaIO

本项目采用 **GNU Affero General Public License v3.0 (AGPL-3.0)** 授权，详见 [LICENSE](LICENSE)。

简单说：你可以自由使用、修改和分发，但如果你把修改后的版本作为网络服务提供给他人，也必须以同样许可开源你的修改。
