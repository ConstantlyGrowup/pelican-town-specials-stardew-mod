from openai import OpenAI
from pathlib import Path
import base64

# 配置 API
client = OpenAI(
    api_key="sk-xxxxxxxxxxx",
    base_url="https://yibuapi.com/v1"
)

# 要编辑的图片路径列表，最多支持 10 张
image_paths = [
    "./b8c915b68fea534fe1eac2c2baa38d0c.png",
    "./d74d64acd6298180d1a0421792b99afd.png",
    "./image_num1.png",
    "./image_num2.png",
    "./image_num3.png",
    # 最多添加到第 10 张
]

# 编辑指令
prompt = """
把这几张图片按照顺序整合到一起

"""

if not image_paths:
    raise ValueError("image_paths 不能为空")
if len(image_paths) > 10:
    raise ValueError(f"最多支持 10 张图片，当前传入了 {len(image_paths)} 张")

# 打开所有图片文件
image_files = [Path(p).open("rb") for p in image_paths]

try:
    result = client.images.edit(
        model="gpt-image-2-max",
        image=image_files if len(image_files) > 1 else image_files[0],
        prompt=prompt,
        size="3840x2160"
    )
finally:
    for f in image_files:
        f.close()

img_data = base64.b64decode(result.data[0].b64_json)
output_path = "./output.png"
with open(output_path, "wb") as f:
    f.write(img_data)
print(f"已保存到: {output_path} ({len(img_data)} bytes)")
