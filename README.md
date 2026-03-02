# 汽水音乐免费畅听自动看广告工具

程序使用 claude-code 配合 GLM4.7 编写,并作细节修改。

## 功能描述
通过ADB命令截取Android设备屏幕，在截取的图片中匹配预定义的模板图片列表。如果匹配到任何一个模板图片，则计算该图片的中心位置，并使用ADB命令发送点击事件。每间隔n秒自动执行一次。

## 环境要求
- Python 3.6+
- OpenCV
- ADB工具

## 安装依赖
```bash
pip install -r requirements.txt
```

## 在termux中运行

没有 opencv 安装:

pkg install x11-repo

pkg install opencv-python


## 使用方法

### 1. 确认手机型号

```bash
adb shell getprop ro.product.model
```

例如 mate 50 手机: CET-AL00

### 2. 获取模板图片

如果没有对应的手机型号，需要截屏, 并裁剪需要模式匹配的位置, 保存到对应的手机型号下

```bash
# 截取整个屏幕
adb exec-out screencap -p > screenshot.png

# 使用图片编辑工具裁剪出需要匹配的区域
# 将裁剪后的图片保存到 images/ 目录下
```


## 配置说明
- 检测间隔: 默认5秒，可在代码中修改
- 匹配阈值: 默认0.8（80%相似度），可在代码中调整
- 模板图片目录: `images/`
- 临时文件目录: `temp/`

## 注意事项
1. 确保设备已通过USB连接并启用USB调试
2. 确保ADB设备识别正常 (`adb devices`)
3. 模板图片质量影响匹配精度，建议使用清晰的截图
4. 程序运行中按 Ctrl+C 停止

