# 常见任务配方

## 单张封面图

读取:

- `references/general-styles.md`
- `references/prompt-template.md`
- `references/model-integration.md`

输出:

```text
style-plan.md
prompts/01.md
raw/01.png
```

推荐尺寸:

- 横向封面: 画幅 3:2 或 16:9,分辨率 `2K`
- 竖向封面: 画幅 3:4,分辨率 `2K`
- 方图: 画幅 1:1,分辨率 `2K`
- 高清打印或需要二次裁切: 分辨率提到 `4K`

画幅比例写在提示词里,`--size` 只决定分辨率档位 `1K`/`2K`/`4K`。

## 小红书封面/知识卡

读取:

- `references/xiaohongshu-styles.md`
- `references/prompt-template.md`
- `references/model-integration.md`
- 用户要求压缩或发布包时读取 `references/post-processing.md`

默认尺寸:

- 画幅 3:4,分辨率 `2K`

规则:

- 标题短,优先 8-18 字。
- 一张图只表达一个重点。
- 先判断图片角色: 封面、铺垫页、核心页、总结页或结尾页。
- 封面默认稀疏版式,知识卡默认平衡版式,速查表才用密集版式。
- 明确安全区: 关键文字避开右上角和底部 10%-14%,边缘留白 6%-8%。
- 保留足够留白: 封面 60%-70%,知识卡 40%-50%,密集速查 20%-30%。
- 图片内文字优先标题、关键词、数字和标签;长说明写到外部文案。
- 字体、标签、箭头、贴纸、边框和背景材质必须服务阅读路径。
- 不放二维码、真实品牌标志、明星脸、受保护 IP。

推荐输出:

```text
style-plan.md
prompts/01.md
raw/01.png
compressed/01.webp  # 仅在用户要求压缩或发布包时生成
```

常用组合:

- 英语/亲子/学习资料: `hand-drawn-edu`、`watercolor-card`、`sketch-notes`。
- 语法/教程/步骤: `chalkboard-tutorial`、`checklist`、`concept-map`。
- 种草/方法论/强钩子: `versus`、`cute-share`、`poster-art`。
- 工具总结/知识框架: `knowledge-card`、`minimal-summary`。

## 参考图改风格

读取:

- `references/reference-images.md`
- `references/prompt-template.md`
- `references/model-integration.md`

规则:

- 先说明参考图角色。
- 明确保留项和改变项。
- 执行 `generate_image.py --image <参考图>`。

## 批量变体

读取:

- `references/general-styles.md`
- `references/prompt-template.md`
- `references/model-integration.md`

规则:

- 先写 `style-plan.md`,定义统一风格。
- 每张图一个 `prompts/NN.md`。
- 每个任务一个 output。
- 如果第 1 张是视觉锚,后续任务用 `ref` 指向第 1 张输出。

## 生成后压缩

读取:

- `references/post-processing.md`

规则:

- 保留 `raw/` 原图。
- 压缩图输出到 `compressed/`。
- 默认 `webp` + `quality 80`;发布图需要更高质量时用 `quality 85-90`。
- 批量图压缩目录时使用 `--recursive`。
- 压缩失败只报告错误,不要删除原图。

脚本:

```bash
python <技能目录>/scripts/compress_image.py \
  "<输出目录>/raw" \
  --output "<输出目录>/compressed" \
  --format webp \
  --quality 80
```

## 只要提示词

用户明确说“先给提示词”“只要 prompt”“不要生成”时:

- 只写 `style-plan.md` 和 `prompts/*.md`。
- 不写或不执行 `tasks.json`。
- 回复中明确“未执行生图脚本”。
