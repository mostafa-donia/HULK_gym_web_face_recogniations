import socket
import sys

try:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

def get_lan_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(('8.8.8.8', 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        pass
    try:
        hostname = socket.gethostname()
        for ip in socket.gethostbyname_ex(hostname)[2]:
            if not ip.startswith("127.") and not ip.startswith("169.254."):
                return ip
    except Exception:
        pass
    return "127.0.0.1"

lan_ip = get_lan_ip()
hostname = socket.gethostname()
ip_url = f"http://{lan_ip}:8000"
host_url = f"http://{hostname}:8000"

print("=" * 66)
print("  🎉 تم تجهيز المنفذ بنجاح! جاهز للاتصال من أي جهاز آخر.")
print("=" * 66)
print("")
print("  🌐 روابط فتح النظام من اللابتوب الثاني أو الموبايل:")
print(f"     ⭐ الرابط الثابت باسم الجهاز (موصى به - لا يتغير):")
print(f"        👉  {host_url}")
print(f"     🔹 أو رابط الـ IP المباشر:")
print(f"        👉  {ip_url}")
print("")
print("=" * 66)
print("  📋 خطوات هامة لضمان الاتصال السلس:")
print("  1. تأكد أن الجهازين متصلان بنفس شبكة الواي فاي أو الراوتر.")
print(f"  2. على الجهاز الثاني: افتح المتصفح واكتب الرابط: {host_url}")
print("  3. تأكد أن النظام يعمل على هذا الجهاز الرئيسي (السيرفر).")
print("  4. تأكد أن شبكة الواي فاي في ويندوز مضبوطة على 'Private network'.")
print("=" * 66)
