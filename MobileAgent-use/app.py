import os
import json
import time
import copy
import torch
import shutil
from PIL import Image, ImageDraw
from flask import Flask, render_template, request, jsonify, redirect, url_for, flash
from threading import Thread

from MobileAgent.api import inference_chat
from MobileAgent.controller import get_screenshot, tap, slide, type, back, home
from MobileAgent.prompt import get_action_prompt, get_reflect_prompt, get_memory_prompt, get_process_prompt
from MobileAgent.chat import init_action_chat, init_reflect_chat, init_memory_chat, add_response, add_response_two_image
from MobileAgent.layout_parser import get_ui_elements, format_elements_for_llm, detect_keyboard, find_app_by_name

# 仍然需要ModelScope库用于GPT相关功能
from modelscope import AutoModelForCausalLM, AutoTokenizer, GenerationConfig

from dashscope import MultiModalConversation
import dashscope
import concurrent

# 应用配置
app = Flask(__name__)
app.secret_key = 'mobile_agent_secret_key'

# 全局变量
model = None
tokenizer = None
qwen_api = None
caption_model = None
caption_call_method = None

# 默认配置
DEFAULT_CONFIG = {
    "adb_path": "D:/安卓逆向工具/adb/platform-tools/adb.exe",
    "instruction": "打开浏览器，搜索最近新闻，然后显示一下内容",
    "API_url": "https://api.openai.com/v1/chat/completions",
    "token": "",
    "caption_call_method": "api",
    "caption_model": "qwen-vl-plus",
    "add_info": "If you want to tap an icon of an app, use the action \"Open app\". If you want to exit an app, use the action \"Home\"",
    "reflection_switch": True,
    "memory_switch": True,
    "record_operations": True,
    "operations_log_file": "operations_log.json",
    "replay_mode": False
}

# 配置文件路径
CONFIG_FILE = 'config.json'
OPERATIONS_DIR = 'operation_logs'
TEMP_DIR = "temp"
SCREENSHOT_DIR = "screenshot"

# 确保必要的目录存在
for dir_path in [OPERATIONS_DIR, TEMP_DIR, SCREENSHOT_DIR]:
    if not os.path.exists(dir_path):
        os.makedirs(dir_path)
    elif dir_path == TEMP_DIR:
        shutil.rmtree(dir_path)
        os.mkdir(dir_path)

# 加载配置
def load_config():
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            print(f"加载配置文件错误: {e}")
            return DEFAULT_CONFIG
    else:
        # 如果配置文件不存在，创建默认配置
        save_config(DEFAULT_CONFIG)
        return DEFAULT_CONFIG

# 保存配置
def save_config(config):
    with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
        json.dump(config, f, indent=2, ensure_ascii=False)

# 获取所有操作日志文件
def get_operation_logs():
    logs = []
    try:
        # 获取主目录中的操作日志
        if os.path.exists('operations_log.json'):
            logs.append({
                'name': 'operations_log.json',
                'path': 'operations_log.json',
                'modified': time.ctime(os.path.getmtime('operations_log.json')),
                'size': f"{os.path.getsize('operations_log.json') / 1024:.2f} KB"
            })
        
        # 获取操作日志目录中的日志
        for file in os.listdir(OPERATIONS_DIR):
            if file.endswith('.json'):
                file_path = os.path.join(OPERATIONS_DIR, file)
                logs.append({
                    'name': file,
                    'path': file_path,
                    'modified': time.ctime(os.path.getmtime(file_path)),
                    'size': f"{os.path.getsize(file_path) / 1024:.2f} KB"
                })
    except Exception as e:
        print(f"获取操作日志错误: {e}")
    
    return logs

# 运行状态跟踪
run_status = {
    'is_running': False,
    'mode': None,
    'output': [],
    'process': None,
    'thought_history': [],
    'summary_history': [],
    'action_history': [],
    'summary': "",
    'action': "",
    'completed_requirements': "",
    'memory': "",
    'insight': ""
}

# 主页
@app.route('/')
def index():
    config = load_config()
    logs = get_operation_logs()
    return render_template('index.html', config=config, logs=logs, run_status=run_status)

