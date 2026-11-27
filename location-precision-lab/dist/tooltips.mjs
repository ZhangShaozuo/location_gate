export function enableTooltips() {
  const tooltip = document.createElement("div");
  tooltip.className = "tooltip";
  tooltip.setAttribute("aria-hidden", "true");
  tooltip.hidden = true;
  document.body.append(tooltip);

  let active;
  let hideTimer;
  let keyboard = true;
  const descriptions = new Map();

  function position() {
    if (!active) return;
    const rect = active.anchor.getBoundingClientRect();
    const viewport = document.documentElement;
    if (rect.bottom < 0 || rect.top > viewport.clientHeight) {
      close();
      return;
    }
    const margin = 12;
    const gap = 6;
    const left = Math.min(rect.left, viewport.clientWidth - tooltip.offsetWidth - margin);
    const below = rect.bottom + gap;
    const above = rect.top - tooltip.offsetHeight - gap;
    const top = below + tooltip.offsetHeight + margin <= viewport.clientHeight ? below : above;
    tooltip.style.left = `${Math.max(margin, left)}px`;
    tooltip.style.top = `${Math.max(margin, top)}px`;
  }

  function close() {
    clearTimeout(hideTimer);
    active?.button?.setAttribute("aria-expanded", "false");
    active = undefined;
    tooltip.hidden = true;
  }

  function show(anchor, description, mode, button) {
    close();
    active = { anchor, description, mode, button };
    button?.setAttribute("aria-expanded", "true");
    tooltip.textContent = description.textContent.trim();
    tooltip.hidden = false;
    position();
  }

  function hideHover() {
    clearTimeout(hideTimer);
    hideTimer = setTimeout(() => {
      if (active?.mode === "hover") close();
    }, 180);
  }

  const observer = new MutationObserver(() => {
    if (!active) return;
    tooltip.textContent = active.description.textContent.trim();
    position();
  });

  for (const control of document.querySelectorAll("[aria-describedby]")) {
    const ids = control.getAttribute("aria-describedby").split(/\s+/);
    const description = ids.map(id => document.getElementById(id)).find(el => el?.hasAttribute("data-help"));
    if (!description) continue;
    const labels = Array.from(control.labels ?? []);
    const targets = new Set([control, ...labels]);
    for (const target of targets) {
      target.addEventListener("pointerenter", event => {
        if (event.pointerType === "touch" || active?.mode === "tap") return;
        show(control, description, "hover");
      });
      target.addEventListener("pointerleave", hideHover);
    }
    control.addEventListener("focus", () => {
      if (keyboard) show(control, description, "focus");
    });
    control.addEventListener("blur", () => {
      if (active?.anchor === control) close();
    });

    const previous = descriptions.get(description);
    if (previous && (previous.labels.length || !labels.length)) continue;
    descriptions.set(description, { control, labels });
  }

  for (const [description, { control, labels }] of descriptions) {
    observer.observe(description, { childList: true, characterData: true, subtree: true });
    const label = labels[0];
    const icon = document.createElement("button");
    icon.type = "button";
    icon.className = "help-toggle";
    icon.textContent = "?";
    const name = control.dataset.helpLabel ?? label?.textContent.trim() ?? control.textContent.trim();
    icon.setAttribute("aria-label", `${name}的说明`);
    icon.setAttribute("aria-describedby", description.id);
    icon.setAttribute("aria-expanded", "false");
    (label ?? control).after(icon);
    icon.addEventListener("click", () => {
      if (active?.button === icon) close();
      else show(icon, description, "tap", icon);
    });
  }

  tooltip.addEventListener("pointerenter", () => clearTimeout(hideTimer));
  tooltip.addEventListener("pointerleave", hideHover);
  document.addEventListener("pointerdown", event => {
    keyboard = false;
    if (active && !active.button?.contains(event.target) && active.mode !== "hover") close();
  });
  document.addEventListener("keydown", event => {
    keyboard = true;
    if (event.key === "Escape" && active) {
      close();
      event.preventDefault();
    }
  });
  window.addEventListener("resize", position);
  document.addEventListener("scroll", position, { capture: true, passive: true });
}
