/* Meal Planner — tag input, API call, and results rendering */
'use strict';

// ── State ────────────────────────────────────────────────────────────────────

const tags = new Set();

// ── DOM refs ─────────────────────────────────────────────────────────────────

const tagWrapper   = document.getElementById('tagWrapper');
const tagInput     = document.getElementById('tagInput');
const coverageSlider = document.getElementById('coverageSlider');
const coverageLabel  = document.getElementById('coverageLabel');
const findBtn      = document.getElementById('findBtn');
const resultsArea  = document.getElementById('resultsArea');

// ── Tag input ────────────────────────────────────────────────────────────────

function addTag(raw) {
  const value = raw.trim().toLowerCase();
  if (!value || tags.has(value)) return;
  tags.add(value);
  renderTags();
  syncButton();
}

function removeTag(value) {
  tags.delete(value);
  renderTags();
  syncButton();
}

function renderTags() {
  // Remove existing tag elements (leave the input intact)
  tagWrapper.querySelectorAll('.tag').forEach(el => el.remove());

  // Insert tags before the input
  for (const value of tags) {
    const tag = document.createElement('span');
    tag.className = 'tag';
    tag.innerHTML = `${escHtml(value)} <span class="remove" data-value="${escHtml(value)}" title="Remove">&times;</span>`;
    tagWrapper.insertBefore(tag, tagInput);
  }
}

function syncButton() {
  findBtn.disabled = tags.size === 0;
}

tagWrapper.addEventListener('click', e => {
  if (e.target.classList.contains('remove')) {
    removeTag(e.target.dataset.value);
  } else {
    tagInput.focus();
  }
});

tagInput.addEventListener('keydown', e => {
  if (e.key === 'Enter' || e.key === ',') {
    e.preventDefault();
    addTag(tagInput.value.replace(/,$/, ''));
    tagInput.value = '';
  } else if (e.key === 'Backspace' && tagInput.value === '' && tags.size > 0) {
    // Remove last tag on backspace when input is empty
    const last = [...tags].pop();
    removeTag(last);
  }
});

tagInput.addEventListener('blur', () => {
  if (tagInput.value.trim()) {
    addTag(tagInput.value);
    tagInput.value = '';
  }
});

// ── Coverage slider ──────────────────────────────────────────────────────────

coverageSlider.addEventListener('input', () => {
  coverageLabel.textContent = coverageSlider.value + '%';
});

// ── API call ─────────────────────────────────────────────────────────────────

findBtn.addEventListener('click', fetchRecipes);

async function fetchRecipes() {
  if (tags.size === 0) return;

  setLoading(true);
  resultsArea.innerHTML = '';

  const params = new URLSearchParams();
  for (const t of tags) params.append('ingredient', t);
  params.set('min_coverage', (parseInt(coverageSlider.value) / 100).toFixed(2));
  params.set('limit', '50');

  try {
    const resp = await fetch(`/recipes/meal-plan?${params}`);
    if (!resp.ok) throw new Error(`Server error: ${resp.status}`);
    const recipes = await resp.json();
    renderResults(recipes);
  } catch (err) {
    resultsArea.innerHTML = errorBanner(err.message);
  } finally {
    setLoading(false);
  }
}

// ── Rendering ────────────────────────────────────────────────────────────────

function renderResults(recipes) {
  if (recipes.length === 0) {
    resultsArea.innerHTML = `
      <div class="text-center py-5 text-muted">
        <i class="bi bi-emoji-frown fs-1 d-block mb-2"></i>
        <p class="mb-1 fw-semibold">No recipes found</p>
        <p class="small">Try adding more ingredients or lowering the coverage threshold.</p>
      </div>`;
    return;
  }

  const header = `
    <p class="text-muted mb-3">
      <i class="bi bi-check2-circle text-success me-1"></i>
      Found <strong>${recipes.length}</strong> recipe${recipes.length !== 1 ? 's' : ''}
    </p>`;

  const cards = recipes.map(r => recipeCard(r)).join('');
  resultsArea.innerHTML = header + cards;

  // Toggle ingredient panels without depending on Bootstrap's JS global.
  // Bootstrap CSS handles visibility: .collapse = hidden, .collapse.show = visible.
  resultsArea.addEventListener('click', e => {
    const btn = e.target.closest('[data-bs-toggle="collapse"]');
    if (!btn) return;
    const target = document.querySelector(btn.dataset.bsTarget);
    if (target) target.classList.toggle('show');
  });
}