# 配置页面
@app.route('/config', methods=['GET', 'POST'])
def config_page():
    if request.method == 'POST':
        config = {
            "adb_path": request.form.get('adb_path'),
            "instruction": request.form.get('instruction'),
            "API_url": request.form.get('API_url'),
            "token": request.form.get('token'),
            "caption_call_method": request.form.get('caption_call_method'),
            "caption_model": request.form.get('caption_model'),
            "qwen_api": request.form.get('qwen_api'),
            "add_info": request.form.get('add_info'),
            "reflection_switch": request.form.get('reflection_switch') == 'on',
            "memory_switch": request.form.get('memory_switch') == 'on',
            "record_operations": request.form.get('record_operations') == 'on',
            "operations_log_file": request.form.get('operations_log_file'),
            "replay_mode": request.form.get('replay_mode') == 'on'
        }
        save_config(config)
        flash('配置已保存', 'success')
        return redirect(url_for('index'))
    
    config = load_config()
    return render_template('config.html', config=config)

# 查看操作日志
@app.route('/view_log/<path:log_path>')
def view_log(log_path):
    try:
        if log_path == 'operations_log.json':
            file_path = log_path
        else:
            file_path = os.path.join(OPERATIONS_DIR, os.path.basename(log_path))
        
        if os.path.exists(file_path):
            with open(file_path, 'r', encoding='utf-8') as f:
                log_data = json.load(f)
            return render_template('view_log.html', log_data=log_data, log_name=os.path.basename(file_path))
        else:
            flash('日志文件不存在', 'error')
            return redirect(url_for('index'))
    except Exception as e:
        flash(f'读取日志文件错误: {e}', 'error')
        return redirect(url_for('index'))

