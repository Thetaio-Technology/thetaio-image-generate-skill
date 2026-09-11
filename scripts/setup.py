#!/usr/bin/env python
"""ThetaIO 图片生成器 —— 首次安装与配置脚本。

把 base_url 和 api_key 写入技能外部的 scripts/config.local,只做一次。
之后重复运行会检测到已有配置并直接跳过,不会重复安装。

用法:

    # 交互式(在终端里手动运行)
    python scripts/setup.py

    # 非交互式(交给 agent 或脚本调用)
    python scripts/setup.py --base-url https://api.thetaio.tech/v1 --api-key "你的密钥"

    # 覆盖已有配置
    python scripts/setup.py --force

配置写入 scripts/config.local,该文件已被 .gitignore 忽略,不会被提交。
"""

from __future__ import annotations

import argparse
import pathlib
import sys


SCRIPT_DIR = pathlib.Path(__file__).resolve().parent
CONFIG_PATH = SCRIPT_DIR / "config.local"
CONFIG_CANDIDATES = (SCRIPT_DIR / "config.local", SCRIPT_DIR / "config")
DEFAULT_BASE_URL = "https://api.thetaio.tech/v1"
DEFAULT_MODEL = "gpt-image-2"


def load_key_value_config(path: pathlib.Path) -> dict[str, str]:
    if not path.exists():
        return {}
    parsed: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8-sig").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or ":" not in line:
            continue
        key, value = line.split(":", 1)
        parsed[key.strip()] = value.split("#", 1)[0].strip()
    return parsed


def find_existing_config() -> tuple[pathlib.Path, dict[str, str]] | None:
    for candidate in CONFIG_CANDIDATES:
        if candidate.exists():
            config = load_key_value_config(candidate)
            if config.get("api_key"):
                return candidate, config
    return None


def write_config(base_url: str, api_key: str, model: str) -> pathlib.Path:
    content = (
        "# 由 scripts/setup.py 生成,请勿提交到版本库。\n"
        "# 如需重新配置,运行 python scripts/setup.py --force\n"
        f"base_url: {base_url}\n"
        f"api_key: {api_key}\n"
        f"model: {model}\n"
    )
    CONFIG_PATH.write_text(content, encoding="utf-8")
    return CONFIG_PATH


def prompt_value(label: str, default: str | None = None) -> str:
    suffix = f" [{default}]" if default else ""
    while True:
        value = input(f"{label}{suffix}: ").strip()
        if value:
            return value
        if default:
            return default
        print("该值不能为空,请重新输入。")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="ThetaIO 图片生成器安装与配置脚本")
    parser.add_argument("--base-url", help=f"ThetaIO 网关地址,默认 {DEFAULT_BASE_URL}")
    parser.add_argument("--api-key", help="ThetaIO API Key")
    parser.add_argument("--model", help=f"默认模型,默认 {DEFAULT_MODEL}; ThetaIO 用 gpt-image-2 或 gpt-image-2.5,其他服务商填对应模型名")
    parser.add_argument("--force", action="store_true", help="已有配置时强制覆盖")
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    if not args.force:
        existing = find_existing_config()
        if existing:
            path, config = existing
            print(f"已配置,跳过安装: {path}")
            print(f"base_url: {config.get('base_url', DEFAULT_BASE_URL)}")
            print(f"model: {config.get('model', DEFAULT_MODEL)}")
            print("如需修改,运行: python scripts/setup.py --force")
            return 0

    base_url = args.base_url
    api_key = args.api_key
    model = args.model

    if not base_url or not api_key:
        print("首次安装: 请填写 ThetaIO 配置(直接回车使用默认值)。")
        base_url = base_url or prompt_value("ThetaIO API 地址 (base_url)", DEFAULT_BASE_URL)
        api_key = api_key or prompt_value("ThetaIO API Key")
        model = model or prompt_value("默认模型 (gpt-image-2 / gpt-image-2.5)", DEFAULT_MODEL)

    model = model or DEFAULT_MODEL

    base_url = base_url.strip().rstrip("/")
    if not base_url:
        print("错误: base_url 不能为空", file=sys.stderr)
        return 1
    if not api_key.strip():
        print("错误: api_key 不能为空", file=sys.stderr)
        return 1

    path = write_config(base_url, api_key.strip(), model)
    print(f"配置已保存: {path}")
    print(f"base_url: {base_url}")
    print(f"model: {model}")
    print("安装完成,之后无需重复安装。")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (EOFError, KeyboardInterrupt):
        print("\n已取消。", file=sys.stderr)
        raise SystemExit(1)
