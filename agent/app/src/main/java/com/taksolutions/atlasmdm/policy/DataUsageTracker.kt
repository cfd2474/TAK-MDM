/*
 * Copyright 2026 TAK-Solutions LLC
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *     http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */

package com.taksolutions.atlasmdm.policy

import android.app.NotificationManager
import android.app.usage.NetworkStats
import android.app.usage.NetworkStatsManager
import android.content.Context
import android.content.pm.PackageManager
import android.net.ConnectivityManager
import androidx.core.app.NotificationCompat
import com.taksolutions.atlasmdm.R
import com.taksolutions.atlasmdm.core.AgentConfig
import com.taksolutions.atlasmdm.diag.AgentLog
import com.taksolutions.atlasmdm.ui.AlertOverlay
import org.json.JSONArray
import org.json.JSONObject

/**
 * Reads how much data the device and its apps have used, and warns when a policy's
 * threshold is crossed (W44).
 *
 * **Only the reading half of NETWORK_DATA_USE is implementable.** There is no AOSP
 * Device Owner API to *block* Wi-Fi, mobile or per-app data — the server refuses to
 * store those fields for that reason, so nothing here needs to enforce them
 * (Android reference §W43).
 *
 * ⚠️ Two traps, both recorded in the platform reference:
 *
 * 1. The non-deprecated `NetworkTemplate` overloads are `@SystemApi`, so this must
 *    use the `int networkType` ones and their deprecated `TYPE_MOBILE` /
 *    `TYPE_WIFI` constants. That is the supported path for an ordinary app, not an
 *    oversight to tidy up.
 * 2. A `null` bucket means **"you may not have this"**, not "no data used". Treating
 *    it as zero would leave every threshold permanently un-crossed and look exactly
 *    like a device that never touches the network, so it is reported as an error.
 */
class DataUsageTracker(private val context: Context) {

    private val config: AgentConfig by lazy { AgentConfig(context) }

    private val stats: NetworkStatsManager? =
        context.getSystemService(NetworkStatsManager::class.java)

    /**
     * Evaluate the policy's thresholds and warn on anything newly crossed.
     *
     * @return failures to report as `apply_errors`, empty when all is well.
     */
    @Suppress("DEPRECATION") // TYPE_MOBILE / TYPE_WIFI: see the class comment.
    fun reconcile(spec: JSONObject): List<String> {
        val failures = mutableListOf<String>()

        // Absent or switched off means "do not account", which is different from
        // "no thresholds": tracking off must not silently keep warning.
        if (!spec.optBoolean("track_usage", false)) {
            config.forgetDataUsageWarningsExcept(emptySet())
            return failures
        }

        val manager = stats ?: return listOf(
            "data usage: NetworkStatsManager unavailable on this device"
        )

        val now = System.currentTimeMillis()
        val resetDailyAt = spec.optString("reset_daily_at").takeIf { it.isNotBlank() }
        val resetMonthlyOnDay = spec.optInt("reset_monthly_on_day").takeIf {
            spec.has("reset_monthly_on_day")
        }

        val rules = readRules(spec)
        val liveKeys = mutableSetOf<String>()

        for (rule in rules) {
            val window = DataUsagePlan.windowFor(
                rule.period, now, resetDailyAt, resetMonthlyOnDay
            )
            val key = DataUsagePlan.notifiedKey(rule, window)
            liveKeys += key

            val used = runCatching {
                if (rule.packageName == null) deviceBytes(manager, rule.metric, window)
                else appBytes(manager, rule.packageName, rule.metric, window)
            }.getOrElse { failure ->
                failures += "data usage: ${rule.describe()} could not be read - ${failure.message}"
                null
            } ?: continue

            if (!DataUsagePlan.isCrossed(rule, used)) continue
            if (key in config.dataUsageWarned) continue

            warn(rule, used)
            config.recordDataUsageWarning(key)
        }

        // Windows that have rolled over can never be warned about again, so their
        // keys are dead weight in a preference that would otherwise grow forever.
        config.forgetDataUsageWarningsExcept(liveKeys)
        return failures
    }

