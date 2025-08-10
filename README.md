# Whisper 音频转录管理系统

基于Flask和SocketIO的现代化Web音频转录管理系统，支持拖拽上传、多GPU选择、实时队列管理、WebSocket实时通信和智能任务调度。

> 🤖 **AI开发说明**: 本项目完全由AI助手开发完成，使用Cline和Trae AI进行协作编程，展示了现代AI在复杂Web应用开发中的能力。

## 功能特性

### 🎯 核心功能
- ✅ **Web管理界面** - 现代化、响应式设计，支持Bootstrap UI框架
- ✅ **文件上传** - 支持拖拽批量添加文件和点击文件上传
- ✅ **智能队列管理** - 支持任务排队、状态跟踪和优先级处理
- ✅ **实时通信** - 基于WebSocket的实时状态更新和日志推送
- ✅ **GPU/CPU自适应** - 智能检测GPU可用性，支持多GPU选择

### 📊 任务管理
- ✅ **任务计时器** - 实时显示转录进度和已用时间
- ✅ **状态持久化** - 页面刷新后自动恢复任务状态和计时器
- ✅ **批量操作** - 支持多文件同时转录和批量停止
- ✅ **任务控制** - 支持单个或批量停止正在进行的转录任务

### 🔧 系统功能
- ✅ **文件管理** - 支持文件预览、下载和删除，文件列表采用等高布局设计
- ✅ **手动文件管理** - 支持单个和批量文件删除操作
- ✅ **日志系统** - 完整的日志记录和轮转机制
- ✅ **API支持** - 提供完整的RESTful API接口
- ✅ **错误处理** - 完善的错误处理和用户反馈机制

## 🖼️ 界面预览

### 主界面
![主界面](./screenshots/main-interface.png)
*现代化的Web界面，支持拖拽上传和实时状态显示*

## 系统要求

### 基础环境
- **Python**: 3.8+ (推荐 3.9+)
- **操作系统**: Windows 10+, Linux, macOS
- **内存**: 至少4GB RAM (GPU模式推荐8GB+)
- **存储**: 至少10GB 可用磁盘空间

### GPU支持 (可选)
- **CUDA**: 11.8+ 或 12.0+
- **显存**: 至少4GB VRAM (推荐8GB+)
- **驱动**: 最新的NVIDIA显卡驱动

### 网络要求
- 首次运行需要网络连接下载Whisper模型
- 模型文件大小约1-3GB (取决于选择的模型)

## 安装步骤

### 1. 克隆仓库
```bash
git clone https://github.com/grigs28/whisper-web-transcriber.git
cd whisper-web-transcriber
```

### 2. 创建虚拟环境
```bash
python -m venv venv
source venv/bin/activate  # Linux/Mac
# 或者在Windows上使用:
# venv\Scripts\activate
```

### 3. 安装依赖
```bash
pip install -r requirements.txt
```

### 4. 配置应用
复制配置模板并根据需要修改：
```bash
cp .env.sample .env
```

编辑 `.env` 文件配置应用参数（详见配置说明部分）：
```bash
# Windows: notepad .env
# Linux/Mac: nano .env 或 vim .env
```

### 5. 安装Whisper模型
首次运行前需要下载Whisper模型：
```bash
# 下载所需的模型（例如：large-v3）
python -c "import whisper; whisper.load_model('large-v3')"

# 或者让模型自动下载到指定目录
mkdir -p /opt/models/openai/
```

### 6. 运行应用
```bash
python app.py
```

## 使用方法

### 🚀 快速开始
1. 启动应用后访问 `http://127.0.0.1:5551`
2. 拖拽音频文件到上传区域或点击选择文件
3. 选择Whisper模型（tiny, base, small, medium, large）
4. 选择GPU设备（如果可用）
5. 点击"开始转录"按钮
6. 实时查看转录队列和进度
7. 在"转录结果"区域下载或管理文件

### 📋 队列管理
- **查看队列**: 实时显示所有任务的状态和进度
- **任务计时**: 自动显示每个任务的运行时间
- **批量控制**: 支持同时停止多个正在进行的任务
- **状态恢复**: 页面刷新后自动恢复任务状态

