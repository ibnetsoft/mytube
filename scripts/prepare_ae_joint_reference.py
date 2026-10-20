"""Prepare an isolated AE CC Bend It reference queue, independent of worker projects."""
from pathlib import Path
import json

out = Path(__file__).resolve().parents[1] / 'output/motion-joint-comparison'
(out / 'ae-media').mkdir(exist_ok=True)
poses = json.loads((out / 'poses.json').read_text(encoding='utf-8'))
for p in poses:
    p['start'] = [v*s for v,s in zip(p['rig']['bones'][p['bone']]['start'], (p['width'],p['height']))]
    p['end'] = [v*s for v,s in zip(p['rig']['bones'][p['bone']]['end'], (p['width'],p['height']))]
poses = [{k: p[k] for k in ('number','name','angle','start','end','width','height','left','top','background')} for p in poses]
payload = json.dumps({'out': out.as_posix(), 'poses': poses}, ensure_ascii=True)
script = r'''
var D=__DATA__;
app.beginSuppressDialogs();
function log(s){try{var f=new File(D.out+'/ae-bend-status.txt');if(f.open('a')){f.writeln(s);f.close();}}catch(ignore){} }
function footage(p){return app.project.importFile(new ImportOptions(new File(p)));}
try {
 if(!app.project)throw new Error('Open one AE session before running this script.');
 if(!app.project.file || app.project.file.name!=='puppet-ui-reference.aep')throw new Error('Expected the current saved comparison project; existing project preserved.');
 log('started|AE '+app.version);
 for(var k=0;k<D.poses.length;k++){
  var p=D.poses[k],stem='scene-'+p.number+'-'+p.name;
  var c=app.project.items.addComp(stem,1920,1080,1,2,24);
  for(var b=0;b<p.background.length;b++){var bg=p.background[b],l=c.layers.add(footage(D.out+'/scene-'+p.number+'-layer-'+bg.id+'.png'));l.property('ADBE Transform Group').property('ADBE Position').setValue([l.source.width/2+bg.left,l.source.height/2+bg.top]);}
  var l=c.layers.add(footage(D.out+'/scene-'+p.number+'-character.png'));
  l.property('ADBE Transform Group').property('ADBE Position').setValue([p.width/2+p.left,p.height/2+p.top]);
  var effect=l.property('ADBE Effect Parade').addProperty('CC Bend It');
  effect.property('CC Bend It-0002').setValue(p.start);
  effect.property('CC Bend It-0003').setValue(p.end);
  effect.property('CC Bend It-0001').setValueAtTime(0,0);
  effect.property('CC Bend It-0001').setValueAtTime(1,p.angle);
  for(var frame=0;frame<=1;frame++){
   var q=app.project.renderQueue.items.add(c);q.timeSpanStart=frame;q.timeSpanDuration=1/24;
   q.outputModule(1).file=new File(D.out+'/ae-media/'+stem+(frame===0?'-rest':'-peak')+'.avi');
  }
  log('queued|'+stem+'|CC Bend It|angle='+p.angle);
 }
 app.project.save(new File(D.out+'/bend-reference-current.aep'));log('queue-ready|bend-reference-current.aep');app.project.renderQueue.render();app.project.save();log('render-complete|bend-reference-current.aep');
}catch(e){log('error|'+e.toString()+' line '+e.line);alert('Reference render stopped: '+e.toString()+' line '+e.line);}
app.endSuppressDialogs(false);
'''.replace('__DATA__', payload)
(out / 'ae-reference.jsx').write_text(script, encoding='utf-8')
print(out / 'ae-reference.jsx')
