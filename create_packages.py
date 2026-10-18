import os
import sys
import zipfile
import time

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

PACKAGES = [
    {
        "name": "Systemize.zip",
        "source": os.path.join(BASE_DIR, "dist", "Systemize"),
        "root_in_zip": "Systemize",
    },
    {
        "name": "ControlCenter.zip",
        "source": os.path.join(BASE_DIR, "dist", "ControlCenter"),
        "root_in_zip": "ControlCenter",
    },
    {
        "name": "Presentation.zip",
        "source": os.path.join(BASE_DIR, "presentation"),
        "root_in_zip": "Presentation",
    },
]

EXCLUDE_DIRS = {"__pycache__", ".git", ".idea", ".vscode", "tmp", "temp"}
EXCLUDE_EXTS = {".pyc", ".pyo", ".pyd~"}

def zip_folder(source_dir, output_zip_path, root_in_zip):
    print(f"\n==========================================")
    print(f"[*] Packaging: {os.path.basename(output_zip_path)}")
    print(f"    Source: {source_dir}")
    print(f"==========================================")
    t0 = time.time()
    total_files = 0
    total_bytes = 0

    with zipfile.ZipFile(output_zip_path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
        for root, dirs, files in os.walk(source_dir):
            dirs[:] = [d for d in dirs if d not in EXCLUDE_DIRS]
            for file in files:
                ext = os.path.splitext(file)[1].lower()
                if ext in EXCLUDE_EXTS:
                    continue
                file_path = os.path.join(root, file)
                rel_path = os.path.relpath(file_path, source_dir)
                archive_name = os.path.join(root_in_zip, rel_path) if root_in_zip else rel_path
                zf.write(file_path, archive_name)
                total_files += 1
                try:
                    total_bytes += os.path.getsize(file_path)
                except OSError:
                    pass

    elapsed = time.time() - t0
    zip_size_mb = os.path.getsize(output_zip_path) / (1024 * 1024)
    raw_size_mb = total_bytes / (1024 * 1024)
    print(f"[V] Done: {output_zip_path}")
    print(f"    Files packed: {total_files}")
    print(f"    Raw size: {raw_size_mb:.2f} MB -> Zip size: {zip_size_mb:.2f} MB")
    print(f"    Time taken: {elapsed:.1f}s")
    return output_zip_path, zip_size_mb

def main():
    print("[*] Starting Final Packaging for the 3 Deliverables...")
    results = []
    for pkg in PACKAGES:
        out_zip = os.path.join(BASE_DIR, pkg["name"])
        if os.path.exists(out_zip):
            try:
                os.remove(out_zip)
            except Exception as e:
                print(f"[!] Warning removing old zip {out_zip}: {e}")
        path, size_mb = zip_folder(pkg["source"], out_zip, pkg["root_in_zip"])
        results.append((pkg["name"], path, size_mb))

    print("\n==========================================")
    print("           PACKAGING SUMMARY")
    print("==========================================")
    for name, path, size_mb in results:
        print(f" - {name:20s}: {size_mb:8.2f} MB | {path}")
    print("==========================================")
    print("[V] All 3 packages ready for standalone deployment!")

if __name__ == "__main__":
    main()
