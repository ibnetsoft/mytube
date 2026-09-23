from http.server import SimpleHTTPRequestHandler,ThreadingHTTPServer
from pathlib import Path
import re

class PreviewHandler(SimpleHTTPRequestHandler):
    def __init__(self,*args,**kwargs):
        super().__init__(*args,directory=str(Path(__file__).resolve().parent),**kwargs)
    def send_head(self):
        self.remaining=None
        path=Path(self.translate_path(self.path))
        value=self.headers.get('Range','')
        if value and path.is_file():
            match=re.fullmatch(r'bytes=(\d+)-(\d*)',value)
            size=path.stat().st_size
            if not match:
                self.send_error(416);return None
            start=int(match[1]);end=min(size-1,int(match[2]) if match[2] else size-1)
            if start>end:
                self.send_response(416);self.send_header('Content-Range',f'bytes */{size}');self.end_headers();return None
            stream=path.open('rb');stream.seek(start)
            self.remaining=end-start+1
            self.send_response(206)
            self.send_header('Content-Type',self.guess_type(str(path)))
            self.send_header('Content-Length',str(self.remaining))
            self.send_header('Content-Range',f'bytes {start}-{end}/{size}')
            self.end_headers()
            return stream
        return super().send_head()
    def end_headers(self):
        self.send_header('Accept-Ranges','bytes')
        self.send_header('Cache-Control','no-cache')
        super().end_headers()
    def copyfile(self,source,outputfile):
        try:
            if self.remaining is None:return super().copyfile(source,outputfile)
            while self.remaining:
                data=source.read(min(self.remaining,65536))
                if not data:break
                outputfile.write(data);self.remaining-=len(data)
        except (BrokenPipeError,ConnectionResetError,ConnectionAbortedError):pass

ThreadingHTTPServer(('127.0.0.1',3005),PreviewHandler).serve_forever()