# 运行MobileAgent
def execute_mobile_agent(config):
    global run_status
    screenshot_file = "./screenshot/screenshot.jpg"
    error_flag = False
    iter = 0
    
    try:
        while True:
            iter += 1
            if iter == 1:
                perception_infos, width, height = get_perception_infos(config['adb_path'], screenshot_file, config)
                shutil.rmtree(TEMP_DIR)
                os.mkdir(TEMP_DIR)
                
                # 使用布局解析器检测键盘状态
                elements, _, keyboard_height = get_ui_elements(config['adb_path'])
                keyboard = False
                keyboard_height_limit = 0.6 * keyboard_height
                
                for element in elements:
                    y = element["center"][1]
                    if y > keyboard_height_limit and ("keyboard" in element["text"].lower() or 
                                                    "keyboard" in element.get("resource-id", "").lower()):
                        keyboard = True
                        break

            # 生成动作提示并获取响应
            prompt_action = get_action_prompt(
                config['instruction'], 
                perception_infos, 
                width, 
                height, 
                keyboard, 
                run_status['summary_history'], 
                run_status['action_history'], 
                run_status['summary'], 
                run_status['action'], 
                config['add_info'], 
                error_flag, 
                run_status['completed_requirements'], 
                run_status['memory']
            )
            
            chat_action = init_action_chat()
            chat_action = add_response("user", prompt_action, chat_action, screenshot_file)

            output_action = inference_chat(chat_action, 'gpt-4o', config['API_url'], config['token'])
            thought = output_action.split("### Thought ###")[-1].split("### Action ###")[0].replace("\n", " ").replace(":", "").replace("  ", " ").strip()
            run_status['summary'] = output_action.split("### Operation ###")[-1].replace("\n", " ").replace("  ", " ").strip()
            run_status['action'] = output_action.split("### Action ###")[-1].split("### Operation ###")[0].replace("\n", " ").replace("  ", " ").strip()
            chat_action = add_response("assistant", output_action, chat_action)
            
            # 记录输出到状态
            status_output = "#" * 50 + " 决策 " + "#" * 50 + "\n"
            status_output += output_action + "\n"
            status_output += '#' * 110 + "\n"
            run_status['output'].append(status_output)
            
            # 处理记忆相关内容
            if config['memory_switch']:
                prompt_memory = get_memory_prompt(run_status['insight'])
                chat_action = add_response("user", prompt_memory, chat_action)
                output_memory = inference_chat(chat_action, 'gpt-4o', config['API_url'], config['token'])
                chat_action = add_response("assistant", output_memory, chat_action)
                
                status_output = "#" * 50 + " 记忆 " + "#" * 50 + "\n"
                status_output += output_memory + "\n"
                status_output += '#' * 110 + "\n"
                run_status['output'].append(status_output)
                
                output_memory = output_memory.split("### Important content ###")[-1].split("\n\n")[0].strip() + "\n"
                if "None" not in output_memory and output_memory not in run_status['memory']:
                    run_status['memory'] += output_memory
            
            # 执行动作
            action = run_status['action']
            if "Open app" in action:
                app_name = action.split("(")[-1].split(")")[0]
                
                elements, _, _ = get_ui_elements(config['adb_path'])
                app_center = find_app_by_name(elements, app_name)
                
                if app_center:
                    tap(config['adb_path'], app_center[0], app_center[1])
                    if config['record_operations']:
                        log_operation("Open app", {
                            "app_name": app_name,
                            "x": app_center[0],
                            "y": app_center[1],
                            "wait_time": 5
                        })
                else:
                    run_status['output'].append(f"未找到应用: {app_name}")
            
            elif "Tap" in action:
                coordinate = action.split("(")[-1].split(")")[0].split(", ")
                x, y = int(coordinate[0]), int(coordinate[1])
                tap(config['adb_path'], x, y)
                if config['record_operations']:
                    log_operation("Tap", {"x": x, "y": y, "wait_time": 5})
            
            elif "Swipe" in action:
                coordinate1 = action.split("Swipe (")[-1].split("), (")[0].split(", ")
                coordinate2 = action.split("), (")[-1].split(")")[0].split(", ")
                x1, y1 = int(coordinate1[0]), int(coordinate1[1])
                x2, y2 = int(coordinate2[0]), int(coordinate2[1])
                slide(config['adb_path'], x1, y1, x2, y2)
                if config['record_operations']:
                    log_operation("Swipe", {
                        "start_x": x1, 
                        "start_y": y1, 
                        "end_x": x2, 
                        "end_y": y2,
                        "wait_time": 5
                    })
                
            elif "Type" in action:
                if "(text)" not in action:
                    text = action.split("(")[-1].split(")")[0]
                else:
                    text = action.split(" \"")[-1].split("\"")[0]
                type(config['adb_path'], text)
                if config['record_operations']:
                    log_operation("Type", {"text": text, "wait_time": 5})
            
            elif "Back" in action:
                back(config['adb_path'])
                if config['record_operations']:
                    log_operation("Back", {"wait_time": 5})
            
            elif "Home" in action:
                home(config['adb_path'])
                if config['record_operations']:
                    log_operation("Home", {"wait_time": 5})
                
            elif "Stop" in action:
                if config['record_operations']:
                    log_operation("Stop", {"wait_time": 0})
                break
            
            time.sleep(5)
            
            # 保存上一次的状态
            last_perception_infos = copy.deepcopy(perception_infos)
            last_screenshot_file = "./screenshot/last_screenshot.jpg"
            last_keyboard = keyboard
            if os.path.exists(last_screenshot_file):
                os.remove(last_screenshot_file)
            os.rename(screenshot_file, last_screenshot_file)
            
            # 获取新的感知信息
            perception_infos, width, height = get_perception_infos(config['adb_path'], screenshot_file, config)
            
            # 使用布局解析器检测键盘状态
            elements, _, keyboard_height = get_ui_elements(config['adb_path'])
            keyboard = False
            keyboard_height_limit = 0.6 * keyboard_height
            
            for element in elements:
                y = element["center"][1]
                if y > keyboard_height_limit and ("keyboard" in element["text"].lower() or 
                                                "keyboard" in element.get("resource-id", "").lower()):
                    keyboard = True
                    break
            
            # 反思机制
            if config['reflection_switch']:
                prompt_reflect = get_reflect_prompt(
                    config['instruction'], 
                    last_perception_infos, 
                    perception_infos, 
                    width, 
                    height, 
                    last_keyboard, 
                    keyboard, 
                    run_status['summary'], 
                    run_status['action'], 
                    config['add_info']
                )
                chat_reflect = init_reflect_chat()
                chat_reflect = add_response_two_image("user", prompt_reflect, chat_reflect, [last_screenshot_file, screenshot_file])

                output_reflect = inference_chat(chat_reflect, 'gpt-4o', config['API_url'], config['token'])
                reflect = output_reflect.split("### Answer ###")[-1].replace("\n", " ").strip()
                chat_reflect = add_response("assistant", output_reflect, chat_reflect)
                
                status_output = "#" * 50 + " 反思 " + "#" * 50 + "\n"
                status_output += output_reflect + "\n"
                status_output += '#' * 110 + "\n"
                run_status['output'].append(status_output)
            
                if 'A' in reflect:  # 操作成功
                    run_status['thought_history'].append(thought)
                    run_status['summary_history'].append(run_status['summary'])
                    run_status['action_history'].append(run_status['action'])
                    
                    prompt_planning = get_process_prompt(
                        config['instruction'], 
                        run_status['thought_history'], 
                        run_status['summary_history'], 
                        run_status['action_history'], 
                        run_status['completed_requirements'], 
                        config['add_info']
                    )
                    chat_planning = init_memory_chat()
                    chat_planning = add_response("user", prompt_planning, chat_planning)
                    output_planning = inference_chat(chat_planning, 'gpt-4-turbo', config['API_url'], config['token'])
                    chat_planning = add_response("assistant", output_planning, chat_planning)
                    
                    status_output = "#" * 50 + " 规划 " + "#" * 50 + "\n"
                    status_output += output_planning + "\n"
                    status_output += '#' * 110 + "\n"
                    run_status['output'].append(status_output)
                    
                    run_status['completed_requirements'] = output_planning.split("### Completed contents ###")[-1].replace("\n", " ").strip()
                    error_flag = False
                
                elif 'B' in reflect:  # 需要返回
                    error_flag = True
                    back(config['adb_path'])
                    
                elif 'C' in reflect:  # 操作失败
                    error_flag = True
            
            else:  # 不使用反思机制
                run_status['thought_history'].append(thought)
                run_status['summary_history'].append(run_status['summary'])
                run_status['action_history'].append(run_status['action'])
                
                prompt_planning = get_process_prompt(
                    config['instruction'], 
                    run_status['thought_history'], 
                    run_status['summary_history'], 
                    run_status['action_history'], 
                    run_status['completed_requirements'], 
                    config['add_info']
                )
                chat_planning = init_memory_chat()
                chat_planning = add_response("user", prompt_planning, chat_planning)
                output_planning = inference_chat(chat_planning, 'gpt-4-turbo', config['API_url'], config['token'])
                chat_planning = add_response("assistant", output_planning, chat_planning)
                
                status_output = "#" * 50 + " 规划 " + "#" * 50 + "\n"
                status_output += output_planning + "\n"
                status_output += '#' * 110 + "\n"
                run_status['output'].append(status_output)
                
                run_status['completed_requirements'] = output_planning.split("### Completed contents ###")[-1].replace("\n", " ").strip()
                 
            os.remove(last_screenshot_file)
            
    except Exception as e:
        run_status['output'].append(f"错误: {str(e)}")
    finally:
        run_status['is_running'] = False

