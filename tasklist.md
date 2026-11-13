# 本文档为4象限的任务清单，全文书写大白话

## 想做：
- [1794474792] PR 交给作者 review；后续真实账号联调按用户决定另行开展。

## 做完：
- [1794533810] 已按用户要求暂停，等待用户明确恢复；暂停期间不继续开发、部署、申请凭证或轮询联调。
- [1794534453] 恢复后核对 85d9a05 的 push CI 43345179904：Python、Worker 与 Docker 浏览器任务全部通过；PR CI 43345185486 也通过，Docker 在 PR 事件按配置跳过。
- [1794534453] 已检索 GitHub 的 Cloudflare workers-sdk 与 boto3，并比较 CLI 和 S3 能力。Wrangler 4.160.1 没有条件覆盖及自定义校验元数据参数；保留已有 boto3 条件上传，原因和参考链接已补进设计文档。
- [1794534453] 用户确认后，创建仅授权 tgmusic-private 对象读写的专用 R2 凭证，保存并回读核对 Infisical prod /github-actions 两项密钥；临时转交文件已删除，未把密钥写入日志或 Git。Docker 服务已启动，README 已补 Docker 人工登录和上传重试步骤。
- [1794472132] 已读取 Issue #1 正文与四条评论，以最新随笔为准；同步空仓库，创建 feature/issue-1-music-sync 分支；为提交 PR 建立最小 main 分支。
- [1794472797] 已在 GitHub 检索并比较 NeriPlayer、ytmusicapi，确认星数、近期提交、问题处理与 GPL-3.0 / MIT 许可证；只参考设计，自行实现代码，链接写入 docs/design.md。
- [1794472797] 已实现收藏完整分页、每目标基线和去重、授权音频与链接回退、Telegram 重试、D1 状态、R2 加密档案、逐首回执与待核对恢复。
- [1794473798] 已实现 Infisical 启动、Mihomo 美国备用出口、Cloudflare Worker 指令和角色权限，并提交草稿 PR #2。已修正第一轮工作流 YAML 解析问题。
- [1794473798] 已通过浏览器创建 Infisical 专用项目、D1 tgmusic、R2 tgmusic-private；用户亲自开通 R2 订阅，确认桶公开访问关闭。没有创建长期 R2 凭证。
- [1794474385] 用户允许使用 Cloudflare / Infisical CLI；已通过 Wrangler 在远端应用 D1 迁移，在 Infisical prod 创建 shared、github-actions、cloudflare-worker 目录。检查 1/.env 后确认属于其他项目，没有复用其凭证。
- [1794474484] 已补齐 Admin 仅同步授权目标、建连超时安全重试、部署文档、登录档案导入、恢复入口和密钥轮换说明。
- [1794474792] 远端 CI 43189104317 通过：Python 26 项、Worker 7 项、Worker 打包；实际验证有头 Chromium、加密档案 Cookie 恢复、MP3/M4A 转码、固定工具校验安装及真实 S3/D1 客户端。浏览器和存储测试使用测试数据，没有冒充真实账号验收。
- [1794474792] 完成源码静态语法、脚本静态语法、JSON 和差异检查；已更新 README、设计参考和验收清单。

- [1794530653] 用户要求开始真实 Telegram 联调，指定使用 gotd tg CLI；先读取官方 README、现有 CLI 登录状态和项目配置，不进行本地构建或编译。
- [1794531715] 已获用户同意创建专用测试 Bot；通过 tg CLI 创建 C0verSnow_TGMusic_Test_bot，Token 写入 Infisical。已从本人账号发送 /start，并从 tg history 看到 Bot API 的真实回复。
- [1794531715] 用户要求补齐剩余工作和明确问题；并行只读审查规范与规格，确认失败目标可能耗尽预算、浏览器 UNKNOWN 未触发备用代理。真实 Google 账号尚未登录，不能把此前测试 Cookie 当成账号登录。
- [1794531715] Infisical CLI 带格式令牌被误作纯令牌触发报错，已撤销该会话，并用服务器返回 401 确认旧会话失效；正在重新登录。不记录令牌值。

