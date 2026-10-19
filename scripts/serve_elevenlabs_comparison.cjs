const http = require('node:http'), fs = require('node:fs'), path = require('node:path');
const root = path.resolve(__dirname,'../_dev/artifacts/elevenlabs-v4-comparison');
const mime = {'.html':'text/html; charset=utf-8','.mp3':'audio/mpeg','.vtt':'text/vtt; charset=utf-8','.png':'image/png','.json':'application/json'};
http.createServer((req,res)=>{
  const name = decodeURIComponent(new URL(req.url,'http://localhost').pathname).slice(1) || 'comparison.html';
  if (name !== path.basename(name) || !/\.(html|mp3|vtt|png|json)$/.test(name)) {res.writeHead(404);return res.end()}
  const file = path.join(root,name);
  if (!fs.existsSync(file)) {res.writeHead(404);return res.end()}
  const size = fs.statSync(file).size;
  const range = req.headers.range?.match(/^bytes=(\d+)-(\d*)$/);
  const start = range ? Number(range[1]) : 0, end = range?.[2] ? Math.min(Number(range[2]),size-1) : size-1;
  if(start>end || start>=size){res.writeHead(416,{'Content-Range':`bytes */${size}`});return res.end()}
  res.writeHead(range?206:200,{'Content-Type':mime[path.extname(name)],'Content-Length':end-start+1,'Accept-Ranges':'bytes',...(range?{'Content-Range':`bytes ${start}-${end}/${size}`}:{})});
  if(req.method==='HEAD')return res.end();
  fs.createReadStream(file,{start,end}).pipe(res);
}).listen(3018,'127.0.0.1',()=>console.log('http://127.0.0.1:3018/comparison.html'));
