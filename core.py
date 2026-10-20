"""Reproducible Day 3 implementation; no live identity or LLM services."""
from __future__ import annotations
import os
os.environ.setdefault('MPLCONFIGDIR', '.cache/matplotlib')
os.environ.setdefault('HF_HOME', '.cache/huggingface')
os.environ.setdefault('TOKENIZERS_PARALLELISM', 'false')
import csv, hashlib, html, json, math, re, sqlite3, time, uuid
from pathlib import Path
from typing import Literal, TypedDict
import numpy as np
import pandas as pd
import httpx, jwt
from pydantic import BaseModel, ConfigDict, Field, ValidationError
from fastapi import FastAPI, Depends, Header, HTTPException, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline
from sklearn.metrics import accuracy_score, f1_score, confusion_matrix, balanced_accuracy_score
from pypdf import PdfReader
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
SEED = 20261015
ROOT = Path('.')
DATA = ROOT/'Day3/Day3_Datasets'
OUT = ROOT/'output'
OUT.mkdir(exist_ok=True)
DB = OUT/'day3.sqlite'
MODEL_MANIFEST = json.loads(Path('Day3/Day3_Resources/embedding_model_manifest.json').read_text())
MODEL_ID = MODEL_MANIFEST['model_id']
REVISION = MODEL_MANIFEST['revision']
MODEL_PATH = Path('Day3/Day3_Resources/embedding_model')
R = {}

def sha(raw): return hashlib.sha256(raw).hexdigest()
def fingerprint(obj): return sha(json.dumps(obj, sort_keys=True, ensure_ascii=False).encode())
def read_jsonl(path): return [json.loads(x) for x in Path(path).read_text().splitlines() if x.strip()]
def save_json(name, obj):
    (OUT/name).write_text(json.dumps(obj, ensure_ascii=False, indent=2, default=lambda x: x.item() if isinstance(x,np.generic) else str(x)))
def save_jsonl(name, rows):
    (OUT/name).write_text(''.join(json.dumps(x, ensure_ascii=False, default=lambda v: v.item() if isinstance(v,np.generic) else str(v))+'\n' for x in rows))
def result(q, **kw): R[q] = kw; return kw
def plot(name, title, values):
    plt.figure(figsize=(7,4)); plt.bar([str(x) for x in values],list(values.values())); plt.title(title); plt.tight_layout(); plt.savefig(OUT/name); plt.close()

def connect(path=DB):
    con=sqlite3.connect(path,timeout=3,check_same_thread=False); con.row_factory=sqlite3.Row
    con.execute('PRAGMA foreign_keys=ON'); return con
SCHEMA = '''
CREATE TABLE IF NOT EXISTS users(user_id TEXT PRIMARY KEY,role TEXT NOT NULL,tenant TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS cases(case_id TEXT PRIMARY KEY,owner_id TEXT NOT NULL REFERENCES users(user_id),topic TEXT NOT NULL,summary TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS idx_cases_owner ON cases(owner_id);
CREATE TABLE IF NOT EXISTS sessions(session_id TEXT PRIMARY KEY,owner_id TEXT NOT NULL REFERENCES users(user_id),case_id TEXT NOT NULL REFERENCES cases(case_id),idempotency_key TEXT NOT NULL UNIQUE);
CREATE TABLE IF NOT EXISTS messages(message_id TEXT PRIMARY KEY,session_id TEXT NOT NULL REFERENCES sessions(session_id),content TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS documents(doc_id TEXT PRIMARY KEY,version TEXT NOT NULL,content_hash TEXT NOT NULL,title TEXT,source_url TEXT,access TEXT,tenant TEXT,archived INTEGER DEFAULT 0);
CREATE TABLE IF NOT EXISTS chunks(chunk_id TEXT PRIMARY KEY,doc_id TEXT NOT NULL REFERENCES documents(doc_id),content TEXT NOT NULL,embedding BLOB,model_id TEXT,model_revision TEXT,start INTEGER,end INTEGER,section TEXT,content_hash TEXT);
'''
def migrate_seed(path=DB):
    con=connect(path); con.executescript(SCHEMA)
    with con:
        for u in csv.DictReader((DATA/'03_Application/users.csv').open()):
            con.execute('INSERT INTO users VALUES(?,?,?) ON CONFLICT(user_id) DO UPDATE SET role=excluded.role,tenant=excluded.tenant',(u['user_id'],u['role'],u['tenant']))
        for c in read_jsonl(DATA/'03_Application/cases.jsonl'):
            con.execute('INSERT INTO cases VALUES(?,?,?,?) ON CONFLICT(case_id) DO UPDATE SET owner_id=excluded.owner_id,topic=excluded.topic,summary=excluded.summary',tuple(c[k] for k in ['case_id','owner_id','topic','summary']))
    con.close()

