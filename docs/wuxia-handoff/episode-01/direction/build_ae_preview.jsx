/* Editable still-art AE preview. No videos, auto publication or rendering.
   Uses source images + separate text/shape layers. Timing is explicitly UNBOUND
   until the production worker binds exact quote anchors to final narration. */
(function () {
    var DIR = File($.fileName).parent;
    var ROOT = DIR.parent;
    function readJSON(file) {
        if (!file.exists) throw new Error('Missing file: ' + file.fsName);
        file.encoding = 'UTF-8'; file.open('r'); var text = file.read(); file.close();
        return typeof JSON !== 'undefined' && JSON.parse ? JSON.parse(text) : eval('(' + text + ')');
    }
    var CFG = readJSON(new File(DIR.fsName + '/ae-scene-package.json'));
    var W = CFG.width, H = CFG.height, FPS = CFG.fps;
    var warnings = [], cache = {};
    if (!app.project) app.newProject();
    app.beginUndoGroup('Wuxia E01 editable still-art preview');
    var stamp = String(new Date().getTime());
    var folder = app.project.items.addFolder('WUXIA_E01_' + stamp);
    var sources = app.project.items.addFolder('Originals_' + stamp); sources.parentFolder = folder;
    function xy(p) { return [p[0] * W, p[1] * H]; }
    function footage(path) {
        if (cache[path]) return cache[path];
        var file = new File(ROOT.fsName + '/' + path);
        if (!file.exists) throw new Error('Actual original missing: ' + file.fsName);
        var opt = new ImportOptions(file), item = app.project.importFile(opt);
        item.parentFolder = sources; cache[path] = item; return item;
    }
    function fade(layer, start, end, peak) {
        var o = layer.property('Opacity');
        o.setValueAtTime(start, 0); o.setValueAtTime(start + Math.min(.09, (end-start)/4), peak);
        o.setValueAtTime(Math.max(start+.1, end-.10), peak); o.setValueAtTime(end, 0);
    }
    function polygon(comp, name, points, fill, stroke, sw) {
        var l = comp.layers.addShape(); l.name = name; l.property('Position').setValue([0,0]);
        var group = l.property('Contents').addProperty('ADBE Vector Group');
        var inner = group.property('Contents');
        var path = inner.addProperty('ADBE Vector Shape - Group'), shape = new Shape();
        shape.vertices = points; shape.closed = true;
        var ins=[], outs=[]; for(var i=0;i<points.length;i++){ins.push([0,0]);outs.push([0,0]);}
        shape.inTangents=ins;shape.outTangents=outs;path.property('Path').setValue(shape);
        if(fill){var f=inner.addProperty('ADBE Vector Graphic - Fill');f.property('Color').setValue(fill);}
        if(stroke){var s=inner.addProperty('ADBE Vector Graphic - Stroke');s.property('Color').setValue(stroke);s.property('Stroke Width').setValue(sw);}
        return l;
    }
    function ellipse(comp,name,center,size,fill,stroke,sw) {
        var l=comp.layers.addShape();l.name=name;l.property('Position').setValue(center);
        var group=l.property('Contents').addProperty('ADBE Vector Group'),inner=group.property('Contents');
        var e=inner.addProperty('ADBE Vector Shape - Ellipse');e.property('Size').setValue(size);
        if(fill){var f=inner.addProperty('ADBE Vector Graphic - Fill');f.property('Color').setValue(fill);}
        if(stroke){var s=inner.addProperty('ADBE Vector Graphic - Stroke');s.property('Color').setValue(stroke);s.property('Stroke Width').setValue(sw);}
        return l;
    }
    function wrap(text, maxChars) {
        var out=[],paragraphs=text.split('\n');
        for(var p=0;p<paragraphs.length;p++){
            var words=paragraphs[p].split(' '),line='';
            for(var i=0;i<words.length;i++){
                var word=words[i];
                if(line.length && line.length+1+word.length>maxChars){out.push(line);line='';}
                while(word.length>maxChars){if(line){out.push(line);line='';}out.push(word.substr(0,maxChars));word=word.substr(maxChars);}
                line+=(line.length?' ':'')+word;
            }if(line)out.push(line);
        }return out.join('\r');
    }
    function font(doc, requested) {
        try { doc.font=requested; if(doc.font!==requested) warnings.push('Font substituted: '+requested+' -> '+doc.font); }
        catch(e){doc.font='MalgunGothicBold';warnings.push('Font unavailable: '+requested+'; explicit MalgunGothicBold fallback');}
    }
    function textLayer(comp,name,text,style,center,start,end,width) {
        var l=comp.layers.addText(wrap(text,Math.max(7,Math.floor(width/style.size))));l.name=name;
        var prop=l.property('Source Text'),doc=prop.value;
        font(doc,style.font);doc.fontSize=style.size;doc.fillColor=style.fill;
        doc.applyFill=true;doc.justification=ParagraphJustification.CENTER_JUSTIFY;
        doc.leading=style.size*1.16;doc.autoLeading=false;
        if(style.stroke){doc.applyStroke=true;doc.strokeColor=style.stroke;doc.strokeWidth=style.stroke_width||3;doc.strokeOverFill=false;}
        prop.setValue(doc);
        var rect=l.sourceRectAtTime(0,false);
        l.property('Anchor Point').setValue([rect.left+rect.width/2,rect.top+rect.height/2]);
        l.property('Position').setValue(center);l.property('Rotation').setValue(style.rotation||0);
        l.inPoint=start;l.outPoint=end;
        var t=Math.min(.14,(end-start)/3),peak=style.scale_peak||102;
        l.property('Scale').setValueAtTime(start,[peak,peak]);
        l.property('Scale').setValueAtTime(start+t,[100,100]);
        fade(l,start,end,100);return l;
    }
    function bubble(comp,g,start,end,index) {
        var lay=g.layout,c=xy(lay.center),size=[lay.size[0]*W,lay.size[1]*H],tip=xy(lay.tail||[lay.center[0],lay.center[1]+.2]);
        var base=[c[0]+(tip[0]<c[0]?-1:1)*size[0]*.18,c[1]+size[1]*.29];
        var tail=polygon(comp,'bubble_tail_'+index,[[base[0]-18,base[1]],[base[0]+18,base[1]],tip],[1,.995,.97],[.08,.1,.13],3);
        tail.inPoint=start;tail.outPoint=end;fade(tail,start,end,100);
        var body=ellipse(comp,'bubble_body_'+index,c,size,[1,.995,.97],[.08,.1,.13],3);
        body.inPoint=start;body.outPoint=end;fade(body,start,end,100);
        textLayer(comp,'dialogue_'+g.speaker+'_'+index,g.text,g.style,c,start,end,size[0]*.80);
    }
    function impact(comp,e,at,dur,stateLayer,index) {
        var p=xy(e.center),r=e.radius*W,l,ty=e.type;
        if(ty==='impact_shake'){
            var position=stateLayer.property('Position'),base=position.value;
            var amp=4+e.intensity*18;
            var pattern=[[0,0],[1,-.45],[-.65,.7],[.35,-.3],[0,0]];
            for(var k=0;k<pattern.length;k++)position.setValueAtTime(at+dur*k/(pattern.length-1),[base[0]+pattern[k][0]*amp,base[1]+pattern[k][1]*amp]);
            return;
        }
        if(ty==='debris_burst'){
            for(var j=0;j<9;j++){
                var ang=j*2.399963,s=5+(j%3)*3;
                l=polygon(comp,'debris_'+index+'_'+j,[[-s,-s],[s,-s*.6],[s*.6,s],[-s*.7,s*.8]],[.53,.48,.39],null,0);
                l.inPoint=at;l.outPoint=at+dur;l.property('Position').setValueAtTime(at,p);
                l.property('Position').setValueAtTime(at+dur,[p[0]+Math.cos(ang)*r,p[1]+Math.sin(ang)*r*.6+24]);
                fade(l,at,at+dur,55);l.property('Rotation').setValueAtTime(at,0);l.property('Rotation').setValueAtTime(at+dur,(j%2?1:-1)*55);
            }return;
        }
        if(ty==='speedline_burst'){
            for(var z=0;z<10;z++){
                var a=z*Math.PI*2/10,inside=r*.6,outside=r*1.8,dx=Math.cos(a),dy=Math.sin(a);
                l=polygon(comp,'speedline_'+index+'_'+z,[[p[0]+dx*inside,p[1]+dy*inside],[p[0]+dx*outside-dy*2,p[1]+dy*outside+dx*2],[p[0]+dx*outside+dy*2,p[1]+dy*outside-dx*2]],[.8,.94,.96],null,0);
                l.inPoint=at;l.outPoint=at+dur;fade(l,at,at+dur,40);
            }return;
        }
        l=ellipse(comp,'fx_'+ty+'_'+index,p,[r*2,r*1.4],ty==='impact_flash'?[1,.97,.88]:[.45,.85,.95],null,0);
        l.inPoint=at;l.outPoint=at+dur;l.blendingMode=BlendingMode.SCREEN;
        fade(l,at,at+dur,ty==='impact_flash'?e.intensity*100:e.intensity*40);
    }
    var mainDuration=0;for(var q=0;q<CFG.scenes.length;q++)mainDuration+=CFG.scenes[q].preview_duration_seconds;
    var main=app.project.items.addComp('E01_PREVIEW_UNBOUND_'+stamp,W,H,1,mainDuration,FPS);main.parentFolder=folder;
    main.comment='Still-art and editable AE direction preview. No finalized narration sync or render verification.';
    var elapsed=0;
    for(var si=0;si<CFG.scenes.length;si++){
        var S=CFG.scenes[si],dur=S.preview_duration_seconds;
        var comp=app.project.items.addComp(S.scene_id+'_UNBOUND',W,H,1,dur,FPS);comp.parentFolder=folder;
        comp.comment=S.intent;
        var mark=new MarkerValue('UNBOUND VOICE TIMING: exact source anchors stored in ae-scene-package.json');
        comp.markerProperty.setValueAtTime(0,mark);
        var layers={};
        for(var st=0;st<S.states.length;st++){
            var state=S.states[st],item=footage(state.file),l=comp.layers.add(item,dur);
            l.name=state.asset_id;l.inPoint=state.start*dur;l.outPoint=state.end*dur;
            var scale=Math.max(W/item.width,H/item.height)*100*1.035;
            l.property('Scale').setValue([scale,scale]);l.property('Position').setValue([W/2,H/2]);
            if(state.static_crop){
                var C=state.static_crop,cx=(C[0]+C[2])/2,cy=(C[1]+C[3])/2;
                var cropScale=Math.max(W/((C[2]-C[0])*item.width),H/((C[3]-C[1])*item.height))*100;
                var coverage= Math.max(cropScale,100*W/(2*Math.min(cx,1-cx)*item.width),100*H/(2*Math.min(cy,1-cy)*item.height));
                l.property('Scale').setValue([coverage,coverage]);
                l.property('Position').setValue([W/2+(0.5-cx)*item.width*coverage/100,H/2+(0.5-cy)*item.height*coverage/100]);
            }
            layers[state.asset_id]=l;
        }
        for(var ei=0;ei<S.effects.length;ei++){
            var E=S.effects[ei],at=E.preview_at*dur;
            var ed=Math.min(E.duration_seconds,dur-at-.01);
            if(ed>0)impact(comp,E,at,ed,layers[E.asset_id],ei);
        }
        for(var gi=0;gi<S.graphics.length;gi++){
            var G=S.graphics[gi],begin=G.preview_start*dur,end=Math.min(dur,G.preview_end*dur);
            if(end-begin<.15)begin=Math.max(0,end-.6);
            if(G.kind==='speech_bubble')bubble(comp,G,begin,end,gi);
            else textLayer(comp,G.kind+'_'+gi,G.text,G.style,xy(G.layout.center),begin,end,G.layout.size[0]*W);
        }
        if(si===CFG.scenes.length-1){
            var black=comp.layers.addSolid([0,0,0],'cliffhanger_black_before_result',W,H,1,dur);
            black.inPoint=dur*.975;black.outPoint=dur;
            black.property('Opacity').setValueAtTime(dur*.975,0);
            black.property('Opacity').setValueAtTime(dur*.99,100);
        }
        var clip=main.layers.add(comp);clip.startTime=elapsed;clip.inPoint=elapsed;clip.outPoint=elapsed+dur;
        elapsed+=dur;
    }
    main.openInViewer();
    var report=new File(DIR.fsName+'/ae-preview-build-report.txt');report.encoding='UTF-8';report.open('w');
    report.writeln('Created '+CFG.scenes.length+' editable still-art scene comps. No render or voice synchronization claimed.');
    for(var wi=0;wi<warnings.length;wi++)report.writeln(warnings[wi]);report.close();
    app.endUndoGroup();
})();
