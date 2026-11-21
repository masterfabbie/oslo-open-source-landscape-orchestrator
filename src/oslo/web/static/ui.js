// Small helpers for the interface. Everything works without them; they only make it nicer.
(function () {
  "use strict";

  // Menus: only one open at a time; a click outside closes them.
  var menus = document.querySelectorAll("details.menu");
  menus.forEach(function (menu) {
    menu.addEventListener("toggle", function () {
      if (!menu.open) return;
      menus.forEach(function (other) {
        if (other !== menu) other.open = false;
      });
    });
  });
  document.addEventListener("click", function (event) {
    menus.forEach(function (menu) {
      if (menu.open && !menu.contains(event.target)) menu.open = false;
    });
  });

  // Questions before an action: forms and buttons with data-confirm. The
  // Content-Security-Policy forbids inline handlers, so they are attached here.
  document.addEventListener("submit", function (event) {
    var form = event.target;
    if (form.dataset && form.dataset.confirm && !window.confirm(form.dataset.confirm)) {
      event.preventDefault();
    }
  });
  document.addEventListener("click", function (event) {
    var button = event.target.closest && event.target.closest("button[data-confirm]");
    if (button && !window.confirm(button.dataset.confirm)) event.preventDefault();
  });
})();
