import os
import time
import copy
import torch
import shutil
import json
from PIL import Image, ImageDraw

from MobileAgent.api import inference_chat
from MobileAgent.text_localization import ocr
from MobileAgent.icon_localization import det
from MobileAgent.controller import get_screenshot, tap, slide, type, back, home
from MobileAgent.prompt import get_action_prompt, get_reflect_prompt, get_memory_prompt, get_process_prompt
from MobileAgent.chat import init_action_chat, init_reflect_chat, init_memory_chat, add_response, add_response_two_image

from modelscope.pipelines import pipeline
from modelscope.utils.constant import Tasks
from modelscope import snapshot_download, AutoModelForCausalLM, AutoTokenizer, GenerationConfig

from dashscope import MultiModalConversation
import dashscope
import concurrent

####################################### Edit your Setting #########################################
# Your ADB path
adb_path = "D:/安卓逆向工具/adb/platform-tools/adb.exe"

# Your instruction
instruction = "打开浏览器，搜索最近新闻，然后显示一下内容"

# Your GPT-4o API URL
API_url = "https://api.openai.com/v1/chat/completions"

# Your GPT-4o API Token
token = ""

# Choose between "api" and "local". api: use the qwen api. local: use the local qwen checkpoint
caption_call_method = "api"

# Choose between "qwen-vl-plus" and "qwen-vl-max" if use api method. Choose between "qwen-vl-chat" and "qwen-vl-chat-int4" if use local method.
caption_model = "qwen-vl-plus"

# If you choose the api caption call method, input your Qwen api here
qwen_api = ""

# You can add operational knowledge to help Agent operate more accurately.
add_info = "If you want to tap an icon of an app, use the action \"Open app\". If you want to exit an app, use the action \"Home\""

# Reflection Setting: If you want to improve the operating speed, you can disable the reflection agent. This may reduce the success rate.
reflection_switch = True

# Memory Setting: If you want to improve the operating speed, you can disable the memory unit. This may reduce the success rate.
memory_switch = True

# Record operations for replay
record_operations = False  # 设置为True启用操作记录
operations_log_file = "operations_log.json"  # 操作记录文件名
replay_mode = True  # 设置为True启用重放模式
###################################################################################################


def get_all_files_in_folder(folder_path):
    file_list = []
    for file_name in os.listdir(folder_path):
        file_list.append(file_name)
    return file_list


def draw_coordinates_on_image(image_path, coordinates):
    image = Image.open(image_path) #打开图片
    draw = ImageDraw.Draw(image)  #进行画图
    point_size = 10
    for coord in coordinates:
        draw.ellipse((coord[0] - point_size, coord[1] - point_size, coord[0] + point_size, coord[1] + point_size), fill='red')
    output_image_path = './screenshot/output_image.png'
    image.save(output_image_path)  #保存图片
    return output_image_path


def crop(image, box, i): #于裁剪图像的指定区域
    image = Image.open(image) 
    x1, y1, x2, y2 = int(box[0]), int(box[1]), int(box[2]), int(box[3])  #这行代码把裁剪框的四个数字（左上角和右下角的坐标）转换成整数，确保它们可以用来裁剪图像。
    if x1 >= x2-10 or y1 >= y2-10:
        return
    cropped_image = image.crop((x1, y1, x2, y2))
    cropped_image.save(f"./temp/{i}.jpg")


def generate_local(tokenizer, model, image_file, query):
    query = tokenizer.from_list_format([
        {'image': image_file},
        {'text': query},
    ])
    response, _ = model.chat(tokenizer, query=query, history=None)
    return response


def process_image(image, query):
    dashscope.api_key = qwen_api
    image = "file://" + image
    messages = [{
        'role': 'user',
        'content': [
            {
                'image': image
            },
            {
                'text': query
            },
        ]
    }]
    response = MultiModalConversation.call(model=caption_model, messages=messages)
    
    try:
        response = response['output']['choices'][0]['message']['content'][0]["text"]
    except:
        response = "This is an icon."
    
    return response


