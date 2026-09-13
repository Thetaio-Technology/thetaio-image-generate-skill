"""
ThetaIO 图片生成器技能的批量生图脚本。

任务格式:
[
  {
    "prompt": "...",
    "output": "output/raw/01.png",
    "size": "2K"
  },
  {
    "prompt_file": "output/prompts/02.md",
    "output": "output/raw/02.png",
    "ref": "output/raw/01.png",
    "size": "2K"
  },
  {
    "prompt_file": "output/prompts/03.md",
    "output": "output/raw/03.png",
    "refs": ["output/raw/01.png", "output/raw/02.png"],
    "size": "2K"
  }
]

- `ref`: 单张参考图(旧字段,继续支持)。
- `refs`: 多张参考图数组,单次请求一次携带,最多 15 张。与 `ref` 同时出现时以 `refs` 为准。

支持两阶段执行: 无参考图的任务先并发生成作为视觉锚,有参考图的任务再基于锚图
并发生成,保证同一组图片风格一致。并发时每个任务各自携带自己的参考图集合。
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

from generate_image import (
    DEFAULT_MODE,
    DEFAULT_SIZE,
    MAX_REFERENCE_IMAGES,
    SUPPORTED_MODES,
    generate_image,
    normalize_size,
)


MAX_RETRIES = 3
RETRY_BASE_SECONDS = 10
DEFAULT_WORKERS = 2
PROMPT_JOINER = "\n\n负向要求:\n"


def resolve_path(raw_path: str | Path, base_dir: Path) -> Path:
    path = Path(raw_path).expanduser()
    if not path.is_absolute():
        path = base_dir / path
    return path.resolve()


def load_prompt(task: dict[str, Any], base_dir: Path) -> str:
    prompt = task.get("prompt")
    if prompt:
        prompt_text = str(prompt).strip()
    elif task.get("prompt_file"):
        prompt_file = resolve_path(task["prompt_file"], base_dir)
        if not prompt_file.exists():
            raise RuntimeError(f"prompt_file 不存在: {prompt_file}")
        prompt_text = prompt_file.read_text(encoding="utf-8-sig").strip()
    else:
        raise RuntimeError("每个任务必须提供 prompt 或 prompt_file")

    negative_prompt = str(task.get("negative_prompt") or "").strip()
    if negative_prompt:
        prompt_text = f"{prompt_text}{PROMPT_JOINER}{negative_prompt}"
    if not prompt_text:
        raise RuntimeError("prompt 内容不能为空")
    return prompt_text


def normalize_task(task: dict[str, Any], base_dir: Path) -> dict[str, Any]:
    if not isinstance(task, dict):
        raise RuntimeError("tasks.json 中每一项必须是对象")
    if not task.get("output"):
        raise RuntimeError("每个任务必须提供 output")

    normalized = dict(task)
    normalized["prompt"] = load_prompt(task, base_dir)
    normalized["output"] = str(resolve_path(task["output"], base_dir))
    normalized["size"] = normalize_size(str(task.get("size") or DEFAULT_SIZE))
    if task.get("model"):
        normalized["model"] = str(task["model"])
    refs = resolve_refs(task, base_dir)
    if refs:
        normalized["refs"] = refs
    return normalized


def resolve_refs(task: dict[str, Any], base_dir: Path) -> list[str]:
    """解析任务的参考图: 优先 refs(数组),否则回退单张 ref。最多 15 张。"""
    raw = task.get("refs")
    if raw is None:
        raw = task.get("ref")
    if raw is None:
        return []
    if isinstance(raw, (str, Path)):
        refs = [str(raw)]
    elif isinstance(raw, list):
        refs = [str(item) for item in raw]
    else:
        raise RuntimeError("ref/refs 必须是路径字符串或路径数组")
    refs = [str(resolve_path(item, base_dir)) for item in refs if str(item).strip()]
    if len(refs) > MAX_REFERENCE_IMAGES:
        raise RuntimeError(
            f"单次请求最多支持 {MAX_REFERENCE_IMAGES} 张参考图（ThetaIO 自定义上限），"
            f"任务 output={task.get('output')} 携带了 {len(refs)} 张；一般 6~8 张就足够了"
        )
    return refs


def load_tasks(tasks_file: Path) -> list[dict[str, Any]]:
    tasks = json.loads(tasks_file.read_text(encoding="utf-8-sig"))
    if not isinstance(tasks, list) or not tasks:
        raise RuntimeError("tasks.json 必须为非空数组")
    return [normalize_task(task, tasks_file.parent) for task in tasks]


def split_tasks_by_dependency(
    tasks: list[dict[str, Any]],
) -> tuple[list[tuple[int, dict[str, Any]]], list[tuple[int, dict[str, Any]]]]:
    stage1: list[tuple[int, dict[str, Any]]] = []
    stage2: list[tuple[int, dict[str, Any]]] = []
    for index, task in enumerate(tasks):
        if task.get("refs"):
            stage2.append((index, task))
        else:
            stage1.append((index, task))
    if not stage1:
        raise RuntimeError("至少需要一个无参考图的文生图任务作为视觉锚")
    return stage1, stage2


def validate_refs(stage2: list[tuple[int, dict[str, Any]]]) -> None:
    missing_refs = [
        ref
        for _, task in stage2
        for ref in task.get("refs", [])
        if not Path(ref).exists()
    ]
    if missing_refs:
        raise RuntimeError(f"阶段二参考图未生成,无法继续: {missing_refs}")


def run_single_task(
    task: dict[str, Any], task_index: int, total: int, config_path: str | None,
    request_mode: str = DEFAULT_MODE, auto_compress: bool = True,
) -> dict[str, Any]:
    output_path = Path(task["output"])
    output_path.parent.mkdir(parents=True, exist_ok=True)
    refs = task.get("refs") or []
    mode = "img2img" if refs else "text2img"
    display_name = output_path.name

    last_error = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            result_path = generate_image(
                prompt=task["prompt"],
                images=refs if refs else None,
                output=output_path,
                size=task["size"],
                model=task.get("model"),
                config_path=config_path,
                mode=request_mode,
                auto_compress=auto_compress,
                verbose=False,
            )
            file_size = os.path.getsize(result_path)
            print(f"  [{task_index + 1}/{total}] 成功 {mode:8s} {display_name} ({file_size:,} bytes)")
            return {
                "index": task_index,
                "output": str(result_path),
                "success": True,
                "mode": mode,
                "attempts": attempt,
            }
        except Exception as exc:  # noqa: BLE001
            last_error = str(exc)[:500]
            if attempt < MAX_RETRIES:
                wait_seconds = RETRY_BASE_SECONDS * attempt
                print(
                    f"  [{task_index + 1}/{total}] 重试 {display_name} "
                    f"attempt={attempt} wait={wait_seconds}s err={last_error[:120]}"
                )
                time.sleep(wait_seconds)
            else:
                print(f"  [{task_index + 1}/{total}] 失败 {mode:8s} {display_name} err={last_error[:180]}")

    return {
        "index": task_index,
        "output": str(output_path),
        "success": False,
        "mode": mode,
        "attempts": MAX_RETRIES,
        "error": last_error,
    }


def run_stage(
    stage_name: str,
    indexed_tasks: list[tuple[int, dict[str, Any]]],
    total: int,
    max_workers: int,
    config_path: str | None,
    request_mode: str = DEFAULT_MODE,
    auto_compress: bool = True,
) -> list[dict[str, Any]]:
    if not indexed_tasks:
        return []

    worker_count = min(max_workers, len(indexed_tasks))
    print(f"\n[{stage_name}] 共 {len(indexed_tasks)} 个任务,并发 {worker_count}")
    results: list[dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=worker_count) as pool:
        futures = {
            pool.submit(run_single_task, task, index, total, config_path, request_mode, auto_compress): index
            for index, task in indexed_tasks
        }
        for future in as_completed(futures):
            results.append(future.result())
    return results


def batch_generate(
    tasks: list[dict[str, Any]], max_workers: int = DEFAULT_WORKERS, config_path: str | None = None,
    request_mode: str = DEFAULT_MODE, auto_compress: bool = True,
) -> list[dict[str, Any]]:
    if max_workers <= 0:
        raise RuntimeError("workers 必须大于 0")
    total = len(tasks)
    stage1, stage2 = split_tasks_by_dependency(tasks)

    stage1_results = run_stage("阶段一 文生图", stage1, total, max_workers, config_path, request_mode, auto_compress)
    if any(not result["success"] for result in stage1_results):
        print("\n阶段一有失败任务,跳过依赖 ref 的阶段二。")
        stage2_results = [
            {
                "index": index,
                "output": task["output"],
                "success": False,
                "mode": "img2img",
                "attempts": 0,
                "error": "阶段一视觉锚生成失败,未执行",
            }
            for index, task in stage2
        ]
    elif stage2:
        validate_refs(stage2)
        stage2_results = run_stage("阶段二 图生图", stage2, total, max_workers, config_path, request_mode, auto_compress)
    else:
        stage2_results = []

    results = stage1_results + stage2_results
    results.sort(key=lambda result: result["index"])
    ok_count = sum(1 for result in results if result["success"])
    print(f"\n总结: {ok_count}/{total} 成功")
    return results


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="ThetaIO 通用批量生图脚本")
    parser.add_argument("--batch", required=True, help="tasks.json 路径")
    parser.add_argument("--workers", type=int, default=DEFAULT_WORKERS, help=f"并发数,默认 {DEFAULT_WORKERS}")
    parser.add_argument("--result", help="结果 JSON 写入路径")
    parser.add_argument("--config", help="可选 scripts/config.local 路径")
    parser.add_argument(
        "--mode", choices=SUPPORTED_MODES, default=DEFAULT_MODE,
        help="请求方式: auto(默认,按请求大小自动选)、sync(同步等待)、async(异步提交后轮询)",
    )
    parser.add_argument(
        "--no-compress", action="store_true",
        help="关闭上传前自动压缩(默认开启): 超过阈值的参考图会转为 JPEG 再上传",
    )
    parser.add_argument("--validate-only", action="store_true", help="只校验 tasks.json,不调用图片接口")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        tasks_file = Path(args.batch).expanduser().resolve()
        if not tasks_file.exists():
            raise RuntimeError(f"tasks.json 不存在: {tasks_file}")
        tasks = load_tasks(tasks_file)

        if args.validate_only:
            split_tasks_by_dependency(tasks)
            print(f"tasks.json 校验通过: {len(tasks)} 个任务")
            return 0

        results = batch_generate(
            tasks, max_workers=args.workers, config_path=args.config,
            request_mode=args.mode, auto_compress=not args.no_compress,
        )
        if args.result:
            result_path = Path(args.result).expanduser().resolve()
            result_path.parent.mkdir(parents=True, exist_ok=True)
            result_path.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
        return 0 if all(result["success"] for result in results) else 1
    except Exception as exc:  # noqa: BLE001
        print(f"错误: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
