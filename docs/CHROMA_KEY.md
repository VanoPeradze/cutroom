# Chroma Key

Chroma Key removes a chosen color from video source **A or B** and replaces it with a **solid color or ready image from the Media library**. Green is the default key color. Settings are independent for A/B and apply to the chosen source throughout the edit, before framing and Layout. An image covers the source frame and may crop at its edges; the same fit is used in the frame preview and export.

Background video, source B beneath keyed source A and transparent MP4 output are not supported. No AI, model download or external upload is needed.

## Try it on a short section

1. Add footage and create an edit. Open **Studio > Layout > Chroma Key**, below **Stabilize footage**.
2. Select **A** or **B** and enable **Enable chroma key**. Choose the **Color to remove** from your recording.
3. Adjust **Tolerance** to remove a narrower/wider color range and **Edge softness** to blend its boundary. Choose a solid-color or image background. For an image, import it through **Media & audio > Add media**, wait until it is ready and select it in the background selector. It need not be placed as a separate timeline clip. A key can also remove matching clothing or foreground details; inspect those edges.
4. Choose **Apply changes**. Slider/color changes remain unsaved until applied; export uses the saved settings.
5. Seek the selected source to the frame you want to inspect, then choose **Refresh current frame**. This generates a single PNG from the saved settings at that source's current time. Refresh again after seeking or changing settings.
6. Export a short MP4 and watch it. The frame preview and export use the same local FFmpeg key/replacement processing; the normal Layout is applied in export.

**The main player remains Original playback and shows unkeyed footage.** The visible PNG is an explicit processed-frame check, not a live keyed playback preview or a full composition preview. Originals are not overwritten, and Chroma Key does not change audio or timeline timing.

## Reset, history and support

**Reset this source** restores that source's default/off settings. Apply and Reset support **Undo/Redo**. A protected A/B source must be unlocked under **Edit > Track protection** before its key can change.

The tool checks the installed FFmpeg for the required filters. If support is missing, it explains the limitation and blocks enabling the key or refreshing a keyed frame preview. You can still switch off a saved key and apply that change, or use **Reset this source**, to continue exporting without the key. Exporting with an enabled key requires those filters. CUTROOM does not install them automatically.

An image that is missing, still preparing or unavailable reports an error instead of silently switching to a solid color. Choose a ready image or solid-color background, or disable/reset the key before exporting.

[Return to the user guide](USER_GUIDE_EN.md) · [Beta status](BETA_STATUS.md)
