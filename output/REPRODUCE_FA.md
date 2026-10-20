# بازتولید
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
