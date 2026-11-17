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

    def test_cache_preserves_short_name_for_direct_game_launch(self):
        games = gfn_cache_sync.extract_cached_games(fake_game())
        self.assertEqual(games['12345']['shortName'], 'Portal 2')

    def test_direct_launch_argument_contains_exact_game_variant_and_parent(self):
        from geforce_library import direct_route
        route = direct_route('102303511', 'my_game', '12345678-1234-1234-1234-123456789012')
        self.assertEqual(route, '--url-route=#?cmsId=102303511&launchSource=External'
                         '&shortName=my_game&parentGameId=12345678-1234-1234-1234-123456789012')

    def test_direct_launch_rejects_arbitrary_arguments(self):
        from geforce_library import direct_route
        for variant, short in [('1 --flag', 'safe'), ('123', '--url-route=evil'),
                               ('123', 'game\nmalicious')]:
            with self.subTest(variant=variant, short=short):
                with self.assertRaises(ValueError):
                    direct_route(variant, short)

    def test_sync_stores_direct_route_metadata_and_merges_by_variant(self):
        from backend import Engine
        engine = Engine.__new__(Engine)
        engine.lock = threading.RLock()
        engine.local = {'gfnGames': {}}
        engine.save_local = MagicMock()
        scanned = {'games':list(gfn_cache_sync.extract_cached_games(fake_game()).values()),
                   'scanned':1, 'message':'one game'}
        with patch.object(gfn_cache_sync,'scan_cache',return_value=scanned):
            first=engine.gfn_sync_cache()
            second=engine.gfn_sync_cache()
        self.assertEqual(first['added'],1)
        self.assertEqual(second['added'],0)
        self.assertEqual(second['total'],1)
        entry=next(iter(engine.local['gfnGames'].values()))
        self.assertEqual(entry['variantId'],'12345')
        self.assertEqual(entry['shortName'],'Portal 2')

    def test_native_direct_launch_is_used_for_synced_entries(self):
        from backend import Engine
        import geforce_library
        engine=Engine.__new__(Engine)
        engine.lock=threading.RLock()
        engine.local={'gfnGames':{'gfn-sync:12345':{'name':'Portal 2',
                      'shortcut':'', 'variantId':'12345', 'shortName':'Portal 2'}}}
        with patch.object(geforce_library,'launch_selected_game',
                          return_value={'ok':True,'directLaunch':True}) as launch:
            result=engine.gfn_launch('gfn-sync:12345')
        self.assertTrue(result['directLaunch'])
        launch.assert_called_once()

    def test_geforce_deck_uses_home_screen_dimensions_and_full_cover(self):
        css=(ROOT/'app'/'premium_32.css').read_text(encoding='utf-8')
        html=(ROOT/'app'/'index.html').read_text(encoding='utf-8')
        spec=(ROOT/'build'/'ElmosWorld.spec').read_text(encoding='utf-8')
        self.assertIn('premium_32.css', html)
        self.assertIn('premium_32.css', spec)
        server=(ROOT/'app'/'server.py').read_text(encoding='utf-8')
        self.assertIn("u.path=='/premium_32.css'", server)
        self.assertIn('var(--deck-width', css)
        self.assertIn('scroll-snap-align:center', css)
        self.assertIn('object-fit:cover!important', css)
        self.assertIn('background-size:cover,cover,cover!important',css)
        self.assertIn('background-image:var(--gfn-cover,none)', css)
        self.assertIn('#gfnView>.gfn-hero', css)
        self.assertIn('#gfnView>.gfn-bottom', css)

    def test_geforce_art_prioritizes_portrait_over_landscape_tile(self):
        js=(ROOT/'app'/'app.js').read_text(encoding='utf-8')
        begin=js.index('function gfnArtFor(g,slot){')
        end=js.index('function gfnSelectedItem()',begin)
        block=js[begin:end]
        self.assertIn("if(slot==='portrait')",block)
        self.assertLess(block.index("art(local,'portrait')"),block.index('cached.portrait||cached.hero'))
        self.assertIn('library_600x900.jpg',block)
        self.assertIn('library_hero.jpg',block)
        self.assertNotIn("cached.portrait)return cached.portrait; if(slot!=='portrait'",block)

    def test_geforce_wheel_and_controller_navigation_match_main_deck(self):
        script=(ROOT/'app'/'app.js').read_text(encoding='utf-8')
        self.assertIn("('gfnView').addEventListener('wheel'",script)
        self.assertIn("('gfnCards').addEventListener('scroll'",script)
        self.assertIn('function gfnSelectCentered()', script)
        self.assertIn('function gfnCenterCard(card)', script)
        self.assertIn("screen==='gfn'&&!modal&&['left','right'].includes(dir)",script)
        self.assertNotIn('card.onpointerenter=()=>gfnSelect',script)
        self.assertNotIn("card?.scrollIntoView({inline:'center'",script)

    def test_frontend_exposes_explicit_sync_without_api_signin(self):
        html=(ROOT/'app'/'index.html').read_text(encoding='utf-8')
        js=(ROOT/'app'/'app.js').read_text(encoding='utf-8')
        self.assertIn('id="gfnSync"',html)
        self.assertIn("api('/api/gfn-sync',{})",js)
        self.assertIn('cached.portrait',js)
        self.assertIn('g.directLaunch',js)


if __name__ == '__main__':
    unittest.main()
