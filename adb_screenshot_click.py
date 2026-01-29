#!/usr/bin/env python3
"""
ADB截图图片匹配点击工具
功能：通过ADB截屏，匹配图片列表，匹配成功则点击图片中心位置
"""
import os
import argparse
import time
import subprocess
import cv2
import numpy as np
from pathlib import Path

class ADBScreenshotClick:
    def __init__(self, image_dir="images", temp_dir="temp"):
        self.image_dir = Path(image_dir)
        self.temp_dir = Path(temp_dir)
        self.temp_dir.mkdir(exist_ok=True)
        self.image_dir.mkdir(exist_ok=True)
        
    def take_screenshot(self):
        """通过ADB截取屏幕截图"""
        screenshot_path = self.temp_dir / "screenshot.png"
        try:
            # 执行ADB截图命令
            result = subprocess.run([
                "adb", "exec-out", "screencap", "-p"
            ], capture_output=True, check=True)
            
            # 保存截图
            with open(screenshot_path, "wb") as f:
                f.write(result.stdout)
            
            print(f"截图已保存: {screenshot_path}")
            return str(screenshot_path)
            
        except subprocess.CalledProcessError as e:
            print(f"截图失败: {e}")
            return None
        except Exception as e:
            print(f"截图异常: {e}")
            return None
    
    def load_template_images(self):
        """加载模板图片列表"""
        template_images = []
        if self.image_dir.exists():
            for img_file in self.image_dir.glob("*.png"):
                template_img = cv2.imread(str(img_file), cv2.IMREAD_COLOR)
                if template_img is not None:
                    template_images.append({
                        'path': str(img_file),
                        'image': template_img,
                        'name': img_file.stem
                    })
                    print(f"加载模板图片: {img_file.name}")
        return template_images
    
    def find_template_in_screenshot(self, screenshot_path, template_data, threshold=0.8):
        """在截图中查找模板图片"""
        # 读取截图
        screenshot = cv2.imread(screenshot_path, cv2.IMREAD_COLOR)
        if screenshot is None:
            print("无法读取截图文件")
            return None
        
        # 读取模板图片
        template = template_data['image']
        
        # 使用模板匹配
        result = cv2.matchTemplate(screenshot, template, cv2.TM_CCOEFF_NORMED)
        min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(result)
        
        print(f"匹配 {template_data['name']}: 置信度 {max_val:.3f}")
        
        if max_val >= threshold:
            # 计算匹配位置和中心点
            h, w = template.shape[:2]
            top_left = max_loc
            bottom_right = (top_left[0] + w, top_left[1] + h)
            center_x = top_left[0] + w // 2
            center_y = top_left[1] + h // 2
            
            return {
                'template': template_data['name'],
                'confidence': max_val,
                'center': (center_x, center_y),
                'bbox': (top_left, bottom_right)
            }
        
        return None
    
    def adb_tap(self, x, y):
        """通过ADB执行点击操作"""
        try:
            subprocess.run([
                "adb", "shell", "input", "tap", str(x), str(y)
            ], check=True)
            print(f"点击位置: ({x}, {y})")
            return True
        except subprocess.CalledProcessError as e:
            print(f"点击失败: {e}")
            return False
    
    def run_once(self):
        """执行一次完整的截图-匹配-点击流程"""
        print("\n" + "="*50)
        print("开始执行截图匹配流程")
        print("="*50)
        
        # 截取屏幕
        screenshot_path = self.take_screenshot()
        if not screenshot_path:
            return False
        
        # 加载模板图片
        templates = self.load_template_images()
        if not templates:
            print("未找到模板图片，请在 images/ 目录下放置PNG格式的模板图片")
            return False
        
        # 逐个匹配模板
        for template in templates:
            match_result = self.find_template_in_screenshot(screenshot_path, template)
            if match_result:
                print(f"匹配成功: {match_result['template']} (置信度: {match_result['confidence']:.3f})")
                print(f"中心位置: {match_result['center']}")
                
                # 执行点击
                x, y = match_result['center']
                if self.adb_tap(x, y):
                    print("点击执行成功!")
                    return True
                else:
                    print("点击执行失败")
                    return False
        
        print("未匹配到任何模板图片")
        return False
    
    def run_loop(self, interval=5):
        """循环执行截图匹配点击"""
        print("ADB截图图片匹配点击工具启动")
        print(f"检测间隔: {interval}秒")
        print("按 Ctrl+C 停止")
        print("请在 images/ 目录下放置需要匹配的PNG格式图片")
        
        try:
            while True:
                self.run_once()
                print(f"\n等待 {interval} 秒后继续...")
                time.sleep(interval)
                
        except KeyboardInterrupt:
            print("\n程序已停止")

def main(image_dir):
    """主函数"""
    # 创建工具实例
    adb_tool = ADBScreenshotClick(image_dir=image_dir)
    
    # 创建示例模板图片目录说明
    example_dir = adb_tool.image_dir / "example"
    example_dir.mkdir(exist_ok=True)
    
    # 创建使用说明文件
    readme_path = adb_tool.image_dir / "README.md"
    if not readme_path.exists():
        with open(readme_path, "w", encoding="utf-8") as f:
            f.write("""# 模板图片使用说明

## 图片要求
- 格式: PNG
- 内容: 需要匹配的屏幕区域截图
- 建议: 使用ADB截图后裁剪出需要匹配的部分

## 使用方法
1. 将需要匹配的图片放在此目录下
2. 图片文件名将作为匹配时的标识
3. 支持放置多个模板图片，程序会按顺序匹配

## 示例
你可以使用以下命令截取模板图片：
```bash
# 截取整个屏幕
adb exec-out screencap -p > screenshot.png

# 然后使用图片编辑工具裁剪出需要匹配的区域
```
""")
    
    # 运行循环
    adb_tool.run_loop(interval=2)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="ADB截图图片匹配点击工具")
    parser.add_argument("--image-dir", type=str, default="images", help="模板图片目录")
    args = parser.parse_args()
    if not os.path.exists(args.image_dir):
        parser.error(f"The directory {args.image_dir} does not exist.")
    main(args.image_dir)
