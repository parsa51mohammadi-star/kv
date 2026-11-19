# ربات پارسا — ساخته شده توسط پارسا

اپ اندروید سلف‌بات سروش (پایتون داخل اپ با Chaquopy).

## ساخت APK بدون Android Studio (با GitHub)
1. در github.com یک حساب رایگان بساز و یک Repository جدید (ترجیحا Private) بساز.
2. محتویات همین پوشه (نه خود پوشه) را در Repository آپلود کن:
   Add file ← Upload files ← همه‌ی فایل‌ها و پوشه‌ها (app، .github، فایل‌های gradle و ...).
   مهم: پوشه‌ی مخفی `.github` هم باید آپلود شود.
3. به تب Actions برو؛ ساخت خودکار شروع می‌شود (حدود ۵ تا ۱۰ دقیقه).
4. بعد از تموم شدن: تب Releases (سمت راست صفحه‌ی اصلی Repository) ← فایل ParsaBot.apk را دانلود و نصب کن.
   (یا از خود صفحه‌ی اجرای Actions، بخش Artifacts)
5. اگر ساخت خطا داد، متن خطای آخرین مرحله (Build debug APK) را برای Claude بفرست.
