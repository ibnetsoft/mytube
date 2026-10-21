"""ES3-compatible AE graphics: one bubble outline and one shared animation rig."""

DIRECTED_GRAPHICS_JSX = r'''
function directedBubbleOutline(w, h, tail) {
  var x=w/2, y=h/2, r=Math.min(28,h*.22), k=.5522847498*r;
  var v=[], ins=[], outs=[];
  function p(a,b,c,d,e,f) {v.push([a,b]);ins.push([c||0,d||0]);outs.push([e||0,f||0]);}
  p(-x+r,-y,-k,0,0,0); p(x-r,-y,0,0,k,0);
  p(x,-y+r,0,-k,0,0); p(x,y-r,0,0,0,k); p(x-r,y,k,0,0,0);
  if(tail!="none") {
    var sign=tail=="right"?1:-1, center=sign*w*.18;
    p(center+14,y); p(center+sign*24,y+Math.min(38,h*.24)); p(center-14,y);
  }
  p(-x+r,y,0,0,-k,0); p(-x,y-r,0,k,0,0); p(-x,-y+r,0,0,0,-k);
  var shape=new Shape();shape.vertices=v;shape.inTangents=ins;shape.outTangents=outs;shape.closed=true;
  return shape;
}
function makeDirectedSpeechBubbles(comp) {
  var cues=(PLAN.speech_bubbles||{}).bubbles||[];
  for(var i=0;i<cues.length;i++) {
    var c=cues[i], value=String(c.text||"");if(!value)continue;
    var a=Math.max(0,Number(c.start_seconds||0)), b=Math.min(DUR,Number(c.end_seconds||DUR));
    if(b-a<.3)throw new Error("Speech bubble cue is too short");
    var label=comp.layers.addText(value);label.name="directed_bubble_text_"+i;
    var prop=label.property("Source Text"), doc=prop.value;
    doc.fontSize=Math.round(H*.043);doc.fillColor=[.04,.04,.04];
    doc.applyFill=true;doc.applyStroke=false;doc.justification=ParagraphJustification.LEFT_JUSTIFY;prop.setValue(doc);
    var rect=label.sourceRectAtTime(a,false), maxWidth=W*.46;
    if(rect.width>maxWidth) {doc.fontSize=Math.max(30,doc.fontSize*maxWidth/rect.width);prop.setValue(doc);rect=label.sourceRectAtTime(a,false);}
    if(rect.width>maxWidth+1)throw new Error("Speech bubble needs line wrapping before rendering");
    label.property("Anchor Point").setValue([rect.left+rect.width/2,rect.top+rect.height/2]);
    var w=Math.max(W*.16,rect.width+64), h=Math.max(H*.10,rect.height+44);
    var pos=c.position||[.72,.22], cx=Number(pos[0])*W,cy=Number(pos[1])*H;
    if(cx-w/2<W*.04||cx+w/2>W*.96||cy-h/2<H*.04||cy+h/2+38>H*.82)throw new Error("Speech bubble exceeds title/subtitle safe area");
    var rig=comp.layers.addNull();rig.name="directed_bubble_rig_"+i;rig.inPoint=a;rig.outPoint=b;
    rig.property("Position").setValue([cx,cy]);rig.property("Anchor Point").setValue([0,0]);
    var bubble=comp.layers.addShape();bubble.name="directed_bubble_unified_"+i;
    var g=bubble.property("Contents").addProperty("ADBE Vector Group").property("Contents");
    var tail=String(c.tail||"none");if(c.style=="narration"||c.style=="thought"||c.style=="electronic")tail="none";
    g.addProperty("ADBE Vector Shape - Group").property("Path").setValue(directedBubbleOutline(w,h,tail));
    g.addProperty("ADBE Vector Graphic - Fill").property("Color").setValue([1,1,1]);
    var stroke=g.addProperty("ADBE Vector Graphic - Stroke");stroke.property("Color").setValue([.04,.04,.04]);stroke.property("Stroke Width").setValue(Math.max(2,H/360));
    bubble.parent=rig;label.parent=rig;
    bubble.property("Position").setValue([0,0]);label.property("Position").setValue([0,0]);
    bubble.inPoint=a;bubble.outPoint=b;label.inPoint=a;label.outPoint=b;
    var fade=Math.min(.12,(b-a)/4);
    // Parent opacity does not propagate in AE. Each child shares the same fade.
    setOpacity(bubble,a,0,a+fade,100,b-fade,100);bubble.property("Opacity").setValueAtTime(b,0);
    setOpacity(label,a,0,a+fade,100,b-fade,100);label.property("Opacity").setValueAtTime(b,0);
    rig.property("Scale").setValueAtTime(a,[96,96]);rig.property("Scale").setValueAtTime(a+fade,[100,100]);
    label.moveBefore(bubble);
  }
}
function makeDirectedSpeedLines(comp) {
  var design=(PLAN.directorial_plan||{}).execution_design;
  if(!design||!design.graphics.speedlines)return;
  var at=IMPACT_AT, end=Math.min(DUR,at+.20);
  for(var i=0;i<8;i++) {
    var angle=(i+.35)*Math.PI*2/8, dx=Math.cos(angle),dy=Math.sin(angle);
    var x=PRIMARY[0]+dx*W*.34, y=PRIMARY[1]+dy*W*.34;
    var s=new Shape();s.vertices=[[x-dy*1.5,y+dx*1.5],[x+dx*W*.22,y+dy*W*.22],[x+dy*1.5,y-dx*1.5]];
    s.inTangents=[[0,0],[0,0],[0,0]];s.outTangents=[[0,0],[0,0],[0,0]];s.closed=true;
    var layer=comp.layers.addShape();layer.name="directed_speedline_"+i;layer.inPoint=at;layer.outPoint=end;
    var contents=layer.property("Contents").addProperty("ADBE Vector Group").property("Contents");
    contents.addProperty("ADBE Vector Shape - Group").property("Path").setValue(s);
    contents.addProperty("ADBE Vector Graphic - Fill").property("Color").setValue([.12,.12,.12]);
    layer.property("Position").setValue([0,0]);setOpacity(layer,at,0,Math.min(end,at+.04),24,end,0);
  }
}
'''
