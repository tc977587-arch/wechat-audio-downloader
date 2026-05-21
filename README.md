# WeChat Audio Downloader

![Python](https://img.shields.io/badge/python-%3E%3D3.10-2ea44f?style=for-the-badge&labelColor=555555)
![Platform](https://img.shields.io/badge/platform-macOS%20%7C%20Linux%20%7C%20Windows-2ea44f?style=for-the-badge&labelColor=555555)
![License](https://img.shields.io/badge/license-MIT-4c8f7a?style=for-the-badge&labelColor=555555)

一个简单易用的微信公众号音频下载工具。输入微信公众号文章链接或合集链接，即可提取文章中的音频，并自动保存到本机下载文件夹。

支持单篇文章下载，也支持公众号合集批量下载。合集模式会逐个解析分集文章，并按照顺序命名音频文件。

## 功能特点

- 支持微信公众号单篇文章音频提取
- 支持微信公众号合集批量下载
- 合集音频自动保存到独立文件夹
- 自动按顺序命名，例如 `001 - 标题.mp3`
- 支持常见公众号音频组件
- 支持 macOS Python 证书异常兜底
- 仅依赖 Python 标准库，无需额外安装第三方包

## 环境要求

- Python 3.10 或更高版本
- macOS / Linux / Windows 均可运行

## 快速开始

下载脚本后，在终端运行：

```bash
python3 wechat_audio_extractor.py
```

程序会提示选择解析模式：

```text
请选择解析模式：
1. 单篇/分集链接：直接提取当前文章里的音频
2. 合集链接：先提取合集里的所有分集，再逐集下载音频
请输入 1 或 2:
```

选择后粘贴对应的微信公众号链接即可。

## 命令行用法

下载单篇文章或分集音频：

```bash
python3 wechat_audio_extractor.py --mode 1 "https://mp.weixin.qq.com/s/..."
```

下载公众号合集里的所有分集音频：

```bash
python3 wechat_audio_extractor.py --mode 2 "https://mp.weixin.qq.com/mp/appmsgalbum?..."
```

指定保存目录：

```bash
python3 wechat_audio_extractor.py --mode 1 "文章链接" -o "/path/to/save"
```

## 保存规则

默认保存到系统下载文件夹：

```text
~/Downloads
```

单篇文章会保存为：

```text
文章标题.mp3
```

合集会创建一个独立文件夹，并按顺序保存：

```text
合集标题/
├── 001 - 第一集标题.mp3
├── 002 - 第二集标题.mp3
├── 003 - 第三集标题.mp3
```

## Cookie 支持

部分公众号文章或合集需要微信网页登录态。如果页面在浏览器中能看到音频，但脚本提示无法解析，可以尝试传入 Cookie：

```bash
python3 wechat_audio_extractor.py --mode 1 "文章链接" --cookie "你的 Cookie"
```

也可以使用环境变量：

```bash
export WECHAT_COOKIE="你的 Cookie"
python3 wechat_audio_extractor.py --mode 1 "文章链接"
```

## 常见问题

### 提示证书校验失败怎么办？

如果看到类似提示：

```text
本机 Python 证书库校验失败，已临时跳过 HTTPS 证书校验重试。
```

通常是 macOS Python 证书库不完整导致的。脚本会自动兜底重试，一般不影响使用。

如果想彻底修复，可以在 macOS 中找到 Python 安装目录，并运行：

```text
Install Certificates.command
```

### 页面有音频，但脚本提示没有找到

可能原因包括：

- 音频由微信登录态接口动态加载
- 文章需要登录、关注或微信客户端环境
- 公众号页面结构发生变化
- 链接复制的是合集页，但运行时选择了单篇模式

可以先确认链接在浏览器中能正常打开，再尝试传入 Cookie。

### 合集模式没有解析到分集

部分合集页面会通过微信客户端或登录态动态加载分集列表。可以尝试：

- 确认输入的是合集链接，而不是单篇文章链接
- 在浏览器中打开合集后复制完整 URL
- 使用 `--cookie` 参数提供登录态

## 注意事项

本项目仅用于学习、研究和下载自己有权访问的公开音频内容。使用者应遵守微信公众号平台规则、相关网站服务条款以及版权法律法规。

请勿将本工具用于批量抓取、商业转载、侵犯版权或其他未经授权的用途。

## License

MIT License
