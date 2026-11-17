"""Tests: cached GeForce NOW selected games sync without credentials or duplicates."""
import json
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'app'))

import gfn_cache_sync


def fake_game(name='Portal 2', selected='true', ident='12345', store='STEAM'):
    return (
        '{"__typename":"GameItem","id":"12345678-1234-1234-1234-123456789012",'
        '"title":"'+name+'","HERO_IMAGE":"https://images.nvidia.com/hero.jpg",'
        '"BOX_ART":"https://images.nvidia.com/box.jpg",'
        '"variants":[{"id":"'+ident+'","shortName":"'+name+'",'
        '"appStore":"'+store+'","selected":'+selected+'}]}'
    )


class GfnCachedLibraryTests(unittest.TestCase):
    def test_only_selected_games_are_imported(self):
        content = (fake_game() + fake_game('Not my game','false','23456'))
        games = gfn_cache_sync.extract_cached_games(content)
        self.assertEqual(set(games), {'12345'})
        self.assertEqual(games['12345']['store'], 'Steam')
        self.assertEqual(games['12345']['name'], 'Portal 2')

    def test_nvidia_images_are_used_but_non_nvidia_hosts_rejected(self):
        games = gfn_cache_sync.extract_cached_games(fake_game())
        self.assertTrue(games['12345']['images']['hero'].startswith('https://images.nvidia.com/'))
        self.assertEqual(gfn_cache_sync._safe_art('https://example.com/token?code=123'), '')
        self.assertEqual(gfn_cache_sync._safe_art('http://images.nvidia.com/cover.jpg'), '')

    def test_scan_is_read_only_and_does_not_scan_unrelated_directories(self):
        with tempfile.TemporaryDirectory() as tmp:
            cache = Path(tmp)/'CacheStorage';cache.mkdir()
            (cache/'a.bin').write_bytes(fake_game().encode('utf-8'))
            (cache/'b.bin').write_bytes(fake_game('Fortnite','true','56789','EPIC').encode('utf-8'))
            outcome = gfn_cache_sync.scan_cache(root=cache)
            self.assertEqual(len(outcome['games']),2)
            self.assertEqual([x['store'] for x in outcome['games']],['Epic Games','Steam'])
            self.assertEqual(outcome['scanned'],2)

    def test_empty_cache_does_not_claim_all_games_are_installed(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = gfn_cache_sync.scan_cache(root=Path(tmp))
        self.assertEqual(result['games'],[])
        self.assertIn('No selected games', result['message'])

    def test_sync_deduplicates_and_preserves_manual_shortcut(self):
        from backend import Engine
        engine = Engine.__new__(Engine)
        engine.lock = threading.RLock()
        engine.local = {'gfnGames': {
            'gfn:manual': {'name':'Portal 2','shortcut':'X:/NVIDIA/Portal 2.lnk','steamId':620}
        }}
        engine.save_local = MagicMock()
        scanned = {'games':list(gfn_cache_sync.extract_cached_games(fake_game()).values()),
                   'scanned':1,'message':'1 entry'}
        with patch.object(gfn_cache_sync, 'scan_cache', return_value=scanned):
            first = engine.gfn_sync_cache()
            second = engine.gfn_sync_cache()
        self.assertEqual(first['added'],0)
        self.assertEqual(second['added'],0)
        self.assertEqual(first['total'],1)
        self.assertEqual(second['total'],1)
        self.assertEqual(engine.local['gfnGames']['gfn:manual']['steamId'],620)

    def test_sync_preserves_previous_entries_when_cache_has_no_games(self):
        from backend import Engine
        engine = Engine.__new__(Engine)
        engine.lock = threading.RLock()
        engine.local = {'gfnGames': {'gfn-sync:123':{'name':'Portal 2','shortcut':'',
                                  'variantId':'123','store':'Steam','images':{}}}}
        engine.save_local=MagicMock()
        with patch.object(gfn_cache_sync,'scan_cache',return_value={'games':[],'scanned':0,'message':'No games cached'}):
            response=engine.gfn_sync_cache()
        self.assertEqual(response['total'],1)
        engine.save_local.assert_not_called()

    def test_frontend_exposes_explicit_sync_without_api_signin(self):
        html=(ROOT/'app'/'index.html').read_text(encoding='utf-8')
        js=(ROOT/'app'/'app.js').read_text(encoding='utf-8')
        self.assertIn('id="gfnSync"',html)
        self.assertIn("api('/api/gfn-sync',{})",js)
        self.assertIn('cached.portrait',js)
        self.assertIn('g.directLaunch',js)


if __name__ == '__main__':
    unittest.main()
