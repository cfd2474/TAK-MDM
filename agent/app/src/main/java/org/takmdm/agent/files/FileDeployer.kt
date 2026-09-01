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

package org.takmdm.agent.files

import android.content.Context
import android.os.Environment
import org.takmdm.agent.diag.AgentLog
import java.io.File
import java.util.zip.ZipFile
import org.json.JSONObject
import org.takmdm.agent.core.AgentConfig

/**
 * Places managed files onto the device, extracting archives where policy says to.
 *
 * All-files access is required for destinations like `/sdcard/atak`, which is not a
 * MediaStore collection. A Device Owner cannot grant that to itself — it is an
 * app-op, not a runtime permission — so the agent asks for it once and reports
 * clearly when it is missing rather than failing obscurely per file.
 */
class FileDeployer(private val context: Context, private val config: AgentConfig) {

    fun hasAllFilesAccess(): Boolean = Environment.isExternalStorageManager()

    /**
     * @return failure messages, empty on success.
     */
    fun deploy(entry: JSONObject, payload: File): List<String> {
        val fileId = entry.optString("file_id")
        val destinationPath = entry.optString("dest_path")
        if (destinationPath.isBlank()) return listOf("$fileId: no destination")

        val destinationDir = resolve(destinationPath)
        // The resolved path, not the one the policy asked for. A destination like
        // "/atak/imagery" resolves to the filesystem root, not external storage,
        // and the difference is invisible until someone goes looking for the file.
        AgentLog.d(
            TAG,
            "$fileId: '$destinationPath' resolves to ${destinationDir.absolutePath} " +
                "(all-files access: ${hasAllFilesAccess()})"
        )
        if (!hasAllFilesAccess() && requiresAllFiles(destinationDir)) {
            return listOf(
                "$fileId: cannot write $destinationPath without all-files access; " +
                    "grant it in the agent"
            )
        }

        return runCatching {
            if (entry.optBoolean("extract")) {
                val target = resolve(
                    entry.optString("extract_to").ifBlank { destinationPath }
                )
                extract(payload, target)
                AgentLog.i(TAG, "$fileId: extracted into ${target.absolutePath}")
            } else {
                val name = entry.optString("file_name").ifBlank { payload.name }
                val destination = File(destinationDir, name)
                place(payload, destination, entry.optString("overwrite", "if_newer"))
                // Report what is actually on disk afterwards rather than that the
                // copy returned without throwing. A silent no-op and a successful
                // write are otherwise indistinguishable.
                AgentLog.i(
                    TAG,
                    if (destination.exists())
                        "$fileId: placed ${destination.absolutePath} (${destination.length()} bytes)"
                    else
                        "$fileId: ${destination.absolutePath} is MISSING after place()"
                )
            }
            emptyList<String>()
        }.getOrElse {
            AgentLog.e(TAG, "$fileId: deployment failed", it)
            listOf("$fileId: ${it.message ?: it.javaClass.simpleName}")
        }
    }

    /**
     * Whether the entry's content is actually on disk where it belongs.
     *
     * Asked because remembering that we once placed a file is not the same as the
     * file being there. A user can delete it, an app can clear its own directory, a
     * card can be swapped — and a reconciler that trusts its own record will report
     * the device compliant with the file missing. Verified on `SM-X520`: deleting a
     * required file left the MDM entirely unaware of it.
     *
     * Size rather than a hash: a full digest of every managed file on every
     * check-in is real work on a tablet, and existence plus length already catches
     * deletion and truncation. Content changes are caught by the recorded hash on
     * the next policy change.
     */
    fun isDeployed(entry: JSONObject, expectedSize: Long): Boolean {
        if (entry.optBoolean("extract")) {
            // An archive lands as many files; "is it still there" would mean
            // tracking every one. Existence of a non-empty target is the honest
            // approximation, and it still catches the directory being wiped.
            val target = resolve(entry.optString("extract_to").ifBlank { entry.optString("dest_path") })
            return target.isDirectory && (target.list()?.isNotEmpty() == true)
        }

        val name = entry.optString("file_name").ifBlank { return false }
        val destination = File(resolve(entry.optString("dest_path")), name)
        return destination.isFile && (expectedSize <= 0 || destination.length() == expectedSize)
    }

    private fun resolve(path: String): File {
        // Treat a leading /sdcard or /storage/emulated/0 as external storage so a
        // policy can use the path an operator would type.
        val external = Environment.getExternalStorageDirectory()
        val normalised = path.replace('\\', '/')
        return when {
            normalised.startsWith("/sdcard/") -> File(external, normalised.removePrefix("/sdcard/"))
            normalised == "/sdcard" -> external
            normalised.startsWith("/storage/emulated/0/") ->
                File(external, normalised.removePrefix("/storage/emulated/0/"))
            normalised.startsWith("/") -> File(normalised)
            else -> File(external, normalised)
        }
    }

    private fun requiresAllFiles(target: File): Boolean {
        val appPrivate = context.getExternalFilesDir(null)?.absolutePath
        return appPrivate == null || !target.absolutePath.startsWith(appPrivate)
    }

    private fun place(payload: File, destination: File, overwrite: String) {
        destination.parentFile?.mkdirs()
        if (destination.exists()) {
            when (overwrite) {
                "if_absent" -> return
                "if_newer" -> if (destination.lastModified() >= payload.lastModified()) return
            }
        }
        payload.copyTo(destination, overwrite = true)
    }

    private fun extract(archive: File, targetDir: File) {
        targetDir.mkdirs()
        val root = targetDir.canonicalFile

        var skipped = 0
        ZipFile(archive).use { zip ->
            for (entry in zip.entries()) {
                if (isArchiverJunk(entry.name)) {
                    skipped++
                    continue
                }
                val output = File(targetDir, entry.name).canonicalFile

                // Zip-slip: an archive entry named ../../something would otherwise
                // write outside the destination. Uploads are admin-curated, but an
                // extractor that trusts entry names is a well-known way to be wrong.
                if (!output.path.startsWith(root.path + File.separator) && output != root) {
                    throw SecurityException("archive entry escapes destination: ${entry.name}")
                }

                if (entry.isDirectory) {
                    output.mkdirs()
                } else {
                    output.parentFile?.mkdirs()
                    zip.getInputStream(entry).use { input ->
                        output.outputStream().use { out -> input.copyTo(out) }
                    }
                }
            }
        }
        AgentLog.i(
            TAG,
            "extracted ${archive.name} into $targetDir" +
                if (skipped > 0) " (skipped $skipped archiver metadata entr${if (skipped == 1) "y" else "ies"})" else ""
        )
    }

    /**
     * Metadata the archiver added, which no device wants unpacked.
     *
     * `__MACOSX` resource forks and `.DS_Store` ride along in every zip built on a
     * Mac, and ATAK data packages routinely are. They are an artifact of the tool
     * rather than anything the operator chose to ship, so they are dropped — but
     * the count is logged, because silently changing what an archive contains is
     * its own kind of surprise.
     */
    private fun isArchiverJunk(name: String): Boolean {
        val normalised = name
        return normalised == "__MACOSX" ||
            normalised.startsWith("__MACOSX/") ||
            normalised.substringAfterLast('/') == ".DS_Store" ||
            normalised.substringAfterLast('/').startsWith("._")
    }

    /** Key under which an applied file's hash is remembered. */
    fun stateKey(entry: JSONObject): String =
        "${entry.optString("file_id")}|${entry.optString("dest_path")}"

    companion object {
        private const val TAG = "FileDeployer"
    }
}
