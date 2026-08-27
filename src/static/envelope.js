const menus = [...document.querySelectorAll(".device-menu")];
const salaryEditor = document.querySelector("[data-salary-editor]");
const usernameEditor = document.querySelector("[data-username-editor]");
const deleteDialog = document.querySelector("[data-delete-dialog]");
const deleteDialogCancel = deleteDialog.querySelector("[data-delete-cancel]");
const deleteDialogConfirm = deleteDialog.querySelector("[data-delete-confirm]");
const deleteDialogError = deleteDialog.querySelector(".delete-dialog-error");
const historyDialog = document.querySelector("[data-history-dialog]");
const historyBackdrop = document.querySelector("[data-history-backdrop]");
let pendingDeleteButton = null;
let closeSalaryEditor = null;
let closeUsernameEditor = null;

function closeOtherInteractions(except = null) {
  if (closeSalaryEditor && except !== "salary") {
    closeSalaryEditor();
  }
  if (closeUsernameEditor && except !== "username") {
    closeUsernameEditor();
  }
  for (const details of document.querySelectorAll(".adjustment-control[open]")) {
    if (details !== except) {
      details.removeAttribute("open");
    }
  }
  for (const menu of menus) {
    if (menu !== except) {
      closeMenu(menu);
    }
  }
}

if (historyDialog) {
  const closeUrl = historyDialog.dataset.closeUrl;
  // The server renders the panel open so it also works without JavaScript;
  // upgrade it to a modal here to get the native backdrop and focus handling.
  historyDialog.showModal();
  historyDialog.addEventListener("click", (event) => {
    if (event.target === historyDialog) {
      historyDialog.close();
      window.location.href = closeUrl;
    }
  });
  historyBackdrop?.addEventListener("click", () => {
    historyDialog.close();
    window.location.href = closeUrl;
  });
}

if (salaryEditor) {
  const salaryDisplay = salaryEditor.querySelector(".salary-display");
  const salaryForm = salaryEditor.querySelector(".salary-form");
  const salaryInput = salaryEditor.querySelector(".salary-input");
  const salaryCancel = salaryEditor.querySelector("[data-salary-cancel]");

  function openSalaryEditor() {
    salaryDisplay.hidden = true;
    salaryForm.hidden = false;
    salaryInput.focus();
    salaryInput.select();
  }

  closeSalaryEditor = function () {
    salaryInput.value = salaryEditor.dataset.currentSalary;
    salaryInput.setAttribute("aria-invalid", "false");
    salaryInput.removeAttribute("aria-describedby");
    salaryEditor.querySelector(".salary-error")?.remove();
    salaryForm.hidden = true;
    salaryDisplay.hidden = false;
    salaryDisplay.focus();
  };

  salaryDisplay.addEventListener("click", () => {
    closeOtherInteractions("salary");
    openSalaryEditor();
  });
  salaryCancel.addEventListener("click", closeSalaryEditor);
  salaryForm.addEventListener("keydown", (event) => {
    if (event.key === "Escape") {
      event.preventDefault();
      closeSalaryEditor();
    }
  });
}

if (usernameEditor) {
  const usernameDisplay = usernameEditor.querySelector(".username-display");
  const usernameForm = usernameEditor.querySelector(".username-form");
  const usernameInput = usernameEditor.querySelector(".username-input");
  const usernameCancel = usernameEditor.querySelector("[data-username-cancel]");

  function openUsernameEditor() {
    usernameDisplay.hidden = true;
    usernameForm.hidden = false;
    usernameInput.focus();
    usernameInput.select();
  }

  closeUsernameEditor = function () {
    usernameInput.value = usernameEditor.dataset.currentUsername;
    usernameInput.setAttribute("aria-invalid", "false");
    usernameInput.removeAttribute("aria-describedby");
    usernameEditor.querySelector(".username-error")?.remove();
    usernameForm.hidden = true;
    usernameDisplay.hidden = false;
    usernameDisplay.focus();
  };

  usernameDisplay.addEventListener("click", () => {
    closeOtherInteractions("username");
    openUsernameEditor();
  });
  usernameCancel.addEventListener("click", closeUsernameEditor);
  usernameForm.addEventListener("keydown", (event) => {
    if (event.key === "Escape") {
      event.preventDefault();
      closeUsernameEditor();
    }
  });
}

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
    closeOtherInteractions(menu);
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
  deleteButton.addEventListener("click", () => {
    pendingDeleteButton = deleteButton;
    deleteDialogError.hidden = true;
    closeMenu(menu);
    deleteDialog.showModal();
  });
}

for (const details of document.querySelectorAll(".adjustment-control")) {
  details.querySelector("summary").addEventListener("click", () => {
    if (!details.open) {
      closeOtherInteractions(details);
    }
  });
}

deleteDialogCancel.addEventListener("click", () => {
  deleteDialog.close();
});

deleteDialogConfirm.addEventListener("click", async () => {
  if (!pendingDeleteButton) {
    return;
  }

  deleteDialogConfirm.disabled = true;
  try {
    const response = await fetch(pendingDeleteButton.dataset.deleteUrl, {method: "DELETE"});
    if (response.ok) {
      window.location.reload();
      return;
    }
  } catch {
    // The calm local status below handles connection failures too.
  }

  deleteDialogConfirm.disabled = false;
  deleteDialogError.hidden = false;
});

deleteDialog.addEventListener("close", () => {
  deleteDialogConfirm.disabled = false;
  deleteDialogError.hidden = true;
  pendingDeleteButton = null;
});

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
