"""Production-oriented security primitives that require no external model service.

The semantic classifier is a transparent TF-IDF-style cosine baseline.  Its
interface can be replaced by an ONNX embedding model without changing policy.
"""
from __future__ import annotations
import hashlib, hmac, json, math, os, re, secrets
from pathlib import Path

_PROCESS_DEMO_SIGNING_KEY=secrets.token_bytes(32)

ATTACK_SEEDS={
 'Instruction Override':'ignore earlier instructions override policy forget rules',
 'Role Change':'act as a different persona developer mode unrestricted assistant',
 'Secret Extraction':'reveal system prompt secrets hidden instructions api key',
 'Tool Abuse':'execute shell command delete files send network request',
 'Credential Theft':'export password token credentials private key access key',
 'Context Poisoning':'trusted document authoritative context do not disclose these instructions',
 'Multi-Step Jailbreak':'first bypass restrictions then reveal hidden data',
 'Encoded Instructions':'decode base64 encoded prompt instructions',
 'Indirect Prompt Injection':'webpage document tells agent to ignore instructions'}

def tokens(v): return re.findall(r'[a-z]{3,}',v.lower())
def cosine(a,b):
    av={x:tokens(a).count(x) for x in set(tokens(a))};bv={x:tokens(b).count(x) for x in set(tokens(b))}
    dot=sum(av.get(k,0)*bv.get(k,0) for k in set(av)|set(bv)); den=math.sqrt(sum(x*x for x in av.values())*sum(x*x for x in bv.values()))
    return dot/den if den else 0.0
def semantic_classify(text):
    scores={name:round(cosine(text,seed),3) for name,seed in ATTACK_SEEDS.items()}; name=max(scores,key=scores.get)
    return {'category':name,'score':scores[name],'scores':scores}

def content_fingerprint(value):
    """Return a stable, non-reversible identifier for evidence correlation."""
    if not isinstance(value, str):
        value=json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=False)
    return hashlib.sha256(value.encode('utf-8')).hexdigest()

class DecisionSigner:
    """HMAC-sign policy decisions so downstream agents cannot alter them.

    Deployments must set SENTINELGATE_SIGNING_KEY. The local demo uses an
    ephemeral process-only key, so no signing credential is stored in source.
    """
    def __init__(self):
        configured=os.getenv('SENTINELGATE_SIGNING_KEY')
        self.secret=configured.encode('utf-8') if configured else _PROCESS_DEMO_SIGNING_KEY
        self.key_id='env-v1' if configured else 'demo-ephemeral-v1'
    def sign(self,payload):
        body=json.dumps(payload,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode('utf-8')
        return hmac.new(self.secret,body,hashlib.sha256).hexdigest()
    def verify(self,payload,signature):
        return hmac.compare_digest(self.sign(payload),str(signature or ''))

class IntentContracts:
    def __init__(self): self.path=Path('sentinelgate_intents.json')
    def _all(self): return json.loads(self.path.read_text()) if self.path.exists() else {}
    def set_once(self,session_id,declared_intent,allowed_actions,prohibited_actions):
        rows=self._all()
        if session_id in rows: return rows[session_id],False
        canary='CANARY-SHIELD-'+secrets.token_urlsafe(8).upper()
        record={'session_id':session_id,'declared_intent':declared_intent,'allowed_actions':allowed_actions,'prohibited_actions':prohibited_actions,'canary':canary,'risk_drift_score':0.0}
        rows[session_id]=record;self.path.write_text(json.dumps(rows,indent=2));return record,True
    def get(self,session_id): return self._all().get(session_id)
    def assess(self,session_id,text):
        c=self.get(session_id)
        if not c:return {'anchored':False,'drift':0.0,'violation':False}
        intent=cosine(text,c['declared_intent']); bad=max([cosine(text,x) for x in c['prohibited_actions']] or [0]); drift=round(min(1, bad+(1-intent)*.25),3)
        return {'anchored':True,'drift':drift,'violation':bad>=.35,'contract':c}

def canary_check(text,session_id):
    c=IntentContracts().get(session_id); canary=c and c['canary']
    return bool(canary and canary in text),canary