    /** A compact usage summary for the check-in, so the console can show it later. */
    @Suppress("DEPRECATION")
    fun snapshot(spec: JSONObject): JSONObject? {
        if (!spec.optBoolean("track_usage", false)) return null
        val manager = stats ?: return null

        val window = DataUsagePlan.windowFor(
            DataUsagePlan.Period.MONTHLY,
            System.currentTimeMillis(),
            spec.optString("reset_daily_at").takeIf { it.isNotBlank() },
            spec.optInt("reset_monthly_on_day").takeIf { spec.has("reset_monthly_on_day") },
        )

        return runCatching {
            JSONObject()
                .put("window_start", window.start)
                .put("window_end", window.end)
                .put("mobile_bytes", deviceBytes(manager, DataUsagePlan.Metric.MOBILE_DATA, window))
                .put("wifi_bytes", deviceBytes(manager, DataUsagePlan.Metric.WIFI_DATA, window))
        }.getOrElse {
            AgentLog.w(TAG, "usage snapshot unavailable: ${it.message}")
            null
        }
    }

    // ----------------------------------------------------------------------- //
    // Reading
    // ----------------------------------------------------------------------- //

    @Suppress("DEPRECATION")
    private fun deviceBytes(
        manager: NetworkStatsManager,
        metric: DataUsagePlan.Metric,
        window: DataUsagePlan.Window,
    ): Long = transportsFor(metric).sumOf { transport ->
        // subscriberId null: documented as "usage for all mobile networks", and the
        // real value needs privileged access we do not have (API 29+).
        val bucket = manager.querySummaryForDevice(transport, null, window.start, window.end)
            ?: throw IllegalStateException(
                "querySummaryForDevice returned null - the Device Owner stats " +
                    "exemption does not apply on this firmware"
            )
        bucket.rxBytes + bucket.txBytes
    }

    @Suppress("DEPRECATION")
    private fun appBytes(
        manager: NetworkStatsManager,
        packageName: String,
        metric: DataUsagePlan.Metric,
        window: DataUsagePlan.Window,
    ): Long {
        val uid = uidOf(packageName)
            ?: throw IllegalStateException("$packageName is not installed")

        return transportsFor(metric).sumOf { transport ->
            var total = 0L
            manager.queryDetailsForUid(transport, null, window.start, window.end, uid).use { s ->
                val bucket = NetworkStats.Bucket()
                while (s.hasNextBucket()) {
                    s.getNextBucket(bucket)
                    total += bucket.rxBytes + bucket.txBytes
                }
            }
            total
        }
    }

    @Suppress("DEPRECATION")
    private fun transportsFor(metric: DataUsagePlan.Metric): List<Int> = when (metric) {
        DataUsagePlan.Metric.MOBILE_DATA -> listOf(ConnectivityManager.TYPE_MOBILE)
        DataUsagePlan.Metric.WIFI_DATA -> listOf(ConnectivityManager.TYPE_WIFI)
        DataUsagePlan.Metric.TOTAL_DATA ->
            listOf(ConnectivityManager.TYPE_MOBILE, ConnectivityManager.TYPE_WIFI)
    }

    private fun uidOf(packageName: String): Int? = runCatching {
        context.packageManager.getApplicationInfo(packageName, 0).uid
    }.getOrElse { if (it is PackageManager.NameNotFoundException) null else throw it }

    // ----------------------------------------------------------------------- //
    // Warning
    // ----------------------------------------------------------------------- //

