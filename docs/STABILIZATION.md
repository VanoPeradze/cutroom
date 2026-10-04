# Local footage stabilization

In **Media**, open **Stabilize footage**, choose source A or B, and select **Create stabilized copy**. CUTROOM makes a separate video asset with two local FFmpeg passes. Download the finished copy or add it as extra footage from the media library. It does not replace your original sources, change your existing edit, use AI, or upload media.

Stabilization smooths camera movement and may zoom/crop the edges. It cannot repair every kind of shake, motion blur or rolling shutter. Review the copy before using it.

The action checks the **FFmpeg executable configured for this CUTROOM installation** for `vidstabdetect` and `vidstabtransform`. It is unavailable when that build lacks either filter; no dependency or cloud service is installed automatically. The existing Windows FFmpeg 7.1.1 build was tested locally. Mac and Linux builds must pass the same runtime check; they have not been manually validated for this feature here.

Progress appears in the existing job controls. **Stop process** cancels processing and removes its unfinished output. A failed or cancelled copy can be retried in the media library. If the original source has changed, start a new copy of the current source instead. Ready copies remain available after reopening the project.

Video and audio timing are preserved within the supported media/output timing checks. Compatible audio is copied; other codecs are converted to AAC for the MP4 copy. Preview media is a separate editor proxy; the download link returns the full stabilized file.
