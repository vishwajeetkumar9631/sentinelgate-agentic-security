"""Enforcement components for SentinelGate's D3 firewall pipeline."""
from __future__ import annotations
import base64, codecs, hashlib, html, json, os, re, sqlite3, time, unicodedata, uuid
from contextlib import closing
from dataclasses import asdict, dataclass
from email import policy
from email.parser import BytesParser
from html.parser import HTMLParser
from pathlib import Path
from zipfile import ZipFile
from advanced_security import DecisionSigner, IntentContracts, canary_check, content_fingerprint, semantic_classify

@dataclass
class Finding: attack:str; severity:str; confidence:int; evidence:str; rule:str
RULES=[
 ("Instruction Override","critical",r"\b(ignore|disregard|override|forget)\b.{0,70}\b(previous|prior|system|instructions?|rules?)\b",96,"instruction-override"),("Role Change","high",r"\b(you are now|act as|pretend to be|switch (your )?role|developer mode|dan mode)\b",90,"role-change"),("Secret Extraction","critical",r"\b(reveal|show|print|dump|exfiltrate|leak)\b.{0,90}\b(system prompt|hidden prompt|secret|private (key|data)|api key)\b",97,"secret-extraction"),("Tool Abuse","critical",r"\b(run|execute|call|invoke|use)\b.{0,80}\b(shell|terminal|tool|browser|api|command)\b.{0,90}\b(delete|transfer|send|download|upload|without (asking|confirmation))\b",94,"tool-abuse"),("Credential Theft","critical",r"\b(password|token|credential|access key|api[_ -]?key|oauth)\b.{0,90}\b(send|share|post|paste|upload|reveal|steal|export)\b|\b(send|share|post|paste|upload|reveal|steal|export)\b.{0,90}\b(password|token|credential|access key|api[_ -]?key|oauth)\b",98,"credential-theft"),("Context Poisoning","high",r"\b(trusted|verified|safe)\s+(source|context|document).{0,90}\b(must|always|only)\b|\bdo not mention (this|these) instructions\b",84,"context-poisoning"),("Multi-Step Jailbreak","high",r"\b(step\s*1|first).{0,140}\b(step\s*2|then|next).{0,160}\b(bypass|ignore|reveal|disable|jailbreak)\b",88,"multi-step-jailbreak"),("Encoded Instructions","high",r"\b(base64|rot13|decode|hex)\b.{0,90}\b(ignore|instructions?|prompt|system|secret|token)\b",82,"encoded-instruction"),("Indirect Prompt Injection","critical",r"\b(webpage|document|email|pdf|retrieved|page)\b.{0,100}\b(instruction|assistant|agent)\b.{0,100}\b(ignore|send|reveal|execute)\b|<!--.{0,220}(ignore|system prompt|secret).{0,220}-->",93,"indirect-injection")]
SECRET=re.compile(r"\b(?:DEMO_SECRET_[A-Za-z0-9_-]{8,}|sk-[A-Za-z0-9_-]{16,}|AKIA[0-9A-Z]{16}|ghp_[A-Za-z0-9]{20,}|AIza[\w-]{20,}|eyJ[a-zA-Z0-9_-]{10,}\.[\w-]+\.[\w-]+)\b|-----BEGIN (?:RSA |OPENSSH )?PRIVATE KEY-----",re.I)
class MarkupCollector(HTMLParser):
 def __init__(self): super().__init__(); self.parts=[]; self.hidden_stack=[]
 def handle_comment(self,d): self.parts.append('[HTML comment] '+d)
 def handle_starttag(self,tag,attrs):
  a=dict(attrs); parent=any(x[1] for x in self.hidden_stack); hidden=parent or tag in {'script','style','template'} or 'display:none' in a.get('style','').replace(' ','').lower() or a.get('hidden') is not None or a.get('aria-hidden')=='true'
  if tag not in {'area','base','br','col','embed','hr','img','input','link','meta','param','source','track','wbr'}:self.hidden_stack.append((tag,hidden))
  for k in ('alt','title','content','value','href','src','data-instruction'):
   if a.get(k): self.parts.append(f'[{tag} {k}] {a[k]}')
 def handle_data(self,d):
  if d.strip(): self.parts.append(('[hidden] ' if any(x[1] for x in self.hidden_stack) else '')+d)
 def handle_endtag(self,tag):
  for i in range(len(self.hidden_stack)-1,-1,-1):
   if self.hidden_stack[i][0]==tag:del self.hidden_stack[i:];break
