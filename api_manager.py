import json
import os
import httpx
from typing import Dict, Any, Optional, List

class ApiManager:
    def __init__(self, data_path: str):
        self.data_path = data_path
        self.api_data_file = os.path.join(self.data_path, 'api_data.json')
        self.apis = self.load_apis()

    def load_apis(self) -> Dict[str, Any]:
        if not os.path.exists(self.api_data_file):
            return {}
        try:
            with open(self.api_data_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except (json.JSONDecodeError, FileNotFoundError):
            return {}

    def save_apis(self):
        with open(self.api_data_file, 'w', encoding='utf-8') as f:
            json.dump(self.apis, f, indent=4, ensure_ascii=False)

    def get_api(self, keyword: str) -> Optional[Dict[str, Any]]:
        return self.apis.get(keyword)

    def get_all_apis(self) -> Dict[str, Any]:
        return self.apis

    def add_api(self, keyword: str, api_info: Dict[str, Any]) -> bool:
        if keyword in self.apis:
            return False
        self.apis[keyword] = api_info
        self.save_apis()
        return True

    def remove_api(self, keyword: str) -> bool:
        if keyword in self.apis:
            del self.apis[keyword]
            self.save_apis()
            return True
        return False

    async def call_api(self, keyword: str, params: Optional[Dict[str, Any]] = None) -> Any:
        api_info = self.get_api(keyword)
        if not api_info:
            return None

        api_url = api_info.get('url')
        method = api_info.get('method', 'GET').upper()
        req_params = api_info.get('params', {})
        if params:
            req_params.update(params)

        try:
            async with httpx.AsyncClient() as client:
                if method == 'GET':
                    response = await client.get(api_url, params=req_params, follow_redirects=True)
                elif method == 'POST':
                    response = await client.post(api_url, json=req_params)
                else:
                    return None
                
                response.raise_for_status()

                api_type = api_info.get('type')
                if api_type in ['image', 'video', 'audio']:
                    return response.content
                
                # Handle JSON response with a target field
                if 'target' in api_info:
                    try:
                        json_data = response.json()
                        target_keys = api_info['target'].split('.')
                        data = json_data
                        for key in target_keys:
                            if isinstance(data, dict):
                                data = data.get(key)
                            elif isinstance(data, list) and key.isdigit():
                                data = data[int(key)]
                            else:
                                data = None
                                break
                        return data
                    except (json.JSONDecodeError, KeyError, IndexError):
                        return response.text # Fallback to text
                
                return response.text

        except httpx.RequestError as e:
            print(f"请求API {keyword} 出错: {e}")
            return None