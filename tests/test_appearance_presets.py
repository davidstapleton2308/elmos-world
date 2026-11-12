from pathlib import Path
import unittest
ROOT=Path(__file__).resolve().parent.parent
APP=ROOT/'app'
class AppearancePresetTests(unittest.TestCase):
 def test_classic_is_original(self):
  c=APP/'presets'/'classic-3.1.1'
  for n in ('app.css','app.js','premium_23.css','premium_24.css','premium_25.css','premium_26.css','premium_27.css','premium_28.css','premium_30.css','premium_31.css'):
   self.assertEqual((c/n).read_bytes(),(APP/n).read_bytes(),n)
  self.assertEqual((c/'index.html').read_text(encoding='utf-8').count('3.1.1')>0,True)
 def test_unified_has_controller_features(self):
  u=APP/'presets'/'unified-3.2'
  for n in ('app.css','app.js','index.html','premium_31.css','README.md'): self.assertTrue((u/n).is_file(),n)
  js=(u/'app.js').read_text(encoding='utf-8')
  self.assertIn('controllerProfileDialog',js)
  self.assertIn('/api/controller-lab/config',js)
 def test_server_exposes_both_presets(self):
  s=(APP/'server.py').read_text(encoding='utf-8')
  self.assertIn('classic-3.1.1',s);self.assertIn('unified-3.2',s)
if __name__=='__main__':unittest.main()
