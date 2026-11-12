import json
from pathlib import Path
import tempfile
import unittest
import sys

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "app"))
from store_inventory import collect_inventory, match_candidate, parse_keyvalues


def steam_manifest(appid, name, install_dir, flags="4"):
    return ('"AppState" { "appid" "' + appid + '" "name" "' + name +
            '" "installdir" "' + install_dir + '" "StateFlags" "' + flags + '" }')


class StoreInventoryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_keyvalues_parser_handles_nested_libraryfolders_and_comments(self):
        parsed = parse_keyvalues('''// comment
        "libraryfolders" { "0" { "path" "C:\\Steam" "apps" { "480" "1" } } }''')
        self.assertEqual(parsed["libraryfolders"]["0"]["path"], "C:\Steam")
        self.assertEqual(parsed["libraryfolders"]["0"]["apps"]["480"], "1")

    def test_steam_inventory_requires_matching_id_installed_flags_and_real_path(self):
        steam = self.root / "Steam"
        apps = steam / "steamapps"
        game = apps / "common" / "Spacewar"
        game.mkdir(parents=True)
        (apps / "appmanifest_480.acf").write_text(steam_manifest("480", "Spacewar", "Spacewar"), encoding="utf-8")
        records = collect_inventory(steam_root=steam, program_data=self.root / "NoProgramData")
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["productId"], "480")
        self.assertEqual(records[0]["title"], "Spacewar")

    def test_uninstalled_steam_manifest_is_not_inventory_evidence(self):
        steam = self.root / "Steam"
        apps = steam / "steamapps"
        (apps / "common" / "Spacewar").mkdir(parents=True)
        (apps / "appmanifest_480.acf").write_text(steam_manifest("480", "Spacewar", "Spacewar", "2"), encoding="utf-8")
        self.assertEqual(collect_inventory(steam_root=steam, program_data=self.root / "NoProgramData"), [])

    def test_candidate_manifest_requires_independent_store_match(self):
        candidate = self.root / "download"
        candidate.mkdir()
        acf = candidate / "appmanifest_480.acf"
        acf.write_text(steam_manifest("480", "Spacewar", "Spacewar"), encoding="utf-8")
        self.assertFalse(match_candidate(candidate, [acf], [])["matched"])
        records = [{"source": "steam", "productId": "480", "title": "Spacewar",
                    "installPath": str(self.root / "installed")}]
        matched = match_candidate(candidate, [acf], records)
        self.assertTrue(matched["matched"])
        self.assertEqual(matched["title"], "Spacewar")

    def test_candidate_store_id_with_conflicting_installed_titles_requires_review(self):
        candidate = self.root / "download"
        candidate.mkdir()
        appid = candidate / "steam_appid.txt"
        appid.write_text("480", encoding="ascii")
        records = [
            {"source": "steam", "productId": "480", "title": "Spacewar", "installPath": "a"},
            {"source": "steam", "productId": "480", "title": "Outer Wilds", "installPath": "b"},
        ]
        self.assertTrue(match_candidate(candidate, [appid], records)["conflict"])

    def test_epic_manifest_must_resolve_to_an_existing_install(self):
        program_data = self.root / "ProgramData"
        manifests = program_data / "Epic" / "EpicGamesLauncher" / "Data" / "Manifests"
        install = self.root / "EpicGames" / "Game"
        install.mkdir(parents=True)
        manifests.mkdir(parents=True)
        (manifests / "one.item").write_text(json.dumps({
            "AppName": "OuterWilds", "CatalogItemId": "catalog-1",
            "DisplayName": "Outer Wilds", "InstallLocation": str(install),
            "LaunchExecutable": "OuterWilds.exe"
        }), encoding="utf-8")
        (install / "OuterWilds.exe").write_bytes(b"MZ")
        records = collect_inventory(steam_root=self.root / "NoSteam", program_data=program_data)
        self.assertEqual([r["source"] for r in records], ["epic"])
        self.assertEqual(records[0]["productId"], "OuterWilds")


if __name__ == "__main__":
    unittest.main()
