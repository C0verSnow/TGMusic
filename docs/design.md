# 设计与参考记录

核对日期：2026-11-12。Issue 最新随笔优先，采用 Cloudflare Worker；代理默认 auto；新增目标默认 baseline；默认偏好 audio；权限放 D1；Worker 使用 Infisical Cloud 的 Secret Sync。

## GitHub 检索与候选比较

已在 GitHub 搜索 `youtube music innertube`，找到 Metrolist、InnerTune 等候选，并进一步核对用户指定的 NeriPlayer 与 Python 备选 ytmusicapi。用于接口设计参考的候选均有明确许可证、较高星数、近期提交和已处理问题。

| 项目 | 维护与许可（核对时） | 实现、依赖 | 已知问题与本项目取舍 |
|---|---|---|---|
| [NeriPlayer](https://github.com/cwuom/NeriPlayer) | 4170 星；2026-11-11 有提交；GPL-3.0；#652/#653 有响应并关闭 | Kotlin/Android，OkHttp、JSON、浏览器认证、Innertube browse/player、独立播放仓库 | WebView 兼容问题、播放签名/挑战、分页中断。借鉴凭据上下文、分页及音源选择的职责划分；不引入 Android 栈，不复制 Kotlin；本项目遇到中断丢弃整份列表，防止错误基线 |
| [ytmusicapi](https://github.com/sigma67/ytmusicapi) | 3115 星；2026-11-04 有提交；MIT；#1025 修复重复 videoId 的问题 | Python、requests，浏览器 headers 认证、LM 收藏列表、browse continuation | 非官方接口会随 YouTube 改动，登录凭据有时失效。复用锁定版库作为方案 A 备用，浏览器登录态仍是唯一认证来源 |

研究过的具体源文件：

- [YouTubeMusicClient.kt](https://github.com/cwuom/NeriPlayer/blob/master/modules/platform/src/main/java/moe/ouom/neriplayer/platform/youtube/api/client/YouTubeMusicClient.kt)：收藏/歌单 browseId、续页、认证上下文。
- [YouTubeMusicPlaybackRepository.kt](https://github.com/cwuom/NeriPlayer/blob/master/modules/platform/src/main/java/moe/ouom/neriplayer/platform/youtube/repository/YouTubeMusicPlaybackRepository.kt)：播放信息和音源选择。
- [PlayerManagerUrlExtensions.kt](https://github.com/cwuom/NeriPlayer/blob/master/modules/playback/runtime/src/main/java/moe/ouom/neriplayer/core/player/url/PlayerManagerUrlExtensions.kt)：播放器与音源解析的分层。
- [ytmusicapi playlists.py](https://github.com/sigma67/ytmusicapi/blob/main/ytmusicapi/mixins/playlists.py)：LM → VLLM，get_playlist(limit=None) 与续页。

这些项目的许可证不转授权其媒体内容。本仓库自行编写实现，没有复制来源不明的代码或把 GPL 源码直接改写放入 MIT 文件。

## 使用的基础组件

- [DrissionPage](https://github.com/g1879/DrissionPage)：用户指定，锁定 4.1.1.4。[官方浏览器配置文档](https://www.drissionpage.cn/browser_control/browser_options/) 用于用户目录、自定义 ini、有头浏览器。其[自定义许可](https://github.com/g1879/DrissionPage/blob/master/LICENSE)限制商业使用，不能把它视为 MIT；本项目许可不替代依赖许可。
- [Mihomo](https://github.com/MetaCubeX/mihomo)：MIT，35705 星，核对时当天仍有提交。使用官方 TUN/controller 能力，不自行实现代理内核。
- [Infisical CLI](https://github.com/Infisical/cli)：锁定 0.45.6，检查该 tag 的 `packages/util/auth.go`，确认 login 支持 `INFISICAL_UNIVERSAL_AUTH_CLIENT_ID/SECRET`。显式 login 获取短期 Token，再用 run 注入密钥；凭证不放命令参数。[CLI #212](https://github.com/Infisical/cli/issues/212) 说明不能凭空假定所有命令都能自动推断认证。
- [Cloudflare D1 binding API](https://developers.cloudflare.com/d1/worker-api/d1-database/)：Worker 使用绑定和参数化语句；Runner 使用官方 REST query。Schema 在真实 SQLite 上测试，部署仍需 D1 集成验收。
- [Cloudflare R2 条件操作](https://developers.cloudflare.com/r2/api/s3/api/)：使用 S3 兼容接口、If-Match/If-None-Match、ETag，上传单独版本后才更新主对象。
- [Telegram sendAudio](https://core.telegram.org/bots/api#sendaudio)：当前官方播放器格式 MP3/M4A、Bot 文件限制 50 MB；实现留余量使用 49 MB。
- [Infisical Cloudflare Workers Secret Sync](https://infisical.com/docs/integrations/secret-syncs/cloudflare-workers)：独立目录同步 Worker Secrets；Runner 身份不读取 Worker 路径。

Infisical 0.45.6 Linux amd64 包 SHA-256 为 `b427391e76113e351fa0509d6493cb400577dec26b28afb462c2c2f9c5a37d4d`；Mihomo 1.19.34 Linux amd64-v1 包为 `0c07340a01408d033dda4088ea2a4c1e4d82aeed7b2f84f7c046e93b6ff3290c`。来源是对应官方 GitHub Release asset digest，固定在安装脚本，运行时不接受未经校验的最新包。

## Docker 登录与上传方式

沿用预构建的 [LinuxServer Chromium](https://github.com/linuxserver/docker-chromium)，浏览器与 Python 工具容器使用固定镜像摘要。Observer 只连接容器内的 DevTools；宿主只发布 127.0.0.1 的桌面端口。检测到 YouTube Music 登录有效后，宿主停止整个浏览器容器，再归档完整 ini 与完整用户目录，避免镜像的进程守护在归档期间重启 Chromium。完整目录包括缓存与空目录，只排除 Singleton 运行锁和 DevToolsActivePort。

恢复工作时检索并比较了两个已在本项目使用的上传候选：

| 项目 | 本轮核对的维护与许可 | 依赖与适用范围 | 决定 |
|---|---|---|---|
| [Cloudflare workers-sdk / Wrangler](https://github.com/cloudflare/workers-sdk) | 4719 星，近期持续提交，Apache-2.0；维护者已响应 [#13000](https://github.com/cloudflare/workers-sdk/issues/13000)，转为功能讨论 [#13169](https://github.com/cloudflare/workers-sdk/discussions/13169) | 已安装 CLI 4.160.1；Node.js；可利用现有登录管理 R2/D1 | 实际读取 CLI help 及官方 [`packages/wrangler/src/r2/helpers/object.ts`](https://github.com/cloudflare/workers-sdk/blob/main/packages/wrangler/src/r2/helpers/object.ts) 对应实现，确认 `r2 object put` 没有 If-Match/If-None-Match 与自定义元数据参数；不用于替换档案条件上传 |
| [boto3](https://github.com/boto/boto3) | 9937 星，近期持续提交，Apache-2.0；项目现有依赖及远端存储测试已经使用 | Python、botocore；需桶级 R2 S3 凭证；支持现有条件请求和元数据 | 保留现有客户端，继续先写独立版本，再条件更新主对象，不引入新 SDK |

官方 [R2 CLI 参考](https://developers.cloudflare.com/workers/wrangler/commands/r2/)与 [R2 条件操作](https://developers.cloudflare.com/r2/api/s3/conditional-operations/)分别说明两个接口的能力。CLI 优先意味着先检查其能力；不会把缺失的条件上传换成“先 get 再无条件 put”，也不假定官方 REST 对象上传接口支持未列出的条件和校验元数据。以上仅参考经过核对的设计，没有复制开源实现。

Docker 登录入口不要求 D1/Telegram 配置，因而没有取得同步主流程的 D1 租约。它在打开浏览器前读取主档案 ETag，上传时沿用该 ETag；首次档案则使用 If-None-Match。冲突保留云端当前对象与本地加密副本，交由用户核对后重新开展登录流程。

真实档案读回时发现，不能仅凭 `Default/Cache` 是否存在判断有无缓存：User Data 中还包括 GPUCache、Service Worker/CacheStorage 等缓存。本次档案共 673 项，其中 238 项路径与缓存有关。按 [Chromium 官方目录说明](https://chromium.googlesource.com/chromium/src/+/HEAD/docs/user_data_dir.md#User-Cache-Directory)，Linux 的网页磁盘缓存也可能位于 User Data 之外的 `~/.cache/chromium`。当前归档范围是完整 Chromium User Data 与 ini，不包含外部 XDG 缓存或整个桌面容器配置目录。此次修正的是临时核对条件与文档描述，没有改归档代码。

## 状态与失败边界

D1 保存 installation、targets、history、roles、admin_targets、审计及命令限频。R2 保存独立安装标识、加密档案、逐首发送回执及 latest.md。安装标识及历史预计条数用于区分真实首次安装与意外数据丢失。

首次初始化只由 manage bootstrap 显式执行。默认目标可以选择 baseline/all；以后新加目标固定默认 baseline；移除目标只是停用，不删除其历史，重新加入不会重复旧歌。

D1 租约与 Actions concurrency 防止同一安装重叠执行；租约 35 分钟，工作流最多 30 分钟，发送和档案更新前检查租约。R2 ETag 防止旧档案覆盖新档案。不尝试构造跨 Telegram、R2、D1 的分布式事务。

发送前 pending，明确拒绝 failed，明确成功 R2 receipt → D1 sent。收到不确定结果时保持 pending，只有现成回执或 Owner 核对才能恢复。网络超时不自动重发，因为 Bot API 无法自动查询任意消息历史。这个约束直接来自 Issue 的“成功后状态写失败可能重复”场景。

## 暂不假定已验证的事实

- 自建代码不保证非官方 YouTube API 永远有效；签名/反机器人挑战回退链接。
- 完整浏览器目录不代表跨操作系统、Chrome 版本和出口可无条件复用 Cookie；首次认证使用兼容 Linux 桌面环境。
- Xvfb 无法替人处理 Google 验证码。
- 确认有下载和再分发授权后才将 videoId 加入授权清单；默认偏好音频与实际发出音频是两件事。
- 仓库为空，没有原有 CI；本次为交付要求增加远端测试工作流，未引入本地编译验证流程。
