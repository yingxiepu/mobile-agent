import subprocess
import json
import xml.etree.ElementTree as ET
from datetime import datetime
import os
import re
from PIL import Image

def run_adb_command(adb_path, command):
    """执行 ADB 命令并返回输出结果"""
    try:
        full_command = f"{adb_path} {command}"
        result = subprocess.run(full_command, capture_output=True, text=True, shell=True)
        return result.stdout
    except Exception as e:
        print(f"执行ADB命令时出错: {str(e)}")
        return None

def parse_bounds(bounds_str):
    """解析bounds字符串为坐标值"""
    pattern = r'\[(\d+),(\d+)\]\[(\d+),(\d+)\]'
    match = re.match(pattern, bounds_str)
    if match:
        x1, y1, x2, y2 = map(int, match.groups())
        return x1, y1, x2, y2
    return 0, 0, 0, 0

def get_element_center(bounds_str):
    """获取元素中心点坐标"""
    x1, y1, x2, y2 = parse_bounds(bounds_str)
    return [(x1 + x2) // 2, (y1 + y2) // 2]

def get_element_bounds(bounds_str):
    """获取元素边界坐标"""
    x1, y1, x2, y2 = parse_bounds(bounds_str)
    return [x1, y1, x2, y2]

def get_ui_elements(adb_path, screenshot_path=None):
    """获取当前界面的UI元素信息"""
    # 获取屏幕截图（如果需要，只用于记录，不用于视觉识别）
    if screenshot_path:
        get_screenshot(adb_path, screenshot_path)
    
    # 将当前界面布局保存到临时文件
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"layout_{timestamp}.xml"
    temp_dir = "temp"
    if not os.path.exists(temp_dir):
        os.makedirs(temp_dir)
    
    local_path = os.path.join(temp_dir, filename)
    
    # 使用 ADB 命令获取界面布局
    run_adb_command(adb_path, f"shell uiautomator dump /sdcard/{filename}")
    run_adb_command(adb_path, f"pull /sdcard/{filename} {local_path}")
    
    elements = []
    try:
        # 解析XML文件
        tree = ET.parse(local_path)
        root = tree.getroot()
        
        # 提取屏幕尺寸
        width = int(root.get("width", "0"))
        height = int(root.get("height", "0"))
        
        # 递归函数来处理节点
        def process_node(node, parent_info=""):
            # 获取节点属性
            class_name = node.get("class", "")
            package = node.get("package", "")
            content_desc = node.get("content-desc", "").strip()
            text = node.get("text", "").strip()
            resource_id = node.get("resource-id", "").strip()
            bounds = node.get("bounds", "")
            
            # 构建有意义的描述
            description = text or content_desc
            
            # 如果没有文本和内容描述，尝试使用resource_id
            if not description and resource_id:
                parts = resource_id.split("/")
                if len(parts) > 1:
                    description = parts[1]
            
            # 确定元素类型
            element_type = "text"
            if "Button" in class_name or "button" in resource_id.lower():
                element_type = "button"
            elif "EditText" in class_name or "edit" in resource_id.lower():
                element_type = "input"
            elif "Image" in class_name or "image" in resource_id.lower() or "icon" in resource_id.lower():
                element_type = "icon"
            elif "CheckBox" in class_name:
                element_type = "checkbox"
            
            # 只保存有用的节点（有文本、内容描述或有意义的resource_id）
            if (description or (resource_id and "id/" in resource_id)) and bounds:
                center = get_element_center(bounds)
                coords = get_element_bounds(bounds)
                
                # 构造元素信息
                element = {
                    "type": element_type,
                    "text": description,
                    "package": package,
                    "class": class_name,
                    "resource-id": resource_id,
                    "content-desc": content_desc,
                    "bounds": bounds,
                    "coordinates": coords,
                    "center": center
                }
                
                elements.append(element)
            
            # 递归处理子节点
            for child in node:
                process_node(child, description)
        
        # 从根节点开始处理
        process_node(root)
        
        # 清理临时文件
        run_adb_command(adb_path, f"shell rm /sdcard/{filename}")
        if os.path.exists(local_path):
            os.remove(local_path)
        
        return elements, width, height
        
    except Exception as e:
        print(f"解析布局时出错: {str(e)}")
        if os.path.exists(local_path):
            os.remove(local_path)
        return [], 0, 0

def get_screenshot(adb_path, save_path="./screenshot/screenshot.jpg"):
    """获取屏幕截图并保存（仅用于记录，不用于视觉识别）"""
    screenshot_dir = os.path.dirname(save_path)
    if not os.path.exists(screenshot_dir):
        os.makedirs(screenshot_dir)
        
    png_path = save_path.replace(".jpg", ".png")
    
    # 移除旧的截图
    if os.path.exists(png_path):
        os.remove(png_path)
    
    # 获取新的截图
    run_adb_command(adb_path, "shell rm /sdcard/screenshot.png")
    run_adb_command(adb_path, "shell screencap -p /sdcard/screenshot.png")
    run_adb_command(adb_path, f"pull /sdcard/screenshot.png {png_path}")
    
    # 转换为JPG
    image = Image.open(png_path)
    image.convert("RGB").save(save_path, "JPEG")
    
    # 清理临时PNG
    if os.path.exists(png_path):
        os.remove(png_path)
    
    return save_path

def format_elements_for_llm(elements):
    """格式化元素列表，以便于大语言模型处理"""
    perception_infos = []
    
    for element in elements:
        element_type = element["type"]
        text = element["text"]
        
        # 跳过没有文本的元素
        if not text:
            continue
            
        if element_type == "text":
            perception_info = {"text": f"text: {text}", "coordinates": element["center"]}
        elif element_type == "button":
            perception_info = {"text": f"button: {text}", "coordinates": element["center"]}
        elif element_type == "icon":
            perception_info = {"text": f"icon: {text}", "coordinates": element["center"]}
        elif element_type == "input":
            perception_info = {"text": f"input: {text}", "coordinates": element["center"]}
        elif element_type == "checkbox":
            perception_info = {"text": f"checkbox: {text}", "coordinates": element["center"]}
        else:
            perception_info = {"text": f"{element_type}: {text}", "coordinates": element["center"]}
        
        perception_infos.append(perception_info)
    
    return perception_infos

def detect_keyboard(elements, height):
    """检测键盘是否打开"""
    keyboard_height_limit = 0.6 * height
    
    for element in elements:
        y = element["center"][1]
        if y > keyboard_height_limit and ("keyboard" in element["text"].lower() or "keyboard" in element.get("resource-id", "").lower()):
            return True
    
    return False

def find_app_by_name(elements, app_name):
    """根据应用名称查找应用图标"""
    for element in elements:
        if element["text"].lower() == app_name.lower():
            return element["center"]
    return None 