function recipeCard(recipe) {
  const pct        = Math.round(recipe.coverage * 100);
  const barColor   = pct === 100 ? 'bg-success' : pct >= 75 ? 'bg-primary' : pct >= 50 ? 'bg-warning' : 'bg-danger';
  const sourceBadge = sourceBadgeHtml(recipe.source);
  const recipeTitle = recipe.source_id || `Recipe #${recipe.id}`;
  const cardId      = `recipe-${recipe.id}`;

  const ingredientPills = (recipe.ingredients || []).map(ing => {
    const isCovered = isIngredientCovered(ing);
    return `<span class="ingredient-pill badge ${isCovered ? 'bg-success-subtle text-success-emphasis border border-success-subtle' : 'bg-secondary-subtle text-secondary-emphasis border border-secondary-subtle'}">
      ${isCovered ? '<i class="bi bi-check-lg me-1"></i>' : '<i class="bi bi-dash me-1"></i>'}${escHtml(ing.ingredient_name)}
    </span>`;
  }).join(' ');

  return `
    <div class="card shadow-sm mb-3 recipe-card">
      <div class="card-body">
        <div class="d-flex align-items-start justify-content-between gap-2 mb-2">
          <div>
            ${sourceBadge}
            <span class="fw-semibold ms-1">${escHtml(recipeTitle)}</span>
          </div>
          <a href="${escHtml(recipe.url)}" target="_blank" rel="noopener"
             class="btn btn-sm btn-outline-secondary flex-shrink-0">
            <i class="bi bi-box-arrow-up-right me-1"></i>Open
          </a>
        </div>

        <!-- Coverage bar -->
        <div class="coverage-bar mb-2">
          <div class="d-flex justify-content-between small text-muted mb-1">
            <span>${recipe.matched_count} / ${recipe.total_count} ingredients covered</span>
            <span class="fw-bold ${pct === 100 ? 'text-success' : ''}">${pct}%</span>
          </div>
          <div class="progress">
            <div class="progress-bar ${barColor}" style="width: ${pct}%" role="progressbar"
                 aria-valuenow="${pct}" aria-valuemin="0" aria-valuemax="100"></div>
          </div>
        </div>

        <!-- Ingredient pills (collapsible) -->
        <button class="btn btn-link btn-sm p-0 text-decoration-none text-muted mb-2"
                type="button" data-bs-toggle="collapse" data-bs-target="#${cardId}-ingredients">
          <i class="bi bi-list-ul me-1"></i>Show ingredients
        </button>
        <div class="collapse" id="${cardId}-ingredients">
          <div class="d-flex flex-wrap gap-1 mt-2">
            ${ingredientPills}
          </div>
        </div>
      </div>
    </div>`;
}

function isIngredientCovered(ing) {
  const name      = (ing.ingredient_name || '').toLowerCase();
  const canonical = (ing.canonical_name  || '').toLowerCase();
  for (const t of tags) {
    if (name.includes(t) || t.includes(name))           return true;
    if (canonical && (canonical.includes(t) || t.includes(canonical))) return true;
  }
  return false;
}

function sourceBadgeHtml(source) {
  const map = {
    youtube:   ['badge-youtube',   'bi-youtube',    'YouTube'],
    themealdb: ['badge-themealdb', 'bi-journal-text','TheMealDB'],
    reddit:    ['badge-reddit',    'bi-reddit',     'Reddit'],
  };
  const [cls, icon, label] = map[source] || ['bg-secondary', 'bi-globe', source];
  return `<span class="badge ${cls} text-white"><i class="bi ${icon} me-1"></i>${label}</span>`;
}

// ── Helpers ──────────────────────────────────────────────────────────────────

function setLoading(on) {
  findBtn.disabled = on;
  findBtn.innerHTML = on
    ? '<span class="spinner-border spinner-border-sm me-2"></span>Searching…'
    : '<i class="bi bi-search me-2"></i>Find Recipes';
}

function errorBanner(msg) {
  return `<div class="alert alert-danger"><i class="bi bi-exclamation-triangle me-2"></i>${escHtml(msg)}</div>`;
}

function escHtml(str) {
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}
