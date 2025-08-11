#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
GPU内存管理测试脚本
用于验证Ctrl+C信号处理和GPU内存释放是否有效
"""

import torch
import gc
import time
import signal
import sys
import os
from config import config

def get_gpu_memory_info():
    """获取GPU内存使用信息"""
    if not torch.cuda.is_available():
        return "GPU不可用"
    
    info = []
    for i in range(torch.cuda.device_count()):
        allocated = torch.cuda.memory_allocated(i) / 1024**3  # GB
        reserved = torch.cuda.memory_reserved(i) / 1024**3   # GB
        total = torch.cuda.get_device_properties(i).total_memory / 1024**3  # GB
        info.append(f"GPU {i}: 已分配 {allocated:.2f}GB, 已保留 {reserved:.2f}GB, 总计 {total:.2f}GB")
    return "\n".join(info)

def get_system_memory_info():
    """获取系统内存使用信息"""
    try:
        import psutil
        memory = psutil.virtual_memory()
        return f"系统内存: 已使用 {memory.used / 1024**3:.2f}GB / 总计 {memory.total / 1024**3:.2f}GB ({memory.percent:.1f}%)"
    except ImportError:
        return "系统内存: psutil未安装，无法获取详细信息"

def cleanup_gpu_memory():
    """清理GPU内存"""
    try:
        print("开始清理GPU内存...")
        
        # 强制垃圾回收
        for _ in range(3):
            gc.collect()
        
        # 清空所有GPU显存
        if torch.cuda.is_available():
            for i in range(torch.cuda.device_count()):
                with torch.cuda.device(i):
                    torch.cuda.empty_cache()
                    torch.cuda.synchronize()
                    torch.cuda.reset_peak_memory_stats(i)
                    torch.cuda.reset_accumulated_memory_stats(i)
            print("GPU内存已清理")
        
        # 再次垃圾回收
        gc.collect()
        
    except Exception as e:
        print(f"清理GPU内存时出错: {e}")

def signal_handler(signum, frame):
    """信号处理函数"""
    print(f"\n接收到信号 {signum}，正在清理资源...")
    
    print("\n清理前的内存状态:")
    print(get_gpu_memory_info())
    print(get_system_memory_info())
    
    cleanup_gpu_memory()
    
    print("\n清理后的内存状态:")
    print(get_gpu_memory_info())
    print(get_system_memory_info())
    
    print("\n资源清理完成，程序退出")
    sys.exit(0)

def simulate_model_loading():
    """模拟模型加载和使用"""
    print("模拟加载Whisper模型...")
    
    try:
        # 创建一些张量来模拟模型占用GPU内存
        if torch.cuda.is_available():
            device = torch.device('cuda:0')
            # 创建一些大张量模拟模型权重
            tensors = []
            for i in range(5):
                tensor = torch.randn(1000, 1000, device=device)
                tensors.append(tensor)
                print(f"创建张量 {i+1}/5")
                time.sleep(0.5)
            
            print("\n模型加载完成，内存状态:")
            print(get_gpu_memory_info())
            print(get_system_memory_info())
            
            # 模拟处理过程
            print("\n模拟处理过程...")
            for i in range(10):
                if i % 2 == 0:
                    print(f"处理进度: {(i+1)*10}%")
                    print(get_gpu_memory_info())
                time.sleep(1)
            
            # 手动清理张量
            print("\n手动清理张量...")
            for tensor in tensors:
                tensor.to('cpu')
                del tensor
            del tensors
            
            cleanup_gpu_memory()
            
            print("\n手动清理后的内存状态:")
            print(get_gpu_memory_info())
            print(get_system_memory_info())
            
        else:
            print("GPU不可用，使用CPU模式")
            time.sleep(10)
            
    except Exception as e:
        print(f"模拟过程中出错: {e}")

def main():
    """主函数"""
    print("GPU内存管理测试脚本")
    print("=" * 50)
    
    # 注册信号处理器
    signal.signal(signal.SIGINT, signal_handler)   # Ctrl+C
    signal.signal(signal.SIGTERM, signal_handler)  # 终止信号
    
    print("信号处理器已注册")
    print("按 Ctrl+C 测试信号处理和内存清理")
    print("=" * 50)
    
    print("\n初始内存状态:")
    print(get_gpu_memory_info())
    print(get_system_memory_info())
    
    # 模拟模型加载和使用
    simulate_model_loading()
    
    print("\n测试完成，程序将继续运行...")
    print("按 Ctrl+C 测试信号处理")
    
    # 保持程序运行
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        signal_handler(signal.SIGINT, None)

if __name__ == '__main__':
    main()