def generate_api(images, query):
    icon_map = {}
    with concurrent.futures.ThreadPoolExecutor() as executor:
        futures = {executor.submit(process_image, image, query): i for i, image in enumerate(images)}
        
        for future in concurrent.futures.as_completed(futures):
            i = futures[future]
            response = future.result()
            icon_map[i + 1] = response
    
    return icon_map


def merge_text_blocks(text_list, coordinates_list):
    merged_text_blocks = []
    merged_coordinates = []

    sorted_indices = sorted(range(len(coordinates_list)), key=lambda k: (coordinates_list[k][1], coordinates_list[k][0]))
    sorted_text_list = [text_list[i] for i in sorted_indices]
    sorted_coordinates_list = [coordinates_list[i] for i in sorted_indices]

    num_blocks = len(sorted_text_list)
    merge = [False] * num_blocks

    for i in range(num_blocks):
        if merge[i]:
            continue
        
        anchor = i
        
        group_text = [sorted_text_list[anchor]]
        group_coordinates = [sorted_coordinates_list[anchor]]

        for j in range(i+1, num_blocks):
            if merge[j]:
                continue

            if abs(sorted_coordinates_list[anchor][0] - sorted_coordinates_list[j][0]) < 10 and \
            sorted_coordinates_list[j][1] - sorted_coordinates_list[anchor][3] >= -10 and sorted_coordinates_list[j][1] - sorted_coordinates_list[anchor][3] < 30 and \
            abs(sorted_coordinates_list[anchor][3] - sorted_coordinates_list[anchor][1] - (sorted_coordinates_list[j][3] - sorted_coordinates_list[j][1])) < 10:
                group_text.append(sorted_text_list[j])
                group_coordinates.append(sorted_coordinates_list[j])
                merge[anchor] = True
                anchor = j
                merge[anchor] = True

        merged_text = "\n".join(group_text)
        min_x1 = min(group_coordinates, key=lambda x: x[0])[0]
        min_y1 = min(group_coordinates, key=lambda x: x[1])[1]
        max_x2 = max(group_coordinates, key=lambda x: x[2])[2]
        max_y2 = max(group_coordinates, key=lambda x: x[3])[3]

        merged_text_blocks.append(merged_text)
        merged_coordinates.append([min_x1, min_y1, max_x2, max_y2])

    return merged_text_blocks, merged_coordinates


