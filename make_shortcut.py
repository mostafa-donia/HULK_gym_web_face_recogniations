import os
import sys
import base64
import subprocess

try:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

# Setup django environment
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)
sys.path.insert(0, os.path.join(BASE_DIR, "apps"))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

try:
    import django
    django.setup()
    from apps.core.models import GymProfile
    from django.core.files import File
    profile = GymProfile.get_solo()
    gym_name = profile.gym_name or "Systemize Gym"
except Exception as e:
    profile = None
    gym_name = "Systemize Gym"

# 1. Image path argument
custom_logo = sys.argv[1] if len(sys.argv) > 1 else ""
custom_logo = custom_logo.strip().strip('"').strip("'")

ico_path = os.path.join(BASE_DIR, "gym_icon.ico")
from PIL import Image

src_img_path = None
if custom_logo and os.path.isfile(custom_logo):
    src_img_path = custom_logo
    # Also save to profile
    if profile:
        try:
            ext = os.path.splitext(custom_logo)[1].lower()
            with open(custom_logo, "rb") as f:
                profile.logo.save(f"gym_logo{ext}", File(f), save=True)
            print(f"[OK] Gym logo updated in database: {profile.gym_name}")
        except Exception as e:
            print(f"[!] Note: Database logo update skipped ({e})")
elif profile and profile.logo:
    try:
        if os.path.isfile(profile.logo.path):
            src_img_path = profile.logo.path
    except Exception:
        pass

# Check if logo.png exists in current directory as fallback
if not src_img_path:
    for candidate in ["logo.png", "logo.jpg", "logo.jpeg", "gym_logo.png", "gym_logo.jpg"]:
        c_path = os.path.join(BASE_DIR, candidate)
        if os.path.isfile(c_path):
            src_img_path = c_path
            break

if src_img_path and os.path.isfile(src_img_path):
    try:
        img = Image.open(src_img_path)
        img = img.convert("RGBA")
        icon_sizes = [(256, 256), (128, 128), (64, 64), (48, 48), (32, 32), (16, 16)]
        img.save(ico_path, format="ICO", sizes=icon_sizes)
        print(f"[OK] Generated Windows icon from: {os.path.basename(src_img_path)}")
    except Exception as e:
        print(f"[!] Warning generating icon from image: {e}")
        ico_path = ""
else:
    # If no image found, generate a sleek colored gym icon
    try:
        from PIL import ImageDraw
        img = Image.new("RGBA", (256, 256), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        draw.rounded_rectangle([10, 10, 246, 246], radius=40, fill=(15, 23, 42, 255), outline=(132, 204, 22, 255), width=12)
        draw.ellipse([65, 65, 191, 191], fill=(132, 204, 22, 255))
        img.save(ico_path, format="ICO")
        print("[OK] Generated default high-res Systemize icon.")
    except Exception:
        ico_path = ""

# Target files
bat_target = os.path.join(BASE_DIR, "START_SYSTEMIZE.bat")
work_dir = BASE_DIR

# Clean name for shortcut (Latin/ASCII safe for all Windows Shell versions)
ascii_name = "".join([c for c in gym_name if (c.isalnum() or c in (" ", "-", "_")) and ord(c) < 128]).strip()
while "  " in ascii_name:
    ascii_name = ascii_name.replace("  ", " ")
safe_gym_name = ascii_name if len(ascii_name) >= 3 else "Systemize Gym"

# Build PowerShell script with full UTF-16 Base64 encoding to support all Unicode/Arabic characters
ps_script = f"""
$Desktop = [Environment]::GetFolderPath('Desktop')
if (-not (Test-Path $Desktop)) {{
    $Desktop = Join-Path $env:USERPROFILE 'Desktop'
}}
$WshShell = New-Object -ComObject WScript.Shell
$ShortcutPath = Join-Path $Desktop "{safe_gym_name}.lnk"
$Shortcut = $WshShell.CreateShortcut($ShortcutPath)
$Shortcut.TargetPath = "{bat_target}"
$Shortcut.WorkingDirectory = "{work_dir}"
$Shortcut.Description = "{safe_gym_name} - Systemize Gym OS"
if ('{ico_path}' -ne '' -and (Test-Path '{ico_path}')) {{
    $Shortcut.IconLocation = "{ico_path},0"
}}
$Shortcut.Save()
Write-Host "[OK] Saved shortcut to $ShortcutPath"
"""

encoded_ps = base64.b64encode(ps_script.encode("utf-16le")).decode("ascii")

try:
    subprocess.run(["powershell", "-NoProfile", "-EncodedCommand", encoded_ps], check=True)
    print("=" * 64)
    print(f" [V] Desktop Shortcut Created Successfully!")
    print(f"     Name: {safe_gym_name}.lnk")
    print(f"     Icon: {ico_path}")
    print("=" * 64)
except Exception as e:
    print(f"[!] Error creating desktop shortcut: {e}")
