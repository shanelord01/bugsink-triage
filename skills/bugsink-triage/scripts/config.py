#!/usr/bin/env python3
"""Show or create the Bugsink Triage config. Never prints a token.

  config.py show    # the effective settings, where each came from, and whether a token resolves
  config.py init    # copy the commented example into the state directory (never overwrites)
  config.py path    # where the config file is read from
"""
import os
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import bugsink as bs  # noqa: E402

EXAMPLE = Path(__file__).resolve().parent.parent / "bugsink-triage.config.example.json"


def main() -> None:
    cmd = sys.argv[1] if len(sys.argv) > 1 else "show"
    path = bs.config_path()
    if cmd == "path":
        print(path)
    elif cmd == "init":
        if path.exists():
            sys.exit(f"{path} already exists; not overwriting.")
        path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(EXAMPLE, path)
        print(f"Wrote {path}. Edit it and keep only what you need.")
    elif cmd == "show":
        cfg = bs.config()
        print(f"config file   {path} ({'found' if path.exists() else 'not found, using defaults'})")
        url_env = cfg.get("urlEnv") or "BUGSINK_URL"
        print(f"server        {'set' if os.environ.get(url_env) or cfg.get('baseUrl') else 'NOT SET'} (env {url_env}"
              f"{', baseUrl in config' if cfg.get('baseUrl') else ''})")
        for label, env, cmd_key in (("read token", cfg.get("readTokenEnv") or "BUGSINK_TOKEN", "readTokenCommand"),
                                    ("write token", cfg.get("writeTokenEnv") or "BUGSINK_TRIAGE_TOKEN", "writeTokenCommand")):
            src = f"env {env}" if os.environ.get(env) else ("command in config" if cfg.get(cmd_key) else "not set")
            print(f"{label:<13} {src}")
        print(f"state dir     {bs.state_dir()}")
        print(f"projects      {bs.default_projects() or 'all'}")
        print(f"tags          {', '.join(bs.tags_to_show())}")
        print(f"repos         {cfg.get('repos') or 'none (no PR discovery)'}")
        print(f"prSessions    {len(cfg.get('prSessions') or {})} mapped")
        print(f"handoff due   {cfg.get('handoffDueHours', 24)} hours")
        print(f"style note    {cfg.get('styleNote') or 'none'}")
    else:
        sys.exit(__doc__)


if __name__ == "__main__":
    main()
