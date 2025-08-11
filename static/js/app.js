// ==============================
// 初始化WebSocket连接
// ==============================
const socket = io('/status', { 
    transports: ['websocket', 'polling'],
    reconnection: true,
    reconnectionDelay: 1000,
    reconnectionDelayMax: 5000,
    reconnectionAttempts: 5,
    timeout: 20000
});

// 转录状态变量
let taskStatus = {};
let queueItems = {};
let uploadedFiles = []; // 存储上传的文件名
let currentTaskId = null; // 当前活动的任务ID
let isTranscribing = false; // 是否正在转录
let gpuMemoryInfo = {}; // GPU内存信息

// ==============================
// WebSocket事件处理
// ==============================

// 连接到WebSocket服务器
socket.on('connect', () => {
    addStatusLog('已连接到服务器', 'info');
    // 恢复状态
    checkTranscriptionStatus();
});

// 断开连接处理
socket.on('disconnect', (reason) => {
    addStatusLog(`与服务器断开连接: ${reason}`, 'warning');
});

// 重连尝试
socket.on('reconnect_attempt', (attemptNumber) => {
    addStatusLog(`正在尝试重连... (${attemptNumber}/5)`, 'info');
});

// 重连成功
socket.on('reconnect', (attemptNumber) => {
    addStatusLog(`重连成功 (尝试次数: ${attemptNumber})`, 'success');
});

// 重连失败
socket.on('reconnect_failed', () => {
    addStatusLog('重连失败，请刷新页面', 'error');
});

// 连接错误
socket.on('connect_error', (error) => {
    addStatusLog(`连接错误: ${error.message}`, 'error');
});

// 接收日志消息
socket.on('log_message', (data) => {
    addStatusLog(data.message, data.level);
});

// 接收内存警告
socket.on('memory_warning', (data) => {
    const message = data.message || '显存不足';
    const insufficientGpus = data.insufficient_gpus || [];
    const recommendedModels = data.recommended_models || [];
    
    let warningHtml = `<div class="alert alert-warning" role="alert">`;
    warningHtml += `<h6><i class="fas fa-exclamation-triangle"></i> ${message}</h6>`;
    
    if (insufficientGpus.length > 0) {
        warningHtml += `<p><strong>显存不足的GPU:</strong> ${insufficientGpus.join(', ')}</p>`;
    }
    
    if (recommendedModels.length > 0) {
        warningHtml += `<p><strong>建议使用的模型:</strong> ${recommendedModels.join(', ')}</p>`;
        warningHtml += `<p class="mb-0">请选择较小的模型或等待当前任务完成后再试。</p>`;
    }
    
    warningHtml += `</div>`;
    
    // 显示警告信息
    const memoryInfo = document.getElementById('memoryInfo');
    if (memoryInfo) {
        memoryInfo.innerHTML = warningHtml;
        document.getElementById('gpuMemoryStatus').style.display = 'block';
    }
    
    addStatusLog(message, 'warning');
});

// 接收任务更新
socket.on('task_update', (data) => {
    const taskId = data.task_id;
    const status = data.status;
    const message = data.message || '';
    const filename = data.filename || '未知文件';
    const progress = data.progress || 0;
    
    // 更新任务状态
    taskStatus[taskId] = {
        status: status,
        message: message,
        filename: filename,
        progress: progress,
        startTime: taskStatus[taskId]?.startTime || Date.now()
    };
    
    // 处理不同状态
    switch(status) {
        case 'queued':
            addQueueItem(taskId, filename, 'queued', message, data.position);
            currentTaskId = taskId;
            isTranscribing = true;
            break;
        case 'processing':
            updateQueueItem(taskId, 'processing', message, progress);
            startTaskTimer(taskId);
            currentTaskId = taskId;
            isTranscribing = true;
            break;
        case 'completed':
            updateQueueItem(taskId, 'completed', message);
            stopTaskTimer(taskId);
            // 重置状态
            if (currentTaskId === taskId) {
                currentTaskId = null;
                isTranscribing = false;
                // 恢复按钮状态
                if (startTranscriptionBtn) {
                    startTranscriptionBtn.disabled = false;
                }
                // 启用文件选择和上传
                document.querySelectorAll('.uploaded-file-checkbox').forEach(checkbox => {
                    checkbox.disabled = false;
                });
                dropArea.classList.remove('disabled');
            }
            if (data.output_file) {
                // 刷新输出文件列表而不是整个页面
                refreshOutputFilesList();
            }
            break;
        case 'failed':
            updateQueueItem(taskId, 'failed', message);
            stopTaskTimer(taskId);
            // 重置状态
            if (currentTaskId === taskId) {
                currentTaskId = null;
                isTranscribing = false;
                // 恢复按钮状态
                if (startTranscriptionBtn) {
                    startTranscriptionBtn.disabled = false;
                }
                // 启用文件选择和上传
                document.querySelectorAll('.uploaded-file-checkbox').forEach(checkbox => {
                    checkbox.disabled = false;
                });
                dropArea.classList.remove('disabled');
            }
            break;
        // 移除stopped状态处理
    }
    
    // 添加状态日志
    addStatusLog(message, status);
    
    // 更新队列状态
    updateQueueStatus();
});

// 接收系统消息
socket.on('system_message', (data) => {
    addStatusLog(data.message, 'system');
});

// ==============================
// 文件上传功能
// ==============================

// 获取DOM元素
const dropArea = document.getElementById('dropArea');
const fileInput = document.getElementById('fileInput');
const startTranscriptionBtn = document.getElementById('startTranscriptionBtn');
const clearLogsBtn = document.getElementById('clearLogsBtn');

// 阻止默认拖拽行为
['dragenter', 'dragover', 'dragleave', 'drop'].forEach(eventName => {
    dropArea.addEventListener(eventName, preventDefaults, false);
});

function preventDefaults(e) {
    e.preventDefault();
    e.stopPropagation();
}

// 拖拽高亮处理
['dragenter', 'dragover'].forEach(eventName => {
    dropArea.addEventListener(eventName, highlight, false);
});

['dragleave', 'drop'].forEach(eventName => {
    dropArea.addEventListener(eventName, unhighlight, false);
});

function highlight() {
    dropArea.style.borderColor = '#667eea';
    dropArea.style.backgroundColor = '#f0f5ff';
}

function unhighlight() {
    dropArea.style.borderColor = '#ccc';
    dropArea.style.backgroundColor = '';
}

// 文件拖拽上传处理
dropArea.addEventListener('drop', handleDrop, false);

