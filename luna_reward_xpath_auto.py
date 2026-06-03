#!/usr/bin/env python3
"""
通过 ADB 导出 uiautomator XML，并按 XPath 风格路径检测/领取汽水音乐奖励。
"""

import argparse
import json
import os
import re
import subprocess
import sys
import time
import xml.etree.ElementTree as ET
import uiautomator2 as u2

DEFAULT_CONFIG_PATH = "luna_reward_xpaths.json"
BOUNDS_PATTERN = re.compile(r"\[(\d+),(\d+)\]\[(\d+),(\d+)\]")
FIRST_XPATH_STEP_PATTERN = re.compile(
    r"""^//\*\[@(?P<name>[^=\]]+)=(?P<quote>['"])(?P<value>.*?)(?P=quote)\]$"""
)
CLASS_STEP_PATTERN = re.compile(r"^(?P<class_name>[\w.]+)(?:\[(?P<index>\d+)\])?$")


def load_xpath_config(config_path):
    """加载 XPath 配置。"""
    with open(config_path, "r", encoding="utf-8") as file:
        config = json.load(file)

    reward_status_xpaths = config.get("reward_status_xpaths")
    continue_reward_xpath = config.get("continue_reward_xpath")

    if not isinstance(reward_status_xpaths, list) or not reward_status_xpaths:
        raise ValueError("配置项 reward_status_xpaths 必须是非空字符串数组。")
    if not all(isinstance(xpath, str) and xpath.strip() for xpath in reward_status_xpaths):
        raise ValueError("配置项 reward_status_xpaths 中的每一项都必须是非空字符串。")
    if not isinstance(continue_reward_xpath, str) or not continue_reward_xpath.strip():
        raise ValueError("配置项 continue_reward_xpath 必须是非空字符串。")

    return {
        "reward_status_xpaths": reward_status_xpaths,
        "continue_reward_xpath": continue_reward_xpath,
    }


def run_adb_command(args, timeout=10):
    """运行 adb 命令。"""
    return subprocess.run(
        ["adb", *args],
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )


def ensure_adb_ready():
    """确认 ADB 可用且至少连接了一台设备。"""
    version = run_adb_command(["version"], timeout=5)
    if version.returncode != 0:
        raise RuntimeError("ADB 不可用，请确认 adb 已安装并加入 PATH。")

    devices = run_adb_command(["devices"], timeout=5)
    if devices.returncode != 0:
        raise RuntimeError("执行 adb devices 失败。")

    for line in devices.stdout.splitlines()[1:]:
        if "\tdevice" in line:
            device_id = line.split("\t", 1)[0].strip()
            print(f"[OK] 已连接设备: {device_id}")
            return device_id

    raise RuntimeError("未检测到已连接且可用的 Android 设备。")


def connect_uiautomator2(serial):
    """连接 uiautomator2 设备。"""
    if u2 is None:
        raise RuntimeError("缺少依赖 uiautomator2，请先安装 uiviewer 或 uiautomator2。")
    return u2.connect(serial)


def dump_ui_xml(device, local_path):
    """通过 uiautomator2 导出当前界面的 XML 到本地。"""
    content = device.dump_hierarchy()
    if not content:
        raise RuntimeError("uiautomator2 dump_hierarchy 返回空内容。")

    with open(local_path, "w", encoding="utf-8") as file:
        file.write(content)


def parse_bounds(bounds_text):
    """将 [x1,y1][x2,y2] 解析为坐标和尺寸。"""
    if not bounds_text:
        return None

    match = BOUNDS_PATTERN.fullmatch(bounds_text.strip())
    if not match:
        return None

    x1, y1, x2, y2 = map(int, match.groups())
    width = x2 - x1
    height = y2 - y1
    if width <= 0 or height <= 0:
        return None

    return x1, y1, x2, y2, width, height


def split_xpath(xpath):
    """拆分本脚本支持的 XPath 子集，保留开头的 //*[@attr="value"]。"""
    xpath = xpath.strip()
    if not xpath.startswith("//*[@"):
        raise ValueError(f"不支持的 XPath 起始格式: {xpath}")

    close_index = xpath.find("]")
    if close_index == -1:
        raise ValueError(f"XPath 属性条件未闭合: {xpath}")

    first_step = xpath[: close_index + 1]
    rest = xpath[close_index + 1 :].strip("/")
    return [first_step, *[part for part in rest.split("/") if part]]


