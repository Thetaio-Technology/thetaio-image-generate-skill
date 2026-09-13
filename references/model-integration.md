# 模型接入与脚本调用

## 首次安装(只做一次)

第一次使用前,运行安装脚本把 `base_url` 和 `api_key` 写入 `scripts/config.local`:

```bash
python <技能目录>/scripts/setup.py \
  --base-url "https://api.thetaio.tech/v1" \
  --api-key "<你的密钥>"
```

省略参数时会交互式提问。脚本是幂等的: 已有配置时直接跳过,不会重复安装;需要修改时加 `--force`。配置只写入 `scripts/config.local`(`.gitignore` 已忽略)。

## 配置优先级

图片脚本按以下顺序读取配置:

1. 环境变量: `THETAIO_BASE_URL`、`THETAIO_API_KEY`、`THETAIO_MODEL`
2. 兼容变量: `IMAGE_BASE_URL`、`IMAGE_API_KEY`、`IMAGE_MODEL`、`OPENAI_API_KEY`
3. `scripts/config.local`(由安装脚本生成)
4. `scripts/config`
5. 默认值: `base_url=https://api.thetaio.tech/v1`, `model=gpt-image-2`

不要把真实密钥写进 `SKILL.md` 或参考文件。需要手动配置时,复制 `scripts/config.example` 为 `scripts/config.local`。

## 运行依赖

运行环境需要:

- `python`
- Python 包: `Pillow`(仅压缩脚本使用;生图脚本零依赖,只用标准库)

缺依赖时先安装依赖,不要改脚本逻辑:

```bash
python -m pip install Pillow
```

## 模型配置

默认通过 ThetaIO 网关调用,常用模型:

- `gpt-image-2`(默认)
- `gpt-image-2.5`

不要静默替换为其他模型 ID。显式配置示例:

```bash
export THETAIO_API_KEY="你的密钥"
export THETAIO_BASE_URL="https://api.thetaio.tech/v1"
export THETAIO_MODEL="gpt-image-2"
```

用户若自带其他 OpenAI Images 兼容服务商,把 `base_url` 和 `model` 换成对方的即可;只要接口支持 `/images/generations`,本技能可直接调用。不要主动替用户切换服务商。

## 尺寸

支持三档分辨率,通过 `--size` 指定:

| 档位 | 说明 | 适用 |
| --- | --- | --- |
| `1K` | ~1024px 级 | 快速预览、草图、小图 |
| `2K` | ~2048px 级(默认) | 常规封面、知识卡、发布图 |
| `4K` | ~4096px 级 | 高清打印、大图、二次裁切 |

画幅比例(3:4、1:1、16:9 等)不在 `--size` 里设置,请在提示词中明确描述比例与用途。`--size` 只决定分辨率档位。

## 请求方式(同步 / 异步)

生图脚本支持两种请求方式,用 `--mode` 控制,默认 `auto`:

| 值 | 行为 |
| --- | --- |
| `auto`(默认) | 按请求大小自动选: 参考图 ≥ 2 张、参考图总体积 ≥ 4MB、`--n > 1` 或 `--size 4K` 时走异步,否则走同步 |
| `sync` | 强制同步: 一次请求等到出图(30~180 秒),期间连接必须保持 |
| `async` | 强制异步: 提交后立刻返回任务号,脚本轮询到完成再取图 |

对照:

- 同步接口: `POST /images/generations`、`POST /images/edits`
- 异步接口: `POST /images/generations/async`、`POST /images/edits/async`,结果用 `GET /images/tasks/{task_id}` 轮询

同步适合小请求(单张、小图);异步更适合参考图多、体积大、4K、多张输出——长等待不占用连接,抗网络抖动更好。`auto` 已覆盖这些经验规则,通常无需手动指定。

## 单张生图

文生图:

```bash
python <技能目录>/scripts/generate_image.py \
  --prompt "<提示词>" \
  --output "<输出目录>/raw/01.png" \
  --size 2K
```

图生图:

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

多参考图(默认 auto 会自动走异步,也可显式强制):

```bash
python <技能目录>/scripts/generate_image.py \
  --prompt "<提示词>" \
  --image "<参考图1>" --image "<参考图2>" --image "<参考图3>" \
  --output "<输出目录>/raw/01.png" \
  --size 2K \
  --mode async
```

> `--image` 可重复传入,但**单次请求上限 15 张**(ThetaIO 自定义上限); 超过会直接报错,请拆分成多个任务。
> **不建议贴上限使用**: 一般 **6~8 张参考图就足够**,张数越多出图越慢、也越容易触发上游风控。

## 批量生图

优先使用 `scripts/batch_generate.py`(默认 `--mode auto`,同样可按需传 `sync`/`async`)。支持并发,且**每个任务可携带多张参考图**:

```bash
python <技能目录>/scripts/batch_generate.py \
  --batch "<输出目录>/tasks.json" \
  --workers 2 \
  --result "<输出目录>/batch_result.json"
```

只校验任务文件、不调用接口:

```bash
python <技能目录>/scripts/batch_generate.py --batch "<输出目录>/tasks.json" --validate-only
```

## 生成后压缩

压缩不调用图片接口,不需要 API Key。只有用户明确要求压缩、转格式或发布包时才执行:

```bash
python <技能目录>/scripts/compress_image.py \
  "<输出目录>/raw" \
  --output "<输出目录>/compressed" \
  --format webp \
  --quality 80
```

如果要递归处理子目录,增加 `--recursive`。如果要输出机器可读结果,增加 `--json`。

## 任务文件字段

每项必须有:

- `output`: 输出图片路径,可写绝对路径或相对 `tasks.json` 所在目录的路径
- `prompt` 或 `prompt_file`: 二选一

可选字段:

- `size`: 默认 `2K`,可选 `1K`、`2K`、`4K`
- `model`: 可选,默认 `gpt-image-2`;可用 `gpt-image-2`、`gpt-image-2.5`,或自带服务商对应的模型名
- `ref`: 单张参考图路径(旧字段); 存在时走图生图
- `refs`: 参考图路径数组,单次请求一次携带,**最多 15 张**(ThetaIO 自定义上限,一般 6~8 张足够); 与 `ref` 同时出现时以 `refs` 为准
- `negative_prompt`: 会追加到提示词末尾,因为多数 OpenAI 兼容图片接口不支持单独的负向参数

## 失败处理

- 未配置 API 密钥: 停止并要求用户设置环境变量或运行 `scripts/setup.py`
- API 返回 200 但没有图片数据: 视为失败,记录响应前 1000 字符
- 参考图不存在: 直接失败,不要自动改成文生图
- 批量任务中一张失败: 在 `batch_result.json` 记录失败项,不要伪造成功产物
- 模型名不可用: 报告接口返回的真实错误,不要自行换模型
- 压缩失败: 报告 `compress_image.py` 的真实错误,不要删除或覆盖原图
- 不要在任何错误输出里暴露 API Key 或 `Authorization` 头
