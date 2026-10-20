# بررسی خودکار دیتابیس

دیتابیس این تمرین یک فایل SQLite است (`day3.sqlite`)؛ Docker، PostgreSQL و رمز لازم نیست.

```sh
python Day3_Grading/check_day3_db.py day3.sqlite
```

کد خروج 0 یعنی همهٔ بررسی‌ها درست است، 1 یعنی دست‌کم یکی نادرست است و 2 یعنی فایل خوانا نیست. گزارش در `database_check.json` ذخیره می‌شود.
همین بررسی پس از ارسال، خودکار روی فایلی که بارگذاری کرده‌ای اجرا می‌شود و نمرهٔ بخش اجرایی سؤال‌های دیتابیس از روی آن است؛ گزارش خودت جایگزین آن نیست.
بررسی فایل را فقط می‌خواند: روی یک کپی در حافظه چند آزمون می‌نویسد و برمی‌گرداند و هیچ کدی از فایل تو اجرا نمی‌شود.

## قرارداد جدول‌ها

| جدول | ستون‌های لازم |
|---|---|
| users | user_id, role, tenant |
| cases | case_id, owner_id, topic, summary |
| sessions | session_id, owner_id, case_id, idempotency_key |
| messages | message_id, session_id, content |
| documents | doc_id, version, content_hash |
| chunks | chunk_id, doc_id, content, embedding, model_id, model_revision |

کلیدهای خارجی: cases.owner_id و sessions.owner_id به users.user_id؛ sessions.case_id به cases.case_id؛ messages.session_id به sessions.session_id؛ chunks.doc_id به documents.doc_id.
داده: ۲۰ کاربر، ۱۲۰ پرونده، دست‌کم ۲۴ سند و همهٔ chunkها با بردار ۳۸۴بعدی. ستون embedding یا BLOB با ۳۸۴ عدد float32 است یا متن JSON آرایهٔ ۳۸۴ عددی.
همچنین باید روی cases.owner_id ایندکس و روی sessions.idempotency_key و documents.doc_id یکتایی باشد.
