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
  const [configResponse, photosResponse] = await Promise.all([fetch('/api/config'), fetch('/api/photos')]);
  config = await configResponse.json(); const photos = (await photosResponse.json()).photos;
  addOptions(domain, Object.keys(config.domains), 'matrixedu');
  domain.innerHTML = Object.keys(config.domains).map(key => `<option value="${key}">${key === 'matrixedu' ? 'MatrixEdu' : key === 'edunews' ? 'EduNews' : key}</option>`).join('');
  refreshTemplates(); addOptions(category, config.categories, 'news');
  photo.innerHTML = `<option value="">Auto-select for category</option>${photos.map(item => `<option value="${item}">${item.split('/').pop().replace('.png', '')}</option>`).join('')}`;
  document.getElementById('brandCount').textContent = Object.keys(config.domains).length;
  document.getElementById('templateCount').textContent = Object.values(config.domains).reduce((sum, item) => sum + item.templates.length, 0);
  document.getElementById('assetCount').textContent = photos.length;
  renderPreview();
}
domain.addEventListener('change', refreshTemplates);
[template, category, photo, title, highlight, subtitle].forEach(element => element.addEventListener('input', schedulePreview));
form.addEventListener('submit', async event => {
  event.preventDefault(); error.hidden = true; previewState.textContent = 'Exporting…';
  try { const response = await fetch('/api/export', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(getPayload()) }); if (!response.ok) throw new Error((await response.json()).error || 'Export failed.'); const result = await response.json(); downloadLink.href = result.webp; downloadLink.textContent = 'Download latest export'; downloadLink.hidden = false; previewState.textContent = 'Export complete'; window.location.assign(result.webp); } catch (problem) { error.textContent = problem.message; error.hidden = false; previewState.textContent = 'Needs attention'; }
});
document.getElementById('newButton').addEventListener('click', () => { window.location.hash = 'create'; title.value = ''; highlight.value = ''; subtitle.value = ''; downloadLink.hidden = true; updateTitleCount(); schedulePreview(); title.focus(); });
initialise().catch(problem => { error.textContent = `Could not load the editor: ${problem.message}`; error.hidden = false; });
