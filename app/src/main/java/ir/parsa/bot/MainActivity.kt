package ir.parsa.bot

import android.Manifest
import android.app.Activity
import android.app.AlertDialog
import android.content.ComponentName
import android.content.Intent
import android.content.pm.PackageManager
import android.graphics.Color
import android.graphics.Typeface
import android.graphics.drawable.GradientDrawable
import android.net.Uri
import android.os.Build
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.os.PowerManager
import android.provider.Settings
import android.text.InputType
import android.view.Gravity
import android.view.View
import android.view.ViewGroup
import android.widget.Button
import android.widget.EditText
import android.widget.FrameLayout
import android.widget.LinearLayout
import android.widget.ScrollView
import android.widget.TextView
import android.widget.Toast
import org.json.JSONObject

class MainActivity : Activity() {

    private val cBg = Color.parseColor("#0F1419")
    private val cCard = Color.parseColor("#1A222C")
    private val cText = Color.parseColor("#E8EDF2")
    private val cSub = Color.parseColor("#8FA0B3")
    private val cGreen = Color.parseColor("#2E9E5B")
    private val cRed = Color.parseColor("#C0392B")
    private val cBlue = Color.parseColor("#2F6FDE")
    private val cTabOff = Color.parseColor("#26303C")

    private val MATCH = ViewGroup.LayoutParams.MATCH_PARENT
    private val WRAP = ViewGroup.LayoutParams.WRAP_CONTENT

    private lateinit var content: FrameLayout
    private val tabButtons = ArrayList<Button>()
    private val ui = Handler(Looper.getMainLooper())
    private var refresher: Runnable? = null
    private var tab = 0

    // ویجت‌های صفحه‌ی کنترل
    private var statusView: TextView? = null
    private var toggleBtn: Button? = null
    private var accountsBox: LinearLayout? = null
    private var logView: TextView? = null
    private var lastAccKey = ""
    private var accountCount = -1
    private var lastKick = 0L

    // ---------------------------------------------------------------- چرخه‌ی عمر
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        window.statusBarColor = cBg
        window.navigationBarColor = cBg

