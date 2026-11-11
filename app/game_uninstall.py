"""Explicitly approved deletion of one validated PC game folder.

Never asks for administrator access, bypasses access controls, or touches other
game folders. Refuses Windows reparse points inside the chosen directory.
"""
from pathlib import Path
import os
import sys
import shutil
import stat


def validated_game_directory(game, games_root):
    if not game or game.get('type') != 'pc':
        raise ValueError('Full-folder removal is available only for PC games. ROMs can be removed from the library without affecting the emulator or ISO.')
    raw_folder = Path(game.get('folder') or '')
    raw_root = Path(games_root)
    if not raw_folder.is_dir() or not raw_root.is_dir():
        raise ValueError('Game folder or games library no longer exists.')
    if raw_folder.is_symlink() or raw_root.is_symlink():
        raise ValueError('Refusing to remove a linked game directory.')
    folder = raw_folder.resolve(strict=True)
    root = raw_root.resolve(strict=True)
    if folder == root or folder.parent != root:
        raise ValueError('Only one directly contained game folder may be removed. The game library root and shared folders are protected.')
    if not folder.name or folder.name in ('.', '..'):
        raise ValueError('Unsafe game directory name.')
    if not game['id'].startswith('pc:') or game['id'][3:].casefold() != str(raw_folder).casefold():
        raise ValueError('The game ID does not match the folder selected for removal.')
    # The game's binary must be INSIDE the selected folder (not outside it).
    exe = Path(game.get('exe') or '')
    if not exe.is_file() or exe.is_symlink() or not exe.resolve().is_relative_to(folder):
        raise ValueError('Executable is outside the selected game folder or is unavailable. Removal was blocked.')
    # Junctions are reparse points on Windows, even when they aren't detected by
    # Path.is_symlink(). Neither a linked game folder nor a linked library root
    # is eligible for recursive folder removal.
    if sys.platform == 'win32':
        import ctypes
        for path in (raw_root, raw_folder):
            attributes = ctypes.windll.kernel32.GetFileAttributesW(str(path))
            if attributes == 0xFFFFFFFF or attributes & 0x400:
                raise ValueError('A Windows reparse-point/linked folder cannot be uninstalled automatically.')
        # Remote/removable drives may not have a Recycle Bin. Never risk a
        # direct shell deletion on those devices.
        if ctypes.windll.kernel32.GetDriveTypeW(str(folder.anchor)) != 3:  # DRIVE_FIXED
            raise ValueError('Game removal requires a fixed local drive with a Windows Recycle Bin. Network and removable drives are protected.')
        windir = Path(os.environ.get('WINDIR', 'C:/Windows')).resolve(strict=False)
        forbidden = [windir, Path(os.environ.get('ProgramFiles', 'C:/Program Files')),
                     Path(os.environ.get('ProgramFiles(x86)', 'C:/Program Files (x86)'))]
        if any(root == p.resolve(strict=False) or root.is_relative_to(p.resolve(strict=False)) for p in forbidden):
            raise ValueError('System and program installation directories are protected.')
    return folder


def delete_entire_folder(folder):
    """Permanently remove the precise validated directory after explicit approval.

    The UI owns the single confirmation. Python does not show shell prompts.
    Files locked by Windows or requiring additional permission fail normally:
    no privilege escalation, registry hacks, or forced ownership changes.
    """
    folder=Path(folder)
    if not folder.is_dir() or folder.is_symlink():
        raise ValueError('The selected game folder no longer exists or is linked.')
    # Refuse every link/junction: a legitimate standalone game shouldn't require
    # us to follow external paths. This check is intentionally conservative.
    for current,dirs,files in os.walk(folder, topdown=True, followlinks=False):
        for name in dirs+files:
            p=Path(current)/name
            info=p.lstat()
            if stat.S_ISLNK(info.st_mode) or (sys.platform=='win32' and (getattr(info,'st_file_attributes',0) & 0x400)):
                raise ValueError('This game contains a linked/reparse-point file or folder; permanent uninstall is blocked. Remove only its library entry instead.')
    try:
        shutil.rmtree(folder)
    except (PermissionError,OSError) as exc:
        raise RuntimeError('Windows could not delete every item. Close the game and any installers, then inspect its folder: '+str(exc)) from exc
    if folder.exists():
        raise RuntimeError('Deletion was incomplete. Check the selected game folder.')
    return True