function handleDrop(e) {
    e.preventDefault();
    e.stopPropagation();
    
    const dt = e.dataTransfer;
    const files = dt.files;
    if (files.length > 0) {
        // 为拖拽区域添加图标显示文件名
        const dropAreaContent = dropArea.querySelector('p:first-of-type');
        if (dropAreaContent) {
            const fileNames = Array.from(files).map(file => file.name).join(', ');
            dropAreaContent.innerHTML = `
                <i class="fas fa-check-circle text-success"></i> 
                ${fileNames}
            `;
        }
        handleFiles(files);
    }
}

// 点击选择文件
dropArea.addEventListener('click', () => {
    fileInput.click();
});

// 文件选择后处理
fileInput.addEventListener('change', function() {
    const files = this.files;
    if (files.length > 0) {
        // 为拖拽区域添加图标显示文件名
        const dropAreaContent = dropArea.querySelector('p:first-of-type');
        if (dropAreaContent) {
            const fileNames = Array.from(files).map(file => file.name).join(', ');
            dropAreaContent.innerHTML = `
                <i class="fas fa-check-circle text-success"></i> 
                ${fileNames}
            `;
        }
        handleFiles(this.files);
    }
});

// 处理文件上传
function handleFiles(files) {
    // 创建FormData对象
    const formData = new FormData();
    for (let i = 0; i < files.length; i++) {
        formData.append('files', files[i]);
    }
    
    // 显示上传状态
    showUploadProgress('文件上传中...');
    
    // 发送请求
    fetch('/upload', {
        method: 'POST',
        body: formData
    })
    .then(response => response.json())
    .then(data => {
        if (data.status === 'success') {
            addStatusLog(data.message, 'success');
            // 动态更新文件列表而不是刷新页面
        updateUploadedFilesList(data.uploaded_files || [], data.files || []);
        // 重新获取文件列表以确保同步
        refreshUploadedFilesList();
        } else {
            addStatusLog('上传失败: ' + (data.error || '未知错误'), 'error');
        }
    })
    .catch(error => {
        console.error('Error:', error);
        addStatusLog('上传过程中出现错误: ' + error.message, 'error');
    })
    .finally(() => {
        // 隐藏进度条
        setTimeout(hideProgress, 2000);
    });
}

// ==============================
// 文件管理功能
// ==============================

// 下载文件
function downloadFile(filename) {
    window.location.href = '/download/' + encodeURIComponent(filename);
}

// 播放音频文件
function playFile(filename) {
    console.log('Playing file:', filename);
    const modalAudioPlayer = document.getElementById('modalAudioPlayer');
    const modal = new bootstrap.Modal(document.getElementById('audioPlayerModal'));
    const currentFileName = document.getElementById('currentFileName');
    
    if (modalAudioPlayer && currentFileName) {
        // 停止当前播放
        modalAudioPlayer.pause();
        modalAudioPlayer.currentTime = 0;
        
        // 设置文件名
        currentFileName.textContent = filename;
        
        // 设置音频源
        modalAudioPlayer.src = `/play/${filename}`;
        
        // 重置播放器状态
        resetPlayerState();
        
        // 显示模态框
        modal.show();
        
        // 加载音频并自动播放
        modalAudioPlayer.load();
        
        // 监听加载完成事件，自动开始播放
        modalAudioPlayer.addEventListener('loadeddata', function() {
            modalAudioPlayer.play().then(() => {
                // 更新播放按钮状态
                const playStopIcon = document.getElementById('playStopIcon');
                if (playStopIcon) {
                    playStopIcon.className = 'fas fa-stop';
                }
            }).catch(error => {
                console.log('自动播放失败，可能需要用户交互:', error);
            });
        }, { once: true });
        
    } else {
        console.error('Modal audio player elements not found');
    }
}

// 播放音频文件（别名函数，用于HTML调用）
function playAudio(filename) {
    playFile(filename);
}

// 关闭播放器
function closePlayer() {
    const modalAudioPlayer = document.getElementById('modalAudioPlayer');
    
    if (modalAudioPlayer) {
        modalAudioPlayer.pause();
        modalAudioPlayer.src = '';
    }
    
    // 模态框会自动关闭，不需要手动处理
}

// 重置播放器状态
function resetPlayerState() {
    const playStopIcon = document.getElementById('playStopIcon');
    const progressFill = document.getElementById('progressFill');
    const currentTimeSpan = document.getElementById('currentTime');
    
    if (playStopIcon) {
        playStopIcon.className = 'fas fa-play';
    }
    
    if (progressFill) {
        progressFill.style.width = '0%';
    }
    
    if (currentTimeSpan) {
        currentTimeSpan.textContent = '00:00';
    }
}

// 更新总时长
function updateTotalTime() {
    const modalAudioPlayer = document.getElementById('modalAudioPlayer');
    const totalTimeSpan = document.getElementById('totalTime');
    
    if (modalAudioPlayer && totalTimeSpan && !isNaN(modalAudioPlayer.duration)) {
        totalTimeSpan.textContent = formatTime(modalAudioPlayer.duration);
    }
}

// 格式化时间
function formatTime(seconds) {
    const mins = Math.floor(seconds / 60);
    const secs = Math.floor(seconds % 60);
    return `${mins}:${secs.toString().padStart(2, '0')}`;
}

// 播放/停止控制（合并按钮）
function togglePlayStop() {
    const modalAudioPlayer = document.getElementById('modalAudioPlayer');
    const playStopIcon = document.getElementById('playStopIcon');
    
    if (modalAudioPlayer && playStopIcon) {
        if (modalAudioPlayer.paused || modalAudioPlayer.currentTime === 0) {
            // 当前是暂停状态或已停止，开始播放
            modalAudioPlayer.play();
            playStopIcon.className = 'fas fa-stop';
        } else {
            // 当前是播放状态，停止播放
            modalAudioPlayer.pause();
            modalAudioPlayer.currentTime = 0;
            playStopIcon.className = 'fas fa-play';
            
            // 重置进度条和时间显示
            const progressFill = document.getElementById('progressFill');
            const currentTimeSpan = document.getElementById('currentTime');
            
            if (progressFill) {
                progressFill.style.width = '0%';
            }
            
            if (currentTimeSpan) {
                currentTimeSpan.textContent = '00:00';
            }
        }
    }
}

// 保留原有的togglePlayPause函数以兼容其他可能的调用
function togglePlayPause() {
    togglePlayStop();
}