class SQLiteAdapter:
    def __init__(self,path=DB): self.path=path
    def user(self,uid):
        with connect(self.path) as c: row=c.execute('SELECT * FROM users WHERE user_id=?',(uid,)).fetchone()
        if not row: raise HTTPException(401,'Identity required')
        return dict(row)
    def case(self,cid,uid):
        u=self.user(uid)
        with connect(self.path) as c: row=c.execute('SELECT * FROM cases WHERE case_id=?',(cid,)).fetchone()
        if not row: raise HTTPException(404,'Case not found')
        if row['owner_id']!=uid and u['role']!='admin': raise HTTPException(403,'Access denied')
        return dict(row)
    def cases(self,uid,limit=3,offset=0):
        u=self.user(uid)
        with connect(self.path) as c:
            rows=c.execute('SELECT * FROM cases WHERE owner_id=? ORDER BY case_id LIMIT ? OFFSET ?',(uid,limit,offset)).fetchall()
        return [dict(x) for x in rows]
    def session(self,uid,cid,key):
        self.case(cid,uid)
        with connect(self.path) as c:
            c.execute('BEGIN IMMEDIATE')
            old=c.execute('SELECT * FROM sessions WHERE idempotency_key=?',(key,)).fetchone()
            if old:
                if old['owner_id']!=uid or old['case_id']!=cid: raise HTTPException(409,'Idempotency conflict')
                return dict(old)
            sid='S-'+uuid.uuid4().hex
            c.execute('INSERT INTO sessions VALUES(?,?,?,?)',(sid,uid,cid,key))
            return dict(session_id=sid,owner_id=uid,case_id=cid,idempotency_key=key)
    def history(self,uid,cid):
        case=self.case(cid,uid)
        with connect(self.path) as c:
            rows=c.execute('SELECT m.content FROM messages m JOIN sessions s ON s.session_id=m.session_id WHERE s.case_id=? ORDER BY m.message_id',(cid,)).fetchall()
        return [{'kind':'private_case','case_id':cid,'text':case['summary']}]+[{'kind':'private_message','text':x['content']} for x in rows]

class SearchInput(BaseModel):
    model_config=ConfigDict(extra='forbid')
    query:str=Field(min_length=3,max_length=1000)
    top_k:int=Field(default=3,ge=1,le=10)
    method:Literal['lexical','dense','hybrid']='lexical'
class SessionInput(BaseModel):
    model_config=ConfigDict(extra='forbid')
    case_id:str
class AnswerInput(SearchInput): case_id:str
class Claim(BaseModel):
    model_config=ConfigDict(extra='forbid')
    text:str
    citation_ids:list[str]
    quote:str
class Answer(BaseModel):
    model_config=ConfigDict(extra='forbid')
    mode:Literal['general','rag','both']
    claims:list[Claim]
    message:str=''

def make_app(adapter,graph=None):
    app=FastAPI()
    @app.middleware('http')
    async def correlation(req,call_next):
        req.state.correlation_id=uuid.uuid4().hex
        res=await call_next(req); res.headers['X-Correlation-ID']=req.state.correlation_id; return res
    @app.exception_handler(HTTPException)
    async def http_error(req,err):
        return JSONResponse(status_code=err.status_code,content={'code':f'HTTP_{err.status_code}','message':str(err.detail),'correlation_id':req.state.correlation_id})
    @app.exception_handler(RequestValidationError)
    async def invalid(req,err):
        return JSONResponse(status_code=422,content={'code':'VALIDATION_ERROR','message':'Invalid request schema','correlation_id':req.state.correlation_id})
    def identity(x_user_id:str|None=Header(default=None)):
        if not x_user_id: raise HTTPException(401,'Identity required')
        return adapter.user(x_user_id)['user_id']
    @app.get('/health')
    def health():
        with connect(adapter.path) as c: ok=c.execute('SELECT 1').fetchone()[0]==1
        return {'status':'ok' if ok else 'error','engine':'SQLite'}
    @app.get('/cases')
    def cases(uid=Depends(identity),limit:int=Query(3,ge=1,le=10),offset:int=Query(0,ge=0)):
        return adapter.cases(uid,limit,offset)
    @app.get('/cases/{cid}')
    def case(cid:str,uid=Depends(identity)): return adapter.case(cid,uid)
    @app.post('/sessions',status_code=201)
    def session(body:SessionInput,uid=Depends(identity),idempotency_key:str=Header(min_length=1,max_length=200)):
        return adapter.session(uid,body.case_id,idempotency_key)
    @app.post('/search')
    def search(body:SearchInput,uid=Depends(identity)): return {'query':body.query,'method':body.method,'top_k':body.top_k}
    @app.post('/answer')
    def answer(body:AnswerInput,req:Request,uid=Depends(identity)):
        adapter.case(body.case_id,uid)
        if graph is None: raise HTTPException(503,'Graph unavailable')
        state=graph.invoke(initial_state(body.query,uid,body.case_id,req.state.correlation_id))
        if state.get('denied'): raise HTTPException(403,'Access denied')
        return {'correlation_id':req.state.correlation_id,'claims':state['answer']['claims'],'answer':state['answer'],'trace':state['trace']}
    return app

