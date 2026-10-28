"""Local, non-publishing comparison of archived scene 25's exact AE script in EffectCraft."""
import hashlib,json,shutil,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'worker')]
from effectcraft_render import binary,_execute
SRC=Path('C:/Users/kimse/AppData/Local/AIRStudio/AIRWorker/temp/ae_highlight/3376-025-effect-4f1f31dca3da0ae9')
OUT=ROOT/'output/effectcraft/psd-3376-scene25-20261021'
OUT.mkdir(parents=True,exist_ok=True)
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
original=(SRC/'create_project.jsx').read_text(encoding='utf-8-sig')
cfg=json.JSONDecoder().raw_decode(original.split('var CFG = ',1)[1])[0]
shutil.copy2(SRC/'input/scene.psd',OUT/'source.psd')
shutil.copy2(SRC/'render/ae_highlight.mp4',OUT/'ae-reference.mp4')
shutil.copy2(SRC/'create_project.jsx',OUT/'original-ae.jsx')
(OUT/'original-config.json').write_text(json.dumps(cfg,ensure_ascii=False,indent=2),encoding='utf-8')
cfg['source']=(OUT/'source.psd').as_posix()
prefix=original[original.index('var W = CFG.width'):original.index('app.beginSuppressDialogs();\ntry {')]
body=original.split('  var options = new ImportOptions(new File(CFG.source));',1)[1].split('  var rq = app.project.renderQueue.items.add(comp);',1)[0]
script='var CFG = '+json.dumps(cfg,ensure_ascii=True)+';\n'+prefix+'\nvar options = new ImportOptions(new File(CFG.source));'+body
# Fail visibly if the original optional-effect helper encounters an unsupported effect.
script=script.replace('catch (e) { return null; }','catch (e) { throw e; }')
script+='\nJSON.stringify({layers:comp.numLayers,comp:comp.name});\n'
(OUT/'comparison.jsx').write_text(script,encoding='utf-8')
(OUT/'provenance.json').write_text(json.dumps(dict(source=str(SRC),psd_sha256=sha(OUT/'source.psd'),ae_sha256=sha(OUT/'ae-reference.mp4'),original_jsx_sha256=sha(OUT/'original-ae.jsx'),note='Archived legacy parallax script; AE process/save/quit wrappers replaced by CLI, same PSD and animation settings; not a current queued job or approval.'),indent=2),encoding='utf-8')
cli=binary();project=OUT/'scene.ecproj'
_execute(cli,['script','--eval','null','--empty','--save-as',str(project),'--json'],OUT,'initialize')
_execute(cli,['script',str(OUT/'comparison.jsx'),'--project',str(project),'--save','--json'],OUT,'create')
print('Project created',flush=True)
_execute(cli,['render',str(project),'--comp',cfg['comp'],'--out',str(OUT/'effectcraft.mp4'),'--format','h264','--audio','off','--fps',str(cfg['fps']),'--json'],OUT,'render')
print('Rendered '+str(OUT/'effectcraft.mp4'),flush=True)