// 保留原有的stopAudio函数以兼容其他可能的调用
function stopAudio() {
    const modalAudioPlayer = document.getElementById('modalAudioPlayer');
    const playStopIcon = document.getElementById('playStopIcon');
    const progressFill = document.getElementById('progressFill');
    const currentTimeSpan = document.getElementById('currentTime');
    
    if (modalAudioPlayer) {
        modalAudioPlayer.pause();
        modalAudioPlayer.currentTime = 0;
        
        if (playStopIcon) {
            playStopIcon.className = 'fas fa-play';
        }
        
        if (progressFill) {
            progressFill.style.width = '0%';
        }
        
        if (currentTimeSpan) {
            currentTimeSpan.textContent = '00:00';
        }
    }
}

// 进度条点击跳转
function seekToPosition(event) {
    const modalAudioPlayer = document.getElementById('modalAudioPlayer');
    const progressBar = document.getElementById('progressBar');
    
    if (modalAudioPlayer && progressBar && !isNaN(modalAudioPlayer.duration)) {
        const rect = progressBar.getBoundingClientRect();
        const clickX = event.clientX - rect.left;
        const percentage = clickX / rect.width;
        const seekTime = percentage * modalAudioPlayer.duration;
        modalAudioPlayer.currentTime = seekTime;
    }
}

// 音量控制
function changeVolume(event) {
    const modalAudioPlayer = document.getElementById('modalAudioPlayer');
    const volumeSlider = document.getElementById('volumeSlider');
    
    if (modalAudioPlayer && volumeSlider) {
        modalAudioPlayer.volume = volumeSlider.value / 100;
    }
}

// 初始化播放器事件监听
function initializeAudioPlayerEvents() {
    const modalAudioPlayer = document.getElementById('modalAudioPlayer');
    const progressBar = document.getElementById('progressBar');
    const progressFill = document.getElementById('progressFill');
    const currentTimeSpan = document.getElementById('currentTime');
    const playStopIcon = document.getElementById('playStopIcon');
    const audioPlayerModal = document.getElementById('audioPlayerModal');
    
    if (modalAudioPlayer) {
        // 时间更新事件
        modalAudioPlayer.addEventListener('timeupdate', function() {
            if (!isNaN(modalAudioPlayer.duration)) {
                const progress = (modalAudioPlayer.currentTime / modalAudioPlayer.duration) * 100;
                if (progressFill) {
                    progressFill.style.width = progress + '%';
                }
                if (currentTimeSpan) {
                    currentTimeSpan.textContent = formatTime(modalAudioPlayer.currentTime);
                }
            }
        });
        
        // 播放结束事件
        modalAudioPlayer.addEventListener('ended', function() {
            if (playStopIcon) {
                playStopIcon.className = 'fas fa-play';
            }
            if (progressFill) {
                progressFill.style.width = '0%';
            }
        });
        
        // 加载完成事件
        modalAudioPlayer.addEventListener('loadedmetadata', function() {
            updateTotalTime();
        });
    }
    
    // 进度条点击事件
    if (progressBar) {
        progressBar.addEventListener('click', seekToPosition);
    }
    
    // 模态框关闭时停止播放
    if (audioPlayerModal) {
        audioPlayerModal.addEventListener('hidden.bs.modal', function() {
            if (modalAudioPlayer) {
                modalAudioPlayer.pause();
                modalAudioPlayer.currentTime = 0;
                resetPlayerState();
            }
        });
    }
}

// 删除上传的文件
function deleteUploadedFile(filename) {
    fetch('/delete/' + encodeURIComponent(filename))
    .then(response => {
        if (response.ok) {
            // 直接从UI中移除文件项
            const uploadedItem = document.querySelector(`.uploaded-file-checkbox[value="${filename}"]`)?.closest('.list-group-item');
            if (uploadedItem) {
                uploadedItem.remove();
                addStatusLog('文件删除成功', 'success');
            } else {
                // 如果找不到直接匹配的项，刷新整个列表
                refreshUploadedFilesList();
            }
        } else {
            alert('删除失败');
        }
    })
    .catch(error => {
        console.error('Error:', error);
        alert('删除过程中出现错误');
    });
}

// 删除输出的文件
function deleteOutputFile(filename) {
    fetch('/delete_output/' + encodeURIComponent(filename))
    .then(response => {
        if (response.ok) {
            // 直接从UI中移除文件项
            const outputItem = document.querySelector(`.output-file-checkbox[value="${filename}"]`)?.closest('.list-group-item');
            if (outputItem) {
                outputItem.remove();
                addStatusLog('输出文件删除成功', 'success');
            } else {
                // 如果找不到直接匹配的项，刷新整个列表
                refreshOutputFilesList();
            }
        } else {
            alert('删除失败');
        }
    })
    .catch(error => {
        console.error('Error:', error);
        alert('删除过程中出现错误');
    });
}

// ==============================
// 转录控制功能
// ==============================

// 启动转录
function startTranscription() {
    // 获取选中的文件
    const selectedFiles = [];
    document.querySelectorAll('.uploaded-file-checkbox:checked').forEach(checkbox => {
        selectedFiles.push(checkbox.value);
    });
    
    if (selectedFiles.length === 0) {
        alert('请在上传的文件中选择要转录的文件');
        return;
    }
    
    // 获取设置
    const gpuSelector = document.getElementById('gpuSelector');
    const modelSelector = document.getElementById('modelSelector');
    const languageSelector = document.getElementById('languageSelector');
    
    const data = {
        files: selectedFiles,
        gpus: [gpuSelector.value],
        model: modelSelector.value,
        language: languageSelector.value
    };
    
    // 显示进度
    showUploadProgress('正在提交转录任务...');
    
    // 发送请求
    fetch('/add_to_queue', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify(data)
    })
    .then(response => response.json())
    .then(data => {
        if (data.status === 'success') {
            addStatusLog(data.message, 'success');
            
            // 设置当前任务状态
            isTranscribing = true;
            
            // 更新按钮状态
            startTranscriptionBtn.disabled = true;
            
            // 禁用文件选择和上传
            document.querySelectorAll('.uploaded-file-checkbox').forEach(checkbox => {
                checkbox.disabled = true;
            });
            dropArea.classList.add('disabled');
            
            // 清除内存警告显示
            const memoryStatus = document.getElementById('gpuMemoryStatus');
            if (memoryStatus) {
                memoryStatus.style.display = 'none';
            }
        } else if (data.status === 'memory_insufficient') {
            // 处理内存不足的情况
            const message = data.message || '显存不足，无法开始转录';
            const insufficientGpus = data.insufficient_gpus || [];
            const recommendedModels = data.recommended_models || [];
            
            let warningHtml = `<div class="alert alert-danger" role="alert">`;
            warningHtml += `<h6><i class="fas fa-exclamation-triangle"></i> ${message}</h6>`;
            
            if (insufficientGpus.length > 0) {
                warningHtml += `<p><strong>显存不足的GPU:</strong> ${insufficientGpus.join(', ')}</p>`;
            }
            
            if (recommendedModels.length > 0) {
                warningHtml += `<p><strong>建议使用的模型:</strong> ${recommendedModels.join(', ')}</p>`;
                warningHtml += `<p class="mb-0">请选择较小的模型或等待当前任务完成后再试。</p>`;
            }
            
            warningHtml += `</div>`;
            
            // 显示内存警告
            const memoryInfo = document.getElementById('memoryInfo');
            const memoryStatus = document.getElementById('gpuMemoryStatus');
            if (memoryInfo && memoryStatus) {
                memoryInfo.innerHTML = warningHtml;
                memoryStatus.style.display = 'block';
            }
            
            addStatusLog(message, 'error');
        } else {
            addStatusLog('提交转录任务失败: ' + (data.error || '未知错误'), 'error');
        }
    })
    .catch(error => {
        console.error('Error:', error);
        addStatusLog('提交转录任务过程中出现错误: ' + error.message, 'error');
    })
    .finally(() => {
        setTimeout(hideProgress, 2000);
    });
}

