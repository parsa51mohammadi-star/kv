package ir.parsa.bot

import android.content.Context
import com.chaquo.python.PyObject
import com.chaquo.python.Python

/** دسترسی مشترک به هسته‌ی پایتونی و وضعیت روشن/خاموش (برای اکتیویتی، سرویس و بوت) */
object Core {
    private var module: PyObject? = null

    @Synchronized
    fun get(ctx: Context): PyObject {
        module?.let { return it }
        val m = Python.getInstance().getModule("bot_core")
        m.callAttr("init", ctx.applicationContext.filesDir.absolutePath)
        module = m
        return m
    }

    private fun prefs(ctx: Context) =
        ctx.applicationContext.getSharedPreferences("bot", Context.MODE_PRIVATE)

    fun enabled(ctx: Context): Boolean = prefs(ctx).getBoolean("enabled", false)

    fun setEnabled(ctx: Context, value: Boolean) {
        prefs(ctx).edit().putBoolean("enabled", value).apply()
    }
}
