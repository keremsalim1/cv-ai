(frameIndex) => {
  const CONTROL_ROLES = new Set(['combobox', 'listbox', 'textbox', 'searchbox',
    'checkbox', 'radio', 'switch', 'spinbutton', 'slider', 'option',
    'file', 'password']);
  const LANDMARK_ROLES = new Set(['banner', 'navigation', 'search',
    'contentinfo', 'main', 'form', 'dialog']);

  function* walk(root) {
    for (const el of root.querySelectorAll('*')) {
      yield el;
      if (el.shadowRoot) yield* walk(el.shadowRoot);
    }
  }

  function parentOf(node) {
    if (node.parentElement) return node.parentElement;
    const r = node.getRootNode();
    return r && r.host ? r.host : null;
  }

  function textOf(el) {
    return el ? (el.textContent || '').trim().replace(/\s+/g, ' ') : '';
  }

  function byId(el, id) {
    const r = el.getRootNode();
    return r.getElementById ? r.getElementById(id) : document.getElementById(id);
  }

  function labelledbyText(el) {
    const ids = (el.getAttribute('aria-labelledby') || '').split(/\s+/).filter(Boolean);
    return ids.map((id) => textOf(byId(el, id))).filter(Boolean).join(' ');
  }

  function labelText(el) {
    if (el.labels && el.labels.length) return textOf(el.labels[0]);
    if (el.id) {
      const r = el.getRootNode();
      const l = r.querySelector && r.querySelector(`label[for="${CSS.escape(el.id)}"]`);
      if (l) return textOf(l);
    }
    let p = parentOf(el);
    while (p) {
      if (p.tagName === 'LABEL') return textOf(p);
      if (p.tagName === 'FIELDSET') {
        const lg = p.querySelector('legend');
        if (lg) return textOf(lg);
      }
      p = parentOf(p);
    }
    return '';
  }

  function implicitRole(el) {
    const tag = el.tagName.toLowerCase();
    if (tag === 'textarea') return 'textbox';
    if (tag === 'select') return el.multiple ? 'listbox' : 'combobox';
    // <option> deliberately has no implicit role here: a native country select
    // would otherwise contribute 200 entries. Only an explicit role="option",
    // which is how custom popups mark their choices, is collected.
    if (tag !== 'input') return '';
    // file and password are not ARIA roles; we carry them as pseudo-roles so
    // the Python side can type and drop them without re-reading the tag
    const byType = {
      checkbox: 'checkbox', radio: 'radio', file: 'file', password: 'password',
      number: 'spinbutton', search: 'searchbox', range: 'slider',
      submit: '', button: '', hidden: '', image: '', reset: '',
    };
    const t = (el.getAttribute('type') || 'text').toLowerCase();
    return t in byType ? byType[t] : 'textbox';
  }

  function landmarkOf(el) {
    let node = parentOf(el);
    while (node) {
      const role = (node.getAttribute('role') || '').toLowerCase();
      if (LANDMARK_ROLES.has(role)) return role;
      if (node.getAttribute('aria-modal') === 'true') return 'dialog';
      const tag = node.tagName.toLowerCase();
      if (tag === 'nav') return 'navigation';
      if (tag === 'header') return 'banner';
      if (tag === 'footer') return 'contentinfo';
      if (tag === 'main') return 'main';
      if (tag === 'form') return 'form';
      if (tag === 'dialog' && node.hasAttribute('open')) return 'dialog';
      node = parentOf(node);
    }
    return '';
  }

  function isVisible(el) {
    if (!el.getClientRects().length) return false;
    const s = getComputedStyle(el);
    return s.visibility !== 'hidden' && s.display !== 'none';
  }

  function optionsOf(el) {
    if (el.tagName === 'SELECT') {
      return [...el.options].map(textOf).filter(Boolean);
    }
    const owns = el.getAttribute('aria-controls') || el.getAttribute('aria-owns');
    const box = owns ? byId(el, owns) : null;
    return box ? [...box.querySelectorAll('[role=option]')].map(textOf).filter(Boolean) : [];
  }

  let n = 0;
  const out = [];
  for (const el of walk(document)) {
    const role = (el.getAttribute('role') || '').toLowerCase() || implicitRole(el);
    if (!CONTROL_ROLES.has(role)) continue;
    const ref = frameIndex + '-' + (++n);
    el.setAttribute('data-cvai-ref', ref);
    out.push({
      ref: ref,
      frame: frameIndex,
      tag: el.tagName.toLowerCase(),
      type: (el.getAttribute('type') || '').toLowerCase(),
      role: role,
      aria_label: (el.getAttribute('aria-label') || '').trim(),
      labelledby_text: labelledbyText(el),
      label_text: labelText(el),
      placeholder: (el.getAttribute('placeholder') || '').trim(),
      name: el.getAttribute('name') || '',
      value: el.value === undefined || el.value === null ? '' : String(el.value),
      required: el.hasAttribute('required') || el.getAttribute('aria-required') === 'true',
      disabled: el.disabled === true || el.getAttribute('aria-disabled') === 'true',
      visible: isVisible(el),
      options: optionsOf(el),
      landmark: landmarkOf(el),
      autocomplete_hint: (el.getAttribute('aria-autocomplete') || '').toLowerCase(),
    });
  }
  return out;
}
