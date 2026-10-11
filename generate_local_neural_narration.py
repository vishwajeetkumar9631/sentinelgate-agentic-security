"""Generate private, offline neural narration with Piper Lessac High."""
from __future__ import annotations
import json, subprocess
from pathlib import Path

ROOT=Path(__file__).resolve().parent
PIPER=ROOT/'piper_local'/'piper'/'piper.exe'
MODEL=ROOT/'piper_local'/'en_US-lessac-high.onnx'
CONFIG=ROOT/'piper_local'/'en_US-lessac-high.onnx.json'
ESPEAK=ROOT/'piper_local'/'piper'/'espeak-ng-data'
LENGTH_SCALE='1.08'


def main():
    segments=json.loads((ROOT/'video_narration.json').read_text(encoding='utf-8'))
    output_dir=ROOT/'narration_clips';output_dir.mkdir(exist_ok=True)
    for index,segment in enumerate(segments,1):
        output=output_dir/f'scene_{index:02}.wav'
        command=[str(PIPER),'--model',str(MODEL),'--config',str(CONFIG),'--espeak_data',str(ESPEAK),'--length_scale',LENGTH_SCALE,'--sentence_silence','0.32','--output_file',str(output),'--quiet']
        completed=subprocess.run(command,input=segment['narration']+'\n',text=True,capture_output=True,cwd=PIPER.parent)
        if completed.returncode:raise RuntimeError(completed.stderr[-2000:])
        print(f"Created {output.name} · {segment['title']} · Piper Lessac High",flush=True)
    metadata={'engine':'Piper local neural TTS','voice':'en_US-lessac-high','quality':'high','length_scale':float(LENGTH_SCALE),'privacy':'offline synthesis; narration not uploaded'}
    (ROOT/'voice_metadata.json').write_text(json.dumps(metadata,indent=2),encoding='utf-8')


if __name__=='__main__':main()
