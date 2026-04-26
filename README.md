# 🎨 Codex ImageGen

Python wrapper để tạo và chỉnh sửa hình ảnh thông qua `codex exec`, sử dụng built-in `image_gen` tool của Codex CLI.

**Không cần `OPENAI_API_KEY`** — Codex tự xử lý authentication qua ChatGPT OAuth.

Sau khi setup, dùng script này để tạo Skill cho Antigravity/Claude... để có thể tạo ảnh bằng OpenAI Image-Gen-2. Chi tiết: https://www.facebook.com/nguyenhung.vietnix/posts/pfbid02vz9wF97a85TKxBNriTHduxpJjvg17HAeT84HFzfwB7DQ7sQV8g7pK4fCxsmmZ9nhl

## Yêu cầu

- [Codex CLI](https://github.com/openai/codex) đã cài đặt và đăng nhập (`codex login`)
- Python 3.8+

## Cài đặt

```bash
git clone https://github.com/hung-vietnix/python-codex-imagegen.git
cd python-codex-imagegen
```

Không cần cài thêm dependencies — script chỉ dùng thư viện chuẩn Python.

## Cách dùng

### Tạo ảnh

```bash
# Cơ bản
python3 codex_imagegen.py generate -p "A sunset over the ocean" -o sunset.png

# Với size và quality
python3 codex_imagegen.py gen -p "Mountain landscape" -o mountain.png --size landscape --quality high

# Với prompt augmentation
python3 codex_imagegen.py gen -p "A ceramic coffee mug" -o mug.png \
  --use-case product-mockup \
  --style "clean product photography" \
  --constraints "no logos, no text"
```

### Chỉnh sửa ảnh

```bash
python3 codex_imagegen.py edit -i photo.png -p "Add a rainbow to the sky" -o edited.png

# Với mask
python3 codex_imagegen.py edit -i photo.png -p "Replace background" -o edited.png --mask mask.png
```

### Batch generate

```bash
# Từ file text (mỗi dòng 1 prompt)
python3 codex_imagegen.py batch -f prompts.txt --output-dir ./images

# Từ file JSONL (hỗ trợ per-prompt options)
python3 codex_imagegen.py batch -f prompts.jsonl --output-dir ./images --quality high
```

### Dry-run

Xem instruction sẽ gửi cho Codex mà không thực sự generate:

```bash
python3 codex_imagegen.py gen -p "Test prompt" --dry-run
```

## Size aliases

| Alias | Kích thước |
|---|---|
| `square` | 1024×1024 |
| `landscape` | 1536×1024 |
| `portrait` | 1024×1536 |
| `2k-square` | 2048×2048 |
| `2k-landscape` | 2048×1152 |
| `4k-landscape` | 3840×2160 |
| `4k-portrait` | 2160×3840 |
| `auto` | Tự động (mặc định) |

## Prompt augmentation

Script hỗ trợ structured prompt theo [imagegen skill spec](https://github.com/openai/codex) với các field:

```bash
python3 codex_imagegen.py gen -p "A wolf in snow" \
  --use-case photorealistic-natural \
  --style "wildlife photography" \
  --composition "eye-level, close-up" \
  --lighting "golden hour, dramatic shadows" \
  --palette "cool blues and whites" \
  --constraints "no text, no watermark" \
  --negative "blurry, low quality"
```

## Batch file format

**Text** — mỗi dòng 1 prompt:
```text
A sunset over the ocean
A cat sitting on a windowsill
A futuristic cityscape
```

**JSONL** — mỗi dòng 1 JSON object:
```jsonl
{"prompt": "A sunset over the ocean", "size": "landscape", "quality": "high"}
{"prompt": "A cat on a windowsill", "use_case": "photorealistic-natural"}
{"prompt": "A futuristic city", "style": "concept art", "size": "2k-landscape"}
```

## Cách hoạt động

```
codex_imagegen.py
      │
      ▼
  codex exec --full-auto
      │
      ▼
  Built-in image_gen tool (ChatGPT OAuth)
      │
      ▼
  ~/.codex/generated_images/
      │
      ▼
  Copy → output file
```

1. Script gửi structured prompt tới `codex exec --full-auto`
2. Codex sử dụng built-in `image_gen` tool (không cần API key)
3. Ảnh được lưu vào `~/.codex/generated_images/`
4. Script detect ảnh mới và copy tới output path

## Use-case taxonomy

| Slug | Mô tả |
|---|---|
| `photorealistic-natural` | Ảnh chụp tự nhiên, lifestyle |
| `product-mockup` | Ảnh sản phẩm, packaging |
| `ui-mockup` | Mockup giao diện app/web |
| `infographic-diagram` | Infographic, biểu đồ |
| `ads-marketing` | Ảnh quảng cáo, marketing |
| `logo-brand` | Logo, brand identity |
| `illustration-story` | Minh họa, truyện tranh |
| `stylized-concept` | Concept art, 3D render |
| `historical-scene` | Cảnh lịch sử |

## License

MIT
