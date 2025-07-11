import os
import json
import shutil
import random
import re
from pathlib import Path
from typing import Any, List, Dict, Optional
from urllib.parse import unquote, urlparse

import httpx
from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star, register
from astrbot.api import logger, astrbot_path
import astrbot.api.message_components as Comp

from .api_manager import ApiManager


@register("astrbot_plugin_apis", "Roo", "API聚合插件，参考Zhalslar实现", "1.1.0")
class AstrbotPluginApis(Star):
    def __init__(self, context: Context):
        super().__init__(context)
        # 路径设置
        self.plugin_data_path = os.path.join(astrobot_path.get_plugins_data_path(), "astrbot_plugin_apis")
        self.media_path = os.path.join(self.plugin_data_path, "media")
        os.makedirs(self.media_path, exist_ok=True)

        # 复制api_data.json
        source_api_data = os.path.join(os.path.dirname(__file__), 'api_data.json')
        dest_api_data = os.path.join(self.plugin_data_path, 'api_data.json')
        if not os.path.exists(dest_api_data) and os.path.exists(source_api_data):
            shutil.copy(source_api_data, dest_api_data)

        # 初始化管理器和配置
        self.api_manager = ApiManager(self.plugin_data_path)
        self.load_config()

    def load_config(self):
        """加载插件配置"""
        self.debug = self.config.get("debug", False)
        self.auto_save = self.config.get("auto_save_data", True)
        self.prefix_mode = self.config.get("prefix_mode", False)
        self.type_switch = self.config.get("type_switch", {})
        self.disabled_apis = self.config.get("disable_api", [])
        self.wake_prefix = self.context.get_config().get("wake_prefix", [])

    async def initialize(self):
        """插件初始化"""
        self.api_manager.apis = self.api_manager.load_apis() # Reload APIs on start
        logger.info("astrbot_plugin_apis Initialized.")

    # --- 指令 ---
    @filter.command("api列表")
    async def list_apis(self, event: AstrMessageEvent):
        """查看所有可用的API关键词"""
        apis = self.api_manager.get_all_apis()
        if not apis:
            yield event.plain_result("当前没有可用的API。")
            return

        api_by_type = {"text": [], "image": [], "video": [], "audio": []}
        for keyword, api_info in apis.items():
            api_type = api_info.get("type", "text")
            if api_type in api_by_type:
                api_by_type[api_type].append(keyword)

        response = f"---共收录了{len(apis)}个API---\n"
        for api_type, keywords in api_by_type.items():
            if keywords:
                response += f"\n【{api_type}】{len(keywords)}个：\n" + "、".join(keywords)
        
        yield event.plain_result(response)

    @filter.command("api详情")
    async def api_details(self, event: AstrMessageEvent):
        """查看API的详细信息。用法: /api详情 <关键词>"""
        keyword = event.message_str.strip()
        if not keyword:
            yield event.plain_result("请输入要查询的API关键词。用法: /api详情 <关键词>")
            return

        api = self.api_manager.get_api(keyword)
        if not api:
            yield event.plain_result(f"未找到关键词为 '{keyword}' 的API。")
            return

        params = api.get("params", {})
        params_list = [f"{k}={v}" if v not in [None, ""] else k for k, v in params.items()]
        params_str = ",".join(params_list) if params_list else "无"
        
        details = (
            f"关键词: {keyword}\n"
            f"名称: {api.get('name', '无')}\n"
            f"类型: {api.get('type', '无')}\n"
            f"URL: {api.get('url', '无')}\n"
            f"参数: {params_str}\n"
            f"目标: {api.get('target', '无')}"
        )
        yield event.plain_result(details)

    @filter.command("添加api")
    async def add_api_command(self, event: AstrMessageEvent):
        """添加一个新的API。用法: /添加api <关键词> <JSON格式的API信息>"""
        try:
            parts = event.message_str.strip().split(maxsplit=1)
            if len(parts) != 2:
                raise ValueError("格式错误，需要关键词和API信息。")
            
            keyword, api_info_str = parts
            api_info = json.loads(api_info_str)

            if self.api_manager.add_api(keyword, api_info):
                yield event.plain_result(f"API '{keyword}' 添加成功。")
            else:
                yield event.plain_result(f"API '{keyword}' 已存在。")
        except (json.JSONDecodeError, ValueError) as e:
            if self.debug:
                logger.error(f"添加API失败: {e}")
            yield event.plain_result(f"添加失败，请确保格式正确。")

    @filter.command("删除api")
    async def remove_api_command(self, event: AstrMessageEvent):
        """删除一个API。用法: /删除api <关键词>"""
        keyword = event.message_str.strip()
        if not keyword:
            yield event.plain_result("请输入要删除的API关键词。")
            return
        
        if self.api_manager.remove_api(keyword):
            yield event.plain_result(f"API '{keyword}' 删除成功。")
        else:
            yield event.plain_result(f"未找到关键词为 '{keyword}' 的API。")

    # --- 核心逻辑 ---
    @filter.on_message(priority=99)
    async def match_api_handler(self, event: AstrMessageEvent):
        """主API匹配和处理函数"""
        # 1. 检查前缀模式
        msg_text = event.get_message_str()
        if self.prefix_mode:
            if not event.is_prefix and not event.is_at:
                return
            if event.is_prefix:
                for p in self.wake_prefix:
                    if msg_text.startswith(p):
                        msg_text = msg_text[len(p):].lstrip()
                        break
        elif msg_text.startswith('/'):
            return

        # 2. 提取关键词和参数
        parts = msg_text.strip().split()
        keyword = parts[0]
        args = parts[1:]

        # 3. 检查API是否存在和是否被禁用
        api_info = self.api_manager.get_api(keyword)
        if not api_info or keyword in self.disabled_apis:
            return

        # 4. 检查API类型是否被禁用
        api_type = api_info.get('type', 'text')
        type_enabled_map = {
            "text": self.type_switch.get("enable_text", True),
            "image": self.type_switch.get("enable_image", True),
            "video": self.type_switch.get("enable_video", True),
            "audio": self.type_switch.get("enable_audio", True),
        }
        if not type_enabled_map.get(api_type, False):
            if self.debug: logger.info(f"API类型 '{api_type}' 已被禁用。")
            return

        # 5. 参数补充
        params = api_info.get('params', {})
        final_args = await self._supplement_args(event, args)
        
        update_params = {}
        param_keys = list(params.keys())
        for i, key in enumerate(param_keys):
            if i < len(final_args):
                update_params[key] = final_args[i]
            elif params[key] not in [None, ""]:
                update_params[key] = params[key]

        # 6. 调用API
        if self.debug: logger.debug(f"调用API '{keyword}'，参数: {update_params}")
        response_data = await self.api_manager.call_api(keyword, update_params)

        # 7. 处理响应
        if response_data is not None:
            chain = await self._process_api_response(keyword, api_type, response_data)
        else: # 尝试本地缓存
            if self.debug: logger.warning(f"API '{keyword}' 调用失败，尝试本地缓存。")
            chain = await self._get_local_data(keyword, api_type)

        # 8. 发送结果
        if chain:
            try:
                await event.send(event.chain_result(chain))
                event.stop_event()
            except Exception as e:
                logger.error(f"发送消息失败: {e}")
        elif self.debug:
            logger.info(f"API '{keyword}' 无有效返回且无本地缓存。")

    # --- 辅助函数 ---
    async def _supplement_args(self, event: AstrMessageEvent, args: List[str]) -> List[str]:
        """智能补充参数，从回复、@中提取"""
        if args:
            return args

        # 尝试从回复中提取
        reply_seg = next((s for s in event.get_messages() if isinstance(s, Comp.Reply)), None)
        if reply_seg and reply_seg.chain:
            text_in_reply = " ".join(s.text for s in reply_seg.chain if isinstance(s, Comp.Plain))
            if text_in_reply.strip():
                return text_in_reply.strip().split()

        # 尝试从@中提取
        at_seg = next((s for s in event.get_messages() if isinstance(s, Comp.At) and str(s.qq) != event.get_self_id()), None)
        if at_seg:
            # 此处简化，直接用@对象的昵称，实际可根据平台API获取
            return [at_seg.display_text or str(at_seg.qq)]
            
        # 使用发送者昵称
        return [event.get_sender_name()]

    async def _process_api_response(self, keyword: str, api_type: str, data: Any) -> List[Comp.BaseMessageComponent]:
        """处理API返回的数据，并决定是否缓存"""
        # 文本中提取URL
        if isinstance(data, str) and api_type != 'text':
            url = self._extract_url(data)
            if url:
                try:
                    async with httpx.AsyncClient() as client:
                        response = await client.get(url, follow_redirects=True, timeout=20)
                        response.raise_for_status()
                        data = response.content
                except Exception as e:
                    if self.debug: logger.error(f"从文本中提取URL后下载失败: {e}")
                    return []
        
        # 保存并创建消息链
        if self.auto_save:
            await self._save_data(keyword, api_type, data)

        if api_type == 'text':
            return [Comp.Plain(str(data))]
        elif isinstance(data, bytes):
            if api_type == 'image': return [Comp.Image.from_bytes(data)]
            if api_type == 'video': return [Comp.Video.from_bytes(data)]
            if api_type == 'audio': return [Comp.Audio.from_bytes(data)]
        return []

    async def _save_data(self, keyword: str, api_type: str, data: Any):
        """保存数据到本地文件系统"""
        type_path = os.path.join(self.media_path, api_type)
        os.makedirs(type_path, exist_ok=True)

        if api_type == 'text':
            file_path = os.path.join(type_path, f"{keyword}.json")
            try:
                history = json.loads(Path(file_path).read_text('utf-8')) if os.path.exists(file_path) else []
            except json.JSONDecodeError:
                history = []
            if str(data) not in history:
                history.append(str(data))
                Path(file_path).write_text(json.dumps(history, ensure_ascii=False, indent=4), 'utf-8')
        else:
            file_dir = os.path.join(type_path, keyword)
            os.makedirs(file_dir, exist_ok=True)
            ext = {"image": ".jpg", "video": ".mp4", "audio": ".mp3"}.get(api_type, ".dat")
            file_count = len(os.listdir(file_dir))
            file_path = os.path.join(file_dir, f"{keyword}_{file_count}{ext}")
            if isinstance(data, bytes):
                Path(file_path).write_bytes(data)

    async def _get_local_data(self, keyword: str, api_type: str) -> List[Comp.BaseMessageComponent]:
        """从本地缓存获取数据"""
        type_path = os.path.join(self.media_path, api_type)
        if not os.path.exists(type_path): return []

        if api_type == 'text':
            file_path = os.path.join(type_path, f"{keyword}.json")
            if os.path.exists(file_path):
                try:
                    history = json.loads(Path(file_path).read_text('utf-8'))
                    if history: return [Comp.Plain(random.choice(history))]
                except (json.JSONDecodeError, IndexError):
                    return []
        else:
            file_dir = os.path.join(type_path, keyword)
            if os.path.isdir(file_dir):
                files = os.listdir(file_dir)
                if files:
                    chosen_file = os.path.join(file_dir, random.choice(files))
                    if api_type == 'image': return [Comp.Image.from_file(chosen_file)]
                    if api_type == 'video': return [Comp.Video.from_file(chosen_file)]
                    if api_type == 'audio': return [Comp.Audio.from_file(chosen_file)]
        return []

    def _extract_url(self, text: str) -> Optional[str]:
        """从字符串中提取第一个有效URL"""
        try:
            text = text.replace("\\", "")
            match = re.search(r'https?://[^\s"\']+', text)
            if match:
                url = unquote(match.group(0).strip('"'))
                parsed = urlparse(url)
                if parsed.scheme in ["http", "https"] and parsed.netloc:
                    return url
        except Exception:
            return None
        return None

    async def terminate(self):
        """插件销毁"""
        logger.info("astrbot_plugin_apis Terminated.")