        val root = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setBackgroundColor(cBg)
            layoutDirection = View.LAYOUT_DIRECTION_RTL
        }

        content = FrameLayout(this)
        root.addView(content, LinearLayout.LayoutParams(MATCH, 0, 1f))

        val bar = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            setBackgroundColor(cCard)
            setPadding(dp(8), dp(8), dp(8), dp(8))
        }
        listOf("راهنما", "اکانت‌ها", "کنترل").forEachIndexed { i, label ->
            val b = Button(this).apply {
                text = label
                isAllCaps = false
                setTextColor(cText)
                setOnClickListener { showTab(i) }
            }
            tabButtons.add(b)
            bar.addView(b, LinearLayout.LayoutParams(0, WRAP, 1f).apply {
                marginStart = dp(4)
                marginEnd = dp(4)
            })
        }
        root.addView(bar, LinearLayout.LayoutParams(MATCH, WRAP))

        val footer = TextView(this).apply {
            text = "ساخته شده توسط پارسا"
            setTextColor(cSub)
            textSize = 12f
            gravity = Gravity.CENTER
            setBackgroundColor(cCard)
            setPadding(0, dp(4), 0, dp(10))
        }
        root.addView(footer, LinearLayout.LayoutParams(MATCH, WRAP))

        setContentView(root)

        if (Build.VERSION.SDK_INT >= 33 &&
            checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS) != PackageManager.PERMISSION_GRANTED
        ) {
            requestPermissions(arrayOf(Manifest.permission.POST_NOTIFICATIONS), 1)
        }

        showTab(0)
    }

    override fun onResume() {
        super.onResume()
        // اگه ربات باید روشن باشه ولی سرویس (مثلا توسط گوشی) کشته شده، دوباره بالا بیار
        ensureService()
        if (tab == 2) startRefresh()
    }

    override fun onPause() {
        stopRefresh()
        super.onPause()
    }

    private fun ensureService() {
        if (!Core.enabled(this)) return
        try {
            startForegroundService(Intent(this, BotService::class.java))
        } catch (_: Throwable) {
        }
    }

    /** باز کردن صفحه‌ی «شروع خودکار» در گوشی‌هایی که برنامه‌ی بسته‌شده را می‌کشند */
    private fun openAutostart() {
        val targets = listOf(
            "com.miui.securitycenter" to "com.miui.permcenter.autostart.AutoStartManagementActivity",
            "com.huawei.systemmanager" to "com.huawei.systemmanager.startupmgr.ui.StartupNormalAppListActivity",
            "com.huawei.systemmanager" to "com.huawei.systemmanager.optimize.process.ProtectActivity",
            "com.coloros.safecenter" to "com.coloros.safecenter.permission.startup.StartupAppListActivity",
            "com.oppo.safe" to "com.oppo.safe.permission.startup.StartupAppListActivity",
            "com.vivo.permissionmanager" to "com.vivo.permissionmanager.activity.BgStartUpManagerActivity",
            "com.samsung.android.lool" to "com.samsung.android.sm.ui.battery.BatteryActivity",
            "com.asus.mobilemanager" to "com.asus.mobilemanager.powersaver.PowerSaverSettings"
        )
        for ((pkg, cls) in targets) {
            try {
                startActivity(Intent().setComponent(ComponentName(pkg, cls)))
                return
            } catch (_: Throwable) {
            }
        }
        try {
            startActivity(
                Intent(Settings.ACTION_APPLICATION_DETAILS_SETTINGS)
                    .setData(Uri.parse("package:$packageName"))
            )
        } catch (_: Throwable) {
        }
    }

    // ---------------------------------------------------------------- ابزارهای ظاهر
    private fun dp(v: Int): Int = (v * resources.displayMetrics.density).toInt()

    private fun rounded(color: Int, radius: Int = 12): GradientDrawable =
        GradientDrawable().apply {
            setColor(color)
            cornerRadius = dp(radius).toFloat()
        }

    private fun lp(top: Int = 10): LinearLayout.LayoutParams =
        LinearLayout.LayoutParams(MATCH, WRAP).apply { topMargin = dp(top) }

    private fun label(s: String, size: Float = 16f, bold: Boolean = false, color: Int = cText): TextView =
        TextView(this).apply {
            text = s
            textSize = size
            setTextColor(color)
            if (bold) setTypeface(typeface, Typeface.BOLD)
            layoutParams = lp()
        }

    private fun card(title: String, body: String): LinearLayout =
        LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            background = rounded(cCard)
            setPadding(dp(14), dp(12), dp(14), dp(12))
            layoutParams = lp(12)
            addView(TextView(context).apply {
                text = title
                textSize = 17f
                setTextColor(cText)
                setTypeface(typeface, Typeface.BOLD)
            })
            addView(TextView(context).apply {
                text = body
                textSize = 14f
                setTextColor(cSub)
                setLineSpacing(0f, 1.25f)
                setPadding(0, dp(6), 0, 0)
            })
        }

    private fun button(s: String, color: Int): Button =
        Button(this).apply {
            text = s
            isAllCaps = false
            setTextColor(Color.WHITE)
            textSize = 16f
            background = rounded(color)
            layoutParams = lp(14)
        }

    private fun input(hint: String, type: Int): EditText =
        EditText(this).apply {
            this.hint = hint
            inputType = type
            setTextColor(cText)
            setHintTextColor(cSub)
            background = rounded(cCard)
            setPadding(dp(14), dp(12), dp(14), dp(12))
            textDirection = View.TEXT_DIRECTION_LTR
            gravity = Gravity.START or Gravity.CENTER_VERTICAL
            layoutParams = lp(14)
        }

    private fun page(vararg views: View): ScrollView {
        val col = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(dp(16), dp(16), dp(16), dp(16))
        }
        views.forEach { col.addView(it) }
        return ScrollView(this).apply {
            isFillViewport = true
            addView(col, ViewGroup.LayoutParams(MATCH, WRAP))
        }
    }

    private fun toast(s: String) = Toast.makeText(this, s, Toast.LENGTH_LONG).show()

    private fun latinDigits(s: String): String = buildString {
        for (c in s) {
            append(
                when (c) {
                    in '۰'..'۹' -> '0' + (c - '۰')
                    in '٠'..'٩' -> '0' + (c - '٠')
                    else -> c
                }
            )
        }
    }

    private fun normalizePhone(raw: String): String? {
        var s = latinDigits(raw).trim().replace(" ", "").replace("-", "")
        s = when {
            s.startsWith("+") -> s
            s.startsWith("00") -> "+" + s.substring(2)
            s.startsWith("09") -> "+98" + s.substring(1)
            s.startsWith("9") && s.length == 10 -> "+98$s"
            s.startsWith("98") -> "+$s"
            else -> return null
        }
        return if (s.length in 11..15 && s.drop(1).all { it.isDigit() }) s else null
    }

    /** اجرای کار سنگین (پایتون) در ترد جدا و برگشت نتیجه به UI */
    private fun <T> bg(work: () -> T, done: (Result<T>) -> Unit) {
        Thread {
            val r = try {
                Result.success(work())
            } catch (e: Throwable) {
                Result.failure(e)
            }
            runOnUiThread { done(r) }
        }.start()
    }

    // ---------------------------------------------------------------- تب‌ها
    private fun setContent(v: View) {
        stopRefresh()
        content.removeAllViews()
        content.addView(v)
    }

    private fun showTab(i: Int) {
        tab = i
        tabButtons.forEachIndexed { idx, b ->
            b.background = rounded(if (idx == i) cBlue else cTabOff, 10)
        }
        when (i) {
            0 -> setContent(guideView())
            1 -> setContent(loginPhoneView())
            else -> {
                setContent(controlView())
                startRefresh()
            }
        }
    }

    // ---------------------------------------------------------------- صفحه‌ی راهنما
    private fun guideView(): View {
        val go = button("ورود اکانت سروش", cBlue).apply { setOnClickListener { showTab(1) } }
        val panel = button("پنل کنترل ربات", cGreen).apply { setOnClickListener { showTab(2) } }
        return page(
            label("🤖 ربات پارسا", 26f, true),
            label("سلف‌بات سروش پلاس که روی خود گوشی اجرا می‌شود و با بسته شدن برنامه هم خاموش نمی‌شود.", 15f, color = cSub),
            card(
                "راه‌اندازی",
                "۱. از تب «اکانت‌ها» شماره‌ی سروشت را بزن.\n" +
                    "۲. کدی که داخل خود برنامه‌ی سروش برایت آمده را اینجا وارد کن (اگر رمز دومرحله‌ای داری، رمز را هم بزن).\n" +
                    "۳. به تب «کنترل» برو و ربات را روشن کن.\n" +
                    "۴. همان‌جا «معافیت از بهینه‌سازی باتری» را بزن تا اندروید ربات را نکشد.\n" +
                    "۵. اگر گوشی شیائومی، سامسونگ، هوآوی یا مشابه است، در تنظیمات گوشی «شروع خودکار» (Autostart) و «بدون محدودیت باتری» را هم برای این برنامه روشن کن."
            ),
            card(
                "نحوه‌ی استفاده",
                "دستورها را از خود همین اکانت در هر چتی بنویس (مثلاً در «پیام‌های ذخیره‌شده»). پیام‌های خود اکانت همیشه دستور حساب می‌شوند. برای دیدن همه‌ی دستورها بنویس: /help"
            ),
            card(
                "دستورهای اصلی",
                "/ping — بررسی روشن بودن\n" +
                    "/bot on|off — روشن/خاموش کردن همان اکانت\n" +
                    "/id — آیدی عددی (گروه، پیوی یا ریپلای)\n" +
                    "/settime عدد — فاصله‌ی اسپم (ثانیه)\n" +
                    "/reply on|off — ریپلای به دشمن\n" +
                    "/typing on|off — حالت تایپینگ\n\n" +
                    "فحش (مشترک بین اکانت‌ها):\n" +
                    "/addfosh | /addallfosh | /delfosh | /flist | /cleanflist\n\n" +
                    "دشمن:\n" +
                    "/setenemy | /delenemy | /enemylist | /cleanlist\n\n" +
                    "سکوت:\n" +
                    "/add آیدی | /del آیدی | /dellist\n\n" +
                    "اسپم:\n" +
                    "/setspam | /spamlist | /cleanslist | /settext | /deltext\n\n" +
                    "تایمر:\n" +
                    "/timer on|off | /pingtimer | /timertext | /settimer دقیقه\n" +
                    "/setspamtimer | /listspamtimer | /deltimerspam | /cleanlisttimer\n\n" +
                    "دیگر:\n" +
                    "/name (ریپلای) — تغییر اسم اکانت\n" +
                    "/clock on|off — ساعت کنار اسم"
            ),
            card(
                "هشدار",
                "رشته‌ی سشن اکانت مثل رمز حساب است و فقط داخل حافظه‌ی خصوصی همین برنامه ذخیره می‌شود. جایی منتشرش نکن. استفاده‌ی زیاد از اسپم و پاسخ خودکار ممکن است باعث محدود شدن اکانت شود."
            ),
            go,
            panel
        )
    }

    // ---------------------------------------------------------------- ورود (شماره ← کد ← رمز)
    private fun loginPhoneView(): View {
        val phone = input("شماره‌ی سروش (مثال 09123456789)", InputType.TYPE_CLASS_PHONE)
        val msg = label("", 14f, color = cSub)
        val btn = button("ارسال کد ورود", cBlue)
        btn.setOnClickListener {
            val p = normalizePhone(phone.text.toString())
            if (p == null) {
                msg.text = "شماره نامعتبر است."
                return@setOnClickListener
            }
            btn.isEnabled = false
            msg.text = "در حال ارسال کد..."
            bg({ Core.get(this).callAttr("send_code", p).toString() }) { r ->
                btn.isEnabled = true
                r.onSuccess { setContent(loginCodeView()) }
                    .onFailure { msg.text = "خطا: ${it.message}" }
            }
        }
        return page(
            label("ورود اکانت سروش", 22f, true),
            label("شماره‌ی اکانت را بزن؛ کد ورود داخل برنامه‌ی سروش برایت می‌آید.", 14f, color = cSub),
            phone, btn, msg
        )
    }

    private fun loginCodeView(): View {
        val code = input("کد ورود", InputType.TYPE_CLASS_NUMBER)
        val msg = label("", 14f, color = cSub)
        val btn = button("تایید کد", cGreen)
        btn.setOnClickListener {
            val c = latinDigits(code.text.toString()).trim()
            if (c.isEmpty()) {
                msg.text = "کد را وارد کن."
                return@setOnClickListener
            }
            btn.isEnabled = false
            msg.text = "در حال ورود..."
            bg({ Core.get(this).callAttr("sign_in_code", c).toString() }) { r ->
                btn.isEnabled = true
                r.onSuccess {
                    when (it) {
                        "PASSWORD" -> setContent(loginPasswordView())
                        else -> loginDone()
                    }
                }.onFailure { msg.text = "خطا: ${it.message}" }
            }
        }
        val back = button("برگشت", cTabOff).apply { setOnClickListener { setContent(loginPhoneView()) } }
        return page(
            label("کد ورود", 22f, true),
            label("کدی که در برنامه‌ی سروش آمده را وارد کن.", 14f, color = cSub),
            code, btn, msg, back
        )
    }

    private fun loginPasswordView(): View {
        val pass = input("رمز دومرحله‌ای", InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_VARIATION_PASSWORD)
        val msg = label("", 14f, color = cSub)
        val btn = button("تایید رمز", cGreen)
        btn.setOnClickListener {
            val p = pass.text.toString()
            if (p.isEmpty()) {
                msg.text = "رمز را وارد کن."
                return@setOnClickListener
            }
            btn.isEnabled = false
            msg.text = "در حال ورود..."
            bg({ Core.get(this).callAttr("sign_in_password", p).toString() }) { r ->
                btn.isEnabled = true
                r.onSuccess { loginDone() }.onFailure { msg.text = "خطا: ${it.message}" }
            }
        }
        return page(
            label("رمز دومرحله‌ای", 22f, true),
            label("این اکانت رمز دومرحله‌ای دارد؛ آن را وارد کن.", 14f, color = cSub),
            pass, btn, msg
        )
    }

    private fun loginDone() {
        toast("اکانت با موفقیت وارد شد ✅")
        lastAccKey = ""
        showTab(2)
    }

    // ---------------------------------------------------------------- صفحه‌ی کنترل
    private fun controlView(): View {
        lastAccKey = ""
        statusView = label("...", 22f, true)
        toggleBtn = button("", cGreen).apply { setOnClickListener { toggle() } }
        accountsBox = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            layoutParams = lp(6)
        }
        logView = label("", 12f, color = cSub).apply { typeface = Typeface.MONOSPACE }

        val addBtn = button("افزودن اکانت", cBlue).apply { setOnClickListener { showTab(1) } }
        val batteryBtn = button("معافیت از بهینه‌سازی باتری", cTabOff).apply {
            setOnClickListener { requestBatteryExemption() }
        }

        val autoBtn = button("تنظیم شروع خودکار (شیائومی/سامسونگ/...)", cTabOff).apply {
            setOnClickListener { openAutostart() }
        }

        val v = page(
            statusView!!,
            toggleBtn!!,
            label("اکانت‌ها", 18f, true),
            accountsBox!!,
            addBtn,
            batteryBtn,
            autoBtn,
            label("گزارش اجرا", 18f, true),
            logView!!
        )
        updateToggle()
        return v
    }

    private fun updateToggle() {
        val on = Core.enabled(this)
        toggleBtn?.apply {
            text = if (on) "خاموش کردن ربات" else "روشن کردن ربات"
            background = rounded(if (on) cRed else cGreen)
        }
    }

    private fun toggle() {
        if (Core.enabled(this)) {
            Core.setEnabled(this, false)
            startService(Intent(this, BotService::class.java).setAction(BotService.ACTION_STOP))
        } else {
            if (accountCount == 0) {
                toast("اول یک اکانت وارد کن.")
                return
            }
            Core.setEnabled(this, true)
            try {
                startForegroundService(Intent(this, BotService::class.java))
            } catch (e: Throwable) {
                Core.setEnabled(this, false)
                toast("روشن نشد: ${e.message}")
            }
            val pm = getSystemService(PowerManager::class.java)
            if (Core.enabled(this) && !pm.isIgnoringBatteryOptimizations(packageName)) {
                requestBatteryExemption()
            }
        }
        updateToggle()
        refresh()
    }

    private fun requestBatteryExemption() {
        val pm = getSystemService(PowerManager::class.java)
        if (pm.isIgnoringBatteryOptimizations(packageName)) {
            toast("این برنامه از قبل از بهینه‌سازی باتری معاف است ✅")
            return
        }
        try {
            startActivity(
                Intent(Settings.ACTION_REQUEST_IGNORE_BATTERY_OPTIMIZATIONS)
                    .setData(Uri.parse("package:$packageName"))
            )
        } catch (e: Throwable) {
            startActivity(Intent(Settings.ACTION_IGNORE_BATTERY_OPTIMIZATION_SETTINGS))
        }
    }

    private fun startRefresh() {
        stopRefresh()
        val r = object : Runnable {
            override fun run() {
                refresh()
                ui.postDelayed(this, 3000)
            }
        }
        refresher = r
        ui.post(r)
    }

    private fun stopRefresh() {
        refresher?.let { ui.removeCallbacks(it) }
        refresher = null
    }

    private fun refresh() {
        bg({ Core.get(this).callAttr("status").toString() }) { r ->
            if (tab != 2) return@bg
            r.onSuccess { applyStatus(JSONObject(it)) }
                .onFailure { logView?.text = "خطا: ${it.message}" }
        }
    }

    private fun applyStatus(o: JSONObject) {
        val running = o.getBoolean("running")
        val accs = o.getJSONArray("accounts")
        accountCount = accs.length()
        val on = Core.enabled(this)

        statusView?.apply {
            when {
                on && running -> {
                    text = "🟢 ربات روشن است"
                    setTextColor(cGreen)
                }
                on -> {
                    // گیر کرده؟ هر ۱۰ ثانیه سرویس را دوباره راه بینداز
                    val now = System.currentTimeMillis()
                    if (now - lastKick > 10_000) {
                        lastKick = now
                        ensureService()
                    }
                    text = "🟡 در حال راه‌اندازی..."
                    setTextColor(Color.parseColor("#E0A800"))
                }
                else -> {
                    text = "🔴 ربات خاموش است"
                    setTextColor(cRed)
                }
            }
        }

        val key = (0 until accs.length()).joinToString("|") {
            val a = accs.getJSONObject(it)
            a.getString("name") + ":" + a.getBoolean("connected")
        }
        if (key != lastAccKey) {
            lastAccKey = key
            accountsBox?.removeAllViews()
            if (accs.length() == 0) {
                accountsBox?.addView(label("هنوز اکانتی وارد نشده است.", 14f, color = cSub))
            }
            for (i in 0 until accs.length()) {
                val a = accs.getJSONObject(i)
                accountsBox?.addView(accountRow(a))
            }
        }
        logView?.text = o.getString("log")
        updateToggle()
    }

    private fun accountRow(a: JSONObject): View {
        val name = a.getString("name")
        val connected = a.getBoolean("connected")
        val title = a.optString("label").ifEmpty { name }
        val info = TextView(this).apply {
            text = "$title\n${a.optString("phone")}  •  " + if (connected) "✅ وصل" else "⏳ وصل نیست"
            textSize = 14f
            setTextColor(cText)
        }
        val del = Button(this).apply {
            text = "حذف"
            isAllCaps = false
            setTextColor(Color.WHITE)
            background = rounded(cRed, 10)
            setOnClickListener {
                AlertDialog.Builder(this@MainActivity)
                    .setMessage("اکانت $title حذف شود؟")
                    .setPositiveButton("حذف") { _, _ ->
                        bg({ Core.get(this@MainActivity).callAttr("remove_account", name).toString() }) {
                            lastAccKey = ""
                            refresh()
                        }
                    }
                    .setNegativeButton("نه", null)
                    .show()
            }
        }
        return LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            gravity = Gravity.CENTER_VERTICAL
            background = rounded(cCard)
            setPadding(dp(14), dp(10), dp(10), dp(10))
            layoutParams = lp(8)
            addView(info, LinearLayout.LayoutParams(0, WRAP, 1f))
            addView(del, LinearLayout.LayoutParams(WRAP, WRAP))
        }
    }

    override fun onDestroy() {
        stopRefresh()
        super.onDestroy()
    }
}
