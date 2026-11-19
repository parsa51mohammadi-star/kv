package ir.parsa.bot

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.app.Service
import android.content.Intent
import android.content.pm.ServiceInfo
import android.net.wifi.WifiManager
import android.os.Build
import android.os.Handler
import android.os.IBinder
import android.os.Looper
import android.os.PowerManager
import android.util.Log
import java.util.concurrent.Executors
import java.util.concurrent.TimeUnit

/**
 * سرویس پیش‌زمینه: تا وقتی روشنه، حتی با بسته شدن اپ، ربات زنده می‌مونه.
 * همه‌ی کارهای پایتون (روشن/خاموش) روی یک ترد واحد و پشت سر هم اجرا می‌شن
 * تا روشن/خاموش سریع، ربات‌های دوتایی و زامبی درست نکنه.
 */
class BotService : Service() {

    companion object {
        const val ACTION_STOP = "ir.parsa.bot.STOP"
        private const val CHANNEL = "bot_running"
        private const val NOTIF_ID = 1
        private const val TAG = "ParsaBot"
    }

    private var wakeLock: PowerManager.WakeLock? = null
    private var wifiLock: WifiManager.WifiLock? = null
    private val main = Handler(Looper.getMainLooper())
    private val worker = Executors.newSingleThreadScheduledExecutor { r ->
        Thread(r, "bot-service-worker").apply { isDaemon = true }
    }
    private var watchdogStarted = false

    override fun onBind(intent: Intent?): IBinder? = null

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        if (intent?.action == ACTION_STOP) {
            // نوتیف را سریع برمی‌داریم ولی تا خاموش شدن کامل پایتون، قفل‌ها را نگه می‌داریم
            try {
                stopForeground(STOP_FOREGROUND_REMOVE)
            } catch (_: Throwable) {
            }
            worker.execute {
                try {
                    Core.get(applicationContext).callAttr("stop_bot")
                } catch (e: Throwable) {
                    Log.e(TAG, "stop_bot failed", e)
                }
                // stopSelf(startId) فقط وقتی سرویس را می‌بندد که بعد از این استارت جدیدی نیامده باشد
                main.post {
                    if (!Core.enabled(this)) releaseLocks()
                    stopSelf(startId)
                }
            }
            return START_NOT_STICKY
        }

        if (!Core.enabled(this)) {
            stopSelf(startId)
            return START_NOT_STICKY
        }

        ensureChannel()
        val notification = buildNotification()
        try {
            if (Build.VERSION.SDK_INT >= 34) {
                startForeground(NOTIF_ID, notification, ServiceInfo.FOREGROUND_SERVICE_TYPE_SPECIAL_USE)
            } else {
                startForeground(NOTIF_ID, notification)
            }
        } catch (e: Throwable) {
            Log.e(TAG, "startForeground failed", e)
            stopSelf(startId)
            return START_NOT_STICKY
        }

        acquireLocks()
        worker.execute { startBotWithRetry() }
        startWatchdog()
        return START_STICKY
    }

    /** اگه پایتون بالا نیومد چند بار دوباره تلاش می‌کنه (قبلا خطا بی‌صدا قورت داده می‌شد) */
    private fun startBotWithRetry() {
        var attempt = 0
        while (attempt < 5) {
            if (!Core.enabled(this)) return
            try {
                Core.get(applicationContext).callAttr("start_bot")
                return
            } catch (e: Throwable) {
                Log.e(TAG, "start_bot failed (attempt $attempt)", e)
                attempt++
                try {
                    Thread.sleep(2000L * attempt)
                } catch (_: InterruptedException) {
                    return
                }
            }
        }
    }

    /** هر ۶۰ ثانیه: اگه باید روشن باشه، start_bot را دوباره صدا می‌زند (تکراری بی‌ضرر است و تسک‌های مرده را بالا می‌آورد) */
    private fun startWatchdog() {
        if (watchdogStarted) return
        watchdogStarted = true
        worker.scheduleWithFixedDelay({
            try {
                if (Core.enabled(this)) {
                    acquireLocks()
                    Core.get(applicationContext).callAttr("start_bot")
                }
            } catch (e: Throwable) {
                Log.e(TAG, "watchdog failed", e)
            }
        }, 60, 60, TimeUnit.SECONDS)
    }

    private fun acquireLocks() {
        try {
            if (wakeLock?.isHeld != true) {
                val pm = getSystemService(PowerManager::class.java)
                wakeLock = pm.newWakeLock(PowerManager.PARTIAL_WAKE_LOCK, "ParsaBot:run").apply {
                    setReferenceCounted(false)
                    acquire()
                }
            }
            if (wifiLock?.isHeld != true) {
                val wm = applicationContext.getSystemService(WIFI_SERVICE) as WifiManager
                @Suppress("DEPRECATION")
                wifiLock = wm.createWifiLock(WifiManager.WIFI_MODE_FULL_HIGH_PERF, "ParsaBot:wifi").apply {
                    setReferenceCounted(false)
                    acquire()
                }
            }
        } catch (_: Throwable) {
        }
    }

    private fun releaseLocks() {
        try {
            wakeLock?.let { if (it.isHeld) it.release() }
            wifiLock?.let { if (it.isHeld) it.release() }
        } catch (_: Throwable) {
        }
    }

    private fun ensureChannel() {
        val nm = getSystemService(NotificationManager::class.java)
        if (nm.getNotificationChannel(CHANNEL) == null) {
            nm.createNotificationChannel(
                NotificationChannel(CHANNEL, "ربات پارسا", NotificationManager.IMPORTANCE_LOW)
            )
        }
    }

    private fun buildNotification(): Notification {
        val open = PendingIntent.getActivity(
            this, 0, Intent(this, MainActivity::class.java), PendingIntent.FLAG_IMMUTABLE
        )
        return Notification.Builder(this, CHANNEL)
            .setContentTitle("ربات پارسا روشن است")
            .setContentText("ربات در پس‌زمینه در حال اجراست")
            .setSmallIcon(android.R.drawable.stat_notify_sync)
            .setContentIntent(open)
            .setOngoing(true)
            .build()
    }

    /** وقتی اپ از لیست اخیر پاک شد سرویس باید زنده بماند؛ فقط قفل‌ها را دوباره مطمئن می‌شویم */
    override fun onTaskRemoved(rootIntent: Intent?) {
        if (Core.enabled(this)) acquireLocks()
        super.onTaskRemoved(rootIntent)
    }

    override fun onDestroy() {
        releaseLocks()
        worker.shutdown()
        super.onDestroy()
    }
}
