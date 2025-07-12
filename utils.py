import re
import random
from typing import Any, Optional, Dict
from urllib.parse import unquote, urlparse

def parse_params_str(params_str: str) -> dict:
    """解析参数字符串为字典"""
    params = {}
    if params_str:
        for pair in params_str.split(","):
            key_value = pair.split("=", 1)
            if len(key_value) == 2:
                params[key_value[0].strip()] = key_value[1].strip() or ""
            else:
                params[key_value[0].strip()] = None
    return params

def parse_api_input(input_str: str) -> Dict[str, Any]:
    """从字符串解析API信息"""
    info_map = {"名称": "name", "地址": "url", "类型": "type", "参数": "params", "解析路径": "target"}
    api_info = {}
    parts = re.split(r'\s*(名称|地址|类型|参数|解析路径)：', '名称：' + input_str)
    
    it = iter(parts[1:])
    for key_zh in it:
        key_en = info_map.get(key_zh)
        value = next(it, "").strip()
        if key_en == "params":
            api_info[key_en] = parse_params_str(value)
        elif value:
            api_info[key_en] = value
    return api_info

def get_nested_value(result: dict, target: str) -> Any:
    """安全地从嵌套字典中获取值"""
    try:
        keys = re.split(r'\.|(\[\d*\])', target)
        keys = [k.strip("[]") for k in keys if k and k.strip()]
        value = result
        for key in keys:
            if isinstance(value, list):
                value = random.choice(value) if key == "" else value[int(key)]
            else:
                value = value.get(key)
        return value
    except (KeyError, IndexError, TypeError, ValueError):
        return None

def extract_url(text: str) -> Optional[str]:
    """从字符串中提取第一个有效URL"""
    match = re.search(r"https?://[^\s\"']+", text.replace("\\", ""))
    if match:
        url = unquote(match.group(0).strip('"'))
        if urlparse(url).scheme in {"http", "https"}: return url
    return None