// 停止转录
// 停止转录功能已移除

// ==============================
// GPU内存管理函数
// ==============================

// 获取GPU内存信息
function fetchGpuMemoryInfo() {
    fetch('/api/gpu_memory')
        .then(response => response.json())
        .then(data => {
            if (data.status === 'success') {
                // 更新数据结构以匹配新的API响应
                gpuMemoryInfo = {
                    gpu_memory: {}
                };
                
                // 转换新的GPU信息格式
                if (data.gpu_info && data.gpu_info.available && data.gpu_info.gpus) {
                    for (const [gpuId, gpuData] of Object.entries(data.gpu_info.gpus)) {
                        gpuMemoryInfo.gpu_memory[gpuId] = {
                            used: gpuData.reserved * 1024, // 转换为MB
                            total: gpuData.total * 1024,   // 转换为MB
                            free: gpuData.free * 1024,     // 转换为MB
                            gpu_utilization: gpuData.gpu_utilization,
                            memory_utilization: gpuData.memory_utilization,
                            temperature: gpuData.temperature
                        };
                    }
                }
                
                updateGpuMemoryDisplay();
            }
        })
        .catch(error => {
            console.error('获取GPU内存信息失败:', error);
        });
}

// 更新GPU内存显示
function updateGpuMemoryDisplay() {
    const gpuSelector = document.getElementById('gpuSelector');
    const memoryInfo = document.getElementById('memoryInfo');
    const memoryStatus = document.getElementById('gpuMemoryStatus');
    const headerGpuMemory = document.getElementById('headerGpuMemory');
    
    if (!gpuSelector || !memoryInfo || !memoryStatus) return;
    
    const selectedGpu = gpuSelector.value;
    
    if (!selectedGpu || !gpuMemoryInfo.gpu_memory) {
        memoryStatus.style.display = 'none';
        if (headerGpuMemory) {
            headerGpuMemory.textContent = '无GPU信息';
        }
        return;
    }
    
    const gpuData = gpuMemoryInfo.gpu_memory[selectedGpu];
    if (!gpuData) {
        memoryStatus.style.display = 'none';
        if (headerGpuMemory) {
            headerGpuMemory.textContent = '无GPU信息';
        }
        return;
    }
    
    const usedGB = (gpuData.used / 1024).toFixed(1);
    const totalGB = (gpuData.total / 1024).toFixed(1);
    const freeGB = (gpuData.free / 1024).toFixed(1);
    const usagePercent = ((gpuData.used / gpuData.total) * 100).toFixed(1);
    
    let statusClass = 'text-success';
    if (usagePercent > 80) statusClass = 'text-danger';
    else if (usagePercent > 60) statusClass = 'text-warning';
    
    // GPU使用率信息
    const gpuUtilization = gpuData.gpu_utilization !== null && gpuData.gpu_utilization !== undefined ? gpuData.gpu_utilization : 'N/A';
    const memoryUtilization = gpuData.memory_utilization !== null && gpuData.memory_utilization !== undefined ? gpuData.memory_utilization : 'N/A';
    const temperature = gpuData.temperature !== null && gpuData.temperature !== undefined ? gpuData.temperature : 'N/A';
    
    // 根据GPU使用率调整状态颜色
    let utilizationClass = 'text-success';
    if (gpuUtilization !== 'N/A') {
        if (gpuUtilization > 80) utilizationClass = 'text-danger';
        else if (gpuUtilization > 60) utilizationClass = 'text-warning';
    }
    
    memoryInfo.innerHTML = `
        <div class="${statusClass}">
            <i class="fas fa-memory"></i> GPU ${selectedGpu}: ${usedGB}GB / ${totalGB}GB (${usagePercent}%)
            <br><small>可用: ${freeGB}GB</small>
        </div>
        <div class="${utilizationClass} mt-1">
            <i class="fas fa-microchip"></i> GPU使用率: ${gpuUtilization}${gpuUtilization !== 'N/A' ? '%' : ''}
            <br><small>显存使用率: ${memoryUtilization}${memoryUtilization !== 'N/A' ? '%' : ''}</small>
            ${temperature !== 'N/A' ? `<br><small><i class="fas fa-thermometer-half"></i> 温度: ${temperature}°C</small>` : ''}
        </div>
    `;
    
    // 更新页面头部的GPU信息
    if (headerGpuMemory) {
        const utilizationText = gpuUtilization !== 'N/A' ? ` | ${gpuUtilization}%` : '';
        headerGpuMemory.innerHTML = `<span class="${statusClass}">${usedGB}/${totalGB}GB (${usagePercent}%)${utilizationText}</span>`;
    }
    
    memoryStatus.style.display = 'block';
}