def find_nodes_by_xpath(root, xpath):
    """
    在 uiautomator XML 中按 Appium 风格 XPath 查找节点。

    uiautomator XML 的节点标签通常都是 node，真实控件类型在 class 属性中；
    因此这里把 /android.widget.FrameLayout[1] 映射为 class 属性匹配。
    """
    steps = split_xpath(xpath)
    first_match = FIRST_XPATH_STEP_PATTERN.fullmatch(steps[0])
    if not first_match:
        raise ValueError(f"不支持的 XPath 属性条件: {steps[0]}")

    attr_name = first_match.group("name")
    attr_value = first_match.group("value")
    current_nodes = [
        node for node in root.iter("node") if node.attrib.get(attr_name) == attr_value
    ]

    for step in steps[1:]:
        class_match = CLASS_STEP_PATTERN.fullmatch(step)
        if not class_match:
            raise ValueError(f"不支持的 XPath 层级片段: {step}")

        class_name = class_match.group("class_name")
        index = int(class_match.group("index") or "0")
        next_nodes = []

        for node in current_nodes:
            matched_children = [
                child for child in list(node) if child.attrib.get("class") == class_name
            ]
            if index:
                if len(matched_children) >= index:
                    next_nodes.append(matched_children[index - 1])
            else:
                next_nodes.extend(matched_children)

        current_nodes = next_nodes
        if not current_nodes:
            break

    return current_nodes


def find_first_node(xml_path, xpath):
    """从 XML 文件中查找第一个匹配节点。"""
    tree = ET.parse(xml_path)
    nodes = find_nodes_by_xpath(tree.getroot(), xpath)
    return nodes[0] if nodes else None


def find_first_node_by_xpaths(xml_path, xpaths):
    """从 XML 文件中按候选 XPath 顺序查找第一个匹配节点。"""
    tree = ET.parse(xml_path)
    root = tree.getroot()
    for xpath in xpaths:
        nodes = find_nodes_by_xpath(root, xpath)
        if nodes:
            return nodes[0], xpath
    return None, None


def get_reward_status(xml_path, reward_status_xpaths):
    """根据奖励状态元素的宽高比例判断 available/unavailable/missing。"""
    node, matched_xpath = find_first_node_by_xpaths(xml_path, reward_status_xpaths)
    if node is None:
        return "missing", None, None

    bounds = parse_bounds(node.attrib.get("bounds"))
    if bounds is None:
        return "missing", node, matched_xpath

    y = bounds[1]
    width = bounds[4]
    height = bounds[5]
    if width < height * 4 and y == height:
        return "available", node, matched_xpath

    return "unavailable", node, matched_xpath


def get_continue_reward_click_point(node):
    """返回继续领取奖励元素内部横向 50%、纵向 75% 的点击坐标。"""
    bounds = parse_bounds(node.attrib.get("bounds"))
    if bounds is None:
        return None

    x1, y1, _x2, _y2, width, height = bounds
    x = x1 + int(width * 0.5)
    y = y1 + int(height * 0.75)
    return x, y


def get_click_point_at_center(node):
    """返回元素中心点坐标。"""
    bounds = parse_bounds(node.attrib.get("bounds"))
    if bounds is None:
        return None

    x1, y1, _x2, _y2, width, height = bounds
    x = x1 + width // 2
    y = y1 + height // 2
    return x, y


def tap(x, y):
    """点击屏幕坐标。"""
    result = run_adb_command(["shell", "input", "tap", str(x), str(y)], timeout=5)
    if result.returncode != 0:
        raise RuntimeError(f"点击失败: {result.stderr.strip()}")


