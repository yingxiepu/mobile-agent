MobileAgent Web 控制台是一个基于 Flask 的 Web 应用程序，为 MobileAgent 提供图形用户界面😎。它允许用户配置 MobileAgent，执行操作记录和回放，以及可视化查看操作日志。
功能特点
可视化配置 MobileAgent 的所有参数🥰
启动 AI 记录操作模式🚀
查看和回放已记录的操作📺
实时显示执行日志📄
操作日志可视化，包括点击和滑动动作的可视化展示👀
安装
确保已安装 Python 和所需依赖👏。Python 是运行这个 Web 应用程序的基础，你可以从 Python 官方网站 下载并安装适合你操作系统的版本。
安装 Flask 和其他依赖😃：
plaintext
pip install flask

这里的 pip 是 Python 的包管理工具，执行上述命令后，它会自动从 Python 包索引（PyPI）下载并安装 Flask 库。
使用方法
1. 启动 Web 服务器🎬
在命令行终端中，使用以下命令启动 Flask 应用程序：
plaintext
python mobile_agent_webapp/app.py
当你执行这个命令后，Flask 会启动一个本地的 Web 服务器。如果一切顺利，你会在终端看到类似如下的输出：
plaintext
 * Serving Flask app 'app'
 * Debug mode: off
WARNING: This is a development server. Do not use it in a production deployment. Use a production WSGI server instead.
 * Running on http://127.0.0.1:5000
Press CTRL+C to quit
这表明服务器已经成功启动，并且正在监听 http://127.0.0.1:5000（等同于 http://localhost:5000）这个地址。
2. 在浏览器中访问🌐
打开你常用的浏览器（如 Chrome、Firefox 等），在地址栏中输入：
plaintext
http://localhost:5000
按下回车键后，你将看到 MobileAgent Web 控制台的主页😀。如果浏览器显示页面无法访问，可能是服务器没有正确启动，你可以检查终端中的输出信息，查看是否有错误提示。
3. 配置参数🛠️
进入配置页面：在主页上找到并点击 “配置” 相关的按钮或链接，进入配置页面。
设置 ADB 路径：ADB（Android Debug Bridge）是一个通用的命令行工具，用于与 Android 设备进行通信。你需要在配置页面中找到 “ADB 路径” 的输入框，然后输入你本地计算机上 ADB 工具的完整路径。例如，如果 ADB 工具安装在 C:\Android\Sdk\platform-tools\adb.exe（Windows 系统），你就将这个路径填入输入框中。
设置 API 密钥：这里可能涉及到多个 API，比如 GPT - 4o 和千问 API。找到对应的输入框，分别输入你从相应平台获取的 API 密钥。这些密钥是访问 API 服务的凭证，务必确保输入的密钥准确无误。
4. 开始记录操作🚦
在完成所有参数配置后，返回主页。在主页上找到 “开始记录操作” 的按钮，点击它😎。这时，AI 就会开始执行任务，并记录下相关的操作。在记录过程中，你可以实时观察到执行日志的更新，了解任务的执行情况。
5. 查看和回放操作日志📝
查看操作日志：在主页或相关页面中，找到 “操作日志” 的入口，点击进入日志查看页面。这里会显示所有已记录的操作日志，包括操作的时间、类型（如点击、滑动等）等详细信息。
回放操作：对于每条记录的操作，通常会有一个 “回放” 按钮。点击这个按钮，系统会重新执行该操作，让你可以直观地看到操作的效果。
目录结构
mobile_agent_webapp/app.py - Flask 应用程序主文件📄
mobile_agent_webapp/templates/ - HTML 模板📋
mobile_agent_webapp/static/ - 静态资源 (CSS、JavaScript)🖼️
operation_logs/ - 保存的操作日志文件📁
config.json - 用户配置文件⚙️
注意事项
请确保已正确设置 ADB 路径和其他配置✅，否则可能无法与 Android 设备进行正常通信。
确保 Android 设备已连接并启用 USB 调试🤖，这样才能让 ADB 工具识别并控制设备。
正确配置 GPT - 4o 和千问 API 密钥🔑，否则无法使用相关的 AI 服务。