### 🎛️ 高级功能
- **多文件处理**: 支持批量上传和并发转录
- **实时日志**: WebSocket实时推送转录日志和状态
- **文件管理**: 支持文件预览、下载和批量删除
- **系统监控**: 实时显示GPU使用情况和系统状态

## API端点

### 🔄 转录相关
```http
# 添加文件到转录队列
POST /add_to_queue
Content-Type: multipart/form-data
Parameters:
- files[]: 音频文件数组
- model: Whisper模型名称 (tiny/base/small/medium/large)
- language: 语言代码 (可选)
- gpus: GPU ID列表，逗号分隔 (可选)

# 停止转录任务
POST /api/stop_transcription
Content-Type: application/json
Body: {"task_id": "任务ID"}
```

### 📊 状态和监控
```http
# 获取系统状态和队列信息
GET /api/status
Response: {
  "status": "ready/busy",
  "available_gpus": [...],
  "queue": [...],
  "active_tasks": 0,
  "queued_tasks": 0
}

# 获取任务进度
GET /api/progress/<task_id>
```

### 📁 文件管理
```http
# 获取上传文件列表
GET /api/uploaded_files

# 获取输出文件列表
GET /api/output_files

# 下载文件
GET /download/<filename>

# 删除文件
GET /delete/<filepath>
GET /delete_output/<filepath>
```

### 🔌 WebSocket连接
```javascript
// 连接到状态更新频道
const socket = io('/status');

// 监听事件
socket.on('task_update', (data) => { /* 任务状态更新 */ });
socket.on('log_message', (data) => { /* 日志消息 */ });
socket.on('system_message', (data) => { /* 系统消息 */ });
```

## 目录结构

```
whisper/
├── app.py                    # 主应用程序文件
├── config.py                 # 配置管理模块
├── .env.sample              # 配置模板文件
├── .env                     # 实际配置文件（需要创建）
├── requirements.txt          # Python依赖包列表
├── README.md                # 项目说明文档
├── .gitignore               # Git忽略文件列表
├── templates/
│   └── index.html           # Web界面HTML模板
├── static/                  # 静态资源文件
│   ├── css/                # 样式文件
│   │   ├── bootstrap.min.css
│   │   ├── fontawesome.min.css
│   │   ├── index.css       # 主要自定义样式（包含布局优化）
│   │   └── style.css       # 额外样式文件
│   ├── js/                 # JavaScript文件
│   │   ├── app.js          # 主要前端逻辑
│   │   ├── bootstrap.bundle.min.js
│   │   └── socket.io.min.js # WebSocket客户端
│   └── webfonts/           # 字体文件
├── screenshots/             # 界面截图文件
├── uploads/                 # 上传的音频文件存储
├── outputs/                 # 转录结果文件存储
├── logs/                    # 应用日志文件
│   └── app.log             # 应用日志（可配置）
├── venv/                    # Python虚拟环境 (可选)
└── /opt/models/openai/      # Whisper模型文件存储（可配置）
```

### 📁 重要文件说明

- **`config.py`**: 核心配置管理模块，负责加载环境变量、类型转换和配置验证
- **`.env.sample`**: 配置模板，包含所有可配置项的默认值和说明
- **`.env`**: 实际使用的配置文件，基于 `.env.sample` 创建并根据需要修改
- **`.gitignore`**: 确保敏感配置文件（如 `.env`）不被提交到版本控制

## 配置管理

### 📋 配置文件说明

本项目采用现代化的配置管理系统，支持环境变量配置和默认值管理：

- **`.env.sample`**: 配置模板文件，包含所有可配置项和说明
- **`.env`**: 实际配置文件，基于模板创建并根据需要修改
- **`config.py`**: 配置管理模块，负责加载和验证配置

### 🔧 配置步骤

1. **复制配置模板**：
```bash
cp .env.sample .env
```

2. **编辑配置文件**：
根据实际环境修改 `.env` 文件中的配置项。

### ⚙️ 主要配置项

#### 🖥️ 服务器配置
```env
# 应用密钥（生产环境请修改）
SECRET_KEY=your-secret-key-here

# 调试模式
DEBUG=False

# 监听地址和端口
HOST=0.0.0.0
PORT=5000
```