// 检查模型内存需求
function checkModelMemoryRequirement() {
    const gpuSelector = document.getElementById('gpuSelector');
    const modelSelector = document.getElementById('modelSelector');
    
    if (!gpuSelector || !modelSelector) return;
    
    const selectedGpu = gpuSelector.value;
    const selectedModel = modelSelector.value;
    
    if (!selectedGpu || !selectedModel) return;
    
    fetch(`/api/check_memory/${selectedModel}?gpu_ids=${selectedGpu}`)
        .then(response => response.json())
        .then(data => {
            const memoryInfo = document.getElementById('memoryInfo');
            const memoryStatus = document.getElementById('gpuMemoryStatus');
            
            if (data.status === 'insufficient') {
                let warningHtml = `<div class="alert alert-warning" role="alert">`;
                warningHtml += `<h6><i class="fas fa-exclamation-triangle"></i> ${data.message}</h6>`;
                
                if (data.insufficient_gpus && data.insufficient_gpus.length > 0) {
                    warningHtml += `<p><strong>显存不足的GPU:</strong> ${data.insufficient_gpus.join(', ')}</p>`;
                }
                
                if (data.recommended_models && data.recommended_models.length > 0) {
                    warningHtml += `<p><strong>建议使用的模型:</strong> ${data.recommended_models.join(', ')}</p>`;
                }
                
                warningHtml += `</div>`;
                memoryInfo.innerHTML = warningHtml;
                memoryStatus.style.display = 'block';
            } else {
                updateGpuMemoryDisplay();
            }
        })
        .catch(error => {
            console.error('检查模型内存需求失败:', error);
        });
}

// ==============================
// UI功能函数
// ==============================

// 添加状态日志
function addStatusLog(message, type = 'info') {
    const logsContainer = document.getElementById('statusLogs');
    if (!logsContainer) return;
    
    const logEntry = document.createElement('div');
    logEntry.className = `log-entry ${type}`;
    
    const timestamp = new Date().toLocaleTimeString();
    logEntry.innerHTML = `
        <span class="log-timestamp">[${timestamp}]</span>
        <span class="log-message">${message}</span>
    `;
    
    logsContainer.prepend(logEntry);
    
    // 自动滚动到最新日志
    logsContainer.scrollTop = 0;
    
    // 限制日志数量
    const maxLogs = 100;
    if (logsContainer.children.length > maxLogs) {
        logsContainer.removeChild(logsContainer.lastChild);
    }
}

// 添加队列项
function addQueueItem(taskId, filename, status, message, position) {
    const queueContainer = document.getElementById('queueItems');
    if (!queueContainer) return;
    
    const queueItem = document.createElement('div');
    queueItem.id = `queue-item-${taskId}`;
    queueItem.className = `queue-item ${status}`;
    
    queueItem.innerHTML = `
        <div class="queue-item-header">
            <span class="filename">${filename}</span>
            <span class="status-badge badge ${getStatusBadgeClass(status)}">${getStatusText(status)}</span>
        </div>
        <div class="queue-item-body">
            <div class="message">${message}</div>
            <div class="progress-container" id="progress-container-${taskId}" style="display: none;">
                <div class="progress-bar">
                    <div class="progress-fill" id="progress-fill-${taskId}" style="width: 0%;"></div>
                </div>
                <div class="progress-text" id="progress-text-${taskId}">0%</div>
            </div>
            <div class="timer" id="timer-${taskId}">--:--</div>
        </div>
    `;
    
    queueContainer.appendChild(queueItem);
    queueItems[taskId] = {
        element: queueItem,
        timer: null
    };
    
    updateQueueStatus();
}

// 更新队列项
function updateQueueItem(taskId, status, message, progress = 0) {
    const queueItem = queueItems[taskId];
    if (!queueItem) return;
    
    const element = queueItem.element;
    element.className = `queue-item ${status}`;
    
    // 更新状态徽章
    const badge = element.querySelector('.status-badge');
    if (badge) {
        badge.className = `status-badge badge ${getStatusBadgeClass(status)}`;
        badge.textContent = getStatusText(status);
    }
    
    // 更新消息
    const msgElement = element.querySelector('.message');
    if (msgElement) {
        msgElement.textContent = message;
    }
    
    // 更新进度条
    const progressContainer = document.getElementById(`progress-container-${taskId}`);
    const progressFill = document.getElementById(`progress-fill-${taskId}`);
    const progressText = document.getElementById(`progress-text-${taskId}`);
    
    if (status === 'processing' && progress > 0) {
        // 显示进度条
        if (progressContainer) progressContainer.style.display = 'block';
        if (progressFill) progressFill.style.width = `${progress}%`;
        if (progressText) progressText.textContent = `${progress}%`;
    } else {
        // 隐藏进度条
        if (progressContainer) progressContainer.style.display = 'none';
    }
    
    updateQueueStatus();
}

// 启动任务计时器
function startTaskTimer(taskId, initialElapsedSeconds = 0) {
    if (queueItems[taskId] && !queueItems[taskId].timer) {
        const startTime = Date.now() - (initialElapsedSeconds * 1000);
        
        // 立即更新一次显示
        const updateTimer = () => {
            const elapsed = Math.floor((Date.now() - startTime) / 1000);
            const mins = Math.floor(elapsed / 60).toString().padStart(2, '0');
            const secs = (elapsed % 60).toString().padStart(2, '0');
            
            const timerElement = document.getElementById(`timer-${taskId}`);
            if (timerElement) {
                timerElement.textContent = `${mins}:${secs}`;
            }
        };
        
        // 立即执行一次
        updateTimer();
        
        // 设置定时器
        queueItems[taskId].timer = setInterval(updateTimer, 1000);
    }
}

// 停止任务计时器
function stopTaskTimer(taskId) {
    if (queueItems[taskId] && queueItems[taskId].timer) {
        clearInterval(queueItems[taskId].timer);
        queueItems[taskId].timer = null;
    }
}

// 更新队列状态
function updateQueueStatus() {
    const queueInfo = document.getElementById('queueInfo');
    const queueBadge = document.getElementById('queueBadge');
    
    if (!queueInfo) return;
    
    const items = document.querySelectorAll('.queue-item');
    const processing = document.querySelectorAll('.queue-item.processing').length;
    const queued = document.querySelectorAll('.queue-item.queued').length;
    
    // 更新队列徽章
    if (queueBadge) {
        queueBadge.textContent = processing + queued;
        queueBadge.className = 'badge ' + (processing > 0 ? 'bg-warning' : queued > 0 ? 'bg-info' : 'bg-success');
    }
    
    if (processing > 0) {
        queueInfo.textContent = `正在处理 (${processing}个进行中, ${queued}个等待中)`;
        queueInfo.className = 'text-warning';
    } else if (queued > 0) {
        queueInfo.textContent = `等待中 (${queued}个任务)`;
        queueInfo.className = 'text-info';
    } else {
        queueInfo.textContent = '空闲';
        queueInfo.className = 'text-success';
    }
}

// 辅助函数：获取状态徽章类
function getStatusBadgeClass(status) {
    switch(status) {
        case 'processing': return 'bg-warning';
        case 'completed': return 'bg-success';
        case 'failed': return 'bg-danger';
        case 'queued': return 'bg-info';
        case 'stopped': return 'bg-secondary';
        default: return 'bg-secondary';
    }
}

