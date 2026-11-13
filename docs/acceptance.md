# 真实服务与远端 CI 验收记录

本文件区分“代码有测试”和“真实服务已跑通”。最新进展见文末 Issue #5；Issue #3 已完成两个真实新 Runner 的登录恢复、指定歌单读取、91 首基线和无新增不重复。禁止本地编译验证；本轮用户另行明确允许预构建 Docker 的本地真实账号排查，没有进行本地镜像构建或编译。

## 已有远端证据

[CI 43189104317](https://github.com/C0verSnow/TGMusic/actions/runs/43189104317)：对应代码提交 `f59b89c`，Python **26 项通过**、Node Worker **7 项通过**、Worker 打包检查通过。远端还实际完成：

- 安装并核对固定 SHA-256 的 Infisical CLI 0.45.6、Mihomo 1.19.34。
- Xvfb 中以有头模式启动 Chromium，使用独立目录；真实浏览器 Cookie 随加密档案恢复。
- 对测试音频实际执行 FFmpeg 转码，ffprobe 确认 MP3/M4A 对应正确编码。
- 正式 boto3 S3 客户端通过 HTTP 存储夹具验证 ETag 冲突、版本保留、元数据读取。
- 正式 D1 HTTP 客户端通过 HTTP + SQLite 夹具验证查询及 SQL 失败处理。

浏览器测试使用可控测试页面与测试 Cookie；**没有将其当作真实 Google 登录有效的证据**。存储 HTTP 夹具不是实际 R2/D1 凭证验收。

| 验收项 | 证据或现状 |
|---|---|
| AT-01/02/04 新增、无新增、不重复 | `test_baseline_then_only_new_and_no_repeat` |
| AT-03 发送失败保留重试 | `test_failure_is_retried_without_resending_success` |
| AT-05 新 Runner 恢复历史 | D1 为持久化来源；SQLite 测试已覆盖重用历史，真实跨 Runner 已验收：91 首基线由下一台 Runner 恢复，见 Issue #3 |
| AT-06 首次基线/all | `test_all_mode_and_global_budget`，每目标单独 baseline |
| AT-07 登录失败保留状态 | 主流程在读列表/修改歌曲状态前检查；真实失效账号待验收 |
| AT-08 未授权音源回退 | `test_audio_requires_explicit_permission`、cipher stream fallback；实际播放待验收 |
| AT-09 加密档案恢复 | 完整 ini/User Data 自动测试通过；真实 R2 档案已上传并读回核对，见下文 |
| AT-10/11/12/13 浏览器/Xvfb/登录 | 有头 Chromium、目录和测试 Cookie 恢复已在远端通过；真实 Google 已在 Docker 登录，真实新 Runner 恢复已通过，见 Issue #3 |
| AT-14/15/16 Mihomo/TUN/出口 | 配置、路由、美国出口和固定代理已实现；真实代理节点待提供与验收 |
| AT-17/18 音频发送 | HTTP 发送/重试路径有测试；专用测试 Bot 已验证文本收发、默认私聊等于 Owner；真实音频和群组待验收 |
| AT-19/20 白名单与入群不自动授权 | Worker `guest has help only...`、admin scope 测试通过 |
| AT-21/22/23 多目标与隔离失败 | `test_targets_are_independent_and_new_target_baselines` |
| AT-24 存储失败保留数据 | receipt 恢复、历史丢失拒绝发送、租约、档案完整性与 S3 ETag 冲突测试通过 |
| AT-25 Webhook Secret | Worker `webhook rejects missing/wrong secret...` |
| AT-26 触发 Actions | Worker `owner dispatches once...`；细粒度触发 Token 已配置且通过 Actions 只读 API 验证；令牌已真实触发 bootstrap 与 sync；Worker 指令入口仍待部署 |
| AT-27 GitHub 只存启动凭证 | 仓库已保存且只保存两项 Infisical 启动 Secret；五项定位/启用变量已写入并回读核对 |
| AT-28/29 Universal Auth/密钥注入 | 已核对 CLI 0.45.6 官方源码，远端已校验和安装 CLI；使用用户提供的 Example Project 机器身份成功登录并逐项读回迁移配置；GitHub Runner bootstrap 和两次 sync 已验证实际注入 |
| AT-30 YAML 配置写入 | 权限 0600、退出删除；真实 Mihomo 验收待进行 |
| AT-31 R2/Telegram/解密密钥 | R2 凭证、加密密钥与真实档案上传/读回已通过；新 Runner 已通过；真实音频仍待验收 |
| AT-32/33 独立身份/跨路径隔离 | 用户已改为共用 Example Project 身份；当前仅按目录分组，不再声明仓库之间具备身份隔离。Worker Secret Sync 待部署 |
| AT-34 Infisical 失败退出 | boot 捕获认证输出并拒绝启动；真实拒绝认证待远端验收 |
| AT-35 日志脱敏 | 第三方异常不输出原文；敏感值注册 GitHub mask，测试未使用真实凭证 |

## Docker 方案的远端验证

后续代码 `85d9a05` 的 [push CI 43345179904](https://github.com/C0verSnow/TGMusic/actions/runs/43345179904) 已全部通过，包含 Docker 浏览器任务：实际启动固定摘要的 LinuxServer Chromium，验证桌面 HTTP 服务、有头浏览器及 DevTools 连接。Python 测试另覆盖完整 ini、缓存、空目录的归档恢复，以及旧档案格式读取。[PR CI 43345185486](https://github.com/C0verSnow/TGMusic/actions/runs/43345185486) 也已通过，但该事件按工作流约定跳过 Docker 任务。以上仍没有验证真实 Google 账号。

## 真实 Google 登录与 R2 档案

用户已在本机的 Docker Linux Chromium 中亲自完成 Google 登录及验证，Observer 实际检测为 VALID。程序正常停止浏览器容器后，将完整 ini 和 Chromium User Data 加密上传到私有对象 `tgmusic-private/auth/google-profile.tar.enc`，成功退出并清理明文浏览器目录、容器和网络。

已使用 Wrangler CLI 从真实 R2 下载该对象，再只读检查：密文与本地副本逐字节一致，大小 84,656,076 字节；Fernet 认证解密、原始归档 SHA-256 与 R2 元数据、ETag、manifest schema 2、完整 ini 字节比较全部通过。归档 673 项，含 Cookie、Local Storage 和 238 个缓存相关条目；未包含运行锁及调试端口文件。范围为 Chromium User Data 内的数据，Linux 另放在外部 XDG 路径的网页磁盘缓存不在此范围。

临时下载副本已移除，原始加密副本保留在 `.runtime/docker-login/google-profile.latest.enc`。此次是真实账号登录和真实 R2 上传验收，仍未证明新 GitHub Runner 能恢复该登录，也未验收音频发送或开启定时同步。

## Infisical 目录迁移与 GitHub 启动配置

用户同意后，使用原有个人 CLI 会话将 TGMusic 配置复制到 Example Project（`2ab57808-907b-4fd8-9f95-bd91e0601003`）的 prod `/tgmusic` 下，再用用户提供的现有机器身份逐项读回比较：`github-actions` 10 项、`cloudflare-worker` 3 项、`shared` 空目录，所有键值与源一致。密钥名保持不变，未增加前缀转换代码。

TGMusic 本机 `.env` 已切到新项目和 `/tgmusic/github-actions`，保存机器身份启动凭据，权限为 0600 且被 Git 忽略。原 TGMusic 项目和用户提供的 `1/.env` 保留。GitHub 仓库已通过官方加密 API 保存 INFISICAL_CLIENT_ID / INFISICAL_CLIENT_SECRET，读取元数据确认名称存在；API 不支持读回 Secret 明文。四项 Infisical 定位变量和 `TGMUSIC_ENABLED=false` 已设置并回读核对。尚未开启定时或完成真实新 Runner 验收。

迁移当时缺少的 Actions D1 Token 和 Worker GitHub 触发 Token 已在后续补齐，读回与接入证据见下节；这仍不代表同步服务已经上线。

## 业务令牌补齐时的历史记录

2026-11-13，经用户分别明确确认，已创建并保存：

| 配置 | Infisical 位置 | 权限、到期日与实际核对 |
|---|---|---|
| `CLOUDFLARE_API_TOKEN` | Example Project prod `/tgmusic/github-actions` | `TGMusic D1 sync`，仅 D1 Write，2027-02-11 到期；Cloudflare 当前页面只支持账号级 D1 范围，不能限制到单个数据库，用户已知情同意。机器身份读回后，用此 Token 对真实 D1 查询成功 |
| `GITHUB_WORKFLOW_TRIGGER_TOKEN` | Example Project prod `/tgmusic/cloudflare-worker` | `TGMusic Worker workflow trigger`，仅 `C0verSnow/TGMusic` 的 Actions 读写及必需的 Metadata 只读，2027-02-10 到期；机器身份读回后，用此 Token 读取仓库和 Actions 工作流列表成功。尚未执行真实 dispatch |

Actions 目录现在有 11 项必需配置，Worker 目录有 4 项。新令牌未写入仓库或本机 `.env`，也未放到迁移前的旧项目。Bot API `getMe` 确认 `@C0verSnow_TGMusic_Test_bot` 有效，默认私聊与 Owner 一致；`getWebhookInfo` 显示尚无 Webhook。已将 `worker/wrangler.toml` 中的 Bot 用户名占位值更新为实际用户名。

远端 D1 的 installation、targets、history 均为 0；Wrangler 查询确认 R2 尚无 `sync/installation.json` 安装标识，尚未初始化。GitHub 默认分支仍为 `main`，只有 README 和任务日志；Actions API 只列出 CI，没有 `sync.yml`。按照 [GitHub workflow_dispatch 规则](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#workflow_dispatch)，同步工作流需要先进入默认分支才能首次手动触发。PR #2 仍等待用户 review，本轮没有自行合并或修改默认分支。

配置提交 `3eb9fa4` 的 [PR CI 43375794236](https://github.com/C0verSnow/TGMusic/actions/runs/43375794236) 已通过；[push CI 43375787609](https://github.com/C0verSnow/TGMusic/actions/runs/43375787609) 第二次尝试也全部通过，包含 Docker 浏览器。第一次 Docker 任务在镜像拉取时遭遇 `toomanyrequests`，尚未启动容器；只重跑该失败任务即通过，没有修改应用逻辑或镜像配置。

`TGMUSIC_ENABLED=false` 已从 GitHub API 回读确认。真实初始化、Runner 密钥注入与 Google 登录恢复、Worker Secret Sync / 部署 / Webhook、真实音频与群组联调仍待进行。本轮只进行了配置写入、真实服务 API 查询和静态差异检查，没有本地构建、编译、测试或冒烟脚本。

## 已创建的云资源

- Infisical：当前运行配置在 Example Project 的 prod `/tgmusic` 下；原 youtube-music-telegram-sync 项目保留为迁移前副本。
- Cloudflare D1：tgmusic，`0001_initial.sql` 已通过 Wrangler 在远端应用。
- Cloudflare R2：tgmusic-private，控制台确认 Public Access Disabled；用户已自行开通 R2 订阅。恢复任务后，经用户确认创建只授权此桶对象读写的专用凭证，保存并回读核对 Infisical prod `/github-actions` 的 R2_ACCESS_KEY_ID / R2_SECRET_ACCESS_KEY。档案加密密钥也已配置；真实登录档案已上传并完成读回核对。

## 完整上线的后续工作（新 Runner 已完成，Worker / 音频仍未完成）

1. D1/R2 已在 Issue #3 通过真实 Runner 显式初始化，安装标识一致；不要再次 bootstrap 或重置历史。
2. 沿用已确认的测试 Bot 和 Owner 默认私聊；已完成 `/start` 文本收发，真实音频及群组仍待验收。
3. GitHub Runner 的共享身份注入已通过；后续将 Worker Secret Sync 指向 `/tgmusic/cloudflare-worker`。当前不要求验证共享身份对另一应用目录访问被拒绝。
4. PR #2 已合并，默认分支已注册同步工作流；本次 PR #4 的修复仍等用户 review，未自行合并。
5. 两次 Runner 的直连、登录、完整歌单读取、R2 解密、91 首基线及再次运行不重复已通过；真实新增歌曲的发送尚未进行。
6. 部署 Worker、注册 Webhook；测试错误 Secret、Guest、Owner/Admin、未授权群组、真实 `/sync`。
7. 对一首确有下载和分发授权的歌曲验证 MP3/M4A 在 Telegram 播放器中显示，再启用定时。

这些剩余项目属于完整上线验收，不能因新 Runner 已通过就宣称音频、群组或 Worker 已上线。Issue #3 的交付范围为新 Runner 联调；按用户要求提交 PR 待 review 并关闭该 Issue，定时同步继续关闭。

## Issue #1 早期交付决定（历史）

- [1794474792] 用户决定先完成 PR，暂不联调真实 Telegram。因此保留 Issue，等待作者 review；不申请后续长期凭证，不部署 Worker 或开启定时同步。已有 Infisical 项目、空密钥目录、D1 表和私有 R2 桶保留。
- [1794474792] 仅运行源码静态解析、脚本静态语法及差异检查，没有进行本地构建、编译或测试。


## Issue #3：新 Runner 真实联调

### 真实远端结果

| 执行 | 结果与证据 |
|---|---|
| 显式初始化 | [bootstrap 43377633951](https://github.com/C0verSnow/TGMusic/actions/runs/43377633951) 成功。此前只读确认 D1 installation/targets/history 均为空、R2 无安装标识；初始化后读回 D1/R2 标识一致 |
| 第一台新 Runner | [sync 43382782005](https://github.com/C0verSnow/TGMusic/actions/runs/43382782005)：直连成功，自动继续普通 Sign in 后 VALID，完整读取指定歌单 91 首，建立 91 首 baseline；发送 0、失败 0、待核对 0 |
| 第二台新 Runner | [sync 43383234383](https://github.com/C0verSnow/TGMusic/actions/runs/43383234383)：恢复上一台更新的真实 R2 档案，直接 VALID，再次读取 91 首；already_sent=91、new=0、success=0、failed=0、held=0。already_sent 包含 baseline，不表示此前发出了音乐 |
| 数据读回 | D1 auth_state=VALID，baseline=91、expected_history_count=91、sent=0、pending=0，租约已释放（lease_until=0）。GitHub API 再次回读 TGMUSIC_ENABLED=false |
| 自动测试 | [push CI 43383233679](https://github.com/C0verSnow/TGMusic/actions/runs/43383233679) 与 [PR CI 43383240442](https://github.com/C0verSnow/TGMusic/actions/runs/43383240442) 通过：Python 38 项、Worker 7 项、Worker 打包；push 还完成预构建 Docker 浏览器检查 |

当前实际目标是用户指定的 [歌单 PLc_u7T_eRp6c](https://www.youtube.com/playlist?list=PLc_u7T_eRp6c)，已保存到 Example Project prod `/tgmusic/github-actions` 的 YOUTUBE_PLAYLIST_ID。原 LM 读取为 0 首；指定歌单返回 91 首，网页另提示隐藏 40 个不可用视频，未把不可用项伪造成有效歌曲。

### 定位到的具体问题

1. 关闭定时也会跳过手动 job。手动触发现在独立可运行，并提供复用现有命令的显式 bootstrap 选项；普通 sync 不自动初始化。
2. 匿名 Python 请求收到 HTTP 200，但没有 INNERTUBE_CONTEXT，被误当网络不通。正式回归在 [修复前 CI 43378596021](https://github.com/C0verSnow/TGMusic/actions/runs/43378596021) 准确失败；现在网络检查只判断 HTTP 状态，登录和页面交给真实浏览器。
3. 恢复后的 Google 会话可用，YouTube 仍需要普通 Sign in 跳转。用户在本地 Docker 只点 Sign in 即进入账号；脚本现在会继续同一个页面上的登录入口，等待最多 20 秒。需要密码、验证码或二次验证时仍留给用户，不自动填写。
4. 隔离重放还实际遇到 consent.youtube.com 的 Cookie 选择页。现在拒绝可选 Cookie 后等待回到页面；未识别的选择页停止并请求人工查看，不盲目开启代理。

### 用户授权的本地 Docker 排查

用户本轮明确允许本地 Docker 测试；使用原有固定摘要的预构建 Python / LinuxServer Chromium，没有构建镜像或编译。本地加密副本与当前 R2 ETag 一致，通过正式 BrowserSession.restore 的认证解密和元数据校验；实际 chrome://version 目录为 `/config/.config/chromium/Default`，与归档路径一致。

用户明确选择保存完整 Chromium User Data，而非整个容器 HOME。现有 schema 2 已保存完整 ini、Cookie、Local Storage、目录内缓存和空目录，只排除运行锁与调试端口文件，无需修改归档格式。Docker Chromium 的 stdout/stderr 被镜像包装脚本重定向，不能仅靠容器启动日志判断网页登录；本次结合真实页面、正常导航链及正式读取器定位。

隔离重放从原加密档案开始：UNKNOWN（Cookie 选择页）→ 正常页面准备与 Sign in → VALID → 正式读取器返回 91 首。临时 DEBUG-issue3 探针已全部移除。GitHub 检索和官方文档参考写入 docs/design.md，未复制来源不明的代码或加入新依赖；myenv/config.yaml 未修改，也没有写入或启用 Mihomo 配置。

本次已完成新 Runner 的真实恢复、基线与无新增不重复；真实新增发送、音频播放、群组和 Worker 部署仍未验收，定时同步继续关闭。PR #4 交用户 review，不自行合并。


## Issue #5：六小时调度、真实 Worker 与发送联调（进行中）

- 分支 `feature/issue-5-six-hour-sync`，草稿 [PR #6](https://github.com/C0verSnow/TGMusic/pull/6)，未合并。
- 提交 `a76aa52` 的 [push CI 43414821023](https://github.com/C0verSnow/TGMusic/actions/runs/43414821023) 通过：Python 39 项、Worker 8 项、Worker 打包与预构建 Docker 浏览器。[PR CI 43415122375](https://github.com/C0verSnow/TGMusic/actions/runs/43415122375) 第二次尝试通过；第一次是原有浏览器归档回归在导航时出现 ContextLostError，只重跑失败任务，没有因此修改产品代码。
- 六小时 cron 已改为 UTC 00:17、06:17、12:17、18:17，移除旧 `SYNC_INTERVAL_MINUTES` 门槛；正式 `main()` 回归使用真实 SQLite 和正式同步流程，验证近期成功后定时及手动任务照常执行且不重发。
- Worker 已通过 `wrangler deploy --no-bundle` 直接上传（没有本地构建），地址 `https://tgmusic-webhook.f1515xcn.workers.dev`。首次版本 `d2ecc348-cab2-4fdb-952b-1b0a00c9e39c`；为联调临时将 GITHUB_REF 指向 feature 分支，仓库配置仍为 main。
- 现有四项 Worker Secrets 已通过 Wrangler 注入；真实 `setWebhook` 成功，`getWebhookInfo` 的 URL 正确、待投递为 0。缺失和错误 Webhook Secret 请求实际均返回 403。**一次性 Secrets 上传不等于持续 Infisical Secret Sync**。
- 用户确认验收群为 Music `-1004447109031`。Bot API 验证 Owner 为 creator，Bot 为 administrator。通过用户指定的本机 `tg` 真实账号发送 `/addtarget`，收到“目标已授权”；D1 新增群目标，首次模式仍是 baseline。
- 群内真实 `/sync@C0verSnow_TGMusic_Test_bot` 触发 [43415724056](https://github.com/C0verSnow/TGMusic/actions/runs/43415724056)，私聊 `/sync` 触发 [43415732090](https://github.com/C0verSnow/TGMusic/actions/runs/43415732090)。D1 审计均 allowed；不是伪造 Telegram Webhook。
- 用户授权的音频样例是 `gHk8MIx6nfY`，已写入 Infisical `AUDIO_AUTHORIZED_VIDEO_IDS`。它原本就在 91 首旧基线中；经用户明确同意，先备份并只撤销私聊该首 baseline，预计历史计数同步为 90。没有删除已发送记录或其他歌曲。此测试模拟新歌曲，不将它描述成歌单实际新增。
- 当前阻塞：Infisical 无 Cloudflare App Connection。现有机器身份不能管理 App Connection；个人 CLI 会话可以读取。Wrangler OAuth 可以部署和注入 Secrets，但用户/账号 Token 管理接口为 403，CLI 没有创建长期 API Token 的命令。仍需 Workers Scripts Edit + Account Settings Read 的专用 Token，才能创建并验收持续 Secret Sync。用户授权接管浏览器，但 macOS 辅助功能和 Chrome AppleEvents JavaScript 均阻止控制；没有更改这些系统权限。
- 合并 review 前 `TGMUSIC_ENABLED=false`：GitHub schedule 只运行默认分支，提前打开会执行 main 中旧的五分钟 cron。合并后才启用并核对六小时调度。

本轮仅做本地静态解析、语法与差异检查，没有进行本地构建、编译、测试或冒烟。已在 GitHub 检索并比较 Infisical 与 workers-sdk，维护、许可证、方案取舍及源码链接见 `docs/design.md`。
