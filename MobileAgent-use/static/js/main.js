$(document).ready(function() {
    // 程序状态轮询
    let statusPoller = null;
    
    // 开始轮询状态
    function startStatusPolling() {
        if (statusPoller !== null) {
            clearInterval(statusPoller);
        }
        
        statusPoller = setInterval(function() {
            $.ajax({
                url: '/status',
                method: 'GET',
                success: function(response) {
                    updateStatus(response);
                },
                error: function() {
                    console.error('获取状态信息失败');
                }
            });
        }, 2000);
    }
    
    // 停止轮询状态
    function stopStatusPolling() {
        if (statusPoller !== null) {
            clearInterval(statusPoller);
            statusPoller = null;
        }
    }
    
    // 更新状态显示
    function updateStatus(status) {
        const isRunning = status.is_running;
        const mode = status.mode;
        const output = status.output;
        
        // 更新状态标签
        if (isRunning) {
            $('#statusBadge').removeClass('bg-secondary').addClass('bg-success');
            $('#statusBadge').text(mode === 'record' ? '记录中' : '回放中');
            
            // 禁用按钮
            $('#startRecordBtn, #startReplayBtn, #logFileSelect').prop('disabled', true);
            $('#stopBtn').prop('disabled', false);
        } else {
            $('#statusBadge').removeClass('bg-success').addClass('bg-secondary');
            $('#statusBadge').text('未运行');
            
            // 启用按钮
            $('#startRecordBtn, #startReplayBtn, #logFileSelect').prop('disabled', false);
            $('#stopBtn').prop('disabled', true);
            
            // 停止轮询
            stopStatusPolling();
            
            // 刷新页面 (如果之前在运行)
            if ($('#stopBtn').data('was-running')) {
                $('#stopBtn').data('was-running', false);
                location.reload();
                return;
            }
        }
        
        // 更新输出日志
        const outputLog = $('#outputLog');
        outputLog.empty();
        
        output.forEach(function(line) {
            // 格式化输出，让关键信息高亮
            let formattedLine = line;
            
            // 高亮决策信息
            if (line.includes('决策')) {
                formattedLine = '<strong class="text-info">' + line + '</strong>';
            }
            // 高亮反思信息
            else if (line.includes('反思')) {
                formattedLine = '<strong class="text-warning">' + line + '</strong>';
            }
            // 高亮记忆信息
            else if (line.includes('记忆')) {
                formattedLine = '<strong class="text-success">' + line + '</strong>';
            }
            // 高亮规划信息
            else if (line.includes('规划')) {
                formattedLine = '<strong class="text-primary">' + line + '</strong>';
            }
            // 高亮操作信息
            else if (line.includes('已记录操作')) {
                formattedLine = '<strong class="text-light">' + line + '</strong>';
            }
            // 高亮错误信息
            else if (line.includes('错误') || line.includes('Error') || line.includes('Failed')) {
                formattedLine = '<strong class="text-danger">' + line + '</strong>';
            }
            
            outputLog.append('<div class="log-line">' + formattedLine + '</div>');
        });
        
        // 滚动到底部
        outputLog.scrollTop(outputLog[0].scrollHeight);
    }
    
    // 开始记录操作
    $('#startRecordBtn').click(function() {
        $.ajax({
            url: '/start_record',
            method: 'POST',
            success: function(response) {
                if (response.success) {
                    // 开始轮询状态
                    startStatusPolling();
                } else {
                    alert('启动记录失败: ' + response.message);
                }
            },
            error: function() {
                alert('网络错误，请重试');
            }
        });
    });
    
    // 开始重放操作
    $('#startReplayBtn').click(function() {
        const logFile = $('#logFileSelect').val();
        
        if (!logFile) {
            alert('请选择要重放的操作日志文件');
            return;
        }
        
        $.ajax({
            url: '/start_replay',
            method: 'POST',
            data: {
                log_file: logFile
            },
            success: function(response) {
                if (response.success) {
                    // 开始轮询状态
                    startStatusPolling();
                } else {
                    alert('启动重放失败: ' + response.message);
                }
            },
            error: function() {
                alert('网络错误，请重试');
            }
        });
    });
    
    // 停止运行
    $('#stopBtn').click(function() {
        $.ajax({
            url: '/stop',
            method: 'POST',
            success: function(response) {
                if (response.success) {
                    $('#stopBtn').data('was-running', true);
                } else {
                    alert('停止失败: ' + response.message);
                }
            },
            error: function() {
                alert('网络错误，请重试');
            }
        });
    });
    
    // 如果当前有任务在运行，开始轮询状态
    if ($('#statusBadge').text() !== '未运行') {
        startStatusPolling();
    }
}); 