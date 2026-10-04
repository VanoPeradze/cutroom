// Edit protection is not visibility or audio mute. The server enforces locks;
// these controls make that protection understandable before a user edits.
export function lockedSources(project, target = "edit") {
  return ["A", "B"].filter(slot => project?.sources?.[slot]
    && project?.manual?.track_locks?.[slot] === true && (target === "edit" || target === slot));
}

export function initTrackProtection({ document, getProject, busy, change }) {
  const panel = document.getElementById("trackProtection");
  if (!panel) return null;
  const status = document.getElementById("trackProtectionStatus");
  const summary = document.getElementById("trackProtectionSummary");
  const buttons = ["A", "B"].map(slot => document.getElementById(`trackLock${slot}`));
  let pending = null;
  const render = () => {
    const project = getProject(), locks = lockedSources(project);
    panel.hidden = !project?.draft;
    summary.textContent = locks.length ? `${locks.join(" + ")} locked` : "Unlocked";
    buttons.forEach((button, i) => {
      const slot = ["A", "B"][i], locked = locks.includes(slot);
      button.hidden = !project?.sources?.[slot];
      button.disabled = !project?.draft || Boolean(pending) || busy();
      button.textContent = `${locked ? "Unlock" : "Lock"} ${slot}`;
      button.setAttribute("aria-pressed", String(locked));
      button.title = locked ? `Allow edits to source ${slot}` : `Protect source ${slot} clips from editing. Playback and export stay enabled.`;
    });
    status.textContent = pending?.projectId === project?.id ? "Saving protection…"
      : locks.length ? `${locks.join(" + ")} protected. Choose an unlocked source to edit, or unlock here. Together edits cannot change a protected source.`
      : "Lock a finished source to avoid accidental cuts, moves or trims. Locks do not mute or hide footage.";
  };
  buttons.forEach((button, i) => button.addEventListener("click", async () => {
    const project = getProject(), slot = ["A", "B"][i];
    if (pending || busy() || !project?.draft || !project.sources?.[slot]) return;
    const request = { projectId: project.id };
    pending = request; render();
    let saved = false;
    try { saved = Boolean(await change(slot, !lockedSources(project).includes(slot))); }
    catch { /* The editor reports API failures; retain the actual saved lock. */ }
    finally {
      if (pending === request) pending = null;
      render();
      if (!saved && getProject()?.id === project.id) status.textContent = "Protection was not changed. Please try again.";
    }
  }));
  render();
  return { render, lockedNames: target => lockedSources(getProject(), target) };
}
