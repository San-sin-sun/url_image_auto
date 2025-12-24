# astrbot_plugin_url_image_auto

## 简介
这是一个 AstrBot 插件，用于自动将发送消息中的图片链接转换为 AstrBot 的原生图片组件。
支持 Markdown 图片语法、CQ 码图片语法以及直接发送的图片 URL。

适用于：
- 通过 LLM 输出 Markdown 图片格式时，自动转为图片发送。
- 用户或 bot 发送裸链接时，若确认为图片（后缀匹配或白名单），自动转为图片。
- 随机图 API 的 seed 参数自动随机化（防止缓存）。

## 功能特性
1. **自动识别 Markdown 图片**：`![alt](url)` -> 图片组件
2. **自动识别 CQ 码图片**：`[CQ:image,file=url]` -> 图片组件
3. **裸链接识别**：
   - 根据后缀名 (`.png`, `.jpg` 等) 自动识别。
   - 支持自定义白名单域名/路径（如随机图 API）。
4. **随机数优化**：针对某些随机图 API，自动替换 URL 中的 `seed=random` 等参数为随机数字，确保每次获取不同图片。

## 配置说明
插件加载后，可在 AstrBot 管理面板的插件配置中修改以下设置：

| 配置项 | 类型 | 说明 | 默认值 |
| :--- | :--- | :--- | :--- |
| `extensions` | 列表 | 被视为图片的 URL 后缀名 | `.png`, `.jpg`, ... |
| `whitelist_rules` | 列表 | 白名单规则，匹配的域名/路径强制视为图片 | (默认包含一个示例 API) |
| `convert_markdown` | 布尔 | 是否转换 Markdown 图片 | `true` |
| `convert_cq_code` | 布尔 | 是否转换 CQ 码图片 | `true` |
| `randomize_seed` | 布尔 | 是否自动处理 `seed` 参数 | `true` |

### 白名单规则示例
```json
[
  {
    "host": "your.api.com",
    "path_chars": "/random/image"
  }
]
```

## 安装
1. 将本项目克隆至 `AstrBot/data/plugins/url_image_auto` 目录。
2. 重启 AstrBot。
3. 在管理面板启用插件。
