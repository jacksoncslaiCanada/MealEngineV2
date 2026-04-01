'use strict';

const PAGE_SIZE = 50;
let currentOffset = 0;
let currentTotal = 0;
let currentSort = 'newest';

// ── DOM refs ──────────────────────────────────────────────────────────────────
const filterQ       = document.getElementById('filterQ');
const filterSource  = document.getElementById('filterSource');
const filterMinIng  = document.getElementById('filterMinIng');
const minIngLabel   = document.getElementById('minIngLabel');
const applyBtn      = document.getElementById('applyBtn');
const resetBtn      = document.getElementById('resetBtn');
const sortNewest    = document.getElementById('sortNewest');
const sortEngagement = document.getElementById('sortEngagement');

const spinner       = document.getElementById('loadingSpinner');
const emptyState    = document.getElementById('emptyState');
const tableCard     = document.getElementById('tableCard');
const tbody         = document.getElementById('recipesTbody');
const resultsMeta   = document.getElementById('resultsMeta');
const pageLabel     = document.getElementById('pageLabel');
const prevBtn       = document.getElementById('prevBtn');
const nextBtn       = document.getElementById('nextBtn');

// ── Helpers ───────────────────────────────────────────────────────────────────
function sourceBadge(source) {
  const labels = { youtube: 'YouTube', themealdb: 'TheMealDB', rss: 'RSS', reddit: 'Reddit' };
  const label = labels[source] || source;
  return `<span class="source-badge source-${source}">${label}</span>`;
}

function scoreBar(score) {
  if (score == null) return '<span class="text-muted small">—</span>';
  const pct = Math.round(score);
  const colour = pct >= 70 ? 'success' : pct >= 40 ? 'warning' : 'secondary';
  return `
    <div class="d-flex align-items-center gap-2">
      <div class="progress flex-grow-1" style="height:.45rem">
        <div class="progress-bar bg-${colour}" style="width:${pct}%"></div>
      </div>
      <span class="small text-muted">${pct}</span>
    </div>`;
}

function relativeDate(iso) {
  const d = new Date(iso);
  const days = Math.floor((Date.now() - d) / 86400000);
  if (days === 0) return 'Today';
  if (days === 1) return 'Yesterday';
  if (days < 30) return `${days}d ago`;
  if (days < 365) return `${Math.floor(days / 30)}mo ago`;
  return `${Math.floor(days / 365)}y ago`;
}

function truncate(str, n) {
  return str.length > n ? str.slice(0, n) + '…' : str;
}

// ── Build API URL from current filter state ───────────────────────────────────
function buildUrl(offset) {
  const params = new URLSearchParams();
  const q = filterQ.value.trim();
  if (q) params.set('q', q);
  const src = filterSource.value;
  if (src) params.set('source', src);
  const minIng = parseInt(filterMinIng.value, 10);
  if (minIng > 0) params.set('min_ingredients', minIng);
  params.set('sort', currentSort);
  params.set('limit', PAGE_SIZE);
  params.set('offset', offset);
  return `/recipes/browse?${params}`;
}

// ── Render ────────────────────────────────────────────────────────────────────
function renderRows(recipes) {
  tbody.innerHTML = '';
  recipes.forEach(r => {
    const tr = document.createElement('tr');
    tr.className = 'recipe-row';
    tr.innerHTML = `
      <td>
        <a href="${r.url}" target="_blank" rel="noopener" class="text-decoration-none fw-semibold">
          ${truncate(r.title || r.url, 80)}
        </a>
      </td>
      <td>${sourceBadge(r.source)}</td>
      <td class="text-center">
        ${r.ingredient_count > 0
          ? `<span class="ing-pill">${r.ingredient_count}</span>`
          : '<span class="text-muted small">—</span>'}
      </td>
      <td>${scoreBar(r.engagement_score)}</td>
      <td><span class="small text-muted" title="${r.fetched_at}">${relativeDate(r.fetched_at)}</span></td>
      <td class="text-end">
        <a href="${r.url}" target="_blank" rel="noopener"
           class="btn btn-outline-secondary btn-sm py-0">
          <i class="bi bi-box-arrow-up-right"></i>
        </a>
      </td>`;
    tbody.appendChild(tr);
  });
}

// ── Fetch & display ───────────────────────────────────────────────────────────
async function load(offset = 0) {
  currentOffset = offset;

  spinner.classList.remove('d-none');
  tableCard.classList.add('d-none');
  emptyState.classList.add('d-none');
  resultsMeta.textContent = '';

  try {
    const res = await fetch(buildUrl(offset));
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const recipes = await res.json();

    spinner.classList.add('d-none');

    if (recipes.length === 0 && offset === 0) {
      emptyState.classList.remove('d-none');
      prevBtn.disabled = true;
      nextBtn.disabled = true;
      pageLabel.textContent = '';
      return;
    }

    renderRows(recipes);
    tableCard.classList.remove('d-none');

    // Pagination state
    const from = offset + 1;
    const to = offset + recipes.length;
    const hasMore = recipes.length === PAGE_SIZE;
    resultsMeta.textContent = `Showing ${from}–${to}`;
    pageLabel.textContent = `${from}–${to}`;
    prevBtn.disabled = offset === 0;
    nextBtn.disabled = !hasMore;

  } catch (err) {
    spinner.classList.add('d-none');
    emptyState.classList.remove('d-none');
    emptyState.querySelector('p').textContent = `Error loading recipes: ${err.message}`;
  }
}

// ── Event listeners ───────────────────────────────────────────────────────────
filterMinIng.addEventListener('input', () => {
  minIngLabel.textContent = filterMinIng.value;
});

applyBtn.addEventListener('click', () => load(0));

resetBtn.addEventListener('click', () => {
  filterQ.value = '';
  filterSource.value = '';
  filterMinIng.value = 0;
  minIngLabel.textContent = '0';
  currentSort = 'newest';
  sortNewest.classList.add('active');
  sortEngagement.classList.remove('active');
  load(0);
});

[sortNewest, sortEngagement].forEach(btn => {
  btn.addEventListener('click', () => {
    currentSort = btn.dataset.sort;
    sortNewest.classList.toggle('active', currentSort === 'newest');
    sortEngagement.classList.toggle('active', currentSort === 'engagement');
    load(0);
  });
});

filterQ.addEventListener('keydown', e => { if (e.key === 'Enter') load(0); });

prevBtn.addEventListener('click', () => load(Math.max(0, currentOffset - PAGE_SIZE)));
nextBtn.addEventListener('click', () => load(currentOffset + PAGE_SIZE));

// ── Initial load ──────────────────────────────────────────────────────────────
load(0);
