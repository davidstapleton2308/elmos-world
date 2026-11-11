"""Read-only discovery adapters for future store integration.

No authentication, store APIs, account data, automatic imports, launch attempts,
or changes to game folders. Future integrations should implement a common interface
and require explicit user consent before importing a third-party library.
"""
import json, os
from pathlib import Path

class Provider:
 def __init__(self,name,description,launcher_paths=(),metadata_paths=()):
  self.name=name
  self.description=description
  self.launcher_paths=tuple(launcher_paths)
  self.metadata_paths=tuple(metadata_paths)
 def discovery(self):
  launchers=[str(p) for p in self.launcher_paths if p.is_file()]
  return {'name':self.name,'status':'planned','installed':bool(launchers),
          'launcherPath':launchers[0] if launchers else None,
          'note':self.description,'libraryConnected':False}

def providers():
 pf=Path(os.environ.get('PROGRAMFILES',r'C:\Program Files'))
 pf86=Path(os.environ.get('PROGRAMFILES(X86)',r'C:\Program Files (x86)'))
 local=Path(os.environ.get('LOCALAPPDATA',str(Path.home()/'AppData/Local')))
 return [
  Provider('Steam','Steam installation detection only. Library import and supported launch integration are future work.',
   [pf86/'Steam/steam.exe',pf/'Steam/steam.exe']),
  Provider('Epic Games','Epic Launcher detection only. Manifest discovery/import requires a separate opt-in adapter.',
   [pf86/'Epic Games/Launcher/Portal/Binaries/Win64/EpicGamesLauncher.exe',pf/'Epic Games/Launcher/Portal/Binaries/Win64/EpicGamesLauncher.exe']),
  Provider('GeForce NOW','Separate cloud shortcut collection is available; account-library sync is not implemented.',
   [local/'NVIDIA Corporation/GeForceNOW/CEF/GeForceNOW.exe',pf86/'NVIDIA Corporation/GeForceNOW/CEF/GeForceNOW.exe',pf/'NVIDIA Corporation/GeForceNOW/CEF/GeForceNOW.exe',local/'NVIDIA Corporation/GeForceNOW/GeForceNOW.exe',pf86/'NVIDIA Corporation/GeForceNOW/GeForceNOW.exe',pf/'NVIDIA Corporation/GeForceNOW/GeForceNOW.exe'])
 ]

def discover():return [p.discovery() for p in providers()]
