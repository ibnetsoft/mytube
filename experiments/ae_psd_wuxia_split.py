"""Build an editable layered PSD from generated wuxia webtoon assets."""
from __future__ import annotations

import shutil
import json
from pathlib import Path

from PIL import Image
from psd_tools import PSDImage


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'output' / 'ae-psd-wuxia-3285'
GENERATED = Path.home() / '.codex' / 'generated_images' / '01a0d958-582f-7af2-b97c-4e1492f70446'
ASSETS = {
    'left-character.png': GENERATED / 'exec-a1f76741-7acf-480d-9bc1-455220b51202.png',
    'right-character.png': GENERATED / 'exec-d20f5902-61eb-4fba-9733-b5f45e730ad3.png',
    'background.png': GENERATED / 'exec-3f65c56b-ee3b-48ff-9092-ef93eec635e3.png',
}
W, H = 1920, 1080


def placed_character(source: Image.Image, height: int, left: int, top: int,
                     panel: tuple[int, int]) -> Image.Image:
    source = source.convert('RGBA')
    width = round(source.width * height / source.height)
    scaled = source.resize((width, height), Image.Resampling.LANCZOS)
    layer = Image.new('RGBA', (W, H), (0, 0, 0, 0))
    layer.alpha_composite(scaled, (left, top))
    # Each figure belongs to one editable panel, so overlapping portions stay transparent.
    if panel[0] > 0:
        layer.paste((0, 0, 0, 0), (0, 0, panel[0], H))
    if panel[1] < W:
        layer.paste((0, 0, 0, 0), (panel[1], 0, W, H))
    return layer


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    for name, source in ASSETS.items():
        if not source.is_file():
            raise FileNotFoundError(source)
        shutil.copy2(source, OUT / name)

    background = Image.open(OUT / 'background.png').convert('RGB').resize((W, H), Image.Resampling.LANCZOS)
    left = placed_character(Image.open(OUT / 'left-character.png'), 1250, -155, -65, (0, 960))
    right = placed_character(Image.open(OUT / 'right-character.png'), 1260, 790, -60, (960, W))

    # Keep the full-canvas layers in PNG as well as PSD for direct inspection.
    background.save(OUT / 'layer-01-background.png')
    left.save(OUT / 'layer-02-swordsman.png')
    right.save(OUT / 'layer-03-investigator.png')

    psd = PSDImage.new('RGBA', (W, H), color=0)
    psd.create_pixel_layer(background, name='01 Background - split locations')
    psd.create_pixel_layer(left, name='02 Swordsman - left panel')
    psd.create_pixel_layer(right, name='03 Investigator - right panel')
    output = OUT / 'wuxia-split-layered.psd'
    psd.save(output)
    psd.composite().save(OUT / 'preview.png')
    reopened = PSDImage.open(output)
    if len(reopened) != 3 or reopened.size != (W, H):
        raise RuntimeError('PSD layer validation failed')
    write_after_effects_script(output)
    print(f'{output} ({len(reopened)} layers, {W}x{H})')


def write_after_effects_script(psd_path: Path) -> None:
    paths = {
        'psd': psd_path,
        'project': OUT / 'wuxia-split-animation.aep',
        'movie': OUT / 'wuxia-split-animation.mp4',
        'status': OUT / 'ae-status.txt',
    }
    values = {key: json.dumps(str(path.resolve()).replace('\\', '/'), ensure_ascii=True)
              for key, path in paths.items()}
    jsx = '''// Layered PSD animation test: independent characters and background.
var PSD = %(psd)s, PROJECT = %(project)s, MOVIE = %(movie)s, STATUS = %(status)s;
function report(value) { var f = new File(STATUS); if (f.open("w")) { f.write(value); f.close(); } }
function keyOpacity(layer, times, values) {
  var p = layer.property("Opacity");
  for (var i=0; i<times.length; i++) p.setValueAtTime(times[i], values[i]);
}
app.beginSuppressDialogs();
try {
  if (app.project) app.project.close(CloseOptions.DO_NOT_SAVE_CHANGES);
  app.newProject();
  var opt = new ImportOptions(new File(PSD));
  opt.importAs = ImportAsType.COMP;
  var imported = app.project.importFile(opt);
  if (!(imported instanceof CompItem)) throw "PSD was not imported as composition";
  if (imported.numLayers < 3) throw "PSD layers missing: " + imported.numLayers;
  var comp = app.project.items.addComp("Wuxia_PSD_Split", 1920, 1080, 1, 4, 24);
  comp.bgColor = [0.04,0.03,0.07];
  var names = [];
  for (var i=imported.numLayers; i>=1; i--) {
    var sourceLayer = imported.layer(i);
    var layer = comp.layers.add(sourceLayer.source);
    layer.name = sourceLayer.name;
    layer.property("Position").setValue([960,540]);
    names.push(layer.name);
    if (layer.name.indexOf("Background") >= 0) {
      layer.property("Scale").setValueAtTime(0,[100,100]);
      layer.property("Scale").setValueAtTime(4,[103,103]);
    } else if (layer.name.indexOf("Swordsman") >= 0) {
      layer.property("Position").setValueAtTime(0,[940,552]);
      layer.property("Position").setValueAtTime(2,[962,538]);
      layer.property("Position").setValueAtTime(4,[970,532]);
      layer.property("Scale").setValueAtTime(0,[101,101]);
      layer.property("Scale").setValueAtTime(4,[106,106]);
    } else if (layer.name.indexOf("Investigator") >= 0) {
      layer.property("Position").setValueAtTime(0,[982,540]);
      layer.property("Position").setValueAtTime(4,[947,543]);
      layer.property("Scale").setValueAtTime(0,[105,105]);
      layer.property("Scale").setValueAtTime(4,[109,109]);
    }
  }
  // Place energy behind the character faces and above the background.
  var energy = comp.layers.addShape();
  energy.name = "04 Violet meridian pulse";
  var group = energy.property("Contents").addProperty("ADBE Vector Group");
  var contents = group.property("Contents");
  var ellipse = contents.addProperty("ADBE Vector Shape - Ellipse");
  ellipse.property("Size").setValue([340,220]);
  var fill = contents.addProperty("ADBE Vector Graphic - Fill");
  fill.property("Color").setValue([0.55,0.25,0.82]);
  energy.property("Position").setValue([420,690]);
  energy.blendingMode = BlendingMode.ADD;
  keyOpacity(energy,[0,0.6,1.3,2.0,2.8,4],[0,15,6,20,8,0]);
  try { energy.property("Effects").addProperty("ADBE Glo2"); } catch(err) {}
  try { energy.property("Effects").addProperty("ADBE Gaussian Blur 2"); } catch(err) {}
  var divider = comp.layers.addSolid([0.06,0.04,0.06],"05 Split divider",10,1080,1,4);
  divider.property("Position").setValue([960,540]);
  var rq = app.project.renderQueue.items.add(comp);
  rq.outputModule(1).file = new File(MOVIE);
  app.project.save(new File(PROJECT));
  report("ready|" + imported.numLayers + "|" + names.join(","));
} catch (error) { report("error|" + error.toString()); }
finally { app.endSuppressDialogs(false); }
''' % values
    (OUT / 'create-layered-ae.jsx').write_text(jsx, encoding='utf-8')


if __name__ == '__main__':
    main()