def run_mobile_agent(mode):
    global config
    try:
        config = load_config()
        
        # 检查 API 密钥设置
        if config['caption_call_method'] == "api" and (not config['qwen_api'] or config['qwen_api'].strip() == ""):
            run_status['output'].append("警告: 使用API模式但未提供有效的API密钥，请在设置中配置API密钥")
        
        # 根据模式设置配置
        if mode == 'record':
            config['record_operations'] = True
            config['replay_mode'] = False
        elif mode == 'replay':
            config['record_operations'] = False
            config['replay_mode'] = True
            
        # 清空输出列表
        run_status['output'] = []
        
        # 检查ADB路径
        if not os.path.exists(config['adb_path']):
            run_status['output'].append(f"警告: ADB路径不存在: {config['adb_path']}")
        
        # 重置运行状态
        run_status.update({
            'thought_history': [],
            'summary_history': [],
            'action_history': [],
            'summary': "",
            'action': "",
            'completed_requirements': "",
            'memory': "",
            'insight': ""
        })
        
        # 加载模型
        run_status['output'].append("开始加载模型...")
        load_models(config)
        
        if config['replay_mode']:
            # 重放模式
            if not os.path.exists(config['operations_log_file']):
                run_status['output'].append(f"操作日志文件 {config['operations_log_file']} 不存在!")
                return
            
            try:
                with open(config['operations_log_file'], 'r') as f:
                    operations = json.load(f)
                
                for op in operations:
                    action_type = op["action_type"]
                    params = op["params"]
                    status_output = f"重放操作: {action_type} {params}"
                    run_status['output'].append(status_output)
                    
                    if action_type == "Tap":
                        x, y = params["x"], params["y"]
                        tap(config['adb_path'], x, y)
                    elif action_type == "Swipe":
                        x1, y1 = params["start_x"], params["start_y"]
                        x2, y2 = params["end_x"], params["end_y"]
                        slide(config['adb_path'], x1, y1, x2, y2)
                    elif action_type == "Type":
                        text = params["text"]
                        type(config['adb_path'], text)
                    elif action_type == "Back":
                        back(config['adb_path'])
                    elif action_type == "Home":
                        home(config['adb_path'])
                    elif action_type == "Open app":
                        app_name = params["app_name"]
                        from MobileAgent.layout_parser import get_ui_elements, find_app_by_name
                        
                        elements, _, _ = get_ui_elements(config['adb_path'])
                        app_center = find_app_by_name(elements, app_name)
                        
                        if app_center:
                            tap(config['adb_path'], app_center[0], app_center[1])
                        else:
                            run_status['output'].append(f"重放时未找到应用: {app_name}")
                    
                    time.sleep(params.get("wait_time", 5))
                
                run_status['output'].append("操作重放完成!")
                
            except Exception as e:
                run_status['output'].append(f"重放操作时出错: {str(e)}")
        else:
            # 正常执行模式
            execute_mobile_agent(config)
            
            # 如果是记录模式，复制操作日志到logs目录
            if mode == 'record' and os.path.exists(config['operations_log_file']):
                timestamp = time.strftime("%Y%m%d_%H%M%S")
                log_name = f"log_{timestamp}.json"
                shutil.copy2(config['operations_log_file'], os.path.join(OPERATIONS_DIR, log_name))
                
    except Exception as e:
        run_status['output'].append(f"错误: {str(e)}")
    finally:
        run_status['is_running'] = False

