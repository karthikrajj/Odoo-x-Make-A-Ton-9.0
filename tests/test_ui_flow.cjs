// Run the application's actual form handlers against an isolated real HTTP server.
const assert = require('node:assert/strict'),
  fs = require('node:fs'),
  vm = require('node:vm');
const base = process.argv[2];
if (!base) throw Error('Run through verify_frontend.py');
const events = {},
  requests = [],
  feedback = [];
let cookie = '';
const code = fs.readFileSync('static/app.js', 'utf8');
const context = vm.createContext({
  console,
  URLSearchParams,
  Intl,
  encodeURIComponent,
  setTimeout,
  clearTimeout,
  performance,
  location: { hash: '', search: '' },
  history: { replaceState() {} },
  window: { addEventListener() {} },
  document: {
    querySelector() {
      return null;
    },
    addEventListener(type, fn) {
      events[type] = fn;
    },
  },
  FormData: class {
    constructor(form) {
      return form.entries;
    }
  },
  fetch: async (path, options = {}) => {
    const response = await fetch(base + path, {
      ...options,
      headers: { ...options.headers, ...(cookie ? { Cookie: cookie } : {}) },
    });
    const setCookie = response.headers.get('set-cookie');
    if (setCookie) cookie = setCookie.split(';')[0];
    requests.push({ path, status: response.status });
    return response;
  },
});
vm.runInContext(code.slice(0, code.indexOf('// Application startup.')), context);
context.feedback = feedback;
vm.runInContext(
  "render=async()=>{};notice=s=>feedback.push(s);auth=()=>{};start=async()=>{me=await api('me')};",
  context,
);
function run(script) {
  return vm.runInContext(script, context);
}
async function api(path, data) {
  context.testPath = path;
  context.testData = data;
  return run('api(testPath,testData)');
}
async function form(name, values, lines = null, checks = {}, options = {}) {
  if (name.startsWith('edit-')) run('editId=' + Number(options.id || 0) + '||null');
  const error = { textContent: '', focus() {} },
    button = { disabled: false };
  const fields = Object.entries(values),
    checkboxes = Object.entries(checks).map(([name, checked]) => ({
      name,
      checked,
    }));
  const f = {
    id: values.id ? { value: values.id } : name,
    entries: fields,
    dataset: { dirty: 'true' },
    getAttribute: (key) => (key === 'id' ? name : null),
    querySelector(selector) {
      if (selector === 'button[type=submit]') return button;
      if (selector === '.form-error') return error;
      if (selector === '#lines') return lines ? {} : null;
      return null;
    },
    querySelectorAll(selector) {
      if (selector === '[required]') return [];
      if (selector === 'input[type=checkbox]') return checkboxes;
      if (selector === '.line-row')
        return (lines || []).map((line) => ({
          querySelectorAll: () =>
            Object.entries(line).map(([name, value]) => ({
              name,
              value: String(value),
            })),
        }));
      return [];
    },
  };
  await events.submit({ preventDefault() {}, target: f });
  if (options.error) assert.match(error.textContent, options.error);
  else assert.equal(error.textContent, '', name);
  assert.equal(button.disabled, false);
  return feedback.at(-1);
}
(async () => {
  await form('signup', {
    name: 'Frontend Customer',
    email: 'frontend.customer@example.test',
    password: 'FrontendPass!2026',
  });
  await form('login', {
    email: 'admin@renewsure.demo',
    password: 'DemoPass!2026',
  });
  await form(
    'edit-products',
    {
      name: 'Frontend Software',
      type: 'Software',
      sales_price: '1000',
      cost_price: '400',
      notes: 'Audit product',
    },
    null,
    { active: true },
  );
  let products = await api('products'),
    product = products.find((p) => p.name === 'Frontend Software');
  assert.equal(product.sales_price, 100000);
  assert.equal(product.cost_price, 40000);
  await form('edit-variants', {
    name: 'Odoo audit',
    product_id: String(product.id),
    extra: '560',
  });
  let variant = (await api('variants')).find((v) => v.name === 'Odoo audit');
  assert.equal(variant.extra, 56000);
  await form('edit-taxes', { name: 'Audit 18%', rate: '18' }, null, {
    active: true,
  });
  let tax = (await api('taxes')).find((t) => t.name === 'Audit 18%');
  assert.equal(tax.rate, 1800);
  await form(
    'edit-plans',
    {
      name: 'Frontend Monthly',
      price: '500',
      cycle: 'monthly',
      min_qty: '2',
      available_from: '2026-01-01',
      available_to: '2027-12-31',
    },
    null,
    {
      allow_pause: true,
      allow_close: true,
      allow_renew: true,
      auto_close: true,
    },
  );
  let plan = (await api('plans')).find((p) => p.name === 'Frontend Monthly');
  assert.equal(plan.price, 50000);
  await form(
    'edit-discounts',
    {
      name: 'Audit fixed',
      kind: 'fixed',
      value: '100',
      min_qty: '2',
      min_purchase: '500',
      start: '2026-10-01',
      end: '2026-12-31',
      limit_uses: '2',
      product_id: '0',
    },
    null,
    { active: true },
  );
  let discount = (await api('discounts')).find((d) => d.name === 'Audit fixed');
  assert.equal(discount.value, 10000);
  const lines = [{ product_id: product.id, variant_id: variant.id, qty: 2, tax_id: tax.id }];
  await form(
    'edit-templates',
    { name: 'Frontend quote', plan_id: String(plan.id), valid_days: '14' },
    lines,
  );
  let template = (await api('templates')).find((t) => t.name === 'Frontend quote');
  await form(
    'edit-subscription',
    {
      customer: 'Frontend Customer',
      email: 'frontend.customer@example.test',
      plan_id: String(plan.id),
      template_id: String(template.id),
      start_date: '2026-10-31',
      expiry: '2026-12-31',
      terms_days: '0',
      valid_days: '14',
      discount_id: String(discount.id),
    },
    lines,
  );
  let sub = (await api('subscriptions?q=Frontend')).rows[0];
  assert.equal(sub.state, 'Draft');
  for (const state of ['Quotation', 'Confirmed', 'Active']) {
    await form('transition', { id: String(sub.id), state });
    assert.equal((await api('subscription?id=' + sub.id)).state, state);
  }
  let detail = await api('subscription?id=' + sub.id);
  assert.equal(detail.calculation.total, 238360);
  assert.equal(detail.lines[0].unit_price, 106000);
  let preview = await api('preview');
  await form('bill', {
    id: String(sub.id),
    revision: String(preview.revision),
  });
  let invoice = (await api('invoices?q=Frontend')).rows[0];
  assert.equal(invoice.total, 238360);
  assert.equal(invoice.state, 'Draft');
  await form('invoice-action', { id: String(invoice.id), action: 'confirm' });
  await form('payment', {
    invoice_id: String(invoice.id),
    amount: '1000.00',
    reference: 'FRONT-UPI',
    date: '2026-10-31',
    method: 'UPI',
    note: 'First installment',
  });
  assert.equal((await api('invoice?id=' + invoice.id)).balance, 138360);
  const csv = `reference,customer,amount,date,method\nINV-${invoice.id},Frontend Customer,1383.60,2026-10-31,NEFT\n`;
  const upload = {
    id: 'csv',
    disabled: false,
    files: [{ size: csv.length, text: async () => csv }],
  };
  await events.change({ target: upload });
  assert.equal(upload.disabled, false);
  let bank = (await api('bank?q=Frontend')).rows[0];
  assert.equal(bank.suggestions[0].id, invoice.id);
  await form('allocate', {
    bank_id: String(bank.id),
    invoice_id: String(invoice.id),
    amount: '1383.60',
  });
  assert.equal((await api('invoice?id=' + invoice.id)).state, 'Paid');
  await form('invoice-action', { id: String(invoice.id), action: 'send' });
  let mail = (await api('mailbox-all')).rows[0];
  assert.equal(mail.recipient, 'frontend.customer@example.test');
  assert.equal(mail.status, 'Suppressed demo recipient');
  detail = await api('subscription?id=' + sub.id);
  const changedLines = detail.lines.map((l) => ({
    line_id: l.id,
    product_id: l.product_id,
    variant_id: l.variant_id || 0,
    qty: 3,
    tax_id: l.tax_id,
  }));
  await form(
    'edit-subscription',
    {
      customer: 'Frontend Customer',
      email: 'frontend.customer@example.test',
      expiry: '2026-12-31',
      terms_days: '0',
      quotation_until: detail.quotation_until,
      discount_id: String(discount.id),
    },
    changedLines,
    { reprice: false },
    { id: sub.id },
  );
  assert.equal((await api('subscription?id=' + sub.id)).lines[0].qty, 3);
  assert.equal((await api('invoice?id=' + invoice.id)).total, 238360);
  // Staff creation is exercised through the real form and backend.
  await form('edit-staff', {
    name: 'Frontend Staff',
    email: 'frontend.staff@example.test',
    password: 'FrontendPass!2026',
  });
  const screens = [
    'dashboard',
    'subscriptions',
    'invoices',
    'payments',
    'reconcile',
    'bank',
    'rehearsal',
    'recovery',
    'products',
    'variants',
    'plans',
    'taxes',
    'discounts',
    'templates',
    'staff',
    'checks',
    'mailbox-all',
  ];
  for (const view of screens) {
    context.testView = view;
    run("state={view:testView,page:1,q:'',status:'',from:'',to:''}");
    const html = await run('viewHTML()');
    assert.equal(typeof html, 'string');
    assert.ok(html.length > 50, view);
  }
  // Test failed server validation remains visible in the form.
  await form(
    'transition',
    { id: String(sub.id), state: 'Quotation' },
    null,
    {},
    { error: /Invalid subscription transition/ },
  );
  await run("action('logout')");
  await form('login', {
    email: 'frontend.customer@example.test',
    password: 'FrontendPass!2026',
  });
  let owned = (await api('subscriptions')).rows;
  assert.equal(owned.length, 1);
  assert.equal(owned[0].id, sub.id);
  assert.equal((await api('invoices')).rows[0].id, invoice.id);
  assert.equal((await api('payments')).rows.length, 2);
  for (const view of ['dashboard', 'subscriptions', 'invoices', 'payments']) {
    context.testView = view;
    run("state={view:testView,page:1,q:'',status:'',from:'',to:''}");
    assert.ok((await run('viewHTML()')).length > 50);
  }
  const denied = await fetch(base + '/api/invoice.pdf?id=1', {
    headers: { Cookie: cookie },
  });
  assert.equal(denied.status, 403);
  const pdf = await fetch(base + '/api/invoice.pdf?id=' + invoice.id, {
    headers: { Cookie: cookie },
  });
  assert.equal(pdf.status, 200);
  assert.equal(
    Buffer.from(await pdf.arrayBuffer())
      .subarray(0, 4)
      .toString(),
    '%PDF',
  );
  const report = {
    kind: 'Actual frontend handlers + real HTTP; isolated DOM adapter, not a browser',
    forms: [
      'signup',
      'login',
      'products',
      'variants',
      'taxes',
      'plans',
      'discounts',
      'templates',
      'subscriptions',
      'transitions',
      'billing',
      'invoice confirmation',
      'partial payment',
      'CSV upload',
      'allocation',
      'email queue',
      'staff',
    ],
    admin_screen_templates_checked: screens,
    customer_screen_templates_checked: 4,
    requests: requests.length,
    all_passed: true,
  };
  fs.mkdirSync('reports', { recursive: true });
  fs.writeFileSync('reports/frontend-verification.json', JSON.stringify(report, null, 2));
  console.log(JSON.stringify(report, null, 2));
})().catch((e) => {
  console.error(e);
  process.exitCode = 1;
});
