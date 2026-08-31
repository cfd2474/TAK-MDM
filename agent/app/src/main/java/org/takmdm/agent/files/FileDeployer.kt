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
import android.util.Log
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
            } else {
                val name = entry.optString("file_name").ifBlank { payload.name }
                place(payload, File(destinationDir, name), entry.optString("overwrite", "if_newer"))
            }
            emptyList<String>()
        }.getOrElse { listOf("$fileId: ${it.message ?: it.javaClass.simpleName}") }
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

        ZipFile(archive).use { zip ->
            for (entry in zip.entries()) {
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
        Log.i(TAG, "extracted ${archive.name} into $targetDir")
    }

    /** Key under which an applied file's hash is remembered. */
    fun stateKey(entry: JSONObject): String =
        "${entry.optString("file_id")}|${entry.optString("dest_path")}"

    companion object {
        private const val TAG = "FileDeployer"
    }
}