#### 📁 文件管理
```env
# 文件保存天数
MAX_FILE_AGE=30

# 最大文件大小（MB）
MAX_CONTENT_LENGTH=500

# 上传和输出目录
UPLOAD_FOLDER=uploads
OUTPUT_FOLDER=outputs
```

#### 🤖 模型配置
```env
# 模型存储路径
MODEL_BASE_PATH=/opt/models/openai

# 默认模型
DEFAULT_MODEL=large-v3

# 支持的模型列表（逗号分隔）
SUPPORTED_MODELS=tiny,base,small,medium,large,large-v2,large-v3
```

#### 🎮 GPU配置
```env
# 默认GPU ID（逗号分隔，0表示第一个GPU）
DEFAULT_GPU_IDS=0

# 最大GPU内存使用率
MAX_GPU_MEMORY=0.8
```

#### 🎵 转录设置
```env
# 默认语言（auto为自动检测）
DEFAULT_LANGUAGE=auto

# 最大并发转录数
MAX_CONCURRENT_TRANSCRIPTIONS=3

# 转录超时时间（秒）
TRANSCRIPTION_TIMEOUT=3600
```

#### 📝 日志配置
```env
# 日志级别
LOG_LEVEL=INFO

# 日志文件路径
LOG_FILE=logs/app.log

# 最大日志文件大小（字节）
MAX_LOG_SIZE=10485760

# 日志备份数量
LOG_BACKUP_COUNT=5
```

#### 🔌 WebSocket配置
```env
# WebSocket ping超时时间（秒）
WEBSOCKET_PING_TIMEOUT=60

# WebSocket ping间隔（秒）
WEBSOCKET_PING_INTERVAL=25
```

#### 🔒 安全配置
```env
# 允许的文件扩展名（逗号分隔）
ALLOWED_EXTENSIONS=wav,mp3,mp4,avi,mov,m4a,flac,ogg,wma,aac

# 最大文件名长度
MAX_FILENAME_LENGTH=255
```

#### ⚡ 性能配置
```env
# 工作线程数
WORKER_THREADS=4

# 清理间隔（秒）
CLEANUP_INTERVAL=3600

# 内存清理阈值
MEMORY_CLEANUP_THRESHOLD=0.9
```

### 🛠️ 配置验证

应用启动时会自动验证配置的有效性：
- 端口号范围检查（1-65535）
- 文件大小和保存天数验证
- 模型列表和默认模型检查
- GPU内存使用率范围验证

### 💡 配置最佳实践

1. **生产环境**：
   - 修改 `SECRET_KEY` 为随机字符串
   - 设置 `DEBUG=False`
   - 根据服务器性能调整并发数和内存阈值

2. **开发环境**：
   - 可以设置 `DEBUG=True` 启用调试模式
   - 使用较小的模型（如 `base`）加快测试速度

3. **资源受限环境**：
   - 减少 `MAX_CONCURRENT_TRANSCRIPTIONS`
   - 降低 `MAX_GPU_MEMORY` 使用率
   - 选择较小的模型

## 注意事项

### ⚠️ 重要提醒
1. **首次运行**: 系统会自动下载Whisper模型，需要稳定的网络连接
2. **文件管理**: 系统提供手动文件管理功能，支持单个和批量删除操作
3. **内存使用**: 大模型(large)需要更多内存，建议根据硬件选择合适的模型
4. **并发限制**: 系统支持队列管理，避免同时运行过多任务导致内存不足

### 📋 支持格式
- **音频格式**: MP3, MP4, WAV, OPUS, FLAC, M4A, WEBM, OGG
- **输出格式**: TXT文本文件
- **最大文件大小**: 500MB

### 🔧 性能优化
- **GPU模式**: 自动检测可用GPU，显著提升转录速度
- **CPU模式**: 无GPU时自动切换，确保系统正常运行
- **模型选择**: 
  - `tiny`: 最快，准确率较低
  - `base`: 平衡速度和准确率
  - `small`: 较好的准确率
  - `medium`: 高准确率
  - `large`: 最高准确率，需要更多资源