def get_perception_infos(adb_path, screenshot_file):  #提取并处理感知信息
    get_screenshot(adb_path)  # 获取手机屏幕截图
    
    width, height = Image.open(screenshot_file).size  # 获取截图的宽度和高度
    
    text, coordinates = ocr(screenshot_file, ocr_detection, ocr_recognition)  # 使用OCR识别截图中的文本和坐标
    text, coordinates = merge_text_blocks(text, coordinates)  # 合并相邻的文本块
    
    center_list = [[(coordinate[0]+coordinate[2])/2, (coordinate[1]+coordinate[3])/2] for coordinate in coordinates]  # 计算每个文本块的中心点坐标
    draw_coordinates_on_image(screenshot_file, center_list)  # 在截图上标记中心点
    
    perception_infos = []  # 初始化感知信息列表
    for i in range(len(coordinates)):  # 遍历所有文本块
        perception_info = {"text": "text: " + text[i], "coordinates": coordinates[i]}  # 创建包含文本和坐标的字典
        perception_infos.append(perception_info)  # 将字典添加到感知信息列表
        
    coordinates = det(screenshot_file, "icon", groundingdino_model)  # 使用GroundingDINO检测图标位置
    
    for i in range(len(coordinates)):  # 遍历所有检测到的图标
        perception_info = {"text": "icon", "coordinates": coordinates[i]}  # 创建包含图标标记和坐标的字典
        perception_infos.append(perception_info)  # 将字典添加到感知信息列表
        
    image_box = []  # 初始化图标边界框列表
    image_id = []  # 初始化图标ID列表
    for i in range(len(perception_infos)):  # 遍历所有感知信息
        if perception_infos[i]['text'] == 'icon':  # 如果是图标
            image_box.append(perception_infos[i]['coordinates'])  # 添加边界框
            image_id.append(i)  # 添加ID

    for i in range(len(image_box)):  # 遍历所有图标边界框
        crop(screenshot_file, image_box[i], image_id[i])  # 裁剪图标图像

    images = get_all_files_in_folder(temp_file)  # 获取临时文件夹中的所有图像
    if len(images) > 0:  # 如果有图像
        images = sorted(images, key=lambda x: int(x.split('/')[-1].split('.')[0]))  # 按文件名排序图像
        image_id = [int(image.split('/')[-1].split('.')[0]) for image in images]  # 获取图像ID列表
        icon_map = {}  # 初始化图标描述映射
        prompt = 'This image is an icon from a phone screen. Please briefly describe the shape and color of this icon in one sentence.'  # 设置提示语
        if caption_call_method == "local":  # 如果使用本地模型生成描述
            for i in range(len(images)):  # 遍历所有图像
                image_path = os.path.join(temp_file, images[i])  # 获取图像路径
                icon_width, icon_height = Image.open(image_path).size  # 获取图标尺寸
                if icon_height > 0.8 * height or icon_width * icon_height > 0.2 * width * height:  # 如果图标太大
                    des = "None"  # 设置为None
                else:
                    des = generate_local(tokenizer, model, image_path, prompt)  # 使用本地模型生成描述
                icon_map[i+1] = des  # 添加到映射
        else:  # 如果使用API生成描述
            for i in range(len(images)):  # 遍历所有图像
                images[i] = os.path.join(temp_file, images[i])  # 获取完整路径
            icon_map = generate_api(images, prompt)  # 使用API生成描述
        for i, j in zip(image_id, range(1, len(image_id)+1)):  # 遍历图标ID和索引
            if icon_map.get(j):  # 如果有描述
                perception_infos[i]['text'] = "icon: " + icon_map[j]  # 更新感知信息中的文本

    for i in range(len(perception_infos)):  # 遍历所有感知信息
        perception_infos[i]['coordinates'] = [int((perception_infos[i]['coordinates'][0]+perception_infos[i]['coordinates'][2])/2), int((perception_infos[i]['coordinates'][1]+perception_infos[i]['coordinates'][3])/2)]  # 计算中心点坐标
        
    return perception_infos, width, height  # 返回感知信息、宽度和高度

### Load caption model ###================================================================================
device = "cuda"  # 设置设备为CUDA
torch.manual_seed(1234)  # 设置随机种子以确保结果可重复
if caption_call_method == "local":  # 如果使用本地模型生成描述
    if caption_model == "qwen-vl-chat":  # 如果使用qwen-vl-chat模型
        model_dir = snapshot_download('qwen/Qwen-VL-Chat', revision='v1.1.0')  # 下载qwen-vl-chat模型
        model = AutoModelForCausalLM.from_pretrained(model_dir, device_map=device, trust_remote_code=True).eval()  # 加载模型并设置为评估模式
        model.generation_config = GenerationConfig.from_pretrained(model_dir, trust_remote_code=True)  # 加载生成配置
    elif caption_model == "qwen-vl-chat-int4":  # 如果使用qwen-vl-chat-int4模型
        qwen_dir = snapshot_download("qwen/Qwen-VL-Chat-Int4", revision='v1.0.0')  # 下载qwen-vl-chat-int4模型
        model = AutoModelForCausalLM.from_pretrained(qwen_dir, device_map=device, trust_remote_code=True,use_safetensors=True).eval()  # 加载int4量化模型
        model.generation_config = GenerationConfig.from_pretrained(qwen_dir, trust_remote_code=True, do_sample=False)  # 加载生成配置
    else:  # 如果选择了其他模型
        print("If you choose local caption method, you must choose the caption model from \"Qwen-vl-chat\" and \"Qwen-vl-chat-int4\"")  # 打印错误信息
        exit(0)  # 退出程序
    tokenizer = AutoTokenizer.from_pretrained(qwen_dir, trust_remote_code=True)  # 加载分词器
elif caption_call_method == "api":  # 如果使用API生成描述
    pass  # 不需要加载模型
else:  # 如果选择了其他方法
    print("You must choose the caption model call function from \"local\" and \"api\"")  # 打印错误信息
    exit(0)  # 退出程序


