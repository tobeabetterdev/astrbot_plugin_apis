import json
from pathlib import Path
from typing import Dict, Any, Optional, List


class APIManager:
    """
    API管理器，负责加载、添加、删除和获取API信息。
    """

    def __init__(self, api_file: Path):
        """
        初始化APIManager。

        :param api_file: api_data.json 文件路径。
        """
        self.api_file = api_file
        self.apis: Dict[str, Any] = self.load_apis()
        self.apis_names: List[str] = list(self.apis.keys())

    def load_apis(self) -> Dict[str, Any]:
        """
        从 api_data.json 文件加载API数据。

        :return: 包含API数据的字典。
        """
        try:
            with open(self.api_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except FileNotFoundError:
            # 文件不存在是正常情况，返回空字典
            return {}
        except json.JSONDecodeError as e:
            # JSON格式错误是严重问题，需要记录日志
            print(f"错误: api_data.json 文件格式错误，无法解析: {e}")
            return {}
        except Exception as e:
            print(f"错误: 加载api_data.json时发生未知错误: {e}")
            return {}

    def save_apis(self) -> None:
        """
        将当前的API数据保存到 api_data.json 文件。
        """
        with open(self.api_file, "w", encoding="utf-8") as f:
            json.dump(self.apis, f, ensure_ascii=False, indent=4)

    def add_api(self, api_info: Dict[str, Any]) -> None:
        """
        添加或更新一个API。

        :param api_info: 包含API信息的字典。
        """
        api_name = api_info.get("name")
        if api_name:
            self.apis[api_name] = api_info
            self.save_apis()
            self.apis_names = list(self.apis.keys())

    def remove_api(self, api_name: str) -> None:
        """
        根据API名称删除一个API。

        :param api_name: 要删除的API的名称。
        """
        if api_name in self.apis:
            del self.apis[api_name]
            self.save_apis()
            self.apis_names = list(self.apis.keys())

    def get_api_info(self, api_name: str) -> Optional[Dict[str, Any]]:
        """
        根据API名称获取API的详细信息。

        :param api_name: API的名称。
        :return: 包含API信息的字典，如果未找到则返回None。
        """
        return self.apis.get(api_name)

    def get_apis_names(self) -> List[str]:
        """
        获取所有API的名称列表。

        :return: 包含所有API名称的列表。
        """
        return self.apis_names

    def check_duplicate_api(self, api_name: str) -> bool:
        """
        检查API名称是否存在。

        :param api_name: 要检查的API名称。
        :return: 如果存在则返回True，否则返回False。
        """
        return api_name in self.apis
