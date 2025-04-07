# MobileAgent Web 控制台

MobileAgent Web 控制台是一个基于Flask的Web应用程序，为MobileAgent提供图形用户界面。它允许用户配置MobileAgent，执行操作记录和回放，以及可视化查看操作日志。

## 功能特点

- 可视化配置MobileAgent的所有参数
- 启动AI记录操作模式
- 查看和回放已记录的操作
- 实时显示执行日志
- 操作日志可视化，包括点击和滑动动作的可视化展示

## 安装

1. 确保已安装Python和所需依赖
2. 安装Flask和其他依赖:
   ```
   pip install flask
   ```

## 使用方法

1. 启动Web服务器:
   ```
   python mobile_agent_webapp/app.py
   ```

2. 在浏览器中访问:
   ```
   http://localhost:5000
   ```

3. 在配置页面设置所有参数，包括ADB路径和API密钥

4. 在主页上点击"开始记录操作"让AI执行任务

5. 查看已记录的操作日志并重放

## 目录结构

- `mobile_agent_webapp/app.py` - Flask应用程序主文件
- `mobile_agent_webapp/templates/` - HTML模板
- `mobile_agent_webapp/static/` - 静态资源(CSS、JavaScript)
- `operation_logs/` - 保存的操作日志文件
- `config.json` - 用户配置文件

## 注意事项

- 请确保已正确设置ADB路径和其他配置
- 确保Android设备已连接并启用USB调试
- 正确配置GPT-4o和千问API密钥 