# GPU支持安装指南

## 安装PyTorch GPU版本

为了启用GPU加速功能，需要安装支持CUDA的PyTorch版本。

### 步骤1：卸载现有的CPU版本（如果已安装）
```bash
pip uninstall torch torchaudio -y
```

### 步骤2：安装CUDA版本的PyTorch

根据您的CUDA版本选择对应的安装命令：

**CUDA 11.8:**
```bash
pip install torch torchaudio --index-url https://download.pytorch.org/whl/cu118
```

**CUDA 12.1:**
```bash
pip install torch torchaudio --index-url https://download.pytorch.org/whl/cu121
```

**CUDA 12.4:**
```bash
pip install torch torchaudio --index-url https://download.pytorch.org/whl/cu124
```

### 步骤3：安装其他依赖
```bash
pip install -r requirements.txt
```

### 验证GPU支持
运行以下命令验证GPU是否可用：
```python
import torch
print('CUDA可用:', torch.cuda.is_available())
print('GPU数量:', torch.cuda.device_count())
if torch.cuda.is_available():
    print('GPU名称:', torch.cuda.get_device_name(0))
```

## 注意事项

- 确保系统已安装NVIDIA驱动程序
- 支持的CUDA版本：11.8及以上（推荐11.8、12.1、12.4）
- 如果遇到问题，请检查NVIDIA驱动程序版本是否兼容
- 可以使用 `nvidia-smi` 命令查看当前CUDA版本

## 故障排除

如果GPU检测失败：
1. 确认使用正确的虚拟环境
2. 重新安装PyTorch GPU版本
3. 检查NVIDIA驱动程序状态
4. 重启应用程序