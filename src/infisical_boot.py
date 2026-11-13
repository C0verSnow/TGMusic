import os
import subprocess
import sys


def main():
    required = ["INFISICAL_CLIENT_ID", "INFISICAL_CLIENT_SECRET", "INFISICAL_PROJECT_ID"]
    if any(not os.getenv(key) for key in required):
        print("Infisical bootstrap configuration missing", file=sys.stderr)
        return 1
    env = os.environ.copy()
    env["INFISICAL_UNIVERSAL_AUTH_CLIENT_ID"] = env.pop("INFISICAL_CLIENT_ID")
    env["INFISICAL_UNIVERSAL_AUTH_CLIENT_SECRET"] = env.pop("INFISICAL_CLIENT_SECRET")
    domain = env.get("INFISICAL_API_URL") or "https://app.infisical.com"
    command = ["infisical", "login", "--method=universal-auth", "--silent", "--plain", "--domain=" + domain]
    result = subprocess.run(command, env=env, capture_output=True, text=True, timeout=40)
    if result.returncode or not result.stdout.strip():
        print("Infisical authentication failed; no services started", file=sys.stderr)
        return 1
    env["INFISICAL_TOKEN"] = result.stdout.strip()
    if env.get("GITHUB_ACTIONS") == "true":
        print("::add-mask::" + env["INFISICAL_TOKEN"], flush=True)
    command = ["infisical", "run", "--expand=false", "--domain=" + domain, "--projectId=" + env["INFISICAL_PROJECT_ID"],
               "--env=" + (env.get("INFISICAL_ENVIRONMENT") or "dev"),
               "--path=" + (env.get("INFISICAL_SECRET_PATH") or "/tgmusic/github-actions"),
               "--", sys.executable, *sys.argv[1:]]
    return subprocess.run(command, env=env, check=False).returncode


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        print("Infisical bootstrap failed; sensitive output suppressed", file=sys.stderr)
        sys.exit(1)
