# Green screen / Chroma key

Remove a chosen color from a project video. A **Media video can reveal the moving video and earlier layers underneath**; A/B and Media videos can also use a solid color or ready image background. Green is the default key color. The tool needs an existing edit, without AI, model downloads or external uploads.

Each video keeps its own settings. An imported video's key applies to every timeline use before placement. Choosing another video does not copy its key. Same-named files remain separate targets. An image background fills the chosen video's frame and can crop at its edges. Existing saved color/image settings retain their original behavior.

For a moving background, keep it as main footage and add the green-screen foreground through **Media > Add media**, then place it on the timeline. The green-screen Media layer sits above the main edit and earlier Media layers. Select **Video underneath (Media layer)**. Direct A/B transparent compositing is not available; import the foreground in Media for this workflow. The final MP4 is the opaque composite, not an alpha-channel file.

## Try it on a short section

1. Add footage and create an edit. Open **Layout > Green screen / Chroma key**. The controls are visible in Layout rather than hidden behind a folded tool.
2. Select **1 · Foreground video** by its name and thumbnail. A source role and short ID distinguish same-named files. The selected Media clip is used when opening Layout; reopening prefers the video with a saved key. **Add video in Media** opens the normal file importer. Wait for preparation, then add an imported video to the timeline to include it in playback/export.
3. Enable chroma key and choose **2 · Background**: **Video underneath** for a Media overlay, or **Color or image**. For an image, import it in Media first, then choose it in Replacement background. It need not be a timeline clip.
4. Choose **3 · Color to remove**, then adjust Tolerance and Edge softness. **Use green-screen defaults** starts at green, 12% tolerance and 8% softness, with Video underneath for Media. Very high tolerance can erase the subject too; 100% can remove the entire image. A warning explains this. Changes stay unsaved until applied.
5. Choose **Apply & preview**. The saved key appears in **Edited video** playback and a processed frame is refreshed automatically. Apply supports Undo. Original footage mode intentionally shows the original recording.
6. For A/B, seek the source player. For imported video, choose **Frame time (source seconds)**, then **Refresh current frame**. Checkerboard in the processed frame marks transparency to the video underneath. This PNG uses the native-size FFmpeg key used for export; live browser playback approximates it and edges can differ after decoding/downscaling.
7. Export a short MP4 and watch it. The processed frame checks the selected video before composition; playback/export also apply Layout and Media placement. Later Media clips appear above earlier ones.

Original files are not overwritten. Keying does not change audio or timeline timing. If live browser keying is unavailable, the player labels the fallback and the processed frame remains available for checking the result.

## Reset, history and support

**Reset this source** restores only the selected video's default/off settings. Apply and Reset support **Undo/Redo**, and saved per-video settings survive reopening. A protected A/B source must be unlocked under **Edit > Track protection** before its key can change. Imported videos retain their independent Media timeline placement.

Preparing, failed or missing videos cannot accept a key or generate a processed frame. Wait for preparation, retry a failed import, or select another available video. A missing target is not silently replaced by a different file with the same name.

The tool checks installed FFmpeg for the required filters. If support is missing, it explains the limitation and blocks enabling the key or refreshing a keyed frame. You can still disable a saved key or use **Reset this source** to export without it. CUTROOM does not install these filters automatically.

A missing, preparing or unavailable background image reports an error instead of silently switching to a solid color. Choose a ready image or solid-color background, or disable/reset the key before exporting.

[Return to the user guide](USER_GUIDE_EN.md) · [Beta status](BETA_STATUS.md)
