#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试改进后的信号处理机制
验证是否能避免核心转储问题
"""

import signal
import sys
import os
import time
import threading
import gc

# 模拟活动任务字典
active_tasks = {}
task_counter = 0
queue_lock = threading.Lock()

def log_message(message):
    """简单的日志函数"""
    timestamp = time.strftime('%Y-%m-%d %H:%M:%S')
    print(f"[{timestamp}] {message}")

def simulate_task(task_id):
    """模拟一个长时间运行的任务"""
    global active_tasks
    active_tasks[task_id] = {
        'start_time': time.time(),
        'stop_flag': False
    }
    
    log_message(f"任务 {task_id} 开始执行")
    
    # 模拟长时间运行的任务
    for i in range(100):
        if active_tasks[task_id].get('stop_flag', False):
            log_message(f"任务 {task_id} 收到停止信号，正在退出")
            break
        
        time.sleep(0.1)  # 模拟工作
        if i % 20 == 0:
            log_message(f"任务 {task_id} 进度: {i}%")
    
    # 清理任务
    if task_id in active_tasks:
        del active_tasks[task_id]
    log_message(f"任务 {task_id} 已完成")

def cleanup_resources():
    """
    清理所有资源
    """
    try:
        log_message("开始清理资源...")
        
        # 设置所有任务的停止标志
        global active_tasks
        for task_id in list(active_tasks.keys()):
            try:
                task_info = active_tasks[task_id]
                task_info['stop_flag'] = True
                log_message(f"任务 {task_id} 停止标志已设置")
            except Exception as e:
                log_message(f"设置任务 {task_id} 停止标志时出错: {e}")
        
        # 等待任务完成
        max_wait = 5  # 最多等待5秒
        wait_time = 0
        while active_tasks and wait_time < max_wait:
            time.sleep(0.1)
            wait_time += 0.1
        
        # 强制清理剩余任务
        if active_tasks:
            log_message(f"强制清理剩余任务: {list(active_tasks.keys())}")
            active_tasks.clear()
        
        # 垃圾回收
        gc.collect()
        
        # 等待清理完成
        time.sleep(0.5)
        
        log_message("资源清理完成")
        
    except Exception as e:
        log_message(f"资源清理时出错: {e}")

def signal_handler(signum, frame):
    """
    改进的信号处理函数
    """
    log_message(f"接收到信号 {signum}，正在安全退出...")
    cleanup_resources()
    
    log_message("程序已安全退出")
    
    # 使用os._exit而不是sys.exit，避免在多线程环境中的问题
    os._exit(0)

def main():
    """主函数"""
    global task_counter
    
    # 注册信号处理器
    signal.signal(signal.SIGINT, signal_handler)  # Ctrl+C
    if hasattr(signal, 'SIGTERM'):
        signal.signal(signal.SIGTERM, signal_handler)  # 终止信号
    
    log_message("改进的信号处理器已注册")
    log_message("启动多个模拟任务...")
    
    # 启动多个模拟任务
    threads = []
    for i in range(3):
        task_counter += 1
        task_id = f"task_{task_counter}"
        thread = threading.Thread(target=simulate_task, args=(task_id,), daemon=True)
        thread.start()
        threads.append(thread)
    
    log_message(f"已启动 {len(threads)} 个任务")
    log_message("按 Ctrl+C 测试信号处理...")
    
    try:
        # 主循环
        while True:
            time.sleep(1)
            if not active_tasks:
                log_message("所有任务已完成，程序将自动退出")
                break
            else:
                log_message(f"当前活动任务: {list(active_tasks.keys())}")
    
    except KeyboardInterrupt:
        # 这个不应该被触发，因为我们有信号处理器
        log_message("KeyboardInterrupt 被捕获（这不应该发生）")
        signal_handler(signal.SIGINT, None)

if __name__ == "__main__":
    log_message("=== 改进的信号处理测试 ===")
    log_message(f"Python版本: {sys.version}")
    log_message(f"进程ID: {os.getpid()}")
    main()