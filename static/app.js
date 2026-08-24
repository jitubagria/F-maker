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
const assetCategory = document.getElementById('assetCategory');
const assetLibrary = document.getElementById('assetLibrary');
const assetsMessage = document.getElementById('assetsMessage');
const assetComparison = document.getElementById('assetComparison');
const assetBefore = document.getElementById('assetBefore');
const assetAfter = document.getElementById('assetAfter');
let config;
let previewTimer;
let previewUrl;
let assetBeforeUrl;

const addOptions = (element, options, selected) => {
  element.innerHTML = options.map(value => `<option value="${value}" ${value === selected ? 'selected' : ''}>${value.replaceAll('_', ' ')}</option>`).join('');
};
const getPayload = () => ({ domain: domain.value, template: template.value, category: category.value, title: title.value, highlight: highlight.value, subtitle: subtitle.value, photo: photo.value || null });
const updateTitleCount = () => titleCount.textContent = `${title.value.length} / 140`;
const updateLabel = () => label.textContent = `${domain.options[domain.selectedIndex].text} / ${template.value.replaceAll('_', ' ')}`;
const escapeHtml = (value) => String(value).replace(/[&<>'"]/g, (character) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', "'": '&#39;', '"': '&quot;' }[character]));

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

function renderAssets(payload) {
  const selected = assetCategory.value;
  document.getElementById('assetModel').textContent = `rembg model ${payload.model}`;
  addOptions(assetCategory, payload.categories.map((item) => item.name), selected || payload.categories[0]?.name);
  const active = payload.categories.find((item) => item.name === assetCategory.value);
  if (!active) { assetLibrary.innerHTML = '<div class="assets-empty"><h2>No categories yet</h2><p>Create a category to begin building the local library.</p></div>'; return; }
  assetLibrary.innerHTML = `<section class="asset-category-card"><div class="asset-category-heading"><div><p class="eyebrow">${escapeHtml(active.name)}</p><h2>${active.cutouts.length} cutout${active.cutouts.length === 1 ? '' : 's'}</h2><p>${active.raw_count} original${active.raw_count === 1 ? '' : 's'} kept locally.</p></div></div>${active.cutouts.length ? `<div class="asset-grid">${active.cutouts.map((item) => `<article class="asset-card"><div class="checkerboard"><img src="${item.url}" alt="${escapeHtml(item.name)} cutout" /></div><div><h3>${escapeHtml(item.name)}</h3><p>${item.has_raw ? 'Original available' : 'No matching original'}</p><div class="asset-actions">${item.has_raw ? '<button type="button" data-recut>Re-cut</button><label><input type="checkbox" data-alpha /> Alpha matting</label>' : ''}<button type="button" class="danger-link" data-asset-delete>Delete cutout</button></div></div></article>`).join('')}</div>` : '<div class="assets-empty"><h2>No cutouts in this category</h2><p>Upload a source image to create the first transparent PNG.</p></div>'}</section>`;
  assetLibrary.querySelectorAll('[data-recut]').forEach((button) => button.addEventListener('click', () => recutAsset(button.closest('.asset-card'))));
  assetLibrary.querySelectorAll('[data-asset-delete]').forEach((button) => button.addEventListener('click', () => deleteAsset(button.closest('.asset-card'))));
}

async function refreshPhotoPicker() {
  const response = await fetch('/api/photos');
  if (!response.ok) throw new Error('Cutout picker could not be refreshed.');
  const selected = photo.value;
  const photos = (await response.json()).photos;
  photo.innerHTML = `<option value="">Auto-select for category</option>${photos.map((item) => `<option value="${item}">${item.split('/').pop().replace('.png', '')}</option>`).join('')}`;
  if (photos.includes(selected)) photo.value = selected;
}

async function loadAssets() {
  try {
    const response = await fetch('/api/assets');
    if (!response.ok) throw new Error('Asset library could not be loaded.');
    renderAssets(await response.json());
    assetsMessage.textContent = '';
  } catch (problem) { assetsMessage.textContent = problem.message; }
}

