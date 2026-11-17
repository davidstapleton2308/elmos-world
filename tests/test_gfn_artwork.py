"""GeForce NOW artwork prioritizes exact matches and image proportions."""
import sys
import threading
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'app'))
import gfn_artwork


class GeForceArtTests(unittest.TestCase):
    def test_normalization_keeps_game_edition_disambiguation(self):
        self.assertEqual(gfn_artwork.normalized_title("Assassin’s Creed® II"),
                         gfn_artwork.normalized_title("Assassin's Creed 2"))
        self.assertNotEqual(gfn_artwork.normalized_title("Assassin's Creed Origins"),
                            gfn_artwork.normalized_title("Assassin's Creed Odyssey"))
        self.assertNotEqual(gfn_artwork.normalized_title("Portal 2"),
                            gfn_artwork.normalized_title("Portal"))

    def test_no_fuzzy_matching_to_wrong_sequels(self):
        with patch.object(gfn_artwork,'get_json',return_value={'items':[
            {'id':12,'name':'Assassins Creed Odyssey'},
            {'id':22,'name':'Assassin’s Creed Origins Deluxe Edition'}]}):
            self.assertEqual(gfn_artwork.steam_store_match("Assassin's Creed Origins"),{})

    def test_exact_public_store_match_provides_two_shapes(self):
        with patch.object(gfn_artwork,'get_json',return_value={'items':[
            {'id':101,'name':'Assassin’s Creed® II'},
            {'id':102,'name':'Assassin’s Creed® Brotherhood'}]}):
            result=gfn_artwork.steam_store_match("Assassin's Creed II")
        self.assertEqual(result['steamId'],101)
        self.assertIn('library_600x900.jpg',result['portrait'])
        self.assertIn('library_hero.jpg',result['hero'])

    def test_safe_art_rejects_untrusted_and_http_links(self):
        self.assertEqual(gfn_artwork.safe_image('http://cdn.steamgriddb.com/p.jpg'),'')
        self.assertEqual(gfn_artwork.safe_image('https://evil.example/p.png'),'')
        self.assertEqual(gfn_artwork.safe_image('https://steamgriddb.com.evil.example/p.png'),'')
        self.assertEqual(gfn_artwork.safe_image('https://cdn.steamgriddb.com/p.png'),
                         'https://cdn.steamgriddb.com/p.png')

    def test_provider_art_has_priority_in_each_shape(self):
        with patch.object(gfn_artwork,'steam_grid_match',return_value={
                'portrait':'https://cdn.steamgriddb.com/vertical.jpg',
                'hero':'https://cdn.steamgriddb.com/cinematic.jpg'}), \
             patch.object(gfn_artwork,'steam_store_match') as fallback:
            result=gfn_artwork.resolve_art("Assassin's Creed II",'mock-key')
        fallback.assert_not_called()
        self.assertIn('vertical.jpg',result['portrait'])
        self.assertIn('cinematic.jpg',result['hero'])

    def test_backend_preserves_cloud_library_and_only_changes_artwork(self):
        from backend import Engine
        e=Engine.__new__(Engine);e.lock=threading.RLock()
        e.local={'gfnGames':{'gfn-sync:123':{
            'name':'Assassin’s Creed® II','shortcut':'','store':'Steam',
            'variantId':'123','images':{'hero':'https://images.nvidia.com/promo.jpg'}}}}
        e.cfg={'api_key':''};e.save_local=MagicMock()
        art={'portrait':'https://cdn.steamgriddb.com/vertical.jpg',
             'hero':'https://cdn.steamgriddb.com/cinematic.jpg'}
        with patch.object(gfn_artwork,'resolve_art',return_value=art) as provider:
            first=e.gfn_polish_art('gfn-sync:123')
            second=e.gfn_polish_art('gfn-sync:123')
        provider.assert_called_once()
        self.assertEqual(first['artwork'],art)
        self.assertTrue(second['cached'])
        self.assertEqual(e.local['gfnGames']['gfn-sync:123']['images']['hero'],
                         'https://images.nvidia.com/promo.jpg')

    def test_css_and_frontend_render_right_scene_and_custom_landscape_poster(self):
        html=(ROOT/'app'/'index.html').read_text(encoding='utf-8')
        css=(ROOT/'app'/'premium_33.css').read_text(encoding='utf-8')
        js=(ROOT/'app'/'app.js').read_text(encoding='utf-8')
        spec=(ROOT/'build'/'ElmosWorld.spec').read_text(encoding='utf-8')
        server=(ROOT/'app'/'server.py').read_text(encoding='utf-8')
        self.assertIn('premium_33.css',html)
        self.assertIn('premium_33.css',spec)
        self.assertIn("u.path=='/premium_33.css'",server)
        self.assertIn('id="gfnHeroScene"',html)
        self.assertIn("('gfnHeroScene').style.backgroundImage",js)
        self.assertIn('function gfnCoverCandidates(g)',js)
        self.assertIn("img.naturalWidth>img.naturalHeight*1.16",js)
        self.assertIn('function gfnDecoratePoster(card,g)',js)
        self.assertIn('gfn-art-label',js)
        self.assertIn('is-landscape',css)
        self.assertIn('gfn-poster.is-landscape',css)
        self.assertIn('-webkit-mask-image',css)
        self.assertIn("api('/api/gfn-polish-art'",js)
        self.assertIn("'gfn_artwork'",spec)


if __name__=='__main__':
    unittest.main()
