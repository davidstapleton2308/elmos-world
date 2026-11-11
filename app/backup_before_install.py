"""Installer preflight: backup user settings, never import server or start the app."""
import sys
from pathlib import Path
from datetime import datetime
import json,shutil,secrets
p=Path.home()/"AppData/Local/SteamMatch"
if not sys.platform.startswith("win"):sys.exit(0)
files=["settings.json","registry_v2.json","arcade.json","grove_state.json","launch_profiles.json"]
if not any((p/f).is_file() for f in files):sys.exit(0)
root=p/"restore_points"/ (datetime.now().strftime("%Y%m%d-%H%M%S")+"-"+secrets.token_hex(2))

root.mkdir(parents=True,exist_ok=False)
for f in files:
 if (p/f).is_file():shutil.copy2(p/f,root/f)
(root/"manifest.json").write_text(json.dumps({"created":int(datetime.now().timestamp()),"version":"pre-v2.0","files":[f for f in files if (p/f).exists()]}),encoding="utf8")
print("Settings backed up before upgrade:",root)
