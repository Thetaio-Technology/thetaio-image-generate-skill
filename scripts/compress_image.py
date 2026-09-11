"""
图片生成器技能的图片压缩脚本。

默认行为是保留原图,把压缩后的图片写到新路径。适用于生成后发布、上传、
分享或归档前的轻量后处理。
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

from PIL import Image, ImageOps


SUPPORTED_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".tif", ".tiff"}
DEFAULT_FORMAT = "webp"
DEFAULT_QUALITY = 80
DEFAULT_SUFFIX = "-compressed"
JPEG_BACKGROUND = (255, 255, 255)


@dataclass(frozen=True)
class CompressResult:
    input: str
    output: str
    input_size: int
    output_size: int
    ratio: float
    format: str
    quality: int


def normalize_format(raw_format: str) -> str:
    normalized = raw_format.lower().strip()
    if normalized == "jpg":
        normalized = "jpeg"
    assert normalized in {"webp", "png", "jpeg"}, "format 必须是 webp、png 或 jpeg"
    return normalized


def format_to_extension(image_format: str) -> str:
    return ".jpg" if image_format == "jpeg" else f".{image_format}"


def is_supported_image(path: Path) -> bool:
    return path.is_file() and path.suffix.lower() in SUPPORTED_EXTENSIONS


def collect_image_files(input_path: Path, recursive: bool) -> list[Path]:
    if input_path.is_file():
        assert is_supported_image(input_path), f"不支持的图片格式: {input_path.suffix}"
        return [input_path]

    assert input_path.is_dir(), f"输入路径不存在或不是文件/目录: {input_path}"
    pattern = "**/*" if recursive else "*"
    image_files = [path for path in input_path.glob(pattern) if is_supported_image(path)]
    assert image_files, "没有找到可压缩的图片文件"
    return sorted(image_files)


def resolve_output_path(
    image_path: Path,
    input_root: Path,
    output_arg: str | None,
    image_format: str,
    suffix: str,
) -> Path:
    output_extension = format_to_extension(image_format)

    if output_arg:
        requested_output = Path(output_arg).expanduser()
        if input_root.is_file() and requested_output.suffix:
            return requested_output.resolve()

        relative_path = image_path.name if input_root.is_file() else image_path.relative_to(input_root)
        return (requested_output / relative_path).with_suffix(output_extension).resolve()

    if image_path.suffix.lower() == output_extension:
        return image_path.with_name(f"{image_path.stem}{suffix}{output_extension}").resolve()
    return image_path.with_suffix(output_extension).resolve()


def prepare_image_for_format(image: Image.Image, image_format: str) -> Image.Image:
    normalized_image = ImageOps.exif_transpose(image)

    if image_format == "jpeg":
        if normalized_image.mode in {"RGBA", "LA"}:
            background = Image.new("RGB", normalized_image.size, JPEG_BACKGROUND)
            alpha_channel = normalized_image.getchannel("A")
            background.paste(normalized_image.convert("RGBA"), mask=alpha_channel)
            return background
        return normalized_image.convert("RGB")

    if image_format == "png":
        return normalized_image

    if normalized_image.mode == "P":
        return normalized_image.convert("RGBA")
    return normalized_image


def save_compressed_image(image: Image.Image, output_path: Path, image_format: str, quality: int) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    save_options: dict[str, object] = {"optimize": True}

    if image_format == "webp":
        save_options.update({"quality": quality, "method": 6})
        image.save(output_path, "WEBP", **save_options)
    elif image_format == "jpeg":
        save_options.update({"quality": quality, "progressive": True})
        image.save(output_path, "JPEG", **save_options)
    else:
        image.save(output_path, "PNG", **save_options)


def compress_one(
    image_path: Path,
    output_path: Path,
    image_format: str,
    quality: int,
    overwrite: bool,
) -> CompressResult:
    input_path = image_path.resolve()
    output_path = output_path.resolve()

    assert input_path.exists(), f"输入文件不存在: {input_path}"
    if input_path == output_path and not overwrite:
        raise AssertionError("输出路径不能覆盖原图; 如确实需要覆盖,请显式传入 --overwrite")

    input_size = input_path.stat().st_size
    with Image.open(input_path) as source_image:
        prepared_image = prepare_image_for_format(source_image, image_format)
        save_compressed_image(prepared_image, output_path, image_format, quality)

    output_size = output_path.stat().st_size
    return CompressResult(
        input=str(input_path),
        output=str(output_path),
        input_size=input_size,
        output_size=output_size,
        ratio=output_size / input_size if input_size else 0,
        format=image_format,
        quality=quality,
    )


def format_size(byte_count: int) -> str:
    if byte_count < 1024:
        return f"{byte_count}B"
    if byte_count < 1024 * 1024:
        return f"{round(byte_count / 1024)}KB"
    return f"{byte_count / (1024 * 1024):.1f}MB"


def print_human_result(result: CompressResult) -> None:
    reduction = round((1 - result.ratio) * 100)
    print(
        f"{result.input} -> {result.output} "
        f"({format_size(result.input_size)} -> {format_size(result.output_size)}, {reduction}% reduction)"
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="通用图片压缩脚本")
    parser.add_argument("input", help="输入图片文件或目录")
    parser.add_argument("--output", "-o", help="输出文件或目录; 目录输入时会保留相对路径")
    parser.add_argument("--format", "-f", default=DEFAULT_FORMAT, help=f"输出格式: webp、png、jpeg,默认 {DEFAULT_FORMAT}")
    parser.add_argument("--quality", "-q", type=int, default=DEFAULT_QUALITY, help=f"压缩质量 0-100,默认 {DEFAULT_QUALITY}")
    parser.add_argument("--recursive", "-r", action="store_true", help="递归处理目录")
    parser.add_argument("--suffix", default=DEFAULT_SUFFIX, help=f"同格式输出时使用的后缀,默认 {DEFAULT_SUFFIX}")
    parser.add_argument("--overwrite", action="store_true", help="允许输出路径覆盖原图")
    parser.add_argument("--json", action="store_true", help="输出 JSON 结果")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        image_format = normalize_format(args.format)
        assert 0 <= args.quality <= 100, "quality 必须在 0-100 之间"
        assert args.suffix, "suffix 不能为空"

        input_path = Path(args.input).expanduser().resolve()
        image_files = collect_image_files(input_path, recursive=args.recursive)
        results: list[CompressResult] = []
        errors: list[dict[str, str]] = []

        for image_file in image_files:
            try:
                output_path = resolve_output_path(
                    image_path=image_file,
                    input_root=input_path,
                    output_arg=args.output,
                    image_format=image_format,
                    suffix=args.suffix,
                )
                result = compress_one(
                    image_path=image_file,
                    output_path=output_path,
                    image_format=image_format,
                    quality=args.quality,
                    overwrite=args.overwrite,
                )
                results.append(result)
                if not args.json:
                    print_human_result(result)
            except Exception as exc:  # noqa: BLE001
                errors.append({"input": str(image_file), "error": str(exc)})
                if not args.json:
                    print(f"错误: {image_file}: {exc}", file=sys.stderr)

        if args.json:
            total_input_size = sum(result.input_size for result in results)
            total_output_size = sum(result.output_size for result in results)
            payload = {
                "success": not errors,
                "files": [asdict(result) for result in results],
                "errors": errors,
                "summary": {
                    "total_files": len(results),
                    "total_input_size": total_input_size,
                    "total_output_size": total_output_size,
                    "ratio": total_output_size / total_input_size if total_input_size else 0,
                },
            }
            print(json.dumps(payload, ensure_ascii=False, indent=2))
        elif results:
            total_input_size = sum(result.input_size for result in results)
            total_output_size = sum(result.output_size for result in results)
            reduction = round((1 - total_output_size / total_input_size) * 100) if total_input_size else 0
            print(
                f"\n总结: {len(results)} 个文件, "
                f"{format_size(total_input_size)} -> {format_size(total_output_size)}, {reduction}% reduction"
            )

        return 1 if errors else 0
    except Exception as exc:  # noqa: BLE001
        print(f"错误: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
