# astrbot_plugin_apis

这是一个为 [AstrBot](https://github.com/Soulter/AstrBot) 设计的API聚合插件，其灵感和实现参考了 [astrbot_plugin_apis](https://github.com/Zhalslar/astrbot_plugin_apis)。

## 💡 功能

*   **动态API管理**: 通过指令动态添加、删除和查看API。
*   **多种返回类型**: 支持文本、图片、视频和音频类型的API。
*   **关键词触发**: 使用自定义的关键词轻松触发API调用。
*   **可配置**: 可在AstrBot面板中配置插件行为。

## 📦 安装

1.  将插件文件夹 `astrbot_plugin_apis` 放入 AstrBot 的 `data/plugins` 目录下。
2.  重启 AstrBot。

## ⌨️ 指令说明

| 命令 | 说明 |
| --- | --- |
| `/api列表` | 查看所有能触发api的关键词。 |
| `/api详情 <关键词>` | 具体查看某个api的参数。 |
| `/添加api <JSON>` | 添加指定api。JSON格式: `{"keyword": "xx", "api_url": "xx", ...}` |
| `/删除api <关键词>` | 删除指定api。 |
| `{关键词}` | 触发api。 |

## ⚙️ 配置

插件的配置可以在 AstrBot 的管理面板中找到：`插件管理 -> astrbot_plugin_apis -> 操作 -> 插件配置`。

可配置项：
*   **API请求超时**: 设置API请求的超时时间（秒）。
*   **启用本地缓存**: 当在线API请求失败时，是否使用本地缓存的媒体文件。

## 🤝 致谢

感谢 [Zhalslar](https://github.com/Zhalslar) 开发的 `astrbot_plugin_apis` 插件，为本项目提供了宝贵的参考。
