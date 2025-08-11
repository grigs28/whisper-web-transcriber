import os
import shutil
import uuid
import json
import logging
from logging.handlers import RotatingFileHandler
from datetime import datetime, timedelta
from flask import Flask, render_template, request, redirect, url_for, send_file, jsonify
from werkzeug.utils import secure_filename
import torch
import whisper
import threading
import time
from pathlib import Path
from flask_socketio import SocketIO, emit
import gc
import signal
import sys
from config import config

# ==============================
# 应用程序配置和初始化
# ==============================

# 从配置模块获取配置参数
UPLOAD_FOLDER = config.UPLOAD_FOLDER
OUTPUT_FOLDER = config.OUTPUT_FOLDER
LOG_FOLDER = 'logs'
ALLOWED_EXTENSIONS = set(config.ALLOWED_EXTENSIONS)
MAX_FILE_AGE = config.MAX_FILE_AGE
MODEL_BASE_PATH = config.MODEL_BASE_PATH
MAX_LOG_SIZE = config.MAX_LOG_SIZE
BACKUP_COUNT = config.LOG_BACKUP_COUNT

# 创建必要的文件夹
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(OUTPUT_FOLDER, exist_ok=True)
os.makedirs(LOG_FOLDER, exist_ok=True)
os.makedirs(MODEL_BASE_PATH, exist_ok=True)

# 初始化Flask Web应用程序
app = Flask(__name__)
app.secret_key = config.SECRET_KEY
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['OUTPUT_FOLDER'] = OUTPUT_FOLDER
app.config['MAX_CONTENT_LENGTH'] = config.MAX_CONTENT_LENGTH

# 初始化SocketIO
socketio = SocketIO(app, 
                   async_mode='threading', 
                   cors_allowed_origins="*",
                   ping_timeout=config.WEBSOCKET_PING_TIMEOUT,
                   ping_interval=config.WEBSOCKET_PING_INTERVAL)

# 配置日志系统
log_formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
log_file = os.path.join(LOG_FOLDER, 'transcription.log')

# 创建日志处理器 - 限制最大200MB，保留5个备份
log_handler = RotatingFileHandler(
    log_file, 
    maxBytes=MAX_LOG_SIZE, 
    backupCount=BACKUP_COUNT
)
log_handler.setFormatter(log_formatter)
log_handler.setLevel(logging.INFO)

# 获取应用日志记录器
app_logger = app.logger
app_logger.addHandler(log_handler)
app_logger.setLevel(logging.INFO)

# 全局变量
active_transcriptions = {}
transcription_timers = {}
transcription_start_times = {}
# 移除停止标志相关变量
# 转录队列
transcription_queue = []
queue_lock = threading.Lock()

# ==============================
# 辅助函数
# ==============================

