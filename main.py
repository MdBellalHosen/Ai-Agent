"""Run the assistant:
    python main.py               terminal chat
    python main.py --app         window app (also what the Desktop icon runs)
    python main.py --background  no window, waits for "Hey Mira" (runs at Windows start)
    python main.py --install     Desktop icon + Windows start + wake word model
    python main.py --no-startup  stop starting with Windows
    python main.py --check       test the setup
"""
import sys


def quiet_logs():
    """pythonw has no console, so keep messages in data/app.log instead."""
    if sys.stdout is None or sys.stderr is None:
        from agent import config
        config.DATA.mkdir(exist_ok=True)
        log = open(config.DATA / "app.log", "a", encoding="utf-8", buffering=1)
        sys.stdout = sys.stderr = log


def install():
    from agent import shortcut, wake
    if not wake.installed():
        try:
            wake.download()
        except Exception as err:
            print(f"Wake word model download hoyni ({err}). Pore abar: python main.py --install")
    print(shortcut.install(startup=wake.enabled()))
    return 0


if __name__ == "__main__":
    args = sys.argv[1:]
    if "--check" in args:
        from agent.check import run
        sys.exit(run(offline="--offline" in args))
    if "--install" in args:
        sys.exit(install())
    if "--no-startup" in args:
        from agent.shortcut import remove_startup
        print(remove_startup())
        sys.exit(0)
    if "--app" in args or "--background" in args:
        quiet_logs()
        from agent.web import serve
        sys.exit(serve(open_window="--app" in args))
    from agent.cli import main
    main()
