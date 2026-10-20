"""Build and execute the complete, self-contained notebook from actual code cells."""
from pathlib import Path
import json,html
import nbformat
from nbclient import NotebookClient
from concepts import CONCEPTS
from tasks import TASKS
from analyses import ANALYSES
ROOT=Path('.').resolve();OUT=ROOT/'output'
questions=json.loads((ROOT/'questions.json').read_text())
order=list(CONCEPTS)+[f'5.{i}' for i in range(1,13)]+[f'6.{i}' for i in [1,2,3,4,5,6,7,9,10,11]]+[f'7.{i}' for i in range(1,13)]+[f'8.{i}' for i in range(1,13)]+['6.8','6.12']+[f'9.{i}' for i in range(1,13)]+[f'10.{i}' for i in range(1,13)]+[f'11.{i}' for i in range(1,13)]+[f'12.{i}' for i in range(1,13)]
assert len(order)==144 and len(set(order))==144
nb=nbformat.v4.new_notebook(metadata={'kernelspec':{'name':'python3','display_name':'Python 3','language':'python'},'language_info':{'name':'python','version':'3.12'},'assignment_seed':20261015})
nb.cells=[nbformat.v4.new_markdown_cell('''<div dir="rtl">
# پاسخ کامل تکلیف روز سوم
این دفتر شامل ۱۴۴ زیرسؤال و برای هرکدام سه سلول صورت سؤال، کد انگلیسی با خروجی و تحلیل فارسی است. کد زیرساخت، migration/seed، API، بازیابی و گراف در سلول آغازین آمده و داخل همین دفتر قابل بررسی است.

برای رعایت وابستگی محاسبات، ۶٫۸ و ۶٫۱۲ پس از ساخت بردارهای بخش ۸ اجرا می‌شوند؛ عنوان دقیق همهٔ سؤال‌ها حفظ شده است. کد از ریشهٔ پروژه و همراه پوشهٔ Day3 اجرا می‌شود. هر اجرا در محیط ایزولهٔ موجود است و به worktree تازه نیاز ندارد.

کاربران، قیمت‌ها، هویت، حمله‌ها و latency دادهٔ مصنوعی‌اند. embedding، یادگیری شبکه، SQLite، TestClient و LangGraph واقعاً اجرا می‌شوند؛ Google زنده، LLM پولی و استقرار عمومی اجرا نمی‌شوند. gold بازیابی test در اختیار نیست. تنظیمات فقط با train/dev انتخاب و پیش از تولید test قفل می‌شوند.
</div>'''),nbformat.v4.new_code_cell((ROOT/'core.py').read_text()+"\nfrom IPython.display import display, Image\nprint('Infrastructure loaded; reference seed:', SEED)\n")]
figures={'5.2':'api_status.png','7.4':'chunk_lengths.png','9.3':'retrieval_dev.png','10.6':'router_learning.png','12.6':'trace_latency.png'}
for q in order:
    title=q.translate(str.maketrans('0123456789.','۰۱۲۳۴۵۶۷۸۹٫'))
    block=questions[q].splitlines(); prompt='\n'.join(block[1:]).split('\n\n')[0]
    nb.cells.append(nbformat.v4.new_markdown_cell(f'<div dir="rtl">\n\n## زیرسؤال {title}\n\n{prompt}\n\n</div>'))
    if q in CONCEPTS:
        option,reason=CONCEPTS[q];source=f"result({q!r}, selected_option={option!r}, reason_fa={reason!r})"
        explanation=reason
    else:source=TASKS[q];explanation=ANALYSES[q]
    source+=f"\nprint(json.dumps(R[{q!r}], ensure_ascii=False, indent=2, default=lambda x: x.item() if isinstance(x,np.generic) else str(x)))"
    if q in figures:source+=f"\ndisplay(Image(filename=str(OUT/{figures[q]!r})))"
    nb.cells.append(nbformat.v4.new_code_cell(source))
    nb.cells.append(nbformat.v4.new_markdown_cell(f'<div dir="rtl">\n\n**تحلیل و تفسیر:** {explanation}\n\nاعداد و جزئیات این پاسخ در خروجی سلول بالا ثبت شده‌اند.\n\n</div>'))
# A final output-only export keeps all three required cells per question intact.
nb.cells[-2].source+="\nsave_json('question_results.json',R)\nsave_json('execution_status.json',{'questions':{q:'executed' for q in R},'issues':{}})"
path=OUT/'Day3_Complete.ipynb';nbformat.write(nb,path)
NotebookClient(nb,timeout=600,kernel_name='python3',resources={'metadata':{'path':str(ROOT)}},allow_errors=False).execute()
nbformat.write(nb,path)
print('Executed notebook saved:',path.name,'cells:',len(nb.cells))
# Responses for the website: exact values from the executed notebook, no invented test metrics.
results=json.loads((OUT/'question_results.json').read_text())
answers=['# پاسخ‌های تکلیف روز سوم','برای هر زیرسؤال، نتیجهٔ عددی دقیق زیر از اجرای نوت‌بوک آمده است. متن تحلیل فارسی نیز همراه آن است.']
for q in sorted(questions,key=lambda q:tuple(map(int,q.split('.')))):
    v=results[q];answers+=['',f'## زیرسؤال {q}', '', '```json',json.dumps(v,ensure_ascii=False,indent=2),'```','',CONCEPTS[q][1] if q in CONCEPTS else ANALYSES[q]]
(OUT/'Answers_FA.md').write_text('\n'.join(answers))
# Hash final notebook only after outputs have been saved; avoid circular hashes.
import hashlib
manifest=json.loads((OUT/'delivery_manifest.json').read_text())
for name in ['Day3_Complete.ipynb','Answers_FA.md']:
    raw=(OUT/name).read_bytes();manifest['files'][name]={'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest()}
manifest.pop('notebook_hash',None)
(OUT/'submission_hashes.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2))
