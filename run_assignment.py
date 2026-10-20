"""Execute every available question; report missing prerequisites explicitly."""
import argparse,json,traceback
from pathlib import Path
from core import *
from concepts import CONCEPTS
from tasks import TASKS
parser=argparse.ArgumentParser();parser.add_argument('--require-complete',action='store_true');args=parser.parse_args()
import core
namespace=dict(core.__dict__);statuses={};blocked={}
for q,(option,reason) in CONCEPTS.items():
    R[q]={'selected_option':option,'reason_fa':reason};statuses[q]='executed'
# Respect cross-section dependencies, while preserving question numbers in delivery.
order=[f'5.{i}' for i in range(1,13)]+[f'6.{i}' for i in [1,2,3,4,5,6,7,9,10,11]]+[f'7.{i}' for i in range(1,13)]+[f'8.{i}' for i in range(1,13)]+['6.8','6.12']+[f'9.{i}' for i in range(1,13)]+[f'10.{i}' for i in range(1,13)]+[f'11.{i}' for i in range(1,13)]+[f'12.{i}' for i in range(1,13)]
for q in order:
    try:
        exec(compile(TASKS[q],'<question '+q+'>','exec'),namespace)
        statuses[q]='executed';print(q,'executed',flush=True)
    except Exception as e:
        statuses[q]='blocked' if isinstance(e,(NameError,RuntimeError)) else 'failed'
        blocked[q]={'type':type(e).__name__,'message':str(e)}
        R[q]={'execution_status':statuses[q],'error_type':type(e).__name__,'message':str(e)}
        print(q,statuses[q],type(e).__name__,str(e)[:200],flush=True)
        if statuses[q]=='failed':traceback.print_exc()
save_json('question_results.json',R);save_json('execution_status.json',{'questions':statuses,'issues':blocked})
print('Executed:',sum(s=='executed' for s in statuses.values()),'of',len(statuses))
if args.require_complete and blocked:raise SystemExit(1)