def retry_fixture(scenario,max_attempts=3,deadline=10):
    statuses=scenario['statuses']; waits=[]; attempts=0; elapsed=0
    for i in range(max_attempts):
        status=statuses[min(i,len(statuses)-1)]; attempts+=1
        if 200<=status<300: return dict(success=True,attempts=attempts,waits=waits,status=status)
        if status!=429 and not 500<=status<600: break
        delay=float(scenario.get('retry_after',2**i))
        if i+1==max_attempts or elapsed+delay>=deadline: break
        waits.append(delay); elapsed+=delay
    return dict(success=False,attempts=attempts,waits=waits,status=status)

def redact(x):
    if isinstance(x,dict): return {k:('[REDACTED]' if re.search(r'(secret|token|password|api.?key|authorization)',k,re.I) else redact(v)) for k,v in x.items()}
    if isinstance(x,list): return [redact(v) for v in x]
    if isinstance(x,str): return x.replace('TEST-ONLY-SECRET','[REDACTED]')
    return x

def load_documents():
    docs=[]
    for m in csv.DictReader((DATA/'01_Corpus/manifest.csv').open()):
        raw=(DATA/'01_Corpus'/m['path']).read_bytes()
        assert sha(raw)==m['sha256'],m['doc_id']
        text=raw.decode('utf-8')
        # Keep raw newlines; offsets refer to this exact decoded source.
        sections=[]
        for match in re.finditer(r'(?m)^([^\r\n]+)\r?\n([=~\-^"`:#*+])\2{2,}\r?$',text):
            sections.append({'title':match.group(1),'start':match.start()})
        docs.append({**m,'text':text,'sections':sections,'archived':False})
    return docs

def split_doc(doc,tokenizer,size=220,overlap=40):
    encoded=tokenizer(doc['text'],add_special_tokens=False,return_offsets_mapping=True,truncation=False)
    offsets=encoded['offset_mapping']; chunks=[]
    i=0
    while i<len(offsets):
        start=offsets[i][0]; j=min(i+size,len(offsets))
        end=offsets[j-1][1]; text=doc['text'][start:end]
        # Re-tokenization may differ when a window starts inside a WordPiece word.
        while len(tokenizer.encode(text,add_special_tokens=False))>size and j>i+1:
            j-=1;end=offsets[j-1][1];text=doc['text'][start:end]
        section=next((s['title'] for s in reversed(doc.get('sections',[])) if s['start']<=start),doc['title'])
        cid=fingerprint([doc['doc_id'],doc['version'],start,end,sha(text.encode())])
        chunks.append(dict(chunk_id=cid,doc_id=doc['doc_id'],version=doc['version'],start=start,end=end,content=text,content_hash=sha(text.encode()),section=section,access=doc['access'],tenant=doc['tenant'],archived=doc.get('archived',False),tokens=len(tokenizer.encode(text,add_special_tokens=False))))
        if j>=len(offsets): break
        i=max(i+1,j-overlap)
    return chunks

def policy_documents():
    return [{**d,'sections':[],'archived':d['doc_id']=='LAB-OLD','sha256':sha(d['text'].encode()),'source_url':'fixture://'+d['doc_id']} for d in read_jsonl(DATA/'03_Application/policies.jsonl')]

def store_documents(docs):
    with connect() as con:
        for d in docs:
            con.execute('INSERT INTO documents VALUES(?,?,?,?,?,?,?,?) ON CONFLICT(doc_id) DO UPDATE SET version=excluded.version,content_hash=excluded.content_hash,title=excluded.title,source_url=excluded.source_url,access=excluded.access,tenant=excluded.tenant,archived=excluded.archived',tuple(d[k] for k in ['doc_id','version','sha256','title','source_url','access','tenant','archived']))

