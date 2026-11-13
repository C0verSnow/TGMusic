# Issue #1 验收记录

本文件区分“代码有测试”和“真实服务已跑通”，没有把自动化测试替代真实账号验证。禁止本地编译验证，测试在 GitHub CI 执行。

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
| AT-05 新 Runner 恢复历史 | D1 为持久化来源；SQLite 测试已覆盖重用历史，真实跨 Runner 待验收 |
| AT-06 首次基线/all | `test_all_mode_and_global_budget`，每目标单独 baseline |
| AT-07 登录失败保留状态 | 主流程在读列表/修改歌曲状态前检查；真实失效账号待验收 |
| AT-08 未授权音源回退 | `test_audio_requires_explicit_permission`、cipher stream fallback；实际播放待验收 |
| AT-09 加密档案恢复 | 完整 ini/User Data 自动测试通过；真实 R2 档案已上传并读回核对，见下文 |
| AT-10/11/12/13 浏览器/Xvfb/登录 | 有头 Chromium、目录和测试 Cookie 恢复已在远端通过；真实 Google 已在 Docker 登录，真实新 Runner 恢复待验收 |
| AT-14/15/16 Mihomo/TUN/出口 | 配置、路由、美国出口和固定代理已实现；真实代理节点待提供与验收 |
| AT-17/18 音频发送 | HTTP 发送/重试路径有测试；专用测试 Bot 已验证文本收发、默认私聊等于 Owner；真实音频和群组待验收 |
| AT-19/20 白名单与入群不自动授权 | Worker `guest has help only...`、admin scope 测试通过 |
| AT-21/22/23 多目标与隔离失败 | `test_targets_are_independent_and_new_target_baselines` |
| AT-24 存储失败保留数据 | receipt 恢复、历史丢失拒绝发送、租约、档案完整性与 S3 ETag 冲突测试通过 |
| AT-25 Webhook Secret | Worker `webhook rejects missing/wrong secret...` |
| AT-26 触发 Actions | Worker `owner dispatches once...`；细粒度触发 Token 已配置且通过 Actions 只读 API 验证；真实触发待验收 |
| AT-27 GitHub 只存启动凭证 | 仓库已保存且只保存两项 Infisical 启动 Secret；五项定位/启用变量已写入并回读核对 |
| AT-28/29 Universal Auth/密钥注入 | 已核对 CLI 0.45.6 官方源码，远端已校验和安装 CLI；使用用户提供的 Example Project 机器身份成功登录并逐项读回迁移配置；GitHub Runner 实际注入待验收 |
| AT-30 YAML 配置写入 | 权限 0600、退出删除；真实 Mihomo 验收待进行 |
| AT-31 R2/Telegram/解密密钥 | R2 凭证、加密密钥与真实档案上传/读回已通过；新 Runner 与真实音频联调待完成 |
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

## 业务令牌补齐与当前阻塞

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

## 真实部署需要完成

1. 核对 R2 安装标识与当前空的 D1 后，再显式初始化 D1/R2；D1 API Token、Worker 的 GitHub 触发 Token、R2 凭证与加密密钥均已配置。
2. 沿用已确认的测试 Bot 和 Owner 默认私聊；已完成 `/start` 文本收发，真实音频及群组仍待验收。
3. 使用已配置的共享身份完成 GitHub Runner 实际密钥注入验收，再将 Worker Secret Sync 指向 `/tgmusic/cloudflare-worker`。当前不要求验证共享身份对另一应用目录访问被拒绝。
4. 用户 review 后将同步工作流纳入默认分支，再在新的 GitHub Runner 恢复 Linux Google 登录档案，核对真实登录是否仍有效。
5. 手动执行一次 Runner：确认实际出口、登录、列表分页、R2 解密和默认基线；新增歌曲后验证发送与再次运行不重复。
6. 部署 Worker、注册 Webhook；测试错误 Secret、Guest、Owner/Admin、未授权群组、真实 `/sync`。
7. 对一首确有下载和分发授权的歌曲验证 MP3/M4A 在 Telegram 播放器中显示，再启用定时。

在这些项目完成前，不将整个 Issue 标记为真实验收通过，不自动开启同步，不提前关闭 Issue。

## 本轮交付决定

- [1794474792] 用户决定先完成 PR，暂不联调真实 Telegram。因此保留 Issue，等待作者 review；不申请后续长期凭证，不部署 Worker 或开启定时同步。已有 Infisical 项目、空密钥目录、D1 表和私有 R2 桶保留。
- [1794474792] 仅运行源码静态解析、脚本静态语法及差异检查，没有进行本地构建、编译或测试。


## Issue #3：新 Runner 联调（进行中）

PR #2 已合并到 main，同步工作流已注册。真实只读预检查确认 D1 installation/targets/history 均为 0，R2 不存在 `sync/installation.json`，GitHub `TGMUSIC_ENABLED=false`。本次在 feature/issue-3-runner-integration 增加独立的手动 bootstrap 入口，并允许手动任务在定时关闭时运行；正式验收证据将在 Runner 执行后补充。
