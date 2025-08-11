# GPU内存管理优化说明

## 问题描述

在使用Ctrl+C终止Whisper转录应用时，GPU显存可能无法完全释放，导致后续运行时显存不足或系统资源浪费。

## 解决方案

### 1. 信号处理机制

应用程序现在包含了完整的信号处理机制，能够捕获以下信号：
- `SIGINT` (Ctrl+C)
- `SIGTERM` (终止信号)

### 2. 资源清理流程

当接收到终止信号时，应用程序会执行以下清理步骤：

#### 2.1 停止活动任务
```python
# 停止所有活动的转录任务
for task_id in list(active_transcriptions.keys()):
    task_info = active_transcriptions[task_id]
    gpu_ids = task_info.get('gpu_ids', [])
    
    # 释放GPU内存
    if gpu_ids:
        release_model_memory(gpu_ids)
    
    # 从活动转录中移除
    del active_transcriptions[task_id]
```

#### 2.2 清理模型缓存
```python
# 清理全局模型缓存
global models
models.clear()
```

#### 2.3 GPU内存清理
```python
# 强制垃圾回收
gc.collect()

# 清空所有GPU显存
if torch.cuda.is_available():
    for i in range(torch.cuda.device_count()):
        with torch.cuda.device(i):
            torch.cuda.empty_cache()
            torch.cuda.synchronize()
            torch.cuda.reset_peak_memory_stats(i)
            torch.cuda.reset_accumulated_memory_stats(i)
```

### 3. 改进的内存释放函数

`release_model_memory()` 函数已经过优化，包含以下改进：

```python
def release_model_memory(gpu_ids):
    try:
        # 强制垃圾回收
        gc.collect()
        
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
        
        # 额外的垃圾回收
        gc.collect()
        
    except Exception as e:
        log_message('error', f"释放显存失败: {e}")
```

### 4. 任务完成时的内存清理

每个转录任务完成后，都会执行彻底的内存清理：

```python
# 将模型移到CPU以释放GPU内存
if hasattr(model, 'to'):
    model.to('cpu')
del model

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
```

## 使用方法

### 正常启动应用
```bash
python app.py
```

### 安全终止应用
- 使用 `Ctrl+C` 终止应用
- 应用会自动执行资源清理
- 等待 "程序已安全退出" 消息

### 验证内存释放

可以使用提供的测试脚本验证内存管理：

```bash
# 测试信号处理
python test_signal_handling.py

# 测试GPU内存管理（如果有GPU）
python test_gpu_memory.py
```

## 监控GPU内存使用

### 使用nvidia-smi监控
```bash
# 实时监控GPU内存
nvidia-smi -l 1

# 查看详细GPU信息
nvidia-smi -q -d MEMORY
```

### 在Python中检查内存
```python
import torch

if torch.cuda.is_available():
    for i in range(torch.cuda.device_count()):
        allocated = torch.cuda.memory_allocated(i) / 1024**3  # GB
        reserved = torch.cuda.memory_reserved(i) / 1024**3   # GB
        print(f"GPU {i}: 已分配 {allocated:.2f}GB, 已保留 {reserved:.2f}GB")
```

## 故障排除

### 1. 显存仍未完全释放

如果在Ctrl+C后显存仍未完全释放，可以尝试：

```python
# 手动清理GPU内存
import torch
import gc

# 强制垃圾回收
for _ in range(5):
    gc.collect()

# 清空所有GPU缓存
if torch.cuda.is_available():
    for i in range(torch.cuda.device_count()):
        with torch.cuda.device(i):
            torch.cuda.empty_cache()
            torch.cuda.synchronize()
```

### 2. 应用无响应

如果应用在Ctrl+C后无响应：
- 等待几秒钟让清理过程完成
- 如果仍无响应，使用 `Ctrl+Z` 暂停进程，然后 `kill -9 <pid>` 强制终止

### 3. 检查信号处理是否工作

运行测试脚本验证信号处理：
```bash
python test_signal_handling.py
# 按Ctrl+C测试
```

## 最佳实践

1. **正常退出**: 始终使用Ctrl+C而不是强制终止进程
2. **监控内存**: 定期检查GPU内存使用情况
3. **适当的模型大小**: 根据GPU内存选择合适的模型
4. **批处理**: 避免同时运行过多转录任务

## 技术细节

### 信号处理器注册
```python
import signal
import sys

def signal_handler(signum, frame):
    log_message('info', f"接收到信号 {signum}，正在安全退出...")
    cleanup_resources()
    log_message('info', "程序已安全退出")
    sys.exit(0)

# 注册信号处理器
signal.signal(signal.SIGINT, signal_handler)  # Ctrl+C
signal.signal(signal.SIGTERM, signal_handler)  # 终止信号
```

### 内存清理的关键点
1. **模型移动**: 将模型从GPU移动到CPU后再删除
2. **多次垃圾回收**: 确保Python垃圾回收器彻底清理
3. **GPU同步**: 使用 `torch.cuda.synchronize()` 确保GPU操作完成
4. **统计重置**: 重置GPU内存统计以获得准确的内存使用信息

## 更新日志

- **v1.0**: 添加基本的信号处理和GPU内存清理
- **v1.1**: 改进内存释放函数，添加GPU内存统计重置
- **v1.2**: 增强任务完成时的内存清理机制
- **v1.3**: 添加测试脚本和详细文档

---

通过这些改进，Ctrl+C终止应用时的GPU显存释放问题已得到有效解决。如果仍遇到问题，请检查日志文件或运行测试脚本进行诊断。