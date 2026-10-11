"use client";
import { useEffect, useRef, useState } from "react";
import { regionLayerKey, type RegionMotion } from "@/lib/stdRegionMotion";
import { regionMotionText } from '@/lib/stdRegionMotionCopy';

type Props = {
  locale?: string;
  projectId: string;
  headers: Record<string, string>;
  number: number;
  imageId: string;
  sha: string;
  image: string;
  regions: RegionMotion[];
  selected: number;
  patch: (p: Partial<RegionMotion>) => void;
  backgroundAssetId: string;
  onBackground: (id: string) => void;
  onReady: (id: string) => void;
  onPreview: (urls: Record<string, string>) => void;
  onBusy: (busy: boolean) => void;
  locked: boolean;
};
const button =
  "rounded border border-white/20 px-3 py-2 text-sm disabled:opacity-40";
export default function StdRegionLayers(p: Props) {
 const tr = (text: string) => regionMotionText(text, p.locale)
  const api = `/api/std/projects/${p.projectId}/region-layers`;
  const [pack, setPack] = useState<any>(null),
    [busy, setBusy] = useState(false),
    [notice, setNotice] = useState(""),
    [urls, setUrls] = useState<Record<string, string>>({}),
    [reviewed, setReviewed] = useState(false),
    [editing, setEditing] = useState(false);
  const canvas = useRef<HTMLCanvasElement>(null),
    restore = useRef<HTMLImageElement | null>(null),
    drawing = useRef(false),
    lastPoint = useRef<[number, number] | null>(null),
    history = useRef<ImageData[]>([]),
    editRegionId = useRef("");
  const [brush, setBrush] = useState(12),
    [mode, setMode] = useState<"erase" | "restore" | "paint" | "sample">("erase"),
    [color, setColor] = useState("#ffd39b"),
    [zoom, setZoom] = useState(1);
  useEffect(() => {
    p.onBusy(busy);
    return () => p.onBusy(false);
  }, [busy, p.onBusy]);
  const region = p.regions[p.selected];
  let key = "";
  try {
    if (p.sha && p.regions.length)
      key = regionLayerKey(p.imageId, p.sha, p.regions, p.backgroundAssetId);
  } catch {}
  useEffect(() => { p.onPreview(urls); }, [urls, p.onPreview]);
  async function refresh() {
    const r = await fetch(api, { headers: p.headers }),
      data = await r.json();
    if (!r.ok) throw new Error(data.error);
    setPack(data.packages.find((a: any) => a.key === key) || null);
  }
  useEffect(() => {
    setPack(null);
    setReviewed(false);
    setEditing(false);
    if (!key) return;
    let active = true;
    const run = async () => {
      try {
        const r = await fetch(api, { headers: p.headers }),
          d = await r.json();
        if (!r.ok) throw new Error(d.error);
        if (active) setPack(d.packages.find((a: any) => a.key === key) || null);
      } catch (e: any) {
        if (active) setNotice(e.message);
      }
    };
    void run();
    const timer = setInterval(run, 5000);
    return () => {
      active = false;
      clearInterval(timer);
    };
  }, [api, key, p.headers]);
  useEffect(() => {
    p.onReady(pack?.key === key && pack?.state === "approved" ? pack.id : "");
  }, [pack?.id, pack?.key, pack?.state, key, p.onReady]);
  useEffect(() => {
    let active = true;
    const created: string[] = [];
    setUrls({});
    setReviewed(false);
    if (!pack?.result?.files) return;
    void Promise.all(
      pack.result.files.map(async (f: any) => {
        const r = await fetch(
          `${api}?id=${pack.id}&role=${encodeURIComponent(f.role)}`,
          { headers: p.headers },
        );
        if (!r.ok) throw new Error(tr("레이어 미리보기를 불러오지 못했습니다."));
        const url = URL.createObjectURL(await r.blob());
        if (!active) {
          URL.revokeObjectURL(url);
          return [f.role, ""];
        }
        created.push(url);
        return [f.role, url];
      }),
    )
      .then((rows) => {
        if (active) setUrls(Object.fromEntries(rows));
      })
      .catch((e) => {
        if (active) setNotice(e.message);
      });
    return () => {
      active = false;
      created.forEach(URL.revokeObjectURL);
    };
  }, [pack?.id, pack?.result?.files?.length, api, p.headers]);
  async function action(action: string) {
    setBusy(true);
    setNotice("");
    try {
      const r = await fetch(api, {
          method: "POST",
          headers: p.headers,
          body: JSON.stringify({
            action,
            sceneNumber: p.number,
            imageId: p.imageId,
            imageSha256: p.sha,
            regions: p.regions,
            backgroundAssetId: p.backgroundAssetId,
            packageId: pack?.id,
            reviewed,
          }),
        }),
        d = await r.json();
      if (!r.ok) throw new Error(d.error);
      await refresh();
      setNotice(
        action === "approve"
          ? tr("레이어를 확정했습니다. 동작을 바꿔도 재사용합니다.")
          : tr("외곽선 분리와 배경 복원을 요청했습니다."),
      );
    } catch (e: any) {
      setNotice(e.message);
    } finally {
      setBusy(false);
    }
  }
  async function upload(blob: Blob, role: "foreground" | "background") {
    setBusy(true);
    setNotice("");
    try {
      const f = new FormData();
      for (const [k, v] of Object.entries({
        action: "upload",
        sceneNumber: String(p.number),
        imageId: p.imageId,
        imageSha256: p.sha,
        role,
      }))
        f.set(k, v);
      f.set("file", blob, "layer.png");
      const headers = { ...p.headers };
      delete headers["Content-Type"];
      delete headers["content-type"];
      const r = await fetch(api, { method: "POST", headers, body: f }),
        d = await r.json();
      if (!r.ok) throw new Error(d.error);
      if (role === "background") p.onBackground(d.asset.id);
      else p.patch({ replacementAssetId: d.asset.id, contour: "exact" });
      setEditing(false);
      setNotice(
        tr("보완 이미지를 저장했습니다. 레이어 준비를 눌러 합성 결과를 확인해 주세요."),
      );
    } catch (e: any) {
      setNotice(e.message);
    } finally {
      setBusy(false);
    }
  }
  async function edit() {
    if (!region || !p.image) return;
    editRegionId.current = region.id;
    history.current = [];
    setEditing(true);
    setMode("erase");
    setZoom(1);
    const load = (url: string) =>
      new Promise<HTMLImageElement>((resolve, reject) => {
        const im = new Image();
        im.onload = () => resolve(im);
        im.onerror = reject;
        im.src = url;
      });
    try {
      const layerUrl = urls["region:" + region.id];
      let replacementUrl = '';
      try {
        // A saved replacement must survive package invalidation and subsequent edits.
        if (!layerUrl && region.replacementAssetId) {
          const r = await fetch(`${api}?upload=${encodeURIComponent(region.replacementAssetId)}`, {headers: p.headers});
          if (!r.ok) throw new Error('보완 부위를 불러오지 못했습니다.');
          replacementUrl = URL.createObjectURL(await r.blob());
        }
        const [source, layer] = await Promise.all([load(p.image), layerUrl || replacementUrl ? load(layerUrl || replacementUrl) : Promise.resolve(null)]);
        if (editRegionId.current !== region.id) return;
        restore.current = source;
        const c = canvas.current;
        if (!c) return;
        const ratio = Math.min(1, 1920 / Math.max(source.naturalWidth, source.naturalHeight));
        c.width = Math.max(2, Math.floor(source.naturalWidth * ratio / 2) * 2);
        c.height = Math.max(2, Math.floor(source.naturalHeight * ratio / 2) * 2);
        const ctx = c.getContext('2d')!;
        if (layer) ctx.drawImage(layer, 0, 0, c.width, c.height);
        else {
          ctx.save(); ctx.beginPath();
          region.polygon.forEach(([x,y],i) => i ? ctx.lineTo(x*c.width,y*c.height) : ctx.moveTo(x*c.width,y*c.height));
          ctx.closePath(); ctx.clip(); ctx.drawImage(source,0,0,c.width,c.height); ctx.restore();
        }
      } finally { if (replacementUrl) URL.revokeObjectURL(replacementUrl); }
    } catch {
      setNotice(tr("브러시 편집 이미지를 불러오지 못했습니다."));
      setEditing(false);
    }
  }
  function paint(e: React.PointerEvent<HTMLCanvasElement>) {
    const c = e.currentTarget,
      b = c.getBoundingClientRect(),
      x = ((e.clientX - b.left) * c.width) / b.width,
      y = ((e.clientY - b.top) * c.height) / b.height,
      ctx = c.getContext("2d")!;
    if (mode === 'sample') {
      const pixel = ctx.getImageData(Math.min(c.width-1, Math.max(0,Math.floor(x))),Math.min(c.height-1,Math.max(0,Math.floor(y))),1,1).data;
      if (pixel[3]) setColor('#'+Array.from(pixel.slice(0,3), n => n.toString(16).padStart(2,'0')).join(''));
      return;
    }
    const previous = lastPoint.current || [x,y];
    ctx.save(); ctx.beginPath();
    ctx.lineWidth = brush*2; ctx.lineCap = 'round'; ctx.lineJoin = 'round';
    ctx.moveTo(previous[0],previous[1]); ctx.lineTo(x,y);
    if (mode === 'restore') {
      // A continuous capsule clip restores original pixels, including the hidden overlap margin.
      const dx=x-previous[0], dy=y-previous[1], len=Math.hypot(dx,dy);
      ctx.beginPath(); ctx.arc(previous[0],previous[1],brush,0,Math.PI*2);
      ctx.arc(x,y,brush,0,Math.PI*2);
      if (len) {
        const nx=-dy/len*brush, ny=dx/len*brush;
        ctx.moveTo(previous[0]+nx,previous[1]+ny);ctx.lineTo(x+nx,y+ny);
        ctx.lineTo(x-nx,y-ny);ctx.lineTo(previous[0]-nx,previous[1]-ny);ctx.closePath();
      }
      ctx.clip(); if (restore.current) ctx.drawImage(restore.current,0,0,c.width,c.height);
    } else {
      ctx.globalCompositeOperation=mode==='erase'?'destination-out':'source-over';
      ctx.strokeStyle=color;ctx.stroke();
      ctx.beginPath();ctx.arc(x,y,brush,0,Math.PI*2);ctx.fillStyle=color;ctx.fill();
    }
    ctx.restore(); lastPoint.current=[x,y];
  }
  function checkpoint() {
    const c=canvas.current;
    if (c) { history.current.push(c.getContext('2d')!.getImageData(0,0,c.width,c.height)); if(history.current.length>12)history.current.shift(); }
  }
  const disabled = busy || p.locked;
  return (
    <section className="mt-4 rounded border border-cyan-700 p-3 space-y-3">
      <h3 className="font-bold text-cyan-200">{tr("정밀 레이어 준비 · 저장 · 재사용")}</h3>
      <p className="text-xs text-gray-300">{tr("검수한 외곽선과 전체 캔버스 배경을 확정하면, 속도·반복·고정점을 바꿔도 같은 승인 레이어를 재사용합니다. 자동 외곽선 분리와 자동 배경 복원은 사용하지 않습니다.")}</p>
      {region && (
        <fieldset disabled={disabled} className="space-y-2">
          <label className="block">{tr("선택 부위 외곽선")}{" "}
            <select
              className="bg-gray-800 p-1"
              value={region.contour || "auto"}
              onChange={(e) =>
                p.patch({
                  contour: e.target.value as "auto" | "exact",
                })
              }
            >
              <option value="auto" disabled>{tr("자동 분리 사용 안 함")}</option>
              <option value="exact">{tr("내가 그린 외곽선 그대로")}</option>
            </select>
          </label>
          <label className="block">
            <input
              type="checkbox"
              checked={!!region.occluded}
              onChange={(e) => p.patch({ occluded: e.target.checked })}
            />{" "}{tr("이 부위가 가려졌거나 이미지 밖으로 잘려 있음")}</label>
          {region.occluded && (
            <p className="text-amber-200">{tr("보이지 않는 형태는 자동으로 확정하지 않습니다. 부위 그리기에서 가려진 형태와 관절 겹침을 그려 저장하거나 완성된 투명 PNG를 추가하세요.")}</p>
          )}
          <label className="block">{tr("완성·수정한 부위 추가 (투명 PNG)")}{" "}
            <input
              aria-label={tr("보완 부위 이미지")}
              type="file"
              accept="image/png"
              onChange={(e) => {
                const f = e.target.files?.[0];
                if (f) void upload(f, "foreground");
                e.target.value = "";
              }}
            />
          </label>
          {region.replacementAssetId && (
            <button
              className={button}
              onClick={() => p.patch({ replacementAssetId: "" })}
            >{tr("추가 부위 사용 해제")}</button>
          )}
          <label className="block">{tr("검수한 전체 캔버스 배경 이미지 추가 (필수)")}{" "}
            <input
              aria-label={tr("수정 배경 이미지")}
              type="file"
              accept="image/png,image/jpeg,image/webp"
              onChange={(e) => {
                const f = e.target.files?.[0];
                if (f) void upload(f, "background");
                e.target.value = "";
              }}
            />
          </label>
          {p.backgroundAssetId && (
            <button className={button} onClick={() => p.onBackground("")}>{tr("수정 배경 사용 해제")}</button>
          )}
          <p className="text-xs text-gray-400">{tr("추가 이미지는 원본 전체 캔버스와 같은 크기·위치로 맞춰 주세요. 준비된 레이어를 내려받아 수정 후 다시 올릴 수도 있습니다. 최대 4MB.")}</p>
        </fieldset>
      )}
      <button className={button} disabled={disabled || !region || !p.image} onClick={() => void edit()}>{tr("부위 그리기 · 가려진 부분·관절 겹침 보완")}</button>
      <div className="flex flex-wrap gap-2 items-center">
        <button
          className={button}
          disabled={
            disabled ||
            !key ||
            !p.backgroundAssetId ||
            p.regions.some((item) => item.contour !== "exact") ||
            ["queued", "processing"].includes(pack?.state)
          }
          onClick={() => void action("prepare")}
        >{tr("검수 레이어 준비 / 저장 레이어 불러오기")}</button>
        <span>
          {
            (
              {
                queued: tr("레이어 준비 대기"),
                processing: tr("레이어 준비 중"),
                prepared: tr("레이어 검토 필요"),
                approved: tr("확정한 레이어 재사용 가능"),
                failed: tr("준비 실패"),
              } as any
            )[pack?.state]
          }
        </span>
      </div>
      {pack?.error && <p className="text-amber-200">{tr(pack.error)}</p>}
      {pack?.result?.warnings?.map((w: string) => (
        <p className="text-xs text-amber-200" key={tr(w)}>
          {w}
        </p>
      ))}
      {pack?.key === key &&
        pack?.result?.files &&
        !!Object.keys(urls).length && (
          <>
            <div className="grid gap-3 md:grid-cols-3">
              {[
                ["background", tr("복원 배경")],
                ["region:" + region?.id, tr("선택 부위")],
                ["composite", tr("정지 합성 결과")],
              ].map(
                ([role, label]) =>
                  urls[role] && (
                    <div key={role}>
                      <p>{label}</p>
                      <img
                        alt={label}
                        src={urls[role]}
                        className="w-full border border-white/20"
                        style={{
                          background:
                            "repeating-conic-gradient(#777 0% 25%,#bbb 0% 50%) 0/16px 16px",
                        }}
                      />
                      <a
                        className="text-cyan-300 underline"
                        download={`${role.replace(":", "-")}.png`}
                        href={urls[role]}
                      >{tr("PNG 내려받기")}</a>
                    </div>
                  ),
              )}
            </div>
            <div className="flex flex-wrap gap-2">
              <button
                className={button}
                disabled={disabled || !urls["region:" + region?.id]}
                onClick={() => void edit()}
              >{tr("선택 부위 외곽선 브러시 수정")}</button>
              {pack.result.files
                .filter((f: any) => f.role.startsWith("region:"))
                .map((f: any, i: number) => (
                  <a
                    key={f.role}
                    className={button}
                    href={urls[f.role]}
                    download={`layer-${i + 1}.png`}
                  >{tr("부위")}{i + 1} PNG
                  </a>
                ))}
            </div>
            <label className="block">
              <input
                type="checkbox"
                checked={reviewed}
                disabled={disabled}
                onChange={(e) => setReviewed(e.target.checked)}
              />{" "}{tr("모든 부위의 외곽선·가려진 부분·복원 배경과 합성 결과를 확인했습니다.")}</label>
            <button
              className={`${button} bg-emerald-800`}
              disabled={
                disabled ||
                !reviewed ||
                pack?.state === "approved" ||
                Object.keys(urls).length !== pack?.result?.files?.length
              }
              onClick={() => void action("approve")}
            >{tr("레이어 확정하고 재사용")}</button>
          </>
        )}
      <p role="status" className="text-cyan-200">
        {tr(notice)}
      </p>
      {editing && (
        <div className="fixed inset-0 z-[195] bg-black/95 p-4 flex flex-col">
          <p className="text-sm mb-2">{tr("관절 중심에 둥근 겹침 부분을 그려 틈을 덮으세요. 가려진 팔·다리는 색칠로 완성합니다. 저장 후 레이어 준비·확정과 동작 검토가 필요합니다.")}</p>
          <div className="flex flex-wrap gap-2 mb-2">
            <button className={button} onClick={() => setMode('paint')}>{tr("색칠")}{mode === 'paint' ? '✓' : ''}</button>
            <button className={button} onClick={() => setMode('sample')}>{tr("색 추출")}{mode === 'sample' ? '✓' : ''}</button>
            <input aria-label={tr("부위 색상")} type="color" value={color} onChange={(e) => setColor(e.target.value)} />
            <button className={button} onClick={() => {
              const c=canvas.current; if(!c || !region)return; checkpoint();
              const ctx=c.getContext('2d')!;ctx.fillStyle=color;ctx.beginPath();
              ctx.arc(region.anchor[0]*c.width,region.anchor[1]*c.height,brush,0,Math.PI*2);ctx.fill();
            }}>{tr("관절 겹침 원 그리기")}</button>
            <button className={button} onClick={() => {const prev=history.current.pop(); if(prev)canvas.current?.getContext('2d')?.putImageData(prev,0,0)}}>{tr("되돌리기")}</button>
            <button className={button} onClick={() => setMode("erase")}>{tr("지우기")}{mode === "erase" ? "✓" : ""}
            </button>
            <button className={button} onClick={() => setMode("restore")}>{tr("원본에서 복원")}{mode === "restore" ? "✓" : ""}
            </button>
            <label>{tr("브러시")}{" "}
              <input
                type="range"
                min="1"
                max="120"
                value={brush}
                onChange={(e) => setBrush(Number(e.target.value))}
              />
              {brush}px
            </label>
            <label>{tr("확대")}{" "}
              <select
                value={zoom}
                className="bg-gray-800"
                onChange={(e) => setZoom(Number(e.target.value))}
              >
                <option value="1">1×</option>
                <option value="2">2×</option>
                <option value="3">3×</option>
              </select>
            </label>
            <button
              className={button}
              disabled={disabled}
              onClick={() =>
                canvas.current?.toBlob((b) => {
                  if (b) void upload(b, "foreground");
                }, "image/png")
              }
            >{tr("수정한 외곽선 저장")}</button>
            <button
              className={button}
              disabled={busy}
              onClick={() => setEditing(false)}
            >{tr("닫기")}</button>
          </div>
          <div className="overflow-auto flex-1">
            <canvas
              ref={canvas}
              className="touch-none"
              style={{
                width: `${zoom * 100}%`,
                background:
                  "repeating-conic-gradient(#777 0% 25%,#bbb 0% 50%) 0/16px 16px",
              }}
              onPointerDown={(e) => {
                if (disabled) return;
                checkpoint(); lastPoint.current = null;
                drawing.current = true;
                e.currentTarget.setPointerCapture(e.pointerId);
                paint(e);
              }}
              onPointerMove={(e) => {
                if (drawing.current && !disabled) paint(e);
              }}
              onPointerUp={() => {
                drawing.current = false; lastPoint.current = null;
              }}
              onPointerCancel={() => {
                drawing.current = false; lastPoint.current = null;
              }}
            />
          </div>
        </div>
      )}
    </section>
  );
}
