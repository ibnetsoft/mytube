import type { LayerMaskData } from 'ag-psd'

/** Bake a supported PSD raster mask into layer alpha, keeping the layer movable. */
export function applyPsdRasterMask(source:HTMLCanvasElement, mask:LayerMaskData|undefined, left:number, top:number):HTMLCanvasElement {
    if(!mask||mask.disabled)return source
    if(mask.fromVectorData||mask.userMaskFeather||mask.vectorMaskFeather||mask.vectorMaskDensity!==undefined)
        throw Error('벡터·페더 마스크는 아직 지원하지 않습니다. 기존 AE 방식으로 제작해 주세요.')
    const density=mask.userMaskDensity??1,background=mask.defaultColor??0
    if(!Number.isFinite(density)||density<0||density>1||![0,255].includes(background))throw Error('PSD 마스크 농도·배경 값이 올바르지 않습니다.')
    const canvas=document.createElement('canvas');canvas.width=source.width;canvas.height=source.height
    const ctx=canvas.getContext('2d')!;ctx.drawImage(source,0,0)
    const pixels=ctx.getImageData(0,0,canvas.width,canvas.height)
    const raster=mask.canvas
    if(!raster?.width||!raster.height)throw Error('PSD 마스크 픽셀 데이터가 없습니다. 기존 AE 방식으로 제작해 주세요.')
    const data=raster.getContext('2d')!.getImageData(0,0,raster.width,raster.height).data
    // Absolute masks use document coordinates; relative masks use layer coordinates.
    const x0=(mask.left??0)-(mask.positionRelativeToLayer?0:left),y0=(mask.top??0)-(mask.positionRelativeToLayer?0:top)
    if(!Number.isInteger(x0)||!Number.isInteger(y0))throw Error('PSD 마스크 좌표가 올바르지 않습니다.')
    for(let y=0;y<canvas.height;y++)for(let x=0;x<canvas.width;x++){
        const mx=x-x0,my=y-y0,gray=mx>=0&&my>=0&&mx<raster.width&&my<raster.height?data[(my*raster.width+mx)*4]:background
        pixels.data[(y*canvas.width+x)*4+3]*=1-density*(1-gray/255)
    }
    ctx.putImageData(pixels,0,0);return canvas
}
