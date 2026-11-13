# 设计与参考记录

核对日期：2026-11-13。Issue #7 与用户本轮确认优先，采用 Cloudflare Worker；代理默认 auto；新增目标补发未发送歌曲；默认偏好 audio；权限放 D1；Worker 使用 Infisical Cloud 的 Secret Sync。

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
- [Infisical Cloudflare Workers Secret Sync](https://infisical.com/docs/integrations/secret-syncs/cloudflare-workers)：独立目录同步 Worker Secrets；应用只请求各自目录。当前复用 Example Project 身份，身份本身不再保证 Runner 与 Worker 目录互相隔离。

Infisical 0.45.6 Linux amd64 包 SHA-256 为 `b427391e76113e351fa0509d6493cb400577dec26b28afb462c2c2f9c5a37d4d`；Mihomo 1.19.34 Linux amd64-v1 包为 `0c07340a01408d033dda4088ea2a4c1e4d82aeed7b2f84f7c046e93b6ff3290c`。来源是对应官方 GitHub Release asset digest，固定在安装脚本，运行时不接受未经校验的最新包。

## Infisical 共用身份的部署决定

用户已选择将密钥复制到 Example Project 的 prod `/tgmusic/github-actions`、`/tgmusic/cloudflare-worker`、`/tgmusic/shared`，复用其现有项目级身份，避免新增机器身份额度阻塞。运行代码已有 `INFISICAL_PROJECT_ID` 和 `INFISICAL_SECRET_PATH` 参数，因此只修改部署定位和文档，不新增前缀映射逻辑。原项目副本保留用于回退，不删除或变更其他应用的配置。

参考 [Infisical 官方 GitHub 机器身份文档](https://github.com/Infisical/infisical/blob/main/docs/documentation/platform/identities/machine-identities.mdx)和[官方文件夹说明](https://infisical.com/docs/documentation/platform/folder)：项目级身份只能访问自身项目，组织级身份才可加入多个项目；文件夹可按路径组织多个应用。当前共享身份沿用其原有权限，文件夹只防止应用取错配置，不提供仓库之间的权限隔离。这是用户对原独立身份方案的明确调整。

GitHub 启动 Secrets 仍只有 INFISICAL_CLIENT_ID 和 INFISICAL_CLIENT_SECRET，使用 [GitHub 官方 REST API 加密方案](https://docs.github.com/en/rest/guides/encrypting-secrets-for-the-rest-api)和 [PyNaCl](https://github.com/pyca/pynacl) 的 libsodium sealed box 写入。配置时仅在忽略的运行目录安装预构建 wheel，不编译、不加入应用依赖；不自行实现加密协议。

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

首次初始化只由 manage bootstrap 显式执行。旧 baseline/all 配置兼容保留，但 Issue #7 起所有目标都补发未发送歌曲，baseline 不再跳过；移除目标只是停用，不删除其历史，重新加入不会重复旧歌。

D1 租约与 Actions concurrency 防止同一安装重叠执行；租约 35 分钟，工作流最多 30 分钟，发送和档案更新前检查租约。R2 ETag 防止旧档案覆盖新档案。不尝试构造跨 Telegram、R2、D1 的分布式事务。

发送前 pending，明确拒绝 failed，明确成功 R2 receipt → D1 sent。收到不确定结果时保持 pending，只有现成回执或 Owner 核对才能恢复。网络超时不自动重发，因为 Bot API 无法自动查询任意消息历史。这个约束直接来自 Issue 的“成功后状态写失败可能重复”场景。

## 暂不假定已验证的事实

- 自建代码不保证非官方 YouTube API 永远有效；签名/反机器人挑战回退链接。
- 完整浏览器目录不代表跨操作系统、Chrome 版本和出口可无条件复用 Cookie；首次认证使用兼容 Linux 桌面环境。
- Xvfb 无法替人处理 Google 验证码。
- 确认有下载和再分发授权后才将 videoId 加入授权清单；默认偏好音频与实际发出音频是两件事。
- 仓库为空，没有原有 CI；本次为交付要求增加远端测试工作流，未引入本地编译验证流程。


## Issue #3：新 Runner 手动联调入口

PR #2 合并后，`sync.yml` 已注册在默认分支。原来的 job 开关同时挡住手动和定时任务，导致必须先开启定时才能验收。现在 `TGMUSIC_ENABLED` 只控制定时任务，显式 `workflow_dispatch` 可以运行；Worker 的 `/sync` 同属手动触发。手动输入 `operation` 默认 `sync`，只有选择 `bootstrap` 才调用现有管理命令初始化空安装，不将初始化混入正常同步。两种操作共用原来的 Actions concurrency。

本轮在 GitHub 检索了 [Infisical CLI](https://github.com/Infisical/cli) 和 [Infisical Secrets Action](https://github.com/Infisical/secrets-action)，比较现有 CLI 子进程注入与额外引入 JavaScript Action 的实现。2026-11-13 核对时，CLI 101 星、当天有提交，许可证明确区分普通代码的 MIT Expat 与 ee/ 的单独条款；Secrets Action 82 星、MIT、最近提交为 2026-09-14，近期关闭的问题包括 #40 的 project-id 支持。两者均不是高星的新候选，不引入任何新组件。本项目继续使用已锁定、已在 CI 验证的 CLI 0.45.6 与现有 `infisical_boot.py`，不复制其代码。

工作流条件和输入采用 [GitHub 官方手动触发文档](https://docs.github.com/en/actions/how-tos/write-workflows/choose-when-workflows-run/trigger-a-workflow) 的事件与输入上下文；不依赖额外分发服务或第三方 Action。真实初始化前先只读核对 D1 installation/targets/history 均为 0，且 R2 没有安装标识。初始化后不能通过重跑 bootstrap 清空或修复生产状态。


新 Runner 暴露的网络误判：匿名 Python 请求拿到 HTTP 200，但响应不包含 `INNERTUBE_CONTEXT`，旧版把它判为网络不通，立即要求未配置的 Mihomo。网络探测现在只判断 HTTP 成功；应用和登录状态仍由恢复档案后的真实浏览器与收藏 API 判断，UNKNOWN / 收藏读取失败仍按原流程尝试备用代理。只记录失败 HTTP 状态或异常类型，不记录网页和凭证，也不再把缺代理配置描述成已证实被封锁。用户明确要求直连正常时不启用 Mihomo。


本地 Docker 实测进一步定位到正常页面流程缺失：原档案完整恢复后，Google Cookie 仍可使用，但 YouTube 需要点一次 Sign in 才会完成 `ServiceLogin → CheckCookie → SetSID` 跳转。用户亲自只点击 Sign in 后即恢复 VALID，不能据此宣称 Google 会话已经失效。本次在页面检测前处理已实际遇到的 `consent.youtube.com`，拒绝可选 Cookie 后返回 Music；Music 显示未登录时沿页面现有 Sign in 链接继续正常跳转。遇到密码/验证码仍停止，不自行填写或绕过验证。

依照 [DrissionPage 4.1.1.4 等待文档](https://www.drissionpage.cn/browser_control/waiting/)等待实际导航和文档加载；不自行实现 OAuth 或 Cookie 解密。另读取固定镜像 revision [LinuxServer Chromium 启动脚本](https://github.com/linuxserver/docker-chromium/blob/c4bbd54b9bb6a505f0decb422214c39dfdae7650/root/usr/bin/wrapped-chromium)，并在实际浏览器 `chrome://version` 核对目录为 `/config/.config/chromium/Default`，与归档根一致。用户明确选择仅保留完整 Chromium User Data，未扩展到整个容器 HOME，也无需新增归档格式。

用户提供的 `PLc_u7T_eRp6c` 已由正式读取器读取 91 首，原 LM 为 0；按用户要求将 TGMusic Infisical 的 `YOUTUBE_PLAYLIST_ID` 设置为此 ID。网页提示隐藏 40 个不可用视频；不把这些视频伪造为可下载或可发送项目。归档和账号密钥不写入 Git。

## Issue #5：每六小时同步与 Worker 上线

定时改用 GitHub 原生 cron `17 */6 * * *`，UTC 每天 00:17、06:17、12:17、18:17 执行。移除 Python 根据 `last_success` 再拦截任务的旧逻辑：否则 00:17 手动成功后，06:17 的任务可能因完成时间差被跳过，实际等到 12:17。`last_success` 继续用于状态展示；手动 `/sync` 不改变 cron。保留现有 concurrency、目标授权与逐首去重，不增加调度依赖。[GitHub 官方说明](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#schedule)指出 cron 运行默认分支且可能延迟；因此 PR review 合并前保持定时关闭，不能提前打开 main 中原有的五分钟调度。

Secret Sync 沿用现成的 [Infisical Cloudflare Workers Sync](https://infisical.com/docs/integrations/secret-syncs/cloudflare-workers)，源为 Example Project prod `/tgmusic/cloudflare-worker`，目标仅 `tgmusic-webhook`，保留四个敏感键的原名。与 [Wrangler secret bulk](https://developers.cloudflare.com/workers/wrangler/commands/workers/) 比较：前者在密钥变化后自动推送，需要持久的 Cloudflare App Connection；后者依赖部署者临时执行，不构成持续 Secret Sync。本次优先使用前者，不自行实现轮询密钥服务。

借鉴实现为 [Infisical/infisical](https://github.com/Infisical/infisical) 的 [Cloudflare 同步模块](https://github.com/Infisical/infisical/blob/main/backend/src/services/secret-sync/cloudflare-workers/cloudflare-workers-fns.ts)以及已使用的 [cloudflare/workers-sdk](https://github.com/cloudflare/workers-sdk)。前者使用 TypeScript 服务端任务和 Cloudflare API，非 ee 目录为 MIT Expat；后者是 Node CLI，Apache-2.0 / MIT 双许可。2026-11-13 GitHub API 核对：Infisical 30,476 星，当天提交，近期已关闭 PR #9452 有 5 条讨论；workers-sdk 4,723 星，当天提交，问题 #16881 已响应关闭。Infisical 已记录变量类型冲突及未部署版本导致同步失败等边界；当前仅同步加密 secret_text，先部署 Worker 再建立同步，不引入它们的服务端依赖、不复制源码。Cloudflare 连接需要 Workers Scripts Edit 与 Account Settings Read，现有仅 D1 Write 的 Runner Token 不能代替，详见[官方连接权限](https://infisical.com/docs/integrations/app-connections/cloudflare)。

Worker 是无外部 import 的原生 ES module，可用 `wrangler deploy --no-bundle --config worker/wrangler.toml` 直接上传，跳过本地构建步骤。打包与测试仍由现有 GitHub CI 执行。


### 音频实际验收暴露的下载入口问题

真实 Runner 登录为 VALID，但 `gHk8MIx6nfY` 的旧 `player` 调用返回不可播放、0 个音频地址，最终正式流程发送 link；这不是 Telegram 音频成功的证据。按用户建议检索成熟下载器，比较记录见 [YouTube 下载项目研究](audio-download-research.md)。选择 yt-dlp 2026.10.26 + EJS 0.8.0，使用现有 Python pip 二进制安装、现有 setup-node22 和原有 FFmpeg，不自写播放器签名解析，不复制开源源码。

下载器直接承担音源选择和下载，替换旧的自写直链流程；仅处理授权清单内 videoId。Cookie 从 DrissionPage 保存的 YouTube 域元数据注入 CookieJar，不把包含账号 Cookie / SAPISIDHASH 的整个 headers 字典当成全局媒体请求头。保留源域、路径和 Secure 属性；代理从正式 session 读取，空串显式直连，有代理时失败不回落。`max_filesize` 预检查和实际下载进度上限分别覆盖已知和未知 Content-Length；仍用 FFmpeg 生成 MP3/M4A，再走原来的 Telegram、R2 receipt 与 D1 去重。没有引入 CAPTCHA、外部 PO Token 服务或 DRM 解密。

自动测试使用远端 CI 内真实 yt-dlp GenericIE、HTTP downloader 和 FFmpeg，验证文件、Cookie / User-Agent、明确拒绝、已知及未知大小、代理失败。该夹具只证明下载/转换集成，不冒称验证 YouTube 线上提取器；真实样例另用 `check-audio` 和 Telegram 验收。

## Issue #7：按真实发送记录补发并更新仓库清单

用户已确认：Bot API 无法读取任意旧聊天历史时，使用现有成功发送记录和 Telegram 消息 ID 核对；并要求每次同步后自动提交 `docs/latest.md` 到仓库。D1 是去重来源，R2 receipt 恢复“发送已成功但 D1 写失败”的记录。Markdown 是展示，不能手工编辑它来改变发送状态。

实现顺序：完整读取歌单 → 每个授权且启用的聊天对比 D1 → 只跳过 sent，baseline/failed/无记录允许发送，pending 先恢复回执或等待人工核对 → 逐首写 R2 receipt、D1 sent → 导出所有未移除聊天的清单 → 更新 R2 副本与运行分支 `docs/latest.md` → 备份浏览器 → 无剩余歌曲才回复完成。局部同步不会发送其他聊天的歌曲；清单保留其他聊天原记录并注明本次未核对，不把旧记录假装为本次结果。清单保留已不在当前歌单中的历史记录，并逐首标明“本次歌单：是/否/未核对”；不在歌单中的旧未发送记录不阻止本轮歌单同步完成。

预算或发送时限耗尽仍导出未发送歌曲，并返回未完成；再次 `/sync` 继续剩余。403 暂停目标，pending 不确定发送仍由 Owner 核对。仓库发布失败也不会提示完成或更新 last_success；R2/D1 已保存的成功记录保留，下轮不会重发。每次更新后的文档有生成时间，不假定能检测聊天消息被删除。

### 检索与实现选择

2026-11-13 在 GitHub 检索并读取两个项目的持久化实现：

| 项目 | 维护与许可 | 实现、依赖和已知限制 | 本仓库采用方式 |
|---|---|---|---|
| [python-telegram-bot](https://github.com/python-telegram-bot/python-telegram-bot) | 29,591 星，2026-11-12 有提交；[问题 #5270](https://github.com/python-telegram-bot/python-telegram-bot/issues/5270) 有 7 条讨论且已关闭；API 许可摘要 GPL-3.0，所读文件头明确 LGPL-3.0-or-later，使用时须以具体许可文件为准 | [`BasePersistence`](https://github.com/python-telegram-bot/python-telegram-bot/blob/master/src/telegram/ext/_basepersistence.py) 按 chat_id 读写状态，框架异步处理，使用 HTTPX；持久化文档指出不要保存带旧 Token 的 Bot 实例，并提示并发刷新约束；不会提供任意聊天历史读取 | 参考按聊天持久化状态的思路；沿用现有 requests/D1，不引入框架或复制源码 |
| [aiogram](https://github.com/aiogram/aiogram) | 5,936 星，2026-11-10 有提交，MIT；[PR #2003](https://github.com/aiogram/aiogram/pull/2003) 有响应且已关闭 | [`StorageKey` / `BaseStorage`](https://github.com/aiogram/aiogram/blob/dev-3.x/aiogram/fsm/storage/base.py) 把 chat_id 纳入存储键，异步框架使用 aiohttp，持久化后端可选 Redis；PR #2003 记录复制消息时元数据丢失，说明不能凭消息显示猜测发送内容 | 参考存储按聊天隔离；保留现有 `(chat_id, video_id)` 与实际 message_id，不增加 Redis、aiohttp 或聊天爬取 |

仓库文档采用 GitHub 官方 [Contents API](https://docs.github.com/en/rest/repos/contents#create-or-update-file-contents)：读取运行分支现有文件 SHA，再创建或更新唯一的 `docs/latest.md`。使用现有 requests 与工作流短期 [GITHUB_TOKEN](https://docs.github.com/en/actions/tutorials/authenticate-with-github_token)，仅同步 job 增加 contents: write，无新长期密钥。403/409 直接报未完成，不强推或自行扩权。只在 GitHub Actions 自动提交；手动在其他环境运行脚本仅写本机文档，部署验收仍以正式 Actions 为准。同步工作流的 contents 写入不用于修改代码或其他文件。
