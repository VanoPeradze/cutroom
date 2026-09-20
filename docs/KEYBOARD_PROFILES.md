# Timeline keyboard profiles

Choose a profile in Studio's **Keyboard shortcuts** controls. The choice is saved on this browser. These are focused editing presets, not full emulations, imported user keymaps, or affiliations with the named applications. The on-screen shortcut list is generated from the resolver actually used by the editor.

## Familiar core controls

| Profile | Select / blade | Split at playhead | Trim start / end | Navigation and zoom |
| --- | --- | --- | --- | --- |
| CUTROOM | V / B; R for range | S | Q / W | Arrows, Home / End; + / −; F fits |
| DaVinci Resolve | A / B | Ctrl/Cmd+B | Toolbar | Arrows, Home / End; Shift+Z fits |
| Adobe Premiere Pro | V / C | Ctrl/Cmd+K | Q / W | Arrows, Home / End; + / −; backslash fits |
| Pro Tools | Toolbar | B | A / S | L / apostrophe for adjacent edits; R / T zoom; Enter returns to start |
| Final Cut Pro | A / B; R for range | Ctrl/Cmd+B | Toolbar | Arrows, Home / End; semicolon / apostrophe for adjacent edits; Shift+Z fits |

Space plays/pauses. Ctrl/Cmd+Z undoes and Ctrl/Cmd+Shift+Z redoes an edit. Pro Tools additionally supports its Commands Keyboard Focus Z / Shift+Z. Resolve, Premiere, Final Cut and CUTROOM support I / O for range boundaries, X for the clip at the playhead, K to stop and L to play forward at normal speed. **Pro Tools does not inherit those NLE bindings**: its I, O, J, K and X have different native meanings and are not reassigned to unrelated actions here.

### Cut twice and remove the section

For ordinary mouse editing, **Select / Move** selects and moves individual cuts; white clip edges trim or reveal more source footage. **Range** marks an interval, and **Remove from video** removes it. To move just that interval, switch to Select / Move and drag inside the selection. Use **Original footage** to see kept/removed source regions and restore missing material. Click or drag the ruler to seek. Snap starts off, so ranges are not limited to AI cut boundaries. These pointer behaviors are CUTROOM's shared workflow, independent of the keyboard preset.

Select **Cut out** in the timeline toolbar (D in the CUTROOM profile). Click the first cut point, then the second. CUTROOM removes the section between them from the edit. The ordinary Blade tool still only splits; it does not silently remove footage. Cut out is toolbar-only in imported profiles so it does not take over a familiar native command such as Final Cut's Shift+B.

While Cut out is active, Enter places its next cut at the playhead instead of running a profile's ordinary Enter command. Escape cancels the pending cut. These are explicit CUTROOM tool-mode controls. Shift+Left/Right on the focused timeline extends its range as another CUTROOM adaptation, not a claim to match another editor's multi-frame stepping.

## Differences to expect

- CUTROOM supports Together (A+B), A only and B only editing scopes, not Pro Tools' complete track-selection system or Slip/Shuffle modes. It also does not implement sample-accurate nudge, clipboard editing or separate edit/timeline selections. Removal closes time in Together; source-only removal can leave a gap on that track. Comma/period move the playhead **one video frame**, not one audio sample. The shortcut help marks these adaptations. See [scope and trim behavior](INDEPENDENT_TRACKS.md).
- No reverse playback or multi-speed J/K/L shuttle is advertised: J is unbound; L starts 1× playback in NLE profiles. Pro Tools L correctly navigates to the previous edit instead.
- Native commands with no implemented equivalent remain unbound; the help displays **Toolbar** for CUTROOM actions without a key. For example, Premiere's Shift+R is not reused for restoring footage. Final Cut's unmodified plus/minus are not reassigned from timecode entry to zoom.
- Resolve's plain Delete and plain plus/minus are retained browser-safe CUTROOM adaptations. Shift+Delete also removes the selected section. Premiere uses Shift+Delete; plain Delete is not turned into a different ripple operation. Final Cut's Mac Delete key is reported by browsers as Backspace; Forward Delete is an additional CUTROOM removal shortcut.
- Final Cut's Command bindings accept Ctrl for Windows users. Premiere's Ctrl+Shift+X clears the range; it is not also assigned to Cmd+Shift+X, which has a different native meaning.
- Alt/Option shortcuts are left to the operating system/browser, including Final Cut's Option+bracket trims. Browser zoom, search, reload, address bar, clipboard, Tab and function keys are not claimed. Pro Tools users can use B instead of Ctrl+E; Premiere and Resolve also have their pointer Blade/Razor tools if a browser reserves their modified split keys.
- Shortcuts do not run while typing in fields, editing captions, using native controls, composing text with an IME, or inside dialogs. Latin keyboard remaps follow the typed letter; Hebrew and other non-Latin letters fall back to the physical key code. Holding an edit, trim, tool or playback key cannot repeatedly apply it. Navigation and zoom can repeat.

## Primary references

Mappings were checked against these official references on 2026-09-06. Commands depend on the original application's page, focus, version and customized keyboard settings; CUTROOM's list above is the implemented subset.

- [Avid Pro Tools Shortcuts Guide 2025.6](https://resources.avid.com/SupportFiles/PT/Pro_Tools_Shortcuts_2025.6.pdf), Commands Keyboard Focus and editing/navigation sections. This establishes the separate A/S/B, R/T, L/apostrophe and Z/Shift+Z vocabulary; CUTROOM's ripple and one-frame behavior are adaptations, not DAW equivalence.
- [Blackmagic Design: The Editor's Guide to DaVinci Resolve 20](https://documents.blackmagicdesign.com/UserManuals/DaVinci-Resolve-20-Editors-Guide.pdf) and [Resolve 18 Editor's Guide](https://documents.blackmagicdesign.com/UserManuals/DaVinciResolveEditorsGuide.pdf), selection/blade and through-edit workflow. [Resolve 20 Fairlight guide](https://documents.blackmagicdesign.com/UserManuals/DaVinci-Resolve-20-Fairlight-Audio-Post.pdf) documents Shift+Z fitting the timeline. Page-specific operations not implemented here remain outside this profile.
- [Adobe Premiere default keyboard shortcuts](https://helpx.adobe.com/premiere/desktop/get-started/keyboard-shortcuts/default-keyboard-shortcuts.html), [editing tools](https://helpx.adobe.com/premiere/desktop/edit-projects/intro-to-editing/edit-video-in-premiere.html), and [dynamic trimming](https://helpx.adobe.com/ee/premiere-pro/how-to/dynamic-trimming.html). These support V/C, modified K, Q/W, marks, and ripple-removal distinctions; CUTROOM's two-source scopes are not Premiere's full multi-track editing system.
- [Apple Final Cut Pro keyboard shortcuts](https://support.apple.com/guide/final-cut-pro/keyboard-shortcuts-ver90ba5929/mac), timeline navigation, selection and tool sections. A/B/R, Command+B, I/O/X and fit/navigation have corresponding CUTROOM operations; magnetic-storyline, skimming and multi-speed playback are not fully emulated.

## Regression checks

`node --test tests/frontend_keyboard.test.cjs` runs the shipped resolver directly without a browser server, media, model inference or network calls. It checks all five presets, incompatible native key meanings, exact modifiers, Hebrew layout fallback, IME/input/dialog protection, held-key behavior, unknown-profile fallback and honest help rows. Pytest includes this harness through `tests/test_keyboard_profiles.py`.
