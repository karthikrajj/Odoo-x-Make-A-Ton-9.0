/* exported navigate, action */
'use strict';
const $ = (s) => document.querySelector(s),
  E = (s) =>
    String(s ?? '').replace(
      /[&<>"']/g,
      (c) =>
        ({
          '&': '&amp;',
          '<': '&lt;',
          '>': '&gt;',
          '"': '&quot;',
          "'": '&#39;',
        })[c],
    ),
  M = (n) =>
    n == null
      ? '—'
      : new Intl.NumberFormat('en-IN', {
          style: 'currency',
          currency: 'INR',
          maximumFractionDigits: 2,
        }).format(n / 100);
let me,
  catalogs = {},
  current = {},
  revision,
  serial = 0,
  editId = null,
  noticeTimer;
let state = { view: 'dashboard', page: 1, q: '', status: '', from: '', to: '' };
const names = {
  dashboard: 'Overview',
  reconcile: 'Reconciliation',
  rehearsal: 'Billing rehearsal',
  subscriptions: 'Subscriptions',
  invoices: 'Invoices',
  payments: 'Payment history',
  bank: 'Bank matching',
  recovery: 'Overdue recovery',
  products: 'Products',
  variants: 'Variants',
  plans: 'Recurring plans',
  taxes: 'Tax rules',
  discounts: 'Discount rules',
  templates: 'Quotation templates',
  staff: 'Team access',
  checks: 'Verification & audit',
  'mailbox-all': 'Email delivery',
};
function button(label, action, primary = false, disabled = false) {
  return `<button type="button" onclick="action('${E(action)}',this)" class="${primary ? 'primary' : ''}" ${disabled ? 'disabled' : ''}>${label}</button>`;
}
function field(name, label, type = 'text', value = '', required = true) {
  return `<label>${E(label)}<input name="${name}" type="${type}" value="${E(value)}" ${required ? 'required' : ''} ${type === 'number' ? 'step="0.01" min="0"' : ''} ${type === 'password' ? 'autocomplete="new-password"' : ''}></label>`;
}
function select(name, label, options, value = '') {
  return `<label>${E(label)}<select name="${name}">${options
    .map((o) => {
      let [v, t] = Array.isArray(o) ? o : [o, o];
      return `<option value="${E(v)}" ${String(v) === String(value) ? 'selected' : ''}>${E(t)}</option>`;
    })
    .join('')}</select></label>`;
}
function check(name, label, value = true) {
  return `<label class="check"><input type="checkbox" name="${name}" ${value ? 'checked' : ''}>${E(label)}</label>`;
}
function table(head, body) {
  return `<div class="table-wrap"><table><thead><tr>${head.map((h) => `<th scope="col">${h}</th>`).join('')}</tr></thead><tbody>${body.join('') || `<tr><td colspan="${head.length}"><div class="empty">No records match these filters.</div></td></tr>`}</tbody></table></div>`;
}
function pill(v) {
  return `<span class="pill ${['Paid', 'Active', 'Passed', 'High'].includes(v) ? 'good' : ''}">${E(v)}</span>`;
}
function form(id, body, submit = 'Save') {
  return `<form id="${id}" novalidate>${body}<div class="form-footer"><p class="error form-error" role="alert" tabindex="-1"></p><button type="submit" class="primary">${submit}</button></div></form>`;
}
function panel(title, body) {
  return `<section class="panel"><h2>${title}</h2>${body}</section>`;
}
function notice(s) {
  $('#notice').textContent = s;
  clearTimeout(noticeTimer);
  noticeTimer = setTimeout(() => ($('#notice').textContent = ''), 6500);
}
async function api(path, data) {
  const r = await fetch('/api/' + path, {
    method: data === undefined ? 'GET' : 'POST',
    headers: data === undefined ? {} : { 'Content-Type': 'application/json' },
    body: data === undefined ? undefined : JSON.stringify(data),
  });
  const j = await r.json();
  if (!r.ok) {
    if (r.status === 401) auth();
    throw Error(j.error || 'Request failed');
  }
  return j;
}
function modal(title, body) {
  $('#modal')?.remove();
  const dialog = document.createElement('dialog');
  dialog.id = 'modal';
  dialog.setAttribute('aria-label', title);
  dialog.innerHTML = `<header><h2>${E(title)}</h2>${button('Close', 'close')}</header>${body}`;
  document.body.append(dialog);
  dialog.addEventListener('cancel', (e) => {
    if (dialog.querySelector('form')?.dataset.dirty === 'true') {
      e.preventDefault();
      notice('Save your changes or use Discard changes before closing.');
    }
  });
  dialog.showModal();
  dialog.querySelector('input,button')?.focus();
}
function filters(statuses = [], dates = false) {
  return form(
    'filters',
    field('q', 'Search customer', 'search', state.q, false) +
      button('Clear search', 'clear') +
      (statuses.length
        ? select('status', 'Status', [['', 'All statuses'], ...statuses], state.status)
        : '') +
      (dates
        ? field('from', 'From', 'date', state.from, false) +
          field('to', 'To', 'date', state.to, false)
        : ''),
    'Apply filters',
  );
}
function pager(data) {
  return `<div class="toolbar">${button('Previous', 'prev', false, data.page <= 1)}<span>Page ${data.page} · ${data.total.toLocaleString()} records</span>${button('Next', 'next', false, data.page * 30 >= data.total)}</div>`;
}
function auth(mode = 'login') {
  me = null;
  let token = new URLSearchParams(location.search).get('reset');
  if (token) mode = 'reset';
  $('#app').innerHTML =
    `<section class="login"><span class="eyebrow">Revenue, accounted for.</span><h1>RenewSure</h1><p>${{ login: 'Welcome to your revenue workspace.', signup: 'Create your customer account.', forgot: 'Receive a single-use reset link.', reset: 'Choose a new password.' }[mode]}</p>${form(mode, (mode === 'signup' ? field('name', 'Your name') : '') + (['login', 'signup', 'forgot'].includes(mode) ? field('email', 'Email', 'email', mode === 'login' ? 'admin@renewsure.demo' : '') : '') + (['login', 'signup', 'reset'].includes(mode) ? field('password', 'Password', 'password', mode === 'login' ? 'DemoPass!2026' : '') + button('Show password', 'password') : '') + (mode === 'reset' ? `<input type="hidden" name="token" value="${E(token || '')}">` : ''), { login: 'Sign in', signup: 'Create account', forgot: 'Send reset link', reset: 'Update password' }[mode])}<div class="toolbar">${button('Sign in', 'auth:login')}${button('Sign up', 'auth:signup')}${button('Forgot password', 'auth:forgot')}</div><p class="foot">Demo accounts: Admin / staff / customer @renewsure.demo<br>Demo password: DemoPass!2026<br>New passwords: more than 8 characters, uppercase, lowercase and special character.</p></section>`;
}
async function start() {
  try {
    me = await api('me');
    if (me.role !== 'customer') await loadCatalogs();
    await render();
  } catch (e) {
    auth();
    if (!e.message.includes('sign in')) notice(e.message);
  }
}
async function loadCatalogs() {
  const keys = ['products', 'variants', 'plans', 'taxes', 'discounts', 'templates'];
  const results = await Promise.all(keys.map((k) => api(k)));
  keys.forEach((k, i) => (catalogs[k] = results[i]));
}
function params() {
  return new URLSearchParams(
    Object.fromEntries(Object.entries(state).filter(([k, v]) => k !== 'view' && v !== '')),
  ).toString();
}
function saveURL() {
  history.replaceState(null, '', '#' + new URLSearchParams(state).toString());
}
async function navigate(view) {
  if ($('#modal')?.querySelector('form')?.dataset.dirty === 'true') {
    notice('Save or discard the open form before leaving.');
    return;
  }
  state = { view, page: 1, q: '', status: '', from: '', to: '' };
  await render();
}
async function render() {
  const seq = ++serial;
  saveURL();
  const nav =
    me.role === 'customer'
      ? ['dashboard', 'subscriptions', 'invoices', 'payments']
      : [
          'dashboard',
          'reconcile',
          'rehearsal',
          'subscriptions',
          'invoices',
          'payments',
          'bank',
          'recovery',
          'products',
          'variants',
          'plans',
          'taxes',
          'discounts',
          'templates',
          ...(me.role === 'admin' ? ['staff', 'mailbox-all'] : []),
          'checks',
        ];
  if (!nav.includes(state.view)) state.view = 'dashboard';
  $('#app').innerHTML =
    `<aside><h2>◈ RenewSure</h2><small>BRIGHTLOOP SOFTWARE</small><nav>${nav.map((n) => `<button type="button" onclick="navigate('${n}')" class="${state.view === n ? 'active' : ''}" ${state.view === n ? 'aria-current="page"' : ''}>${names[n]}</button>`).join('')}</nav><p class="foot">LOCAL DEMO<br>Persistent data · INR<br>${E(me.mail_mode)}</p></aside><main><header><div><span class="eyebrow">Revenue workspace / ${E(me.role)}</span><h1>${{ dashboard: 'Your revenue, in focus.', reconcile: 'Follow the money.', rehearsal: 'Before billing day.' }[state.view] || names[state.view]}</h1></div><div class="toolbar"><span>${E(me.name)}<br><small>${me.clock_mode === 'live' ? 'Live date' : 'Demo date'} ${me.clock}</small></span>${me.role === 'admin' ? button('Billing settings', 'clock') : ''}${button('Sign out', 'logout')}</div></header><section id="content" aria-live="polite"><div class="loading">Loading workspace…</div></section></main>`;
  let start = performance.now();
  try {
    const html = await viewHTML();
    if (seq !== serial) return;
    $('#content').innerHTML =
      html +
      `<p class="foot muted">Data + browser rendering: ${Math.round(performance.now() - start)} ms · ${current.server_ms ?? '—'} ms server processing · this request only</p>`;
  } catch (e) {
    if (seq === serial && $('#content'))
      $('#content').innerHTML = panel(
        'Unable to load',
        `<p class="error">${E(e.message)}</p>${button('Retry', 'refresh')}`,
      );
  }
}
async function viewHTML() {
  const v = state.view;
  if (v === 'dashboard') {
    let r = (current = await api('dashboard?' + params()));
    const max = Math.max(...Object.values(r.aging), 1);
    return `<p>A clear view of commitments, invoices and collected payments.</p>${filters([], true)}<div class="cards">${[
      ['Monthly recurring revenue', r.mrr, 'Active contract value, before tax and promotions'],
      ['Annual run rate', r.arr, 'MRR × 12'],
      ['Invoiced in period', r.invoiced, `${r.from} to ${r.to} · confirmed invoices`],
      ['Collected in period', r.received, 'Allocated payments by bank date'],
    ]
      .map(
        ([t, n, s]) =>
          `<div class="card"><small>${t}</small><strong>${M(n)}</strong><small>${s}</small></div>`,
      )
      .join(
        '',
      )}</div><div class="flow"><div><small>ACTIVE SUBSCRIPTIONS</small><strong>${r.active.toLocaleString()}</strong></div><div><small>OUTSTANDING · ALL PERIODS</small><strong>${M(r.outstanding)}</strong></div><div><small>DRAFT INVOICE VALUE</small><strong>${M(r.drafts)}</strong></div></div><div class="columns">${panel(
      'MRR movement in selected period',
      `<p>Contract value; excludes taxes and temporary discounts. Historical opening seed is explicitly labelled.</p><div class="waterfall">${Object.entries(
        r.waterfall,
      )
        .map(
          ([k, n]) =>
            `<div class="water-row"><span>${E(k)}</span><div><i style="width:${Math.max(2, (Math.abs(n) / Math.max(...Object.values(r.waterfall).map(Math.abs), 1)) * 100)}%;background:${n < 0 ? '#bc735d' : '#714b67'}"></i></div><strong>${M(n)}</strong></div>`,
        )
        .join('')}</div>`,
    )}${panel(
      'Receivables aging',
      `<p><strong>${r.overdue_count} overdue invoices · ${M(r.overdue_total)}</strong></p>` +
        Object.entries(r.aging)
          .map(
            ([k, n]) =>
              `<div class="age"><div class="between"><span>${k}</span><strong>${M(n)}</strong></div><meter min="0" max="${max}" value="${n}">${M(n)}</meter></div>`,
          )
          .join(''),
    )}</div>${me.role !== 'customer' ? panel('Resolve the next gap', `<p>Work through expected charges, invoice records and bank allocations together.</p>${button('Open reconciliation →', 'go:reconcile', true)}`) : ''}`;
  }
  if (['subscriptions', 'invoices', 'reconcile', 'bank'].includes(v)) {
    let r = (current = await api(v + '?' + params()));
    state.page = r.page;
    let statuses =
      v === 'subscriptions'
        ? ['Draft', 'Quotation', 'Confirmed', 'Active', 'Paused', 'Closed']
        : v === 'invoices'
          ? ['Draft', 'Confirmed', 'Paid', 'Cancelled', 'Overdue', 'Partially paid', 'Unpaid']
          : v === 'reconcile'
            ? [
                'Due, not invoiced',
                'Draft',
                'Unpaid',
                'Overdue',
                'Partially paid',
                'Paid',
                'Amount mismatch',
                'Unmatched bank entry',
                'Cancelled',
              ]
            : [];
    let toolbar = filters(statuses, v !== 'bank');
    if (v === 'subscriptions')
      return (
        toolbar +
        `<div class="toolbar">${me.role !== 'customer' ? button('New subscription', 'new:subscription', true) : ''}</div>` +
        panel(
          'Subscription register',
          table(
            ['Number / customer', 'Next billing', 'Expiry', 'Seats', 'State', ''],
            r.rows.map(
              (s) =>
                `<tr><td><b>SUB-${s.id}</b><br>${E(s.customer)}</td><td>${s.due}</td><td>${s.expiry || 'Open ended'}</td><td>${s.qty}</td><td>${pill(s.state)}</td><td>${button('Manage', 'sub:' + s.id)}</td></tr>`,
            ),
          ) + pager(r),
        )
      );
    if (v === 'invoices')
      return (
        toolbar +
        panel(
          'Invoices',
          table(
            ['Invoice', 'Customer', 'Period / due', 'Total', 'Balance', 'State', ''],
            r.rows.map(
              (i) =>
                `<tr><td>INV-${i.id}</td><td>${E(i.customer)}</td><td>${i.period}<br><small>Due ${i.due_date}</small></td><td>${M(i.total)}</td><td>${M(i.total - i.paid)}</td><td>${pill(i.state)} ${i.disputed ? 'Disputed' : ''}</td><td>${button('Open', 'invoice:' + i.id)}</td></tr>`,
            ),
          ) + pager(r),
        )
      );
    if (v === 'reconcile')
      return (
        `<p>The same billing period, followed from expected charge to invoice to allocated payment. Bank rows show only unallocated funds.</p>` +
        toolbar +
        panel(
          'Expected → Invoiced → Received',
          table(
            ['Customer / period', 'Expected', 'Invoiced', 'Received', 'Discrepancy', 'Next action'],
            r.rows.map(
              (i) =>
                `<tr><td><b>${E(i.customer)}</b><br><small>${i.period}</small></td><td>${M(i.expected)}</td><td>${M(i.invoiced)}</td><td>${M(i.received)}</td><td>${pill(i.status)}${i.overdue && i.status !== 'Overdue' ? '<br><small>Overdue</small>' : ''}</td><td>${button(i.action === 'bill-one' ? 'Create draft' : i.action === 'bank' ? 'Match payment' : 'Review invoice', i.action + ':' + i.id)}</td></tr>`,
            ),
          ) + pager(r),
        )
      );
    if (v === 'bank')
      return (
        `<p>CSV suggestions use invoice reference, customer name and available balance. Every allocation needs staff approval.</p><div class="panel"><label>Import bank CSV<input id="csv" type="file" accept=".csv,text/csv"></label><small>reference, customer, amount (INR), date (YYYY-MM-DD), method, note</small><p id="upload-error" class="error" role="alert"></p></div>` +
        toolbar +
        panel(
          'Unallocated bank transactions',
          table(
            ['Transaction / date', 'Customer', 'Available', 'Suggested invoice / evidence', ''],
            r.rows.map(
              (b) =>
                `<tr><td>#${b.id} · ${E(b.reference)}<br>${b.date}</td><td>${E(b.customer)}</td><td>${M(b.available)}</td><td>${b.suggestions.map((s) => `<div class="suggestion">${pill(s.confidence)} INV-${s.id} · ${M(s.amount)}<br><small>${E(s.reason)}</small>${button('Review match', `match:${b.id}:${s.id}:${s.amount}`)}</div>`).join('') || 'No reliable candidate'}</td><td>${button('Manual allocation', 'allocate:' + b.id)}</td></tr>`,
            ),
          ) + pager(r),
        )
      );
  }
  if (v === 'payments') {
    let r = (current = await api('payments?' + params()));
    state.page = r.page;
    return (
      `<p>Recorded payments, their invoice allocations and remaining funds. Fully allocated payments remain visible.</p>` +
      filters([], true) +
      panel(
        'Payment register',
        table(
          ['Reference / date', 'Customer', 'Method', 'Amount', 'Unallocated', 'Note / invoices'],
          r.rows.map(
            (b) =>
              `<tr><td>#${b.id} · ${E(b.reference)}<br>${b.date}</td><td>${E(b.customer)}</td><td>${E(b.method)}</td><td>${M(b.amount)}</td><td>${M(b.available)}</td><td>${E(b.note)}<div>${b.allocations.map((a) => button('INV-' + a.invoice_id + ' · ' + M(a.amount), 'invoice:' + a.invoice_id)).join('')}</div></td></tr>`,
          ),
        ) + pager(r),
      )
    );
  }
  if (v === 'rehearsal') {
    let r = (current = await api('preview'));
    revision = r.revision;
    return (
      `<p>Read-only forecast. Execution rechecks the data revision, catches up every due period and creates draft invoices.</p><div class="cards"><div class="card"><small>Invoice count</small><strong>+${r.count.toLocaleString()}</strong></div><div class="card"><small>Draft value added</small><strong>${M(r.total)}</strong></div><div class="card"><small>Billing-only MRR change</small><strong>₹0</strong><small>Expired contract closure is logged separately</small></div><div class="card"><small>Ledger checks passed</small><strong>${r.checks.filter((c) => c.passed).length} / ${r.checks.length}</strong><small>${r.skip_count} explained skips</small></div></div><div class="toolbar">${button('Approve billing run', 'run', true, (!r.count && !r.expired.length) || r.checks.some((c) => !c.passed))}${button('Refresh rehearsal', 'refresh')}</div>` +
      panel(
        'First 30 proposed invoices',
        table(
          ['Customer', 'Period', 'Subtotal', 'Discount', 'Tax', 'Total'],
          r.rows.map(
            (i) =>
              `<tr><td>${E(i.customer)}</td><td>${i.period}</td><td>${M(i.subtotal)}</td><td>${M(i.discount)}</td><td>${M(i.tax)}</td><td>${M(i.total)}</td></tr>`,
          ),
        ),
      ) +
      panel(
        'Explained skips · first 30',
        table(
          ['Subscription', 'Customer', 'Reason'],
          r.skips.map(
            (s) => `<tr><td>SUB-${s.id}</td><td>${E(s.customer)}</td><td>${E(s.reason)}</td></tr>`,
          ),
        ),
      )
    );
  }
  if (v === 'recovery') {
    let r = (current = await api('recovery'));
    return (
      `<p>Reminders run every 30 seconds using the selected clock: due date, +3 and +7 days. Paid and disputed invoices are excluded. Only the latest eligible stage is queued on catch-up.</p>${button('Check reminder schedule now', 'chase', true)}` +
      panel(
        'Chase first',
        table(
          ['Invoice / customer', 'Overdue', 'Outstanding', 'Priority score', ''],
          r.rows.map(
            (i) =>
              `<tr><td>INV-${i.id} · ${E(i.customer)}</td><td>${i.days} days</td><td>${M(i.balance)}</td><td>${i.score}<br><small>2 × days (cap 90) + ₹100 units (cap 100)</small></td><td>${button('Review', 'invoice:' + i.id)}</td></tr>`,
          ),
        ),
      ) +
      panel(
        'Reminder history',
        table(
          ['Invoice', 'Stage', 'Recipient', 'Delivery'],
          r.events.map(
            (e) =>
              `<tr><td>INV-${e.invoice_id}</td><td>+${e.stage} days</td><td>${E(e.recipient)}</td><td>${E(e.status)}</td></tr>`,
          ),
        ),
      )
    );
  }
  if (v === 'checks') {
    let r = (current = await api('checks'));
    return (
      panel(
        'Live ledger invariants',
        r.checks
          .map(
            (c) =>
              `<div class="check-row">${pill(c.passed ? 'Passed' : 'Failed')}<span>${E(c.name)}</span><small>${c.failures} failures</small></div>`,
          )
          .join(''),
      ) +
      panel(
        'Billing runs',
        table(
          ['Run', 'Date', 'Created', 'Skipped', 'Value'],
          r.runs.map(
            (x) =>
              `<tr><td>#${x.id}</td><td>${x.date}</td><td>${x.created}</td><td>${x.skipped}</td><td>${M(x.total)}</td></tr>`,
          ),
        ),
      ) +
      panel(
        'Audit trail · latest 50',
        r.audit.map((a) => `<p><small>${a.at}</small><br>${E(a.event)}</p>`).join(''),
      )
    );
  }
  if (v === 'mailbox-all') {
    let r = (current = await api(v + '?' + params()));
    return (
      `<p>Email delivery: ${E(me.mail_mode)}. Run Setup-Gmail.cmd to connect your account. Old demo messages and synthetic recipients are never sent.</p>` +
      panel(
        'Email delivery history',
        table(
          ['To', 'Subject', 'Created', 'Status'],
          r.rows.map(
            (m) =>
              `<tr><td>${E(m.recipient)}</td><td>${E(m.subject)}</td><td>${E(m.created)}</td><td>${E(m.status)}</td></tr>`,
          ),
        ) + pager(r),
      )
    );
  }
  let r = (current = await api(v));
  catalogs[v] = r;
  const headers = {
    products: ['Product', 'Type', 'Sales / cost', 'Notes'],
    variants: ['Variant', 'Product', 'Price addition'],
    plans: ['Plan', 'Cycle', 'Minimum', 'Options'],
    taxes: ['Rule', 'Rate', 'Status'],
    discounts: ['Rule', 'Benefit', 'Validity', 'Uses'],
    templates: ['Template', 'Plan', 'Valid for', 'Lines'],
    staff: ['Name', 'Email', 'Role'],
  };
  const body = r.map((x) => {
    let cells = {
      products: [x.name, x.type, M(x.sales_price) + ' / ' + M(x.cost_price), x.notes],
      variants: [x.name, catalogs.products?.find((p) => p.id === x.product_id)?.name, M(x.extra)],
      plans: [
        x.name,
        x.cycle,
        x.min_qty,
        [
          x.allow_pause ? 'Pause' : '',
          x.allow_close ? 'Close' : '',
          x.allow_renew ? 'Renew' : '',
          x.auto_close ? 'Auto close' : '',
        ]
          .filter(Boolean)
          .join(' · '),
      ],
      taxes: [x.name, x.rate / 100 + '%', x.active ? 'Active' : 'Inactive'],
      discounts: [
        x.name,
        x.kind === 'fixed' ? M(x.value) : x.value / 100 + '%',
        x.start + ' → ' + x.end,
        x.used + ' / ' + x.limit_uses,
      ],
      templates: [
        x.name,
        catalogs.plans?.find((p) => p.id === x.plan_id)?.name,
        x.valid_days + ' days',
        JSON.parse(x.lines || '[]').length,
      ],
      staff: [x.name, x.email, x.role],
    }[v];
    return `<tr>${cells.map((s) => `<td>${E(s)}</td>`).join('')}<td>${me.role === 'admin' && v !== 'staff' ? button('Edit', `edit:${v}:${x.id}`) : ''}</td></tr>`;
  });
  return (
    `<div class="toolbar">${me.role === 'admin' ? button('Add ' + names[v].toLowerCase(), 'new:' + v, true) : '<p>Configuration is managed by your admin.</p>'}</div>` +
    panel(names[v], table([...headers[v], ''], body))
  );
}
function opts(key, empty = false) {
  return [...(empty ? [[0, 'None']] : []), ...(catalogs[key] || []).map((x) => [x.id, x.name])];
}
function lineRow(l = {}) {
  const variants = [
    [0, 'No variant'],
    ...(catalogs.variants || []).map((v) => [
      v.id,
      `${catalogs.products.find((p) => p.id === v.product_id)?.name} / ${v.name} (+${M(v.extra)})`,
    ]),
  ];
  return `<div class="line-row"><input type="hidden" name="line_id" value="${l.id || ''}">${select('product_id', 'Product', opts('products'), l.product_id)}${select('variant_id', 'Variant', variants, l.variant_id || 0)}${field('qty', 'Quantity', 'number', l.qty || 1)}${select('tax_id', 'Tax rule', opts('taxes'), l.tax_id || (catalogs.taxes || []).find((t) => t.rate === l.tax_rate)?.id || (catalogs.taxes || []).find((t) => t.rate === catalogs.plans?.[0]?.tax)?.id)}${button('Remove', 'remove-line')}</div>`;
}
function linesEditor(lines = [{}]) {
  return `<div class="line-editor"><h3>Product lines</h3><p>The plan sets the first product’s unit price. Its variant addition is added. Additional products use their catalog prices.</p><div id="lines">${lines.map(lineRow).join('')}</div>${button('Add product line', 'add-line')}</div>`;
}
function editor(type, x = {}) {
  editId = x.id || null;
  let body = '';
  if (type === 'subscription') {
    body =
      field('customer', 'Customer', 'text', x.customer || '') +
      field('email', 'Customer email', 'email', x.email || '') +
      (x.id
        ? ''
        : select('plan_id', 'Recurring plan', opts('plans'), x.plan_id) +
          select('template_id', 'Template (overrides plan and lines)', opts('templates', true), 0) +
          field('start_date', 'Start date', 'date', x.start_date || me.clock)) +
      field('expiry', 'Expiry (optional)', 'date', x.expiry || '', false) +
      field('terms_days', 'Payment terms (days)', 'number', x.terms_days ?? 15) +
      (x.id ? '' : field('valid_days', 'Quotation validity (days)', 'number', 14)) +
      select('discount_id', 'Discount rule', opts('discounts', true), x.discount_id || 0) +
      (x.id
        ? field('quotation_until', 'Quote valid until', 'date', x.quotation_until || me.clock)
        : '') +
      linesEditor(x.lines || [{}]) +
      (x.id
        ? check('reprice', 'Use current catalog prices and taxes for future invoices', false)
        : '');
  }
  if (type === 'products')
    body =
      field('name', 'Product name', 'text', x.name || '') +
      select('type', 'Type', ['Software', 'Service', 'Physical'], x.type || 'Software') +
      field('sales_price', 'Sales price (INR)', 'number', (x.sales_price || 0) / 100) +
      field('cost_price', 'Cost price (INR)', 'number', (x.cost_price || 0) / 100) +
      field('notes', 'Notes', 'text', x.notes || '', false) +
      check('active', 'Available for new orders', x.active !== 0);
  if (type === 'variants')
    body =
      field('name', 'Variant name', 'text', x.name || '') +
      select('product_id', 'Product', opts('products'), x.product_id) +
      field('extra', 'Price addition (INR)', 'number', (x.extra || 0) / 100);
  if (type === 'taxes')
    body =
      field('name', 'Rule name', 'text', x.name || '') +
      field('rate', 'Tax percent', 'number', (x.rate || 0) / 100) +
      check('active', 'Available', x.active !== 0);
  if (type === 'plans')
    body =
      field('name', 'Plan name', 'text', x.name || '') +
      select(
        'cycle',
        'Billing frequency',
        ['daily', 'weekly', 'monthly', 'yearly'],
        x.cycle || 'monthly',
      ) +
      field(
        'price',
        'Primary product price per unit / cycle (INR)',
        'number',
        (x.price || 0) / 100,
      ) +
      field('min_qty', 'Minimum total quantity', 'number', x.min_qty || 1) +
      field('available_from', 'Available from', 'date', x.available_from || me.clock) +
      field('available_to', 'Available until (optional)', 'date', x.available_to || '', false) +
      ['allow_pause', 'allow_close', 'allow_renew', 'auto_close']
        .map((k) =>
          check(
            k,
            {
              allow_pause: 'Allow pause',
              allow_close: 'Allow early close',
              allow_renew: 'Allow renewal',
              auto_close: 'Close automatically at expiry',
            }[k],
            x[k] !== 0,
          ),
        )
        .join('');
  if (type === 'discounts')
    body =
      field('name', 'Rule name', 'text', x.name || '') +
      select(
        'kind',
        'Benefit type',
        [
          ['fixed', 'Fixed INR'],
          ['percent', 'Percentage'],
        ],
        x.kind,
      ) +
      field('value', 'Benefit (INR or percent)', 'number', (x.value || 0) / 100) +
      field('min_qty', 'Minimum quantity', 'number', x.min_qty || 1) +
      field(
        'min_purchase',
        'Minimum eligible purchase (INR)',
        'number',
        (x.min_purchase || 0) / 100,
      ) +
      field('start', 'Start date', 'date', x.start || me.clock) +
      field('end', 'End date', 'date', x.end || me.clock) +
      field('limit_uses', 'Maximum invoice applications', 'number', x.limit_uses ?? 100) +
      select(
        'product_id',
        'Product (none = whole subscription)',
        opts('products', true),
        x.product_id || 0,
      ) +
      check('active', 'Enabled', x.active !== 0);
  if (type === 'templates')
    body =
      field('name', 'Template name', 'text', x.name || '') +
      select('plan_id', 'Recurring plan', opts('plans'), x.plan_id) +
      field('valid_days', 'Quotation validity in days', 'number', x.valid_days || 14) +
      linesEditor(x.lines ? JSON.parse(x.lines) : [{}]);
  if (type === 'staff')
    body =
      field('name', 'Staff name') +
      field('email', 'Staff email', 'email') +
      field('password', 'Initial password', 'password') +
      button('Show password', 'password');
  modal(
    (x.id ? 'Edit ' : 'Create ') + (type === 'subscription' ? 'subscription' : names[type]),
    form('edit-' + type, body) + button('Discard changes', 'discard'),
  );
  if (type === 'subscription' && x.id) {
    for (let k of ['customer', 'email']) {
      let el = $('#modal').querySelector('[name=' + k + ']');
      el.readOnly = true;
      el.setAttribute('aria-readonly', 'true');
    }
  }
}
async function subscription(id) {
  let s = await api('subscription?id=' + id);
  let allowed =
    {
      Draft: ['Quotation'],
      Quotation: ['Confirmed'],
      Confirmed: ['Active'],
      Active: ['Paused', 'Closed'],
      Paused: ['Active', 'Closed'],
      Closed: ['Active'],
    }[s.state] || [];
  allowed = allowed.filter(
    (t) =>
      !(t === 'Paused' && !s.plan_options.allow_pause) &&
      !(t === 'Closed' && !s.plan_options.allow_close && (!s.expiry || s.expiry >= me.clock)) &&
      !(
        (s.state === 'Closed' || (s.expiry && s.expiry < me.clock)) &&
        t === 'Active' &&
        !s.plan_options.allow_renew
      ),
  );
  if (me.role === 'customer' && ['Draft', 'Quotation', 'Confirmed'].includes(s.state)) allowed = [];
  modal(
    'SUB-' + id,
    `<p>${E(s.customer)} · ${pill(s.state)} · ${E(s.email)}</p><p>Start ${s.start_date} · Expiry ${s.expiry || 'open ended'} · Payment terms ${s.terms_days} days</p>${table(
      ['Product', 'Quantity', 'Unit price', 'Discount', 'Tax', 'Amount'],
      s.lines.map(
        (l) =>
          `<tr><td>${E(l.description)}</td><td>${l.qty}</td><td>${M(l.unit_price)}</td><td>−${M(l.discount)}</td><td>${M(l.tax)} (${l.tax_rate / 100}%)</td><td>${M(l.total)}</td></tr>`,
      ),
    )}<p>Plan: ${E(s.plan_name)} · Next calculation for ${s.due}. Subtotal ${M(s.calculation.subtotal)} − discount ${M(s.calculation.discount)} + tax ${M(s.calculation.tax)} = <strong>${M(s.calculation.total)}</strong></p><div class="toolbar">${allowed.map((t) => button({ Quotation: 'Prepare quotation', Confirmed: 'Confirm quotation', Active: s.state === 'Closed' ? 'Renew' : s.state === 'Paused' ? 'Resume' : 'Activate', Paused: 'Pause', Closed: 'Close' }[t], `transition:${id}:${t}`)).join('')}${me.role !== 'customer' ? button('Edit future contract', 'sub-edit:' + id) : ''}</div>`,
  );
}
async function invoice(id) {
  let i = await api('invoice?id=' + id);
  modal(
    'Invoice INV-' + id,
    `<p><b>${E(i.customer)}</b> · ${E(i.email)} · ${pill(i.state)}</p><p>Billing period ${i.period} · Due ${i.due_date} ${i.disputed ? '· Collection on hold (disputed)' : ''}</p>${table(
      ['Product', 'Qty × unit price', 'Discount', 'Tax', 'Total'],
      i.lines.map(
        (l) =>
          `<tr><td>${E(l.description)}</td><td>${l.qty} × ${M(l.unit_price)}</td><td>−${M(l.discount)}</td><td>${M(l.tax)}</td><td>${M(l.total)}</td></tr>`,
      ),
    )}<div class="flow"><div><small>Total</small><strong>${M(i.total)}</strong></div><div><small>Received</small><strong>${M(i.paid)}</strong></div><div><small>Outstanding</small><strong>${M(i.balance)}</strong></div></div><p>Why this amount: ${M(i.subtotal)} subtotal − ${M(i.discount)} discounts + ${M(i.tax)} tax = ${M(i.total)}. Calculations are preserved from invoice creation.</p><div class="toolbar"><a class="button-link" target="_blank" href="/api/invoice.pdf?id=${id}">Open printable PDF ↗</a>${me.role !== 'customer' ? `${i.state === 'Draft' ? button('Confirm invoice', `inv:confirm:${id}`, true) : ''}${['Confirmed', 'Paid'].includes(i.state) ? button('Queue email', `inv:send:${id}`) : ''}${i.state === 'Confirmed' && i.balance > 0 ? button('Record payment', 'payment:' + id, true) + button(i.disputed ? 'Release collection hold' : 'Mark disputed', `inv:dispute:${id}`) + button('Queue reminder', `inv:remind:${id}`) : ''}${!i.paid && i.state !== 'Cancelled' ? button('Cancel invoice', `inv:cancel:${id}`) : ''}` : ''}</div>`,
  );
}
async function action(a, b) {
  if (b) b.disabled = true;
  try {
    let [cmd, x, y, z] = a.split(':');
    if (cmd === 'auth') {
      history.replaceState(null, '', '/');
      return auth(x);
    }
    if (cmd === 'password') {
      let p = b.closest('form').querySelector('input[name=password]');
      p.type = p.type === 'password' ? 'text' : 'password';
      b.textContent = p.type === 'password' ? 'Show password' : 'Hide password';
      return;
    }
    if (cmd === 'close') {
      if ($('#modal').querySelector('form')?.dataset.dirty === 'true') {
        notice('Save or use Discard changes.');
        return;
      }
      $('#modal').close();
      $('#modal').remove();
      return;
    }
    if (cmd === 'discard') {
      $('#modal').close();
      $('#modal').remove();
      return;
    }
    if (cmd === 'add-line') {
      $('#lines').insertAdjacentHTML('beforeend', lineRow());
      return;
    }
    if (cmd === 'remove-line') {
      if ($('#lines').children.length === 1) throw Error('At least one product line is required');
      b.closest('.line-row').remove();
      return;
    }
    if (cmd === 'logout') {
      await api('logout', {});
      return auth();
    }
    if (cmd === 'go') return navigate(x);
    if (cmd === 'clear') {
      state.q = '';
      state.page = 1;
      return render();
    }
    if (cmd === 'prev') state.page = Math.max(1, state.page - 1);
    if (cmd === 'next') state.page++;
    if (cmd === 'new') return editor(x);
    if (cmd === 'edit')
      return editor(
        x,
        catalogs[x].find((r) => r.id === Number(y)),
      );
    if (cmd === 'sub') return subscription(x);
    if (cmd === 'sub-edit') {
      let s = await api('subscription?id=' + x);
      return editor('subscription', s);
    }
    if (cmd === 'invoice') return invoice(x);
    if (cmd === 'bank') return navigate('bank');
    if (cmd === 'clock') {
      let config = await api('automation');
      return modal(
        'Billing clock & schedule',
        form(
          'clock',
          select(
            'mode',
            'Clock mode',
            [
              ['demo', 'Demo (selected date)'],
              ['live', 'Live (India local date)'],
            ],
            config.clock_mode,
          ) + field('date', 'Demo date (ignored in live mode)', 'date', me.clock),
          'Save clock',
        ) +
          form(
            'automation',
            check('enabled', 'Automatically create due drafts every 30 seconds', config.enabled),
            'Save schedule',
          ),
      );
    }
    if (cmd === 'transition') {
      let sub = await api('subscription?id=' + x);
      let needsExpiry = y === 'Active' && sub.expiry && sub.expiry < me.clock;
      let messages = {
        Quotation: 'Prepare this subscription as a quotation for customer review.',
        Confirmed: 'Confirm the quotation before activation.',
        Active:
          sub.state === 'Confirmed'
            ? 'Activate this subscription. Billing follows its start date and recurring plan.'
            : 'Resume or renew this subscription. A new billing cycle starts on the selected clock date.',
        Paused: 'Pause this subscription. Billing stops while it is paused.',
        Closed: 'Close this subscription. Future billing stops.',
      };
      return modal(
        'Confirm subscription change',
        `<p>Change SUB-${x} to ${E(y)}.</p><p>${E(messages[y] || '')}</p>${form('transition', `<input name="id" type="hidden" value="${x}"><input name="state" type="hidden" value="${y}">` + (needsExpiry ? field('expiry', 'New expiry for this expired contract', 'date', '') : ''), 'Confirm ' + y)}`,
      );
    }
    if (cmd === 'inv')
      return modal(
        'Confirm invoice action',
        `<p>${E(x)} invoice INV-${y}${x === 'cancel' ? '. Cancellation keeps the original record and prevents payment allocation. Discounts remain consumed.' : ''}.</p>${form('invoice-action', `<input name="id" type="hidden" value="${y}"><input name="action" type="hidden" value="${x}">`, 'Confirm ' + x)}`,
      );
    if (cmd === 'run' || cmd === 'bill-one')
      return modal(
        'Approve billing',
        `<p>Create ${cmd === 'run' ? current.count : 'the due'} draft invoices. No money will be charged.</p>${form('bill', `<input name="revision" type="hidden" value="${cmd === 'run' ? revision : ''}"><input name="id" type="hidden" value="${cmd === 'bill-one' ? x : ''}">`, 'Create draft invoices')}`,
      );
    if (cmd === 'payment') {
      let i = await api('invoice?id=' + x);
      return modal(
        'Record payment',
        form(
          'payment',
          `<input name="invoice_id" type="hidden" value="${x}">` +
            field('amount', 'Amount INR', 'number', i.balance / 100) +
            field('reference', 'Unique payment reference') +
            field('date', 'Received date', 'date', me.clock) +
            select('method', 'Method', ['UPI', 'NEFT', 'Card', 'Cash', 'Cheque', 'Other']) +
            field('note', 'Note', 'text', '', false),
          'Record and allocate',
        ),
      );
    }
    if (cmd === 'match' || cmd === 'allocate')
      return modal(
        'Approve payment allocation',
        `<p>Only the amount allocated here is applied. Remaining bank funds stay available.</p>${form('allocate', field('bank_id', 'Bank transaction ID', 'number', x) + field('invoice_id', 'Invoice ID', 'number', y || '') + field('amount', 'Allocation INR', 'number', z ? Number(z) / 100 : ''), 'Approve allocation')}`,
      );
    if (cmd === 'chase') {
      let r = await api('recovery', {});
      notice(`${r.queued} reminder(s) queued for delivery`);
    }
    await render();
  } catch (e) {
    notice(e.message);
  } finally {
    if (b) b.disabled = false;
  }
}
function getLines(f) {
  return [...f.querySelectorAll('.line-row')].map((row) =>
    Object.fromEntries([...row.querySelectorAll('input,select')].map((i) => [i.name, i.value])),
  );
}
document.addEventListener('input', (e) => {
  let f = e.target.closest('form');
  if (f) {
    f.dataset.dirty = 'true';
    e.target.removeAttribute('aria-invalid');
  }
});
document.addEventListener('submit', async (e) => {
  e.preventDefault();
  let f = e.target,
    formId = f.getAttribute('id') || '',
    data = Object.fromEntries(new FormData(f)),
    submit = f.querySelector('button[type=submit]'),
    err = f.querySelector('.form-error');
  err.textContent = '';
  let invalid = [...f.querySelectorAll('[required]')].find((i) => !i.value.trim());
  if (invalid) {
    invalid.setAttribute('aria-invalid', 'true');
    err.textContent = 'Complete all required fields.';
    invalid.focus();
    return;
  }
  submit.disabled = true;
  try {
    if (['login', 'signup', 'forgot', 'reset'].includes(formId)) {
      let r = await api(formId, data);
      if (formId === 'login') return start();
      notice(r.message);
      if (formId === 'reset') {
        history.replaceState(null, '', '/');
        return auth();
      }
      return auth('login');
    }

    if (formId === 'filters') {
      state = { ...state, ...data, page: 1 };
      return render();
    }
    let path = formId;
    if (formId === 'automation') data.enabled = f.querySelector('[name=enabled]').checked;
    if (formId.startsWith('edit-')) {
      let type = formId.slice(5);
      path = type === 'subscription' ? 'subscriptions' : type;
      if (editId) data.id = editId;
      for (let c of f.querySelectorAll('input[type=checkbox]')) data[c.name] = c.checked;
      for (let key of [
        'sales_price',
        'cost_price',
        'extra',
        'rate',
        'price',
        'value',
        'min_purchase',
      ])
        if (key in data) data[key] = Math.round(Number(data[key]) * 100);
      if (f.querySelector('#lines')) data.lines = getLines(f);
      if (type === 'subscription' && data.id) delete data.template_id;
    }
    if (['allocate', 'payment'].includes(formId))
      data.amount = Math.round(Number(data.amount) * 100);
    if (formId === 'invoice-action') path = 'invoice';
    if (formId === 'bill') {
      if (!data.revision) delete data.revision;
      if (!data.id) delete data.id;
    }
    let r = await api(path, data);
    f.dataset.dirty = 'false';
    $('#modal')?.close();
    $('#modal')?.remove();
    notice(
      r.created !== undefined
        ? `${r.created} draft invoices created`
        : r.queued !== undefined
          ? `${r.queued} reminder(s) queued`
          : 'Saved successfully',
    );
    if (formId === 'clock') me = await api('me');
    if (
      me.role !== 'customer' &&
      ['products', 'variants', 'plans', 'taxes', 'discounts', 'templates'].includes(path) &&
      state.view !== path
    )
      catalogs[path] = await api(path);
    await render();
  } catch (e) {
    err.textContent = e.message;
    err.focus();
  } finally {
    submit.disabled = false;
  }
});
document.addEventListener('change', async (e) => {
  if (e.target.id === 'csv' && e.target.files[0]) {
    let file = e.target.files[0];
    e.target.disabled = true;
    try {
      if (file.size > 2000000) throw Error('Maximum CSV size is 2 MB');
      let r = await api('import', { csv: await file.text() });
      notice(`${r.imported} imported · ${r.duplicates} duplicates skipped`);
      await render();
    } catch (err) {
      $('#upload-error').textContent = err.message;
    } finally {
      e.target.disabled = false;
    }
  }
});
window.addEventListener('beforeunload', (e) => {
  if ($('#modal')?.querySelector('form')?.dataset.dirty === 'true') {
    e.preventDefault();
    e.returnValue = '';
  }
});
window.addEventListener('hashchange', () => {
  if (me) {
    Object.assign(state, Object.fromEntries(new URLSearchParams(location.hash.slice(1))));
    state.page = Number(state.page) || 1;
    render();
  }
});
// Application startup.
if (location.hash) {
  Object.assign(state, Object.fromEntries(new URLSearchParams(location.hash.slice(1))));
  state.page = Number(state.page) || 1;
}
if (new URLSearchParams(location.search).has('reset')) auth('reset');
else start();