async function recutAsset(card) {
  const name = card.querySelector('h3').textContent;
  const alpha = card.querySelector('[data-alpha]').checked;
  try {
    assetsMessage.textContent = `Re-cutting ${name}…`;
    const response = await fetch('/api/assets/recut', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ category: assetCategory.value, file: name, alpha_matting: alpha }) });
    const result = await response.json();
    if (!response.ok) throw new Error(result.error || 'Cutout could not be reprocessed.');
    assetAfter.src = `${result.asset.url}?v=${Date.now()}`;
    assetComparison.hidden = false;
    await loadAssets();
    assetsMessage.textContent = `Re-cut ${name}${alpha ? ' with alpha matting' : ''}.`;
  } catch (problem) { assetsMessage.textContent = problem.message; }
}

async function deleteAsset(card) {
  const name = card.querySelector('h3').textContent;
  if (!window.confirm(`Delete transparent cutout ${name}? The original photo is kept.`)) return;
  try {
    const response = await fetch(`/api/assets/${encodeURIComponent(assetCategory.value)}/${encodeURIComponent(name)}`, { method: 'DELETE' });
    const result = await response.json();
    if (!response.ok) throw new Error(result.error || 'Cutout could not be deleted.');
    await loadAssets();
    await refreshPhotoPicker();
    schedulePreview();
    assetsMessage.textContent = `Deleted ${name}; its original photo remains.`;
  } catch (problem) { assetsMessage.textContent = problem.message; }
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
  loadAssets();
  renderPreview();
}
domain.addEventListener('change', refreshTemplates);
[template, category, photo, title, highlight, subtitle].forEach(element => element.addEventListener('input', schedulePreview));
form.addEventListener('submit', async event => {
  event.preventDefault(); error.hidden = true; previewState.textContent = 'Exporting…';
  try { const response = await fetch('/api/export', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(getPayload()) }); if (!response.ok) throw new Error((await response.json()).error || 'Export failed.'); const result = await response.json(); downloadLink.href = result.webp; downloadLink.textContent = 'Download latest export'; downloadLink.hidden = false; previewState.textContent = 'Export complete'; await loadExports(); window.location.assign(result.webp); } catch (problem) { error.textContent = problem.message; error.hidden = false; previewState.textContent = 'Needs attention'; }
});
document.getElementById('newButton').addEventListener('click', () => { window.location.hash = 'create'; title.value = ''; highlight.value = ''; subtitle.value = ''; downloadLink.hidden = true; updateTitleCount(); schedulePreview(); title.focus(); });
assetCategory.addEventListener('change', loadAssets);
document.getElementById('createCategoryForm').addEventListener('submit', async (event) => {
  event.preventDefault();
  try {
    const response = await fetch('/api/assets/create-category', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ category: document.getElementById('newCategory').value }) });
    const result = await response.json();
    if (!response.ok) throw new Error(result.error || 'Category could not be created.');
    document.getElementById('newCategory').value = '';
    await loadAssets();
    assetCategory.value = result.category;
    await loadAssets();
    assetsMessage.textContent = `Created ${result.category}.`;
  } catch (problem) { assetsMessage.textContent = problem.message; }
});
document.getElementById('assetUploadForm').addEventListener('submit', async (event) => {
  event.preventDefault();
  const file = document.getElementById('assetUpload').files[0];
  if (!file) return;
  if (assetBeforeUrl) URL.revokeObjectURL(assetBeforeUrl);
  assetBeforeUrl = URL.createObjectURL(file);
  assetBefore.src = assetBeforeUrl;
  assetsMessage.textContent = `Creating a cutout with ${document.getElementById('assetModel').textContent.replace('rembg model ', '')}…`;
  const formData = new FormData(); formData.append('category', assetCategory.value); formData.append('photo', file);
  try {
    const response = await fetch('/api/assets/upload', { method: 'POST', body: formData });
    const result = await response.json();
    if (!response.ok) throw new Error(result.error || 'Cutout could not be created.');
    assetAfter.src = result.asset.url;
    assetComparison.hidden = false;
    document.getElementById('assetUploadForm').reset();
    await loadAssets();
    await refreshPhotoPicker();
    schedulePreview();
    assetsMessage.textContent = `Created ${result.asset.name}.`;
  } catch (problem) { assetsMessage.textContent = problem.message; }
});
window.addEventListener('hashchange', () => { if (window.location.hash === '#exports') loadExports(); if (window.location.hash === '#assets') loadAssets(); });
initialise().catch(problem => { error.textContent = `Could not load the editor: ${problem.message}`; error.hidden = false; });
