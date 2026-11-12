# Issue #1 验收记录

本文件区分“代码有测试”和“真实服务已跑通”，没有把自动化测试替代真实账号验证。禁止本地编译验证，测试在 GitHub CI 执行。

## 已有远端证据

[CI 43186861035](https://github.com/C0verSnow/TGMusic/actions/runs/43186861035)：Python 17 项通过，Node Worker 6 项通过，Worker 打包检查通过，对应提交 `29e3fa7`。之后新增或修改的内容以最终 PR 检查为准。

| 验收项 | 证据或现状 |
|---|---|
| AT-01/02/04 新增、无新增、不重复 | `test_baseline_then_only_new_and_no_repeat` |
| AT-03 发送失败保留重试 | `test_failure_is_retried_without_resending_success` |
| AT-05 新 Runner 恢复历史 | D1 为持久化来源；SQLite 测试已覆盖重用历史，真实跨 Runner 待验收 |
| AT-06 首次基线/all | `test_all_mode_and_global_budget`，每目标单独 baseline |
| AT-07 登录失败保留状态 | 主流程在读列表/修改歌曲状态前检查；真实失效账号待验收 |
| AT-08 未授权音源回退 | `test_audio_requires_explicit_permission`、cipher stream fallback；实际播放待验收 |
| AT-09 加密档案恢复 | `test_encrypted_roundtrip_and_excludes_runtime_files`；R2 实际档案待导入 |
| AT-10/11/12/13 浏览器/Xvfb/登录 | 代码已接入，需 Linux Google 登录档案与真实 Runner 验收 |
| AT-14/15/16 Mihomo/TUN/出口 | 配置、路由、美国出口和固定代理已实现；真实代理节点待提供与验收 |
| AT-17/18 音频发送 | HTTP 发送/重试路径有测试；真实 Bot 用户和群组待配置 |
| AT-19/20 白名单与入群不自动授权 | Worker `guest has help only...`、admin scope 测试通过 |
| AT-21/22/23 多目标与隔离失败 | `test_targets_are_independent_and_new_target_baselines` |
| AT-24 存储失败保留数据 | receipt 恢复、历史丢失拒绝发送、租约、档案完整性测试通过 |
| AT-25 Webhook Secret | Worker `webhook rejects missing/wrong secret...` |
| AT-26 触发 Actions | Worker `owner dispatches once...`；真实细粒度触发 Token 待配置 |
| AT-27 GitHub 只存启动凭证 | sync.yml 仅引用两项 Infisical Secret；部署配置待完成 |
| AT-28/29 Universal Auth/密钥注入 | 已核对 CLI 0.45.6 官方源码和命令支持；专用身份及真实 Runner 注入待验收 |
| AT-30 YAML 配置写入 | 权限 0600、退出删除；真实 Mihomo 验收待进行 |
| AT-31 R2/Telegram/解密密钥 | 需实际凭证和登录档案联调 |
| AT-32/33 独立身份/跨路径隔离 | 按独立路径、独立身份/Secret Sync 部署；需实际拒绝访问证据 |
| AT-34 Infisical 失败退出 | boot 捕获认证输出并拒绝启动；真实拒绝认证待远端验收 |
| AT-35 日志脱敏 | 第三方异常不输出原文；敏感值注册 GitHub mask，测试未使用真实凭证 |

## 已创建的云资源

- Infisical：专用项目 youtube-music-telegram-sync，prod 下 shared / github-actions / cloudflare-worker 目录。
- Cloudflare D1：tgmusic，`0001_initial.sql` 已通过 Wrangler 在远端应用。
- Cloudflare R2：tgmusic-private，控制台确认 Public Access Disabled；用户已自行开通 R2 订阅。

## 真实部署需要完成

1. R2 桶级对象读写凭证、D1 API Token、档案加密密钥写入 Infisical。
2. 确认使用哪个 Telegram Bot 和 Owner/默认私聊数字 ID，目标用户先发送 `/start`。
3. Actions 专用 Universal Auth 与 Worker Secret Sync 设置最小权限，并验证另一目录访问被拒绝。
4. 导入兼容 Linux 的有效 Google 登录档案，不上传日常个人浏览器目录。
5. 手动执行一次 Runner：确认实际出口、登录、列表分页、R2 解密和默认基线；新增歌曲后验证发送与再次运行不重复。
6. 部署 Worker、注册 Webhook；测试错误 Secret、Guest、Owner/Admin、未授权群组、真实 `/sync`。
7. 对一首确有下载和分发授权的歌曲验证 MP3/M4A 在 Telegram 播放器中显示，再启用定时。

在这些项目完成前，不将整个 Issue 标记为真实验收通过，不自动开启同步，不提前关闭 Issue。