// 辅助函数：获取状态文本
function getStatusText(status) {
    switch(status) {
        case 'processing': return '处理中';
        case 'completed': return '已完成';
        case 'failed': return '失败';
        case 'queued': return '排队中';
        case 'stopped': return '已停止';
        default: return status;
    }
}

// 显示上传进度
function showUploadProgress(message) {
    hideProgress(); // 先移除旧的进度条
    
    const progressContainer = document.createElement('div');
    progressContainer.className = 'upload-progress';
    progressContainer.id = 'uploadProgress';
    progressContainer.innerHTML = `
        <div class="upload-status">${message}</div>
        <div class="progress mt-2">
            <div class="progress-bar progress-bar-striped progress-bar-animated" role="progressbar" style="width: 0%"></div>
        </div>
    `;
    
    // 将进度条插入到表单下方
    const form = document.getElementById('uploadForm');
    form.parentNode.insertBefore(progressContainer, form.nextSibling);
    
    // 模拟进度更新
    let progress = 0;
    const progressBar = progressContainer.querySelector('.progress-bar');
    const interval = setInterval(() => {
        progress += 5;
        if (progress <= 95) {
            progressBar.style.width = `${progress}%`;
        } else {
            clearInterval(interval);
        }
    }, 200);
}

// 隐藏进度条
function hideProgress() {
    const progressContainer = document.getElementById('uploadProgress');
    if (progressContainer) {
        progressContainer.remove();
    }
}

// ==============================
// 页面加载完成后初始化
// ==============================
document.addEventListener('DOMContentLoaded', function() {
    // 初始化状态日志容器
    const logsContainer = document.getElementById('statusLogs');
    if (logsContainer) {
        addStatusLog('系统已启动，等待任务...', 'system');
    }
    
    // 绑定转录按钮事件
    if (startTranscriptionBtn) {
        startTranscriptionBtn.addEventListener('click', function(e) {
            e.preventDefault();
            startTranscription();
        });
    }
    
    // 停止转录按钮已移除
    
    // 绑定清除日志按钮事件
    if (clearLogsBtn) {
        clearLogsBtn.addEventListener('click', () => {
            const logsContainer = document.getElementById('statusLogs');
            if (logsContainer) {
                logsContainer.innerHTML = '';
                addStatusLog('日志已清除', 'system');
            }
        });
    }
    
    // 绑定GPU选择器事件
    const gpuSelector = document.getElementById('gpuSelector');
    if (gpuSelector) {
        gpuSelector.addEventListener('change', function() {
            fetchGpuMemoryInfo();
            checkModelMemoryRequirement();
        });
    }
    
    // 绑定模型选择器事件
    const modelSelector = document.getElementById('modelSelector');
    if (modelSelector) {
        modelSelector.addEventListener('change', function() {
            checkModelMemoryRequirement();
        });
    }
    
    // 初始化GPU内存信息（仅在页面加载时调用一次）
    fetchGpuMemoryInfo();
    
    // 绑定全选和批量删除按钮事件
    const selectAllUploadedBtn = document.getElementById('selectAllUploaded');
    const deleteSelectedUploadedBtn = document.getElementById('deleteSelectedUploaded');
    const selectAllOutputBtn = document.getElementById('selectAllOutput');
    const deleteSelectedOutputBtn = document.getElementById('deleteSelectedOutput');
    
    if (selectAllUploadedBtn) {
        selectAllUploadedBtn.addEventListener('click', selectAllUploadedFiles);
    }
    if (deleteSelectedUploadedBtn) {
        deleteSelectedUploadedBtn.addEventListener('click', deleteSelectedUploadedFiles);
    }
    if (selectAllOutputBtn) {
        selectAllOutputBtn.addEventListener('click', selectAllOutputFiles);
    }
    if (deleteSelectedOutputBtn) {
        deleteSelectedOutputBtn.addEventListener('click', deleteSelectedOutputFiles);
    }
    
    // 初始化音频播放器事件
    initializeAudioPlayerEvents();
    
    // 绑定README按钮事件
    const readmeBtn = document.getElementById('readmeBtn');
    if (readmeBtn) {
        readmeBtn.addEventListener('click', showReadmeModal);
    }
    
    // 绑定版本按钮事件
    const versionBtn = document.getElementById('versionBtn');
    if (versionBtn) {
        versionBtn.addEventListener('click', showVersionModal);
    }
    
    // 初始化版本信息
    fetchVersionInfo();
    
    // 检查转录状态并恢复UI状态
    checkTranscriptionStatus();
    
    // 获取上传文件列表并恢复选择框状态
    fetch('/api/uploaded_files')
        .then(response => response.json())
        .then(data => {
            if (data.status === 'success' && data.files) {
                updateUploadedFilesList(data.files);
            }
        })
        .catch(error => {
            console.error('Error loading uploaded files:', error);
        });
    
    // 获取输出文件列表
    refreshOutputFilesList();
    
    // 获取当前队列状态
    fetch('/api/status')
        .then(response => response.json())
        .then(data => {
            if (data.status === 'success') {
                // 更新队列状态
                const queueInfo = document.getElementById('queueInfo');
                if (queueInfo) {
                    if (data.active_tasks > 0) {
                        queueInfo.textContent = `正在处理 (${data.active_tasks}个进行中, ${data.queued_tasks}个等待中)`;
                        queueInfo.className = 'text-warning';
                    } else if (data.queued_tasks > 0) {
                        queueInfo.textContent = `等待中 (${data.queued_tasks}个任务)`;
                        queueInfo.className = 'text-info';
                    }
                }
                
                // 更新队列徽章
                const queueBadge = document.getElementById('queueBadge');
                if (queueBadge) {
                    queueBadge.textContent = data.active_tasks + data.queued_tasks;
                }
            }
        });
});

// 全选上传文件
function selectAllUploadedFiles() {
    const checkboxes = document.querySelectorAll('.uploaded-file-checkbox');
    const allChecked = Array.from(checkboxes).every(cb => cb.checked);
    checkboxes.forEach(cb => cb.checked = !allChecked);
}

// 删除选中的上传文件
function deleteSelectedUploadedFiles() {
    const checkboxes = document.querySelectorAll('.uploaded-file-checkbox:checked');
    if (checkboxes.length === 0) {
        alert('请选择要删除的文件');
        return;
    }
    
    if (confirm(`确定要删除选中的 ${checkboxes.length} 个文件吗？`)) {
        Promise.all(Array.from(checkboxes).map(cb => 
            fetch('/delete/' + encodeURIComponent(cb.value))
        ))
        .then(() => {
            fetch('/api/uploaded_files')
            .then(response => response.json())
            .then(data => {
                if (data.status === 'success') {
                    updateUploadedFilesList(data.files || []);
                    addStatusLog('批量删除成功', 'success');
                }
            });
        })
        .catch(error => {
            console.error('Error:', error);
            addStatusLog('批量删除失败', 'error');
        });
    }
}

