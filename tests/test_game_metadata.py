"""Identity resolution for obscure download names using bounded game manifests."""
import json
import os
from pathlib import Path
import sys
import tempfile
import time
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parent.parent/'app'))
from smart_discovery import inspect_folder
from game_metadata import inspect_manifest_names


class ManifestIdentityFixtures(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.root=Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def game(self,name,binary,manifest_name,manifest_value):
        root=self.root/name
        root.mkdir()
        (root/binary).write_bytes(b'MZ'+bytes(100_000))
        (root/'UnityPlayer.dll').write_bytes(bytes(200))
        (root/(Path(binary).stem+'_Data')).mkdir()
        p=root/manifest_name
        p.parent.mkdir(exist_ok=True)
        if isinstance(manifest_value,dict):
            p.write_text(json.dumps(manifest_value),encoding='utf-8')
        else:
            p.write_text(manifest_value,encoding='utf-8')
        old=time.time()-300
        for path in [root,*root.rglob('*')]:
            os.utime(path,(old,old))
        return root

    def test_obscure_folder_with_gog_manifest_has_canonical_title(self):
        root=self.game('x2a5199f','OuterWilds.exe','goggame-123456.info',{'name':'Outer Wilds'})
        result=inspect_folder(root)
        self.assertEqual(result['title'],'Outer Wilds')
        self.assertEqual(result['kind'],'game')
        self.assertEqual(result['action'],'ready')
        self.assertIn('GOG',result['reason'])

    def test_steam_acf_title_with_matching_id_is_recovered(self):
        txt='"AppState"\\n{\\n "appid" "480"\\n "name" "Outer Wilds"\\n "installdir" "Game01"\\n}'
        root=self.game('n0name','OuterWilds.exe','appmanifest_480.acf',txt)
        result=inspect_folder(root)
        self.assertEqual(result['title'],'Outer Wilds')
        self.assertEqual(result['action'],'ready')

    def test_conflicting_manifest_names_cause_review(self):
        root=self.game('UnknownBuild','OuterWilds.exe','goggame-345.info',{'name':'Outer Wilds'})
        (root/'appmanifest_480.acf').write_text('"AppState"\\n{ "name" "Portal" }',encoding='utf-8')
        result=inspect_folder(root,min_age=0)
        self.assertEqual(result['kind'],'game')
        self.assertEqual(result['action'],'review')
        self.assertIn('Conflicting',result['reason'])

    def test_oversized_metadata_is_ignored(self):
        root=self.game('RandomCode','OuterWilds.exe','goggame-345.info',{'name':'Outer Wilds'})
        (root/'goggame-345.info').write_text('X'*130_000,encoding='utf-8')
        names=inspect_manifest_names(root,list(root.iterdir()))
        self.assertFalse(names['title'])

    def test_an_acf_id_mismatch_cannot_identify_an_unknown_game(self):
        root=self.game('Unknown','OuterWilds.exe','appmanifest_480.acf',
                       '"AppState"\\n{\\n "appid" "999"\\n "name" "Outer Wilds"\\n}')
        names=inspect_manifest_names(root,list(root.iterdir()))
        self.assertFalse(names['title'])

    def test_unrelated_nested_metadata_does_not_rename_game(self):
        root=self.game('OuterWilds','OuterWilds.exe','goggame-480.info',
                       {'name':'Outer Wilds'})
        (root/'tools').mkdir()
        (root/'tools'/'goggame-1.info').write_text('{"name":"Unrelated"}')
        result=inspect_folder(root,min_age=0)
        self.assertEqual(result['title'],'Outer Wilds')

    def test_epic_manifest_name_is_detected(self):
        root=self.game('g9ac11','OuterWilds.exe','.egstore/manifest.item',
                       {'AppName':'OuterWilds','DisplayName':'Outer Wilds','CatalogItemId':'100'})
        result=inspect_folder(root)
        self.assertEqual(result['title'],'Outer Wilds')
        self.assertEqual(result['action'],'ready')


if __name__=='__main__':
    unittest.main()