- [1794533810] 用户明确要求暂停；本轮停止后续开发、云端配置和联调，只补齐此任务日志。最新功能分支提交为 85d9a05，已经推送；没有合并 PR，也没有关闭 Issue。
- [1794533810] 真实 Telegram：已通过 gotd tg CLI 创建专用 Bot @C0verSnow_TGMusic_Test_bot；Token 已写入 TGMusic Infisical 的 github-actions / cloudflare-worker 目录，未写入仓库。本人账号发送 /start 后，Bot API 成功回复，tg history 已确认收到。当前仅验证文本收发，尚未验证真实音频、群组与 Worker 指令。
- [1794533810] 凭证处理：曾因把 Infisical CLI 带格式输出误作纯令牌，触发含会话凭证的报错；已撤销该 CLI 会话，并确认旧会话被服务器以 401 拒绝，随后重新完成浏览器登录。本日志不记录任何令牌值。
- [1794533810] 代码检查：规范审查发现 main 夹杂恢复细节；规格核对确认 403 拒收目标可能耗尽额度、浏览器 UNKNOWN 没有触发备用代理。已在 5874f43 修复目标暂停隔离、代理重试、恢复档案清理和主流程整理；对应远端 CI 43341968873 已通过。没有添加未经需求确认的自动重发音频行为。
- [1794533810] Docker 方案：用户要求在 Docker 里亲自登录 Google，再自动归档完整 ini 与完整用户目录并上传 Cloudflare。85d9a05 已加入 docker-compose.login.yml、docker-login.sh、docker_login.py、docker_session.py、docker-entrypoint.sh；使用固定摘要的预构建镜像，不含本地 Docker 构建步骤。
- [1794533810] 档案实现：新增加密 bundle 格式 2，包含 manifest、完整 ini、完整 Chromium User Data（含缓存与空目录，只排除运行时锁和调试端口文件），保留旧格式读取。先关闭浏览器容器，再归档；上传失败保留云端旧版本。上述新 Docker 改动尚未取得最终远端验证结果，不能视为已经可直接交付运行。
- [1794533810] GitHub 检索：本轮已读取 gotd/cli 官方 README，并比较 LinuxServer Chromium、TigerVNC、noVNC 与 cloudflared 的维护、许可证和近期问题。最终用户选择 Docker 登录，不继续搭建临时公网远端桌面。
- [1794533810] 云配置：Infisical 已保存本应用 Telegram 配置、R2 地址与桶名、Cloudflare 账号和 D1 标识、生成的档案加密密钥。本机 .env 仅保存项目定位参数，Docker 可使用现有 Infisical CLI 登录。新建专用机器身份被 Infisical 的身份数量上限拒绝；未删除或复用其他应用身份。
- [1794533810] 用户最新要求优先使用对应 CLI，实在不行再用浏览器。已用 Wrangler 确认 tgmusic-private 存在，并查看远端对象 put/get 命令。当前 Docker 上传仍使用 boto3，需要改成优先 Wrangler 的方案；这一步尚未实现。浏览器仅导航至 R2 凭证页面，未提交创建任何 R2 长期凭证。

## 没做：
- [1794474792] 遵守仓库约定，没有进行本地构建、编译、测试或冒烟脚本验证。
- [1794474792] 用户决定先完成 PR，暂不联调真实 Telegram；真实 Google 登录、音频发出、生产凭证、跨目录权限和 Worker 上线尚未验收，未开启定时同步。
- [1794474792] 未合并 PR，未提前关闭 Issue；PR 合并后由关联的 Closes #1 关闭，交给作者 review。


- [1794533810] 暂停时未完成：Docker 上传改为优先 Wrangler CLI；核对 CLI 方案的版本与并发保护；Docker 实际启动、完整 ini/用户目录归档及真实 R2 上传验证；补齐 Docker 使用文档和最新远端 CI 结果。
- [1794533810] 真实 Google 账号从未在远端或 Docker 浏览器登录。此前 CI 只验证测试 Cookie，不能当成真实 Google 登录证据。待恢复任务后，由用户亲自完成 Google 登录及二次验证，再检查新 Runner 恢复。
- [1794533810] 其余接入仍未完成：Actions 专用机器身份与 GitHub 启动 Secrets、Worker 部署与 Infisical Secret Sync、Webhook 注册、真实音频/群组/去重联调、定时同步。Infisical 身份额度问题仍需处理；没有启动真实定时同步。
- [1794533810] 本轮没有进行本地构建、编译、测试或冒烟验证，也没有启动本地 Docker 登录服务；仅做静态解析与差异检查，执行 Telegram / Infisical / Cloudflare 的实际 CLI 操作，代码测试交给远端 CI。

## 在做：
- [1794534511] 已启动实际 Docker 登录流程，正在下载固定摘要的预构建镜像；不含本地构建步骤。待桌面就绪后由用户亲自登录 Google，再检查真实加密档案上传。
- [1794534048] 用户要求继续，恢复 Docker 登录归档工作：先核对上次远端 CI，查清 Wrangler 上传的版本与条件覆盖能力，再补齐实现和文档；不进行本地编译验证。
