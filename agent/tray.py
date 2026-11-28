"""Icon near the Windows clock: open Mira, talk, private mode, voice, quit."""
import threading

from . import config, voice


def start(app, server, launch):
    """Shows the tray icon. Returns the icon, or None if pystray is missing or TRAY=off."""
    if config.env("TRAY", "on").lower() in ("off", "no", "0", "false"):
        return None
    try:
        import pystray
        from .shortcut import icon_image
    except Exception as err:
        print(f"  [tray problem] {err}")
        return None

    def open_window(icon=None, item=None):
        launch(app.url)

    def talk(icon=None, item=None):
        if not app.page_open():
            launch(app.url)
        app.mic()

    def toggle_private(icon, item):
        if not app.busy():
            voice.settings["private"] = not voice.settings["private"]

    def toggle_mute(icon, item):
        voice.settings["muted"] = not voice.settings["muted"]
        if voice.settings["muted"]:
            voice.stop_speaking()

    def quit_all(icon, item):
        icon.stop()
        app.stop()
        threading.Thread(target=server.shutdown, daemon=True).start()

    menu = pystray.Menu(
        pystray.MenuItem(f"{config.NAME} খোলো", open_window, default=True),
        pystray.MenuItem("কথা বলো", talk),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("প্রাইভেট মোড", toggle_private, checked=lambda item: voice.settings["private"]),
        pystray.MenuItem("ভয়েস বন্ধ", toggle_mute, checked=lambda item: voice.settings["muted"]),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem(f"{config.NAME} বন্ধ করো", quit_all),
    )
    icon = pystray.Icon("mira", icon_image(), f"{config.NAME}: \"Hey Mira\" বলো", menu)
    try:
        icon.run_detached()
    except Exception as err:
        print(f"  [tray problem] {err}")
        return None
    return icon
