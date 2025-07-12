import json
import random
import hashlib
from pathlib import Path
from typing import Any, List, Optional, Union

import astrbot.api.message_components as Comp
from astrbot.core.message.components import BaseMessageComponent

# 定义缓存路径
DATA_PATH = Path("./data/plugins_data/astrbot_plugin_customize")
DATA_PATH.mkdir(parents=True, exist_ok=True)

# 定义子路径
TYPE_DIRS = {
    "text": DATA_PATH / "text",
    "image": DATA_PATH / "image",
    "video": DATA_PATH / "video",
    "audio": DATA_PATH / "audio",
}

class DataManager:
    def build_chain(self, data: Any, data_type: str, from_local: bool = False) -> List[BaseMessageComponent]:
        """构建消息链"""
        if data is None:
            return []
        if data_type == "text":
            return [Comp.Plain(str(data))]
        
        if from_local:  # 本地数据是路径
            if data_type == "image": return [Comp.Image.fromFileSystem(data)]
            if data_type == "video": return [Comp.Video.fromFileSystem(data)]
            if data_type == "audio": return [Comp.Record.fromFileSystem(data)]
        else:
            if data_type == "image":
                if isinstance(data, bytes): return [Comp.Image.fromBytes(data)]
                if isinstance(data, str): return [Comp.Image.fromURL(data)]
            if data_type == "video" and isinstance(data, str): return [Comp.Video.fromURL(data)]
            if data_type == "audio" and isinstance(data, str): return [Comp.Record.fromURL(data)]
        return []

    async def save_data(self, data: Union[str, bytes], path_name: str, data_type: str):
        """将数据保存到本地"""
        TYPE_DIR = TYPE_DIRS.get(data_type)
        if not TYPE_DIR: return
        TYPE_DIR.mkdir(parents=True, exist_ok=True)

        if data_type == "text":
            json_path = TYPE_DIR / f"{path_name}.json"
            try:
                history = json.loads(json_path.read_text("utf-8")) if json_path.exists() else []
            except json.JSONDecodeError:
                history = []
            
            clean_text = str(data).replace("\r", "\n")
            if clean_text not in history:
                history.append(clean_text)
                json_path.write_text(json.dumps(history, ensure_ascii=False, indent=4), "utf-8")
        elif isinstance(data, bytes):
            save_dir = TYPE_DIR / path_name
            save_dir.mkdir(parents=True, exist_ok=True)
            
            file_hash = hashlib.md5(data).hexdigest()
            extension = { "image": ".jpg", "audio": ".mp3", "video": ".mp4"}.get(data_type, ".dat")
            save_path = save_dir / f"{file_hash}{extension}"
            
            if not save_path.exists():
                save_path.write_bytes(data)

    async def get_data(self, path_name: str, data_type: str) -> Optional[List[BaseMessageComponent]]:
        """从本地取出数据"""
        TYPE_DIR = TYPE_DIRS.get(data_type)
        if not TYPE_DIR: return None

        if data_type == "text":
            json_path = TYPE_DIR / f"{path_name}.json"
            if json_path.exists():
                try:
                    history = json.loads(json_path.read_text("utf-8"))
                    if history: return self.build_chain(random.choice(history), "text")
                except (json.JSONDecodeError, IndexError):
                    return None
        else:
            save_dir = TYPE_DIR / path_name
            if save_dir.is_dir():
                files = [f for f in save_dir.iterdir() if f.is_file()]
                if files:
                    return self.build_chain(str(random.choice(files)), data_type, from_local=True)
        return None