def store_chunks(chunks,vectors=None):
    with connect() as con:
        for i,c in enumerate(chunks):
            vec=None if vectors is None else np.asarray(vectors[i],dtype='<f4').tobytes()
            con.execute('INSERT INTO chunks VALUES(?,?,?,?,?,?,?,?,?,?) ON CONFLICT(chunk_id) DO UPDATE SET embedding=COALESCE(excluded.embedding,chunks.embedding),model_id=excluded.model_id,model_revision=excluded.model_revision',
                (c['chunk_id'],c['doc_id'],c['content'],vec,MODEL_ID,REVISION,c['start'],c['end'],c['section'],c['content_hash']))

def verify_model():
    checks=[]
    for f in MODEL_MANIFEST['files']:
        p=MODEL_PATH/f['path']; ok=p.exists() and p.stat().st_size==f['bytes'] and sha(p.read_bytes())==f['sha256']
        checks.append({'file':f['path'],'passed':ok})
    if not all(x['passed'] for x in checks): raise RuntimeError('Model absent or checksum mismatch: '+','.join(x['file'] for x in checks if not x['passed']))
    return checks

def load_encoder():
    verify_model()
    from sentence_transformers import SentenceTransformer
    import torch
    torch.set_num_threads(4)
    return SentenceTransformer(str(MODEL_PATH),local_files_only=True,device='cpu')

class Retrieval:
    def __init__(self,chunks,encoder):
        self.chunks=chunks; self.encoder=encoder
        self.vectorizer=TfidfVectorizer(ngram_range=(1,2),sublinear_tf=True)
        self.lex=self.vectorizer.fit_transform([c['content'] for c in chunks])
        started=time.perf_counter()
        self.vectors=encoder.encode([c['content'] for c in chunks],batch_size=32,normalize_embeddings=True,show_progress_bar=False).astype(np.float32)
        self.encode_seconds=time.perf_counter()-started; self.cache={}
    def query_vector(self,q):
        if q not in self.cache: self.cache[q]=self.encoder.encode([q],normalize_embeddings=True,show_progress_bar=False)[0]
        return self.cache[q]
    def scores(self,q,method):
        if method=='lexical': return (self.lex@self.vectorizer.transform([q]).T).toarray().ravel()
        if method=='dense': return self.vectors@self.query_vector(q)
        raise ValueError(method)
    def ranked(self,q,method='lexical',user=None,k=3,documents=True):
        allowed=np.array([not c['archived'] and (c['access']=='public' or user is not None and (user['role']=='admin' or user['tenant']==c['tenant'])) for c in self.chunks])
        ids=np.flatnonzero(allowed)
        if method=='hybrid':
            scores=np.zeros(len(self.chunks))
            for m in ['lexical','dense']:
                sc=self.scores(q,m); order=ids[np.argsort(-sc[ids],kind='stable')]
                for rank,i in enumerate(order,1): scores[i]+=1/(60+rank)
        else: scores=self.scores(q,method)
        order=ids[np.argsort(-scores[ids],kind='stable')]; out=[]; seen=set()
        for i in order:
            c=self.chunks[i]
            if documents and c['doc_id'] in seen: continue
            seen.add(c['doc_id']); out.append({**c,'score':float(scores[i]),'index':int(i)})
            if len(out)>=k: break
        return out

def retrieval_metrics(gold,ranked,k=3):
    ranked=list(dict.fromkeys(ranked))[:k]; gold=set(gold)
    if not gold: raise ValueError('Answerability is measured separately')
    hits=[1 if x in gold else 0 for x in ranked]
    recall=sum(hits)/len(gold)
    mrr=next((1/(i+1) for i,h in enumerate(hits) if h),0)
    dcg=sum(h/math.log2(i+2) for i,h in enumerate(hits)); ideal=sum(1/math.log2(i+2) for i in range(min(k,len(gold))))
    return dict(recall=recall,mrr=mrr,ndcg=dcg/ideal)

def evaluate(index,rows,method,k=3):
    scores=[retrieval_metrics(r['relevant_doc_ids'],[c['doc_id'] for c in index.ranked(r['query'],method,k=k)],k) for r in rows if r['answerable']]
    return {key:float(np.mean([s[key] for s in scores])) for key in ['recall','mrr','ndcg']}

