#!/usr/bin/env python3
"""
汽水音乐自动获取免费额度
通过adb命令操作android手机，完成自动获取汽水音乐看广告免费畅听的功能
"""

import os
import time
import subprocess
import cv2
import numpy as np

# 配置参数
TARGET_PACKAGE = "com.luna.music/com.ss.android.excitingvideo.ExcitingVideoActivity"
CONFIDENCE_THRESHOLD = 0.8
LOOP_INTERVAL = 2
MAX_NO_ACTION_COUNT = 30


class LunaMusicAuto:
    def __init__(self):
        self.device_model = None
        self.temporary_dir = ".tmp"
        self.device_dir = "phones"
        self.template_dir = None
        self.templates = []
        self.template_names = []

    def check_adb_support(self):
        """检查系统是否支持adb"""
        try:
            result = subprocess.run(["adb", "version"],
                                   capture_output=True,
                                   text=True,
                                   timeout=5)
            if result.returncode == 0:
                print("[OK] ADB 已安装")
                return True
            else:
                print("[ERROR] ADB 不可用")
                return False
        except (subprocess.TimeoutExpired, FileNotFoundError):
            print("[ERROR] 系统未安装 ADB 或 ADB 不在 PATH 中")
            return False

    def check_device_connected(self):
        """检查是否有设备连接"""
        result = subprocess.run(["adb", "devices"],
                                capture_output=True,
                                text=True,
                                timeout=5)
        lines = result.stdout.strip().split('\n')
        # 跳过第一行标题，检查是否有设备
        for line in lines[1:]:
            if line.strip() and '\tdevice' in line:
                device_id = line.split('\t')[0]
                print(f"[OK] 已连接设备: {device_id}")
                return True
        print("[ERROR] 未检测到已连接的设备")
        return False

    def get_device_model(self):
        """获取手机型号"""
        result = subprocess.run(["adb", "shell", "getprop", "ro.product.model"],
                                capture_output=True,
                                text=True,
                                timeout=5)
        model = result.stdout.strip()
        print(f"设备型号: {model}")
        self.device_model = model
        return model

    def get_current_activity(self):
        """获取当前启用的应用"""
        result = subprocess.run(["adb", "shell", "dumpsys", "window"],
                                capture_output=True,
                                text=True,
                                timeout=5)
        # 从输出中提取当前 Activity
        lines = result.stdout.split('\n')
        for line in lines:
            if 'mCurrentFocus' in line:
                # 格式类似: mCurrentFocus=Window{xxx u0 com.luna.music/com.ss.android.excitingvideo.ExcitingVideoActivity}
                parts = line.split('/')
                if len(parts) > 1:
                    activity = parts[0].split()[-1] + '/' + parts[1].split()[0].replace('}', '')
                    return activity
        return None

    def wait_for_target_activity(self):
        """等待用户进入目标应用"""
        print("\n请在手机上打开「汽水音乐 -> 右上角的\"免费\"」界面...")
        while True:
            activity = self.get_current_activity()
            if activity == TARGET_PACKAGE:
                print(f"[OK] 检测到目标应用: {TARGET_PACKAGE}")
                return True
            time.sleep(1)

    def load_templates(self):
        """加载模板图片到内存"""
        # 确定使用哪个目录
        model_dir = os.path.join(os.getcwd(), self.device_dir, self.device_model)
        default_dir = os.path.join(os.getcwd(), self.device_dir, "default")

        if os.path.exists(model_dir):
            self.template_dir = model_dir
            print(f"[OK] 使用设备型号目录: {model_dir}")
        else:
            self.template_dir = default_dir
            print(f"[WARN] 未找到设备型号目录，使用默认目录: {default_dir}")

        # 加载目录下的所有图片
        # 按顺序加载
        files = os.listdir(self.template_dir)
        files.sort()
        for filename in files:
            if filename.lower().endswith(('.png', '.jpg', '.jpeg', '.bmp')):
                filepath = os.path.join(self.template_dir, filename)
                template = cv2.imread(filepath)
                if template is not None:
                    self.templates.append(template)
                    self.template_names.append(filename)
                    print(f"  - 加载模板: {filename}")

        if not self.templates:
            print("[ERROR] 未找到任何模板图片")
            return False

        print(f"[OK] 共加载 {len(self.templates)} 个模板")
        return True

    def capture_screen(self):
        """截屏并返回图像"""
        # 使用 ADB 截屏到设备临时文件
        subprocess.run(["adb", "shell", "screencap", "-p", "/sdcard/screen.png"],
                       capture_output=True,
                       timeout=5)
        
        # 创建临时目录
        if not os.path.exists(self.temporary_dir):
            os.mkdir(self.temporary_dir)
        screen_shot_local_dir = os.path.join(self.temporary_dir, "screen.png")

        # 拉取到本地
        subprocess.run(["adb", "pull", "/sdcard/screen.png", screen_shot_local_dir],
                       capture_output=True,
                       timeout=5)

        # 读取图像
        image = cv2.imread(screen_shot_local_dir)
        return image

    def find_and_click_template(self, screen):
        """查找模板并点击"""
        if screen is None:
            return False

        gray_screen = cv2.cvtColor(screen, cv2.COLOR_BGR2GRAY)

        for i, template in enumerate(self.templates):
            # 模板图片是从屏幕截图中直接提取的部分，不需要缩放
            template_gray = cv2.cvtColor(template, cv2.COLOR_BGR2GRAY)

            # 模板匹配
            result = cv2.matchTemplate(gray_screen, template_gray, cv2.TM_CCOEFF_NORMED)
            min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(result)

            if max_val >= CONFIDENCE_THRESHOLD:
                # 计算中心点坐标
                h, w = template.shape[:2]
                center_x = max_loc[0] + w // 2
                center_y = max_loc[1] + h // 2

                # 点击该位置
                self.click_position(center_x, center_y)
                print(f"[MATCH] 匹配到 [{self.template_names[i]}] (置信度: {max_val:.3f}), 点击 ({center_x}, {center_y})")
                return True

        return False

    def click_position(self, x, y):
        """点击指定位置"""
        subprocess.run(["adb", "shell", "input", "tap", str(x), str(y)],
                      capture_output=True,
                      timeout=5)

    def run(self):
        """主运行逻辑"""
        print("=" * 50)
        print("汽水音乐自动获取免费额度")
        print("=" * 50)

        # 1. 检查 ADB 支持
        if not self.check_adb_support():
            print("程序退出")
            return

        # 2. 检查设备连接
        if not self.check_device_connected():
            print("程序退出")
            return

        # 3. 获取手机型号
        self.get_device_model()

        # 4. 等待目标应用
        self.wait_for_target_activity()

        # 5. 加载模板
        if not self.load_templates():
            print("程序退出")
            return

        # 6-8. 主循环
        no_action_count = 0
        print("\n开始自动化操作...")
        print(f"配置: 间隔={LOOP_INTERVAL}秒, 阈值={CONFIDENCE_THRESHOLD}, 最大无操作={MAX_NO_ACTION_COUNT}次")

        while no_action_count < MAX_NO_ACTION_COUNT:
            # 截屏
            screen = self.capture_screen()
            if screen is None:
                print("[ERROR] 截屏失败")
                continue

            # 模板匹配并点击
            action_performed = self.find_and_click_template(screen)

            if action_performed:
                no_action_count = 0
            else:
                no_action_count += 1
                if no_action_count % 5 == 0:
                    print(f"无操作计数: {no_action_count}/{MAX_NO_ACTION_COUNT}")

            time.sleep(LOOP_INTERVAL)

        print(f"\n[DONE] 完成，连续 {MAX_NO_ACTION_COUNT} 次无操作，程序退出")


def main():
    auto = LunaMusicAuto()
    auto.run()


if __name__ == "__main__":
    main()
