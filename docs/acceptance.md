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
| AT-17/18 音频发送 | HTTP 发送/重试路径有测试；真实 Bot 用户和群组待配置 |
| AT-19/20 白名单与入群不自动授权 | Worker `guest has help only...`、admin scope 测试通过 |
| AT-21/22/23 多目标与隔离失败 | `test_targets_are_independent_and_new_target_baselines` |
| AT-24 存储失败保留数据 | receipt 恢复、历史丢失拒绝发送、租约、档案完整性与 S3 ETag 冲突测试通过 |
| AT-25 Webhook Secret | Worker `webhook rejects missing/wrong secret...` |
| AT-26 触发 Actions | Worker `owner dispatches once...`；真实细粒度触发 Token 待配置 |
| AT-27 GitHub 只存启动凭证 | sync.yml 仅引用两项 Infisical Secret；部署配置待完成 |
| AT-28/29 Universal Auth/密钥注入 | 已核对 CLI 0.45.6 官方源码，远端已校验和安装 CLI；本机已登录 CLI 可访问专用项目，Actions 专用身份及 Runner 注入待验收 |
| AT-30 YAML 配置写入 | 权限 0600、退出删除；真实 Mihomo 验收待进行 |
| AT-31 R2/Telegram/解密密钥 | R2 凭证、加密密钥与真实档案上传/读回已通过；新 Runner 与真实音频联调待完成 |
| AT-32/33 独立身份/跨路径隔离 | 按独立路径、独立身份/Secret Sync 部署；需实际拒绝访问证据 |
| AT-34 Infisical 失败退出 | boot 捕获认证输出并拒绝启动；真实拒绝认证待远端验收 |
| AT-35 日志脱敏 | 第三方异常不输出原文；敏感值注册 GitHub mask，测试未使用真实凭证 |

## Docker 方案的远端验证

后续代码 `85d9a05` 的 [push CI 43345179904](https://github.com/C0verSnow/TGMusic/actions/runs/43345179904) 已全部通过，包含 Docker 浏览器任务：实际启动固定摘要的 LinuxServer Chromium，验证桌面 HTTP 服务、有头浏览器及 DevTools 连接。Python 测试另覆盖完整 ini、缓存、空目录的归档恢复，以及旧档案格式读取。[PR CI 43345185486](https://github.com/C0verSnow/TGMusic/actions/runs/43345185486) 也已通过，但该事件按工作流约定跳过 Docker 任务。以上仍没有验证真实 Google 账号。

## 真实 Google 登录与 R2 档案

用户已在本机的 Docker Linux Chromium 中亲自完成 Google 登录及验证，Observer 实际检测为 VALID。程序正常停止浏览器容器后，将完整 ini 和 Chromium User Data 加密上传到私有对象 `tgmusic-private/auth/google-profile.tar.enc`，成功退出并清理明文浏览器目录、容器和网络。

已使用 Wrangler CLI 从真实 R2 下载该对象，再只读检查：密文与本地副本逐字节一致，大小 84,656,076 字节；Fernet 认证解密、原始归档 SHA-256 与 R2 元数据、ETag、manifest schema 2、完整 ini 字节比较全部通过。归档 673 项，含 Cookie、Local Storage 和 238 个缓存相关条目；未包含运行锁及调试端口文件。范围为 Chromium User Data 内的数据，Linux 另放在外部 XDG 路径的网页磁盘缓存不在此范围。

临时下载副本已移除，原始加密副本保留在 `.runtime/docker-login/google-profile.latest.enc`。此次是真实账号登录和真实 R2 上传验收，仍未证明新 GitHub Runner 能恢复该登录，也未验收音频发送或开启定时同步。

## 已创建的云资源

- Infisical：专用项目 youtube-music-telegram-sync，prod 下 shared / github-actions / cloudflare-worker 目录。
- Cloudflare D1：tgmusic，`0001_initial.sql` 已通过 Wrangler 在远端应用。
- Cloudflare R2：tgmusic-private，控制台确认 Public Access Disabled；用户已自行开通 R2 订阅。恢复任务后，经用户确认创建只授权此桶对象读写的专用凭证，保存并回读核对 Infisical prod `/github-actions` 的 R2_ACCESS_KEY_ID / R2_SECRET_ACCESS_KEY。档案加密密钥也已配置；真实登录档案已上传并完成读回核对。

## 真实部署需要完成

1. 补齐 D1 API Token，并完成 R2 凭证的真实上传验收；R2 桶级对象读写凭证和档案加密密钥已保存到 Infisical。
2. 确认使用哪个 Telegram Bot 和 Owner/默认私聊数字 ID，目标用户先发送 `/start`。
3. Actions 专用 Universal Auth 与 Worker Secret Sync 设置最小权限，并验证另一目录访问被拒绝。
4. 在新的 GitHub Runner 恢复已上传的 Linux Google 登录档案，核对真实登录是否仍有效。
5. 手动执行一次 Runner：确认实际出口、登录、列表分页、R2 解密和默认基线；新增歌曲后验证发送与再次运行不重复。
6. 部署 Worker、注册 Webhook；测试错误 Secret、Guest、Owner/Admin、未授权群组、真实 `/sync`。
7. 对一首确有下载和分发授权的歌曲验证 MP3/M4A 在 Telegram 播放器中显示，再启用定时。

在这些项目完成前，不将整个 Issue 标记为真实验收通过，不自动开启同步，不提前关闭 Issue。

## 本轮交付决定

- [1794474792] 用户决定先完成 PR，暂不联调真实 Telegram。因此保留 Issue，等待作者 review；不申请后续长期凭证，不部署 Worker 或开启定时同步。已有 Infisical 项目、空密钥目录、D1 表和私有 R2 桶保留。
- [1794474792] 仅运行源码静态解析、脚本静态语法及差异检查，没有进行本地构建、编译或测试。
