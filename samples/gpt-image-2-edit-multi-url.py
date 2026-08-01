from openai import OpenAI
from pathlib import Path
from urllib.parse import urlparse
import base64
import io
import os
import requests

# 配置 API
client = OpenAI(
    api_key=os.environ.get("IMAGE_API_KEY", "sk-xxxxxxxxxx"),
    base_url="https://yibuapi.com/v1"
)

# 要编辑的图片列表，最多支持 10 张。
# 每一项可以是【本地路径】或【http(s):// 链接】，脚本会自动识别。
image_sources = [
    "https://inews.gtimg.com/om_bt/Oq2mYnXWYZDCN0XrKRPS4K83IKxKHbw0wEq1Ss7KhDztEAA/641",
    "https://inews.gtimg.com/om_bt/O4lpEyEUtxOuVaHPAZzTy2ycDiwdSIMLh1d38D3nQVRHkAA/641",
    "./b8c915b68fea534fe1eac2c2baa38d0c.png",
    "./d74d64acd6298180d1a0421792b99afd.png",
    "./image_num1.png",
    # 最多添加到第 10 张
]

# 编辑指令
prompt = """
把这几张图片按照顺序整合到一起

"""

if not image_sources:
    raise ValueError("image_sources 不能为空")
if len(image_sources) > 10:
    raise ValueError(f"最多支持 10 张图片，当前传入了 {len(image_sources)} 张")


def is_url(s: str) -> bool:
    """判断是否为 http/https 链接。"""
    try:
        scheme = urlparse(s).scheme.lower()
        return scheme in ("http", "https")
    except Exception:
        return False


def load_image(src: str):
    """把一个来源（URL 或本地路径）加载为可上传的文件对象。

    返回 (filename, file_like)。URL 的内容下载到内存的 BytesIO，
    本地的直接以二进制方式打开。
    """
    if is_url(src):
        resp = requests.get(src, timeout=60)
        resp.raise_for_status()
        # 用 URL 的最后一段作为文件名，缺省给个 .png，便于服务端识别类型
        name = os.path.basename(urlparse(src).path) or "image.png"
        if "." not in name:
            name += ".png"
        buf = io.BytesIO(resp.content)
        buf.name = name  # OpenAI SDK 会读取 .name 推断 mime 类型
        return name, buf
    else:
        p = Path(src)
        if not p.exists():
            raise FileNotFoundError(f"本地文件不存在: {src}")
        f = p.open("rb")
        return p.name, f


# 加载所有图片（URL 下载到内存，本地直接打开）
image_files = []
try:
    for src in image_sources:
        name, fobj = load_image(src)
        print(f"[加载] {'URL ' if is_url(src) else '本地'} -> {name}")
        image_files.append(fobj)

    result = client.images.edit(
        model="gpt-image-2-max",
        image=image_files if len(image_files) > 1 else image_files[0],
        prompt=prompt,
        size="3840x2160"
    )
finally:
    for f in image_files:
        try:
            f.close()
        except Exception:
            pass

img_data = base64.b64decode(result.data[0].b64_json)
output_path = "./output.png"
with open(output_path, "wb") as f:
    f.write(img_data)
print(f"已保存到: {output_path} ({len(img_data)} bytes)")