    private fun warn(rule: DataUsagePlan.Rule, usedBytes: Long) {
        val manager = context.getSystemService(NotificationManager::class.java) ?: return

        val subject = rule.packageName?.let { labelFor(it) }
            ?: context.getString(R.string.data_usage_subject_device)
        val text = context.getString(
            R.string.data_usage_warning_text,
            subject,
            DataUsagePlan.formatMb(usedBytes),
            rule.thresholdMb.toString(),
        )

        val title = context.getString(R.string.data_usage_warning_title)

        manager.notify(
            // Stable per rule, so a re-warned threshold replaces its own old
            // notification instead of stacking a second one beside it.
            DataUsagePlan.notifiedKey(rule, DataUsagePlan.Window(0, 0)).hashCode(),
            NotificationCompat.Builder(context, CHANNEL)
                .setSmallIcon(android.R.drawable.stat_sys_warning)
                .setContentTitle(title)
                .setContentText(text)
                .setStyle(NotificationCompat.BigTextStyle().bigText(text))
                .setAutoCancel(true)
                .build()
        )

        // Posted as well as the notification, never instead of it: the platform
        // reserves the right to move or hide an overlay at any time, so the
        // notification stays as the durable copy (W45).
        val overlaid = AlertOverlay.show(context, title, text)

        AgentLog.i(
            TAG,
            "data usage warning raised: ${rule.describe()} at " +
                "${DataUsagePlan.formatMb(usedBytes)} (overlay=$overlaid)",
        )
    }

    private fun labelFor(packageName: String): String = runCatching {
        val pm = context.packageManager
        pm.getApplicationLabel(pm.getApplicationInfo(packageName, 0)).toString()
    }.getOrDefault(packageName)

    // ----------------------------------------------------------------------- //

    private fun readRules(spec: JSONObject): List<DataUsagePlan.Rule> {
        val rules = mutableListOf<DataUsagePlan.Rule>()
        rules += parse(spec.optJSONArray("notify_rules"), perApp = false)
        rules += parse(spec.optJSONArray("app_notify_rules"), perApp = true)
        return rules
    }

    private fun parse(array: JSONArray?, perApp: Boolean): List<DataUsagePlan.Rule> {
        if (array == null) return emptyList()
        val rules = mutableListOf<DataUsagePlan.Rule>()
        for (i in 0 until array.length()) {
            val row = array.optJSONObject(i) ?: continue
            val threshold = row.optLong("threshold_mb").takeIf { it > 0 } ?: continue
            val packageName = row.optString("package_name").takeIf { it.isNotBlank() }
            if (perApp && packageName == null) continue
            rules += DataUsagePlan.Rule(
                period = DataUsagePlan.period(row.optInt("period", 2)),
                metric = DataUsagePlan.metric(row.optInt("metric", 0)),
                thresholdMb = threshold,
                packageName = packageName,
            )
        }
        return rules
    }

    private fun DataUsagePlan.Rule.describe(): String =
        "${packageName ?: "device"} ${metric.name.lowercase()} ${period.name.lowercase()} ${thresholdMb}MB"

    companion object {
        private const val TAG = "DataUsage"

        /**
         * ⚠️ **The `_v2` is load-bearing.** Channel importance is very nearly
         * immutable: `createNotificationChannel` documents that *"the importance of
         * an existing channel will only be changed if the new importance is **lower**
         * than the current value"*, and deleting it does not help either — *"if you
         * create a new channel with this same id, the deleted channel will be
         * un-deleted with all of the same settings it had before"*.
         *
         * v51 shipped this channel at `IMPORTANCE_DEFAULT`, which does not raise a
         * heads-up over a fullscreen app — the warning landed silently in the shade
         * and was reported as "no notification appeared". Raising it to HIGH on the
         * original id would have been a **no-op on every device that already ran
         * v51**, which is precisely the fleet that matters. A new id is the only
         * way. Never re-point this at the old id, and bump the suffix again rather
         * than trying to raise importance in place.
         */
        const val CHANNEL = "takmdm_data_usage_v2"

        /** v51's channel, replaced because its importance could not be raised. */
        const val LEGACY_CHANNEL = "takmdm_data_usage"
    }
}
