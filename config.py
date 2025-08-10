import os
import logging
from pathlib import Path
from typing import List, Optional

class Config:
    """应用配置管理类"""
    
    def __init__(self):
        self.load_env_file()
        self._validate_config()
    
    def load_env_file(self):
        """加载.env文件"""
        env_file = Path('.env')
        if env_file.exists():
            with open(env_file, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith('#') and '=' in line:
                        key, value = line.split('=', 1)
                        os.environ.setdefault(key.strip(), value.strip())
    
    # Server Configuration
    @property
    def SECRET_KEY(self) -> str:
        return os.getenv('SECRET_KEY', 'your-secret-key-here')
    
    @property
    def DEBUG(self) -> bool:
        return os.getenv('DEBUG', 'False').lower() in ('true', '1', 'yes')
    
    @property
    def HOST(self) -> str:
        return os.getenv('HOST', '0.0.0.0')
    
    @property
    def PORT(self) -> int:
        return int(os.getenv('PORT', 5000))
    
    # File Management
    @property
    def MAX_FILE_AGE(self) -> int:
        return int(os.getenv('MAX_FILE_AGE', 30))
    
    @property
    def MAX_CONTENT_LENGTH(self) -> int:
        return int(os.getenv('MAX_CONTENT_LENGTH', 500)) * 1024 * 1024
    
    @property
    def UPLOAD_FOLDER(self) -> str:
        return os.getenv('UPLOAD_FOLDER', 'uploads')
    
    @property
    def OUTPUT_FOLDER(self) -> str:
        return os.getenv('OUTPUT_FOLDER', 'outputs')
    
    # Model Configuration
    @property
    def MODEL_BASE_PATH(self) -> str:
        return os.getenv('MODEL_BASE_PATH', '/opt/models/openai')
    
    @property
    def DEFAULT_MODEL(self) -> str:
        return os.getenv('DEFAULT_MODEL', 'large-v3')
    
    @property
    def SUPPORTED_MODELS(self) -> List[str]:
        models_str = os.getenv('SUPPORTED_MODELS', 'tiny,base,small,medium,large,large-v2,large-v3')
        return [model.strip() for model in models_str.split(',')]
    
    # GPU Configuration
    @property
    def DEFAULT_GPU_IDS(self) -> List[int]:
        gpu_ids_str = os.getenv('DEFAULT_GPU_IDS', '0')
        return [int(gpu_id.strip()) for gpu_id in gpu_ids_str.split(',') if gpu_id.strip()]
    
    @property
    def MAX_GPU_MEMORY(self) -> float:
        return float(os.getenv('MAX_GPU_MEMORY', 0.8))
    
    # Transcription Settings
    @property
    def DEFAULT_LANGUAGE(self) -> str:
        return os.getenv('DEFAULT_LANGUAGE', 'auto')
    
    @property
    def MAX_CONCURRENT_TRANSCRIPTIONS(self) -> int:
        return int(os.getenv('MAX_CONCURRENT_TRANSCRIPTIONS', 3))
    
    @property
    def TRANSCRIPTION_TIMEOUT(self) -> int:
        return int(os.getenv('TRANSCRIPTION_TIMEOUT', 3600))
    
    # Logging
    @property
    def LOG_LEVEL(self) -> str:
        return os.getenv('LOG_LEVEL', 'INFO')
    
    @property
    def LOG_FILE(self) -> str:
        return os.getenv('LOG_FILE', 'logs/app.log')
    
    @property
    def MAX_LOG_SIZE(self) -> int:
        return int(os.getenv('MAX_LOG_SIZE', 10485760))
    
    @property
    def LOG_BACKUP_COUNT(self) -> int:
        return int(os.getenv('LOG_BACKUP_COUNT', 5))
    
    # WebSocket Configuration
    @property
    def WEBSOCKET_PING_TIMEOUT(self) -> int:
        return int(os.getenv('WEBSOCKET_PING_TIMEOUT', 60))
    
    @property
    def WEBSOCKET_PING_INTERVAL(self) -> int:
        return int(os.getenv('WEBSOCKET_PING_INTERVAL', 25))
    
    # Security
    @property
    def ALLOWED_EXTENSIONS(self) -> List[str]:
        extensions_str = os.getenv('ALLOWED_EXTENSIONS', 'wav,mp3,mp4,avi,mov,m4a,flac,ogg,wma,aac')
        return [ext.strip().lower() for ext in extensions_str.split(',')]
    
    @property
    def MAX_FILENAME_LENGTH(self) -> int:
        return int(os.getenv('MAX_FILENAME_LENGTH', 255))
    
    # Performance
    @property
    def WORKER_THREADS(self) -> int:
        return int(os.getenv('WORKER_THREADS', 4))
    
    @property
    def CLEANUP_INTERVAL(self) -> int:
        return int(os.getenv('CLEANUP_INTERVAL', 3600))
    
    @property
    def MEMORY_CLEANUP_THRESHOLD(self) -> float:
        return float(os.getenv('MEMORY_CLEANUP_THRESHOLD', 0.9))
    
    def _validate_config(self):
        """验证配置的有效性"""
        if self.PORT < 1 or self.PORT > 65535:
            raise ValueError(f"Invalid port number: {self.PORT}")
        
        if self.MAX_FILE_AGE < 1:
            raise ValueError(f"MAX_FILE_AGE must be positive: {self.MAX_FILE_AGE}")
        
        if self.MAX_CONTENT_LENGTH < 1024 * 1024:  # 至少1MB
            raise ValueError(f"MAX_CONTENT_LENGTH too small: {self.MAX_CONTENT_LENGTH}")
        
        if not self.SUPPORTED_MODELS:
            raise ValueError("SUPPORTED_MODELS cannot be empty")
        
        if self.DEFAULT_MODEL not in self.SUPPORTED_MODELS:
            raise ValueError(f"DEFAULT_MODEL '{self.DEFAULT_MODEL}' not in SUPPORTED_MODELS")
        
        if self.MAX_GPU_MEMORY <= 0 or self.MAX_GPU_MEMORY > 1:
            raise ValueError(f"MAX_GPU_MEMORY must be between 0 and 1: {self.MAX_GPU_MEMORY}")
    
    def get_log_config(self) -> dict:
        """获取日志配置"""
        return {
            'level': getattr(logging, self.LOG_LEVEL.upper()),
            'filename': self.LOG_FILE,
            'maxBytes': self.MAX_LOG_SIZE,
            'backupCount': self.LOG_BACKUP_COUNT,
            'format': '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        }
    
    def __repr__(self):
        return f"<Config DEBUG={self.DEBUG} HOST={self.HOST} PORT={self.PORT}>"

# 全局配置实例
config = Config()