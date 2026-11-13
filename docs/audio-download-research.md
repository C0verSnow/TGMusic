# Issue #5：YouTube 歌曲下载调研

调研日期：2026-11-13。已在 GitHub 检索 `yt-dlp in:name`、`pytubefix in:name`，再核对项目自己的代码、发布记录、Issue、文档和 PyPI 元数据；没有复制开源项目代码，没有安装依赖或进行本地编译、测试、冒烟验证。

## 选择

建议把 `src/audio_resolver.py` 的音源获取交给 **yt-dlp**，继续使用现有 FFmpeg 转成 MP3/M4A，继续只处理已授权的视频 ID，失败时继续发原曲链接。以下是结合仓库现有结构作出的选择，不代表已验证目标歌曲一定可下载。

| 项目 | 活跃度与许可证 | 做法与依赖 | 对本仓库的影响 |
| --- | --- | --- | --- |
| [yt-dlp](https://github.com/yt-dlp/yt-dlp) | 页面约 207.4k stars；[2026-10-26 发布提交](https://github.com/yt-dlp/yt-dlp/commit/f264a6cbd1f630894da0f368df00f8aae50140e0)；[Issue #18042](https://github.com/yt-dlp/yt-dlp/issues/18042) 有贡献者在 11 月 12 日当天答复、次日继续跟进；主体 Unlicense | 专门的提取器处理播放器响应、格式选择和下载；YouTube 的 JS challenge 由 [EJS](https://github.com/yt-dlp/ejs) 和外部 JS runtime 处理 | 有 Python 嵌入接口、域名范围内的 Cookie jar、代理和下载进度钩子，适合替换当前仅支持直链的部分 |
| [pytubefix](https://github.com/JuanBindez/pytubefix) | 页面约 1.7k stars；[2026-10-16 发布提交](https://github.com/JuanBindez/pytubefix/commit/6f2e17f585bc82c04e11537027e6f8f59002c250) 包含播放器修复；MIT；[Issue #687](https://github.com/JuanBindez/pytubefix/issues/687) 当天有社区答复和关联修复提交，但尚未关闭 | `YouTube(...).streams` 选择音源；当前依赖 `aiohttp>=3.12.13`、`nodejs-wheel-binaries>=22.20.0`，不是零依赖；可借 Node 生成 PO Token | 简单音频 API 适合参考，但公开构造器以 OAuth/PO Token 为主，没有接收现有 `requests.Session` 或浏览器 Cookie jar 的参数；要继续接本仓库浏览器登录态，yt-dlp 更直接 |

这里抽查的是近期提交和具体 Issue，不把 star 数或一次回复当成稳定性保证。pytubefix 的 [11.2.1 发布说明](https://github.com/JuanBindez/pytubefix/releases/tag/v11.2.1)、[构造器源码](https://github.com/JuanBindez/pytubefix/blob/v11.2.1/pytubefix/__main__.py) 和 [PyPI 元数据](https://pypi.org/pypi/pytubefix/json) 支持上表的接口、版本和依赖判断。

## 最小接法

使用固定版本 [yt-dlp 2026.10.26 的 `YoutubeDL` 接口](https://github.com/yt-dlp/yt-dlp/blob/2026.10.26/yt_dlp/YoutubeDL.py)，在授权判断通过后，调用 `extract_info("https://www.youtube.com/watch?v=" + video_id, download=True)`；`format` 选 `bestaudio` 或 `worstaudio`，`noplaylist=True`，输出写进现有临时目录，再交给当前 `convert()`。不要求 YouTube 先给当前 `YouTubeClient.player()` 返回 `OK`，否则会在成熟提取器尝试其他播放器路径之前就提前放弃。

关键参数如下，参数名均已核对固定版本的源码接口：

| 目的 | 接法 |
| --- | --- |
| JS runtime | `js_runtimes={"node": {}}`。Node 默认不启用；官方支持 Node >=22.0.0、Deno >=2.3.0，Deno 默认启用。复用仓库已有的 `actions/setup-node@v4` + Node 22，在同步 workflow 也显式安装即可。[官方 EJS 设置说明](https://github.com/yt-dlp/yt-dlp/wiki/EJS) |
| 代理 | `proxy=session.proxies.get("https") or ""`。当前网络层给 HTTP/HTTPS 设置同一个 Mihomo 地址；空字符串显式直连，避免 yt-dlp 自己读取环境代理而改变当前 `trust_env=False` 的行为。`YoutubeDL` 自己管理网络，不能把 `requests_session` 当作它的参数。[代理实现](https://github.com/yt-dlp/yt-dlp/blob/2026.10.26/yt_dlp/YoutubeDL.py#L3870) |
| 浏览器登录态 | `YouTubeClient` 保留 DrissionPage 已读到的 YouTube 域 Cookie 元数据，在 `extract_info()` 前把标准 `http.cookiejar.Cookie` 对象逐条 `ydl.cookiejar.set_cookie(cookie)`；可以用已存在的 Requests 的 `create_cookie()` 构造，并保留原 domain/path/secure/expires。仅传浏览器 User-Agent 作为公共请求头。不要把整个 `base_headers`（包括 Cookie、Authorization）直接作为所有媒体请求的公共头。[Cookie jar 定义](https://github.com/yt-dlp/yt-dlp/blob/2026.10.26/yt_dlp/cookies.py#L1171)、[Cookie 头的弃用及作用域处理](https://github.com/yt-dlp/yt-dlp/blob/2026.10.26/yt_dlp/YoutubeDL.py#L1676) |
| 49 MB 限额 | `max_filesize=49_000_000` 加 `progress_hooks=[hook]`，hook 在 `downloaded_bytes` 超额时抛出下载异常，转换前后仍检查实际文件大小。真实 HTTP downloader 只有已知 Content-Length 时才提前执行大小限制；没有该响应头时只设 `max_filesize` 不够。[HTTP 下载实现](https://github.com/yt-dlp/yt-dlp/blob/2026.10.26/yt_dlp/downloader/http.py#L190) |

不限定源文件必须为 AAC/M4A：pytubefix 的 [Issue #665](https://github.com/JuanBindez/pytubefix/issues/665) 记录过同一歌曲 AAC 音源 403、WebM/Opus 可下的情况。源容器交给提取器选择，再用仓库现有 FFmpeg 转换即可。

## 版本与远端安装

本次直接读取 PyPI JSON，查到最新稳定发布及 wheel：

| 包 | 当前版本 | 发布文件 | Python |
| --- | --- | --- | --- |
| [yt-dlp](https://pypi.org/pypi/yt-dlp/json) | `2026.10.26` | `yt_dlp-2026.10.26-py3-none-any.whl` | >=3.11 |
| [yt-dlp-ejs](https://pypi.org/pypi/yt-dlp-ejs/json) | `0.8.0` | `yt_dlp_ejs-0.8.0-py3-none-any.whl` | >=3.10 |
| [pytubefix](https://pypi.org/pypi/pytubefix/json) | `11.2.1` | `pytubefix-11.2.1-py3-none-any.whl` | 包元数据 >=3.7；还受传递依赖约束 |

最小方案在现有 `requirements.txt` 增加 `yt-dlp==2026.10.26`、`yt-dlp-ejs==0.8.0` 两条固定依赖。yt-dlp 的 `default` extra 也能带上 EJS，但会额外引入其他可选包；本仓库已有 Requests 和 FFmpeg，可先采用这两个纯 Python wheel 加已有 Node。EJS 包本身为 Unlicense，运行的是其发布包内的 JS，不需要从源码构建它。[EJS 项目](https://github.com/yt-dlp/ejs)、[yt-dlp 依赖声明](https://github.com/yt-dlp/yt-dlp/blob/2026.10.26/pyproject.toml)

继续只在现有 GitHub Actions 执行已有命令 `python -m pip install --only-binary=:all: -r requirements.txt`。该选项禁止源代码分发包；找不到适配 wheel 时失败，不能退回源码构建。[pip 官方说明](https://pip.pypa.io/en/stable/cli/pip_install/#cmdoption-only-binary)

## 已知限制与验收范围

播放器的 `signatureCipher`、URL 签名和 `n` challenge 与媒体 DRM 不是同一件事。成熟提取器可以处理所支持的播放器签名/JS challenge，但不保证取得所有歌曲，也不能把“没有直链”直接判断成 DRM。YouTube 还会按客户端、账号、IP、地区或 PO Token 决定返回哪些格式；Web 客户端可能只返回 SABR 地址。[EJS 说明](https://github.com/yt-dlp/yt-dlp/wiki/EJS)、[PO Token 说明](https://github.com/yt-dlp/yt-dlp/wiki/PO-Token-Guide)、[SABR 跟踪 Issue #12482](https://github.com/yt-dlp/yt-dlp/issues/12482)

Cookie 可以复用当前浏览器登录态，但 YouTube 会轮换它，登录成功也不代表音源一定可用。PO Token 还可能需要额外 provider；本次不预先添加 provider 服务或自写签名逻辑，先用现有远端 probe 确认实际失败原因。[YouTube 提取器说明](https://github.com/yt-dlp/yt-dlp/wiki/Extractors#youtube)

远端 CI 可以用标准库 `ThreadingHTTPServer` 提供短 WAV 或包含 `<audio>` 的网页，让真实 `YoutubeDL.extract_info()` 经过 GenericIE、HTTP downloader 和现有 FFmpeg，验证 MP3/M4A 输出、已知/未知 Content-Length 的超限停止、失败后回退链接。此类 fixture 借鉴 [yt-dlp 自己的 HTTP downloader 测试](https://github.com/yt-dlp/yt-dlp/blob/2026.10.26/test/test_downloader_http.py)，只替换上游网页/音频输入，不模拟下载器，也不复制业务逻辑。

上述 fixture 能验证下载转换接线，不能证明真实 YouTube 提取器可用。`gHk8MIx6nfY` 的真实音源仍需通过现有远端 `check-audio` 操作，用恢复的浏览器登录态和相同出口验证；必须实际生成可解码音频，不能把回退链接算成音频下载通过。
