const menus = [...document.querySelectorAll(".device-menu")];

function closeMenu(menu, restoreFocus = false) {
  const trigger = menu.querySelector(".device-menu-trigger");
  const popup = menu.querySelector(".device-menu-popup");
  trigger.setAttribute("aria-expanded", "false");
  popup.hidden = true;
  if (restoreFocus) {
    trigger.focus();
  }
}

function openMenu(menu, focusFirstItem = false) {
  for (const otherMenu of menus) {
    if (otherMenu !== menu) {
      closeMenu(otherMenu);
    }
  }

  const trigger = menu.querySelector(".device-menu-trigger");
  const popup = menu.querySelector(".device-menu-popup");
  trigger.setAttribute("aria-expanded", "true");
  popup.hidden = false;
  if (focusFirstItem) {
    popup.querySelector('[role="menuitem"]').focus();
  }
}

for (const menu of menus) {
  const trigger = menu.querySelector(".device-menu-trigger");
  const popup = menu.querySelector(".device-menu-popup");
  const items = [...popup.querySelectorAll('[role="menuitem"]')];

  trigger.addEventListener("click", () => {
    if (popup.hidden) {
      openMenu(menu);
    } else {
      closeMenu(menu);
    }
  });

  trigger.addEventListener("keydown", (event) => {
    if (event.key === "ArrowDown") {
      event.preventDefault();
      openMenu(menu, true);
    }
  });

  popup.addEventListener("keydown", (event) => {
    if (event.key === "Escape") {
      event.preventDefault();
      closeMenu(menu, true);
      return;
    }

    const currentIndex = items.indexOf(document.activeElement);
    if (event.key === "ArrowDown" || event.key === "ArrowUp") {
      event.preventDefault();
      const direction = event.key === "ArrowDown" ? 1 : -1;
      const nextIndex = (currentIndex + direction + items.length) % items.length;
      items[nextIndex].focus();
    }
  });

  const deleteButton = popup.querySelector("[data-delete-envelope]");
  deleteButton.addEventListener("click", async () => {
    deleteButton.disabled = true;
    try {
      const response = await fetch(deleteButton.dataset.deleteUrl, {method: "DELETE"});
      if (response.ok) {
        window.location.reload();
        return;
      }
    } catch {
      // The calm local status below handles connection failures too.
    }

    deleteButton.disabled = false;
    popup.querySelector(".device-menu-error").hidden = false;
  });
}

document.addEventListener("click", (event) => {
  for (const menu of menus) {
    if (!menu.contains(event.target)) {
      closeMenu(menu);
    }
  }
});

document.addEventListener("keydown", (event) => {
  if (event.key !== "Escape") {
    return;
  }
  for (const menu of menus) {
    if (!menu.querySelector(".device-menu-popup").hidden) {
      closeMenu(menu, true);
    }
  }
});
