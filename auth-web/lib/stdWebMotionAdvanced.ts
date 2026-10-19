import {boneMatrices,deformPoint,sampleValue,defaultGlow,type GlowSettings,type Point,type LayerAdvanced,type NativeEffect,type NativePath} from './stdMotionRig'
const make=(w:number,h:number)=>{if(!Number.isFinite(w+h)||Math.ceil(w)*Math.ceil(h)>40_000_000)throw Error('효과·변형 캔버스가 너무 큽니다. 원본 크기나 이동 범위를 줄여 주세요.');const c=document.createElement('canvas');c.width=Math.max(1,Math.ceil(w));c.height=Math.max(1,Math.ceil(h));return c}
type MeshGpu={canvas:HTMLCanvasElement;gl:WebGLRenderingContext;program:WebGLProgram;buffer:WebGLBuffer;texture:WebGLTexture;position:number;uv:number;resolution:WebGLUniformLocation|null}
let meshGpu:MeshGpu|undefined
function gpu():MeshGpu {
    if(meshGpu&&!meshGpu.gl.isContextLost())return meshGpu
    const canvas=make(1,1),gl=canvas.getContext('webgl',{alpha:true,premultipliedAlpha:true,antialias:false,preserveDrawingBuffer:true})
    if(!gl)throw Error('관절·메시 변형에는 WebGL을 지원하는 Chrome 또는 Edge가 필요합니다.')
    const shader=(type:number,source:string)=>{const s=gl.createShader(type)!;gl.shaderSource(s,source);gl.compileShader(s);if(!gl.getShaderParameter(s,gl.COMPILE_STATUS))throw Error('메시 셰이더 초기화 실패');return s}
    const vs=shader(gl.VERTEX_SHADER,'attribute vec2 position; attribute vec2 uv; uniform vec2 resolution; varying vec2 tex; void main(){vec2 p=position/resolution*2.0-1.0;gl_Position=vec4(p.x,-p.y,0.0,1.0);tex=uv;}'),fs=shader(gl.FRAGMENT_SHADER,'precision mediump float; varying vec2 tex; uniform sampler2D image; void main(){gl_FragColor=texture2D(image,tex);}')
    const program=gl.createProgram()!;gl.attachShader(program,vs);gl.attachShader(program,fs);gl.linkProgram(program);if(!gl.getProgramParameter(program,gl.LINK_STATUS))throw Error('메시 렌더러 초기화 실패');gl.deleteShader(vs);gl.deleteShader(fs)
    meshGpu={canvas,gl,program,buffer:gl.createBuffer()!,texture:gl.createTexture()!,position:gl.getAttribLocation(program,'position'),uv:gl.getAttribLocation(program,'uv'),resolution:gl.getUniformLocation(program,'resolution')};return meshGpu
}
function drawMesh(canvas:HTMLCanvasElement,source:HTMLCanvasElement,input:Point[],output:Point[],columns:number,rows:number,left:number,top:number){
    const state=gpu(),{gl,program,buffer,texture,position,uv,resolution}=state,limit=Math.min(gl.getParameter(gl.MAX_TEXTURE_SIZE),gl.getParameter(gl.MAX_RENDERBUFFER_SIZE))
    if(Math.max(source.width,source.height,canvas.width,canvas.height)>limit)throw Error('그래픽 장치의 메시 크기 한도를 넘었습니다. 원본 크기를 줄여 주세요.')
    state.canvas.width=canvas.width;state.canvas.height=canvas.height
    const vertices:number[]=[];for(let y=0;y<rows;y++)for(let x=0;x<columns;x++){const a=y*(columns+1)+x,b=a+1,c=a+columns+1,d=c+1;for(const i of [a,b,d,a,d,c])vertices.push(output[i][0]-left,output[i][1]-top,input[i][0]/source.width,input[i][1]/source.height)}
    gl.viewport(0,0,canvas.width,canvas.height);gl.clearColor(0,0,0,0);gl.clear(gl.COLOR_BUFFER_BIT);gl.useProgram(program);gl.bindBuffer(gl.ARRAY_BUFFER,buffer);gl.bufferData(gl.ARRAY_BUFFER,new Float32Array(vertices),gl.STREAM_DRAW);gl.enableVertexAttribArray(position);gl.enableVertexAttribArray(uv);gl.vertexAttribPointer(position,2,gl.FLOAT,false,16,0);gl.vertexAttribPointer(uv,2,gl.FLOAT,false,16,8);gl.uniform2f(resolution,canvas.width,canvas.height)
    gl.activeTexture(gl.TEXTURE0);gl.bindTexture(gl.TEXTURE_2D,texture);gl.texParameteri(gl.TEXTURE_2D,gl.TEXTURE_MIN_FILTER,gl.LINEAR);gl.texParameteri(gl.TEXTURE_2D,gl.TEXTURE_MAG_FILTER,gl.LINEAR);gl.texParameteri(gl.TEXTURE_2D,gl.TEXTURE_WRAP_S,gl.CLAMP_TO_EDGE);gl.texParameteri(gl.TEXTURE_2D,gl.TEXTURE_WRAP_T,gl.CLAMP_TO_EDGE);gl.pixelStorei(gl.UNPACK_PREMULTIPLY_ALPHA_WEBGL,1);gl.texImage2D(gl.TEXTURE_2D,0,gl.RGBA,gl.RGBA,gl.UNSIGNED_BYTE,source);gl.drawArrays(gl.TRIANGLES,0,vertices.length/4)
    if(gl.getError()!==gl.NO_ERROR)throw Error('메시 렌더링에 실패했습니다. 그래픽 장치·원본 크기를 확인해 주세요.')
    canvas.getContext('2d')!.drawImage(state.canvas,0,0)
}
export function noise(x:number,y:number,z:number,seed:number):number {
    const hash=(a:number,b:number,c:number)=>{const v=Math.sin(a*127.1+b*311.7+c*74.7+seed*19.19)*43758.5453;return v-Math.floor(v)},smooth=(v:number)=>v*v*(3-2*v),lerp=(a:number,b:number,t:number)=>a+(b-a)*t,ix=Math.floor(x),iy=Math.floor(y),iz=Math.floor(z),fx=smooth(x-ix),fy=smooth(y-iy),fz=smooth(z-iz)
    const plane=(k:number)=>lerp(lerp(hash(ix,iy,k),hash(ix+1,iy,k),fx),lerp(hash(ix,iy+1,k),hash(ix+1,iy+1,k),fx),fy)
    return lerp(plane(iz),plane(iz+1),fz)
}
export function warpCanvas(source:HTMLCanvasElement,columns:number,rows:number,warp:(p:Point)=>Point){
    const input:Point[]=[],output:Point[]=[];for(let y=0;y<=rows;y++)for(let x=0;x<=columns;x++){const p:Point=[x/columns*source.width,y/rows*source.height];input.push(p);output.push(warp(p))}
    if(output.every((p,i)=>Math.abs(p[0]-input[i][0])<1e-8&&Math.abs(p[1]-input[i][1])<1e-8))return {canvas:source,left:0,top:0}
    const left=Math.floor(Math.min(0,...output.map(p=>p[0])))-1,top=Math.floor(Math.min(0,...output.map(p=>p[1])))-1,right=Math.ceil(Math.max(source.width,...output.map(p=>p[0])))+1,bottom=Math.ceil(Math.max(source.height,...output.map(p=>p[1])))+1
    if((right-left)*(bottom-top)>40_000_000||!Number.isFinite(right+bottom+left+top))throw Error('변형 결과가 너무 큽니다. 관절·핀 이동 범위를 줄여 주세요.')
    const canvas=make(right-left,bottom-top)
    drawMesh(canvas,source,input,output,columns,rows,left,top)
    return {canvas,left,top}
}
function maskCanvas(source:HTMLCanvasElement,mask:NonNullable<LayerAdvanced['mask']>){
    const c=make(source.width,source.height),m=make(source.width,source.height),ctx=c.getContext('2d')!,mc=m.getContext('2d')!;ctx.drawImage(source,0,0);mc.fillStyle='white';if(mask.feather)mc.filter=`blur(${mask.feather*Math.min(c.width,c.height)}px)`
    mc.beginPath();mask.points.forEach((p,i)=>i?mc.lineTo(p[0]*c.width,p[1]*c.height):mc.moveTo(p[0]*c.width,p[1]*c.height));mc.closePath();mc.fill();ctx.globalCompositeOperation=mask.invert?'destination-out':'destination-in';ctx.drawImage(m,0,0);return c
}
/** Extract bright/alpha seed before blur; never duplicate the whole source. */
export function glowSeed(source:HTMLCanvasElement,settings:GlowSettings){
    const seed=make(source.width,source.height),ctx=seed.getContext('2d')!,pixels=source.getContext('2d')!.getImageData(0,0,source.width,source.height)
    const {threshold,softKnee,basedOn}=settings
    for(let i=0;i<pixels.data.length;i+=4){
        const brightness=basedOn==='alpha'?pixels.data[i+3]/255:(.2126*pixels.data[i]+.7152*pixels.data[i+1]+.0722*pixels.data[i+2])/255
        const excess=Math.max(0,brightness-threshold),gain=threshold===1?0:softKnee===0?(brightness>threshold?1:0):Math.min(1,excess/Math.max(.00001,softKnee))
        pixels.data[i+3]*=gain
    }
    ctx.putImageData(pixels,0,0);return seed
}
export function applyNativeEffects(source:HTMLCanvasElement,effects:NativeEffect[],t:number,unit=Math.min(source.width,source.height)):HTMLCanvasElement {
    let current=source
    for(const e of effects){const value=sampleValue(e.keys,t),strength=e.amount/100,radius=e.radius*unit;if(!strength)continue
        const c=make(current.width,current.height),ctx=c.getContext('2d')!
        if(e.type==='blur'){ctx.filter=`blur(${radius*strength*value}px)`;ctx.drawImage(current,0,0)}
        if(e.type==='glow'){ctx.drawImage(current,0,0);if(value>0){const seed=glowSeed(current,e.glow||defaultGlow());ctx.globalCompositeOperation='lighter';ctx.globalAlpha=strength*value;ctx.filter=`blur(${radius}px)`;ctx.drawImage(seed,0,0)}}
        if(e.type==='radial_wipe'){ctx.save();ctx.beginPath();const angle=Math.PI*2*(1-strength*value),cx=c.width/2,cy=c.height/2,r=Math.hypot(c.width,c.height);ctx.moveTo(cx,cy);ctx.arc(cx,cy,r,-Math.PI/2,-Math.PI/2+angle);ctx.closePath();ctx.clip();ctx.drawImage(current,0,0);ctx.restore()}
        if(e.type==='fractal_noise'){
            ctx.drawImage(current,0,0);const small=make(Math.min(192,c.width),Math.min(192,c.height)),sc=small.getContext('2d')!,data=sc.createImageData(small.width,small.height)
            for(let y=0;y<small.height;y++)for(let x=0;x<small.width;x++){let v=0,weight=.5;for(let octave=0;octave<4;octave++){const f=2**octave;v+=noise(x/small.width/e.radius*f,y/small.height/e.radius*f,value*3,e.seed)*weight;weight*=.5}const i=(y*small.width+x)*4;data.data[i]=data.data[i+1]=data.data[i+2]=Math.max(0,(v-.3)*400);data.data[i+3]=255}sc.putImageData(data,0,0);ctx.globalCompositeOperation='screen';ctx.globalAlpha=strength;ctx.drawImage(small,0,0,c.width,c.height)
        }
        if(e.type==='turbulent_displace'){
            const result=warpCanvas(current,24,24,p=>[p[0]+(noise(p[0]/current.width/e.radius,p[1]/current.height/e.radius,value*3,e.seed)-.5)*strength*40,p[1]+(noise(p[0]/current.width/e.radius,p[1]/current.height/e.radius,value*3,e.seed+13)-.5)*strength*40]);ctx.drawImage(result.canvas,result.left,result.top)
        }
        current=c
    }
    return current
}
export function renderAdvancedLayer(source:HTMLCanvasElement,advanced:LayerAdvanced|undefined,t:number){
    if(!advanced)return {canvas:source,left:0,top:0}
    let current=advanced.mask?maskCanvas(source,advanced.mask):source,left=0,top=0
    if(advanced.rig||advanced.mesh?.pins.length){const m=advanced.rig?boneMatrices(advanced.rig,t,source.width,source.height):[],warped=warpCanvas(current,advanced.mesh?.columns||16,advanced.mesh?.rows||16,p=>deformPoint(p,advanced,t,source.width,source.height,m));current=warped.canvas;left=warped.left;top=warped.top}
    const style=advanced.style
    if(style&&(style.shadow||style.stroke)){
        const unit=Math.min(source.width,source.height),radius=style.shadow*unit,stroke=style.stroke*unit,dx=style.shadowX*source.width,dy=style.shadowY*source.height,pad=Math.ceil(Math.max(radius*3+Math.max(Math.abs(dx),Math.abs(dy)),stroke)+2),c=make(current.width+pad*2,current.height+pad*2),ctx=c.getContext('2d')!
        if(c.width*c.height>40_000_000)throw Error('레이어 스타일 결과가 너무 큽니다.')
        if(radius||dx||dy){ctx.shadowColor=style.shadowColor;ctx.shadowBlur=radius;ctx.shadowOffsetX=dx;ctx.shadowOffsetY=dy;ctx.drawImage(current,pad,pad);ctx.shadowColor='transparent'}
        if(stroke){const outline=make(c.width,c.height),oc=outline.getContext('2d')!;for(let i=0;i<16;i++)oc.drawImage(current,pad+Math.cos(i*Math.PI/8)*stroke,pad+Math.sin(i*Math.PI/8)*stroke);oc.globalCompositeOperation='source-in';oc.fillStyle=style.strokeColor;oc.fillRect(0,0,c.width,c.height);ctx.drawImage(outline,0,0)}
        ctx.drawImage(current,pad,pad);current=c;left-=pad;top-=pad
    }
    const effects=advanced.effects||[],unit=Math.min(source.width,source.height),pad=Math.ceil(3*Math.max(0,...effects.filter(e=>['glow','blur'].includes(e.type)&&e.amount>0).map(e=>e.radius*unit)))
    if(pad){const c=make(current.width+2*pad,current.height+2*pad);c.getContext('2d')!.drawImage(current,pad,pad);current=c;left-=pad;top-=pad}
    return {canvas:applyNativeEffects(current,effects,t,unit),left,top}
}
export function drawNativePaths(ctx:CanvasRenderingContext2D,paths:NativePath[],w:number,h:number,t:number){
    for(const p of paths){const points=p.points.map(([x,y])=>[x*w,y*h] as Point);if(p.closed)points.push(points[0]);const lengths=points.slice(1).map((v,i)=>Math.hypot(v[0]-points[i][0],v[1]-points[i][1])),total=lengths.reduce((a,b)=>a+b,0),start=total*(p.startKeys?sampleValue(p.startKeys,t):0),end=total*sampleValue(p.keys,t);let cursor=0,started=false
        ctx.save();ctx.strokeStyle=p.color;ctx.lineWidth=p.width*Math.min(w,h);ctx.lineCap='round';ctx.lineJoin='round';ctx.shadowColor=p.color;ctx.shadowBlur=p.glow*Math.min(w,h);ctx.beginPath();for(let i=0;i<lengths.length&&start<end;i++){const length=lengths[i];if(cursor+length>start&&cursor<end&&length>0){const a=Math.max(0,(start-cursor)/length),b=Math.min(1,(end-cursor)/length),point=(f:number):Point=>[points[i][0]+(points[i+1][0]-points[i][0])*f,points[i][1]+(points[i+1][1]-points[i][1])*f];if(!started){ctx.moveTo(...point(a));started=true}ctx.lineTo(...point(b))}cursor+=length}ctx.stroke();ctx.restore()
    }
}