# 启动记录模式
@app.route('/start_record', methods=['POST'])
def start_record():
    if run_status['is_running']:
        return jsonify({'success': False, 'message': '已有任务正在运行'})
    
    run_status['is_running'] = True
    run_status['mode'] = 'record'
    run_status['output'] = []
    
    # 在新线程中运行
    thread = Thread(target=run_mobile_agent, args=('record',))
    thread.daemon = True
    thread.start()
    
    return jsonify({'success': True})

# 启动重放模式
@app.route('/start_replay', methods=['POST'])
def start_replay():
    if run_status['is_running']:
        return jsonify({'success': False, 'message': '已有任务正在运行'})
    
    log_file = request.form.get('log_file')
    if not log_file:
        return jsonify({'success': False, 'message': '请选择要重放的操作日志'})
    
    # 更新配置文件
    config = load_config()
    config['operations_log_file'] = log_file
    save_config(config)
    
    run_status['is_running'] = True
    run_status['mode'] = 'replay'
    run_status['output'] = []
    
    # 在新线程中运行
    thread = Thread(target=run_mobile_agent, args=('replay',))
    thread.daemon = True
    thread.start()
    
    return jsonify({'success': True})

# 获取运行状态
@app.route('/status')
def get_status():
    return jsonify({
        'is_running': run_status['is_running'],
        'mode': run_status['mode'],
        'output': run_status['output']
    })

