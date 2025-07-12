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

from data.plugins.astrbot_plugin_customize.api_manager import APIManager
from data.plugins.astrbot_plugin_customize.data_manager import DataManager
import data.plugins.astrbot_plugin_customize.utils as utils

api_file = (
    Path(__file__).parent / "api_data.json"
)  # api_data.json 文件路径，更新插件时会被覆盖


@register(
    "astrbot_plugin_customize",
    "tobeabetterdev",
    "[wechatpadpro]API聚合插件，定制化功能整合，个人用",
    "1.0.0",
    "https://github.com/tobeabetterdev/astrbot_plugin_customize",
)
class AstrbotPluginCustomize(Star):
    def __init__(self, context: Context, config: AstrBotConfig):
        super().__init__(context)
        self.load_config(config)
        self.API = APIManager(api_file=api_file)
        self.apis_names = self.API.get_apis_names()
        self.data_manager = DataManager()

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
            api_info = utils.parse_api_input(input_str)
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
                        try:
                            return await response.json()
                        except json.JSONDecodeError:
                            return await response.text()
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
            chain = await self.data_manager.get_data(api_name, api_data.get("type"))

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
        update_params = dict(params)  # Start with default params

        # If user provided arguments, they override defaults in order
        if args:
            for i, key in enumerate(update_params.keys()):
                if i < len(args):
                    update_params[key] = args[i]
            return update_params

        # If no user args, supplement only for params that are placeholders (empty/None)
        supplemented_args = await self._supplement_args(event)
        for i, (key, val) in enumerate(params.items()):
            if val in [None, ""] and i < len(supplemented_args):
                update_params[key] = supplemented_args[i]

        return update_params

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
            data = utils.get_nested_value(data, target)

        if data is None:
            return []

        if isinstance(data, str) and data_type != "text":
            url = utils.extract_url(data)
            if url:
                bytes_data = await self._make_request(url)
                if bytes_data is None:
                    # 如果下载失败，尝试使用原始URL
                    return self.data_manager.build_chain(api_data.get("url"), data_type)
                
                if self.auto_save_data:
                    await self.data_manager.save_data(bytes_data, api_name, data_type)

                # 根据数据类型决定构建消息链的数据
                if data_type == "image":
                    return self.data_manager.build_chain(bytes_data, data_type)
                else: # 对于视频/音频，使用URL构建
                    return self.data_manager.build_chain(url, data_type)
            else:
                # 如果没有可提取的URL，则认为数据无效
                return []

        # 对于文本类型或非字符串的二进制数据
        if self.auto_save_data:
            await self.data_manager.save_data(data, api_name, data_type)

        return self.data_manager.build_chain(data, data_type)
