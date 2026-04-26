#!/usr/bin/env python3
"""
Codex ImageGen — Tạo hình ảnh bằng `codex exec`.

Sử dụng built-in image_gen tool của Codex (KHÔNG cần OPENAI_API_KEY).
Authentication do Codex xử lý qua ChatGPT OAuth.

Yêu cầu:
    - Codex CLI đã cài và đã login (`codex login`)

Cách dùng:
    # Tạo ảnh đơn giản
    python codex_imagegen.py generate -p "A futuristic city at sunset"

    # Tạo ảnh với options
    python codex_imagegen.py generate -p "Mountain landscape" -o mountain.png --size landscape --quality high

    # Edit ảnh
    python codex_imagegen.py edit -i input.png -p "Add snow to the scene" -o winter.png

    # Batch generate từ file
    python codex_imagegen.py batch -f prompts.txt --output-dir ./images

    # Dry-run (xem prompt sẽ gửi cho Codex)
    python codex_imagegen.py generate -p "Test prompt" --dry-run
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Dict, List, Optional


# ─── Constants ───────────────────────────────────────────────────────────────

CODEX_HOME = Path(os.environ.get("CODEX_HOME", os.path.expanduser("~/.codex")))
GENERATED_IMAGES_DIR = CODEX_HOME / "generated_images"

DEFAULT_QUALITY = "medium"
DEFAULT_FORMAT = "png"

# Alias → WxH (từ skill spec)
SIZE_ALIASES: Dict[str, str] = {
    "square": "1024x1024",
    "landscape": "1536x1024",
    "portrait": "1024x1536",
    "2k-square": "2048x2048",
    "2k-landscape": "2048x1152",
    "4k-landscape": "3840x2160",
    "4k-portrait": "2160x3840",
    "auto": "auto",
}

# Use-case taxonomy slugs (từ SKILL.md)
USE_CASES = [
    "photorealistic-natural", "product-mockup", "ui-mockup",
    "infographic-diagram", "scientific-educational", "ads-marketing",
    "productivity-visual", "logo-brand", "illustration-story",
    "stylized-concept", "historical-scene",
]


# ─── Helpers ─────────────────────────────────────────────────────────────────

def _resolve_size(size_input: str) -> str:
    """Chuyển alias sang WIDTHxHEIGHT."""
    return SIZE_ALIASES.get(size_input.lower(), size_input)


def _find_codex() -> str:
    """Tìm binary `codex` trong PATH."""
    path = shutil.which("codex")
    if not path:
        print("❌ Không tìm thấy `codex` trong PATH.", file=sys.stderr)
        print("   Cài Codex CLI: https://github.com/openai/codex", file=sys.stderr)
        sys.exit(1)
    return path


def _slugify(text: str) -> str:
    """Tạo filename-safe string."""
    text = text.strip().lower()
    text = re.sub(r"[^a-z0-9]+", "_", text)
    text = re.sub(r"_{2,}", "_", text).strip("_")
    return text[:50] or "image"


def _snapshot_generated_images() -> Dict[str, float]:
    """Chụp snapshot mtime của tất cả ảnh trong generated_images."""
    result: Dict[str, float] = {}
    if not GENERATED_IMAGES_DIR.exists():
        return result
    for ext in ("*.png", "*.jpg", "*.jpeg", "*.webp"):
        for f in GENERATED_IMAGES_DIR.rglob(ext):
            result[str(f)] = f.stat().st_mtime
    return result


def _find_new_images(before: Dict[str, float]) -> List[Path]:
    """Tìm ảnh mới xuất hiện sau khi chạy codex exec."""
    new_files: List[Path] = []
    if not GENERATED_IMAGES_DIR.exists():
        return new_files
    for ext in ("*.png", "*.jpg", "*.jpeg", "*.webp"):
        for f in GENERATED_IMAGES_DIR.rglob(ext):
            key = str(f)
            if key not in before or f.stat().st_mtime > before[key]:
                new_files.append(f)
    # Sắp xếp theo mtime mới nhất
    new_files.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return new_files


def _run_codex(prompt: str, *, timeout: int = 300) -> subprocess.CompletedProcess:
    """Chạy `codex exec` với full-auto."""
    codex_bin = _find_codex()
    cmd = [
        codex_bin, "exec",
        "--full-auto",
        "--skip-git-repo-check",
        prompt,
    ]
    print(f"   🔧 Running: codex exec --full-auto ...", file=sys.stderr)
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)


def _build_augmented_prompt(
    prompt: str,
    *,
    use_case: Optional[str] = None,
    style: Optional[str] = None,
    composition: Optional[str] = None,
    lighting: Optional[str] = None,
    palette: Optional[str] = None,
    constraints: Optional[str] = None,
    negative: Optional[str] = None,
) -> str:
    """Xây dựng structured prompt theo skill spec schema."""
    sections: List[str] = []
    if use_case:
        sections.append(f"Use case: {use_case}")
    sections.append(f"Primary request: {prompt}")
    if style:
        sections.append(f"Style/medium: {style}")
    if composition:
        sections.append(f"Composition/framing: {composition}")
    if lighting:
        sections.append(f"Lighting/mood: {lighting}")
    if palette:
        sections.append(f"Color palette: {palette}")
    if constraints:
        sections.append(f"Constraints: {constraints}")
    if negative:
        sections.append(f"Avoid: {negative}")
    return "\n".join(sections)


# ─── Core: Generate ─────────────────────────────────────────────────────────


def generate_image(
    prompt: str,
    output: str,
    *,
    size: str = "auto",
    quality: str = DEFAULT_QUALITY,
    output_format: str = DEFAULT_FORMAT,
    use_case: Optional[str] = None,
    style: Optional[str] = None,
    composition: Optional[str] = None,
    lighting: Optional[str] = None,
    palette: Optional[str] = None,
    constraints: Optional[str] = None,
    negative: Optional[str] = None,
    dry_run: bool = False,
) -> List[str]:
    """
    Tạo hình ảnh qua `codex exec` (built-in image_gen tool).

    Codex tự xử lý authentication — KHÔNG cần OPENAI_API_KEY.

    Returns:
        Danh sách đường dẫn file đã lưu.
    """
    size = _resolve_size(size)
    output_path = Path(output).resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Build augmented prompt
    aug_prompt = _build_augmented_prompt(
        prompt,
        use_case=use_case, style=style, composition=composition,
        lighting=lighting, palette=palette, constraints=constraints,
        negative=negative,
    )

    # Prompt cho codex exec — yêu cầu dùng built-in image_gen tool
    codex_instruction = (
        f"Generate an image using the built-in image_gen tool with these specs:\n"
        f"{aug_prompt}\n"
        f"- Size: {size}\n"
        f"- Quality: {quality}\n"
        f"- Output format: {output_format}\n\n"
        f"After generating, copy the image file to: {output_path}\n"
        f"Only generate the image and copy it. Do not do anything else."
    )

    print(f"🎨 Generating image via Codex...")
    print(f"   Prompt : {prompt[:100]}{'...' if len(prompt) > 100 else ''}")
    print(f"   Size   : {size}")
    print(f"   Quality: {quality}")
    print(f"   Output : {output_path}")

    if dry_run:
        print(f"\n📋 Dry-run — Codex instruction:")
        print(f"{'─' * 60}")
        print(codex_instruction)
        print(f"{'─' * 60}")
        return []

    # Snapshot trước khi chạy
    before = _snapshot_generated_images()
    started = time.time()

    result = _run_codex(codex_instruction)
    elapsed = time.time() - started

    if result.returncode != 0:
        print(f"❌ codex exec failed (exit code: {result.returncode})", file=sys.stderr)
        if result.stderr:
            print(f"   Stderr: {result.stderr[:500]}", file=sys.stderr)
        if result.stdout:
            print(f"   Stdout: {result.stdout[:500]}", file=sys.stderr)
        sys.exit(result.returncode)

    # Case 1: Codex đã copy file tới output_path
    if output_path.exists() and output_path.stat().st_size > 0:
        print(f"✅ Done in {elapsed:.1f}s")
        print(f"   💾 Saved: {output_path}")
        return [str(output_path)]

    # Case 2: Tìm ảnh mới trong generated_images và copy
    new_images = _find_new_images(before)
    if new_images:
        src = new_images[0]
        shutil.copy2(str(src), str(output_path))
        print(f"✅ Done in {elapsed:.1f}s")
        print(f"   💾 Copied from cache: {src.name} → {output_path}")
        return [str(output_path)]

    print("⚠️  codex exec completed but no image file found.", file=sys.stderr)
    if result.stdout:
        print(f"   Stdout: {result.stdout[:300]}", file=sys.stderr)
    return []


# ─── Core: Edit ──────────────────────────────────────────────────────────────


def edit_image(
    image_path: str,
    prompt: str,
    output: str,
    *,
    mask_path: Optional[str] = None,
    dry_run: bool = False,
) -> List[str]:
    """
    Chỉnh sửa hình ảnh qua `codex exec`.

    Returns:
        Danh sách đường dẫn file đã lưu.
    """
    image_abs = Path(image_path).resolve()
    if not image_abs.exists():
        print(f"❌ Image file not found: {image_path}", file=sys.stderr)
        sys.exit(1)

    output_path = Path(output).resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)

    mask_info = ""
    if mask_path:
        mask_abs = Path(mask_path).resolve()
        if not mask_abs.exists():
            print(f"❌ Mask file not found: {mask_path}", file=sys.stderr)
            sys.exit(1)
        mask_info = f"\n- Mask file: {mask_abs}"

    codex_instruction = (
        f"Edit the image at: {image_abs}\n"
        f"- Edit instruction: {prompt}{mask_info}\n"
        f"- Preserve all parts of the image except what needs to change.\n"
        f"Save the edited image to: {output_path}\n"
        f"Only edit and save. Do not do anything else."
    )

    print(f"✏️  Editing image via Codex...")
    print(f"   Input : {image_abs}")
    print(f"   Prompt: {prompt[:100]}{'...' if len(prompt) > 100 else ''}")
    print(f"   Output: {output_path}")

    if dry_run:
        print(f"\n📋 Dry-run — Codex instruction:")
        print(f"{'─' * 60}")
        print(codex_instruction)
        print(f"{'─' * 60}")
        return []

    before = _snapshot_generated_images()
    started = time.time()

    result = _run_codex(codex_instruction)
    elapsed = time.time() - started

    if result.returncode != 0:
        print(f"❌ codex exec failed (exit code: {result.returncode})", file=sys.stderr)
        if result.stderr:
            print(f"   Stderr: {result.stderr[:500]}", file=sys.stderr)
        sys.exit(result.returncode)

    if output_path.exists() and output_path.stat().st_size > 0:
        print(f"✅ Done in {elapsed:.1f}s")
        print(f"   💾 Saved: {output_path}")
        return [str(output_path)]

    new_images = _find_new_images(before)
    if new_images:
        src = new_images[0]
        shutil.copy2(str(src), str(output_path))
        print(f"✅ Done in {elapsed:.1f}s")
        print(f"   💾 Copied from cache: {src.name} → {output_path}")
        return [str(output_path)]

    print("⚠️  No edited image found.", file=sys.stderr)
    return []


# ─── Core: Batch ─────────────────────────────────────────────────────────────


def batch_generate(
    prompts_file: str,
    output_dir: str,
    *,
    size: str = "auto",
    quality: str = DEFAULT_QUALITY,
    output_format: str = DEFAULT_FORMAT,
    dry_run: bool = False,
) -> List[str]:
    """
    Tạo nhiều ảnh từ file prompts (text/JSONL, mỗi dòng 1 prompt).

    Returns:
        Danh sách đường dẫn file đã tạo.
    """
    pf = Path(prompts_file)
    if not pf.exists():
        print(f"❌ Prompts file not found: {prompts_file}", file=sys.stderr)
        sys.exit(1)

    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    lines = pf.read_text(encoding="utf-8").strip().splitlines()
    prompts: List[Dict] = []

    for line in lines:
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("{"):
            try:
                data = json.loads(line)
                prompts.append(data)
                continue
            except json.JSONDecodeError:
                pass
        prompts.append({"prompt": line})

    if not prompts:
        print("❌ No prompts found in file.", file=sys.stderr)
        sys.exit(1)

    print(f"📦 Batch: {len(prompts)} prompts → {out_dir}")
    saved: List[str] = []

    for idx, item in enumerate(prompts, start=1):
        prompt_text = item.get("prompt", str(item))
        slug = _slugify(prompt_text[:60])
        filename = f"{idx:03d}_{slug}.{output_format}"
        output = str(out_dir / filename)

        print(f"\n{'━' * 50}")
        print(f"  [{idx}/{len(prompts)}]")

        files = generate_image(
            prompt_text, output,
            size=item.get("size", size),
            quality=item.get("quality", quality),
            output_format=output_format,
            use_case=item.get("use_case"),
            style=item.get("style"),
            constraints=item.get("constraints"),
            negative=item.get("negative"),
            dry_run=dry_run,
        )
        saved.extend(files)

    print(f"\n🎉 Batch done! Created {len(saved)}/{len(prompts)} images.")
    return saved


# ─── CLI ─────────────────────────────────────────────────────────────────────


def _add_common_args(parser: argparse.ArgumentParser) -> None:
    """Thêm arguments chung cho generate/edit."""
    parser.add_argument("--dry-run", action="store_true", help="Xem instruction, không gọi Codex")
    parser.add_argument("--timeout", type=int, default=300, help="Timeout (giây, mặc định: 300)")


def main():
    parser = argparse.ArgumentParser(
        description="🎨 Codex ImageGen — Tạo ảnh bằng `codex exec` (không cần API key)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=f"""\
