package ir.parsa.bot

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent

/** بعد از ریستارت گوشی، اگه ربات روشن بوده دوباره بالا میاد */
class BootReceiver : BroadcastReceiver() {
    override fun onReceive(context: Context, intent: Intent?) {
        if (intent?.action == Intent.ACTION_BOOT_COMPLETED && Core.enabled(context)) {
            try {
                context.startForegroundService(Intent(context, BotService::class.java))
            } catch (_: Throwable) {
            }
        }
    }
}
