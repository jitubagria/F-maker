import { startRouter } from './router.mjs';

startRouter();

const form = document.getElementById('editorForm');
const domain = document.getElementById('domain');
const template = document.getElementById('template');
const category = document.getElementById('category');
const photo = document.getElementById('photo');
const title = document.getElementById('title');
const highlight = document.getElementById('highlight');
const subtitle = document.getElementById('subtitle');
const preview = document.getElementById('previewImage');
const error = document.getElementById('formError');
const label = document.getElementById('previewLabel');
const previewState = document.getElementById('previewState');
const titleCount = document.getElementById('titleCount');
const downloadLink = document.getElementById('downloadLink');
let config;
let previewTimer;
let previewUrl;

const addOptions = (element, options, selected) => {
  element.innerHTML = options.map(value => `<option value="${value}" ${value === selected ? 'selected' : ''}>${value.replaceAll('_', ' ')}</option>`).join('');
};
const getPayload = () => ({ domain: domain.value, template: template.value, category: category.value, title: title.value, highlight: highlight.value, subtitle: subtitle.value, photo: photo.value || null });
const updateTitleCount = () => titleCount.textContent = `${title.value.length} / 140`;
const updateLabel = () => label.textContent = `${domain.options[domain.selectedIndex].text} / ${template.value.replaceAll('_', ' ')}`;

function renderDashboard(stats) {
  document.getElementById('statBrands').textContent = stats.brands;
  document.getElementById('statTemplates').textContent = stats.templates;
  document.getElementById('statCutouts').textContent = stats.total_cutouts;
  document.getElementById('statExports').textContent = stats.total_exports;
  document.getElementById('categoryBreakdown').innerHTML = Object.entries(stats.cutouts_by_category)
    .map(([name, count]) => `<div class="category-row"><span>${name.replaceAll('_', ' ')}</span><strong>${count}</strong></div>`).join('');
}

function bytes(value) {
  if (value < 1024) return `${value} B`;
  if (value < 1024 * 1024) return `${(value / 1024).toFixed(1)} KB`;
  return `${(value / (1024 * 1024)).toFixed(1)} MB`;
}

function renderExports(items) {
  const grid = document.getElementById('exportsGrid');
  const empty = document.getElementById('exportsEmpty');
  empty.hidden = items.length > 0;
  grid.innerHTML = items.map((item) => `<article class="export-card"><div class="export-thumb">${item.thumb_url ? `<img src="${item.thumb_url}" alt="Preview of ${item.name}" />` : '<span>WEBP</span>'}</div><div class="export-card-body"><h2>${item.name}</h2><p>${new Date(item.modified).toLocaleString()} · ${bytes(item.size)}</p><div><a href="${item.url}">Download</a><button type="button" data-export-delete="${item.name}">Delete</button></div></div></article>`).join('');
  grid.querySelectorAll('[data-export-delete]').forEach((button) => button.addEventListener('click', () => deleteExport(button.dataset.exportDelete)));
}

async function loadExports() {
  const message = document.getElementById('exportsMessage');
  try {
    const response = await fetch('/api/exports');
    if (!response.ok) throw new Error('Exports could not be loaded.');
    renderExports(await response.json());
    message.textContent = '';
  } catch (problem) { message.textContent = problem.message; }
}

async function deleteExport(name) {
  if (!window.confirm(`Delete ${name} and its PNG preview?`)) return;
  const message = document.getElementById('exportsMessage');
  try {
    const response = await fetch(`/api/exports/${encodeURIComponent(name)}`, { method: 'DELETE' });
    const result = await response.json();
    if (!response.ok) throw new Error(result.error || 'Export could not be deleted.');
    message.textContent = `Deleted ${name}.`;
    await loadExports();
  } catch (problem) { message.textContent = problem.message; }
}

async function renderPreview() {
  clearTimeout(previewTimer);
  updateTitleCount(); updateLabel(); error.hidden = true;
  if (!title.value.trim()) { preview.removeAttribute('src'); previewState.textContent = 'Add a headline'; return; }
  previewState.textContent = 'Rendering preview…';
  try {
    const response = await fetch('/api/preview', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(getPayload()) });
    if (!response.ok) throw new Error((await response.json()).error || 'Preview could not be created.');
    const nextUrl = URL.createObjectURL(await response.blob());
    if (previewUrl) URL.revokeObjectURL(previewUrl);
    previewUrl = nextUrl; preview.src = nextUrl; previewState.textContent = 'Preview ready';
  } catch (problem) { error.textContent = problem.message; error.hidden = false; previewState.textContent = 'Needs attention'; }
}
function schedulePreview() { clearTimeout(previewTimer); previewTimer = setTimeout(renderPreview, 350); }
function refreshTemplates() { addOptions(template, config.domains[domain.value].templates, config.domains[domain.value].templates[0]); updateLabel(); schedulePreview(); }

async function initialise() {
  const [configResponse, photosResponse, statsResponse] = await Promise.all([fetch('/api/config'), fetch('/api/photos'), fetch('/api/stats')]);
  config = await configResponse.json(); const photos = (await photosResponse.json()).photos; const stats = await statsResponse.json();
  addOptions(domain, Object.keys(config.domains), 'matrixedu');
  domain.innerHTML = Object.keys(config.domains).map(key => `<option value="${key}">${key === 'matrixedu' ? 'MatrixEdu' : key === 'edunews' ? 'EduNews' : key}</option>`).join('');
  refreshTemplates(); addOptions(category, config.categories, 'news');
  photo.innerHTML = `<option value="">Auto-select for category</option>${photos.map(item => `<option value="${item}">${item.split('/').pop().replace('.png', '')}</option>`).join('')}`;
  document.getElementById('brandCount').textContent = stats.brands;
  document.getElementById('templateCount').textContent = stats.templates;
  document.getElementById('assetCount').textContent = stats.total_cutouts;
  renderDashboard(stats);
  loadExports();
  renderPreview();
}
domain.addEventListener('change', refreshTemplates);
[template, category, photo, title, highlight, subtitle].forEach(element => element.addEventListener('input', schedulePreview));
form.addEventListener('submit', async event => {
  event.preventDefault(); error.hidden = true; previewState.textContent = 'Exporting…';
  try { const response = await fetch('/api/export', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(getPayload()) }); if (!response.ok) throw new Error((await response.json()).error || 'Export failed.'); const result = await response.json(); downloadLink.href = result.webp; downloadLink.textContent = 'Download latest export'; downloadLink.hidden = false; previewState.textContent = 'Export complete'; await loadExports(); window.location.assign(result.webp); } catch (problem) { error.textContent = problem.message; error.hidden = false; previewState.textContent = 'Needs attention'; }
});
document.getElementById('newButton').addEventListener('click', () => { window.location.hash = 'create'; title.value = ''; highlight.value = ''; subtitle.value = ''; downloadLink.hidden = true; updateTitleCount(); schedulePreview(); title.focus(); });
window.addEventListener('hashchange', () => { if (window.location.hash === '#exports') loadExports(); });
initialise().catch(problem => { error.textContent = `Could not load the editor: ${problem.message}`; error.hidden = false; });
