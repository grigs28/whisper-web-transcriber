#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
信号处理测试脚本
用于验证应用程序的Ctrl+C信号处理是否正常工作
"""

import signal
import sys
import time
import gc
import torch

def cleanup_resources():
    """
    清理资源函数
    """
    print("\n开始清理资源...")
    
    # 强制垃圾回收
    gc.collect()
    
    # 如果有GPU，清理GPU内存
    if torch.cuda.is_available():
        print(f"检测到 {torch.cuda.device_count()} 个GPU")
        for i in range(torch.cuda.device_count()):
            with torch.cuda.device(i):
                allocated_before = torch.cuda.memory_allocated(i) / 1024**2  # MB
                torch.cuda.empty_cache()
                torch.cuda.synchronize()
                allocated_after = torch.cuda.memory_allocated(i) / 1024**2   # MB
                print(f"GPU {i}: 清理前 {allocated_before:.1f}MB, 清理后 {allocated_after:.1f}MB")
        print("GPU内存已清理")
    else:
        print("未检测到GPU，跳过GPU内存清理")
    
    print("资源清理完成")

def signal_handler(signum, frame):
    """
    信号处理函数
    """
    print(f"\n接收到信号 {signum} (Ctrl+C)")
    print("正在安全退出...")
    
    cleanup_resources()
    
    print("程序已安全退出")
    sys.exit(0)

def main():
    """
    主函数
    """
    print("信号处理测试")
    print("=" * 30)
    
    # 注册信号处理器
    signal.signal(signal.SIGINT, signal_handler)   # Ctrl+C
    signal.signal(signal.SIGTERM, signal_handler)  # 终止信号
    
    print("信号处理器已注册")
    print("\n系统信息:")
    print(f"Python版本: {sys.version}")
    print(f"PyTorch版本: {torch.__version__}")
    print(f"CUDA可用: {torch.cuda.is_available()}")
    if torch.cuda.is_available():
        print(f"GPU数量: {torch.cuda.device_count()}")
        for i in range(torch.cuda.device_count()):
            print(f"GPU {i}: {torch.cuda.get_device_name(i)}")
    
    print("\n按 Ctrl+C 测试信号处理和资源清理")
    print("程序将运行30秒后自动退出...")
    
    # 运行30秒后自动退出
    try:
        for i in range(30):
            print(f"\r运行中... {30-i}秒后自动退出", end="", flush=True)
            time.sleep(1)
        
        print("\n\n30秒已到，程序正常退出")
        cleanup_resources()
        
    except KeyboardInterrupt:
        # 这里不应该被执行，因为信号处理器会处理Ctrl+C
        print("\n意外的KeyboardInterrupt")
        signal_handler(signal.SIGINT, None)

if __name__ == '__main__':
    main()