Size aliases: {', '.join(f'{k}={v}' for k, v in SIZE_ALIASES.items())}

Examples:
  python codex_imagegen.py generate -p "A sunset over the ocean" -o sunset.png
  python codex_imagegen.py generate -p "Logo design" --size square --quality high
  python codex_imagegen.py edit -i photo.png -p "Add a rainbow" -o edited.png
  python codex_imagegen.py batch -f prompts.txt --output-dir ./images
""",
    )

    subs = parser.add_subparsers(dest="command", help="Command")

    # ── generate ──
    gen = subs.add_parser("generate", aliases=["gen", "g"], help="Tạo ảnh mới")
    gen.add_argument("-p", "--prompt", required=True, help="Prompt mô tả ảnh")
    gen.add_argument("-o", "--output", default="output.png", help="File output")
    gen.add_argument("-s", "--size", default="auto", help="Kích thước (alias hoặc WxH)")
    gen.add_argument("-q", "--quality", default=DEFAULT_QUALITY, choices=["low", "medium", "high", "auto"])
    gen.add_argument("--format", default=DEFAULT_FORMAT, choices=["png", "jpeg", "webp"])
    gen.add_argument("--use-case", choices=USE_CASES, help="Use-case taxonomy")
    gen.add_argument("--style", help="Style/medium")
    gen.add_argument("--composition", help="Composition/framing")
    gen.add_argument("--lighting", help="Lighting/mood")
    gen.add_argument("--palette", help="Color palette")
    gen.add_argument("--constraints", help="Constraints (must keep)")
    gen.add_argument("--negative", help="Avoid (negative constraints)")
    _add_common_args(gen)

    # ── edit ──
    edt = subs.add_parser("edit", aliases=["e"], help="Chỉnh sửa ảnh")
    edt.add_argument("-i", "--image", required=True, help="Ảnh input")
    edt.add_argument("-p", "--prompt", required=True, help="Prompt chỉnh sửa")
    edt.add_argument("-o", "--output", default="edited.png", help="File output")
    edt.add_argument("--mask", help="File mask (PNG với alpha)")
    _add_common_args(edt)

    # ── batch ──
    bat = subs.add_parser("batch", aliases=["b"], help="Batch generate từ file")
    bat.add_argument("-f", "--file", required=True, help="File prompts (text/JSONL)")
    bat.add_argument("--output-dir", default="./generated_images", help="Thư mục output")
    bat.add_argument("-s", "--size", default="auto", help="Kích thước mặc định")
    bat.add_argument("-q", "--quality", default=DEFAULT_QUALITY, choices=["low", "medium", "high", "auto"])
    bat.add_argument("--format", default=DEFAULT_FORMAT, choices=["png", "jpeg", "webp"])
    _add_common_args(bat)

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(0)

    # ── Dispatch ──
    cmd = args.command
    if cmd in ("generate", "gen", "g"):
        generate_image(
            args.prompt, args.output,
            size=args.size, quality=args.quality, output_format=args.format,
            use_case=getattr(args, "use_case", None),
            style=getattr(args, "style", None),
            composition=getattr(args, "composition", None),
            lighting=getattr(args, "lighting", None),
            palette=getattr(args, "palette", None),
            constraints=getattr(args, "constraints", None),
            negative=getattr(args, "negative", None),
            dry_run=args.dry_run,
        )
    elif cmd in ("edit", "e"):
        edit_image(
            args.image, args.prompt, args.output,
            mask_path=getattr(args, "mask", None),
            dry_run=args.dry_run,
        )
    elif cmd in ("batch", "b"):
        batch_generate(
            args.file, args.output_dir,
            size=args.size, quality=args.quality,
            output_format=args.format,
            dry_run=args.dry_run,
        )


if __name__ == "__main__":
    main()