### 加载OCR和图标检测模型 ###==========================================================
# 下载并加载GroundingDINO模型用于目标检测
groundingdino_dir = snapshot_download('AI-ModelScope/GroundingDINO', revision='v1.0.0')
groundingdino_model = pipeline('grounding-dino-task', model=groundingdino_dir)
# 加载OCR检测模型
ocr_detection = pipeline(Tasks.ocr_detection, model='damo/cv_resnet18_ocr-detection-line-level_damo')
# 加载OCR识别模型
ocr_recognition = pipeline(Tasks.ocr_recognition, model='damo/cv_convnextTiny_ocr-recognition-document_damo')

# 初始化历史记录列表
thought_history = []  # 思考历史
summary_history = []  # 总结历史
action_history = []  # 动作历史
summary = ""  # 当前总结
action = ""  # 当前动作
completed_requirements = ""  # 已完成的需求
memory = ""  # 记忆内容
insight = ""  # 洞察内容

# 创建临时文件夹
temp_file = "temp"
screenshot = "screenshot"
if not os.path.exists(temp_file):
    os.mkdir(temp_file)
else:
    shutil.rmtree(temp_file)
    os.mkdir(temp_file)
if not os.path.exists(screenshot):
    os.mkdir(screenshot)
error_flag = False  # 错误标志

# 用于记录操作的函数
def log_operation(action_type, params=None):
    """记录操作到日志文件"""
    if not record_operations:
        return
        
    timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
    operation = {
        "timestamp": timestamp,
        "action_type": action_type,
        "params": params
    }
    
    # 检查文件是否存在
    if os.path.exists(operations_log_file):
        # 读取现有操作记录
        try:
            with open(operations_log_file, 'r') as f:
                operations = json.load(f)
        except json.JSONDecodeError:
            operations = []
    else:
        operations = []
    
    # 添加新操作并保存
    operations.append(operation)
    with open(operations_log_file, 'w') as f:
        json.dump(operations, f, indent=2)
    
    print(f"已记录操作: {action_type} {params}")

# 用于重放操作的函数
def replay_operations():
    """从日志文件重放操作"""
    if not os.path.exists(operations_log_file):
        print(f"操作日志文件 {operations_log_file} 不存在!")
        return False
    
    print(f"开始重放操作记录...")
    try:
        with open(operations_log_file, 'r') as f:
            operations = json.load(f)
    except json.JSONDecodeError:
        print("操作日志文件格式错误!")
        return False
    
    for op in operations:
        action_type = op["action_type"]
        params = op["params"]
        print(f"重放操作: {action_type} {params}")
        
        if action_type == "Tap":
            x, y = params["x"], params["y"]
            tap(adb_path, x, y)
        elif action_type == "Swipe":
            x1, y1 = params["start_x"], params["start_y"]
            x2, y2 = params["end_x"], params["end_y"]
            slide(adb_path, x1, y1, x2, y2)
        elif action_type == "Type":
            text = params["text"]
            type(adb_path, text)
        elif action_type == "Back":
            back(adb_path)
        elif action_type == "Home":
            home(adb_path)
        elif action_type == "Open app":
            # 由于无法直接使用之前的应用位置,我们使用OCR重新查找应用
            app_name = params["app_name"]
            get_screenshot(adb_path)
            text, coordinate = ocr("./screenshot/screenshot.jpg", ocr_detection, ocr_recognition)
            for ti in range(len(text)):
                if app_name == text[ti]:
                    name_coordinate = [int((coordinate[ti][0] + coordinate[ti][2])/2), 
                                      int((coordinate[ti][1] + coordinate[ti][3])/2)]
                    tap(adb_path, name_coordinate[0], name_coordinate[1]- int(coordinate[ti][3] - coordinate[ti][1]))
                    # 记录操作
                    log_operation("Open app", {
                        "app_name": app_name,
                        "x": name_coordinate[0],
                        "y": name_coordinate[1]- int(coordinate[ti][3] - coordinate[ti][1]),
                        "wait_time": 5
                    })
                    break
        
        # 等待操作完成
        time.sleep(params.get("wait_time", 5))
    
    print("操作重放完成!")
    return True

# 主循环
iter = 0
if replay_mode:
    # 重放模式,直接执行记录的操作
    replay_operations()