# 停止运行
@app.route('/stop', methods=['POST'])
def stop_run():
    if run_status['is_running'] and run_status['process']:
        try:
            run_status['process'].terminate()
            run_status['is_running'] = False
            return jsonify({'success': True})
        except Exception as e:
            return jsonify({'success': False, 'message': str(e)})
    else:
        return jsonify({'success': False, 'message': '没有运行中的任务'})

# 创建修改后的run.py
def create_run_web_py():
    with open('run.py', 'r', encoding='utf-8') as original_file:
        content = original_file.read()
    
    # 修改导入部分，引入配置
    modified_content = "# 从临时配置文件导入配置\nfrom temp_config import *\n\n"
    
    # 删除原始配置部分
    start_marker = "####################################### Edit your Setting #########################################"
    end_marker = "###################################################################################################"
    
    start_idx = content.find(start_marker)
    end_idx = content.find(end_marker, start_idx) + len(end_marker)
    
    if start_idx != -1 and end_idx != -1:
        modified_content += content[:start_idx] + content[end_idx:]
    else:
        modified_content += content
    
    # 写入修改后的文件
    with open('run_web.py', 'w', encoding='utf-8') as f:
        f.write(modified_content)

# Helper functions from run_web.py
def get_all_files_in_folder(folder_path):
    file_list = []
    for file_name in os.listdir(folder_path):
        file_list.append(file_name)
    return file_list

def draw_coordinates_on_image(image_path, coordinates):
    image = Image.open(image_path)
    draw = ImageDraw.Draw(image)
    point_size = 10
    for coord in coordinates:
        draw.ellipse((coord[0] - point_size, coord[1] - point_size, coord[0] + point_size, coord[1] + point_size), fill='red')
    output_image_path = './screenshot/output_image.png'
    image.save(output_image_path)
    return output_image_path

def crop(image, box, i):
    image = Image.open(image)
    x1, y1, x2, y2 = int(box[0]), int(box[1]), int(box[2]), int(box[3])
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

def process_image(image, query, config):
    # 检查 API 密钥是否有效
    if not config['qwen_api'] or config['qwen_api'].strip() == "":
        return "API key not provided. Unable to process image."
    
    try:
        dashscope.api_key = config['qwen_api']
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
        response = MultiModalConversation.call(model=config['caption_model'], messages=messages)
        
        try:
            response = response['output']['choices'][0]['message']['content'][0]["text"]
        except:
            response = "This is an icon."
        
        return response
    except Exception as e:
        run_status['output'].append(f"API调用错误: {str(e)}")
        return "Error processing image."

def generate_api(images, query, config):
    # 检查 API 密钥是否有效
    if not config['qwen_api'] or config['qwen_api'].strip() == "":
        run_status['output'].append("警告: API密钥未提供，无法处理图像描述")
        return {i+1: "API key not provided" for i in range(len(images))}
    
    icon_map = {}
    try:
        with concurrent.futures.ThreadPoolExecutor() as executor:
            futures = {executor.submit(process_image, image, query, config): i for i, image in enumerate(images)}
            
            for future in concurrent.futures.as_completed(futures):
                i = futures[future]
                response = future.result()
                icon_map[i + 1] = response
    except Exception as e:
        run_status['output'].append(f"并发API调用错误: {str(e)}")
        # 提供默认响应
        for i in range(len(images)):
            icon_map[i + 1] = "Error processing image"
    
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

def get_perception_infos(adb_path, screenshot_file, config):
    # 使用ADB布局解析器获取UI元素
    try:
        from MobileAgent.layout_parser import get_ui_elements, format_elements_for_llm
        
        # 获取UI元素和屏幕尺寸
        elements, width, height = get_ui_elements(adb_path, screenshot_file)
        
        if not elements:
            run_status['output'].append("警告: 无法获取UI元素，请检查设备连接")
            return [], 0, 0
        
        # 转换元素为perception_infos格式
        perception_infos = format_elements_for_llm(elements)
        
        return perception_infos, width, height
    
    except Exception as e:
        run_status['output'].append(f"获取UI元素失败: {str(e)}")
        return [], 0, 0

# 加载模型
device = "cuda"
torch.manual_seed(1234)

