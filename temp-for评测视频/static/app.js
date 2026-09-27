(() => {
  'use strict';

  const PAGE_SIZE = 8;
  const LAST_RUN_KEY = 'jev-video-last-run';
  const HISTORY_KEY = 'jev-video-run-history';
  const ACTIVE_STATUSES = new Set(['queued', 'starting', 'running', 'in_progress', 'stopping']);
  const TERMINAL_STATUSES = new Set(['completed', 'complete', 'finished', 'succeeded', 'success', 'stopped', 'cancelled', 'canceled', 'failed']);
  const COMPLETE_STATUSES = new Set(['completed', 'complete', 'finished', 'succeeded', 'success']);

  const el = (id) => document.getElementById(id);
  const ui = {
    concurrency: el('concurrency'), start: el('start-button'), startPilot: el('start-pilot-button'), stop: el('stop-button'), export: el('export-button'),
    launchHint: el('launch-hint'), model: el('model-name'), launchCount: el('launch-case-count'),
    dishCount: el('dish-count'), ingredientCount: el('ingredient-count'), caseCount: el('case-count'),
    positiveCount: el('positive-count'), negativeCount: el('negative-count'), datasetHash: el('dataset-hash'),
    datasetStatus: el('dataset-status'), footerDataset: el('footer-dataset'),
    caseGrid: el('case-grid'), caseGridEmpty: el('case-grid-empty'), caseGridTotal: el('case-grid-total'),
    caseGridCounts: {
      waiting: el('grid-count-waiting'), running: el('grid-count-running'), correct: el('grid-count-correct'),
      incorrect: el('grid-count-incorrect'), undecidable: el('grid-count-undecidable'), failed: el('grid-count-failed'),
      incomplete: el('grid-count-incomplete')
    },
    progressValue: el('progress-value'), progressBar: el('progress-bar'), progressFill: el('progress-fill'), progressFoot: el('progress-foot'),
    elapsedValue: el('elapsed-value'), elapsedFoot: el('elapsed-foot'), accuracyLabel: el('accuracy-label'),
    accuracyValue: el('accuracy-value'), accuracyFoot: el('accuracy-foot'), costValue: el('cost-value'), costFoot: el('cost-foot'),
    throughputValue: el('throughput-value'), runStrip: document.querySelector('.run-strip'), runState: el('run-state'),
    runStateDetail: el('run-state-detail'), runConcurrency: el('run-concurrency'), runId: el('run-id'),
    resultsBody: el('results-body'), visibleCount: el('visible-count'), pageSummary: el('page-summary'),
    pageIndicator: el('page-indicator'), previousPage: el('previous-page'), nextPage: el('next-page'),
    filterButtons: [...document.querySelectorAll('[data-filter]')], search: el('search-input'),
    filterCounts: { all: el('filter-all-count'), correct: el('filter-correct-count'), incorrect: el('filter-incorrect-count'), undecidable: el('filter-undecidable-count'), failed: el('filter-failed-count') },
    summary: el('summary-section'), summaryScope: el('summary-scope'), summaryStatus: el('summary-status'), summarySentence: el('summary-sentence'),
    summaryFinalLabel: el('summary-final-label'), summaryAccuracy: el('summary-accuracy'), summaryAccuracyDetail: el('summary-accuracy-detail'),
    summaryCoverage: el('summary-coverage'), summaryCoverageDetail: el('summary-coverage-detail'),
    summaryPositive: el('summary-positive-rate'), summaryPositiveDetail: el('summary-positive-detail'),
    summaryNegative: el('summary-negative-rate'), summaryNegativeDetail: el('summary-negative-detail'),
    summaryBalanced: el('summary-balanced-rate'), matrixBody: el('matrix-body'),
    comparisonEmpty: el('comparison-empty'), comparisonContent: el('comparison-content'), toast: el('toast'),
    confirmDialog: el('confirm-dialog'), confirmForm: el('confirm-form'), confirmCount: el('confirm-case-count'),
    confirmTitle: el('confirm-title'), confirmScope: el('confirm-scope'), confirmModel: el('confirm-model'), confirmConcurrency: el('confirm-concurrency'), confirmWarning: el('confirm-warning'), labelDialog: el('label-dialog'),
    detailDialog: el('detail-dialog'), detailTitle: el('detail-title'), detailContent: el('detail-content')
  };

  const state = {
    bootstrap: null,
    run: null,
    runId: null,
    filter: 'all',
    page: 1,
    eventSource: null,
    pollTimer: null,
    elapsedTimer: null,
    toastTimer: null,
    elapsedBase: 0,
    elapsedAnchor: 0,
    recentRuns: [],
    savedRunIds: new Set(),
    caseGridTiles: new Map(),
    pendingScope: 'full',
    runPending: false
  };

  function number(value, fallback = null) {
    return typeof value === 'number' && Number.isFinite(value) ? value : fallback;
  }

  function integer(value, fallback = 0) {
    const parsed = number(value, fallback);
    return Math.max(0, Math.floor(parsed));
  }

  function formatInteger(value) {
    return Number.isFinite(value) ? new Intl.NumberFormat('zh-CN').format(value) : '—';
  }

  function formatPercent(numerator, denominator) {
    if (!Number.isFinite(numerator) || !Number.isFinite(denominator) || denominator <= 0) return '—';
    return `${(numerator / denominator * 100).toFixed(1)}%`;
  }

  function formatDuration(milliseconds, tenths = false) {
    if (!Number.isFinite(milliseconds) || milliseconds < 0) return '—';
    const totalTenths = Math.floor(milliseconds / 100);
    const tenthsPart = totalTenths % 10;
    const totalSeconds = Math.floor(milliseconds / 1000);
    const hours = Math.floor(totalSeconds / 3600);
    const minutes = Math.floor((totalSeconds % 3600) / 60);
    const seconds = totalSeconds % 60;
    if (hours > 0) return `${hours}:${String(minutes).padStart(2, '0')}:${String(seconds).padStart(2, '0')}`;
    if (tenths) return `${String(minutes).padStart(2, '0')}:${String(seconds).padStart(2, '0')}.${tenthsPart}`;
    return `${String(minutes).padStart(2, '0')}:${String(seconds).padStart(2, '0')}`;
  }

  function formatUsd(value) {
    if (!Number.isFinite(value)) return '—';
    return `$${value.toFixed(value > 0 && value < 0.01 ? 6 : 4)}`;
  }

  function text(value, empty = '—') {
    if (value === null || value === undefined || value === '') return empty;
    return String(value);
  }

  function getModelName(model) {
    if (typeof model === 'string') return model;
    if (model && typeof model === 'object') return text(model.name || model.id || model.model || model.slug);
    return '未提供';
  }

  function getModelId(model) {
    if (typeof model === 'string') return model;
    if (model && typeof model === 'object') return text(model.id || model.model || model.slug || model.name, '');
    return '';
  }

  function statusToken(value) {
    return String(value || '').trim().toLowerCase().replace(/[\s-]+/g, '_');
  }

  function currentStatus() {
    return statusToken(state.run?.status);
  }

  function isActive() {
    return ACTIVE_STATUSES.has(currentStatus());
  }

  function isTerminal() {
    return TERMINAL_STATUSES.has(currentStatus());
  }

  function isComplete() {
    return COMPLETE_STATUSES.has(currentStatus());
  }

  function totalCases() {
    if (state.run?.scope === 'pilot32') return integer(state.bootstrap?.pilot?.case_count, 32);
    return integer(state.run?.metrics?.total, integer(state.bootstrap?.dataset?.case_count, state.run?.rows?.length || 0));
  }

  function pilotReady() {
    const pilot = state.bootstrap?.pilot || {};
    return integer(pilot.case_count, 0) === 32
      && integer(pilot.positive_count, 0) === 16
      && integer(pilot.negative_count, 0) === 16
      && Boolean(pilot.sha256);
  }

  function finishedCases() {
    if (!state.run) return 0;
    const explicit = number(state.run.metrics?.done);
    if (explicit !== null) return integer(explicit);
    return (state.run.rows || []).filter((row) => rowIsTerminal(row)).length;
  }

  function rowStatus(row) {
    const status = statusToken(row?.status);
    if (['success', 'succeeded', 'complete', 'completed', 'done'].includes(status)) return 'completed';
    if (['error', 'request_failed', 'timeout', 'exception'].includes(status)) return 'failed';
    if (['pending', 'waiting', 'not_started', 'queued'].includes(status)) return 'pending';
    return status || 'pending';
  }

  function rowIsTerminal(row) {
    return ['completed', 'failed', 'invalid', 'undecidable', 'stopped'].includes(rowStatus(row));
  }

  function rowFailed(row) {
    return ['failed', 'error', 'request_failed', 'timeout', 'exception'].includes(rowStatus(row));
  }

  function choiceToken(choice) {
    let value = choice;
    if (value && typeof value === 'object') {
      value = value.choice ?? value.selection ?? value.value ?? value.decision ?? value.option ?? value.label;
    }
    if (value === null || value === undefined) return '';
    return String(value).trim().toLowerCase().replace(/[\s-]+/g, '_');
  }

  function choiceLabel(choice, row) {
    if (rowFailed(row)) return '请求失败';
    const token = choiceToken(choice);
    if (['reasonable', 'accept', 'accepted', 'yes', 'true', 'match'].includes(token)) return '合理';
    if (['unreasonable', 'reject', 'rejected', 'no', 'false', 'no_match'].includes(token)) return '不合理';
    if (['undecidable', 'unknown', 'uncertain', 'cannot_determine', 'abstain'].includes(token)) return '无法判断';
    if (!token && rowStatus(row) === 'pending') return '等待发送';
    if (!token && rowStatus(row) === 'running') return '处理中';
    if (!token && rowStatus(row) === 'invalid') return '无效响应';
    if (!token) return '暂无选择';
    return String(choice?.choice ?? choice?.selection ?? choice?.value ?? choice?.decision ?? choice?.option ?? choice?.label ?? choice);
  }

  function choiceClass(choice, row) {
    if (rowFailed(row)) return 'choice-failed';
    const token = choiceToken(choice);
    if (['reasonable', 'accept', 'accepted', 'yes', 'true', 'match'].includes(token)) return 'choice-reasonable';
    if (['unreasonable', 'reject', 'rejected', 'no', 'false', 'no_match'].includes(token)) return 'choice-unreasonable';
    if (['undecidable', 'unknown', 'uncertain', 'cannot_determine', 'abstain'].includes(token)) return 'choice-undecidable';
    if (rowStatus(row) === 'running') return 'choice-pending';
    return 'choice-pending';
  }

  function rowVerdict(row) {
    if (typeof row?.correct !== 'boolean') return { label: '待完成', className: 'verdict-pending' };
    return row.correct
      ? { label: '✓ 判断正确', className: 'verdict-correct' }
      : { label: '× 判断错误', className: 'verdict-incorrect' };
  }

  function showToast(message, isError = false) {
    ui.toast.textContent = message;
    ui.toast.hidden = false;
    ui.toast.classList.toggle('is-error', isError);
    window.clearTimeout(state.toastTimer);
    state.toastTimer = window.setTimeout(() => { ui.toast.hidden = true; }, 4200);
  }

  function showLaunchError(message) {
    ui.launchHint.textContent = message;
    ui.launchHint.classList.add('is-error');
  }

  function clearLaunchError() {
    ui.launchHint.classList.remove('is-error');
  }

  async function fetchJson(url, options = {}) {
    const response = await fetch(url, { cache: 'no-store', ...options, headers: { Accept: 'application/json', ...(options.headers || {}) } });
    let data = null;
    const contentType = response.headers.get('content-type') || '';
    if (contentType.includes('json')) {
      try { data = await response.json(); } catch { data = null; }
    }
    if (!response.ok) {
      const message = data?.detail || data?.message || `请求失败（HTTP ${response.status}）`;
      throw new Error(typeof message === 'string' ? message : JSON.stringify(message));
    }
    return data;
  }

  function renderBootstrap() {
    const dataset = state.bootstrap?.dataset || {};
    const modelName = getModelName(state.bootstrap?.model);
    const cases = integer(dataset.case_count, 0);
    ui.model.textContent = modelName;
    ui.launchCount.textContent = `${formatInteger(cases)} 条全量题`;
    ui.dishCount.textContent = formatInteger(number(dataset.dish_count, null));
    ui.ingredientCount.textContent = formatInteger(number(dataset.ingredient_count, null));
    ui.caseCount.textContent = formatInteger(number(dataset.case_count, null));
    ui.positiveCount.textContent = formatInteger(number(dataset.positive_count, null));
    ui.negativeCount.textContent = formatInteger(number(dataset.negative_count, null));
    const hash = text(dataset.sha256, '');
    ui.datasetHash.textContent = hash ? `题集编号 · ${hash.slice(0, 12)}` : '题集编号暂不可用';
    ui.footerDataset.textContent = hash ? `题集编号 · ${hash.slice(0, 12)}` : '题目清单尚未载入';

    const hasKey = state.bootstrap?.api_key_available === true;
    const ready = cases === 720 && Boolean(dataset.sha256) && hasKey;
    ui.start.disabled = !ready || isActive() || state.runPending;
    ui.startPilot.disabled = !pilotReady() || !hasKey || isActive() || state.runPending;
    ui.datasetStatus.classList.toggle('is-error', !dataset.sha256 || cases === 0);
    const statusLabel = !dataset.sha256 || cases === 0 ? '题目未就绪' : '题目已准备';
    ui.datasetStatus.lastChild.textContent = statusLabel;
    if (!cases || !dataset.sha256) showLaunchError('固定题目尚未准备好，请按 README 中的步骤完成准备。');
    else if (!hasKey) showLaunchError('本机服务尚未读取到评测密钥，请按 README 配置后重启服务。');
    else if (isActive()) ui.launchHint.textContent = '已恢复当前活动评测，可继续观察进度。';
    else if (!ui.launchHint.classList.contains('is-error')) ui.launchHint.textContent = '点击开始后会显示本轮请求数量和费用提醒。';
    renderSetupButtons();
  }

  function renderSetupButtons() {
    const keyReady = state.bootstrap?.api_key_available === true;
    const busy = isActive() || state.runPending;
    ui.start.disabled = !keyReady || !state.bootstrap?.dataset?.sha256 || totalBootstrapCases() !== 720 || busy;
    ui.startPilot.disabled = !keyReady || !pilotReady() || busy;
    ui.start.querySelector('.button-label').textContent = `测全部 ${formatInteger(totalBootstrapCases())} 题`;
    ui.stop.disabled = !isActive() || currentStatus() === 'stopping';
    ui.export.disabled = !state.runId;
    ui.concurrency.disabled = busy;
  }

  function totalBootstrapCases() {
    return integer(state.bootstrap?.dataset?.case_count, 0);
  }

  function updateElapsedDisplay() {
    const elapsed = state.run ? currentElapsedMs() : null;
    ui.elapsedValue.textContent = elapsed === null ? '—' : formatDuration(elapsed, isActive());
    if (state.run) {
      ui.elapsedFoot.textContent = isActive() ? '实时计时' : `本轮结束 · ${text(state.run.finished_at, '时间未提供')}`;
    }
  }

  function currentElapsedMs() {
    const reported = number(state.run?.elapsed_ms, null);
    if (isActive()) {
      const base = state.elapsedBase || reported || 0;
      return base + Math.max(0, performance.now() - state.elapsedAnchor);
    }
    return reported;
  }

  function setRunSnapshot(snapshot) {
    if (!snapshot || typeof snapshot !== 'object') return;
    state.run = snapshot;
    state.runId = text(snapshot.run_id, state.runId || '');
    if (state.runId) {
      try { localStorage.setItem(LAST_RUN_KEY, state.runId); } catch { /* Local persistence is an optional refresh aid. */ }
    }
    state.elapsedBase = number(snapshot.elapsed_ms, 0) || 0;
    state.elapsedAnchor = performance.now();
    renderAll();
    if (isTerminal()) {
      stopLiveUpdates();
      saveRunHistory(snapshot);
      refreshRecentRuns();
    }
  }

  function normalizeRunCollection(payload) {
    if (Array.isArray(payload)) return payload;
    if (Array.isArray(payload?.runs)) return payload.runs;
    if (Array.isArray(payload?.recent_runs)) return payload.recent_runs;
    return [];
  }

  function localHistory() {
    try {
      const stored = JSON.parse(localStorage.getItem(HISTORY_KEY) || '[]');
      return Array.isArray(stored) ? stored : [];
    } catch { return []; }
  }

  function runHistoryRecord(run) {
    const dataset = state.bootstrap?.dataset || {};
    return {
      run_id: run.run_id,
      status: run.status,
      mode: run.mode,
      concurrency: run.concurrency,
      elapsed_ms: run.elapsed_ms,
      metrics: run.metrics || {},
      scope: run.scope || 'full',
      selection_sha256: run.selection_sha256 || '',
      started_at: run.started_at,
      finished_at: run.finished_at,
      dataset_sha256: run.dataset_sha256 || run.dataset_hash || run.dataset?.sha256 || dataset.sha256 || '',
      actual_models: Array.isArray(run.actual_models) ? run.actual_models : []
    };
  }

  function isRealRun(run) {
    const mode = String(run?.mode || '').toLowerCase();
    return !/(fake|replay|demo|offline|dry)/.test(mode);
  }

  function saveRunHistory(run) {
    if (!run?.run_id || !isComplete() || !isRealRun(run)) return;
    const record = runHistoryRecord(run);
    const existing = localHistory().filter((item) => item.run_id !== record.run_id);
    try { localStorage.setItem(HISTORY_KEY, JSON.stringify([record, ...existing].slice(0, 12))); } catch { /* Server history remains authoritative. */ }
  }

  async function refreshRecentRuns() {
    const fromBootstrap = normalizeRunCollection(state.bootstrap?.recent_runs);
    const fromStorage = localHistory();
    state.recentRuns = [...fromBootstrap, ...fromStorage];
    try {
      const response = await fetchJson('/api/runs');
      state.recentRuns = [...normalizeRunCollection(response), ...fromBootstrap, ...fromStorage];
    } catch {
      // The frozen minimum contract remains usable when the optional run-list route is unavailable.
    }
    renderComparison();
  }

  function historyEntry(run) {
    if (!run || !isRealRun(run) || !COMPLETE_STATUSES.has(statusToken(run.status))) return null;
    const scope = text(run.scope, 'full');
    if (scope !== 'full') return null;
    const metrics = run.metrics || {};
    const actualModels = Array.isArray(run.actual_models) ? run.actual_models : [];
    const model = actualModels.length === 1
      ? text(typeof actualModels[0] === 'string' ? actualModels[0] : actualModels[0]?.version || actualModels[0]?.model || actualModels[0]?.id, '')
      : '';
    return {
      runId: text(run.run_id, ''),
      scope,
      concurrency: integer(run.concurrency, 0),
      elapsed: number(run.elapsed_ms, null),
      correct: integer(metrics.correct, 0),
      done: number(metrics.done, null),
      total: integer(metrics.total, 0),
      failed: number(metrics.failed, null),
      skipped: number(metrics.skipped, null),
      cost: number(metrics.cost_usd, null),
      costReported: number(metrics.cost_reported, null),
      sha: text(run.dataset_sha256 || run.dataset_hash || run.dataset?.sha256, ''),
      model,
      startedAt: text(run.started_at, ''),
      finishedAt: text(run.finished_at, '')
    };
  }

  function renderComparison() {
    const records = [...state.recentRuns];
    if (state.run && isComplete() && isRealRun(state.run)) records.unshift(runHistoryRecord(state.run));
    const entries = [...new Map(records.map(historyEntry).filter(Boolean).map((entry) => [entry.runId, entry])).values()]
      .sort((a, b) => {
        const aTime = Date.parse(a.startedAt);
        const bTime = Date.parse(b.startedAt);
        return (Number.isFinite(bTime) ? bTime : 0) - (Number.isFinite(aTime) ? aTime : 0);
      });
    const datasetHash = text(state.bootstrap?.dataset?.sha256, '');
    const sameData = entries.filter((entry) => entry.sha && datasetHash && entry.sha === datasetHash);
    const serial = sameData.find((entry) => entry.concurrency === 1 && entry.elapsed !== null);
    const concurrent = sameData.find((entry) => entry.concurrency >= 8 && entry.elapsed !== null);
    if (!serial || !concurrent) {
      ui.comparisonEmpty.hidden = false;
      ui.comparisonContent.hidden = true;
      ui.comparisonEmpty.textContent = entries.length
        ? '需要同一题集下各跑完一轮“同时 1 个请求”和“同时 8 个或更多请求”，才能对比速度。'
        : '跑完“同时发送 1 个请求”和任一更高并发档位后，这里会对比本机保存的运行记录。';
      return;
    }

    ui.comparisonEmpty.hidden = true;
    ui.comparisonContent.hidden = false;
    ui.comparisonContent.replaceChildren();
    const serialCard = makeCompareCard('同时 1 个请求', serial);
    const concurrentCard = makeCompareCard(`同时 ${formatInteger(concurrent.concurrency)} 个请求`, concurrent);
    ui.comparisonContent.append(serialCard, concurrentCard);
    const delta = document.createElement('div');
    delta.className = 'comparison-delta';
    const description = document.createElement('span');
    const expected = integer(state.bootstrap?.dataset?.case_count, 720);
    const sameActualModel = Boolean(serial.model && concurrent.model && serial.model === concurrent.model);
    const bothCleanAndComplete = [serial, concurrent].every((entry) =>
      entry.total === expected && entry.done === expected && entry.failed === 0 && entry.skipped === 0
    );
    if (!sameActualModel) {
      description.textContent = '题目相同，但实际模型版本不同或无法确认；不显示速度倍数。';
      delta.classList.add('comparison-delta-note');
      delta.append(description);
    } else if (!bothCleanAndComplete) {
      description.textContent = `两轮都需要完整处理 ${formatInteger(expected)} 道题，并且没有失败或跳过，才显示速度倍数。`;
      delta.classList.add('comparison-delta-note');
      delta.append(description);
    } else {
      description.textContent = '相同题目 / 相同模型版本 / 无失败或跳过';
      const speedup = document.createElement('strong');
      speedup.textContent = concurrent.elapsed > 0 ? `${(serial.elapsed / concurrent.elapsed).toFixed(2)}×` : '—';
      const label = document.createElement('span');
      label.textContent = '并发轮次耗时倍数';
      delta.append(description, label, speedup);
    }
    ui.comparisonContent.append(delta);
  }

  function makeCompareCard(title, entry) {
    const card = document.createElement('div');
    card.className = 'comparison-run';
    const name = document.createElement('span');
    name.textContent = title;
    const elapsed = document.createElement('strong');
    elapsed.textContent = formatDuration(entry.elapsed);
    const meta = document.createElement('small');
    const cost = entry.cost === null ? '费用未报告' : `费用 ${formatUsd(entry.cost)}`;
    const failed = entry.failed === null ? '失败数未知' : `失败 ${formatInteger(entry.failed)}`;
    const skipped = entry.skipped === null ? '未完成数未知' : `未完成 ${formatInteger(entry.skipped)}`;
    meta.textContent = `${entry.correct}/${entry.total || '—'} 题判断正确 · ${failed} · ${skipped} · ${cost}`;
    card.append(name, elapsed, meta);
    return card;
  }

  function renderMetrics() {
    if (!state.run) {
      ui.progressValue.textContent = '—';
      ui.progressFoot.textContent = '尚未开始';
      ui.progressFill.style.width = '0%';
      ui.progressBar.setAttribute('aria-valuenow', '0');
      ui.accuracyValue.textContent = '—';
      ui.accuracyFoot.textContent = '开始评测后显示';
      ui.accuracyLabel.textContent = '判断正确率';
      ui.costValue.textContent = '—';
      ui.costFoot.textContent = '仅统计服务商实际报告的费用';
      ui.throughputValue.textContent = '—';
      updateElapsedDisplay();
      return;
    }

    const metrics = state.run.metrics || {};
    const total = totalCases();
    const done = finishedCases();
    const correct = integer(metrics.correct, (state.run.rows || []).filter((row) => row.correct === true).length);
    const valid = integer(metrics.valid, (state.run.rows || []).filter((row) => !rowFailed(row) && ['合理', '不合理'].includes(choiceLabel(row.decision, row))).length);
    const progress = total > 0 ? Math.min(100, done / total * 100) : 0;

    ui.progressValue.textContent = `${formatInteger(done)} / ${formatInteger(total)}`;
    ui.progressFoot.textContent = `${formatPercent(done, total)} 已处理 · 失败和未完成仍计入总数`;
    ui.progressFill.style.width = `${progress}%`;
    ui.progressBar.setAttribute('aria-valuenow', String(Math.round(progress)));

    if (isActive()) {
      ui.accuracyLabel.textContent = '已处理题目正确率';
      ui.accuracyValue.textContent = done > 0 ? formatPercent(correct, done) : '—';
      ui.accuracyFoot.textContent = done > 0 ? `${formatInteger(correct)} / ${formatInteger(done)} 道已处理题` : '等待第一批题目完成';
    } else {
      ui.accuracyLabel.textContent = '全部题目正确率';
      ui.accuracyValue.textContent = formatPercent(correct, total);
      ui.accuracyFoot.textContent = `${formatInteger(correct)} / ${formatInteger(total)} 道；失败和未完成算未答对`;
    }

    const cost = number(metrics.cost_usd, null);
    ui.costValue.textContent = cost === null ? '—' : formatUsd(cost);
    const reported = number(metrics.cost_reported, null);
    const missing = number(metrics.cost_missing, null);
    if (reported !== null && missing !== null) {
      ui.costFoot.textContent = `费用字段覆盖 ${formatInteger(reported)} 项 · ${formatInteger(missing)} 项未提供`;
    } else if (reported !== null) {
      ui.costFoot.textContent = `${formatInteger(reported)} 项收到费用字段${missing === null ? ' · 缺失项数未提供' : ''}`;
    } else if (cost === null) {
      ui.costFoot.textContent = '接口还没有报告费用；未知费用不按 $0 处理';
    } else {
      ui.costFoot.textContent = '汇总来自本轮已报告费用';
    }

    const elapsed = currentElapsedMs();
    const throughput = number(metrics.throughput, elapsed > 0 ? valid / (elapsed / 1000) : null);
    ui.throughputValue.textContent = throughput === null ? '—' : `${throughput.toFixed(2)}`;
    updateElapsedDisplay();
  }

  function statusDescription() {
    const labels = {
      idle: ['等待开始', '当前没有运行中的评测'],
      queued: ['等待开始', '本机服务已收到本轮任务'],
      starting: ['正在启动', '准备发送第一批请求'],
      running: ['正在评测', '下方方块会逐题显示最新状态'],
      in_progress: ['正在评测', '下方方块会逐题显示最新状态'],
      stopping: ['正在停止', '不再发送新请求；已发出的请求仍会完成'],
      completed: ['评测完成', '全部题目都已处理'],
      complete: ['评测完成', '全部题目都已处理'],
      finished: ['评测完成', '本轮运行已结束'],
      succeeded: ['评测完成', '本轮运行已结束'],
      success: ['评测完成', '本轮运行已结束'],
      stopped: ['已停止', '未完成的题仍算在总题数里'],
      cancelled: ['已取消', '未完成的题仍算在总题数里'],
      canceled: ['已取消', '未完成的题仍算在总题数里'],
      failed: ['运行结束', '请查看失败项目与服务端错误摘要']
    };
    return labels[currentStatus()] || ['等待开始', state.run ? `状态：${text(state.run.status)}` : '当前没有运行中的评测'];
  }

  function renderRunState() {
    if (!state.run) {
      ui.runState.textContent = '等待开始';
      ui.runStateDetail.textContent = '当前没有运行中的评测';
      ui.runConcurrency.textContent = '同时请求 —';
      ui.runId.textContent = 'RUN —';
      ui.runStrip.className = 'run-strip';
      renderSetupButtons();
      return;
    }
    const [label, detail] = statusDescription();
    ui.runState.textContent = label;
    const mode = String(state.run.mode || '').toLowerCase();
    const modeLabel = /(fake|offline|dry|demo)/.test(mode) ? '离线测试' : (/replay/.test(mode) ? '查看历史记录' : '真实请求');
    const scopeLabel = state.run.scope === 'pilot32' ? '32 题小批量试跑' : '全量题集';
    ui.runStateDetail.textContent = `${modeLabel} · ${scopeLabel} · ${detail}`;
    const selectedConcurrency = integer(state.run.concurrency, 0);
    const reportedEffective = number(state.run.effective_concurrency, null);
    const effectiveConcurrency = state.run.scope === 'pilot32'
      ? Math.min(integer(reportedEffective, selectedConcurrency || 32), 32)
      : integer(reportedEffective, selectedConcurrency);
    ui.runConcurrency.textContent = state.run.scope === 'pilot32'
      ? `试跑并发 ${effectiveConcurrency || '—'}${selectedConcurrency > effectiveConcurrency ? `（所选 ${selectedConcurrency}，封顶 32）` : ''}`
      : `同时请求 ${effectiveConcurrency || '—'}`;
    ui.runId.textContent = `RUN ${text(state.run.run_id, '—').slice(0, 12)}`;
    ui.runStrip.className = `run-strip${isActive() ? ' is-running' : ''}${currentStatus() === 'stopping' ? ' is-stopping' : ''}${isComplete() ? ' is-complete' : ''}${currentStatus() === 'failed' ? ' is-error' : ''}`;
    renderSetupButtons();
  }

  function caseTileState(row) {
    const status = rowStatus(row);
    if (rowFailed(row)) return 'failed';
    if (status === 'running') return 'running';
    if (['pending', 'queued'].includes(status)) return 'waiting';
    if (['skipped', 'stopped', 'cancelled', 'canceled', 'invalid'].includes(status)) return 'incomplete';
    if (choiceLabel(row?.decision, row) === '无法判断' && rowIsTerminal(row)) return 'undecidable';
    if (row?.correct === true) return 'correct';
    if (row?.correct === false) return 'incorrect';
    if (rowIsTerminal(row)) return 'undecidable';
    return 'incomplete';
  }

  const CASE_TILE_COPY = {
    waiting: { label: '等待发送', mark: '待' },
    running: { label: '正在处理', mark: '进' },
    correct: { label: '判断正确', mark: '对' },
    incorrect: { label: '判断错误', mark: '错' },
    undecidable: { label: 'JEV 无法判断', mark: '?' },
    failed: { label: '请求失败', mark: '!' },
    incomplete: { label: '未完成', mark: '未' }
  };

  function renderCaseOverview() {
    const rows = Array.isArray(state.run?.rows) ? state.run.rows : [];
    const total = totalCases();
    ui.caseGridTotal.textContent = rows.length && rows.length !== total
      ? `${formatInteger(rows.length)} / ${formatInteger(total)} 道`
      : `${formatInteger(total)} 道`;
    ui.caseGridEmpty.hidden = rows.length > 0;
    ui.caseGrid.hidden = rows.length === 0;
    if (!rows.length) {
      ui.caseGrid.replaceChildren();
      state.caseGridTiles.clear();
      delete ui.caseGrid.dataset.runId;
      Object.entries(ui.caseGridCounts).forEach(([, counter]) => { counter.textContent = '0'; });
      return;
    }

    const runId = text(state.run.run_id, '');
    if (ui.caseGrid.dataset.runId !== runId) {
      ui.caseGrid.replaceChildren();
      state.caseGridTiles.clear();
      ui.caseGrid.dataset.runId = runId;
    }

    const counts = Object.fromEntries(Object.keys(ui.caseGridCounts).map((key) => [key, 0]));
    rows.forEach((row, index) => {
      const caseId = text(row.case_id, `question-${index + 1}`);
      let button = state.caseGridTiles.get(caseId);
      if (!button) {
        const item = document.createElement('li');
        button = document.createElement('button');
        button.type = 'button';
        button.className = 'case-tile';
        button.dataset.caseId = caseId;
        item.append(button);
        ui.caseGrid.append(item);
        state.caseGridTiles.set(caseId, button);
      }
      const tileState = caseTileState(row);
      const copy = CASE_TILE_COPY[tileState];
      const dish = text(row.dish_zh || row.dish_en, '菜品未提供');
      const ingredient = text(row.ingredient, '原料未提供');
      if (button.dataset.tileState !== tileState) {
        button.dataset.tileState = tileState;
        button.className = `case-tile case-tile-${tileState}`;
        button.textContent = copy.mark;
        button.title = `${caseId} · ${dish} · ${ingredient} · ${copy.label}`;
        button.setAttribute('aria-label', `${caseId}，${dish}，${ingredient}：${copy.label}。点击查看题目详情。`);
      }
      counts[tileState] += 1;
    });

    Object.entries(ui.caseGridCounts).forEach(([key, counter]) => {
      counter.textContent = formatInteger(counts[key]);
    });
    ui.caseGrid.setAttribute('aria-label', `本轮全部 ${formatInteger(rows.length)} 道题目进度；点击任一题目方块打开详情`);
  }

  function createCell(className = '') {
    const cell = document.createElement('td');
    if (className) cell.className = className;
    return cell;
  }

  function createSpan(className, value) {
    const span = document.createElement('span');
    span.className = className;
    span.textContent = text(value);
    return span;
  }

  function appendNameCell(cell, primary, secondary) {
    cell.append(createSpan('cell-main', primary));
    if (secondary) cell.append(createSpan('cell-sub', secondary));
  }

  function renderEmptyRow(message, detail) {
    const row = document.createElement('tr');
    row.className = 'empty-row';
    const cell = document.createElement('td');
    cell.colSpan = 8;
    const stateBlock = document.createElement('div');
    stateBlock.className = 'empty-state';
    const icon = document.createElement('span');
    icon.className = 'empty-icon';
    icon.setAttribute('aria-hidden', 'true');
    icon.textContent = '✳';
    const title = document.createElement('strong');
    title.textContent = message;
    const description = document.createElement('p');
    description.textContent = detail;
    stateBlock.append(icon, title, description);
    cell.append(stateBlock);
    row.append(cell);
    return row;
  }

  function searchable(row) {
    return [row.dish_zh, row.dish_en, row.ingredient, row.item_en, row.item_zh, row.item_id, row.case_id]
      .filter(Boolean).join(' ').toLocaleLowerCase('zh-CN');
  }

  function rowMatchesFilter(row, filter) {
    if (filter === 'correct') return row.correct === true;
    if (filter === 'incorrect') return row.correct === false;
    if (filter === 'undecidable') return choiceLabel(row.decision, row) === '无法判断';
    if (filter === 'failed') return rowFailed(row);
    return true;
  }

  function getFilteredRows() {
    const rows = state.run?.rows || [];
    const query = ui.search.value.trim().toLocaleLowerCase('zh-CN');
    return rows.filter((row) => rowMatchesFilter(row, state.filter) && (!query || searchable(row).includes(query)));
  }

  function renderTable() {
    const rows = getFilteredRows();
    const allRows = state.run?.rows || [];
    const pageCount = Math.max(1, Math.ceil(rows.length / PAGE_SIZE));
    state.page = Math.min(Math.max(1, state.page), pageCount);
    const offset = (state.page - 1) * PAGE_SIZE;
    const visible = rows.slice(offset, offset + PAGE_SIZE);
    ui.resultsBody.replaceChildren();
    if (!state.run || allRows.length === 0) {
      ui.resultsBody.append(renderEmptyRow('评测结果将在这里逐项出现', '启动后可以看到真实响应与参考答案的对照。'));
    } else if (!visible.length) {
      ui.resultsBody.append(renderEmptyRow('没有符合条件的记录', '清除筛选或尝试搜索其他菜名、原料。'));
    } else {
      visible.forEach((row) => ui.resultsBody.append(renderResultRow(row)));
    }

    ui.visibleCount.textContent = `${formatInteger(rows.length)} 道`;
    ui.pageSummary.textContent = rows.length ? `第 ${formatInteger(offset + 1)}–${formatInteger(Math.min(offset + PAGE_SIZE, rows.length))} 道，共 ${formatInteger(rows.length)} 道` : '第 0–0 道，共 0 道';
    ui.pageIndicator.textContent = `第 ${state.page} / ${pageCount} 页`;
    ui.previousPage.disabled = state.page <= 1;
    ui.nextPage.disabled = state.page >= pageCount;
    ui.filterCounts.all.textContent = formatInteger(allRows.length);
    ui.filterCounts.correct.textContent = formatInteger(allRows.filter((row) => row.correct === true).length);
    ui.filterCounts.incorrect.textContent = formatInteger(allRows.filter((row) => row.correct === false).length);
    ui.filterCounts.undecidable.textContent = formatInteger(allRows.filter((row) => choiceLabel(row.decision, row) === '无法判断').length);
    ui.filterCounts.failed.textContent = formatInteger(allRows.filter(rowFailed).length);
    ui.filterButtons.forEach((button) => {
      const active = button.dataset.filter === state.filter;
      button.classList.toggle('is-active', active);
      button.setAttribute('aria-pressed', String(active));
    });
  }

  function renderResultRow(row) {
    const tr = document.createElement('tr');
    tr.dataset.caseId = text(row.case_id, '');

    const dish = createCell();
    appendNameCell(dish, row.dish_zh || row.dish_en, row.dish_en ? `${row.dish_en} · ${text(row.case_id)}` : row.case_id);
    tr.append(dish);

    const ingredient = createCell();
    appendNameCell(ingredient, row.ingredient, '现实原料');
    tr.append(ingredient);

    const item = createCell();
    item.append(createSpan('item-cell-en', row.item_en || row.item_id), createSpan('item-cell-zh', row.item_zh || '游戏原料候选'));
    tr.append(item);

    const gold = createCell();
    const goldPill = document.createElement('span');
    const goldLabel = choiceLabel(row.gold_choice, { status: 'completed' });
    goldPill.className = `choice-pill ${choiceClass(row.gold_choice, { status: 'completed' })}`;
    goldPill.textContent = goldLabel;
    gold.append(goldPill);
    tr.append(gold);

    const decision = createCell();
    const decisionPill = document.createElement('span');
    decisionPill.className = `choice-pill ${choiceClass(row.decision, row)}`;
    decisionPill.textContent = choiceLabel(row.decision, row);
    decision.append(decisionPill);
    tr.append(decision);

    const verdict = createCell();
    const verdictInfo = rowVerdict(row);
    const verdictPill = document.createElement('span');
    verdictPill.className = `verdict-pill ${verdictInfo.className}`;
    verdictPill.textContent = verdictInfo.label;
    verdict.append(verdictPill);
    tr.append(verdict);

    const latency = createCell('latency-cell');
    const latencyMs = number(row.latency_ms, null);
    latency.textContent = latencyMs === null ? '—' : `${(latencyMs / 1000).toFixed(2)} s`;
    tr.append(latency);

    const detailCell = createCell();
    const detailButton = document.createElement('button');
    detailButton.type = 'button';
    detailButton.className = 'detail-button';
    detailButton.dataset.caseId = text(row.case_id, '');
    detailButton.textContent = '详情';
    detailButton.setAttribute('aria-label', `查看 ${text(row.dish_zh || row.dish_en)} 的 ${text(row.ingredient)} 评测详情`);
    detailCell.append(detailButton);
    tr.append(detailCell);
    return tr;
  }

  function detailBlock(label, value, wide = false, code = false) {
    const block = document.createElement('div');
    block.className = `detail-block${wide ? ' detail-block-wide' : ''}`;
    const heading = document.createElement('span');
    heading.textContent = label;
    const content = document.createElement(code ? 'code' : 'p');
    content.textContent = typeof value === 'string' ? text(value) : JSON.stringify(value ?? null, null, 2);
    block.append(heading, content);
    return block;
  }

  function openCaseDetail(caseId) {
    const row = (state.run?.rows || []).find((candidate) => text(candidate.case_id, '') === caseId);
    if (!row) return;
    ui.detailTitle.textContent = `${text(row.dish_zh || row.dish_en)} · ${text(row.case_id)}`;
    ui.detailContent.replaceChildren(
      detailBlock('现实原料', row.ingredient),
      detailBlock('参考答案', choiceLabel(row.gold_choice, { status: 'completed' })),
      detailBlock('参考答案依据', row.gold_reason, true),
      detailBlock('游戏原料候选 · 中文', row.item_zh),
      detailBlock('游戏原料候选 · English', row.item_en),
      detailBlock('游戏目录 ID', row.item_id),
      detailBlock('JEV 返回的选择', choiceLabel(row.decision, row)),
      detailBlock('JEV 返回的置信度', row.confidence),
      detailBlock('单项响应时间', number(row.latency_ms, null) === null ? '未记录' : `${row.latency_ms} ms`),
      detailBlock('JEV 返回值', row.decision, true, true)
    );
    ui.detailDialog.showModal();
  }

  function renderSummary() {
    if (!state.run || !isTerminal()) {
      ui.summary.hidden = true;
      return;
    }
    ui.summary.hidden = false;
    const metrics = state.run.metrics || {};
    const total = totalCases();
    const correct = integer(metrics.correct, (state.run.rows || []).filter((row) => row.correct === true).length);
    const valid = integer(metrics.valid, (state.run.rows || []).filter((row) => !rowFailed(row) && ['合理', '不合理'].includes(choiceLabel(row.decision, row))).length);
    const pilot = state.run.scope === 'pilot32';
    const positiveTotal = integer(metrics.positive_total, integer(pilot ? state.bootstrap?.pilot?.positive_count : state.bootstrap?.dataset?.positive_count, 0));
    const negativeTotal = integer(metrics.negative_total, integer(pilot ? state.bootstrap?.pilot?.negative_count : state.bootstrap?.dataset?.negative_count, 0));
    const positiveCorrect = integer(metrics.positive_correct, 0);
    const negativeCorrect = integer(metrics.negative_correct, 0);
    const positiveRate = positiveTotal ? positiveCorrect / positiveTotal : null;
    const negativeRate = negativeTotal ? negativeCorrect / negativeTotal : null;
    const balanced = positiveRate === null || negativeRate === null ? null : (positiveRate + negativeRate) / 2;
    const complete = isComplete();
    const done = finishedCases();
    const elapsed = number(state.run.elapsed_ms, null);
    const cost = number(metrics.cost_usd, null);
    const undecidable = integer(metrics.undecidable, (state.run.rows || []).filter((row) => choiceLabel(row.decision, row) === '无法判断').length);
    const failed = integer(metrics.failed, (state.run.rows || []).filter(rowFailed).length);

    ui.summaryScope.textContent = pilot ? '小批量试跑 · 32 题' : `全量评测 · ${formatInteger(total)} 题`;
    ui.summaryStatus.textContent = complete ? '已结束' : '部分完成';
    ui.summaryStatus.classList.toggle('is-partial', !complete);
    ui.summaryFinalLabel.textContent = complete
      ? (pilot ? '32 道试跑题已处理' : '全部题目已处理')
      : '未完成的题也计入总数';
    ui.summaryAccuracy.textContent = formatPercent(correct, total);
    ui.summaryAccuracyDetail.textContent = `${formatInteger(correct)} / ${formatInteger(total)} 道题正确；失败和未完成算错`;
    ui.summaryCoverage.textContent = formatPercent(valid, total);
    ui.summaryCoverageDetail.textContent = `${formatInteger(valid)} 道题有明确选择 / ${formatInteger(total)} 道`;
    ui.summaryPositive.textContent = positiveRate === null ? '—' : `${(positiveRate * 100).toFixed(1)}%`;
    ui.summaryPositiveDetail.textContent = `${formatInteger(positiveCorrect)} / ${formatInteger(positiveTotal)} 道应判“合理”的题答对`;
    ui.summaryNegative.textContent = negativeRate === null ? '—' : `${(negativeRate * 100).toFixed(1)}%`;
    ui.summaryNegativeDetail.textContent = `${formatInteger(negativeCorrect)} / ${formatInteger(negativeTotal)} 道应判“不合理”的题答对`;
    ui.summaryBalanced.textContent = balanced === null ? '—' : `${(balanced * 100).toFixed(1)}%`;

    const timeText = elapsed === null ? '耗时未提供' : `耗时 ${formatDuration(elapsed)}`;
    const costText = cost === null ? '费用未完整报告' : `已报告费用 ${formatUsd(cost)}`;
    ui.summarySentence.textContent = `${pilot ? '32 题小批量试跑' : '全量评测'}：${complete ? '本轮已完成' : `本轮${text(state.run.status, '已停止')}`} ${formatInteger(done)} / ${formatInteger(total)} 道题，${timeText}，${costText}；${formatInteger(correct)} 道题判断正确。`;
    renderConfusionMatrix(total);
    renderComparison();
  }

  function renderConfusionMatrix(total) {
    const cells = {
      reasonable: { reasonable: 0, unreasonable: 0, undecidable: 0, other: 0 },
      unreasonable: { reasonable: 0, unreasonable: 0, undecidable: 0, other: 0 }
    };
    const missingReference = { reasonable: 0, unreasonable: 0, undecidable: 0, other: 0 };
    let observedRows = 0;
    for (const row of state.run?.rows || []) {
      observedRows += 1;
      const gold = choiceToken(row.gold_choice);
      const ref = ['reasonable', 'accept', 'accepted', 'yes', 'true', 'match'].includes(gold) ? 'reasonable'
        : (['unreasonable', 'reject', 'rejected', 'no', 'false', 'no_match'].includes(gold) ? 'unreasonable' : null);
      const choice = choiceToken(row.decision);
      const outcome = rowFailed(row) || !rowIsTerminal(row) ? 'other'
        : (['reasonable', 'accept', 'accepted', 'yes', 'true', 'match'].includes(choice) ? 'reasonable'
          : (['unreasonable', 'reject', 'rejected', 'no', 'false', 'no_match'].includes(choice) ? 'unreasonable'
            : (['undecidable', 'unknown', 'uncertain', 'cannot_determine', 'abstain'].includes(choice) ? 'undecidable' : 'other')));
      if (ref) cells[ref][outcome] += 1;
      else missingReference[outcome] += 1;
    }
    // Missing rows or labels remain visible without being reassigned to either reference class.
    missingReference.other += Math.max(0, total - observedRows);

    ui.matrixBody.replaceChildren();
    const rows = [['reasonable', '参考答案：合理'], ['unreasonable', '参考答案：不合理']];
    if (Object.values(missingReference).some((count) => count > 0)) rows.push(['missing', '参考答案 / 记录缺失']);
    for (const [key, label] of rows) {
      const row = document.createElement('tr');
      const head = document.createElement('th');
      head.scope = 'row';
      head.textContent = label;
      row.append(head);
      for (const field of ['reasonable', 'unreasonable', 'undecidable', 'other']) {
        const cell = document.createElement('td');
        cell.textContent = formatInteger(key === 'missing' ? missingReference[field] : cells[key][field]);
        row.append(cell);
      }
      ui.matrixBody.append(row);
    }
  }

  function renderAll() {
    renderBootstrap();
    renderMetrics();
    renderRunState();
    renderCaseOverview();
    renderTable();
    renderSummary();
    renderComparison();
  }

  function parseSseData(raw) {
    try { return JSON.parse(raw); } catch { return null; }
  }

  function handleSseMessage(event) {
    const payload = parseSseData(event.data);
    if (!payload) return;
    const snapshot = payload.snapshot || payload.data?.snapshot || payload.data || payload;
    if (snapshot && typeof snapshot === 'object' && (snapshot.run_id || snapshot.status || snapshot.rows)) {
      setRunSnapshot(snapshot);
    }
  }

  function stopLiveUpdates() {
    if (state.eventSource) {
      state.eventSource.close();
      state.eventSource = null;
    }
    if (state.pollTimer) {
      window.clearInterval(state.pollTimer);
      state.pollTimer = null;
    }
  }

  function startPolling(runId) {
    if (state.pollTimer) window.clearInterval(state.pollTimer);
    state.pollTimer = window.setInterval(() => { refreshRun(runId); }, 1400);
  }

  function connectEvents(runId) {
    stopLiveUpdates();
    if (typeof EventSource === 'function') {
      try {
        const source = new EventSource(`/api/runs/${encodeURIComponent(runId)}/events`);
        state.eventSource = source;
        source.onmessage = handleSseMessage;
        ['snapshot', 'progress', 'update'].forEach((name) => source.addEventListener(name, handleSseMessage));
        source.onerror = () => {
          if (state.eventSource === source) {
            source.close();
            state.eventSource = null;
            if (isActive()) startPolling(runId);
          }
        };
      } catch {
        startPolling(runId);
      }
    } else {
      startPolling(runId);
    }
  }

  async function refreshRun(runId) {
    try {
      const snapshot = await fetchJson(`/api/runs/${encodeURIComponent(runId)}`);
      setRunSnapshot(snapshot);
      if (isActive() && !state.eventSource && !state.pollTimer) startPolling(runId);
      else if (!isActive()) stopLiveUpdates();
    } catch (error) {
      if (!state.run) showToast(`读取运行记录失败：${error.message}`, true);
    }
  }

  async function attachRun(runId) {
    if (!runId) return;
    state.runId = runId;
    await refreshRun(runId);
    if (isActive()) connectEvents(runId);
  }

  async function loadRecentRunsFromBootstrap() {
    state.recentRuns = normalizeRunCollection(state.bootstrap?.recent_runs);
    await refreshRecentRuns();
  }

  async function loadApp() {
    try {
      state.bootstrap = await fetchJson('/api/bootstrap');
      clearLaunchError();
      renderAll();
      await loadRecentRunsFromBootstrap();
      const activeRunId = text(state.bootstrap.active_run_id, '');
      let savedRunId = '';
      try { savedRunId = localStorage.getItem(LAST_RUN_KEY) || ''; } catch { /* Browser storage can be disabled. */ }
      if (activeRunId) await attachRun(activeRunId);
      else if (savedRunId) await attachRun(savedRunId);
    } catch (error) {
      ui.datasetStatus.classList.add('is-error');
      ui.datasetStatus.lastChild.textContent = '服务未连接';
      showLaunchError(`无法连接本地评测服务：${error.message}`);
      ui.start.disabled = true;
      ui.startPilot.disabled = true;
    }
  }

  function openConfirm(scope) {
    if (isActive() || state.runPending) {
      showToast('当前已有一轮评测，结束后再开始下一轮。');
      return;
    }
    if (!state.bootstrap?.api_key_available) {
      showLaunchError('本机服务尚未读取到评测密钥，请按 README 配置后重启服务。');
      return;
    }
    if (scope === 'pilot32' && !pilotReady()) {
      showLaunchError('32 题试跑题集尚未准备好，请重启本地服务并检查题集清单。');
      return;
    }
    if (scope !== 'pilot32' && totalBootstrapCases() !== 720) {
      showLaunchError('全量题集尚未准备好，请按 README 中的步骤完成准备。');
      return;
    }
    state.pendingScope = scope === 'pilot32' ? 'pilot32' : 'full';
    clearLaunchError();
    ui.confirmCount.textContent = formatInteger(state.pendingScope === 'pilot32' ? state.bootstrap.pilot.case_count : totalBootstrapCases());
    ui.confirmModel.textContent = `模型 ${getModelName(state.bootstrap.model)}`;
    ui.confirmTitle.textContent = state.pendingScope === 'pilot32' ? '即将开始 32 题小批量试跑' : '即将开始全部 720 题评测';
    ui.confirmScope.textContent = state.pendingScope === 'pilot32' ? '范围：固定 32 题（16 合理 / 16 不合理）' : '范围：全部 720 题';
    updateConfirmCopy();
    ui.confirmDialog.showModal();
  }

  function updateConfirmCopy() {
    const isPilot = state.pendingScope === 'pilot32';
    const concurrency = Number(ui.concurrency.value);
    const effectiveConcurrency = isPilot ? Math.min(concurrency, 32) : concurrency;
    ui.confirmConcurrency.textContent = isPilot
      ? `最多同时 ${formatInteger(effectiveConcurrency)} 个请求${concurrency > effectiveConcurrency ? `（选择 ${formatInteger(concurrency)}，试跑封顶 32）` : ''}`
      : `同时请求 ${formatInteger(effectiveConcurrency)}`;
    if (isPilot) {
      ui.confirmWarning.textContent = '这是固定的 32 题预跑，包含 16 道应判“合理”和 16 道应判“不合理”。服务商可能按实际用量收费；失败请求不会自动重试。';
    } else if (concurrency === 720) {
      ui.confirmWarning.textContent = '720 档会一次把全部题目同时发出。服务商可能限流或超时，失败不会自动重试；这个档位不保证最快。';
    } else if (concurrency >= 64) {
      ui.confirmWarning.textContent = '高并发时服务商可能限流或超时；失败不会自动重试。可跑完后与同题集的 1 档记录比较速度。';
    } else {
      ui.confirmWarning.textContent = '服务商可能限流或请求超时；失败不会自动重试。要比较速度，请用同一题集完成 1 档和更高并发档位。';
    }
  }

  async function startRun(scope) {
    if (isActive() || state.runPending) {
      showToast('已有一轮评测正在运行，页面已连接到当前任务。');
      return;
    }
    const selectedScope = scope === 'pilot32' ? 'pilot32' : 'full';
    state.runPending = true;
    renderSetupButtons();
    ui.launchHint.classList.remove('is-error');
    ui.launchHint.textContent = '正在创建评测任务…';
    try {
      const response = await fetchJson('/api/runs', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ concurrency: Number(ui.concurrency.value), confirm: true, scope: selectedScope })
      });
      if (!response?.run_id) throw new Error('服务端没有返回 run_id');
      state.runId = response.run_id;
      await attachRun(response.run_id);
      if (isActive()) connectEvents(response.run_id);
      else showToast('服务端已返回评测记录。');
    } catch (error) {
      showLaunchError(`无法开始评测：${error.message}`);
      showToast(`开始失败：${error.message}`, true);
    } finally {
      state.runPending = false;
      renderSetupButtons();
    }
  }

  async function stopRun() {
    if (!state.runId || !isActive()) return;
    ui.stop.disabled = true;
    try {
      await fetchJson(`/api/runs/${encodeURIComponent(state.runId)}/stop`, { method: 'POST' });
      await refreshRun(state.runId);
      showToast('已停止发送新请求；已发出的请求仍会完成并计入时间和费用。');
    } catch (error) {
      showToast(`停止请求失败：${error.message}`, true);
      renderSetupButtons();
    }
  }

  async function exportRun() {
    if (!state.runId) return;
    ui.export.disabled = true;
    try {
      const response = await fetch(`/api/runs/${encodeURIComponent(state.runId)}/export`, { cache: 'no-store' });
      if (!response.ok) {
        let message = `导出失败（HTTP ${response.status}）`;
        try { const data = await response.json(); message = data.detail || data.message || message; } catch { /* Keep HTTP summary. */ }
        throw new Error(message);
      }
      const blob = await response.blob();
      const objectUrl = URL.createObjectURL(blob);
      const anchor = document.createElement('a');
      const disposition = response.headers.get('content-disposition') || '';
      const filenameMatch = disposition.match(/filename\*?=(?:UTF-8''|\")?([^\";]+)/i);
      anchor.href = objectUrl;
      anchor.download = filenameMatch ? decodeURIComponent(filenameMatch[1]) : `jev-run-${state.runId}.json`;
      document.body.append(anchor);
      anchor.click();
      anchor.remove();
      URL.revokeObjectURL(objectUrl);
      showToast('本轮运行记录已导出。');
    } catch (error) {
      showToast(`导出失败：${error.message}`, true);
    } finally {
      renderSetupButtons();
    }
  }

  function setFilter(filter) {
    state.filter = filter;
    state.page = 1;
    renderTable();
  }

  function bindEvents() {
    ui.start.addEventListener('click', () => openConfirm('full'));
    ui.startPilot.addEventListener('click', () => openConfirm('pilot32'));
    ui.confirmForm.addEventListener('submit', (event) => {
      event.preventDefault();
      ui.confirmDialog.close();
      startRun(state.pendingScope);
    });
    el('cancel-run').addEventListener('click', () => ui.confirmDialog.close());
    ui.stop.addEventListener('click', stopRun);
    ui.export.addEventListener('click', exportRun);
    ui.concurrency.addEventListener('change', () => {
      if (state.bootstrap) updateConfirmCopy();
    });
    ui.filterButtons.forEach((button) => button.addEventListener('click', () => setFilter(button.dataset.filter)));
    ui.search.addEventListener('input', () => { state.page = 1; renderTable(); });
    ui.previousPage.addEventListener('click', () => { state.page = Math.max(1, state.page - 1); renderTable(); });
    ui.nextPage.addEventListener('click', () => { state.page += 1; renderTable(); });
    ui.resultsBody.addEventListener('click', (event) => {
      const button = event.target.closest('[data-case-id]');
      if (button) openCaseDetail(button.dataset.caseId);
    });
    ui.caseGrid.addEventListener('click', (event) => {
      const button = event.target.closest('[data-case-id]');
      if (button) openCaseDetail(button.dataset.caseId);
    });
    el('label-help').addEventListener('click', () => ui.labelDialog.showModal());
    el('show-mismatches').addEventListener('click', () => {
      setFilter('incorrect');
      el('results-title').scrollIntoView({ behavior: 'smooth', block: 'start' });
    });
    window.addEventListener('keydown', (event) => {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === 'k') {
        event.preventDefault();
        ui.search.focus();
      }
    });
    state.elapsedTimer = window.setInterval(updateElapsedDisplay, 100);
  }

  bindEvents();
  loadApp();
})();
