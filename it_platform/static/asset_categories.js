"use strict";

const groupSelect = document.querySelector("[data-asset-group]");
const typeSelect = document.querySelector("[data-asset-type]");

if (groupSelect && typeSelect) {
  const filterTypes = () => {
    for (const option of typeSelect.options) {
      option.hidden = option.dataset.group !== groupSelect.value;
      option.disabled = option.hidden;
    }
    for (const group of typeSelect.querySelectorAll("optgroup")) {
      group.hidden = !Array.from(group.querySelectorAll("option")).some(option => !option.disabled);
      group.disabled = group.hidden;
    }
    const selected = typeSelect.selectedOptions[0];
    if (!selected || selected.disabled) {
      const first = Array.from(typeSelect.options).find(option => !option.disabled);
      typeSelect.value = first ? first.value : "";
    }
  };
  groupSelect.addEventListener("change", filterTypes);
  filterTypes();
}