def load_models(config):
    global model, tokenizer
    global qwen_api, caption_model, caption_call_method
    
    # 将配置中的值赋给全局变量
    qwen_api = config['qwen_api']
    caption_model = config['caption_model']
    caption_call_method = config['caption_call_method']
    
    if config['caption_call_method'] == "local":
        if config['caption_model'] == "qwen-vl-chat":
            model_dir = snapshot_download('qwen/Qwen-VL-Chat', revision='v1.1.0')
            model = AutoModelForCausalLM.from_pretrained(model_dir, device_map=device, trust_remote_code=True).eval()
            model.generation_config = GenerationConfig.from_pretrained(model_dir, trust_remote_code=True)
        elif config['caption_model'] == "qwen-vl-chat-int4":
            qwen_dir = snapshot_download("qwen/Qwen-VL-Chat-Int4", revision='v1.0.0')
            model = AutoModelForCausalLM.from_pretrained(qwen_dir, device_map=device, trust_remote_code=True,use_safetensors=True).eval()
            model.generation_config = GenerationConfig.from_pretrained(qwen_dir, trust_remote_code=True, do_sample=False)
        else:
            print("If you choose local caption method, you must choose the caption model from \"Qwen-vl-chat\" and \"Qwen-vl-chat-int4\"")
            exit(0)
        tokenizer = AutoTokenizer.from_pretrained(qwen_dir, trust_remote_code=True)
    elif config['caption_call_method'] == "api":
        pass
    else:
        print("You must choose the caption model call function from \"local\" and \"api\"")
        exit(0)
    
    run_status['output'].append("模型加载完成")

def log_operation(action_type, params=None):
    """记录操作到日志文件"""
    if not config['record_operations']:
        return
        
    timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
    operation = {
        "timestamp": timestamp,
        "action_type": action_type,
        "params": params
    }
    
    # 检查文件是否存在
    if os.path.exists(config['operations_log_file']):
        # 读取现有操作记录
        try:
            with open(config['operations_log_file'], 'r') as f:
                operations = json.load(f)
        except json.JSONDecodeError:
            operations = []
    else:
        operations = []
    
    # 添加新操作并保存
    operations.append(operation)
    with open(config['operations_log_file'], 'w') as f:
        json.dump(operations, f, indent=2)
    
    status_output = f"已记录操作: {action_type} {params}"
    run_status['output'].append(status_output)

# 保存修改后的日志
@app.route('/save_log_changes', methods=['POST'])
def save_log_changes():
    try:
        data = request.json
        log_path = data.get('log_path')
        log_data = data.get('log_data')
        
        if not log_path or not log_data:
            return jsonify({'success': False, 'message': '缺少必要参数'})
        
        # 确定文件路径
        if log_path == 'operations_log.json':
            file_path = log_path
        else:
            file_path = os.path.join(OPERATIONS_DIR, os.path.basename(log_path))
        
        # 保存修改后的日志
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(log_data, f, indent=2, ensure_ascii=False)
        
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})

# 复制日志文件
@app.route('/duplicate_log', methods=['POST'])
def duplicate_log():
    try:
        source_log = request.form.get('source_log')
        new_log_name = request.form.get('new_log_name')
        
        if not source_log or not new_log_name:
            return jsonify({'success': False, 'message': '缺少必要参数'})
        
        # 确定源文件路径
        if source_log == 'operations_log.json':
            source_path = source_log
        else:
            source_path = os.path.join(OPERATIONS_DIR, os.path.basename(source_log))
        
        # 确定目标文件路径
        target_path = os.path.join(OPERATIONS_DIR, os.path.basename(new_log_name))
        
        # 读取源文件并写入目标文件
        with open(source_path, 'r', encoding='utf-8') as source_file:
            log_data = json.load(source_file)
            
        with open(target_path, 'w', encoding='utf-8') as target_file:
            json.dump(log_data, target_file, indent=2, ensure_ascii=False)
        
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})

if __name__ == '__main__':
    # 创建修改后的run.py
    create_run_web_py()
    app.run(debug=True, host='0.0.0.0', port=5000) 