class LunaRewardXPathAuto:
    def __init__(
        self,
        device,
        xml_path,
        interval,
        reward_status_click_interval,
        reward_status_xpaths,
        continue_reward_xpath,
    ):
        self.device = device
        self.xml_path = xml_path
        self.interval = interval
        self.reward_status_click_interval = reward_status_click_interval
        self.reward_status_xpaths = reward_status_xpaths
        self.continue_reward_xpath = continue_reward_xpath
        self.last_reward_status_click_time = None
        self.reward_status = "unknown"

    def reset_status(self):
        self.reward_status = "unknown"

    def run_once(self):
        dump_ui_xml(self.device, self.xml_path)

        status, status_node, matched_xpath = get_reward_status(
            self.xml_path,
            self.reward_status_xpaths,
        )
        self.reward_status = status

        if status_node is None:
            print("[STATUS] 奖励状态元素不存在")
            return

        bounds = parse_bounds(status_node.attrib.get("bounds"))
        if bounds:
            print(
                f"[STATUS] 奖励状态: {status}, "
                f"y={bounds[1]}, width={bounds[4]}, height={bounds[5]}"
            )
        else:
            print(f"[STATUS] 奖励状态: {status}, bounds 无效")

        if status != "available":
            return

        continue_node = find_first_node(self.xml_path, self.continue_reward_xpath)
        if continue_node is None:
            now = time.monotonic()
            if self.last_reward_status_click_time is not None:
                elapsed = now - self.last_reward_status_click_time
                if elapsed < self.reward_status_click_interval:
                    wait_seconds = self.reward_status_click_interval - elapsed
                    print(
                        "[ACTION] 继续领取奖励元素不存在，"
                        f"奖励状态元素点击冷却中: {wait_seconds:.1f}s"
                    )
                    self.reset_status()
                    return

            point = get_click_point_at_center(status_node)
            if point is None:
                print("[ACTION] 继续领取奖励元素不存在，奖励状态元素 bounds 无效")
                self.reset_status()
                return

            x, y = point
            tap(x, y)
            self.last_reward_status_click_time = now
            print(f"[ACTION] 继续领取奖励元素不存在，点击奖励状态元素中心: ({x}, {y})")
            self.reset_status()
            return

        point = get_continue_reward_click_point(continue_node)
        if point is None:
            print("[ACTION] 继续领取奖励元素 bounds 无效")
            self.reset_status()
            return

        x, y = point
        tap(x, y)
        print(f"[ACTION] 点击继续领取奖励: ({x}, {y})")
        self.reset_status()

    def run(self):
        print("开始通过 XPath 检测汽水音乐奖励状态，按 Ctrl+C 停止。")
        while True:
            try:
                self.run_once()
            except Exception as exc:
                print(f"[ERROR] {exc}")
            time.sleep(self.interval)


def main():
    parser = argparse.ArgumentParser(
        description="通过 adb 导出 XML，用 XPath 风格路径检测并领取汽水音乐奖励。"
    )
    parser.add_argument(
        "--config",
        default=DEFAULT_CONFIG_PATH,
        help=f"XPath 配置 JSON 路径，默认是 {DEFAULT_CONFIG_PATH}",
    )
    parser.add_argument(
        "--xml-path",
        default=os.path.join(".tmp", "luna_reward_ui.xml"),
        help="本地临时 XML 路径，默认是 .tmp/luna_reward_ui.xml",
    )
    parser.add_argument(
        "--interval",
        type=float,
        default=2.0,
        help="循环间隔秒数，默认 2 秒",
    )
    parser.add_argument(
        "--reward-status-click-interval",
        type=float,
        default=10.0,
        help="点击奖励状态元素的最小间隔秒数，默认 10 秒",
    )
    args = parser.parse_args()

    os.makedirs(os.path.dirname(args.xml_path) or ".", exist_ok=True)

    try:
        xpath_config = load_xpath_config(args.config)
        serial = ensure_adb_ready()
        device = connect_uiautomator2(serial)
        LunaRewardXPathAuto(
            device,
            args.xml_path,
            args.interval,
            args.reward_status_click_interval,
            xpath_config["reward_status_xpaths"],
            xpath_config["continue_reward_xpath"],
        ).run()
    except KeyboardInterrupt:
        print("\n已停止。")
    except Exception as exc:
        print(f"[ERROR] {exc}")
        sys.exit(1)


if __name__ == "__main__":
    main()