def ocr_image_bytes(raw,is_pdf=False):
 try:
  import pytesseract
  from PIL import Image
  if is_pdf:return '[OCR unavailable for scanned PDF in this environment]'
  return pytesseract.image_to_string(Image.open(__import__('io').BytesIO(raw)))
 except Exception:return '[OCR adapter unavailable: install Tesseract + pytesseract, or configure PaddleOCR]'
def canonicalize(raw,filename,source):
 name=(filename or '').lower(); notes=[]
 if name.endswith('.pdf'):
  import pymupdf
  doc=pymupdf.open(stream=raw,filetype='pdf'); text='\n'.join(p.get_text() for p in doc)
  if not text.strip():notes.append('Scanned PDF detected; OCR adapter required.');text=ocr_image_bytes(raw,True)
 elif name.endswith('.docx'):
  with ZipFile(__import__('io').BytesIO(raw)) as z:
   from xml.etree import ElementTree as ET
   root=ET.fromstring(z.read('word/document.xml'));text=' '.join(n.text or '' for n in root.iter() if n.tag.endswith('}t'))
 elif name.endswith(('.eml','.email')):
  msg=BytesParser(policy=policy.default).parsebytes(raw); body=msg.get_body(preferencelist=('plain','html'));text='\n'.join([msg.get('subject',''),msg.get('from',''),body.get_content() if body else ''])
 elif name.endswith(('.html','.htm')) or source=='Web page / HTML':
  p=MarkupCollector();p.feed(raw.decode('utf-8','replace'));text='\n'.join(p.parts)
 elif name.endswith(('.png','.jpg','.jpeg','.webp','.tiff','.bmp')) or source=='OCR text / image':text=ocr_image_bytes(raw)
 else:text=raw.decode('utf-8','replace')
 return text,notes
def normalize(text,depth=0):
 text=unicodedata.normalize('NFKC',html.unescape(text)).replace('\x00','').replace('\u200b','').replace('\u200c','').replace('\u200d','')
 if depth>=3:return text,[]
 vals=[]; tokens=re.findall(r'(?<![\w+/])[A-Za-z0-9+/]{24,8192}={0,2}(?![\w+/])',text)+re.findall(r'(?<!\w)(?:[0-9a-fA-F]{2}){12,4096}(?!\w)',text)
 for t in tokens[:12]:
  try:
   v=bytes.fromhex(t).decode('utf-8','ignore') if re.fullmatch(r'(?:[0-9a-fA-F]{2})+',t) else base64.b64decode(t,validate=True).decode('utf-8','ignore')
   if len(v)>3 and sum(c.isprintable() for c in v)/len(v)>.8:vals.append(v)
  except Exception:pass
 if re.search(r'\b(rot13|caesar)\b',text,re.I):vals.append(codecs.decode(text,'rot_13'))
 nxt,more=normalize('\n'.join(vals),depth+1) if vals else ('',[]);return text+('\n[decoded for inspection]\n'+nxt if nxt else ''),['decoded payload']*len(vals)+more
def excerpt(t,s,e):return re.sub(r'\s+',' ',t[max(0,s-55):e+75]).strip()

def sanitize_text(text, findings):
 """Remove only malicious sentence/line chunks and preserve surrounding data."""
 chunks=re.split(r'(?<=[.!?])\s+|\n+',text);kept=[];removed=[]
 for chunk in chunks:
  matches=[name for name,_,pat,_,_ in RULES if re.search(pat,chunk,re.I|re.S)]
  if matches:removed.append({'text':chunk[:500],'reason':', '.join(matches),'action':'removed'})
  else:kept.append(chunk)
 if findings and not removed:
  fallback=[]
  for chunk in kept:
   if re.search(r'\b(ignore|bypass|override|reveal|exfiltrate|credential|secret|password|delete|execute)\b',chunk,re.I):removed.append({'text':chunk[:500],'reason':findings[0].attack,'action':'removed'});fallback.append(chunk)
  kept=[x for x in kept if x not in fallback]
 clean='\n'.join(x for x in kept if x.strip()).strip()
 residual=sorted({name for name,_,pat,_,_ in RULES if re.search(pat,clean,re.I|re.S)})
 return clean,removed,residual

