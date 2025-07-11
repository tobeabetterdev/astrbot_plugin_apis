import asyncio
import json
import os
from pathlib import Path
import random
import re
import hashlib
from typing import Any, List, Optional, Union, Dict
from urllib.parse import unquote, urlparse

import aiohttp

from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star, register
import astrbot.api.message_components as Comp
from astrbot.api import logger
from astrbot.core.config.astrbot_config import AstrBotConfig
from astrbot.core.message.components import BaseMessageComponent
from astrbot.core.star.filter.event_message_type import EventMessageType

from data.plugins.astrbot_plugin_apis.api_manager import APIManager

# 定义缓存路径
DATA_PATH = Path("./data/plugins_data/astrbot_plugin_apis")
DATA_PATH.mkdir(parents=True, exist_ok=True)

# 定义子路径
TYPE_DIRS = {
    "text": DATA_PATH / "text",
    "image": DATA_PATH / "image",
    "video": DATA_PATH / "video",
    "audio": DATA_PATH / "audio",
}

api_file = (
    Path(__file__).parent / "api_data.json"
)  # api_data.json 文件路径，更新插件时会被覆盖


@register(
    "astrbot_plugin_apis",
    "tobeabetterdev",
    "API聚合插件，定制化功能整合，个人用",
    "1.0.0", # version up
    "https://github.com/tobeabetterdev/astrbot_plugin_apis",
)
class ArknightsPlugin(Star):
    def __init__(self, context: Context, config: AstrBotConfig):
        super().__init__(context)
        self.load_config(config)
        self.API = APIManager(api_file=api_file)
        self.apis_names = self.API.get_apis_names()

    def load_config(self, config: AstrBotConfig):
        self.wake_prefix: list[str] = self.context.get_config().get("wake_prefix", [])
        self.prefix_mode = config.get("prefix_mode", False)
        self.debug = config.get("debug", False)
        self.auto_save_data = config.get("auto_save_data", True)
        self.timeout = config.get("timeout", 20)
        
        type_switch = config.get("type_switch", {})
        self.disable_api_type = [
            "text" if not type_switch.get("enable_text", True) else None,
            "image" if not type_switch.get("enable_image", True) else None,
            "video" if not type_switch.get("enable_video", True) else None,
            "audio" if not type_switch.get("enable_audio", True) else None,
        ]
        self.disable_api = config.get("disable_api", [])

    @filter.command("api列表")
    async def api_ls(self, event: AstrMessageEvent):
        """ 根据API字典生成分类字符串,即api列表。 """
        api_types = {"text": [], "image": [], "video": [], "audio": []}
        for key, value in self.API.apis.items():
            api_type = value.get("type", "unknown")
            if api_type in api_types:
                api_types[api_type].append(key)

        result = f"----共收录了{len(self.API.apis)}个API----\n\n"
        for api_type, keywords in api_types.items():
            if keywords:
                result += f"【{api_type}】{len(keywords)}个：\n{'、'.join(keywords)}\n\n"
        yield event.plain_result(result.strip())

    @filter.command("api详情")
    async def api_help(self, event: AstrMessageEvent, api_name: str | None = None):
        """查看api的详细信息"""
        if not api_name:
            yield event.plain_result("请输入要查询的API名称。")
            return
            
        api_info = self.API.get_api_info(api_name)
        if not api_info:
            yield event.plain_result(f"未找到名为 '{api_name}' 的API。")
            return

        params = api_info.get("params", {})
        params_list = [f"{k}={v}" if v not in [None, ""] else k for k, v in params.items()]
        params_str = ",".join(params_list) if params_list else "无"

        api_str = (
            f"api名称：{api_info.get('name') or '无'}\n"
            f"api地址：{api_info.get('url') or '无'}\n"
            f"api类型：{api_info.get('type') or '无'}\n"
            f"所需参数：{params_str}\n"
            f"解析路径：{api_info.get('target') or '无'}"
        )
        yield event.plain_result(api_str)

    @filter.command("添加api")
    async def add_api(self, event: AstrMessageEvent, input_str: str | None = None):
        """添加api，格式: /添加api 名称：xxx 地址：xxx ..."""
        if not input_str:
            yield event.plain_result("请输入API信息。")
            return
        
        try:
            api_info = self._parse_api_input(input_str)
            name = api_info.get("name")

            if not name or not api_info.get("url"):
                yield event.plain_result("添加失败，'名称'和'地址'为必填项。")
                return

            if name in self.disable_api:
                yield event.plain_result(f"API '{name}' 已在禁用列表中，无法添加。")
                return

            if self.API.check_duplicate_api(name):
                yield event.plain_result(f"API '{name}' 已存在，将自动覆盖。")

            self.API.add_api(api_info)
            yield event.plain_result(f"【{name}】API添加/更新成功。")
        except Exception as e:
            if self.debug:
                logger.error(f"添加API失败: {e}")
            yield event.plain_result("添加失败，请检查格式。")
            
    def _parse_api_input(self, input_str: str) -> Dict[str, Any]:
        """从字符串解析API信息"""
        info_map = {"名称": "name", "地址": "url", "类型": "type", "参数": "params", "解析路径": "target"}
        api_info = {}
        parts = re.split(r'\s*(名称|地址|类型|参数|解析路径)：', '名称：' + input_str)
        
        it = iter(parts[1:])
        for key_zh in it:
            key_en = info_map.get(key_zh)
            value = next(it, "").strip()
            if key_en == "params":
                api_info[key_en] = self._parse_params_str(value)
            elif value:
                api_info[key_en] = value
        return api_info

    def _parse_params_str(self, params_str: str) -> dict:
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

    @filter.command("删除api")
    async def remove_api(self, event: AstrMessageEvent, api_name: str):
        """删除api"""
        if not api_name:
            yield event.plain_result("请输入要删除的API名称。")
            return
        self.API.remove_api(api_name)
        yield event.plain_result(f"已删除api：{api_name}")

    async def _make_request(self, url: str, params: Optional[dict] = None) -> Union[bytes, str, dict, None]:
        """发送GET请求"""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url=url, params=params, timeout=self.timeout) as response:
                    response.raise_for_status()
                    content_type = response.headers.get("Content-Type", "").lower()
                    if "application/json" in content_type:
                        return await response.json()
                    if "text/" in content_type:
                        return (await response.text()).strip()
                    return await response.read()
        except Exception as e:
            logger.error(f"请求异常: {url}, {e}")
            return None

    @filter.event_message_type(EventMessageType.ALL)
    async def match_api(self, event: AstrMessageEvent):
        """主处理函数"""
        msg_text = self._check_prefix(event)
        if msg_text is None:
            return

        msgs = msg_text.split(" ")
        api_name = next((i for i in self.apis_names if i == msgs[0]), None)
        if not self._is_api_enabled(api_name):
            return

        api_data = self.API.get_api_info(api_name)
        args = msgs[1:]
        update_params = await self._prepare_params(event, args, api_data.get("params", {}))
        
        if self.debug:
            logger.debug(f"请求API: {api_name}, 参数: {update_params}")

        data = await self._make_request(url=api_data.get("url"), params=update_params)

        if data is not None:
            chain = await self._process_api_data(data, api_name, api_data)
        else:
            logger.warning(f"API '{api_name}' 响应为空，尝试本地缓存。")
            chain = await self._get_data(api_name, api_data.get("type"))

        if chain:
            try:
                await event.send(event.chain_result(chain))
                event.stop_event()
            except Exception as e:
                logger.error(f"发送消息失败: {e}")
        elif self.debug:
            logger.debug(f"API '{api_name}' 无有效返回且无缓存。")
            
    def _check_prefix(self, event: AstrMessageEvent) -> Optional[str]:
        """检查前缀模式和消息有效性"""
        msg_text = event.get_message_str()
        if self.prefix_mode:
            if not event.is_prefix and not event.is_at:
                return None
            if event.is_prefix:
                for p in self.wake_prefix:
                    if msg_text.startswith(p):
                        return msg_text[len(p):].lstrip()
        elif msg_text.startswith('/'):
            return None
        return msg_text

    def _is_api_enabled(self, api_name: Optional[str]) -> bool:
        """检查API是否有效且未被禁用"""
        if not api_name or api_name in self.disable_api:
            return False
        api_type = self.API.get_api_info(api_name).get("type")
        if api_type in self.disable_api_type:
            if self.debug: logger.debug(f"API类型 '{api_type}' 已被禁用。")
            return False
        return True

    async def _prepare_params(self, event: AstrMessageEvent, args: list, params: dict) -> dict:
        """准备API请求参数"""
        final_args = args or await self._supplement_args(event)
        return {
            key: final_args[i] if i < len(final_args) else val
            for i, (key, val) in enumerate(params.items())
        }

    async def _supplement_args(self, event: AstrMessageEvent) -> list:
        """从上下文补充参数"""
        reply_seg = next((s for s in event.get_messages() if isinstance(s, Comp.Reply)), None)
        if reply_seg and reply_seg.chain:
            text = " ".join(s.text for s in reply_seg.chain if isinstance(s, Comp.Plain))
            if text.strip(): return text.strip().split(" ")

        at_seg = next((s for s in event.get_messages() if isinstance(s, Comp.At) and str(s.qq) != event.get_self_id()), None)
        if at_seg:
            # 实际应使用平台API获取昵称
            return [at_seg.display_text or str(at_seg.qq)]
            
        return [event.get_sender_name()]

    async def _process_api_data(self, data: Any, api_name: str, api_data: dict) -> List[BaseMessageComponent]:
        """处理API响应数据"""
        data_type = api_data.get("type")
        target = api_data.get("target")

        if isinstance(data, dict) and target:
            data = self._get_nested_value(data, target)

        if isinstance(data, str) and data_type != "text":
            url = self._extract_url(data)
            if url: data = await self._make_request(url)
            else: data = None

        if data is None: return []

        if self.auto_save_data:
            await self._save_data(data, api_name, data_type)
        
        return self._build_chain(data, data_type)

    def _build_chain(self, data: Any, data_type: str, from_local: bool = False) -> List[BaseMessageComponent]:
        """构建消息链"""
        if data_type == "text":
            return [Comp.Plain(str(data))]
        
        if from_local: # 本地数据是路径
            if data_type == "image": return [Comp.Image.fromFileSystem(data)]
            if data_type == "video": return [Comp.Video.fromFileSystem(data)]
            if data_type == "audio": return [Comp.Record.fromFileSystem(data)]
        elif isinstance(data, bytes): # 网络数据是字节
            if data_type == "image": return [Comp.Image.from_bytes(data)]
            if data_type == "video": return [Comp.Video.from_bytes(data)]
            if data_type == "audio": return [Comp.Record.from_bytes(data)]
        return []

    def _get_nested_value(self, result: dict, target: str) -> Any:
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

    @staticmethod
    def _extract_url(text: str) -> Optional[str]:
        """从字符串中提取第一个有效URL"""
        match = re.search(r"https?://[^\s\"']+", text.replace("\\", ""))
        if match:
            url = unquote(match.group(0).strip('"'))
            if urlparse(url).scheme in {"http", "https"}: return url
        return None

    async def _save_data(self, data: Union[str, bytes], path_name: str, data_type: str):
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

    async def _get_data(self, path_name: str, data_type: str) -> Optional[List[BaseMessageComponent]]:
        """从本地取出数据"""
        TYPE_DIR = TYPE_DIRS.get(data_type)
        if not TYPE_DIR: return None

        if data_type == "text":
            json_path = TYPE_DIR / f"{path_name}.json"
            if json_path.exists():
                try:
                    history = json.loads(json_path.read_text("utf-8"))
                    if history: return self._build_chain(random.choice(history), "text")
                except (json.JSONDecodeError, IndexError):
                    return None
        else:
            save_dir = TYPE_DIR / path_name
            if save_dir.is_dir():
                files = [f for f in save_dir.iterdir() if f.is_file()]
                if files:
                    return self._build_chain(str(random.choice(files)), data_type, from_local=True)
        return None