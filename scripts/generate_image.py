#!/usr/bin/env python
"""通过 ThetaIO OpenAI 兼容网关生成或编辑图片。

封装:
- 文生图: POST /images/generations
- 图生图: POST /images/edits

密钥必须放在技能外部,优先使用环境变量,也可以在脚本旁创建不提交的
scripts/config.local。本模块同时提供可复用的 generate_image() 函数,
供 batch_generate.py 调用。
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import pathlib
import sys
import time
import urllib.error
import urllib.request
import uuid


DEFAULT_BASE_URL = "https://api.thetaio.tech/v1"
DEFAULT_MODEL = "gpt-image-2"
DEFAULT_SIZE = "2K"
NO_API_KEY_MARKER = "[NO_API_KEY]"
SUPPORTED_SIZES = ("1K", "2K", "4K")
DEFAULT_TIMEOUT_SECONDS = 180
MODE_SYNC = "sync"
MODE_ASYNC = "async"
MODE_AUTO = "auto"
DEFAULT_MODE = MODE_AUTO
SUPPORTED_MODES = (MODE_AUTO, MODE_SYNC, MODE_ASYNC)
# auto 模式下判定为“重请求”的阈值: 多个参考图 / 总字节数偏大 / 多张输出 / 4K。
AUTO_ASYNC_IMAGE_COUNT = 2
AUTO_ASYNC_TOTAL_BYTES = 4 * 1024 * 1024
ASYNC_POLL_INTERVAL_SECONDS = 4
ASYNC_MAX_WAIT_SECONDS = 900
CONFIG_CANDIDATES = ("config.local", "config")
ENV_BASE_URL_KEYS = ("THETAIO_BASE_URL", "IMAGE_BASE_URL")
ENV_API_KEY_KEYS = ("THETAIO_API_KEY", "IMAGE_API_KEY", "OPENAI_API_KEY")
ENV_MODEL_KEYS = ("THETAIO_MODEL", "IMAGE_MODEL")


def load_key_value_config(path: pathlib.Path) -> dict[str, str]:
    """读取简单的 'key: value' 配置文件。"""
    if not path.exists():
        return {}

    parsed_config: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8-sig").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or ":" not in line:
            continue
        key, value = line.split(":", 1)
        parsed_config[key.strip()] = value.split("#", 1)[0].strip()
    return parsed_config


def first_env_value(keys) -> str | None:
    for key in keys:
        value = os.getenv(key)
        if value:
            return value
    return None


def find_config_path(explicit_path: str | None = None) -> pathlib.Path | None:
    if explicit_path:
        candidate = pathlib.Path(explicit_path).expanduser().resolve()
        if not candidate.exists():
            raise RuntimeError(f"config 文件不存在: {candidate}")
        return candidate

    script_dir = pathlib.Path(__file__).resolve().parent
    for filename in CONFIG_CANDIDATES:
        candidate = script_dir / filename
        if candidate.exists():
            return candidate
    return None


def load_runtime_config(config_path: str | None = None) -> tuple[str, str, str]:
    """返回 (base_url, api_key, model),密钥缺失时直接报错。"""
    selected_config_path = find_config_path(config_path)
    file_config = load_key_value_config(selected_config_path) if selected_config_path else {}

    base_url = first_env_value(ENV_BASE_URL_KEYS) or file_config.get("base_url") or DEFAULT_BASE_URL
    api_key = first_env_value(ENV_API_KEY_KEYS) or file_config.get("api_key")
    model = first_env_value(ENV_MODEL_KEYS) or file_config.get("model") or DEFAULT_MODEL

    if not api_key:
        raise RuntimeError(
            f"{NO_API_KEY_MARKER} 未找到 ThetaIO API Key。运行 scripts/setup.py 配置, "
            "或联系 ThetaIO 开通。"
        )

    return base_url.rstrip("/"), api_key, model


def normalize_size(size: str) -> str:
    """把 1k/2k/4k 归一化为 1K/2K/4K,其余值原样透传给网关。"""
    cleaned = size.strip()
    upper = cleaned.upper()
    if upper in SUPPORTED_SIZES:
        return upper
    return cleaned


def build_multipart_body(payload, images, mask):
    boundary = f"----ThetaIO{uuid.uuid4().hex}"
    chunks = []
    for name, value in payload.items():
        chunks.extend([
            f"--{boundary}\r\n".encode(),
            f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode(),
            str(value).encode(),
            b"\r\n",
        ])

    files = [("image", path) for path in images]
    if mask:
        files.append(("mask", mask))
    for name, path in files:
        file_path = pathlib.Path(path)
        if not file_path.is_file():
            raise RuntimeError(f"文件不存在: {file_path}")
        content_type = "image/png" if file_path.suffix.lower() == ".png" else "image/jpeg"
        chunks.extend([
            f"--{boundary}\r\n".encode(),
            f'Content-Disposition: form-data; name="{name}"; filename="{file_path.name}"\r\n'.encode(),
            f"Content-Type: {content_type}\r\n\r\n".encode(),
            file_path.read_bytes(),
            b"\r\n",
        ])
    chunks.append(f"--{boundary}--\r\n".encode())
    return b"".join(chunks), f"multipart/form-data; boundary={boundary}"


def build_payload(model_id, prompt, size, quality, n, response_format):
    payload = {
        "model": model_id,
        "prompt": prompt,
        "size": normalize_size(size),
        "n": n,
        "response_format": response_format,
    }
    if quality:
        payload["quality"] = quality
    return payload


def should_use_async(mode, images, mask, n, size):
    """auto 模式: 参考图多、请求体大、多张输出或 4K 时改走异步,其余走同步。"""
    if mode == MODE_SYNC:
        return False
    if mode == MODE_ASYNC:
        return True
    # auto
    image_count = len(images or []) + (1 if mask else 0)
    if image_count >= AUTO_ASYNC_IMAGE_COUNT:
        return True
    total_bytes = 0
    for path in (images or []):
        try:
            total_bytes += pathlib.Path(path).stat().st_size
        except OSError:
            pass
    if total_bytes >= AUTO_ASYNC_TOTAL_BYTES:
        return True
    if n and n > 1:
        return True
    if normalize_size(size) == "4K":
        return True
    return False


def build_request_once(base_url, api_key, payload, images, mask, endpoint_path):
    """构造一次 POST 请求; images 非空时走 multipart 编辑,否则走 JSON 生成。"""
    url = f"{base_url}{endpoint_path}"
    if images:
        body, content_type = build_multipart_body(payload, images, mask)
    else:
        body = json.dumps(payload).encode("utf-8")
        content_type = "application/json"
    return urllib.request.Request(
        url,
        data=body,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": content_type,
            "Accept": "application/json",
        },
        method="POST",
    )


def _http_json(request, timeout):
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        detail = error.read().decode("utf-8", errors="replace")
        try:
            detail = json.loads(detail).get("error", {}).get("message", detail)
        except (json.JSONDecodeError, AttributeError):
            pass
        raise RuntimeError(f"ThetaIO HTTP {error.code}: {detail}") from error
    except urllib.error.URLError as error:
        raise RuntimeError(f"ThetaIO 连接失败: {error.reason}") from error


def request_image_sync(base_url, api_key, payload, images, mask):
    endpoint_path = "/images/edits" if images else "/images/generations"
    request = build_request_once(base_url, api_key, payload, images, mask, endpoint_path)
    return _http_json(request, DEFAULT_TIMEOUT_SECONDS)


def request_image_async(base_url, api_key, payload, images, mask):
    """提交异步任务并轮询到完成,返回与同步接口同形的结果 (含 data[].url)。"""
    submit_path = "/images/edits/async" if images else "/images/generations/async"
    request = build_request_once(base_url, api_key, payload, images, mask, submit_path)
    submitted = _http_json(request, DEFAULT_TIMEOUT_SECONDS)

    task_id = submitted.get("task_id") or submitted.get("id")
    poll_url = submitted.get("poll_url") or (f"/images/tasks/{task_id}" if task_id else "")
    if not task_id and not poll_url:
        raise RuntimeError(f"ThetaIO 异步提交失败: {json.dumps(submitted, ensure_ascii=False)[:300]}")
    if poll_url.startswith("/v1"):
        poll_url = poll_url[len("/v1"):]
    if not poll_url:
        raise RuntimeError("ThetaIO 异步提交未返回可轮询的任务地址")

    deadline = time.time() + ASYNC_MAX_WAIT_SECONDS
    while time.time() < deadline:
        time.sleep(ASYNC_POLL_INTERVAL_SECONDS)
        poll_request = urllib.request.Request(
            f"{base_url}{poll_url}",
            headers={"Authorization": f"Bearer {api_key}", "Accept": "application/json"},
            method="GET",
        )
        task = _http_json(poll_request, 60)
        status = task.get("status")
        if status == "processing":
            continue
        if status == "completed":
            result = task.get("result")
            if isinstance(result, dict) and result.get("data"):
                return result
            raise RuntimeError(f"ThetaIO 异步完成但无图片数据: {json.dumps(task, ensure_ascii=False)[:300]}")
        error = task.get("error") or {}
        message = error.get("message") if isinstance(error, dict) else str(error)
        raise RuntimeError(f"ThetaIO 异步任务失败 (http={task.get('http_status')}): {message or status}")
    raise RuntimeError(f"ThetaIO 异步任务超时未完成 (task_id={task_id})")


def request_image(prompt, model, size, quality, n, response_format, images, mask,
                  config_path, mode=DEFAULT_MODE, verbose=True):
    base_url, api_key, config_model = load_runtime_config(config_path)
    model_id = model or config_model
    if not model_id:
        raise RuntimeError("未指定模型; 请通过 --model 或配置中的 model 提供")

    payload = build_payload(model_id, prompt, size, quality, n, response_format)
    use_async = should_use_async(mode, images, mask, n, size)
    if verbose:
        print(f"请求方式: {'异步 (提交后轮询)' if use_async else '同步'}")
    if use_async:
        return request_image_async(base_url, api_key, payload, images, mask), model_id
    return request_image_sync(base_url, api_key, payload, images, mask), model_id


def save_result(result, output, response_format):
    data = result.get("data") or []
    if not data:
        raise RuntimeError("ThetaIO 未返回图片数据")
    first = data[0]
    output_path = pathlib.Path(output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if response_format == "b64_json" and first.get("b64_json"):
        output_path.write_bytes(base64.b64decode(first["b64_json"]))
    elif first.get("url"):
        try:
            with urllib.request.urlopen(first["url"], timeout=DEFAULT_TIMEOUT_SECONDS) as response:
                output_path.write_bytes(response.read())
        except urllib.error.URLError as error:
            raise RuntimeError(f"图片下载失败: {error.reason}") from error
    else:
        raw_path = output_path.with_suffix(output_path.suffix + ".json")
        raw_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        raise RuntimeError(f"无法识别的图片响应; 原始响应已保存到 {raw_path}")
    return output_path


def generate_image(
    prompt: str,
    output: str | pathlib.Path,
    size: str = DEFAULT_SIZE,
    model: str | None = None,
    images: list[str | pathlib.Path] | None = None,
    mask: str | pathlib.Path | None = None,
    quality: str | None = None,
    n: int = 1,
    response_format: str = "b64_json",
    config_path: str | None = None,
    mode: str = DEFAULT_MODE,
    verbose: bool = True,
) -> pathlib.Path:
    """生成或编辑图片并返回输出路径,供脚本和批量任务复用。"""
    prompt_text = prompt.strip()
    if not prompt_text:
        raise RuntimeError("prompt 不能为空")
    if n < 1:
        raise RuntimeError("--n 必须至少为 1")
    image_paths = [str(path) for path in images] if images else None

    if verbose:
        kind = "图生图" if image_paths else "文生图"
        print(f"模式: {kind}")
        print(f"尺寸: {normalize_size(size)}")

    result, model_id = request_image(
        prompt_text, model, size, quality, n, response_format, image_paths, mask,
        config_path, mode=mode, verbose=verbose,
    )
    output_path = save_result(result, output, response_format)
    if verbose:
        print(f"成功: {output_path} (model={model_id}, size={normalize_size(size)})")
    return output_path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="ThetaIO 通用图片生成脚本")
    parser.add_argument("--prompt", required=True, help="图片提示词")
    parser.add_argument("--output", help="输出图片路径; 不传时打印返回的图片 URL")
    parser.add_argument("--image", action="append", help="参考图路径; 可重复传入,传入后走图生图")
    parser.add_argument("--mask", help="可选透明 PNG 蒙版,用于局部编辑")
    parser.add_argument("--model", help=f"模型,默认 {DEFAULT_MODEL}; ThetaIO 支持 gpt-image-2 与 gpt-image-2.5,其他兼容服务商可传对应模型名")
    parser.add_argument("--size", default=DEFAULT_SIZE, help="尺寸: 1K、2K、4K,默认 2K")
    parser.add_argument("--quality", help="可选质量参数,透传给网关")
    parser.add_argument("--n", type=int, default=1, help="生成数量,默认 1")
    parser.add_argument("--response-format", choices=("url", "b64_json"), default="b64_json")
    parser.add_argument("--config", help="可选 scripts/config.local 路径")
    parser.add_argument(
        "--mode", choices=SUPPORTED_MODES, default=DEFAULT_MODE,
        help="请求方式: auto(默认,按请求大小自动选)、sync(同步等待)、async(异步提交后轮询)",
    )
    parser.add_argument("--quiet", action="store_true", help="减少日志输出")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        if args.output:
            generate_image(
                prompt=args.prompt,
                output=args.output,
                size=args.size,
                model=args.model,
                images=args.image,
                mask=args.mask,
                quality=args.quality,
                n=args.n,
                response_format=args.response_format,
                config_path=args.config,
                mode=args.mode,
                verbose=not args.quiet,
            )
        else:
            result, model_id = request_image(
                args.prompt, args.model, args.size, args.quality, args.n,
                args.response_format, args.image, args.mask, args.config,
                mode=args.mode, verbose=not args.quiet,
            )
            urls = [item["url"] for item in result.get("data", []) if item.get("url")]
            if urls:
                print("\n".join(urls))
            else:
                print(f"ThetaIO 返回图片数据 (model={model_id}); 传入 --output 可保存文件。")
        return 0
    except (RuntimeError, ValueError, OSError) as error:
        print(f"错误: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
