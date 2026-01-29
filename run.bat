@echo off
echo 安装Python依赖...
pip install -r requirements.txt

echo.
echo 启动ADB截图图片匹配点击工具...
python adb_screenshot_click.py

pause