def log_message(level, message, emit_to_ws=True):
    """
    记录日志并发送到WebSocket
    
    Args:
        level (str): 日志级别 (info, warning, error)
        message (str): 日志消息
        emit_to_ws (bool): 是否发送到WebSocket
    """
    # 记录到文件
    if level == 'info':
        app_logger.info(message)
    elif level == 'warning':
        app_logger.warning(message)
    elif level == 'error':
        app_logger.error(message)
    
    # 发送到WebSocket
    if emit_to_ws:
        try:
            socketio.emit('log_message', {
                'level': level,
                'message': message,
                'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            }, namespace='/status')
        except Exception as e:
            app_logger.error(f"发送日志到WebSocket失败: {str(e)}")

# ==============================
# GPU管理函数
# ==============================

def get_available_gpus():
    """
    检查系统中可用的GPU设备数量
    
    Returns:
        list: 可用GPU的ID列表
    """
    if torch.cuda.is_available():
        gpus = [i for i in range(torch.cuda.device_count())]
        log_message('info', f"检测到可用GPU: {gpus}")
        return gpus
    log_message('info', "未检测到GPU，将使用CPU")
    return []

# 设置默认GPU ID
available_gpus = get_available_gpus()
if available_gpus and config.DEFAULT_GPU_IDS:
    # 验证配置的GPU ID是否可用
    valid_gpu_ids = [gpu_id for gpu_id in config.DEFAULT_GPU_IDS if gpu_id < len(available_gpus)]
    DEFAULT_GPU_ID = valid_gpu_ids if valid_gpu_ids else [0]
    log_message('info', f"设置默认GPU为: {DEFAULT_GPU_ID}")
else:
    DEFAULT_GPU_ID = []
    log_message('info', "使用CPU模式")

# 全局字典用于缓存已加载的模型
models = {}

# ==============================
# 文件处理辅助函数
# ==============================

def allowed_file(filename):
    """
    检查文件扩展名是否在允许的列表中
    
    Args:
        filename (str): 文件名
        
    Returns:
        bool: 如果文件扩展名被允许返回True，否则返回False
    """
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# ==============================
# 文件清理服务
# ==============================

# 文件清理功能已禁用
# def cleanup_old_files():
#     """
#     后台线程函数：定期清理过期的文件（已禁用）
#     """
#     pass

# cleanup_thread = None  # 文件清理线程已禁用

# ==============================
# 模型管理函数
# ==============================

def load_model(model_name, gpu_ids):
    """
    加载Whisper语音识别模型（每次转录时重新加载）
    
    Args:
        model_name (str): 模型名称
        gpu_ids (list): 要使用的GPU ID列表
        
    Returns:
        model: 加载的模型对象
    """
    try:
        # 如果没有GPU，则使用CPU
        if not gpu_ids:
            device = "cpu"
            log_message('info', f"加载模型 {model_name} 到 CPU")
        else:
            device = f"cuda:{gpu_ids[0]}"
            log_message('info', f"加载模型 {model_name} 到 GPU {gpu_ids[0]}")
        
        # 创建特定模型目录
        model_dir = os.path.join(MODEL_BASE_PATH, f"whisper-{model_name}")
        os.makedirs(model_dir, exist_ok=True)
        
        # 检查模型是否已存在
        model_file_pattern = os.path.join(model_dir, "*.pt")
        import glob
        existing_models = glob.glob(model_file_pattern)
        
        if not existing_models:
            log_message('info', f"模型 whisper-{model_name} 不存在，正在下载...")
        
        # 加载指定Whisper模型
        log_message('info', f"正在加载模型: whisper-{model_name}，路径: {model_dir}")
        model = whisper.load_model(model_name, download_root=model_dir).to(device)
        log_message('info', f"模型 {model_name} 加载成功")
        return model
    except Exception as e:
        log_message('error', f"加载模型失败: {e}")
        return None

def release_model_memory(gpu_ids):
    """
    释放模型显存
    
    Args:
        gpu_ids (list): GPU ID列表
    """
    try:
        # 强制垃圾回收
        gc.collect()
        
        # 如果使用GPU，清空显存缓存
        if gpu_ids and torch.cuda.is_available():
            for gpu_id in gpu_ids:
                if gpu_id < torch.cuda.device_count():
                    with torch.cuda.device(gpu_id):
                        # 清空缓存
                        torch.cuda.empty_cache()
                        # 同步GPU操作
                        torch.cuda.synchronize()
                        # 重置GPU内存统计
                        torch.cuda.reset_peak_memory_stats(gpu_id)
                        torch.cuda.reset_accumulated_memory_stats(gpu_id)
            log_message('info', f"GPU {gpu_ids} 显存已彻底释放")
        else:
            log_message('info', "CPU内存已释放")
            
        # 额外的垃圾回收
        gc.collect()
        
    except Exception as e:
        log_message('error', f"释放显存失败: {e}")

def transcribe_with_progress(model, file_path, language, task_id):
    """带进度更新的转录函数"""
    import whisper.audio as audio
    import numpy as np
    
    try:
        # 加载音频
        audio_data = audio.load_audio(file_path)
        
        # 计算音频总长度（秒）
        sample_rate = whisper.audio.SAMPLE_RATE
        total_duration = len(audio_data) / sample_rate
        
        # 分段处理，重叠2秒避免单词截断
        segment_duration = config.SEGMENT_DURATION  # 从配置文件读取分段时间
        overlap_duration = 2   # 重叠2秒
        segments = []
        current_progress = 15  # 从15%开始
        
        # 计算总段数
        total_segments = int(np.ceil(total_duration / segment_duration))
        
        for i in range(total_segments):
            start_time = i * segment_duration
            # 除了第一段，其他段都向前重叠2秒
            if i > 0:
                start_time -= overlap_duration
            
            end_time = min((i + 1) * segment_duration, total_duration)
            
            # 提取音频段
            start_sample = int(start_time * sample_rate)
            end_sample = int(end_time * sample_rate)
            segment_audio = audio_data[start_sample:end_sample]
            
            # 转录当前段
            segment_result = model.transcribe(
                segment_audio,
                language=language,
                verbose=False
            )
            
            segments.append(segment_result)
            
            # 更新进度（从15%到95%）
            progress_increment = 80 / total_segments  # 80%的进度空间分配给转录
            current_progress += progress_increment
            
            # 确保进度是5的倍数
            display_progress = int(current_progress / 5) * 5
            display_progress = min(display_progress, 95)
            
            socketio.emit('task_update', {
                'task_id': task_id,
                'status': 'processing',
                'message': f'转录进度 {i+1}/{total_segments} 段',
                'progress': display_progress
            }, namespace='/status')
            
            log_message('info', f"任务 {task_id} 完成段 {i+1}/{total_segments}，进度: {display_progress}%")
        
        # 合并所有段的结果，处理重叠部分
        combined_text = ""
        all_segments = []
        
        for i, segment_result in enumerate(segments):
            if 'text' in segment_result:
                current_text = segment_result['text'].strip()
                
                if i == 0:
                    # 第一段直接添加
                    combined_text = current_text
                else:
                    # 处理重叠部分，去除可能的重复文本
                    if current_text:
                        # 简单的重复检测：检查当前段开头是否与前面内容重复
                        words = current_text.split()
                        if len(words) > 0:
                            # 查找重叠点，从当前段的前几个词开始匹配
                            overlap_found = False
                            # 对于最后一段，减少重叠检测的范围，避免过度过滤
                            max_check_words = min(5 if i == len(segments) - 1 else 10, len(words))
                            
                            for j in range(max_check_words):
                                test_phrase = ' '.join(words[:j+1])
                                # 更严格的匹配条件，避免误判
                                if len(test_phrase) > 3 and test_phrase in combined_text[-len(test_phrase)*3:]:
                                    # 找到重叠，跳过重叠部分
                                    remaining_text = ' '.join(words[j+1:])
                                    if remaining_text:
                                        if not combined_text.endswith(' '):
                                            combined_text += " "
                                        combined_text += remaining_text
                                        overlap_found = True
                                        break
                                    # 如果是最后一段且没有剩余文本，强制保留后半部分内容
                                    elif i == len(segments) - 1 and j < len(words) - 1:
                                        # 保留最后一段的后半部分，避免完全丢失
                                        keep_from = max(j, len(words) // 2)
                                        remaining_text = ' '.join(words[keep_from:])
                                        if remaining_text:
                                            if not combined_text.endswith(' '):
                                                combined_text += " "
                                            combined_text += remaining_text
                                        overlap_found = True
                                        break
                            
                            if not overlap_found:
                                # 没有找到重叠，直接添加
                                if not combined_text.endswith(' '):
                                    combined_text += " "
                                combined_text += current_text
            
            if 'segments' in segment_result:
                # 调整时间戳
                base_time = i * segment_duration
                if i > 0:
                    base_time -= overlap_duration
                    
                for seg in segment_result['segments']:
                    adjusted_seg = seg.copy()
                    adjusted_seg['start'] += base_time
                    adjusted_seg['end'] += base_time
                    
                    # 过滤重叠时间段的segments
                    if i == 0 or adjusted_seg['start'] >= (i * segment_duration - overlap_duration/2):
                        all_segments.append(adjusted_seg)
        
        # 构建最终结果
        final_result = {
            'text': combined_text,
            'segments': all_segments,
            'language': segments[0].get('language', language) if segments else language
        }
        
        return final_result
        
    except Exception as e:
        log_message('error', f"任务 {task_id} 分段转录失败: {str(e)}")
        # 回退到原始方法
        return model.transcribe(file_path, language=language, verbose=False)

def transcribe_with_interrupt(model, file_path, language, task_id):
    """转录函数 - 直接转录整个文件"""
    try:
        # 获取模型所在设备
        device = next(model.parameters()).device
        log_message('info', f"任务 {task_id} 开始加载音频文件，模型设备: {device}")
        
        # 检测语言（如果需要）
        if language == "auto" or language is None:
            # 使用前30秒检测语言
            import whisper.audio as audio
            audio_data = audio.load_audio(file_path)
            sample_rate = whisper.audio.SAMPLE_RATE
            sample_audio = audio_data[:min(30 * sample_rate, len(audio_data))]
            # 获取模型的mel通道数以避免维度不匹配
            n_mels = getattr(model.dims, 'n_mels', 80)  # 默认80，large-v3使用128
            mel_sample = audio.log_mel_spectrogram(sample_audio, n_mels=n_mels)
            # 确保mel_sample在正确的设备上
            mel_sample = mel_sample.to(device)
            _, probs = model.detect_language(mel_sample)
            language = max(probs, key=probs.get)
            log_message('info', f"任务 {task_id} 检测到语言: {language}，使用 {n_mels} mel通道")
        
        # 发送开始转录的进度更新
        socketio.emit('task_update', {
            'task_id': task_id,
            'status': 'processing',
            'message': '开始转录音频文件',
            'progress': 10
        }, namespace='/status')
        
        # 使用自定义转录方法实现进度更新
        log_message('info', f"任务 {task_id} 开始转录音频文件")
        result = transcribe_with_progress(
            model,
            file_path,
            language if language != "auto" else None,
            task_id
        )
        
        # 发送完成进度更新
        socketio.emit('task_update', {
            'task_id': task_id,
            'status': 'processing',
            'message': '转录完成',
            'progress': 100
        }, namespace='/status')
        
        log_message('info', f"任务 {task_id} 转录完成")
        return result
        
    except Exception as e:
        log_message('error', f"任务 {task_id} 转录过程中出错: {str(e)}")
        # 如果转录失败，尝试回退到原始方法
        try:
            return model.transcribe(file_path, language=language if language != "auto" else None)
        except Exception as fallback_error:
            log_message('error', f"任务 {task_id} 回退转录也失败: {str(fallback_error)}")
            return None

# ==============================
# 核心处理函数
# ==============================

def transcribe_audio_process(file_path, output_path, model_name, language, gpu_ids, task_id):
    model = None
    try:
        # 通知任务开始
        socketio.emit('task_update', {
            'task_id': task_id,
            'status': 'processing',
            'message': f'开始转录: {os.path.basename(file_path)}',
            'filename': os.path.basename(file_path)
        }, namespace='/status')
        
        log_message('info', f"任务 {task_id} 开始转录: {os.path.basename(file_path)}")
        
        # 加载模型
        model = load_model(model_name, gpu_ids)
        if model is None:
            error_msg = "无法加载模型"
            log_message('error', error_msg)
            raise Exception(error_msg)
        
        # 获取任务开始时间
        start_time = transcription_start_times.get(task_id, time.time())
        
        # 转录音频
        log_message('info', f"开始转录音频文件: {os.path.basename(file_path)}")
        
        # 使用自定义的转录函数
        result = transcribe_with_interrupt(model, file_path, language, task_id)
        
        if result is None:
            log_message('info', f"任务 {task_id} 转录失败")
            return None
        
        text = result["text"]
        
        # 保存结果到文件
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(text)
        
        # 计算耗时
        duration = time.time() - start_time
        mins, secs = divmod(duration, 60)
        time_str = f"{int(mins)}分{int(secs)}秒"
        
        # 单文件转录模式不需要停止检查
        
        # 通知任务完成
        socketio.emit('task_update', {
            'task_id': task_id,
            'status': 'completed',
            'message': f'转录完成! 耗时: {time_str}',
            'output_file': os.path.basename(output_path)
        }, namespace='/status')
        
        log_message('info', f"任务 {task_id} 转录完成! 耗时: {time_str}")
        
        return text
        
    except Exception as e:
        error_msg = f"转录失败: {str(e)}"
        socketio.emit('task_update', {
            'task_id': task_id,
            'status': 'failed',
            'message': error_msg
        }, namespace='/status')
        log_message('error', f"任务 {task_id} {error_msg}")
        
        raise Exception(error_msg)
        
    finally:
        # 清理资源
        if task_id in active_transcriptions:
            task_info = active_transcriptions[task_id]
            gpu_ids = task_info.get('gpu_ids', [])
            
            # 释放GPU内存
            if gpu_ids:
                release_model_memory(gpu_ids)
                log_message('info', f"任务 {task_id} GPU内存已释放")
            
            # 从活动转录中移除
            del active_transcriptions[task_id]
        
        # 清理其他资源
        if task_id in transcription_start_times:
            del transcription_start_times[task_id]
            
        if task_id in transcription_timers:
            del transcription_timers[task_id]
        
        # 释放模型和显存
        if model is not None:
            try:
                # 将模型移到CPU以释放GPU内存
                if hasattr(model, 'to'):
                    model.to('cpu')
                del model
                log_message('info', f"任务 {task_id} 模型已释放")
            except Exception as e:
                log_message('warning', f"释放模型时出错: {e}")
        
        # 彻底释放显存
        try:
            # 多次垃圾回收确保彻底清理
            for _ in range(3):
                gc.collect()
            
            # 使用改进的内存释放函数
            if gpu_ids:
                release_model_memory(gpu_ids)
            
            # 额外的GPU内存清理
            if torch.cuda.is_available():
                for gpu_id in (gpu_ids or []):
                    if gpu_id < torch.cuda.device_count():
                        with torch.cuda.device(gpu_id):
                            torch.cuda.empty_cache()
                            torch.cuda.synchronize()
                            
            log_message('info', f"任务 {task_id} 显存已彻底释放")
        except Exception as e:
            log_message('warning', f"释放显存时出错: {e}")

# 转录工作线程
def transcription_worker():
    log_message('info', "转录工作线程已启动")
    while True:
        with queue_lock:
            if transcription_queue:
                task = transcription_queue.pop(0)
            else:
                task = None
        
        if task:
            file_path, output_path, model_name, language, gpu_ids, task_id = task
            
            # 记录任务开始时间
            transcription_start_times[task_id] = time.time()
            
            active_transcriptions[task_id] = {
                'thread': threading.current_thread(),
                'file': os.path.basename(file_path),
                'gpu_ids': gpu_ids
            }
            
            try:
                transcribe_audio_process(file_path, output_path, model_name, language, gpu_ids, task_id)
            except Exception as e:
                log_message('error', f"转录错误: {e}")
                # 清理开始时间记录
                if task_id in transcription_start_times:
                    del transcription_start_times[task_id]
            
            # 处理完成后检查队列
            with queue_lock:
                if transcription_queue:
                    # 通知下一个任务开始
                    next_task = transcription_queue[0]
                    next_filename = os.path.basename(next_task[0])
                    socketio.emit('task_update', {
                        'task_id': next_task[5],
                        'status': 'processing',
                        'message': f'开始转录: {next_filename}',
                        'filename': next_filename
                    }, namespace='/status')
                    log_message('info', f"开始下一个任务: {next_filename}")
        
        time.sleep(1)

# 创建转录工作线程（不立即启动）
worker_thread = threading.Thread(target=transcription_worker, daemon=True)

# ==============================
# Web路由定义
# ==============================

@app.route('/')
def index():
    """
    返回主页面，显示所有上传的文件和转录结果
    """
    log_message('info', "用户访问主页")
    # 获取所有上传的文件
    uploaded_files = []
    for root, dirs, files in os.walk(UPLOAD_FOLDER):
        for file in files:
            file_path = os.path.join(root, file)
            file_time = datetime.fromtimestamp(os.path.getctime(file_path))
            uploaded_files.append({
                'name': file,
                'path': file_path,
                'upload_time': file_time.strftime('%Y-%m-%d %H:%M:%S')
            })
    
    # 获取所有输出的文件
    output_files = []
    for root, dirs, files in os.walk(OUTPUT_FOLDER):
        for file in files:
            file_path = os.path.join(root, file)
            file_time = datetime.fromtimestamp(os.path.getctime(file_path))
            output_files.append({
                'name': file,
                'path': file_path,
                'upload_time': file_time.strftime('%Y-%m-%d %H:%M:%S')
            })
    
    # 获取GPU信息
    gpus = get_available_gpus()
    
    # 获取可用模型
    whisper_models = config.SUPPORTED_MODELS
    
    # 获取可用语言
    languages = [
        ('auto', '自动检测'),
        ('zh', '中文'),
        ('en', '英文'),
        ('ja', '日文'),
        ('ko', '韩文'),
        ('fr', '法文'),
        ('de', '德文'),
        ('es', '西班牙文'),
        ('ru', '俄文')
    ]
    
    return render_template('index.html', 
                         uploaded_files=uploaded_files, 
                         output_files=output_files, 
                         gpus=gpus, 
                         default_gpu_ids=DEFAULT_GPU_ID,
                         whisper_models=whisper_models,
                         languages=languages)

@app.route('/upload', methods=['POST'])
def upload_file():
    """
    处理文件上传请求（只保存文件，不加入转录队列）
    """
    try:
        # 检查是否有文件被上传
        if 'files' not in request.files:
            error_msg = "没有文件上传"
            log_message('error', error_msg)
            return jsonify({"error": error_msg}), 400
        
        files = request.files.getlist('files')
        
        log_message('info', f"收到上传请求: {len(files)} 个文件")
        
        uploaded_files = []
        for file in files:
            if file and allowed_file(file.filename):
                filename = secure_filename(file.filename)
                file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                file.save(file_path)
                uploaded_files.append(filename)
                log_message('info', f"文件已保存: {filename}")
        
        # 获取所有上传的文件列表
        all_uploaded_files = []
        for root, dirs, files in os.walk(UPLOAD_FOLDER):
            for file in files:
                all_uploaded_files.append(file)
        
        success_msg = f"已成功上传 {len(uploaded_files)} 个文件"
        log_message('info', success_msg)
        return jsonify({
            "status": "success",
            "message": success_msg,
            "files": uploaded_files,  # 本次上传的文件
            "uploaded_files": all_uploaded_files  # 所有上传的文件列表
        })
    except Exception as e:
        error_msg = f"上传失败: {str(e)}"
        log_message('error', error_msg)
        return jsonify({"error": error_msg}), 500

# 新增路由：将文件加入转录队列
@app.route('/add_to_queue', methods=['POST'])
def add_to_queue():
    """
    将已上传的文件加入转录队列
    """
    try:
        data = request.get_json()
        filenames = data.get('files', [])
        selected_gpus = data.get('gpus', DEFAULT_GPU_ID)
        selected_model = data.get('model', 'large-v3')
        selected_language = data.get('language', 'auto')
        
        log_message('info', f"收到转录请求: {len(filenames)} 个文件, GPU: {selected_gpus}, 模型: {selected_model}, 语言: {selected_language}")
        
        # 确保GPU ID是整数列表
        if isinstance(selected_gpus, list):
            gpu_ids = [int(gpu) for gpu in selected_gpus if str(gpu).isdigit()]
        else:
            gpu_ids = DEFAULT_GPU_ID
        
        if not gpu_ids:
            gpu_ids = DEFAULT_GPU_ID
        
        added_files = []
        for filename in filenames:
            file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            if not os.path.exists(file_path):
                log_message('warning', f"文件不存在，跳过: {filename}")
                continue
                
            # 生成唯一任务ID
            task_id = uuid.uuid4().hex
            
            # 生成输出文件名
            output_filename = f"{Path(filename).stem}_{task_id[:8]}.txt"
            output_path = os.path.join(app.config['OUTPUT_FOLDER'], output_filename)
            
            # 添加到转录队列
            with queue_lock:
                is_first_task = len(transcription_queue) == 0
                transcription_queue.append((
                    file_path, 
                    output_path, 
                    selected_model, 
                    selected_language, 
                    gpu_ids, 
                    task_id
                ))
                added_files.append(filename)
                
                # 通知新任务加入队列
                socketio.emit('task_update', {
                    'task_id': task_id,
                    'status': 'queued',
                    'message': f'已加入队列: {filename}',
                    'filename': filename,
                    'position': len(transcription_queue)
                }, namespace='/status')
                
                log_message('info', f"任务 {task_id} 已加入队列: {filename} (位置: {len(transcription_queue)})")
                
                if is_first_task:
                    socketio.emit('task_update', {
                        'task_id': task_id,
                        'status': 'processing',
                        'message': f'开始转录: {filename}',
                        'filename': filename
                    }, namespace='/status')
                    log_message('info', f"任务 {task_id} 开始处理: {filename}")
        
        if added_files:
            success_msg = f"已成功添加 {len(added_files)} 个文件到转录队列"
            log_message('info', success_msg)
            return jsonify({
                "status": "success",
                "message": success_msg
            })
        else:
            error_msg = "没有有效的文件添加到队列"
            log_message('error', error_msg)
            return jsonify({"error": error_msg}), 400
    except Exception as e:
        error_msg = f"添加队列失败: {str(e)}"
        log_message('error', error_msg)
        return jsonify({"error": error_msg}), 500

@app.route('/download/<path:filename>')
def download_file(filename):
    """
    提供文件下载功能
    """
    try:
        # 构造完整的文件路径
        file_path = os.path.join(OUTPUT_FOLDER, filename)
        if os.path.exists(file_path):
            log_message('info', f"用户下载文件: {filename}")
            return send_file(file_path, as_attachment=True, download_name=filename)
        else:
            error_msg = f"文件不存在: {filename}"
            log_message('error', error_msg)
            return error_msg, 404
    except Exception as e:
        error_msg = f"下载失败: {str(e)}"
        log_message('error', error_msg)
        return error_msg, 500

# 新增路由：播放音频文件
@app.route('/play/<path:filename>')
def play_file(filename):
    """
    提供音频文件播放功能
    """
    try:
        # 构造完整的文件路径
        file_path = os.path.join(UPLOAD_FOLDER, filename)
        if os.path.exists(file_path):
            log_message('info', f"用户播放文件: {filename}")
            return send_file(file_path)
        else:
            error_msg = f"文件不存在: {filename}"
            log_message('error', error_msg)
            return error_msg, 404
    except Exception as e:
        error_msg = f"播放失败: {str(e)}"
        log_message('error', error_msg)
        return error_msg, 500

@app.route('/delete/<path:filepath>')
def delete_file(filepath):
    """
    删除上传的文件
    """
    try:
        # 删除文件
        file_path = os.path.join(UPLOAD_FOLDER, filepath)
        if os.path.exists(file_path):
            os.remove(file_path)
            log_message('info', f"文件已删除: {filepath}")
            return jsonify({"status": "success"})
        else:
            error_msg = f"文件不存在: {filepath}"
            log_message('error', error_msg)
            return jsonify({"status": "error", "message": error_msg}), 404
    except Exception as e:
        error_msg = f"删除失败: {str(e)}"
        log_message('error', error_msg)
        return jsonify({"status": "error", "message": error_msg}), 500

@app.route('/delete_output/<path:filepath>')
def delete_output_file(filepath):
    """
    删除转录输出的文件
    """
    try:
        # 删除输出文件
        file_path = os.path.join(OUTPUT_FOLDER, filepath)
        if os.path.exists(file_path):
            os.remove(file_path)
            log_message('info', f"输出文件已删除: {filepath}")
            return jsonify({"status": "success"})
        else:
            error_msg = f"文件不存在: {filepath}"
            log_message('error', error_msg)
            return jsonify({"status": "error", "message": error_msg}), 404
    except Exception as e:
        error_msg = f"删除失败: {str(e)}"
        log_message('error', error_msg)
        return jsonify({"status": "error", "message": error_msg}), 500

# ==============================
# API端点
# ==============================

@app.route('/api/transcribe', methods=['POST'])
def api_transcribe():
    """
    RESTful API端点：转录音频文件
    """
    try:
        # 获取上传的文件
        if 'file' not in request.files:
            error_msg = "没有文件上传"
            log_message('error', error_msg)
            return jsonify({"error": error_msg}), 400
        
        file = request.files['file']
        if file.filename == '':
            error_msg = "没有选择文件"
            log_message('error', error_msg)
            return jsonify({"error": error_msg}), 400
        
        # 获取GPU ID
        gpu_ids = request.form.get('gpus', '').split(',')
        gpu_ids = [int(gpu.strip()) for gpu in gpu_ids if gpu.strip().isdigit()]
        if not gpu_ids:
            gpu_ids = DEFAULT_GPU_ID
        
        # 获取模型和语言
        model_name = request.form.get('model', 'large-v3')
        language = request.form.get('language', 'auto')
        
        log_message('info', f"API转录请求: 文件: {file.filename}, GPU: {gpu_ids}, 模型: {model_name}, 语言: {language}")
        
        # 保存上传的文件并进行转录
        if file and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            file.save(file_path)
            log_message('info', f"API文件已保存: {filename}")
            
            # 生成输出文件名
            task_id = uuid.uuid4().hex
            output_filename = f"{Path(filename).stem}_{task_id[:8]}.txt"
            output_path = os.path.join(app.config['OUTPUT_FOLDER'], output_filename)
            
            # 转录音频
            transcribe_audio_process(file_path, output_path, model_name, language, gpu_ids, task_id)
            
            log_message('info', f"API转录完成: {filename} -> {output_filename}")
            return jsonify({
                "status": "success",
                "output_file": output_filename
            })
        else:
            error_msg = f"不支持的文件类型: {file.filename}"
            log_message('error', error_msg)
            return jsonify({"error": error_msg}), 400
    except Exception as e:
        error_msg = f"转录失败: {str(e)}"
        log_message('error', error_msg)
        return jsonify({"error": error_msg}), 500

# 停止转录API已移除

@app.route('/api/uploaded_files')
def api_uploaded_files():
    """
    获取已上传文件列表
    """
    try:
        files = []
        if os.path.exists(UPLOAD_FOLDER):
            for filename in os.listdir(UPLOAD_FOLDER):
                if allowed_file(filename):
                    file_path = os.path.join(UPLOAD_FOLDER, filename)
                    if os.path.isfile(file_path):
                        files.append({
                            'name': filename,
                            'size': os.path.getsize(file_path),
                            'modified': os.path.getmtime(file_path)
                        })
        
        # 按修改时间排序（最新的在前）
        files.sort(key=lambda x: x['modified'], reverse=True)
        
        return jsonify({
            'status': 'success',
            'files': [f['name'] for f in files],
            'count': len(files)
        })
    except Exception as e:
        error_msg = f"获取上传文件列表失败: {str(e)}"
        log_message('error', error_msg)
        return jsonify({'error': error_msg}), 500

@app.route('/api/output_files')
def api_output_files():
    """
    获取输出文件列表
    """
    try:
        files = []
        if os.path.exists(OUTPUT_FOLDER):
            for filename in os.listdir(OUTPUT_FOLDER):
                if filename.endswith('.txt'):
                    file_path = os.path.join(OUTPUT_FOLDER, filename)
                    if os.path.isfile(file_path):
                        files.append({
                            'name': filename,
                            'size': os.path.getsize(file_path),
                            'modified': os.path.getmtime(file_path)
                        })
        
        # 按修改时间排序（最新的在前）
        files.sort(key=lambda x: x['modified'], reverse=True)
        
        return jsonify({
            'status': 'success',
            'files': [f['name'] for f in files],
            'count': len(files)
        })
    except Exception as e:
        error_msg = f"获取输出文件列表失败: {str(e)}"
        log_message('error', error_msg)
        return jsonify({'error': error_msg}), 500

@app.route('/api/status')
def api_status():
    """
    RESTful API端点：获取系统状态信息
    """
    try:
        gpus = get_available_gpus()
        
        # 获取队列状态
        with queue_lock:
            queue_info = [
                {
                    'task_id': task[5] if len(task) > 5 else f'queue_{idx}_{int(time.time())}',
                    'filename': os.path.basename(task[0]),
                    'status': 'queued',
                    'position': idx + 1
                }
                for idx, task in enumerate(transcription_queue)
            ]
            
            # 添加活动任务
            for task_id, task_info in active_transcriptions.items():
                # 获取任务开始时间
                start_time = transcription_start_times.get(task_id)
                elapsed_seconds = int(time.time() - start_time) if start_time else 0
                
                queue_info.insert(0, {
                    'task_id': task_id,
                    'filename': task_info['file'],
                    'status': 'processing',
                    'position': 0,
                    'start_time': start_time,
                    'elapsed_seconds': elapsed_seconds
                })
        
        log_message('info', "API状态查询")
        return jsonify({
            "status": "success",
            "available_gpus": gpus,
            "default_gpu": DEFAULT_GPU_ID,
            "queue": queue_info,
            "active_tasks": len(active_transcriptions),
            "queued_tasks": len(transcription_queue)
        })
    except Exception as e:
        error_msg = f"获取状态失败: {str(e)}"
        log_message('error', error_msg)
        return jsonify({"error": error_msg}), 500

@app.route('/api/progress/<task_id>')
def api_progress(task_id):
    """
    RESTful API端点：获取处理进度
    """
    try:
        if task_id in active_transcriptions:
            # 计算已处理时间
            if task_id in transcription_start_times:
                elapsed = time.time() - transcription_start_times[task_id]
                progress = min(int(elapsed / 60 * 10), 95)  # 模拟进度
                return jsonify({
                    "status": "processing",
                    "progress": progress,
                    "elapsed": int(elapsed),
                    "message": "正在处理音频文件..."
                })
            else:
                return jsonify({
                    "status": "queued",
                    "progress": 0,
                    "message": "等待处理中..."
                })
        else:
            error_msg = f"任务不存在或已完成: {task_id}"
            log_message('warning', error_msg)
            return jsonify({
                "status": "not_found",
                "message": error_msg
            }), 404
    except Exception as e:
        error_msg = f"获取进度失败: {str(e)}"
        log_message('error', error_msg)
        return jsonify({"error": error_msg}), 500

# ==============================
# WebSocket 处理
# ==============================

@socketio.on('connect', namespace='/status')
def handle_connect():
    log_message('info', "客户端已连接")
    emit('system_message', {'message': '已连接到转录状态服务'})

# ==============================
# 错误处理器
# ==============================

@app.errorhandler(413)
def too_large(e):
    error_msg = "文件过大，请选择小于500MB的文件"
    log_message('error', error_msg)
    return jsonify({"error": error_msg}), 413

@app.errorhandler(500)
def internal_error(e):
    error_msg = "服务器内部错误"
    log_message('error', error_msg)
    return jsonify({"error": error_msg}), 500

# ==============================
# 信号处理和资源清理
# ==============================

def cleanup_resources():
    """
    清理所有资源，包括GPU内存
    """
    try:
        log_message('info', "开始清理资源...")
        
        # 设置全局停止标志（如果存在的话）
        global active_transcriptions
        
        # 停止所有活动的转录任务
        for task_id in list(active_transcriptions.keys()):
            try:
                task_info = active_transcriptions[task_id]
                gpu_ids = task_info.get('gpu_ids', [])
                
                # 设置任务停止标志
                if 'stop_flag' in task_info:
                    task_info['stop_flag'] = True
                
                # 释放GPU内存
                if gpu_ids:
                    release_model_memory(gpu_ids)
                    log_message('info', f"任务 {task_id} GPU内存已释放")
                
                # 从活动转录中移除
                del active_transcriptions[task_id]
            except Exception as e:
                log_message('warning', f"清理任务 {task_id} 时出错: {e}")
        
        # 清理转录队列
        global transcription_queue
        with queue_lock:
            transcription_queue.clear()
        
        # 清理全局模型缓存
        global models
        models.clear()
        
        # 强制垃圾回收
        gc.collect()
        
        # 清空所有GPU显存
        if torch.cuda.is_available():
            for i in range(torch.cuda.device_count()):
                with torch.cuda.device(i):
                    torch.cuda.empty_cache()
                    torch.cuda.synchronize()
            log_message('info', "所有GPU显存已清空")
        
        # 等待一小段时间让清理完成
        time.sleep(0.5)
        
        log_message('info', "资源清理完成")
        
    except Exception as e:
        log_message('error', f"资源清理时出错: {e}")

def signal_handler(signum, frame):
    """
    信号处理函数，处理Ctrl+C等终止信号
    """
    log_message('info', f"接收到信号 {signum}，正在安全退出...")
    cleanup_resources()
    
    # 优雅地关闭SocketIO和Flask应用
    try:
        # 停止SocketIO服务器
        if hasattr(socketio, 'stop'):
            socketio.stop()
        log_message('info', "SocketIO服务器已停止")
    except Exception as e:
        log_message('warning', f"停止SocketIO服务器时出错: {e}")
    
    log_message('info', "程序已安全退出")
    
    # 使用os._exit而不是sys.exit，避免在多线程环境中的问题
    import os
    os._exit(0)

# 注册信号处理器
signal.signal(signal.SIGINT, signal_handler)  # Ctrl+C
signal.signal(signal.SIGTERM, signal_handler)  # 终止信号

# ==============================
# 应用程序入口点
# ==============================

if __name__ == '__main__':
    """
    应用程序启动函数
    """
    # 确保模型基础路径存在
    os.makedirs(MODEL_BASE_PATH, exist_ok=True)
    log_message('info', f"应用程序启动，模型将保存到: {MODEL_BASE_PATH}")
    
    # 文件清理功能已禁用
    # if not cleanup_thread.is_alive():
    #     cleanup_thread.start()
    #     log_message('info', "文件清理线程已启动")
    log_message('info', "文件清理功能已禁用")
    
    # 启动转录工作线程（确保只启动一次）
    if not worker_thread.is_alive():
        worker_thread.start()
        log_message('info', "转录工作线程已启动")
    
    # 启动Flask应用
    log_message('info', f"服务器启动，监听 {config.HOST}:{config.PORT}")
    socketio.run(app, host=config.HOST, port=config.PORT, debug=config.DEBUG)