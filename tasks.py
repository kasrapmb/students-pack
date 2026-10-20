"""Code cells: each entry implements the corresponding assignment question."""
TASKS = {}
def task(q,source): TASKS[q]=source.strip()
task('5.1', '''
logs=pd.read_csv(DATA/'04_API/request_logs.csv')
result('5.1',requests=len(logs),duplicate_ids=int(logs.request_id.duplicated().sum()),http_error_rate=float((logs.status>=400).mean()),synthetic=bool(logs.synthetic.all()))
''')
task('5.2', '''
status_counts=logs.status.value_counts().sort_index()
plot('api_status.png','Synthetic HTTP status counts',status_counts.to_dict())
result('5.2',retryable=int(((logs.status==429)|(logs.status>=500)).sum()),request_correction=int(logs.status.between(400,428).sum()),counts=status_counts.to_dict())
''')
task('5.3', '''
bad_inputs=[{'query':'ab'},{'query':'valid','top_k':11},{'query':'valid','unexpected':True}]
rejected=0
for body in bad_inputs:
    try: SearchInput.model_validate(body)
    except ValidationError: rejected+=1
assert rejected==3
for body in [{'query':'valid','method':'unknown'},{'query':'x'*1001}]:
    try: SearchInput.model_validate(body); raise AssertionError('accepted invalid')
    except ValidationError: pass
result('5.3',rejected_of_three=rejected,additional_invalid_method_and_length_rejected=True)
''')
task('5.4', '''
migrate_seed(); adapter=SQLiteAdapter(); client=TestClient(make_app(adapter)); auth={'X-User-ID':'U-002'}
collected=[]; offset=0
while True:
    response=client.get('/cases',params={'limit':3,'offset':offset},headers=auth)
    assert response.status_code==200
    rows=response.json()
    if not rows: break
    collected.extend(c['case_id'] for c in rows); offset+=len(rows)
assert len(collected)==len(set(collected))
result('5.4',collected=len(collected),unique=len(set(collected)),case_ids=collected)
''')
task('5.5', '''
scenarios=[('missing_identity','/cases/C-001',{}),('wrong_owner','/cases/C-002',auth),('missing_id','/cases/C-999',auth),('invalid_pagination','/cases?limit=11',auth)]
statuses={name:client.get(url,headers=headers).status_code for name,url,headers in scenarios}
assert list(statuses.values())==[401,403,404,422]
result('5.5',statuses=statuses)
''')
task('5.6', '''
retry_runs={r['scenario']:retry_fixture(r) for r in read_jsonl(DATA/'04_API/retry_scenarios.jsonl')}
assert retry_runs['unauthorized']['attempts']==1
result('5.6',successful=sum(r['success'] for r in retry_runs.values()),attempts_401=retry_runs['unauthorized']['attempts'],scenarios=retry_runs)
''')
task('5.7', '''
h={**auth,'Idempotency-Key':'section5-session'}
a=client.post('/sessions',json={'case_id':'C-001'},headers=h)
b=client.post('/sessions',json={'case_id':'C-001'},headers=h)
c=client.post('/sessions',json={'case_id':'C-020'},headers=h)
assert a.status_code==b.status_code==201 and a.json()['session_id']==b.json()['session_id'] and c.status_code==409
result('5.7',same_session=True,conflict=c.status_code)
''')
task('5.8', '''
r=retry_fixture({'statuses':[503]*4})
assert r['attempts']==3 and not r['success']
result('5.8',attempts=r['attempts'],total_backoff_seconds=sum(r['waits']),waits=r['waits'])
''')
task('5.9', '''
def timeout_transport(request): raise httpx.ReadTimeout('Synthetic read timeout',request=request)
with httpx.Client(transport=httpx.MockTransport(timeout_transport),timeout=httpx.Timeout(5,connect=2)) as timeout_client:
    try: timeout_client.get('https://fixture.invalid/v1/answers'); raise AssertionError('timeout missing')
    except httpx.ReadTimeout: timeout_result={'code':'READ_TIMEOUT','message':'Provider response exceeded the read timeout','success':False}
result('5.9',handled=True,envelope=timeout_result)
''')
task('5.10', '''
prices=json.loads((DATA/'04_API/provider_config.json').read_text())
logs['input_cost']=[t*prices[p]['input']/1e6 for t,p in zip(logs.input_tokens,logs.provider)]
logs['output_cost']=[t*prices[p]['output']/1e6 for t,p in zip(logs.output_tokens,logs.provider)]
logs['total_cost']=logs.input_cost+logs.output_cost
logs.to_csv(OUT/'request_costs.csv',index=False)
result('5.10',total_USD=float(logs.total_cost.sum()),per_provider=logs.groupby('provider')[['input_cost','output_cost','total_cost']].sum().to_dict('index'),pricing='fictional USD per million tokens; all logged rows counted, not proof of provider billing')
''')
task('5.11', '''
class Provider:
    def __init__(self,base_url,model_id,transport): self.client=httpx.Client(base_url=base_url,transport=transport); self.model_id=model_id
    def answer(self,query): return self.client.post('/v1/answers',json={'model':self.model_id,'input':query})
seen=[]
def provider_transport(request):
    body=json.loads(request.content); assert body['input']=='Test question'; seen.append({'host':request.url.host,'path':request.url.path,'model':body['model']})
    return httpx.Response(200,json={'output':'fixture only'})
for host,model in [('provider-a.invalid','model-a'),('provider-b.invalid','model-b')]:
    provider=Provider('https://'+host,model,httpx.MockTransport(provider_transport))
    assert provider.answer('Test question').status_code==200; provider.client.close()
result('5.11',configurations=len(seen),live_LLM_calls=0,contracts=seen)
''')
task('5.12', '''
errors=[client.get('/cases/C-001'),client.post('/search',json={'query':'ab'},headers=auth)]
for response in errors:
    assert set(response.json())=={'code','message','correlation_id'}
    assert response.json()['correlation_id']==response.headers['X-Correlation-ID']
result('5.12',envelope_tests=len(errors),statuses=[r.status_code for r in errors])
''')
task('6.1', '''
with connect() as con:
    one=con.execute('SELECT 1').fetchone()[0]; version=con.execute('SELECT sqlite_version()').fetchone()[0]
    fk=con.execute('PRAGMA foreign_keys').fetchone()[0]
assert one==1 and fk==1
result('6.1',connected=True,sqlite_version=version,timeout_seconds=3,foreign_keys=bool(fk))
''')
task('6.2', '''
migrate_seed(); migrate_seed()
with connect() as con: counts={t:con.execute('SELECT count(*) FROM '+t).fetchone()[0] for t in ['users','cases']}
assert counts=={'users':20,'cases':120}
result('6.2',**counts,idempotent_seed=True,schema=SCHEMA)
''')
task('6.3', '''
with connect() as con:
    rejected=False
    try: con.execute('INSERT INTO cases VALUES(?,?,?,?)',('ORPHAN','MISSING','test','test'))
    except sqlite3.IntegrityError as e: rejected='FOREIGN KEY' in str(e); con.rollback()
    usable=con.execute('SELECT 1').fetchone()[0]==1
assert rejected and usable
result('6.3',orphan_rejected=rejected,connection_usable=usable)
''')
task('6.4', '''
with connect() as con:
    before=con.execute('SELECT count(*) FROM sessions').fetchone()[0]
    try:
        con.execute('BEGIN')
        con.execute('INSERT INTO sessions VALUES(?,?,?,?)',('ROLLBACK-S','U-002','C-001','rollback-probe'))
        con.execute('INSERT INTO messages VALUES(?,?,?)',('ROLLBACK-M','INVALID-S','test'))
        con.commit(); raise AssertionError('FK accepted')
    except sqlite3.IntegrityError: con.rollback()
    after=con.execute('SELECT count(*) FROM sessions').fetchone()[0]
assert before==after
result('6.4',before=before,after=after,atomic_rollback=before==after)
''')
task('6.5', '''
with connect() as con:
    attack="U-002' OR 1=1 --"
    matched=con.execute('SELECT count(*) FROM users WHERE user_id=?',(attack,)).fetchone()[0]
    count=con.execute('SELECT count(*) FROM users').fetchone()[0]
assert matched==0 and count==20
result('6.5',matched_rows=matched,users_after=count)
''')
task('6.6', '''
access={}
for uid in ['U-002','U-003','U-000']:
    try: adapter.case('C-001',uid); access[uid]=True
    except HTTPException as e: assert e.status_code==403; access[uid]=False
assert list(access.values())==[True,False,True]
result('6.6',access=access,engine='SQLite')
''')
task('6.7', '''
with connect() as con:
    indexes=[dict(x) for x in con.execute('PRAGMA index_list(cases)')]
    plan=[list(x) for x in con.execute('EXPLAIN QUERY PLAN SELECT * FROM cases WHERE owner_id=?',('U-002',))]
assert any(x['name']=='idx_cases_owner' for x in indexes)
result('6.7',owner_index=True,explain=plan)
''')
task('6.8', '''
store_documents(docs+policies); store_documents(docs+policies)
store_chunks(all_chunks,all_vectors)
with connect() as con: count=con.execute('SELECT count(*) FROM documents').fetchone()[0]
assert count==28
result('6.8',documents_after_two_upserts=count,vectors_in_same_file=True,model_id=MODEL_ID,model_revision=REVISION)
''')
task('6.9', '''
# Ephemeral synthetic signing key is never serialized into delivery artifacts.
fixture_key=os.urandom(32); now=int(time.time())
claims={'sub':'fixture-user','iss':'https://fixture.invalid','aud':'day3','exp':now+300}
def decode_fixture(token):return jwt.decode(token,fixture_key,algorithms=['HS256'],issuer='https://fixture.invalid',audience='day3')
assert decode_fixture(jwt.encode(claims,fixture_key,algorithm='HS256'))['sub']=='fixture-user'
invalid=0
for changes in [{'iss':'https://wrong.invalid'},{'exp':now-10},{'aud':'wrong'}]:
    try: decode_fixture(jwt.encode({**claims,**changes},fixture_key,algorithm='HS256'))
    except jwt.InvalidTokenError: invalid+=1
try: decode_fixture(jwt.encode(claims,os.urandom(32),algorithm='HS256'))
except jwt.InvalidTokenError: invalid+=1
del fixture_key
result('6.9',required_invalid_issuer_and_expiry_rejected=2,all_invalid_tokens_rejected=invalid,live_Google_login=False)
''')
task('6.10', '''
oidc_config={'scopes':['openid','email','profile'],'cookie':{'secure':True,'httponly':True,'samesite':'lax'},'email_report':{'enabled':False,'separate_consent_required':True},'identity_key':['issuer','sub'],'client_secret_source':'environment only, none required for this fixture'}
save_json('identity_contract.json',oidc_config)
result('6.10',**oidc_config)
''')
task('6.11', '''
events=read_jsonl(DATA/'07_Observability/events.jsonl')
sanitized=redact(events+[{'metadata':{'nested':[{'api_key':'TEST-ONLY-SECRET'}],'note':'TEST-ONLY-SECRET'}}])
remaining=json.dumps(sanitized).count('TEST-ONLY-SECRET')
assert remaining==0
save_jsonl('events_sanitized.jsonl',sanitized)
result('6.11',remaining_test_secrets=remaining,events_checked=len(sanitized))
''')
task('6.12', '''
import subprocess,sys
checked=subprocess.run([sys.executable,'Day3/Day3_Grading/check_day3_db.py',str(DB),'--output',str(OUT/'database_check.json')],capture_output=True,text=True)
db_report=json.loads((OUT/'database_check.json').read_text())
result('6.12',exit_code=checked.returncode,status=db_report['status'],meaning={'passed':0,'failed':1,'error':2},stdout=checked.stdout)
assert checked.returncode==0,checked.stdout
''')
task('7.1', '''
docs=load_documents(); policies=policy_documents()
result('7.1',real_documents=len(docs),valid_hashes=len(docs),corpus_version=docs[0]['version'])
''')
task('7.2', '''
pdf_reports=[]
for path in sorted((DATA/'01_Corpus/pdf_fixtures').glob('*.pdf')):
    reader=PdfReader(path); counts=[len(p.extract_text() or '') for p in reader.pages]
    pdf_reports.append({'file':path.name,'pages':len(counts),'characters_per_page':counts,'needs_OCR_or_review':sum(counts)==0})
result('7.2',pdf_count=len(pdf_reports),flagged=sum(x['needs_OCR_or_review'] for x in pdf_reports),reports=pdf_reports)
''')
task('7.3', '''
metadata=[{k:d[k] for k in ['doc_id','title','version','path','source_url','snapshot_url','sections']} for d in docs]
save_json('document_metadata.json',metadata)
assert all(d['sections'] for d in metadata)
result('7.3',metadata_records=len(metadata),sample=metadata[0])
''')
task('7.4', '''
encoder=load_encoder(); tokenizer=encoder.tokenizer
chunks=[c for d in docs for c in split_doc(d,tokenizer)]
policy_chunks=[c for d in policies for c in split_doc(d,tokenizer)]
all_chunks=chunks+policy_chunks
lengths=[c['tokens'] for c in chunks]; assert max(lengths)<=220
plt.figure();plt.hist(lengths,bins=20);plt.xlabel('tokens per chunk');plt.ylabel('count');plt.tight_layout();plt.savefig(OUT/'chunk_lengths.png');plt.close()
result('7.4',chunks=len(chunks),max_tokens=max(lengths),min_tokens=min(lengths),median_tokens=float(np.median(lengths)),overlap=40)
''')
task('7.5', '''
lookup={d['doc_id']:d for d in docs+policies}
errors=sum(lookup[c['doc_id']]['text'][c['start']:c['end']]!=c['content'] or sha(c['content'].encode())!=c['content_hash'] for c in all_chunks)
assert errors==0
c=chunks[0];d=lookup[c['doc_id']]
result('7.5',provenance_errors=errors,sample={**{k:c[k] for k in ['chunk_id','doc_id','version','start','end','section','content_hash']},'source_url':d['source_url'],'path':d['path']})
''')
task('7.6', '''
rerun=[c for d in docs for c in split_doc(d,tokenizer)]
stable=[c['chunk_id'] for c in rerun]==[c['chunk_id'] for c in chunks]
assert stable
result('7.6',stable_ids=stable,compared=len(chunks))
''')
task('7.7', '''
original=split_doc(docs[0],tokenizer)
changed=split_doc({**docs[0],'version':docs[0]['version']+'-experiment','text':docs[0]['text']+'\\nExperimental appendix.\\n'},tokenizer)
intersection=set(c['chunk_id'] for c in original)&set(c['chunk_id'] for c in changed)
assert not intersection
result('7.7',shared_ids=len(intersection),original_unchanged=sha((DATA/'01_Corpus'/docs[0]['path']).read_bytes())==docs[0]['sha256'])
''')
task('7.8', '''
with_duplicates=chunks+chunks[:3]
dedup={c['chunk_id']:c for c in with_duplicates}
removed=len(with_duplicates)-len(dedup)
assert removed==3
result('7.8',removed_duplicates=removed)
''')
task('7.9', '''
chunk_variants={size:[c for d in docs for c in split_doc(d,tokenizer,size)] for size in [110,220,440]}
variant_report={size:{'chunks':len(cs),'truncation_risk':sum(c['tokens']+tokenizer.num_special_tokens_to_add()>256 for c in cs)} for size,cs in chunk_variants.items()}
result('7.9',variants=variant_report,risky_440=variant_report[440]['truncation_risk'])
''')
task('7.10', '''
assert len(policies)==4
result('7.10',policy_chunks=len(policy_chunks),metadata=[{k:c[k] for k in ['doc_id','version','access','tenant','archived']} for c in policy_chunks])
''')
task('7.11', '''
store_documents(docs+policies); store_chunks(all_chunks); store_chunks(all_chunks)
with connect() as con: count=con.execute('SELECT count(*) FROM chunks').fetchone()[0]
assert count==len(all_chunks)
result('7.11',stored_chunks=count,duplicate_rows=0)
''')
task('7.12', '''
save_jsonl('chunks.jsonl',all_chunks)
chunk_config={'size':220,'overlap':40,'offset_unit':'Unicode code points; raw newlines preserved','corpus':docs[0]['version'],'tokenizer_revision':REVISION}
chunk_fingerprint=fingerprint(chunk_config)
save_json('chunk_config.json',{**chunk_config,'fingerprint':chunk_fingerprint})
result('7.12',artifact_records=len(all_chunks),sha256=sha((OUT/'chunks.jsonl').read_bytes()),config_fingerprint=chunk_fingerprint)
''')
task('8.1', '''
model_checks=verify_model()
result('8.1',dimension=MODEL_MANIFEST['dimensions'],max_sequence_length=encoder.max_seq_length,license=MODEL_MANIFEST['license'],model_id=MODEL_ID,revision=REVISION,files_checked=len(model_checks),valid_hashes=sum(x['passed'] for x in model_checks))
''')
task('8.2', '''
index=Retrieval(chunks,encoder)
policy_vectors=encoder.encode([c['content'] for c in policy_chunks],batch_size=32,normalize_embeddings=True,show_progress_bar=False).astype(np.float32)
all_vectors=np.concatenate([index.vectors,policy_vectors])
norms=np.linalg.norm(index.vectors,axis=1)
assert index.vectors.shape==(len(chunks),384) and np.isfinite(index.vectors).all()
result('8.2',vectors=len(chunks),shape=list(index.vectors.shape),seconds=index.encode_seconds,norm_min=float(norms.min()),norm_max=float(norms.max()),non_finite=int((~np.isfinite(index.vectors)).sum()))
''')
task('8.3', '''
a,b=index.vectors[:2]
explicit=float(np.sum(a*b)/(np.linalg.norm(a)*np.linalg.norm(b))); dot=float(a@b)
assert abs(explicit-dot)<1e-6
result('8.3',cosine=explicit,normalized_dot=dot,cosine_distance=1-explicit)
''')
task('8.4', '''
indentation_query='How many spaces should Python indentation use?'
lexical_top=index.ranked(indentation_query,'lexical')
result('8.4',top_document=lexical_top[0]['doc_id'],top3=[{'doc_id':c['doc_id'],'score':c['score']} for c in lexical_top])
''')
task('8.5', '''
dense_top=index.ranked(indentation_query,'dense')
result('8.5',top_document=dense_top[0]['doc_id'],top3=[{'doc_id':c['doc_id'],'score':c['score']} for c in dense_top],same_first=lexical_top[0]['doc_id']==dense_top[0]['doc_id'])
''')
task('8.6', '''
hybrid_top=index.ranked(indentation_query,'hybrid')
result('8.6',top_document=hybrid_top[0]['doc_id'],rrf_constant=60,unit='chunk rank fusion followed by document deduplication',top3=[{'doc_id':c['doc_id'],'score':c['score']} for c in hybrid_top])
''')
task('8.7', '''
store_documents(docs+policies);store_chunks(all_chunks,all_vectors);store_chunks(all_chunks,all_vectors)
with connect() as con:
    stored=con.execute('SELECT embedding FROM chunks ORDER BY chunk_id').fetchall()
    dims=[len(np.frombuffer(r['embedding'],dtype='<f4')) for r in stored]
assert len(stored)==len(all_chunks) and set(dims)=={384}
result('8.7',stored_vectors=len(stored),dimension=dims[0],duplicate_rows=0)
''')
task('8.8', '''
with connect() as con: stored={r['chunk_id']:np.frombuffer(r['embedding'],dtype='<f4') for r in con.execute('SELECT chunk_id,embedding FROM chunks')}
restored=np.stack([stored[c['chunk_id']] for c in chunks])
assert np.array_equal(restored,index.vectors)
qv=index.query_vector(indentation_query)
first_local=int(np.argmax(index.vectors@qv));first_db=int(np.argmax(restored@qv))
assert first_local==first_db
result('8.8',same_top1=True,max_vector_error=float(np.abs(restored-index.vectors).max()),top_chunk=chunks[first_db]['chunk_id'])
''')
task('8.9', '''
# Reuse the already computed vectors, avoiding an unnecessary rebuild.
acl_index=object.__new__(Retrieval)
acl_index.chunks=all_chunks;acl_index.encoder=encoder;acl_index.vectors=all_vectors;acl_index.cache={}
acl_index.vectorizer=TfidfVectorizer(ngram_range=(1,2),sublinear_tf=True)
acl_index.lex=acl_index.vectorizer.fit_transform([c['content'] for c in all_chunks])
t0=adapter.user('U-002'); assert t0['tenant']=='T-0'
acl_hits=acl_index.ranked('Tenant T-1 export retention operations','dense',user=t0,k=len(all_chunks),documents=False)
leaks=sum(c['tenant']=='T-1' and c['access']!='public' for c in acl_hits)
admin_hits=acl_index.ranked('Tenant export retention','dense',user=adapter.user('U-000'),k=len(all_chunks),documents=False)
assert leaks==0 and any(c['doc_id']=='LAB-T1' for c in admin_hits)
result('8.9',tenant_leaks=leaks,admin_can_see_T1=True,archived_returned=any(c['archived'] for c in admin_hits))
''')
task('8.10', '''
ctx_input=index.ranked(indentation_query,'dense',k=10,documents=False)
kept,dropped,token_count=context_budget(ctx_input,tokenizer)
assert token_count<=700
result('8.10',evidence_tokens=token_count,selected=len(kept),dropped=len(dropped),budget=700,includes_prompt_overhead=False)
''')
task('8.11', '''
public_queries=read_jsonl(DATA/'02_Evaluation/queries.jsonl')
train_queries=[q for q in public_queries if q['split']=='train'][:12]
cold=[]
for q in train_queries:
    t=time.perf_counter();index.query_vector(q['query']);cold.append((time.perf_counter()-t)*1000)
latency={}
for method in ['lexical','dense','hybrid']:
    for q in train_queries:index.ranked(q['query'],method)
    timings=[]
    for q in train_queries:
        t=time.perf_counter();index.ranked(q['query'],method);timings.append((time.perf_counter()-t)*1000)
    latency[method]={'p50_ms':float(np.percentile(timings,50)),'p95_ms':float(np.percentile(timings,95)),'n':len(timings)}
result('8.11',warm_latency=latency,cold_embedding_ms={'p50':float(np.percentile(cold,50)),'p95':float(np.percentile(cold,95))})
''')
task('8.12', '''
index_meta={'model_id':MODEL_ID,'revision':REVISION,'dimensions':384,'chunk_fingerprint':chunk_fingerprint,'normalization':'L2','pooling':'mean'}
def validate_index(meta):
    if meta!=index_meta:raise ValueError('Incompatible index fingerprint')
validate_index(dict(index_meta))
try:validate_index({**index_meta,'revision':'incompatible'});raise AssertionError('accepted stale model')
except ValueError:version_rejected=True
index_hash=fingerprint(index_meta)
save_json('index_metadata.json',{**index_meta,'fingerprint':index_hash})
result('8.12',mismatch_rejected=version_rejected,index_fingerprint=index_hash)
''')
task('9.1', '''
queries=read_jsonl(DATA/'02_Evaluation/queries.jsonl');qrels=read_jsonl(DATA/'02_Evaluation/qrels_train_dev.jsonl')
dev=[r for r in qrels if r['split']=='dev']; train=[r for r in qrels if r['split']=='train']
assert all(r['split']!='test' for r in qrels)
result('9.1',queries=len(queries),split_counts=pd.Series([q['split'] for q in queries]).value_counts().to_dict(),answerability={s:{'answerable':sum(r['answerable'] for r in qrels if r['split']==s),'unanswerable':sum(not r['answerable'] for r in qrels if r['split']==s)} for s in ['train','dev']},exact_duplicate_texts=len(queries)-len(set(q['query'] for q in queries)),test_labels_available=False)
''')
task('9.2', '''
manual=[retrieval_metrics({'A'},x) for x in [['B','A','C'],['B','C','D']]]
assert manual[0]['recall']==1 and manual[0]['mrr']==0.5 and abs(manual[0]['ndcg']-1/math.log2(3))<1e-12
assert manual[1]=={'recall':0,'mrr':0,'ndcg':0}
result('9.2',ranked_BAC=manual[0],ranked_BCD=manual[1])
''')
task('9.3', '''
assert sum(r['answerable'] for r in dev)==24
dev_metrics={m:evaluate(index,dev,m) for m in ['lexical','dense','hybrid']}
pd.DataFrame(dev_metrics).T.plot.bar(ylim=(0,1),figsize=(7,4));plt.ylabel('document-level metric');plt.tight_layout();plt.savefig(OUT/'retrieval_dev.png');plt.close()
result('9.3',answerable_dev=24,metrics=dev_metrics)
''')
task('9.4', '''
method_order=['lexical','dense','hybrid']
selected=max(method_order,key=lambda m:(dev_metrics[m]['mrr'],-method_order.index(m)))
retrieval_lock={'method':selected,'k':3,'selected_on':'dev MRR@3','tie_order':method_order,'index_fingerprint':index_hash}
save_json('retrieval_lock.json',retrieval_lock)
result('9.4',selected_method=selected,lock_hash=fingerprint(retrieval_lock),test_gold_accessed=False)
''')
task('9.5', '''
k_sensitivity={k:evaluate(index,dev,selected,k) for k in [1,3,5]}
assert k_sensitivity[1]['recall']<=k_sensitivity[3]['recall']<=k_sensitivity[5]['recall']
result('9.5',k_sensitivity=k_sensitivity)
''')
task('9.6', '''
retrieval_errors=[]
for r in dev:
    if not r['answerable']:continue
    ranked=index.ranked(r['query'],selected)
    if not set(r['relevant_doc_ids'])&set(c['doc_id'] for c in ranked):
        retrieval_errors.append({'query_id':r['query_id'],'query':r['query'],'gold':r['relevant_doc_ids'],'first':ranked[0]['doc_id'],'top3':[c['doc_id'] for c in ranked]})
result('9.6',recall_errors=len(retrieval_errors),first_three=retrieval_errors[:3],unit='document, not passage support')
''')
task('9.7', '''
assert json.loads((OUT/'retrieval_lock.json').read_text())==retrieval_lock
test_queries=[q for q in queries if q['split']=='test']
predictions=[{'query_id':q['query_id'],'ranked_doc_ids':[c['doc_id'] for c in index.ranked(q['query'],selected)]} for q in test_queries]
assert len(predictions)==30 and all(len(set(p['ranked_doc_ids']))==3 for p in predictions)
save_jsonl('test_predictions.jsonl',predictions)
result('9.7',predictions=len(predictions),unique_query_ids=len(set(p['query_id'] for p in predictions)),test_metric='unavailable: hidden gold')
''')
task('9.8', '''
recalls=np.array([retrieval_metrics(r['relevant_doc_ids'],[c['doc_id'] for c in index.ranked(r['query'],selected)])['recall'] for r in dev if r['answerable']])
rng=np.random.default_rng(SEED);boot=rng.choice(recalls,size=(2000,len(recalls)),replace=True).mean(axis=1)
ci=np.percentile(boot,[2.5,97.5])
result('9.8',lower_95=float(ci[0]),upper_95=float(ci[1]),bootstrap_samples=2000,unit='query resampling; semantic family independence is not guaranteed')
''')
task('9.9', '''
dev_scores=np.array([max(c['score'] for c in index.ranked(r['query'],'dense',k=1)) for r in dev])
dev_y=np.array([r['answerable'] for r in dev])
# Include both all-accept and all-reject regimes; accepted is score >= threshold.
thresholds=np.r_[np.nextafter(dev_scores.min(),-np.inf),np.unique(dev_scores),np.nextafter(dev_scores.max(),np.inf)]
threshold=max(thresholds,key=lambda t:(balanced_accuracy_score(dev_y,dev_scores>=t),t))
answerability_lock={'threshold':float(threshold),'comparison':'>=','selected_on':'dev balanced accuracy','tie':'larger threshold','model_revision':REVISION}
save_json('answerability_lock.json',answerability_lock)
result('9.9',threshold=float(threshold),balanced_accuracy=float(balanced_accuracy_score(dev_y,dev_scores>=threshold)),candidates=len(thresholds),confusion_matrix=confusion_matrix(dev_y,dev_scores>=threshold).tolist())
''')
task('9.10', '''
assert json.loads((OUT/'answerability_lock.json').read_text())==answerability_lock
answer_predictions=[{'query_id':q['query_id'],'score':float(index.ranked(q['query'],'dense',k=1)[0]['score'])} for q in test_queries]
for p in answer_predictions:p['accepted']=bool(p['score']>=threshold)
save_jsonl('answerability_predictions.jsonl',answer_predictions)
result('9.10',predictions=len(answer_predictions),accepted=sum(p['accepted'] for p in answer_predictions),abstained=sum(not p['accepted'] for p in answer_predictions),test_gold_accessed=False)
''')
task('9.11', '''
ablation_dev=[r for r in dev if r['answerable']][:6]
small_index=Retrieval(chunk_variants[110],encoder)
ablation={'110':{'vectors':len(small_index.chunks),**evaluate(small_index,ablation_dev,'dense')},'220':{'vectors':len(chunks),**evaluate(index,ablation_dev,'dense')}}
result('9.11',queries=len(ablation_dev),ablation=ablation,changes_to_locked_test_configuration=False)
''')
task('9.12', '''
limitations=['Small English PEP corpus does not establish Persian retrieval quality.','Synthetic and semantically related queries do not establish independent real-user performance.','Document relevance does not establish passage entailment or generated-answer factuality.','Warm local retrieval latency is not production end-to-end latency.']
evaluation_report={'split':'dev','metric_unit':'distinct document; fractions in [0,1]','results':dev_metrics,'config_hash':fingerprint(retrieval_lock),'bootstrap_95':ci.tolist(),'limitations':limitations,'test_gold_used':False}
save_json('evaluation_report.json',evaluation_report)
result('9.12',limitations=len(limitations),unsupported_claims=limitations[:3],config_hash=evaluation_report['config_hash'])
''')
task('10.1', '''
router=pd.read_csv(DATA/'05_Router/requests.csv')
tr=router[router.split=='train'];va=router[router.split=='dev'];te=router[router.split=='test']
groups={s:set(router[router.split==s].template_group) for s in ['train','dev','test']}
shared={a+'_'+b:len(groups[a]&groups[b]) for a,b in [('train','dev'),('train','test'),('dev','test')]}
assert not any(shared.values())
result('10.1',requests=len(router),class_split_counts=router.groupby(['split','route']).size().unstack().to_dict('index'),shared_template_groups=shared)
''')
task('10.2', '''
rule_dev=[rules(q) for q in va['query']]
result('10.2',accuracy=float(accuracy_score(va.route,rule_dev)),macro_F1=float(f1_score(va.route,rule_dev,average='macro')))
''')
task('10.3', '''
linear_candidates={};linear_scores={}
for C in [0.1,1,10]:
    p=Pipeline([('tfidf',TfidfVectorizer(ngram_range=(1,2))),('lr',LogisticRegression(C=C,max_iter=1000,random_state=SEED))])
    p.fit(tr['query'],tr.route);linear_candidates[C]=p
    linear_scores[C]=float(f1_score(va.route,p.predict(va['query']),average='macro'))
best_C=max([0.1,1,10],key=lambda c:(linear_scores[c],-c));linear=linear_candidates[best_C]
save_json('linear_lock.json',{'C':best_C,'dev_macro_F1':linear_scores,'vocabulary_fit':'train only'})
result('10.3',selected_C=best_C,dev_macro_F1=linear_scores)
''')
task('10.4', '''
import torch
from torch import nn
import copy
np.random.seed(SEED);torch.manual_seed(SEED);torch.set_num_threads(4);torch.use_deterministic_algorithms(True)
features={s:encoder.encode(router[router.split==s]['query'].tolist(),normalize_embeddings=True,batch_size=32,show_progress_bar=False).astype(np.float32) for s in ['train','dev','test']}
classes=sorted(tr.route.unique());label_map={v:i for i,v in enumerate(classes)}
y={s:np.array([label_map[v] for v in router[router.split==s].route]) for s in features}
result('10.4',shapes={s:list(v.shape) for s,v in features.items()},norm_min=float(np.linalg.norm(features['train'],axis=1).min()),norm_max=float(np.linalg.norm(features['train'],axis=1).max()),encoder_frozen=True)
''')
task('10.5', '''
network=nn.Sequential(nn.Linear(384,64),nn.ReLU(),nn.Dropout(0.1),nn.Linear(64,4))
parameter_count=sum(p.numel() for p in network.parameters() if p.requires_grad)
assert parameter_count==24900 and network(torch.from_numpy(features['train'][:2])).shape==(2,4)
result('10.5',trainable_parameters=parameter_count,input_shape=[2,384],output_shape=[2,4],formula='384*64+64+64*4+4')
''')
task('10.6', '''
optimizer=torch.optim.AdamW(network.parameters(),lr=0.003)
criterion=nn.CrossEntropyLoss();best_f1=-1;stale=0;learning=[];best_epoch=0
train_x=torch.from_numpy(features['train']);train_y=torch.from_numpy(y['train']).long()
generator=torch.Generator().manual_seed(SEED)
for epoch in range(1,61):
    network.train();total_loss=0
    for batch in torch.randperm(len(train_x),generator=generator).split(32):
        optimizer.zero_grad();loss=criterion(network(train_x[batch]),train_y[batch]);loss.backward();optimizer.step();total_loss+=loss.item()*len(batch)
    network.eval()
    with torch.no_grad():pred=network(torch.from_numpy(features['dev'])).argmax(1).numpy()
    score=float(f1_score(y['dev'],pred,average='macro'))
    learning.append({'epoch':epoch,'train_loss':total_loss/len(train_x),'dev_macro_F1':score})
    if score>best_f1:
        best_f1=score;best_epoch=epoch;best_weights=copy.deepcopy(network.state_dict());stale=0
    else:stale+=1
    if stale>=10:break
network.load_state_dict(best_weights);network.eval();torch.save(best_weights,OUT/'router_weights.pt')
save_json('router_lock.json',{'C':best_C,'best_epoch':best_epoch,'dev_macro_F1':best_f1,'classes':classes,'seed':SEED})
pd.DataFrame(learning).set_index('epoch').plot(subplots=True,figsize=(7,6));plt.tight_layout();plt.savefig(OUT/'router_learning.png');plt.close()
result('10.6',epochs_run=len(learning),best_epoch=best_epoch,best_dev_macro_F1=best_f1,patience=10,history=learning)
''')
task('10.7', '''
# Exactly one held-out comparison after both model choices are frozen.
with torch.no_grad():test_prob=torch.softmax(network(torch.from_numpy(features['test'])),dim=1).numpy()
network_test=test_prob.argmax(1)
test_predictions={'rules':[rules(q) for q in te['query']],'linear':linear.predict(te['query']).tolist(),'neural':[classes[i] for i in network_test]}
router_test_metrics={m:{'accuracy':float(accuracy_score(te.route,p)),'macro_F1':float(f1_score(te.route,p,average='macro'))} for m,p in test_predictions.items()}
# Deployment recommendation is stated separately, without re-tuning on test.
result('10.7',metrics=router_test_metrics,neural_confusion_matrix=confusion_matrix(y['test'],network_test,labels=range(4)).tolist(),class_order=classes)
''')
task('10.8', '''
with torch.no_grad():dev_prob=torch.softmax(network(torch.from_numpy(features['dev'])),dim=1).numpy()
dev_conf=dev_prob.max(1);dev_pred=dev_prob.argmax(1)
coverage={}
for t in [0.5,0.7,0.9]:
    keep=dev_conf>=t
    coverage[t]={'coverage':float(keep.mean()),'accepted':int(keep.sum()),'conditional_accuracy':float((dev_pred[keep]==y['dev'][keep]).mean()) if keep.any() else None}
result('10.8',thresholds=coverage,calibrated_probability=False)
''')
task('10.9', '''
clarify_count=int((dev_conf<0.7).sum())
def route_with_fallback(q):
    feature=encoder.encode([q],normalize_embeddings=True,show_progress_bar=False).astype(np.float32)
    with torch.no_grad():p=torch.softmax(network(torch.from_numpy(feature)),dim=1)[0]
    return classes[int(p.argmax())] if float(p.max())>=0.7 else 'clarify'
result('10.9',clarify_dev=clarify_count,total_dev=len(va),threshold=0.7,confident_unsupported=int(((dev_conf>=0.7)&(dev_pred==label_map['unsupported'])).sum()))
''')
task('10.10', '''
wrong=np.flatnonzero(network_test!=y['test']);chosen=wrong[:3] if len(wrong) else np.argsort(test_prob.max(1))[:2]
examples=[{'query':te.iloc[int(i)]['query'],'truth':te.iloc[int(i)].route,'prediction':classes[network_test[i]],'confidence':float(test_prob[i].max())} for i in chosen]
result('10.10',test_errors=len(wrong),examples=examples,selection='first up to three errors' if len(wrong) else 'zero errors; two lowest-confidence cases instead')
''')
task('10.11', '''
# Topic names are read from train only; no dev refit.
topic_train=tr[tr.template_group=='history-00']['query'].tolist()
topics=sorted([q.removeprefix('Show the case timeline for ').removesuffix('.') for q in topic_train],key=len,reverse=True)
assert len(topics)==10
pattern=re.compile(r'\\b(?:'+ '|'.join(map(re.escape,topics))+r')\\b',re.I)
masked=[pattern.sub('TOPIC',q) for q in va['query']]
masked_pred=linear.predict(masked)
result('10.11',masked_macro_F1=float(f1_score(va.route,masked_pred,average='macro')),original_macro_F1=linear_scores[best_C],topics=topics,refit_on_dev=False)
''')
task('10.12', '''
import joblib
joblib.dump(linear,OUT/'linear_router.joblib')
model_card={'synthetic':True,'group_split':'template_group disjoint','encoder':MODEL_ID,'revision':REVISION,'language':'English; Persian not evaluated','classes':classes,'dev_macro_F1':best_f1,'test_metrics':router_test_metrics,'inappropriate_uses':['authorization decisions','real-world safety guarantee','uncalibrated confidence as probability'],'weights':'router_weights.pt','fallback_threshold':0.7}
save_json('router_model_card.json',model_card)
result('10.12',weights_saved=(OUT/'router_weights.pt').exists(),class_order=classes,model_card=model_card)
''')
task('11.1', '''
s0=initial_state('Find public research on indentation.','U-002','C-001')
secret_fields=[k for k in s0 if re.search('secret|token|password|api_key',k,re.I)]
assert not secret_fields and initial_state('q','u','c')['evidence'] is not initial_state('q','u','c')['evidence']
result('11.1',secret_fields=len(secret_fields),state_fields=list(s0),per_request=True)
''')
task('11.2', '''
graph=make_graph(adapter,acl_index,route_with_fallback)
denied=graph.invoke(initial_state('Find public research on indentation.','U-003','C-001'))
assert denied['denied'] and not denied['evidence'] and not denied['history']
assert [e['event_type'] for e in denied['trace']]==['deny']
result('11.2',nonowner_denied=True,evidence=len(denied['evidence']),trace=[e['event_type'] for e in denied['trace']])
''')
task('11.3', '''
route_example=route_with_fallback('Find a PEP explaining typing.')
route_contract={'history':['history'],'research':['research'],'both':['history','research'],'clarify':[],'unsupported':[]}
controlled={}
for route in ['clarify','unsupported']:
    controlled[route]=make_graph(adapter,acl_index,lambda q,r=route:r).invoke(initial_state('Controlled fixture request','U-002','C-001'))
    assert not controlled[route]['evidence'] and not controlled[route]['history']
result('11.3',sample_route=route_example,tool_mapping=route_contract,controlled_no_private_reads=True)
''')
task('11.4', '''
history_rows=adapter.history('U-002','C-001')
try:adapter.history('U-003','C-001');raise AssertionError('private read permitted')
except HTTPException as e:assert e.status_code==403
allowed_research=acl_index.ranked('Tenant export retention','dense',user=adapter.user('U-002'),k=10,documents=False)
assert all(c['access']=='public' or c['tenant']=='T-0' for c in allowed_research)
result('11.4',authorized_history_rows=len(history_rows),history_role='private context, not scientific citation',research_allowed=True)
''')
task('11.5', '''
# Force routes only for branch coverage, separate from neural-router behavior.
mode_samples={}
for route in ['unsupported','research','both']:
    state=make_graph(adapter,acl_index,lambda q,r=route:r).invoke(initial_state('Python indentation spaces','U-002','C-001'))
    mode_samples[route]=state['answer']
assert mode_samples['research']['claims'] and mode_samples['both']['claims']
result('11.5',sample_claim=mode_samples['research']['claims'][0],modes={k:v['mode'] for k,v in mode_samples.items()},general_limitation=mode_samples['unsupported']['message'])
''')
task('11.6', '''
candidate_evidence=[{'chunk_id':'C-REAL','content':'Use 4 spaces per indentation level.'}]
candidates=read_jsonl(DATA/'06_Robustness/answer_candidates.jsonl')
validation={a['answer_id']:citation_validate(a,candidate_evidence) for a in candidates}
assert sum(v[0] for v in validation.values())==1
result('11.6',accepted=sum(v[0] for v in validation.values()),rejected=sum(not v[0] for v in validation.values()),reasons=validation)
''')
task('11.7', '''
misleading={'claims':[{'text':'Use eight spaces instead of four.','quote':'Use 4 spaces per indentation level.','citation_ids':['C-REAL']}]}
structural=citation_validate(misleading,candidate_evidence)
strict=citation_validate(misleading,candidate_evidence,True)
assert structural[0] and not strict[0]
result('11.7',structural_fooled=structural[0],extractive_rejected=not strict[0],strict_reason=strict[1])
''')
task('11.8', '''
flow=graph.invoke(initial_state('Find a PEP explaining typing.','U-002','C-001'))
steps=[e['event_type'] for e in flow['trace']]
save_json('authorized_graph_trace.json',flow['trace'])
result('11.8',steps=steps,final_route=flow['route'],claims=len(flow['answer']['claims']),actual_langgraph=True)
''')
task('11.9', '''
nonowner=graph.invoke(initial_state('Find a PEP explaining typing.','U-003','C-001'))
owner=graph.invoke(initial_state('Find a PEP explaining typing.','U-002','C-001'))
assert nonowner['denied'] and not owner['denied'] and not nonowner['evidence']
assert not any(e['event_type'] in ['research','history'] for e in nonowner['trace'])
assert nonowner['correlation_id']!=owner['correlation_id']
result('11.9',unauthorized_evidence=len(nonowner['evidence']),next_owner_authorized=not owner['denied'],state_isolated=True)
''')
task('11.10', '''
attacks=read_jsonl(DATA/'06_Robustness/attacks.jsonl')
def extract_only(trusted_passage,untrusted_payload):
    # No interpreter, tool, secret, or live model is provided to this function.
    return {'claims':[{'text':trusted_passage['content'],'quote':trusted_passage['content'],'citation_ids':[trusted_passage['chunk_id']]}]}
attack_results=[]
for a in attacks:
    wrapped={'kind':'untrusted_document_data','text':a['text']}
    answer=extract_only(candidate_evidence[0],wrapped)
    ok,reason=citation_validate(answer,candidate_evidence,True)
    attack_results.append({'attack_id':a['attack_id'],'boundary_passed':ok,'secret_leak':'TEST-ONLY-SECRET' in json.dumps(answer),'live_LLM_calls':0})
assert len(attack_results)==30 and all(x['boundary_passed'] and not x['secret_leak'] for x in attack_results)
save_json('attack_results.json',attack_results)
result('11.10',attack_fixtures=len(attack_results),test_secret_leaks=sum(x['secret_leak'] for x in attack_results),live_LLM_calls=0,scope='extractive data/instruction boundary only')
''')
task('11.11', '''
base={'query':'Same question','user':'U-002','tenant':'T-0','model':MODEL_ID+'@'+REVISION,'corpus':docs[0]['version'],'prompt_version':'v1'}
keys=[cache_key(**base)]
for field,value in [('user','U-003'),('tenant','T-1'),('model','other-model'),('corpus','new-version'),('prompt_version','v2')]:keys.append(cache_key(**{**base,field:value}))
assert len(set(keys))==6
result('11.11',all_changes_missed=True,distinct_keys=len(set(keys)),same_query_different_authorization_separated=keys[0]!=keys[1])
''')
task('11.12', '''
trace=redact(flow['trace']);trace_ids=set(e['correlation_id'] for e in trace)
assert len(trace_ids)==1 and 'TEST-ONLY-SECRET' not in json.dumps(trace)
assert all(set(e)<= {'event_type','correlation_id','metadata'} for e in trace)
save_json('answer_trace.json',trace)
result('11.12',distinct_correlation_ids=len(trace_ids),remaining_secrets=0,events=len(trace),private_full_text_logged=False)
''')
task('12.1', '''
integrated_client=TestClient(make_app(adapter,graph))
checks=[integrated_client.get('/health'),integrated_client.get('/cases/C-001',headers=auth),integrated_client.get('/cases/C-001',headers={'X-User-ID':'U-003'})]
assert [x.status_code for x in checks]==[200,200,403]
result('12.1',engine='SQLite',statuses=[x.status_code for x in checks])
''')
task('12.2', '''
answer_response=integrated_client.post('/answer',json={'case_id':'C-001','query':'Find a PEP explaining typing.'},headers=auth)
assert answer_response.status_code==200
answer_body=answer_response.json()
assert answer_body['correlation_id'] and isinstance(answer_body['claims'],list)
result('12.2',status=answer_response.status_code,correlation_id_present=bool(answer_body['correlation_id']),claims=len(answer_body['claims']))
''')
task('12.3', '''
valid={'case_id':'C-001','query':'Find a PEP explaining typing.'}
negative=[integrated_client.post('/answer',json=valid),integrated_client.post('/answer',json=valid,headers={'X-User-ID':'U-003'}),integrated_client.post('/answer',json={**valid,'query':'a'},headers=auth),integrated_client.post('/answer',json={**valid,'extra':True},headers=auth)]
statuses=[r.status_code for r in negative]
private_summary=adapter.case('C-001','U-002')['summary']
leaked=any(private_summary in r.text for r in negative)
assert statuses==[401,403,422,422] and not leaked
result('12.3',statuses=statuses,private_summary_leaked=leaked)
''')
task('12.4', '''
h={**auth,'Idempotency-Key':'section12-session'}
a=integrated_client.post('/sessions',json={'case_id':'C-001'},headers=h)
b=integrated_client.post('/sessions',json={'case_id':'C-001'},headers=h)
c=integrated_client.post('/sessions',json={'case_id':'C-020'},headers=h)
with connect() as con:n=con.execute('SELECT count(*) FROM sessions WHERE idempotency_key=?',('section12-session',)).fetchone()[0]
assert a.status_code==b.status_code==201 and a.json()['session_id']==b.json()['session_id'] and n==1 and c.status_code==409
result('12.4',same_repeated_id=True,stored_for_key=n,body_conflict=c.status_code)
''')
task('12.5', '''
suspicious='<script>alert("x")</script>';escaped=html.escape(suspicious)
view='''+'"""'+'''<!doctype html><html lang="fa" dir="rtl"><meta charset="utf-8"><title>پاسخ مستند</title><h1>پاسخ و منبع</h1><p id="answer"></p><pre id="source"></pre><p>متن آزمایشی: REPLACE</p><script>document.getElementById("answer").textContent="پاسخ استخراجی آموزشی";document.getElementById("source").textContent="منبع باید بررسی شود";</script></html>'''+ '"""'+'''
(OUT/'answer_view.html').write_text(view.replace('REPLACE',escaped))
assert suspicious not in (OUT/'answer_view.html').read_text()
result('12.5',view_saved=True,escaped_text=escaped,DOM_text_api='textContent')
''')
task('12.6', '''
event_frame=pd.DataFrame(events)
expected_steps=set(event_frame.event_type.unique())
trace_rows=[]
for cid,g in event_frame.groupby('correlation_id'):
    complete=set(g.event_type)==expected_steps and len(g)==len(expected_steps) and not g.event_type.duplicated().any()
    trace_rows.append({'correlation_id':cid,'complete':complete,'total_latency_ms':float(g.latency_ms.sum())})
trace_frame=pd.DataFrame(trace_rows)
lat=trace_frame[trace_frame.complete].total_latency_ms
step_errors=event_frame.assign(is_error=event_frame.status!='ok').groupby('event_type').is_error.mean().to_dict()
plt.figure();plt.hist(lat,bins=30);plt.xlabel('sum of synthetic step latency (ms)');plt.ylabel('complete traces');plt.tight_layout();plt.savefig(OUT/'trace_latency.png');plt.close()
trace_frame.to_csv(OUT/'trace_summary.csv',index=False)
result('12.6',events=len(events),traces=len(trace_rows),incomplete=int((~trace_frame.complete).sum()),p50_ms=float(lat.quantile(.5)),p95_ms=float(lat.quantile(.95)),error_rate_per_step=step_errors,expected_steps=sorted(expected_steps))
''')
task('12.7', '''
gate={'ownership':R['6.6']['access']=={'U-002':True,'U-003':False,'U-000':True} and R['12.3']['statuses']==[401,403,422,422],'idempotency':R['12.4']['same_repeated_id'] and R['12.4']['stored_for_key']==1 and R['12.4']['body_conflict']==409,'embedding_version':R['8.12']['mismatch_rejected'],'citation':R['11.6']['accepted']==1 and R['11.6']['rejected']==3 and R['11.7']['extractive_rejected'],'log_redaction':R['6.11']['remaining_test_secrets']==0 and R['11.12']['remaining_secrets']==0}
save_json('regression_gate.json',{'checks':gate,'passed':all(gate.values()),'evidence_questions':['6.6','12.3','12.4','8.12','11.6','11.7','6.11','11.12']})
assert all(gate.values())
result('12.7',passed_controls=sum(gate.values()),total_controls=len(gate))
''')
task('12.8', '''
pipeline_contract={'engine':'SQLite','fail_fast':True,'steps':[{'name':'dependencies','command':'python -m pip install -r Day3/requirements-day3.txt'},{'name':'prepare','command':'python download_model.py'},{'name':'migration_seed','command':'python -c "from core import migrate_seed; migrate_seed()"'},{'name':'tests','command':'python run_assignment.py --require-complete'},{'name':'health','command':'TestClient GET /health must return 200 and engine SQLite'},{'name':'failure_stop','command':'Stop on nonzero exit; do not release'},{'name':'rollback','command':'Restore a verified pre-migration SQLite backup and the previous application artifact; run health and FK checks'}],'secrets':'read only from environment if real providers are later enabled; none required for fixtures','live_deployment':False}
save_json('pipeline_contract.json',pipeline_contract)
result('12.8',pipeline_steps=len(pipeline_contract['steps']),live_deployment=False)
''')
task('12.9', '''
import subprocess,sys
p=subprocess.run([sys.executable,'Day3/Day3_Grading/check_day3_db.py',str(DB),'--output',str(OUT/'database_check.json')],capture_output=True,text=True)
report=json.loads((OUT/'database_check.json').read_text())
assert p.returncode==0 and report['status']=='passed'
result('12.9',status=report['status'],checks_run=len(report['checks']),checks_passed=sum(c['passed'] for c in report['checks']),exit_code=p.returncode)
''')
task('12.10', '''
reproduction='''+'"""'+'''# بازتولید
از ریشهٔ پروژه و با Python 3.12 یا 3.13 اجرا کنید.
1. python -m venv .venv
2. .venv/bin/python -m pip install torch==2.13.0 --index-url https://download.pytorch.org/whl/cpu
3. .venv/bin/python -m pip install -r Day3/requirements-day3.txt
4. .venv/bin/python download_model.py (نیاز به دامنه‌های Hugging Face؛ hash تمام فایل‌ها کنترل می‌شود)
5. برای ساخت از صفر فایل‌های قبلی output را در محل دیگری پشتیبان بگیرید؛ سپس فقط output/day3.sqlite را حذف کنید.
6. .venv/bin/python run_assignment.py --require-complete
7. .venv/bin/python make_notebook.py
8. .venv/bin/python Day3/Day3_Grading/check_day3_db.py output/day3.sqlite --output output/database_check.json
بذر 20261015؛ مدل و corpus نسخه‌دار؛ هیچ برچسب test بازیابی در دسترس نیست.
تنظیم‌های انتخاب‌شده و hashها در output ذخیره می‌شوند. زمان‌ها وابسته به دستگاه‌اند.
'''+ '"""'+'''
(OUT/'REPRODUCE_FA.md').write_text(reproduction)
manifest_files=['day3.sqlite','test_predictions.jsonl','answerability_predictions.jsonl','chunks.jsonl','retrieval_lock.json','answerability_lock.json','index_metadata.json','router_weights.pt','regression_gate.json','database_check.json']
manifest={f:{'sha256':sha((OUT/f).read_bytes()),'bytes':(OUT/f).stat().st_size} for f in manifest_files}
save_json('delivery_manifest.json',{'files':manifest,'seed':SEED,'notebook_hash':'added after notebook execution; self-reference excluded'})
result('12.10',manifest_files=len(manifest),credentials_or_personal_paths_included=False,hash_algorithm='SHA-256')
''')
task('12.11', '''
rubric={'schema_seed':'Independently inspect the uploaded SQLite bytes using the supplied checker, including FK and rollback probes.','independent_tests':'Recompute counts, validate prediction schema and notebook outputs; never trust student JSON alone.','states':{'passed':'Independent assertions agree with executed evidence.','failed':'An executed check contradicts the required contract; deduct the associated requirement.','error':'Infrastructure or unreadable artifact prevents evaluation; diagnose and rerun rather than assigning a model-quality failure.'},'analysis_review':'Read Persian analyses for provenance, train/dev/test discipline, limitations and consistency with outputs.'}
save_json('grading_rubric.json',rubric)
result('12.11',distinct_grading_states=len(rubric['states']),student_JSON_alone_sufficient=False,rubric=rubric)
''')
task('12.12', '''
final_report={'actually_executed':['FastAPI TestClient and HTTPX MockTransport','SQLite migrations, idempotent seed, ownership, FK, rollback and official checker','Pinned local embedding, lexical/dense/RRF retrieval and train/dev evaluation','PyTorch neural router training and held-out comparison','Real LangGraph invocation and extractive citation validation'],'fixtures':['users and case data','provider responses and fictional prices','signed identity tokens','30 untrusted attack payloads','synthetic latency events'],'not_executed':['live Google OIDC','paid or live LLM calls','PostgreSQL or production vector DB','public deployment','live Gmail integration','hidden-gold retrieval test scoring'],'priorities':['Replace fixture identity with validated OIDC and enforce tenant policy across every store.','Evaluate with representative real data and independent semantic families, including Persian if required.','Add semantic citation validation and live-model adversarial evaluation under limited tool authority.','Establish SLOs, real traces, load tests and per-request deadlines.','Implement reviewed releases, migration backups, restore drills, consent and secret rotation.'],'claim_limit':'Passing a small synthetic extractive POC does not establish production readiness or safety of a live autonomous LLM.'}
save_json('final_report.json',final_report)
result('12.12',explicitly_unexecuted=len(final_report['not_executed']),next_priorities=len(final_report['priorities']),report=final_report)
''')