class SessionStore:
 def __init__(self):
  self.db='sentinelgate_sessions.sqlite3';self.redis=None
  if os.getenv('REDIS_URL'):
   try:
    import redis; self.redis=redis.from_url(os.environ['REDIS_URL'],socket_connect_timeout=.1);self.redis.ping()
   except Exception:self.redis=None
 def record(self,sid,text,hits):
  key='sentinelgate:session:'+(sid or 'anonymous');score=bool(re.search(r'ignore|bypass|reveal|secret|system|tool',text,re.I));item={'s':score,'h':hits}
  if self.redis:
   self.redis.rpush(key,json.dumps(item));self.redis.ltrim(key,-12,-1);self.redis.expire(key,3600);seq=[json.loads(x) for x in self.redis.lrange(key,-3,-1)]
  else:
   with closing(sqlite3.connect(self.db,timeout=10)) as c:
    c.execute('CREATE TABLE IF NOT EXISTS session_events (id INTEGER PRIMARY KEY AUTOINCREMENT, session TEXT NOT NULL, suspicious INT NOT NULL, hits INT NOT NULL)')
    c.execute('BEGIN IMMEDIATE')
    c.execute('INSERT INTO session_events (session,suspicious,hits) VALUES (?,?,?)',(key,int(score),hits))
    c.execute('DELETE FROM session_events WHERE session=? AND id NOT IN (SELECT id FROM session_events WHERE session=? ORDER BY id DESC LIMIT 12)',(key,key))
    seq=[{'s':bool(x[0]),'h':x[1]} for x in c.execute('SELECT suspicious,hits FROM session_events WHERE session=? ORDER BY id DESC LIMIT 3',(key,)).fetchall()]
    c.commit()
  return len(seq)>=2 and sum(x['s'] for x in seq)>=2 and sum(x['h'] for x in seq)>0
class LegacyAudit:
 def __init__(self):
  self.db='sentinelgate_audit.sqlite3'
  with sqlite3.connect(self.db) as c:
   c.execute('CREATE TABLE IF NOT EXISTS audit (id TEXT, created REAL, session TEXT, source TEXT, verdict TEXT, risk INT, latency REAL, categories TEXT)')
   columns={x[1] for x in c.execute('PRAGMA table_info(audit)')}
   for name,definition in [('sanitized','INT DEFAULT 0'),('tool_decision',"TEXT DEFAULT '—'"),('canary_incident','INT DEFAULT 0'),('policy_version',"TEXT DEFAULT 'SG-2026.09'")]:
    if name not in columns:c.execute(f'ALTER TABLE audit ADD COLUMN {name} {definition}')
 def write(self,r,s):
  with sqlite3.connect(self.db) as c:c.execute('INSERT INTO audit (id,created,session,source,verdict,risk,latency,categories,sanitized,tool_decision,canary_incident,policy_version) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)',(r['request_id'],time.time(),s,r['provenance']['source'],r['verdict'],r['risk'],r['latency_ms'],','.join(x['attack'] for x in r['findings']),int(bool(r.get('neutralization'))),'—',0,r.get('policy_version','SG-2026.09')))
 def write_event(self,session,source,verdict,categories,tool='—',canary=False):
  with sqlite3.connect(self.db) as c:c.execute('INSERT INTO audit (id,created,session,source,verdict,risk,latency,categories,sanitized,tool_decision,canary_incident,policy_version) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)',(str(uuid.uuid4()),time.time(),session,source,verdict,100 if verdict=='BLOCK' else 0,0,categories,0,tool,int(canary),'SG-2026.09'))
 def recent(self):
  with sqlite3.connect(self.db) as c:return [{'id':x[0],'time':time.strftime('%H:%M:%S',time.localtime(x[1])),'session':x[2],'source':x[3],'verdict':x[4],'risk':x[5],'latency_ms':x[6],'categories':x[7],'sanitized':bool(x[8]),'tool_decision':x[9],'canary_incident':bool(x[10]),'policy_version':x[11]} for x in c.execute('SELECT id,created,session,source,verdict,risk,latency,categories,sanitized,tool_decision,canary_incident,policy_version FROM audit ORDER BY created DESC LIMIT 30')]

