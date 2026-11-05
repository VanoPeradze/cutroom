# Misleading video suffixes

Import metadata now requires both a compatible filename suffix and the actual
MP4/MOV or WebM container reported by FFprobe before marking a recording ready
for direct browser playback. Compatible codecs alone are insufficient: a
Matroska/AVI recording renamed to `.mp4` still needs the existing preview-proxy
path. Originals are not renamed or changed.

This maintenance fix changes only browser-readiness classification. It adds no
AI features, transcription corrections, speaker framing or proposal UI. Existing
Hebrew transcription/meaning uncertainty and beta/platform limitations remain.