The MobileAgent Web Console is a Flask-based web application that provides a graphical user interface for MobileAgent. It allows users to configure MobileAgent, perform operation recording and playback, and visually view the operation logs.
Features
Visually configure all parameters of MobileAgent 🥰
Launch the AI operation recording mode 🚀
View and playback the recorded operations 📺
Display the execution logs in real time 📄
Visualize the operation logs, including the visual display of click and swipe actions 👀
Installation
Make sure Python and the required dependencies are installed 👏. Python is the foundation for running this web application. You can download and install the version suitable for your operating system from the official Python website.
Install Flask and other dependencies 😃:
plaintext
pip install flask

Here, pip is Python's package management tool. After executing the above command, it will automatically download and install the Flask library from the Python Package Index (PyPI).
Usage Instructions
1. Start the Web Server 🎬
In the command-line terminal, use the following command to start the Flask application:
plaintext
python mobile_agent_webapp/app.py
When you execute this command, Flask will start a local web server. If everything goes smoothly, you will see output similar to the following in the terminal:
plaintext
 * Serving Flask app 'app'
 * Debug mode: off
WARNING: This is a development server. Do not use it in a production deployment. Use a production WSGI server instead.
 * Running on http://127.0.0.1:5000
Press CTRL+C to quit
This indicates that the server has been successfully started and is listening on the address http://127.0.0.1:5000 (which is equivalent to http://localhost:5000).
2. Access in the Browser 🌐
Open your preferred browser (such as Chrome, Firefox, etc.) and enter the following in the address bar:
plaintext
http://localhost:5000
After pressing the Enter key, you will see the home page of the MobileAgent Web Console 😀. If the browser shows that the page cannot be accessed, it is likely that the server was not started correctly. You can check the output information in the terminal to see if there are any error prompts.
3. Configure Parameters 🛠️
Enter the configuration page: Find and click the button or link related to "Configuration" on the home page to enter the configuration page.
Set the ADB path: ADB (Android Debug Bridge) is a general command-line tool for communicating with Android devices. You need to find the input box for the "ADB path" on the configuration page and then enter the full path of the ADB tool on your local computer. For example, if the ADB tool is installed at C:\Android\Sdk\platform-tools\adb.exe (for Windows systems), you should enter this path into the input box.
Set the API keys: There may be multiple APIs involved here, such as the GPT-4o and Qianwen API. Find the corresponding input boxes and enter the API keys you obtained from the respective platforms. These keys are the credentials for accessing the API services, so make sure the entered keys are accurate.
4. Start Recording Operations 🚦
After completing all parameter configurations, return to the home page. Find the button labeled "Start Recording Operations" on the home page and click it 😎. At this time, the AI will start executing tasks and record the relevant operations. During the recording process, you can observe the real-time update of the execution logs to understand the progress of the task execution.
5. View and Playback Operation Logs 📝
View operation logs: Find the entrance to the "Operation Logs" on the home page or the relevant page and click to enter the log viewing page. All recorded operation logs will be displayed here, including detailed information such as the operation time, type (such as click, swipe, etc.).
Playback operations: For each recorded operation, there is usually a "Playback" button. Click this button, and the system will re-execute the operation, allowing you to intuitively see the effect of the operation.
Directory Structure
mobile_agent_webapp/app.py - The main file of the Flask application 📄
mobile_agent_webapp/templates/ - HTML templates 📋
mobile_agent_webapp/static/ - Static resources (CSS, JavaScript) 🖼️
operation_logs/ - Saved operation log files 📁
config.json - User configuration file ⚙️
Notes
Please ensure that the ADB path and other configurations are set correctly ✅, otherwise, it may not be possible to communicate properly with the Android device.
Make sure the Android device is connected and USB debugging is enabled 🤖, so that the ADB tool can recognize and control the device.
Configure the GPT-4o and Qianwen API keys correctly 🔑, otherwise, the related AI services cannot be used.