### 🛡️ 安全考虑
- 上传的文件和转录结果分别存储在不同的目录中
- 系统不会永久保存敏感音频文件
- 建议在生产环境中配置适当的访问控制

## 开发者指南

### 🏗️ 技术架构

**后端技术栈**:
- **Flask**: Web框架和API服务
- **Flask-SocketIO**: WebSocket实时通信
- **OpenAI Whisper**: 音频转录引擎
- **PyTorch**: 深度学习框架
- **Threading**: 多线程任务处理

**前端技术栈**:
- **Bootstrap 5**: 响应式UI框架
- **Socket.IO**: WebSocket客户端
- **Font Awesome**: 图标库
- **原生JavaScript**: 交互逻辑

### 📁 核心模块说明

**后端模块** (`app.py`):
- **应用初始化**: Flask应用和SocketIO配置
- **GPU管理**: 自动检测和管理GPU资源
- **队列系统**: 任务队列和状态管理
- **文件处理**: 上传、下载、删除操作
- **模型管理**: Whisper模型加载和内存管理
- **转录引擎**: 核心音频转录处理
- **API接口**: RESTful API和WebSocket事件
- **日志系统**: 完整的日志记录和轮转

**前端模块** (`static/js/app.js`):
- **文件上传**: 拖拽和点击上传功能
- **队列管理**: 实时队列状态显示
- **任务控制**: 开始、停止、批量操作
- **WebSocket通信**: 实时状态更新
- **UI交互**: 动态界面更新和用户反馈
- **布局优化**: 等高文件列表和统一间距响应式设计

### 🔧 关键特性实现

**队列管理系统**:
```python
# 线程安全的队列操作
with queue_lock:
    transcription_queue.append(task)
    
# 任务状态跟踪
active_transcriptions[task_id] = {
    'filename': filename,
    'status': 'processing',
    'start_time': datetime.now()
}
```

**WebSocket实时通信**:
```python
# 服务端事件发送
socketio.emit('task_update', {
    'task_id': task_id,
    'status': status,
    'message': message
}, namespace='/status')
```

**状态持久化**:
```javascript
// 页面刷新后恢复状态
function checkTranscriptionStatus() {
    fetch('/api/status')
        .then(response => response.json())
        .then(data => {
            // 恢复队列状态和计时器
        });
}
```

## 故障排除

### 🔍 常见问题

**安装和启动问题**:
1. **模块导入错误**: 确保使用`openai-whisper`而不是`whisper`包
2. **端口占用**: 默认端口5551被占用时，修改`app.py`中的端口配置
3. **权限错误**: 确保应用程序对`uploads/`、`outputs/`、`logs/`目录有读写权限

**模型和GPU问题**:
1. **模型下载失败**: 检查网络连接，确保能访问Hugging Face
2. **GPU内存不足**: 减少同时处理的文件数量或切换到较小的模型
3. **CUDA版本不兼容**: 确保PyTorch和CUDA版本匹配

**队列和任务问题**:
1. **任务卡住**: 检查日志文件，重启应用程序清空队列
2. **状态不同步**: 刷新页面或检查WebSocket连接
3. **计时器异常**: 确保浏览器支持WebSocket

### 📋 调试步骤

1. **检查日志**: 查看`logs/transcription.log`获取详细错误信息
2. **验证环境**: 确认Python版本和依赖包版本
3. **测试GPU**: 运行`torch.cuda.is_available()`检查GPU可用性
4. **网络检查**: 确保能正常访问模型下载地址

### 📊 性能监控

**系统资源监控**:
- CPU使用率和内存占用
- GPU显存使用情况
- 磁盘空间剩余量

**应用监控**:
- 队列长度和处理速度
- WebSocket连接状态
- 错误日志频率

### 🛠️ 配置优化

```python
# 在app.py中调整配置
MAX_FILE_AGE = 30          # 文件保留天数
MAX_CONTENT_LENGTH = 500   # 最大文件大小(MB)
MODEL_BASE_PATH = '/opt/models/openai'  # 模型存储路径
```

## 许可证

本项目根据MIT许可证发布。

## 贡献

欢迎提交Issue和Pull Request来帮助改进此项目。
pip install flask flask-socketio gevent torch torchaudio whisper