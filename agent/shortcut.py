"""Desktop icon, and a Startup entry so 'Hey Mira' works right after Windows starts."""
import os
import subprocess
import sys

from . import config

ICON = config.DATA / "mira.ico"

SCRIPT = r"""
$shell = New-Object -ComObject WScript.Shell
$folder = [Environment]::GetFolderPath($env:MIRA_FOLDER)
$link = $shell.CreateShortcut((Join-Path $folder ($env:MIRA_NAME + '.lnk')))
$link.TargetPath = $env:MIRA_TARGET
$link.Arguments = $env:MIRA_ARGS
$link.WorkingDirectory = $env:MIRA_DIR
$link.IconLocation = $env:MIRA_ICON
$link.Description = 'Bangla and English AI assistant'
$link.Save()
"""
REMOVE = r"""
$path = Join-Path ([Environment]::GetFolderPath('Startup')) ($env:MIRA_NAME + '.lnk')
if (Test-Path $path) { Remove-Item $path }
"""


def make_icon():
    config.DATA.mkdir(exist_ok=True)
    icon_image().save(ICON, sizes=[(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])


def icon_image():
    from PIL import Image, ImageDraw, ImageFont
    size = 256
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    for i in range(size // 2, 0, -1):  # soft violet circle
        t = i / (size / 2)
        draw.ellipse([size / 2 - i, size / 2 - i, size / 2 + i, size / 2 + i],
                     fill=(int(124 + 60 * (1 - t)), int(92 + 40 * (1 - t)), 246, 255))
    try:
        font = ImageFont.truetype("segoeuib.ttf", 150)
    except OSError:
        font = ImageFont.load_default(150)
    draw.text((size / 2, size / 2 + 6), config.NAME[:1].upper(), font=font, fill="white", anchor="mm")
    return img


def powershell(script, **values):
    env = {**os.environ, **{f"MIRA_{k.upper()}": str(v) for k, v in values.items()}}
    subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script],
                   env=env, check=True, capture_output=True, timeout=60)


def windowless_python():
    exe = os.path.join(os.path.dirname(sys.executable), "pythonw.exe")
    return exe if os.path.isfile(exe) else sys.executable


def create(folder, args, name=None):
    icon = ICON
    try:
        if not ICON.exists():
            make_icon()
    except Exception:  # an icon is nice to have, not required
        icon = windowless_python()
    powershell(SCRIPT, folder=folder, name=name or config.NAME, target=windowless_python(),
               args=f'"{config.BASE / "main.py"}" {args}', dir=config.BASE, icon=icon)


def install(startup=True):
    if os.name != "nt":
        return "Shortcut shudhu Windows e hoy."
    create("Desktop", "--app")
    lines = [f"Desktop e '{config.NAME}' icon toiri hoyeche."]
    if startup:
        create("Startup", "--background")
        lines.append("Windows chalu holei 'Hey Mira' shunbe (Startup e add kora hoyeche).")
    return "\n".join(lines)


def remove_startup():
    if os.name == "nt":
        powershell(REMOVE, name=config.NAME)
    return "Startup theke bad deya hoyeche."