def context_budget(chunks,tokenizer,budget=700):
    kept=[]; skipped=[]; total=0
    for c in chunks:
        n=len(tokenizer.encode(c['content'],add_special_tokens=False))
        if total+n<=budget: kept.append(c); total+=n
        else: skipped.append(c['chunk_id'])
    return kept,skipped,total

def citation_validate(candidate,evidence,extractive=False):
    try:
        claims=candidate['claims']; parsed=[Claim.model_validate(c) for c in claims]
    except (KeyError,ValidationError): return False,'schema'
    if not claims: return False,'no_claims'
    context={c['chunk_id']:c for c in evidence}
    for c in parsed:
        if not c.citation_ids: return False,'missing_citation'
        if any(i not in context for i in c.citation_ids): return False,'unknown_id'
        if not c.quote.strip() or any(c.quote not in context[i]['content'] for i in c.citation_ids): return False,'quote_not_found'
        if extractive and c.text!=c.quote: return False,'claim_quote_mismatch'
    return True,'valid'

def rules(q):
    q=q.lower()
    # Designed from the train templates only.
    if re.search(r'password|delete|secrets|make up|all tenants|bypass|invent|credentials',q):return 'unsupported'
    private=bool(re.search(r'case|history|recorded|logged|local',q))
    public=bool(re.search(r'pep|public|source|evidence|specification|design proposal|corpus|research|published',q))
    return 'both' if private and public else 'history' if private else 'research' if public else 'unsupported'

class FlowState(TypedDict,total=False):
    query:str; user:str; case:str; route:str; evidence:list; history:list; answer:dict; trace:list; correlation_id:str; denied:bool

def initial_state(query,user,case,correlation_id=None):
    return FlowState(query=query,user=user,case=case,route='',evidence=[],history=[],answer={},trace=[],correlation_id=correlation_id or uuid.uuid4().hex,denied=False)

def make_graph(adapter,index,route_fn):
    from langgraph.graph import StateGraph,START,END
    def traced(state,event,**updates):
        ev={'event_type':event,'correlation_id':state['correlation_id'],'metadata':{'route':updates.get('route',state.get('route',''))}}
        return {**updates,'trace':state['trace']+[redact(ev)]}
    def authorize(s):
        try: adapter.case(s['case'],s['user']); return traced(s,'authorize',denied=False)
        except HTTPException: return traced(s,'deny',denied=True,route='deny',evidence=[],history=[],answer={'mode':'general','claims':[],'message':'Access denied'})
    def route(s): return traced(s,'route',route=route_fn(s['query']))
    def history(s): return traced(s,'history',history=adapter.history(s['user'],s['case']))
    def research(s):
        adapter.case(s['case'],s['user'])
        ev=index.ranked(s['query'],'dense',user=adapter.user(s['user']),k=3,documents=False)
        return traced(s,'research',evidence=ev)
    def generate(s):
        claims=[]
        for c in s['evidence'][:1]:
            # Pure extraction; no instruction execution and no tool/secret parameter.
            quote=c['content']; claims.append({'text':quote,'quote':quote,'citation_ids':[c['chunk_id']]})
        mode='both' if s['route']=='both' else 'rag' if claims else 'general'
        message='Extractive baseline cannot produce free-form general answers.' if not claims else 'Extracted public/authorized research. Private case facts are separate.'
        return traced(s,'generate',answer=Answer(mode=mode,claims=claims,message=message).model_dump())
    def validate(s):
        ok,reason=citation_validate(s['answer'],s['evidence'],True) if s['answer']['claims'] else (True,'controlled_no_claims')
        if not ok: raise ValueError(reason)
        return traced(s,'validate')
    g=StateGraph(FlowState)
    for name,fn in [('authorize',authorize),('route',route),('history',history),('research',research),('generate',generate),('validate',validate)]:g.add_node(name,fn)
    g.add_edge(START,'authorize');g.add_conditional_edges('authorize',lambda s:'deny' if s['denied'] else 'allow',{'deny':END,'allow':'route'})
    g.add_conditional_edges('route',lambda s:s['route'],{'history':'history','both':'history','research':'research','clarify':'generate','unsupported':'generate'})
    g.add_conditional_edges('history',lambda s:'research' if s['route']=='both' else 'generate',{'research':'research','generate':'generate'})
    g.add_edge('research','generate');g.add_edge('generate','validate');g.add_edge('validate',END)
    return g.compile()

def cache_key(query,user,tenant,model,corpus,prompt_version):return fingerprint(dict(query=query,user=user,tenant=tenant,model=model,corpus=corpus,prompt_version=prompt_version))
