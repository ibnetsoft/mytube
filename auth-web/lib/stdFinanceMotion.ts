export type FinanceMotion = {mode:'chart'|'leverage'|'liquidation';pair:string;capital:number;leverage:number;change:number;maintenance:number}
export const financeMotion = ():FinanceMotion => ({mode:'chart',pair:'EUR/USD',capital:1000,leverage:10,change:-5,maintenance:50})
export function normalizeFinanceMotion(v:any):FinanceMotion {
    if(!v||!['chart','leverage','liquidation'].includes(v.mode)||typeof v.pair!=='string'||!v.pair.trim()||v.pair.length>24)throw Error('FX 그래픽의 종류와 통화쌍을 확인해 주세요.')
    for(const [key,min,max] of [['capital',1,1000000000],['leverage',1,1000],['change',-100,100],['maintenance',1,100]] as const)if(typeof v[key]!=='number'||!Number.isFinite(v[key])||v[key]<min||v[key]>max)throw Error(`FX ${key}: ${min}~${max} 범위를 확인해 주세요.`)
    return {mode:v.mode,pair:v.pair.trim(),capital:v.capital,leverage:v.leverage,change:v.change,maintenance:v.maintenance}
}
/** Illustrative long position, fixed initial margin, no fees or currency conversion. */
export function financeFrame(v:FinanceMotion,t:number){
    const progress=Math.max(0,Math.min(1,t)),threshold=(v.maintenance/100-1)/v.leverage*100
    const stopped=v.mode==='liquidation'&&v.change<0&&v.change*progress<=threshold
    const change=stopped?threshold:v.change*progress,pnl=(change===0?0:v.capital*v.leverage*change/100)
    return {progress,change,pnl,equity:v.capital+pnl,exposure:v.capital*v.leverage,stopped,threshold}
}
export function drawFinanceMotion(ctx:CanvasRenderingContext2D,w:number,h:number,v:FinanceMotion,t:number){
    if(h>w){ctx.save();ctx.fillStyle='#0b1220';ctx.fillRect(0,0,w,h);ctx.translate(0,(h-w*9/16)/2);drawFinanceMotion(ctx,w,w*9/16,v,t);ctx.restore();return}
    const f=financeFrame(v,t),u=Math.min(w/1920,h/1080),money=(n:number)=>n.toLocaleString('en-US',{maximumFractionDigits:2}),text=(s:string,x:number,y:number,size=36,color='#e2e8f0')=>{ctx.font=`600 ${size*u}px sans-serif`;ctx.fillStyle=color;ctx.fillText(s,x*w,y*h)}
    ctx.save();ctx.fillStyle='#0b1220';ctx.fillRect(0,0,w,h)
    text(`${v.pair} · ${v.mode==='chart'?'환율과 손익':v.mode==='leverage'?'레버리지와 거래 규모':'증거금과 청산'}`, .07,.12,54)
    text(`매수 예시 · ${v.leverage}배 · 환율 ${f.change>=0?'+':''}${f.change.toFixed(2)}%`,.07,.21)
    if(v.mode==='chart'){
        ctx.strokeStyle='#334155';ctx.lineWidth=3*u;ctx.beginPath();ctx.moveTo(w*.1,h*.32);ctx.lineTo(w*.1,h*.65);ctx.lineTo(w*.9,h*.65);ctx.stroke()
        ctx.strokeStyle=f.change<0?'#fb7185':'#34d399';ctx.lineWidth=7*u;ctx.beginPath();ctx.moveTo(w*.1,h*.48);ctx.lineTo(w*(.1+.8*f.progress),h*(.48-.14*f.change/Math.max(1,Math.abs(v.change))));ctx.stroke()
    }else{
        const rows=v.mode==='leverage'?[['증거금',v.capital,1/v.leverage],['거래 규모',v.capital+(f.exposure-v.capital)*f.progress,(1+(v.leverage-1)*f.progress)/v.leverage]]:[['초기 증거금',v.capital,1],['계좌 평가액',f.equity,Math.max(0,f.equity/v.capital)]]
        rows.forEach(([label,value,ratio],i)=>{const y=.36+i*.17;text(`${label}  $${money(Number(value))}`,.1,y);ctx.fillStyle=i===1&&f.pnl<0?'#fb7185':'#38bdf8';ctx.fillRect(w*.1,h*(y+.025),w*.8*Math.min(1,Number(ratio)),h*.045)})
        if(v.mode==='liquidation'){const x=w*(.1+.8*v.maintenance/100);ctx.strokeStyle='#fbbf24';ctx.lineWidth=4*u;ctx.beginPath();ctx.moveTo(x,h*.51);ctx.lineTo(x,h*.63);ctx.stroke();text(`청산 기준 예시: 초기 증거금의 ${v.maintenance}%`,.1,.68,28,'#fbbf24')}
    }
    text(`손익  ${f.pnl>=0?'+':''}$${money(f.pnl)}    평가액  $${money(f.equity)}`,.1,.76,42,f.pnl<0?'#fb7185':'#34d399')
    if(f.stopped)text('예시 청산 기준 도달 · 포지션 종료',.1,.83,32,'#fbbf24')
    text('교육용 단순 계산 · 비용·환산 제외 · 실제 청산 조건은 거래사마다 다릅니다.',.07,.96,23,'#94a3b8');ctx.restore()
}
