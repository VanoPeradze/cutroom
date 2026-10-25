## CUTROOM 1.2 Beta — 24 October 2026

This beta publishes the existing frozen application source `ad3259bd19abc5fa1bab3e063fe62caeb1ecf93c` and the exact reviewed archives, without rebuilding them.

### Included improvements
- Source timing and coverage controls distinguish synchronized recordings from independently placed camera footage.
- Explicit two-source layouts report missing camera coverage instead of silently exporting a different composition. Camera footage is never invented, looped or frozen to fill a gap.
- Clearer source/layout controls, long-text wrapping, and corrected frontend cache identifiers.
- The entry document now revalidates while versioned frontend assets retain their cache policy. An ordinary reload may be needed once after updating from an older cached page.
- The integrated beta also retains editable review proposals, transcript alternatives and manual timed framing controls. Review and Apply preserve the current edit until an explicit choice; these are not a guarantee of semantic accuracy or automatic speaker recognition.

### Qualification and accepted beta limits
- **Mac Apple Silicon and Intel:** automated native installation, export and app-restart/project-persistence checks passed on these exact combined-package bytes, with 350 feature tests and zero skips on each architecture. Evidence: https://github.com/VanoPeradze/cutroom/actions/runs/40064653092 (orchestration head `c718be7f1af9a0b5fb61b2102f3b14a681578c67`, distinct from application source).
- **Windows clean installation: NOT COMPLETED.** The isolated Sandbox launcher produced no authenticated guest report within 90 seconds. This is an unresolved Sandbox startup blocker, not a passing Windows installation test or a demonstrated application installation failure. The user explicitly accepted this outstanding gate for this beta; it has been waived for publication, not marked passed.
- Hebrew transcription and semantic selection remain imperfect and require review. Automatic audio-to-visible-speaker framing is not implemented; existing framing controls are manual.
- Physical-device UI/listening acceptance, Windows SmartScreen/download quarantine, Mac Finder/Gatekeeper/Safari and OS reboot persistence are not established by automated checks. No new model or private-media processing was performed for this release.

### Downloads
- Windows: extract `CUTROOM-1.2-Beta-Windows-review-ad3259b.zip`; keep `START CUTROOM.bat`, `START HERE.html` and `App` together. WinGet and Microsoft Visual C++ x64 are prerequisites; first setup downloads dependencies.
- Mac: use `CUTROOM-1.2-Beta-combined-review-ad3259b.zip`, open its **mac** folder, then `START CUTROOM.command` beside `App`. The same combined ZIP also contains a Windows folder. No separately rebuilt standalone Mac ZIP is presented as tested.
- Exact frozen source: `SOURCE-ad3259b.zip`. GitHub's automatically generated source downloads are not installation packages.
- SHA-256 sidecars accompany all three archives. Previous releases and website mirrors are retained for rollback.

בטא: בדיקות Mac עברו; בדיקת התקנה נקייה ב־Windows לא הושלמה ואושרה כחריגה לשחרור זה. הבנת עברית ומעבר אוטומטי בין דוברים עדיין אינם מאומתים/מושלמים.
