"""Eight native AE vector presets, in final output coordinates after camera/mouth work."""
BUBBLE_JSX = r'''
function renderPresetBubbles(comp) {
 var cues=(P.speech_bubbles||{}).bubbles||[], W=O.width,H=O.height;
 function shape(v,ins,outs){var s=new Shape();s.vertices=v;s.inTangents=ins||[];s.outTangents=outs||[];if(!ins)for(var j=0;j<v.length;j++){s.inTangents.push([0,0]);s.outTangents.push([0,0]);}s.closed=true;return s;}
 function pathGroup(layer,paths,dashed){var g=layer.property('Contents').addProperty('ADBE Vector Group').property('Contents');for(var pathIndex=0;pathIndex<paths.length;pathIndex++)g.addProperty('ADBE Vector Shape - Group').property('Path').setValue(paths[pathIndex]);if(paths.length>1)g.addProperty('ADBE Vector Filter - Merge').property('ADBE Vector Merge Type').setValue(2);g.addProperty('ADBE Vector Graphic - Fill').property('Color').setValue([1,1,1]);var stroke=g.addProperty('ADBE Vector Graphic - Stroke');stroke.property('Color').setValue([.04,.04,.04]);stroke.property('Stroke Width').setValue(Math.max(2,H/360));if(dashed){var d=stroke.property('ADBE Vector Stroke Dashes');d.addProperty('ADBE Vector Stroke Dash 1').setValue(H*.008);d.addProperty('ADBE Vector Stroke Gap 1').setValue(H*.005);}return g;}
 for(var i=0;i<cues.length;i++){
  var c=cues[i],b=c.box,x=b[0]*W,y=b[1]*H,w=(b[2]-b[0])*W,h=(b[3]-b[1])*H,cx=x+w/2,cy=y+h/2;
  var layer=comp.layers.addShape();layer.name='bubble_preset_'+c.style+'_'+i;layer.property('Position').setValue([0,0]);
  var v=[],ins=[],outs=[],n,j,a,r,px,py,k=.55228475;
  if(c.style=='dialogue'||c.style=='whisper'){
   v=[[cx,y],[x+w,cy],[cx,y+h],[x,cy]];ins=[[-w*k/2,0],[0,-h*k/2],[w*k/2,0],[0,h*k/2]];outs=[[w*k/2,0],[0,h*k/2],[-w*k/2,0],[0,-h*k/2]];
  }else if(c.style=='shout'||c.style=='reaction'||c.style=='thought'){
   n=c.style=='thought'?48:(c.style=='reaction'?20:32);
   for(j=0;j<n;j++){a=-Math.PI/2+j*2*Math.PI/n;r=c.style=='thought'?.95+.05*Math.cos(j*2*Math.PI/4):(j%2? .87:1);v.push([cx+Math.cos(a)*w*r/2,cy+Math.sin(a)*h*r/2]);}
  }else if(c.style=='rounded'){
   r=Math.min(h*.2,w*.1);v=[[x+r,y],[x+w-r,y],[x+w,y+r],[x+w,y+h-r],[x+w-r,y+h],[x+r,y+h],[x,y+h-r],[x,y+r]];
   ins=[[-r*k,0],[0,0],[0,-r*k],[0,0],[r*k,0],[0,0],[0,r*k],[0,0]];outs=[[0,0],[r*k,0],[0,0],[0,r*k],[0,0],[-r*k,0],[0,0],[0,-r*k]];
  }else if(c.style=='electronic'){
   r=Math.min(w,h)*.16;v=[[x+r,y],[x+w-r,y],[x+w,y+r],[x+w,y+h-r],[x+w-r,y+h],[x+r,y+h],[x,y+h-r],[x,y+r]];
  }else if(c.style=='narration'){v=[[x,y],[x+w,y],[x+w,y+h],[x,y+h]];}else throw new Error('Unknown bubble preset');
  if(c.style=='thought'){for(j=0;j<v.length;j++){var prev=v[(j+v.length-1)%v.length],next=v[(j+1)%v.length];ins.push([-(next[0]-prev[0])/6,-(next[1]-prev[1])/6]);outs.push([(next[0]-prev[0])/6,(next[1]-prev[1])/6]);}}
  var paths=[shape(v,ins.length?ins:null,outs.length?outs:null)];
  if(c.style!='thought'&&c.style!='narration'){
   var target=c.speaker_anchor,tx=target[0]*W,ty=target[1]*H,dx=tx-cx,dy=ty-cy,len=Math.sqrt(dx*dx+dy*dy),half=Math.min(42,h*.22),ux=-dy/len*half,uy=dx/len*half;
   // Add body and tail before one union, fill and stroke: no internal seam.
   paths.push(shape([[cx+ux,cy+uy],[tx,ty],[cx-ux,cy-uy]]));
  }
  pathGroup(layer,paths,c.style=='whisper');
  var padding=Math.max(16,H*.022,Math.min(w,h)*.16),label=comp.layers.addText('');label.name='bubble_text_'+i;
  var prop=label.property('Source Text'),doc=prop.value,fontSize=Math.max(26,Math.min(H*.039,h*.3)),rect,wrapped;
  if(/[\uac00-\ud7af]/.test(String(c.text)))doc.font='MalgunGothic';else if(/[\u3040-\u30ff\u3400-\u9fff]/.test(String(c.text)))doc.font='YuGothic-Regular';
  doc.applyFill=true;doc.fillColor=[.04,.04,.04];doc.applyStroke=false;doc.justification=ParagraphJustification.CENTER_JUSTIFY;doc.autoLeading=true;
  function measure(text){doc.text=text;prop.setValue(doc);return label.sourceRectAtTime(c.start_seconds,false);}
  var fits=false;
  for(var fit=0;fit<12;fit++){
   doc.fontSize=fontSize;var lines=[],line='',text=String(c.text);
   for(var ch=0;ch<text.length;ch++){
    var letter=text.charAt(ch);
    if(letter=='\n'){lines.push(line);line='';continue;}
    if(line&&measure(line+letter).width>w-padding*2){lines.push(line);line=letter;}else line+=letter;
   }
   lines.push(line);wrapped=lines.join('\r');rect=measure(wrapped);
   if(rect.width<=w-padding*2&&rect.height<=h-padding*2){fits=true;break;}
   if(fontSize<=26)break;fontSize=Math.max(26,fontSize*.9);
  }
  if(!fits)throw new Error('Bubble text does not fit reviewed box');
  label.property('Anchor Point').setValue([rect.left+rect.width/2,rect.top+rect.height/2]);
  label.property('Position').setValue([cx,cy]);
  var tracking=c.tracking||[];
  for(var ti=0;ti<tracking.length;ti++){
   var sample=tracking[ti],offset=sample.offset;
   layer.property('Position').setValueAtTime(sample.at_seconds,[offset[0]*W,offset[1]*H]);
   label.property('Position').setValueAtTime(sample.at_seconds,[cx+offset[0]*W,cy+offset[1]*H]);
   var lp=layer.property('Position'),tp=label.property('Position');
   lp.setInterpolationTypeAtKey(lp.numKeys,KeyframeInterpolationType.LINEAR,KeyframeInterpolationType.LINEAR);
   tp.setInterpolationTypeAtKey(tp.numKeys,KeyframeInterpolationType.LINEAR,KeyframeInterpolationType.LINEAR);
  }
  layer.inPoint=c.start_seconds;layer.outPoint=c.end_seconds;label.inPoint=c.start_seconds;label.outPoint=c.end_seconds;
  // No pop scale: a fixed speaker endpoint must stay connected throughout.
  for(j=0;j<2;j++){var L=j?label:layer,op=L.property('Opacity'),fade=Math.min(.08,(c.end_seconds-c.start_seconds)/4);op.setValueAtTime(c.start_seconds,0);op.setValueAtTime(c.start_seconds+fade,100);op.setValueAtTime(c.end_seconds-fade,100);op.setValueAtTime(c.end_seconds,0);}
 }
}
renderPresetBubbles(comp);
'''
