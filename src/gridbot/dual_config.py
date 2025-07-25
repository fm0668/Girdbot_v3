"""
双账户配置管理
"""

import json
import os
from pathlib import Path
from dotenv import load_dotenv
from .models import DualAccountConfig

def load_dual_config(config_path: str) -> DualAccountConfig:
    """加载双账户配置"""
    # 加载.env文件
    load_dotenv()

    config_file = Path(config_path)

    if not config_file.exists():
        raise FileNotFoundError(f"配置文件不存在: {config_path}")

    with open(config_file, 'r', encoding='utf-8') as f:
        config_data = json.load(f)

    # 处理环境变量替换
    config_data = _replace_env_vars(config_data)

    return DualAccountConfig(**config_data)

def _replace_env_vars(config_data: dict) -> dict:
    """替换配置中的环境变量"""
    for key, value in config_data.items():
        if isinstance(value, str) and value.startswith('${') and value.endswith('}'):
            env_var = value[2:-1]  # 移除 ${ 和 }
            env_value = os.getenv(env_var)
            if env_value is None:
                raise ValueError(f"环境变量 {env_var} 未设置")
            config_data[key] = env_value
    
    return config_data
