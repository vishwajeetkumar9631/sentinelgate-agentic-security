"""Real-time file arrival monitor backed by the SentinelGate firewall.

The default mode is observation-only. Pass --quarantine to move BLOCK files
from the watched folder into a sibling quarantine folder after inspection.
"""
from __future__ import annotations
import argparse, hashlib, json, time
from datetime import datetime
from pathlib import Path

from firewall import canonicalize, inspect

SUPPORTED={'.txt','.md','.html','.htm','.json','.csv','.pdf','.docx','.eml','.email','.png','.jpg','.jpeg','.webp','.tiff','.bmp','.py','.js','.ts','.xml','.yaml','.yml'}
SOURCE_BY_SUFFIX={'.html':'Web page / HTML','.htm':'Web page / HTML','.eml':'Email','.email':'Email','.pdf':'PDF / document','.docx':'PDF / document','.json':'API response','.xml':'API response','.py':'Source code','.js':'Source code','.ts':'Source code','.png':'OCR text / image','.jpg':'OCR text / image','.jpeg':'OCR text / image','.webp':'OCR text / image'}


class RealtimeFileTracker:
    def __init__(self,watch_dir='demo_watch',quarantine_dir='demo_quarantine',enable_quarantine=False,event_file='file_tracking_events.json'):
        self.watch_dir=Path(watch_dir).resolve();self.quarantine_dir=Path(quarantine_dir).resolve();self.enable_quarantine=enable_quarantine;self.event_file=Path(event_file)
        self.watch_dir.mkdir(parents=True,exist_ok=True)
        if enable_quarantine:self.quarantine_dir.mkdir(parents=True,exist_ok=True)
        self.seen={};self.events=[]

    def _stable(self,path):
        stat=path.stat();signature=(stat.st_mtime_ns,stat.st_size)
        if self.seen.get(str(path))==signature:return False
        self.seen[str(path)]=signature;return True

    def inspect_file(self,path):
        path=Path(path).resolve()
        if path.parent!=self.watch_dir or path.suffix.lower() not in SUPPORTED:return None
        raw=path.read_bytes();digest=hashlib.sha256(raw).hexdigest();source=SOURCE_BY_SUFFIX.get(path.suffix.lower(),'User message')
        try:text,notes=canonicalize(raw,path.name,source);result=inspect(text,source,False,'file-tracker:'+digest[:12])
        except Exception as exc:
            result={'verdict':'BLOCK','risk':100,'findings':[{'attack':'Parser safety failure'}],'latency_ms':0};notes=[type(exc).__name__]
        action='tracked'
        if result['verdict']=='BLOCK' and self.enable_quarantine:
            destination=self.quarantine_dir/path.name
            if destination.exists():destination=self.quarantine_dir/f'{path.stem}-{int(time.time())}{path.suffix}'
            path.replace(destination);action='quarantined'
        event={'time':datetime.now().astimezone().isoformat(timespec='seconds'),'file':path.name,'extension':path.suffix.lower(),'bytes':len(raw),'sha256':digest,'source':source,'verdict':result['verdict'],'risk':result['risk'],'findings':sorted({x['attack'] for x in result['findings']}),'action':action,'latency_ms':result['latency_ms'],'notes':notes}
        self.events.append(event);self.event_file.write_text(json.dumps(self.events[-100:],indent=2),encoding='utf-8');return event

    def scan_once(self):
        events=[]
        for path in sorted(self.watch_dir.iterdir()):
            if path.is_file() and path.suffix.lower() in SUPPORTED and self._stable(path):
                event=self.inspect_file(path)
                if event:events.append(event)
        return events

    def run(self,interval=1.0):
        print(f'Watching {self.watch_dir} (Ctrl+C to stop)')
        try:
            while True:
                for event in self.scan_once():print(json.dumps(event,ensure_ascii=False))
                time.sleep(interval)
        except KeyboardInterrupt:print('Tracker stopped.')


def main():
    parser=argparse.ArgumentParser(description='Monitor arriving files with SentinelGate')
    parser.add_argument('watch_dir',nargs='?',default='demo_watch');parser.add_argument('--quarantine-dir',default='demo_quarantine');parser.add_argument('--quarantine',action='store_true');parser.add_argument('--interval',type=float,default=1.0)
    args=parser.parse_args();RealtimeFileTracker(args.watch_dir,args.quarantine_dir,args.quarantine).run(args.interval)


if __name__=='__main__':main()
