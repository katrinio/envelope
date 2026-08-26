const menus = [...document.querySelectorAll(".device-menu")];
const salaryEditor = document.querySelector("[data-salary-editor]");
const deleteDialog = document.querySelector("[data-delete-dialog]");
const deleteDialogCancel = deleteDialog.querySelector("[data-delete-cancel]");
const deleteDialogConfirm = deleteDialog.querySelector("[data-delete-confirm]");
const deleteDialogError = deleteDialog.querySelector(".delete-dialog-error");
let pendingDeleteButton = null;

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

  function closeSalaryEditor() {
    salaryInput.value = salaryEditor.dataset.currentSalary;
    salaryInput.setAttribute("aria-invalid", "false");
    salaryInput.removeAttribute("aria-describedby");
    salaryEditor.querySelector(".salary-error")?.remove();
    salaryForm.hidden = true;
    salaryDisplay.hidden = false;
    salaryDisplay.focus();
  }

  salaryDisplay.addEventListener("click", openSalaryEditor);
  salaryCancel.addEventListener("click", closeSalaryEditor);
  salaryForm.addEventListener("keydown", (event) => {
    if (event.key === "Escape") {
      event.preventDefault();
      closeSalaryEditor();
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