class Audit:
 """Append-only, hash-chained security evidence ledger."""
 FIELDS=('id','created','session','source','verdict','risk','latency','categories','sanitized','tool_decision','canary_incident','policy_version')
 def __init__(self):
  self.db='sentinelgate_audit.sqlite3'
  with closing(sqlite3.connect(self.db)) as c:
   c.execute('CREATE TABLE IF NOT EXISTS audit (id TEXT, created REAL, session TEXT, source TEXT, verdict TEXT, risk INT, latency REAL, categories TEXT)')
   columns={x[1] for x in c.execute('PRAGMA table_info(audit)')}
   for name,definition in [('sanitized','INT DEFAULT 0'),('tool_decision',"TEXT DEFAULT '—'"),('canary_incident','INT DEFAULT 0'),('policy_version',"TEXT DEFAULT 'SG-2026.10'"),('prev_hash',"TEXT DEFAULT ''"),('event_hash',"TEXT DEFAULT ''")]:
    if name not in columns:c.execute(f'ALTER TABLE audit ADD COLUMN {name} {definition}')
   sealed=c.execute("SELECT COUNT(*) FROM audit WHERE event_hash IS NOT NULL AND event_hash != ''").fetchone()[0]
   if not sealed:
    prev='GENESIS'
    for row in c.execute(f"SELECT rowid,{','.join(self.FIELDS)} FROM audit ORDER BY rowid").fetchall():
     digest=self._digest(row[1:],prev);c.execute('UPDATE audit SET prev_hash=?,event_hash=? WHERE rowid=?',(prev,digest,row[0]));prev=digest
   c.commit()
 @staticmethod
 def _digest(values,prev):
  values=list(values);values[1]=float(values[1]);values[5]=int(values[5]);values[6]=float(values[6]);values[8]=int(values[8]);values[10]=int(values[10]);body=json.dumps(values,ensure_ascii=False,separators=(',',':'))
  return hashlib.sha256((prev+'|'+body).encode('utf-8')).hexdigest()
 def _append(self,values):
  with closing(sqlite3.connect(self.db,timeout=10)) as c:
   c.execute('BEGIN IMMEDIATE');last=c.execute("SELECT event_hash FROM audit WHERE event_hash != '' ORDER BY rowid DESC LIMIT 1").fetchone();prev=last[0] if last else 'GENESIS';digest=self._digest(values,prev)
   marks=','.join('?' for _ in range(len(self.FIELDS)+2));c.execute(f"INSERT INTO audit ({','.join(self.FIELDS)},prev_hash,event_hash) VALUES ({marks})",tuple(values)+(prev,digest))
   c.commit()
 def write(self,r,s):
  self._append((r['request_id'],time.time(),s,r['provenance']['source'],r['verdict'],r['risk'],r['latency_ms'],','.join(x['attack'] for x in r['findings']),int(bool(r.get('neutralization'))),'—',0,r.get('policy_version','SG-2026.10')))
 def write_event(self,session,source,verdict,categories,tool='—',canary=False):
  self._append((str(uuid.uuid4()),time.time(),session,source,verdict,100 if verdict=='BLOCK' else 0,0,categories,0,tool,int(canary),'SG-2026.10'))
 def recent(self):
  with closing(sqlite3.connect(self.db)) as c:return [{'id':x[0],'time':time.strftime('%H:%M:%S',time.localtime(x[1])),'session':x[2],'source':x[3],'verdict':x[4],'risk':x[5],'latency_ms':x[6],'categories':x[7],'sanitized':bool(x[8]),'tool_decision':x[9],'canary_incident':bool(x[10]),'policy_version':x[11],'event_hash':x[12][:12]} for x in c.execute('SELECT id,created,session,source,verdict,risk,latency,categories,sanitized,tool_decision,canary_incident,policy_version,event_hash FROM audit ORDER BY rowid DESC LIMIT 30')]
 def verify(self):
  with closing(sqlite3.connect(self.db)) as c:rows=c.execute(f"SELECT {','.join(self.FIELDS)},prev_hash,event_hash FROM audit ORDER BY rowid").fetchall()
  prev='GENESIS';failures=[]
  for index,row in enumerate(rows,1):
   expected=self._digest(row[:len(self.FIELDS)],prev)
   if row[-2]!=prev or row[-1]!=expected:failures.append(index)
   prev=row[-1] or prev
  return {'valid':not failures,'events':len(rows),'failures':failures[:10],'chain_head':prev if rows else None,'algorithm':'SHA-256 hash chain'}
 def summary(self):
  with closing(sqlite3.connect(self.db)) as c:rows=c.execute('SELECT verdict,latency,categories FROM audit').fetchall()
  lat=sorted(float(x[1] or 0) for x in rows);n=len(rows);counts={v:sum(x[0]==v for x in rows) for v in ('ALLOW','QUARANTINE','BLOCK')};cats={}
  for row in rows:
   for cat in filter(None,(row[2] or '').split(',')):cats[cat]=cats.get(cat,0)+1
  return {'total':n,**counts,'p50_ms':lat[n//2] if n else 0,'p95_ms':lat[max(0,int(n*.95)-1)] if n else 0,'attack_distribution':cats,'feedback_pending':0}
def inspect(text,source,trusted,session_id):
 start=time.perf_counter();text,decodes=normalize(text);fs=[]
 for attack,severity,pat,conf,rule in RULES:
  m=re.search(pat,text,re.I|re.S)
  if m:fs.append(Finding(attack,severity,conf,excerpt(text,m.start(),m.end()),rule))
 semantic=semantic_classify(text)
 if semantic['score']>=.28 and not any(f.attack==semantic['category'] for f in fs):fs.append(Finding(semantic['category'],'high',round(semantic['score']*100), 'Semantic similarity to known '+semantic['category']+' attack pattern.','semantic-cosine'))
 anchor=IntentContracts().assess(session_id,text)
 if anchor['violation']:fs.append(Finding('Context Poisoning','critical',round(anchor['drift']*100),'Input conflicts with immutable session intent contract.','intent-anchor'))
 if source!='User message' and any(f.attack in {'Instruction Override','Secret Extraction','Tool Abuse'} for f in fs):fs.append(Finding('Indirect Prompt Injection','critical',95,'Action instruction appeared in untrusted external content.','provenance-escalation'))
 if SessionStore().record(session_id,text,len(fs)):fs.append(Finding('Multi-Step Jailbreak','high',86,'Session shows escalating instruction/authority language across turns.','session-drift'))
 fs=list({(f.attack,f.rule):f for f in fs}.values());crit=sum(f.severity=='critical' for f in fs);high=sum(f.severity=='high' for f in fs);risk=min(100,crit*38+high*18+len(fs)*3+(0 if trusted else 4));verdict='BLOCK' if crit or risk>=55 else 'QUARANTINE' if fs else 'ALLOW';clean,removed,residual=sanitize_text(text,fs)
 coverage=[]
 for category,_,_,_,_ in RULES:
  hits=[f for f in fs if f.attack==category];coverage.append({'attack':category,'detected':bool(hits),'confidence':max([f.confidence for f in hits] or [0]),'mechanism':', '.join(sorted({f.rule for f in hits})) or 'rules + semantic','evidence':hits[0].evidence if hits else 'No signal','action':'block/quarantine' if hits else 'pass'})
 layers={'normalization':'Passed','recursive_decoding':len(decodes),'signature_matches':sum(f.rule not in {'semantic-cosine','intent-anchor','session-drift','provenance-escalation'} for f in fs),'semantic_risk':semantic['score'],'intent_drift':anchor['drift'],'provenance_risk':'trusted' if trusted else 'external/untrusted','fused_risk':risk}
 r={'request_id':str(uuid.uuid4()),'verdict':verdict,'risk':risk,'findings':[asdict(f) for f in fs],'coverage':coverage,'layers':layers,'original':text[:12000],'sanitized':clean[:12000],'neutralization':removed,'rescan':{'passed':not residual,'residual_attacks':residual},'route':'Human security review' if verdict=='BLOCK' else 'Read-only agent context' if verdict=='QUARANTINE' else 'Agent context (data only)','provenance':{'source':source,'trust':'trusted' if trusted else 'untrusted','content_mode':'data, never instructions'},'semantic':semantic,'intent_anchor':{'anchored':anchor['anchored'],'drift':anchor['drift']},'decode_layers':len(decodes),'latency_ms':round((time.perf_counter()-start)*1000,2),'policy_version':'SG-2026.10','model_version':'semantic-baseline-1','content_fingerprint':content_fingerprint(text)}
 signed={'request_id':r['request_id'],'verdict':r['verdict'],'risk':r['risk'],'content_fingerprint':r['content_fingerprint'],'policy_version':r['policy_version']};signer=DecisionSigner();r['decision_signature']=signer.sign(signed);r['signing_key_id']=signer.key_id;Audit().write(r,session_id);return r

def evaluate_tool(d):
 schemas={'search_knowledge':(set(),set()),'get_customer':({'customer_id'},{'customer_id'}),'send_email':({'to','subject','body'},{'to','subject','body'}),'create_ticket':({'title','priority'},{'title','priority'})};tool=d.get('tool');args=d.get('arguments',{});dest=args.get('url') or args.get('to','') if isinstance(args,dict) else ''
 allowed_fields,required_fields=schemas.get(tool,(set(),set()));schema_valid=tool in schemas and isinstance(args,dict) and set(args).issubset(allowed_fields) and required_fields.issubset(args)
 if schema_valid and tool=='create_ticket':schema_valid=args.get('priority') in {'low','medium','high','critical'}
 contract=IntentContracts().get(d.get('session_id',''));intent_ok=not contract or tool in set(contract.get('allowed_actions',[]))
 serialized=json.dumps(args,ensure_ascii=False) if isinstance(args,dict) else str(args);payload_safe=not SECRET.search(serialized) and not any(re.search(pat,serialized,re.I|re.S) for _,_,pat,_,_ in RULES)
 checks={'user_authorized':bool(d.get('user_authorized')),'allowlisted':tool in schemas,'schema_valid':schema_valid,'destination_allowed':not dest or ('@' not in str(dest) or str(dest).lower().endswith('@company.example')),'intent_compatible':intent_ok,'payload_safe':payload_safe}
 policy_passed=all(checks.values());high_risk=tool in {'send_email'}
 decision='APPROVE' if policy_passed and not high_risk else 'REQUIRE_CONFIRMATION' if policy_passed else 'BLOCK';allowed=decision=='APPROVE'
 failed=[k.replace('_',' ') for k,v in checks.items() if not v];reason='All policy checks passed.' if not failed else 'Failed: '+', '.join(failed)+'.'
 if decision=='REQUIRE_CONFIRMATION':reason='Policy checks passed; explicit step-up confirmation is required before execution.'
 return {'allowed':allowed,'policy_passed':policy_passed,'confirmation_required':decision=='REQUIRE_CONFIRMATION','decision':decision,'reason':reason,'checks':checks,'tool':tool,'destination':dest or 'internal','risk_level':'HIGH' if high_risk else 'LOW','permission_source':'immutable session contract' if contract else 'default least-privilege policy'}

def build_context_envelope(text,source='User message',trusted=False,session_id='anonymous'):
 """Inspect content and create the only payload an agent may consume."""
 result=inspect(text,source,trusted,session_id);deliver=result['verdict']!='BLOCK' and result['rescan']['passed']
 envelope={'request_id':result['request_id'],'deliver':deliver,'mode':'read_only_untrusted_data' if result['verdict']=='QUARANTINE' else 'data_only','content':result['sanitized'] if deliver else '','instructions_allowed':False,'tool_capabilities':[],'source':source,'source_content_hash':result['content_fingerprint'],'policy_version':result['policy_version'],'verdict':result['verdict'],'risk':result['risk'],'finding_categories':[x['attack'] for x in result['findings']]}
 signer=DecisionSigner();signature=signer.sign(envelope)
 return {'delivered':deliver,'envelope':envelope,'signature':signature,'signing_key_id':signer.key_id,'inspection':result}
def guard_tool(d):
 r=evaluate_tool(d);return r['allowed'],r['reason']
def guard_output(text,session_id=''):
 leaked,canary=canary_check(text,session_id);types=[]
 if SECRET.search(text):types.append('credential/private key')
 out=SECRET.sub('[REDACTED SECRET]',text)
 pii=re.compile(r'\b[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}\b|\b(?:\+?\d[\d -]{8,}\d)\b')
 if pii.search(out):types.append('PII')
 out=pii.sub('[REDACTED PII]',out)
 if re.search(r'(?i)system prompt\s*[:=-]?',out):types.append('system prompt')
 out=re.sub(r'(?i)(system prompt\s*[:=-]?).{0,500}',r'\1 [REDACTED]',out)
 if leaked:out=out.replace(canary,'[REDACTED CANARY]')
 if leaked:types.append('honey-canary')
 return {'safe':out==text,'output':out,'redactions':len(types),'redaction_types':types,'canary_leak':leaked,'decision':'ALLOW' if out==text else 'BLOCK_AND_REDACT'}