// 全选输出文件
function selectAllOutputFiles() {
    const checkboxes = document.querySelectorAll('.output-file-checkbox');
    const allChecked = Array.from(checkboxes).every(cb => cb.checked);
    checkboxes.forEach(cb => cb.checked = !allChecked);
}

// 删除选中的输出文件
function deleteSelectedOutputFiles() {
    const checkboxes = document.querySelectorAll('.output-file-checkbox:checked');
    if (checkboxes.length === 0) {
        alert('请选择要删除的文件');
        return;
    }
    
    if (!confirm(`确定要删除选中的 ${checkboxes.length} 个文件吗？`)) {
        return;
    }
    
    Promise.all(Array.from(checkboxes).map(cb => 
        fetch('/delete_output/' + encodeURIComponent(cb.value))
    ))
    .then(() => {
        refreshOutputFilesList();
        addStatusLog('批量删除成功', 'success');
    })
    .catch(error => {
        console.error('Error:', error);
        addStatusLog('批量删除失败', 'error');
    });
}

// 动态更新上传文件列表
function updateUploadedFilesList(uploadedFiles, newFiles = []) {
    const filesList = document.getElementById('uploadedFilesList');
    if (!filesList) return;
    
    // 获取当前已选中的文件
    const currentSelected = Array.from(document.querySelectorAll('.uploaded-file-checkbox:checked')).map(cb => cb.value);
    
    // 清空当前列表
    filesList.innerHTML = '';
    
    if (uploadedFiles.length === 0) {
        filesList.innerHTML = `
            <div class="text-center py-4">
                <i class="fas fa-inbox fa-2x text-muted mb-2"></i>
                <p class="text-muted">暂无上传的文件</p>
            </div>
        `;
        return;
    }
    
    // 重新生成文件列表
    uploadedFiles.forEach(file => {
        const fileName = typeof file === 'string' ? file : file.name;
        // 如果是新上传的文件或之前已选中的文件，则保持选中状态
        const isSelected = newFiles.includes(fileName) || currentSelected.includes(fileName);
        
        const fileItem = document.createElement('div');
        fileItem.className = 'list-group-item d-flex justify-content-between align-items-center';
        fileItem.innerHTML = `
            <div class="d-flex align-items-center">
                <input type="checkbox" class="form-check-input me-2 uploaded-file-checkbox" value="${fileName}" ${isSelected ? 'checked' : ''}>
                <i class="fas fa-file-audio text-primary me-2"></i>
                <span>${fileName}</span>
            </div>
            <div>
                <button class="btn btn-sm btn-outline-primary me-1" onclick="playAudio('${fileName}')">
                    <i class="fas fa-play"></i>
                </button>
                <button class="btn btn-sm btn-outline-danger" onclick="deleteUploadedFile('${fileName}')">
                    <i class="fas fa-trash"></i>
                </button>
            </div>
        `;
        filesList.appendChild(fileItem);
    });
    
    // 更新文件数量徽章
    const badge = document.querySelector('.card-header .badge');
    if (badge) {
        badge.textContent = uploadedFiles.length;
    }
}

// 刷新输出文件列表
function refreshOutputFilesList() {
    fetch('/api/output_files')
        .then(response => response.json())
        .then(data => {
            updateOutputFilesList(data.files);
        })
        .catch(error => {
            console.error('Error refreshing output files list:', error);
        });
}

// 更新输出文件列表
function updateOutputFilesList(outputFiles) {
    const filesList = document.getElementById('outputFilesList');
    if (!filesList) return;
    
    // 清空当前列表
    filesList.innerHTML = '';
    
    if (outputFiles.length === 0) {
        filesList.innerHTML = `
            <div class="text-center py-4">
                <i class="fas fa-inbox fa-2x text-muted mb-2"></i>
                <p class="text-muted">暂无转录结果</p>
            </div>
        `;
        return;
    }
    
    // 重新生成文件列表
    outputFiles.forEach(file => {
        const fileName = typeof file === 'string' ? file : file.name;
        
        const fileItem = document.createElement('div');
        fileItem.className = 'list-group-item d-flex justify-content-between align-items-center';
        fileItem.innerHTML = `
            <div class="d-flex align-items-center">
                <input type="checkbox" class="form-check-input me-2 output-file-checkbox" value="${fileName}">
                <i class="fas fa-file-text text-success me-2"></i>
                <span>${fileName}</span>
            </div>
            <div>
                <button class="btn btn-sm btn-outline-primary me-1" onclick="downloadFile('${fileName}')">
                    <i class="fas fa-download"></i>
                </button>
                <button class="btn btn-sm btn-outline-danger" onclick="deleteOutputFile('${fileName}')">
                    <i class="fas fa-trash"></i>
                </button>
            </div>
        `;
        filesList.appendChild(fileItem);
    });
    
    // 更新文件数量徽章
    const badge = document.querySelector('#outputFiles .card-header .badge');
    if (badge) {
        badge.textContent = outputFiles.length;
    }
}

