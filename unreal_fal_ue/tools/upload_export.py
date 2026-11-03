"""Zip an AnyScene export folder (stored, no compression: PNG/GLB are already compressed) and upload it to fal storage.

    python upload_export.py <export_dir> <out.zip>
Prints the URL and writes it next to the zip as <out.zip>.url. FAL_KEY comes from the environment."""
import os
import sys
import time
import zipfile

import fal_client

src, dst = sys.argv[1], sys.argv[2]
t = time.time()
if not os.path.exists(dst):
    with zipfile.ZipFile(dst + ".part", "w", zipfile.ZIP_STORED, allowZip64=True) as z:
        for root, _, files in os.walk(src):
            for f in files:
                p = os.path.join(root, f)
                z.write(p, os.path.relpath(p, src).replace("\\", "/"))
    os.replace(dst + ".part", dst)
print(f"zip {os.path.getsize(dst) / 1e9:.2f} GB in {time.time() - t:.0f}s", flush=True)
t = time.time()
url = fal_client.upload_file(dst)
print(f"uploaded in {time.time() - t:.0f}s", flush=True)
print(url)
open(dst + ".url", "w").write(url)
