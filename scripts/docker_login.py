"""Launch the prebuilt Linux browser, then archive only after the container stops."""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
REQUIRED = ("R2_ENDPOINT", "R2_BUCKET", "R2_ACCESS_KEY_ID", "R2_SECRET_ACCESS_KEY", "PROFILE_ENCRYPTION_KEY")


def main():
    parser = argparse.ArgumentParser(description="在 Docker 的 Linux Chromium 登录 Google，自动加密归档并上传 R2。")
    parser.add_argument("--ini", default=str(ROOT / "config/browser.ini"))
    parser.add_argument("--state-dir", default=str(ROOT / ".runtime/docker-login"))
    parser.add_argument("--port", type=int, default=3000)
    parser.add_argument("--upload-only", action="store_true", help="重试上传上次已关闭浏览器的档案")
    args = parser.parse_args()
    env = load_environment()
    check_dependencies()
    secrets = load_secrets(env)
    state = Path(args.state_dir).expanduser().resolve()
    state.mkdir(parents=True, exist_ok=True, mode=0o700)
    state.chmod(0o700)
    ini = Path(args.ini).expanduser().resolve()
    if not ini.is_file() or not 1 <= args.port <= 65535:
        raise RuntimeError("请提供存在的 ini 文件和有效端口。")
    env.update(secrets)
    env.update(TGMUSIC_STATE_DIR=str(state), TGMUSIC_INI_PATH=str(ini),
               TGMUSIC_UID=str(os.getuid()), TGMUSIC_GID=str(os.getgid()), TGMUSIC_LOGIN_PORT=str(args.port))
    compose = ["docker", "compose", "--project-name", "tgmusic-login", "--file", str(ROOT / "docker-compose.login.yml")]
    try:
        if not args.upload_only:
            run(compose + ["run", "--rm", "--no-deps", "uploader", "prepare"], env)
            run(compose + ["up", "--detach", "browser"], env)
            print(f"请打开 http://127.0.0.1:{args.port}，在里面登录 Google 并进入 YouTube Music。", flush=True)
            print("登录有效后会自动关闭浏览器、归档完整 ini 和完整用户目录，再加密上传 R2。", flush=True)
            run(compose + ["run", "--rm", "--no-deps", "observer", "observe"], env)
        stop_browser(compose, env)
        run(compose + ["run", "--rm", "--no-deps", "uploader", "upload"], env)
        result = json.loads((state / "upload-result.json").read_text())
        print("上传成功：" + result["object"], flush=True)
        print("ini、Cookie、Local Storage、缓存和其余用户目录已一起加密归档；未上传明文。", flush=True)
        shutil.rmtree(state / "browser-config", ignore_errors=True)
        print("本次明文浏览器目录已清理；加密副本保存在 " + str(state / "google-profile.latest.enc"), flush=True)
    finally:
        subprocess.run(compose + ["down", "--remove-orphans"], env=env, cwd=ROOT, check=False)


def load_environment():
    env = os.environ.copy()
    path = ROOT / ".env"
    if path.exists():
        for line in path.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            env.setdefault(key.strip(), value.strip().strip("\"'"))
    return env


def check_dependencies():
    for executable in ("docker", "infisical"):
        if not shutil.which(executable):
            raise RuntimeError("请先安装并登录 " + executable + "。")
    result = subprocess.run(["docker", "info"], capture_output=True, timeout=20)
    if result.returncode:
        raise RuntimeError("Docker 没有启动，请先打开 Docker Desktop。")


def load_secrets(env):
    client_id, client_secret = env.get("INFISICAL_CLIENT_ID"), env.get("INFISICAL_CLIENT_SECRET")
    if bool(client_id) != bool(client_secret):
        raise RuntimeError("Infisical Client ID 和 Secret 需要同时填写，或使用现有的 CLI 登录。")
    if client_id:
        env["INFISICAL_UNIVERSAL_AUTH_CLIENT_ID"] = client_id
        env["INFISICAL_UNIVERSAL_AUTH_CLIENT_SECRET"] = client_secret
        result = subprocess.run(["infisical", "login", "--method=universal-auth", "--silent", "--plain",
                                 "--domain=" + env.get("INFISICAL_API_URL", "https://app.infisical.com")],
                                env=env, capture_output=True, text=True, timeout=40)
        if result.returncode or not result.stdout.strip():
            raise RuntimeError("Infisical 认证失败，尚未启动浏览器。")
        env["INFISICAL_TOKEN"] = result.stdout.strip()
    project = env.get("INFISICAL_PROJECT_ID")
    if not project:
        raise RuntimeError("请在仓库 .env 填写 INFISICAL_PROJECT_ID。")
    command = ["infisical", "secrets-manager", "secrets", "get", "--output=json", "--silent", "--expand=false",
               "--projectId=" + project, "--env=" + env.get("INFISICAL_ENVIRONMENT", "dev"),
               "--path=" + env.get("INFISICAL_SECRET_PATH", "/tgmusic/github-actions")]
    result = subprocess.run(command, env=env, capture_output=True, text=True, timeout=40)
    if result.returncode:
        raise RuntimeError("无法读取 Infisical 配置，请先运行 infisical login。")
    rows = json.loads(result.stdout) or []
    values = {row["secretKey"]: row["secretValue"] for row in rows}
    values = {key: env.get(key) or values.get(key, "") for key in (*REQUIRED, "R2_PROFILE_OBJECT")}
    missing = [key for key in REQUIRED if not values[key]]
    if missing:
        raise RuntimeError("Infisical 尚缺配置：" + ", ".join(missing) + "。尚未启动浏览器。")
    return values


def run(command, env):
    subprocess.run(command, env=env, cwd=ROOT, check=True)


def stop_browser(compose, env):
    run(compose + ["stop", "browser"], env)
    result = subprocess.run(compose + ["ps", "--all", "--quiet", "browser"], env=env, cwd=ROOT,
                            capture_output=True, text=True, check=True)
    for container in result.stdout.splitlines():
        status = subprocess.run(["docker", "inspect", "--format", "{{json .State}}", container],
                                env=env, capture_output=True, text=True, check=True)
        data = json.loads(status.stdout)
        if data["Running"] or data["ExitCode"] == 137:
            raise RuntimeError("浏览器未正常关闭，停止归档；保留原有 R2 备份。")


if __name__ == "__main__":
    os.umask(0o077)
    try:
        main()
    except KeyboardInterrupt:
        print("已取消；未覆盖 R2 备份。", file=sys.stderr)
        sys.exit(130)
    except RuntimeError as error:
        print(str(error), file=sys.stderr)
        sys.exit(1)
    except Exception as error:
        print("操作未完成：" + type(error).__name__ + "。敏感详情已隐藏；可修复后用 --upload-only 重试。", file=sys.stderr)
        sys.exit(1)
