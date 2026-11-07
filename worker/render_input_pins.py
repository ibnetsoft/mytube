"""Hold verified render inputs open until the leased job exits.

Windows denies deletion of a file opened by the CRT without delete sharing.
This lets maintenance skip active inputs without changing file permissions.
"""
from pathlib import Path

class RenderInputPins:
    def __init__(self):self.handles={}
    def pin(self,path):
        path=Path(path).resolve()
        if path not in self.handles:self.handles[path]=path.open('rb')
        return path
    def close(self):
        for handle in self.handles.values():handle.close()
        self.handles.clear()