else:
    # 正常的AI控制模式
    while True:
        iter += 1
        if iter == 1:  # 第一次迭代
            screenshot_file = "./screenshot/screenshot.jpg"
            # 获取感知信息
            perception_infos, width, height = get_perception_infos(adb_path, screenshot_file)
            shutil.rmtree(temp_file)
            os.mkdir(temp_file)
            
            # 检测键盘状态
            keyboard = False
            keyboard_height_limit = 0.9 * height
            for perception_info in perception_infos:
                if perception_info['coordinates'][1] < keyboard_height_limit:
                    continue
                if 'ADB Keyboard' in perception_info['text']:
                    keyboard = True
                    break

        # 生成动作提示并获取响应
        prompt_action = get_action_prompt(instruction, perception_infos, width, height, keyboard, summary_history, action_history, summary, action, add_info, error_flag, completed_requirements, memory)
        chat_action = init_action_chat()
        chat_action = add_response("user", prompt_action, chat_action, screenshot_file)

        # 获取模型输出并解析
        output_action = inference_chat(chat_action, 'gpt-4o', API_url, token)
        thought = output_action.split("### Thought ###")[-1].split("### Action ###")[0].replace("\n", " ").replace(":", "").replace("  ", " ").strip()
        summary = output_action.split("### Operation ###")[-1].replace("\n", " ").replace("  ", " ").strip()
        action = output_action.split("### Action ###")[-1].split("### Operation ###")[0].replace("\n", " ").replace("  ", " ").strip()
        chat_action = add_response("assistant", output_action, chat_action)
        # 打印决策信息
        status = "#" * 50 + " 决策 " + "#" * 50
        print(status)
        print(output_action)
        print('#' * len(status))
        
        # 处理记忆相关内容
        if memory_switch:
            prompt_memory = get_memory_prompt(insight)
            chat_action = add_response("user", prompt_memory, chat_action)
            output_memory = inference_chat(chat_action, 'gpt-4o', API_url, token)
            chat_action = add_response("assistant", output_memory, chat_action)
            status = "#" * 50 + " 记忆 " + "#" * 50
            print(status)
            print(output_memory)
            print('#' * len(status))
            output_memory = output_memory.split("### Important content ###")[-1].split("\n\n")[0].strip() + "\n"
            if "None" not in output_memory and output_memory not in memory:
                memory += output_memory
        
        # 执行打开应用操作
        if "Open app" in action:
            app_name = action.split("(")[-1].split(")")[0]
            text, coordinate = ocr(screenshot_file, ocr_detection, ocr_recognition)
            tap_coordinate = [0, 0]
            for ti in range(len(text)):
                if app_name == text[ti]:
                    name_coordinate = [int((coordinate[ti][0] + coordinate[ti][2])/2), int((coordinate[ti][1] + coordinate[ti][3])/2)]
                    tap(adb_path, name_coordinate[0], name_coordinate[1]- int(coordinate[ti][3] - coordinate[ti][1]))
                    # 记录操作
                    log_operation("Open app", {
                        "app_name": app_name,
                        "x": name_coordinate[0],
                        "y": name_coordinate[1]- int(coordinate[ti][3] - coordinate[ti][1]),
                        "wait_time": 5
                    })
                    break
        
        # 执行点击操作
        elif "Tap" in action:
            coordinate = action.split("(")[-1].split(")")[0].split(", ")
            x, y = int(coordinate[0]), int(coordinate[1])
            tap(adb_path, x, y)
            # 记录操作
            log_operation("Tap", {"x": x, "y": y, "wait_time": 5})
        
        # 执行滑动操作
        elif "Swipe" in action:
            coordinate1 = action.split("Swipe (")[-1].split("), (")[0].split(", ")
            coordinate2 = action.split("), (")[-1].split(")")[0].split(", ")
            x1, y1 = int(coordinate1[0]), int(coordinate1[1])
            x2, y2 = int(coordinate2[0]), int(coordinate2[1])
            slide(adb_path, x1, y1, x2, y2)
            # 记录操作
            log_operation("Swipe", {
                "start_x": x1, 
                "start_y": y1, 
                "end_x": x2, 
                "end_y": y2,
                "wait_time": 5
            })
            
        # 执行输入操作
        elif "Type" in action:
            if "(text)" not in action:
                text = action.split("(")[-1].split(")")[0]
            else:
                text = action.split(" \"")[-1].split("\"")[0]
            type(adb_path, text)
            # 记录操作
            log_operation("Type", {"text": text, "wait_time": 5})
        
        # 执行返回操作
        elif "Back" in action:
            back(adb_path)
            # 记录操作
            log_operation("Back", {"wait_time": 5})
        
        # 执行返回主页操作
        elif "Home" in action:
            home(adb_path)
            # 记录操作
            log_operation("Home", {"wait_time": 5})
            
        # 执行停止操作
        elif "Stop" in action:
            # 记录操作
            log_operation("Stop", {"wait_time": 0})
            break
        
        time.sleep(5)  # 等待操作完成
        
        # 保存上一次的状态
        last_perception_infos = copy.deepcopy(perception_infos)
        last_screenshot_file = "./screenshot/last_screenshot.jpg"
        last_keyboard = keyboard
        if os.path.exists(last_screenshot_file):
            os.remove(last_screenshot_file)
        os.rename(screenshot_file, last_screenshot_file)
        
        # 获取新的感知信息
        perception_infos, width, height = get_perception_infos(adb_path, screenshot_file)
        shutil.rmtree(temp_file)
        os.mkdir(temp_file)
        
        # 检测键盘状态
        keyboard = False
        for perception_info in perception_infos:
            if perception_info['coordinates'][1] < keyboard_height_limit:
                continue
            if 'ADB Keyboard' in perception_info['text']:
                keyboard = True
                break
        
        # 反思机制
        if reflection_switch:
            prompt_reflect = get_reflect_prompt(instruction, last_perception_infos, perception_infos, width, height, last_keyboard, keyboard, summary, action, add_info)
            chat_reflect = init_reflect_chat()
            chat_reflect = add_response_two_image("user", prompt_reflect, chat_reflect, [last_screenshot_file, screenshot_file])

            output_reflect = inference_chat(chat_reflect, 'gpt-4o', API_url, token)
            reflect = output_reflect.split("### Answer ###")[-1].replace("\n", " ").strip()
            chat_reflect = add_response("assistant", output_reflect, chat_reflect)
            status = "#" * 50 + " 反思 " + "#" * 50
            print(status)
            print(output_reflect)
            print('#' * len(status))
        
            if 'A' in reflect:  # 操作成功
                thought_history.append(thought)
                summary_history.append(summary)
                action_history.append(action)
                
                prompt_planning = get_process_prompt(instruction, thought_history, summary_history, action_history, completed_requirements, add_info)
                chat_planning = init_memory_chat()
                chat_planning = add_response("user", prompt_planning, chat_planning)
                output_planning = inference_chat(chat_planning, 'gpt-4-turbo', API_url, token)
                chat_planning = add_response("assistant", output_planning, chat_planning)
                status = "#" * 50 + " 规划 " + "#" * 50
                print(status)
                print(output_planning)
                print('#' * len(status))
                completed_requirements = output_planning.split("### Completed contents ###")[-1].replace("\n", " ").strip()
                
                error_flag = False
            
            elif 'B' in reflect:  # 需要返回
                error_flag = True
                back(adb_path)
                
            elif 'C' in reflect:  # 操作失败
                error_flag = True
        
        else:  # 不使用反思机制
            thought_history.append(thought)
            summary_history.append(summary)
            action_history.append(action)
            
            prompt_planning = get_process_prompt(instruction, thought_history, summary_history, action_history, completed_requirements, add_info)
            chat_planning = init_memory_chat()
            chat_planning = add_response("user", prompt_planning, chat_planning)
            output_planning = inference_chat(chat_planning, 'gpt-4-turbo', API_url, token)
            chat_planning = add_response("assistant", output_planning, chat_planning)
            status = "#" * 50 + " 规划 " + "#" * 50
            print(status)
            print(output_planning)
            print('#' * len(status))
            completed_requirements = output_planning.split("### Completed contents ###")[-1].replace("\n", " ").strip()
             
        os.remove(last_screenshot_file)  # 删除上一次的截图
