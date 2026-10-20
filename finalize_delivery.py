"""Refresh narrative text, validate submission contracts and package deliverables."""
import json,re,hashlib,zipfile
from pathlib import Path
import nbformat
from analyses import ANALYSES
from concepts import CONCEPTS
root=Path('.');out=root/'output'
nb_path=out/'Day3_Complete.ipynb';nb=nbformat.read(nb_path,as_version=4)
nb.cells[0].source+=('' if 'نسخهٔ PDF قدیمی' in nb.cells[0].source else '\n<div dir="rtl">نسخهٔ PDF قدیمی به PostgreSQL و فرم HTML اشاره دارد؛ مبنای اجرا متن درخواست کاربر و START_HERE بسته است که SQLite و چهار فایل تحویلی را مشخص می‌کنند.</div>')
results=json.loads((out/'question_results.json').read_text())
assert len(results)==144
expected={f'{s}.{q}' for s in range(1,13) for q in range(1,13)}
assert set(results)==expected
for key,value in results.items():assert 'execution_status' not in value,(key,value)
headers=[];translation=str.maketrans('۰۱۲۳۴۵۶۷۸۹٫','0123456789.')
for i,c in enumerate(nb.cells):
    if c.cell_type=='markdown':
        match=re.search(r'## زیرسؤال ([۰-۹٫]+)',c.source)
        if match:
            key=match.group(1).translate(translation);headers.append(key)
            assert nb.cells[i+1].cell_type=='code' and nb.cells[i+2].cell_type=='markdown'
            analysis=CONCEPTS[key][1] if key in CONCEPTS else ANALYSES[key]
            nb.cells[i+2].source=f'<div dir="rtl">\n\n**تحلیل و تفسیر:** {analysis}\n\nاعداد و جزئیات این پاسخ در خروجی سلول بالا ثبت شده‌اند.\n\n</div>'
assert set(headers)==expected and len(headers)==144
code=[c for c in nb.cells if c.cell_type=='code']
assert len(code)==145 and all(c.execution_count is not None for c in code)
assert not any(o.output_type=='error' for c in code for o in c.outputs)
assert len({c.execution_count for c in code})==145
# Remove machine-specific warning locations; retain the warning and substantive outputs.
for cell in code:
    for output in cell.outputs:
        if output.output_type=='stream' and output.name=='stderr':
            output.text=re.sub(r'/workspace/students-pack/\.venv/lib/python[0-9.]+/site-packages/', 'site-packages/',output.text)
nbformat.validate(nb);nbformat.write(nb,nb_path)
answers=['# پاسخ‌های کامل تکلیف روز سوم','اعداد زیر عین خروجی اجرای نوت‌بوک‌اند. gold پنهان test در اختیار نیست و معیار نهایی test بازیابی ادعا نشده است.']
for key in sorted(expected,key=lambda q:tuple(map(int,q.split('.')))):
    answers+=['',f'## زیرسؤال {key}','','```json',json.dumps(results[key],ensure_ascii=False,indent=2),'```','',CONCEPTS[key][1] if key in CONCEPTS else ANALYSES[key]]
(out/'Answers_FA.md').write_text('\n'.join(answers))
queries=[json.loads(line) for line in (root/'Day3/Day3_Datasets/02_Evaluation/queries.jsonl').read_text().splitlines()]
test_ids={q['query_id'] for q in queries if q['split']=='test'}
manifest_csv=root/'Day3/Day3_Datasets/01_Corpus/manifest.csv'
import csv
doc_ids={x['doc_id'] for x in csv.DictReader(manifest_csv.open())}
for filename in ['test_predictions.jsonl','answerability_predictions.jsonl']:
    rows=[json.loads(line) for line in (out/filename).read_text().splitlines()]
    assert len(rows)==len(test_ids)==30 and {r['query_id'] for r in rows}==test_ids
    for row in rows:
        if 'ranked_doc_ids' in row:
            assert set(row)=={'query_id','ranked_doc_ids'} and len(set(row['ranked_doc_ids']))==3 and set(row['ranked_doc_ids'])<=doc_ids
        else:
            assert set(row)=={'query_id','score','accepted'} and type(row['accepted']) is bool and isinstance(row['score'],float) and -1.000001<=row['score']<=1.000001
report=json.loads((out/'database_check.json').read_text())
assert report['status']=='passed' and len(report['checks'])==22 and all(x['passed'] for x in report['checks'])
# Preserve the ten-file manifest count reported by question 12.10.
manifest=json.loads((out/'delivery_manifest.json').read_text())
manifest['files'].pop('Day3_Complete.ipynb',None);manifest['files'].pop('Answers_FA.md',None)
manifest.pop('notebook_hash',None)
assert len(manifest['files'])==results['12.10']['manifest_files']==10
for name,meta in manifest['files'].items():assert hashlib.sha256((out/name).read_bytes()).hexdigest()==meta['sha256'],name
(out/'delivery_manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2))
submission_files=['Day3_Complete.ipynb','day3.sqlite','test_predictions.jsonl','answerability_predictions.jsonl','Answers_FA.md']
# No personal workspace paths or actual credential values in the four submissions.
for name in submission_files:
    raw=(out/name).read_bytes()
    for forbidden in [b'/home/agent',b'/workspace/',b'/opt/codex']:
        assert forbidden not in raw,(name,forbidden)
hashes={name:{'sha256':hashlib.sha256((out/name).read_bytes()).hexdigest(),'bytes':(out/name).stat().st_size} for name in submission_files}
(out/'submission_hashes.json').write_text(json.dumps({'files':hashes},ensure_ascii=False,indent=2))
validation={'notebook_questions':144,'executed_code_cells':145,'notebook_error_outputs':0,'database_passed':22,'database_checks':22,'retrieval_test_predictions':30,'answerability_test_predictions':30,'hidden_retrieval_test_gold_used':False,'submission_uploaded':False}
(out/'delivery_validation.json').write_text(json.dumps(validation,ensure_ascii=False,indent=2))
archive=out/'Day3_Submission_Complete.zip'
with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED) as z:
    for p in sorted(out.iterdir()):
        if p.is_file() and p.suffix not in ['.zip','.log']:z.write(p,Path('output')/p.name)
    for p in sorted(root.glob('*.py')):z.write(p,p.name)
    for p in [root/'README.md',root/'questions.json',root/'.gitignore']:z.write(p,p.name)
    for p in sorted((root/'Day3').rglob('*')):
        if p.is_file() and 'embedding_model' not in p.parts and '__pycache__' not in p.parts:z.write(p,p)
print(json.dumps(validation,ensure_ascii=False,indent=2));print('Archive bytes:',archive.stat().st_size)