// 检查转录状态
function checkTranscriptionStatus() {
    fetch('/api/status')
        .then(response => response.json())
        .then(data => {
            // 检查是否有活动的转录任务（从queue中查找processing状态的任务）
            const activeTask = data.queue && data.queue.find(task => task.status === 'processing');
            if (activeTask) {
                currentTaskId = activeTask.task_id;
                isTranscribing = true;
                
                // 更新按钮状态
                if (startTranscriptionBtn) {
                    startTranscriptionBtn.disabled = true;
                }
                
                // 禁用文件选择和上传
                document.querySelectorAll('.uploaded-file-checkbox').forEach(checkbox => {
                    checkbox.disabled = true;
                });
                dropArea.classList.add('disabled');
                
                addStatusLog('检测到正在进行的转录任务', 'info');
            } else {
                // 没有活动任务时，恢复正常状态
                currentTaskId = null;
                isTranscribing = false;
                
                // 恢复按钮状态
                if (startTranscriptionBtn) {
                    startTranscriptionBtn.disabled = false;
                }
                
                // 启用文件选择和上传
                document.querySelectorAll('.uploaded-file-checkbox').forEach(checkbox => {
                    checkbox.disabled = false;
                });
                dropArea.classList.remove('disabled');
            }
            
            // 检查队列中的任务
            if (data.queue && data.queue.length > 0) {
                // 清空现有队列显示，避免重复
                const queueContainer = document.getElementById('queueItems');
                if (queueContainer) {
                    // 停止所有现有的计时器
                    Object.keys(queueItems).forEach(taskId => {
                        stopTaskTimer(taskId);
                    });
                    // 清空队列容器和记录
                    queueContainer.innerHTML = '';
                    queueItems = {};
                }
                
                data.queue.forEach((task, index) => {
                    // 为队列中的任务生成task_id（如果没有的话）
                    const taskId = task.task_id || `queue_${index}_${Date.now()}`;
                    const status = task.status || 'queued';
                    const message = status === 'processing' ? `开始转录: ${task.filename}` : '等待处理中...';
                    addQueueItem(taskId, task.filename, status, message, task.position);
                    
                    // 如果是正在处理的任务，启动计时器
                    if (status === 'processing') {
                        // 如果有已经过的时间，从该时间开始计时
                        const elapsedSeconds = task.elapsed_seconds || 0;
                        startTaskTimer(taskId, elapsedSeconds);
                    }
                });
            } else {
                // 如果没有队列任务，清空显示
                const queueContainer = document.getElementById('queueItems');
                if (queueContainer) {
                    Object.keys(queueItems).forEach(taskId => {
                        stopTaskTimer(taskId);
                    });
                    queueContainer.innerHTML = '';
                    queueItems = {};
                }
            }
        })
        .catch(error => {
            console.error('Error checking transcription status:', error);
        });
}

function showReadmeModal() {
    const readmeModalElement = document.getElementById('readmeModal');
    const readmeModal = new bootstrap.Modal(readmeModalElement);
    const readmeContent = document.getElementById('readmeContent');
    
    // 显示加载状态
    readmeContent.innerHTML = `
        <div class="text-center py-4">
            <div class="spinner-border text-primary" role="status">
                <span class="visually-hidden">加载中...</span>
            </div>
            <p class="mt-2">正在加载README内容...</p>
        </div>
    `;
    
    // 添加modal关闭事件监听器，确保移除backdrop
    readmeModalElement.addEventListener('hidden.bs.modal', function() {
        // 确保移除所有backdrop
        const backdrops = document.querySelectorAll('.modal-backdrop');
        backdrops.forEach(backdrop => backdrop.remove());
        // 恢复body的overflow
        document.body.style.overflow = '';
        document.body.classList.remove('modal-open');
    }, { once: true });
    
    // 显示模态框
    readmeModal.show();
    
    // 获取README内容
    fetch('/api/readme')
        .then(response => response.json())
        .then(data => {
            if (data.status === 'success') {
                // 将Markdown转换为HTML并显示
                readmeContent.innerHTML = convertMarkdownToHtml(data.content);
            } else {
                readmeContent.innerHTML = `
                    <div class="alert alert-warning" role="alert">
                        <i class="fas fa-exclamation-triangle"></i>
                        ${data.message || 'README文件未找到'}
                    </div>
                `;
            }
        })
        .catch(error => {
            console.error('Error loading README:', error);
            readmeContent.innerHTML = `
                <div class="alert alert-danger" role="alert">
                    <i class="fas fa-times-circle"></i>
                    加载README失败: ${error.message}
                </div>
            `;
        });
}

function convertMarkdownToHtml(markdown) {
    // 简单的Markdown到HTML转换
    let html = markdown
        // 标题
        .replace(/^### (.*$)/gim, '<h3>$1</h3>')
        .replace(/^## (.*$)/gim, '<h2>$1</h2>')
        .replace(/^# (.*$)/gim, '<h1>$1</h1>')
        // 粗体
        .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
        // 斜体
        .replace(/\*(.*?)\*/g, '<em>$1</em>')
        // 代码块
        .replace(/```([\s\S]*?)```/g, '<pre><code>$1</code></pre>')
        // 行内代码
        .replace(/`(.*?)`/g, '<code>$1</code>')
        // 链接
        .replace(/\[([^\]]+)\]\(([^\)]+)\)/g, '<a href="$2" target="_blank">$1</a>')
        // 列表项
        .replace(/^\* (.*$)/gim, '<li>$1</li>')
        .replace(/^- (.*$)/gim, '<li>$1</li>')
        // 换行
        .replace(/\n/g, '<br>');
    
    // 包装列表项
    html = html.replace(/(<li>.*<\/li>)/gs, '<ul>$1</ul>');
    
    return `<div class="markdown-content">${html}</div>`;
}

function fetchVersionInfo() {
    fetch('/api/version')
        .then(response => response.json())
        .then(data => {
            if (data.status === 'success') {
                const versionBtn = document.getElementById('versionBtn');
                if (versionBtn) {
                    versionBtn.textContent = `v${data.version}`;
                }
            }
        })
        .catch(error => {
            console.error('Error fetching version info:', error);
        });
}

function showVersionModal() {
    const modal = document.getElementById('versionModal');
    const modalBody = modal.querySelector('.modal-body');
    
    // 显示加载状态
    modalBody.innerHTML = '<div class="text-center"><div class="spinner-border" role="status"><span class="visually-hidden">Loading...</span></div><p class="mt-2">加载版本信息中...</p></div>';
    
    // 显示模态框 - 使用Bootstrap 5的原生JavaScript API
    const bootstrapModal = new bootstrap.Modal(modal);
    bootstrapModal.show();
    
    // 添加模态框关闭事件监听器
    modal.addEventListener('hidden.bs.modal', function () {
        // 重置模态框内容为加载状态
        modalBody.innerHTML = '<div class="text-center py-4"><div class="spinner-border text-primary" role="status"><span class="visually-hidden">加载中...</span></div><p class="mt-2">正在加载版本信息...</p></div>';
        
        // 确保移除所有遮罩
        const backdrops = document.querySelectorAll('.modal-backdrop');
        backdrops.forEach(backdrop => backdrop.remove());
        
        // 恢复body的滚动
        document.body.classList.remove('modal-open');
        document.body.style.overflow = '';
        document.body.style.paddingRight = '';
    }, { once: true });
    
    // 获取版本日志
    fetch('/api/changelog')
        .then(response => response.json())
        .then(data => {
            if (data.status === 'success') {
                const htmlContent = convertMarkdownToHtml(data.content);
                modalBody.innerHTML = `<div class="version-content">${htmlContent}</div>`;
            } else {
                modalBody.innerHTML = '<div class="alert alert-warning">版本日志加载失败</div>';
            }
        })
        .catch(error => {
            console.error('Error loading changelog:', error);
            modalBody.innerHTML = '<div class="alert alert-danger">版本日志加载失败</div>';
        });
}
