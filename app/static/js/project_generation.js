function el(id) {
    return document.getElementById(id);
}

const projectId = window.pmProjectId;
const initialReferences = window.pmInitialReferences || [];

const dropzone = el("pmDropzone");
const refFilesInput = el("pmReferenceFiles");
const uploadBtn = el("pmUploadRefsBtn");
const uploadStatus = el("pmUploadStatus");
const genBtn = el("pmGenerateAllBtn");
const genStatus = el("pmGenStatus");
const selectedFilesInfo = el("pmSelectedFilesInfo");
const refsCountEl = el("pmRefsCount");
const downloadAllBtn = el("pmDownloadAllBtn");

const refsList = el("pmReferencesList");

const imageModal = el("pmImageModal");
const imageModalImg = el("pmImageModalImg");
const imageModalMeta = el("pmImageModalMeta");
const imageModalCloseBtn = el("pmImageModalCloseBtn");
const imageModalPrevBtn = el("pmImageModalPrevBtn");
const imageModalNextBtn = el("pmImageModalNextBtn");

function setStatus(elNode, text, show = true) {
    if (!elNode) return;
    elNode.textContent = text || "";
    elNode.style.display = show ? "block" : "none";
}

function formatFilesCount(n) {
    const num = Number(n) || 0;
    // Простое склонение:
    // 1 файл, 2-4 файла, 5+ файлов (в т.ч. 0)
    if (num === 1) return `${num} файл`;
    if (num >= 2 && num <= 4) return `${num} файла`;
    return `${num} файлов`;
}

function updateSelectedFilesInfo() {
    if (!selectedFilesInfo || !refFilesInput) return;
    const n = refFilesInput.files ? refFilesInput.files.length : 0;
    if (n > 0) {
        selectedFilesInfo.style.display = "block";
        selectedFilesInfo.textContent = `Выбрано: ${formatFilesCount(n)}`;
    } else {
        selectedFilesInfo.style.display = "none";
        selectedFilesInfo.textContent = "";
    }
}

function updateRefsCount() {
    if (!refsCountEl || !refsList) return;
    const n = refsList.querySelectorAll('.pm-card-ref[data-reference-id]').length;
    refsCountEl.textContent = `Референсов: ${n}`;
}

function updateGenerateButtonState() {
    if (!genBtn || !refsList) return;
    const cards = refsList.querySelectorAll('.pm-card-ref[data-reference-id]');
    const total = cards.length;
    const allHavePrompt = total > 0 && Array.from(cards).every((c) => c.dataset.hasPrompt === "true");
    genBtn.disabled = !allHavePrompt;
    updateDownloadAllButtonState();
}

function updateDownloadAllButtonState() {
    if (!downloadAllBtn || !refsList || !projectId) return;
    const hasResults = refsList.querySelectorAll('.pm-ref-download[data-original-url]').length > 0;
    if (hasResults) {
        downloadAllBtn.href = `/api/projects/${projectId}/download-all`;
        downloadAllBtn.style.display = "";
        downloadAllBtn.classList.remove("disabled");
    } else {
        downloadAllBtn.href = "#";
        downloadAllBtn.style.display = "none";
    }
}

let modalImages = [];
let modalImageIndex = -1;

function getModalImages() {
    if (!refsList) return [];
    const imgs = Array.from(refsList.querySelectorAll('img[data-fullsrc]'))
        .filter((img) => img.dataset && img.dataset.fullsrc);

    return imgs.map((img) => {
        const card = img.closest(".pm-card-ref");
        const refId = card?.dataset?.referenceId || "";
        const isResult = img.classList.contains("pm-ref-result-img");
        const label = isResult ? "Результат" : "Исходник";
        return {
            src: img.dataset.fullsrc,
            metaText: refId ? `${label}: ${refId}` : label,
        };
    });
}

function openImageModalEntry(index) {
    if (!imageModal || !imageModalImg || !modalImages || modalImages.length === 0) return;

    modalImageIndex = Math.max(0, Math.min(index, modalImages.length - 1));
    const entry = modalImages[modalImageIndex];

    if (imageModalMeta) imageModalMeta.textContent = entry?.metaText || "";
    imageModalImg.src = entry?.src || "";
    imageModal.style.display = "block";
}

function openImageModal(src, metaText = "") {
    if (!imageModal || !imageModalImg) return;
    modalImages = getModalImages();
    const idx = modalImages.findIndex((e) => e.src === src);
    if (idx >= 0) openImageModalEntry(idx);
    else {
        modalImageIndex = -1;
        if (imageModalMeta) imageModalMeta.textContent = metaText || "";
        imageModalImg.src = src || "";
        imageModal.style.display = "block";
    }
}

function closeImageModal() {
    if (!imageModal) return;
    imageModal.style.display = "none";
    if (imageModalMeta) imageModalMeta.textContent = "";
    if (imageModalImg) imageModalImg.src = "";
}

function navigateImage(delta) {
    if (!imageModal || imageModal.style.display !== "block") return;
    if (!modalImages || modalImages.length === 0) return;

    const next = modalImageIndex + delta;
    const wrapped = (next + modalImages.length) % modalImages.length;
    openImageModalEntry(wrapped);
}

if (imageModalCloseBtn) {
    imageModalCloseBtn.addEventListener("click", closeImageModal);
}
if (imageModal) {
    imageModal.addEventListener("click", (e) => {
        const target = e.target;
        if (target && target.getAttribute && target.getAttribute("data-close") === "1") {
            closeImageModal();
        }
    });
}

if (imageModalPrevBtn) {
    imageModalPrevBtn.addEventListener("click", () => navigateImage(-1));
}
if (imageModalNextBtn) {
    imageModalNextBtn.addEventListener("click", () => navigateImage(1));
}

document.addEventListener("keydown", (e) => {
    if (!imageModal || imageModal.style.display !== "block") return;
    if (e.key === "Escape") closeImageModal();
    if (e.key === "ArrowLeft") navigateImage(-1);
    if (e.key === "ArrowRight") navigateImage(1);
});

function getPromptStatusHtml(ref) {
    if (ref.generated_prompt) {
        const escaped = escapeHtml(ref.generated_prompt).replace(/"/g, "&quot;");
        return '<span class="pm-prompt-copy pm-ref-openai-prompt" data-prompt="' + escaped + '" role="button" tabindex="0">Promt</span> — Промпт готов';
    }
    return getPromptStatusText(ref, null);
}

function getPromptStatusText(ref, elapsedSec) {
    if (ref.generated_prompt) return "Промпт готов — Promt";
    if (ref.prompt_error) return "Ошибка: " + (ref.prompt_error.length > 120 ? ref.prompt_error.slice(0, 120) + "…" : ref.prompt_error);
    if (elapsedSec != null && elapsedSec >= 0) {
        if (elapsedSec < 3) return "Отправка в OpenAI…";
        if (elapsedSec > 3600) return "Ожидание ответа OpenAI…";
        return "Ожидание ответа OpenAI (" + elapsedSec + " сек)";
    }
    return "Ожидание ответа OpenAI…";
}

function hasPrompt(ref) {
    return !!ref.generated_prompt;
}

function isPromptPending(ref) {
    return !ref.generated_prompt && !ref.prompt_error;
}

const elapsedIntervals = {};

function stopElapsedForCard(refId) {
    const id = elapsedIntervals[refId];
    if (id) {
        clearInterval(id);
        delete elapsedIntervals[refId];
    }
}

function getElapsedSecondsSince(createdAtIso, promptStartedAtIso) {
    const iso = promptStartedAtIso || createdAtIso;
    if (!iso) return 0;
    let str = iso;
    if (!/Z$/.test(str) && !/[+-]\d{2}:\d{2}$/.test(str)) str = str + "Z";
    const created = new Date(str).getTime();
    if (isNaN(created)) return 0;
    const sec = Math.floor((Date.now() - created) / 1000);
    return Math.max(0, Math.min(sec, 3600));
}

function startElapsedForCard(card, refId, createdAtIso, promptStartedAtIso) {
    stopElapsedForCard(refId);
    const statusEl = card.querySelector(".pm-ref-prompt-status");
    if (!statusEl) return;
    let sec = getElapsedSecondsSince(createdAtIso, promptStartedAtIso);
    statusEl.textContent = getPromptStatusText({ generated_prompt: null, prompt_error: null }, sec);
    const id = setInterval(() => {
        sec++;
        statusEl.textContent = getPromptStatusText({ generated_prompt: null, prompt_error: null }, sec);
    }, 1000);
    elapsedIntervals[refId] = id;
}

function escapeHtml(s) {
    if (!s) return "";
    const d = document.createElement("div");
    d.textContent = s;
    return d.innerHTML;
}

function renderReferenceCard(ref) {
    const promptStatusText = getPromptStatusText(ref, isPromptPending(ref) ? 0 : null);
    const hasPromptVal = hasPrompt(ref);
    const promptStatusHtml = hasPromptVal && ref.generated_prompt
        ? getPromptStatusHtml(ref)
        : promptStatusText;
    const hasResult = !!(ref.result_preview_url && ref.result_original_url);
    const resultStatusText = hasResult ? "Результат: готово" : "Результат: ожидание";
    const emptyStyle = hasResult ? "display:none;" : "";
    const resultImgStyle = hasResult ? "" : "display:none;";
    const resultPreview = ref.result_preview_url || "";
    const resultOriginal = ref.result_original_url || "";

    const card = document.createElement("div");
    card.className = "pm-card pm-card-ref";
    card.dataset.referenceId = ref.id;
    card.dataset.hasPrompt = hasPromptVal ? "true" : "false";

    const { baseStyle, torsoStyle } = getSelectedStyles();
    const kieParamsText = `Fit: ${baseStyle}. Print placement: ${torsoStyle}`;
    const kiePromptLine = hasPromptVal
        ? `<span class="pm-ref-kie-prompt">Промпт в Kie</span> — <span class="pm-ref-kie-params">${kieParamsText}</span>`
        : "";
    card.innerHTML = `
        <div class="pm-ref-meta-top">
            <div class="pm-card-title">reference: ${ref.id}</div>
            <div class="pm-muted pm-ref-prompt-status">${promptStatusHtml}</div>
            <div class="pm-muted pm-ref-kie-status" style="${hasPromptVal ? '' : 'display:none;'}">${kiePromptLine}</div>
            <div class="pm-muted pm-ref-status">${resultStatusText}</div>
            <div class="pm-muted pm-ref-error" style="display:none;margin-top:6px;"></div>
        </div>

        <div class="pm-ref-pair">
            <div class="pm-ref-col">
                <div class="pm-muted pm-ref-col-title">Исходник</div>
                <img
                    class="pm-card-img pm-ref-pair-img pm-ref-original-img"
                    src="${ref.preview_url}"
                    alt="Исходник"
                    data-fullsrc="${ref.original_url}"
                    loading="lazy"
                >
            </div>
            <div class="pm-ref-col">
                <div class="pm-muted pm-ref-col-title">Результат</div>
                <div class="pm-ref-result-empty" style="${emptyStyle}">Результат пока не готов</div>
                <img
                    class="pm-card-img pm-ref-pair-img pm-ref-result-img"
                    src="${resultPreview}"
                    alt="Результат"
                    data-fullsrc="${resultOriginal}"
                    loading="lazy"
                    style="${resultImgStyle}"
                >
            </div>
        </div>

        <div class="pm-ref-buttons">
            <button class="pm-btn pm-btn-secondary pm-ref-regenerate-prompt" type="button" data-reference-id="${ref.id}">
                Промпт
            </button>
            <button class="pm-btn pm-btn-secondary pm-ref-regenerate" type="button" data-reference-id="${ref.id}" ${!hasPromptVal ? 'disabled' : ''}>
                Перегенерировать
            </button>
            <button class="pm-btn pm-btn-secondary pm-ref-download" type="button" data-reference-id="${ref.id}"
                data-original-url="${resultOriginal}" style="${hasResult ? '' : 'display:none;'}">
                <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                    <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/>
                    <polyline points="7 10 12 15 17 10"/>
                    <line x1="12" y1="15" x2="12" y2="3"/>
                </svg>
                Скачать
            </button>
        </div>
    `;

    const originalImg = card.querySelector(".pm-ref-original-img");
    if (originalImg) {
        originalImg.addEventListener("click", () => {
            const full = originalImg.dataset.fullsrc || "";
            if (full) openImageModal(full, `Исходник: ${ref.id}`);
        });
    }

    const resultImg = card.querySelector(".pm-ref-result-img");
    if (resultImg) {
        resultImg.addEventListener("click", () => {
            const full = resultImg.dataset.fullsrc || "";
            if (full) openImageModal(full, `Результат: ${ref.id}`);
        });
    }

    const regenBtn = card.querySelector(".pm-ref-regenerate");
    if (regenBtn) {
        regenBtn.addEventListener("click", () => regenerateReference(ref.id, regenBtn));
    }

    const downloadBtn = card.querySelector(".pm-ref-download");
    if (downloadBtn) {
        downloadBtn.addEventListener("click", () => {
            const url = downloadBtn.dataset.originalUrl || resultOriginal;
            if (url) downloadResult(url, ref.id);
        });
    }

    const promptBtn = card.querySelector(".pm-ref-regenerate-prompt");
    if (promptBtn) {
        promptBtn.addEventListener("click", () => regeneratePrompt(ref.id, promptBtn, card));
    }

    const promptCopySpan = card.querySelector(".pm-prompt-copy");
    if (promptCopySpan) {
        promptCopySpan.addEventListener("click", (e) => { e.preventDefault(); e.stopPropagation(); copyPromptToClipboard(promptCopySpan); });
        promptCopySpan.addEventListener("keydown", (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); copyPromptToClipboard(promptCopySpan); } });
        setupOpenaiPromptTooltip(promptCopySpan);
    }

    const kiePromptSpan = card.querySelector(".pm-ref-kie-prompt");
    if (kiePromptSpan) setupKiePromptTooltip(kiePromptSpan, ref.id);

    refsList.appendChild(card);

    if (isPromptPending(ref)) {
        startElapsedForCard(card, ref.id, ref.created_at, ref.prompt_started_at);
    }
}

function copyPromptToClipboard(span) {
    const text = span.getAttribute("data-prompt");
    if (!text) return;
    const done = () => {
        const orig = span.textContent;
        span.textContent = "Скопировано!";
        setTimeout(() => { span.textContent = orig; }, 800);
    };
    if (navigator.clipboard?.writeText) {
        navigator.clipboard.writeText(text).then(done).catch(() => {
            fallbackCopy(text, done);
        });
    } else {
        fallbackCopy(text, done);
    }
}

function fallbackCopy(text, onDone) {
    const ta = document.createElement("textarea");
    ta.value = text;
    ta.style.position = "fixed";
    ta.style.left = "-9999px";
    ta.style.top = "0";
    document.body.appendChild(ta);
    ta.select();
    try {
        if (document.execCommand("copy")) onDone();
    } finally {
        document.body.removeChild(ta);
    }
}

function setupPromptCopyHandler(card) {
    const span = card.querySelector(".pm-prompt-copy");
    if (!span) return;
    span.addEventListener("click", (e) => { e.preventDefault(); e.stopPropagation(); copyPromptToClipboard(span); });
    span.addEventListener("keydown", (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); copyPromptToClipboard(span); } });
}

function updateCardPromptStatus(card, ref) {
    const refId = card.dataset.referenceId;
    stopElapsedForCard(refId);
    const statusEl = card.querySelector(".pm-ref-prompt-status");
    const kieStatusEl = card.querySelector(".pm-ref-kie-status");
    if (!statusEl) return;
    const content = hasPrompt(ref) && ref.generated_prompt ? getPromptStatusHtml(ref) : getPromptStatusText(ref);
    statusEl.innerHTML = content;
    if (kieStatusEl) {
        if (hasPrompt(ref)) {
            kieStatusEl.style.display = "";
            const { baseStyle, torsoStyle } = getSelectedStyles();
            const kieParamsText = `Fit: ${baseStyle}. Print placement: ${torsoStyle}`;
            kieStatusEl.innerHTML = '<span class="pm-ref-kie-prompt">Промпт в Kie</span> — <span class="pm-ref-kie-params">' + kieParamsText + "</span>";
            const kieSpan = kieStatusEl.querySelector(".pm-ref-kie-prompt");
            if (kieSpan) setupKiePromptTooltip(kieSpan, refId);
        } else {
            kieStatusEl.style.display = "none";
        }
    }
    card.dataset.hasPrompt = hasPrompt(ref) ? "true" : "false";
    if (ref.prompt_error) {
        statusEl.classList.add("pm-ref-prompt-error");
    } else {
        statusEl.classList.remove("pm-ref-prompt-error");
    }
    if (hasPrompt(ref) && ref.generated_prompt) {
        setupPromptCopyHandler(card);
        const promptSpan = card.querySelector(".pm-prompt-copy");
        if (promptSpan) setupOpenaiPromptTooltip(promptSpan);
    }
    const regenBtn = card.querySelector(".pm-ref-regenerate");
    if (regenBtn) regenBtn.disabled = !hasPrompt(ref);
}

function refreshReferencesFromApi() {
    if (!projectId || !refsList) return Promise.resolve([]);
    return fetch(`/api/projects/${projectId}/references`)
        .then((r) => r.json())
        .then((data) => data.items || [])
        .catch(() => []);
}

let pollIntervalId = null;

function stopPolling() {
    if (pollIntervalId) {
        clearInterval(pollIntervalId);
        pollIntervalId = null;
    }
}

function startPollingForPrompts() {
    stopPolling();
    function poll() {
        refreshReferencesFromApi().then((refs) => {
            if (!refs || refs.length === 0) return;
            let anyPending = false;
            for (const ref of refs) {
                const card = refsList.querySelector(`.pm-card-ref[data-reference-id="${ref.id}"]`);
                if (!card) continue;
                if (card.dataset.generating === "true") continue;
                if (isPromptPending(ref)) {
                    anyPending = true;
                } else {
                    updateCardPromptStatus(card, ref);
                }
                if (ref.result_preview_url && ref.result_original_url) {
                    setRefResult(ref.id, ref.result_preview_url, ref.result_original_url);
                    setRefStatus(ref.id, "готово");
                }
            }
            updateGenerateButtonState();
            if (!anyPending) stopPolling();
        });
    }
    poll();
    pollIntervalId = setInterval(poll, 2500);
}

function applyRefResultsFromApi(refs) {
    if (!refs || !refsList) return;
    for (const ref of refs) {
        const card = refsList.querySelector(`.pm-card-ref[data-reference-id="${ref.id}"]`);
        if (card && card.dataset.generating === "true") continue;
        if (ref.result_preview_url && ref.result_original_url) {
            setRefResult(ref.id, ref.result_preview_url, ref.result_original_url);
            setRefStatus(ref.id, "готово");
        }
    }
    updateDownloadAllButtonState();
}

function getFriendlyFetchError(e) {
    const msg = (e && e.message) || String(e);
    if (/failed to fetch|networkerror|load failed/i.test(msg)) {
        return "Сетевая ошибка. Проверьте соединение или попробуйте позже.";
    }
    return msg;
}

function selectModel(modelValue) {
    const grid = document.getElementById("pmModelGrid");
    if (!grid) return;
    grid.querySelectorAll(".pm-model-item").forEach((btn) => {
        const isSelected = (btn.dataset.model || "") === (modelValue || "");
        btn.classList.toggle("selected", !!isSelected);
        btn.setAttribute("aria-pressed", isSelected);
    });
}

async function loadModels() {
    const grid = document.getElementById("pmModelGrid");
    if (!grid) return;
    try {
        const res = await fetch("/api/models");
        const data = await res.json().catch(() => ({}));
        const items = data.items || [];
        grid.innerHTML = "";
        const noneBtn = document.createElement("button");
        noneBtn.type = "button";
        noneBtn.className = "pm-model-item pm-model-item-none selected";
        noneBtn.dataset.model = "";
        noneBtn.setAttribute("aria-pressed", "true");
        noneBtn.innerHTML = '<img class="pm-model-thumb" src="/static/img/model-empty.svg" alt="Без модели"><span class="pm-model-name">Без модели</span>';
        noneBtn.addEventListener("click", () => selectModel(""));
        grid.appendChild(noneBtn);
        for (const m of items) {
            const id = m.filename || m.id;
            const url = m.url || `/media/models/${id}`;
            const btn = document.createElement("button");
            btn.type = "button";
            btn.className = "pm-model-item";
            btn.dataset.model = id;
            btn.setAttribute("aria-pressed", "false");
            const thumb = document.createElement("img");
            thumb.className = "pm-model-thumb";
            thumb.src = url;
            thumb.alt = id;
            thumb.loading = "lazy";
            const name = document.createElement("span");
            name.className = "pm-model-name";
            name.textContent = id.length > 14 ? id.slice(0, 11) + "…" : id;
            btn.appendChild(thumb);
            btn.appendChild(name);
            btn.addEventListener("click", () => selectModel(id));
            grid.appendChild(btn);
        }
    } catch (e) {
        console.error("Failed to load models:", e);
    }
}

function renderInitial() {
    refsList.innerHTML = "";
    for (const ref of initialReferences) {
        renderReferenceCard(ref);
    }
    updateRefsCount();
    updateGenerateButtonState();
    if (initialReferences.some(isPromptPending)) {
        startPollingForPrompts();
    }
    loadModels();
    refreshReferencesFromApi().then(applyRefResultsFromApi);
}

async function uploadReferences() {
    const files = refFilesInput.files;
    if (!files || files.length === 0) {
        alert("Выберите файлы референсов");
        return;
    }

    await uploadFiles(files);
}

async function uploadFiles(files) {
    if (!files || files.length === 0) {
        alert("Выберите файлы референсов");
        return;
    }

    const form = new FormData();
    for (const f of files) form.append("files", f);

    setStatus(uploadStatus, "Загрузка файлов...", true);
    uploadBtn.disabled = true;

    try {
        const res = await fetch(`/api/projects/${projectId}/references`, {
            method: "POST",
            body: form,
        });
        const data = await res.json().catch(() => ({}));
        if (!res.ok) throw new Error(data.error || "Upload failed");

        const items = data.items || [];
        for (const ref of items) {
            // avoid duplicates: if card exists, skip
            if (refsList.querySelector(`.pm-card-ref[data-reference-id="${ref.id}"]`)) continue;
            renderReferenceCard(ref);
        }

        refFilesInput.value = "";
        updateSelectedFilesInfo();
        updateRefsCount();
        updateGenerateButtonState();
        setStatus(uploadStatus, "Готово", true);
        if (items.some(isPromptPending)) {
            startPollingForPrompts();
        }
        setTimeout(() => setStatus(uploadStatus, "", false), 1500);
    } catch (e) {
        console.error(e);
        setStatus(uploadStatus, e.message || String(e), true);
    } finally {
        uploadBtn.disabled = false;
    }
}

let statusTooltipEl = null;
let statusTooltipTimeout = null;

function setupOpenaiPromptTooltip(spanEl) {
    if (!spanEl) return;
    spanEl.addEventListener("mouseenter", () => {
        const text = spanEl.getAttribute("data-prompt") || "";
        if (text) showStatusTooltip(spanEl, `Промпт от OpenAI:\n\n${text}`);
    });
    spanEl.addEventListener("mouseleave", (e) => {
        const related = e.relatedTarget;
        if (statusTooltipEl && statusTooltipEl.contains(related)) return;
        hideStatusTooltip();
    });
}

function setupKiePromptTooltip(spanEl, referenceId) {
    if (!spanEl) return;
    spanEl.addEventListener("mouseenter", () => {
        showStatusTooltip(spanEl, "Загрузка…");
        const { baseStyle, torsoStyle, model } = getSelectedStyles();
        const params = new URLSearchParams({ base_style: baseStyle, torso_style: torsoStyle, model });
        const loadingText = "Загрузка…";
        fetch(`/api/projects/${projectId}/references/${referenceId}/generation-preview?${params}`)
            .then((res) => res.json().then((data) => ({ ok: res.ok, data })).catch(() => ({ ok: false, data: {} })))
            .then(({ ok, data }) => {
                if (!statusTooltipEl || !document.body.contains(statusTooltipEl)) return;
                if (statusTooltipEl.textContent !== loadingText) return;
                if (!ok) {
                    statusTooltipEl.textContent = "Ошибка: " + (data.error || "не удалось загрузить превью");
                    return;
                }
                const roleNames = { model: "Модель", shirt: "Футболка", reference: "Референс" };
                const filesList = (data.files || []).map((f) => `${roleNames[f.role] || f.role}: ${f.name}`).join("\n");
                statusTooltipEl.textContent = `Промпт в Kie:\n\n${data.prompt || "(пусто)"}\n\nФайлы:\n${filesList || "(нет)"}`;
            })
            .catch((e) => {
                if (statusTooltipEl && document.body.contains(statusTooltipEl) && statusTooltipEl.textContent === loadingText) {
                    statusTooltipEl.textContent = "Ошибка загрузки";
                }
            });
    });
    spanEl.addEventListener("mouseleave", (e) => {
        const related = e.relatedTarget;
        if (statusTooltipEl && statusTooltipEl.contains(related)) return;
        hideStatusTooltip();
    });
}

function showStatusTooltip(anchorEl, text) {
    hideStatusTooltip();
    const tip = document.createElement("div");
    tip.className = "pm-status-tooltip";
    tip.textContent = text;
    tip.style.whiteSpace = "pre-wrap";
    document.body.appendChild(tip);
    statusTooltipEl = tip;
    const rect = anchorEl.getBoundingClientRect();
    let left = rect.left;
    let top = rect.bottom + 6;
    if (left + tip.offsetWidth > window.innerWidth - 8) left = window.innerWidth - tip.offsetWidth - 8;
    if (top + tip.offsetHeight > window.innerHeight - 8) top = rect.top - tip.offsetHeight - 6;
    if (left < 8) left = 8;
    if (top < 8) top = 8;
    tip.style.left = `${left}px`;
    tip.style.top = `${top}px`;
    tip.addEventListener("mouseenter", () => {});
    tip.addEventListener("mouseleave", () => hideStatusTooltip());
}

function hideStatusTooltip() {
    if (statusTooltipEl && statusTooltipEl.parentNode) statusTooltipEl.parentNode.removeChild(statusTooltipEl);
    statusTooltipEl = null;
}

function setRefStatus(referenceId, status, errorMessage) {
    const card = refsList.querySelector(`[data-reference-id="${referenceId}"]`);
    if (!card) return;
    const statusEl = card.querySelector(".pm-ref-status");
    const errorEl = card.querySelector(".pm-ref-error");

    if (statusEl) statusEl.textContent = `Результат: ${status}`;
    if (errorEl) {
        if (errorMessage) {
            errorEl.textContent = errorMessage;
            errorEl.style.display = "block";
        } else {
            errorEl.textContent = "";
            errorEl.style.display = "none";
        }
    }
}

function setRefResult(referenceId, previewUrl, originalUrl) {
    const card = refsList.querySelector(`[data-reference-id="${referenceId}"]`);
    if (!card) return;
    const empty = card.querySelector(".pm-ref-result-empty");
    const img = card.querySelector(".pm-ref-result-img");
    const downloadBtn = card.querySelector(".pm-ref-download");

    if (empty) empty.style.display = "none";
    if (img) {
        img.src = previewUrl;
        img.dataset.fullsrc = originalUrl;
        img.style.display = "block";
    }
    if (downloadBtn && originalUrl) {
        downloadBtn.dataset.originalUrl = originalUrl;
        downloadBtn.style.display = "";
    }
}

function downloadResult(url, referenceId) {
    const ext = (url.match(/\.(png|jpg|jpeg|webp)(\?|$)/i) || [])[1] || "png";
    const a = document.createElement("a");
    a.href = url;
    a.download = `photomaker-${referenceId}.${ext}`;
    a.style.display = "none";
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
}

function getSelectedStyles() {
    const baseStyle = document.querySelector('input[name="pmBaseStyle"]:checked')?.value || "base";
    const torsoStyle = document.querySelector('input[name="pmTorsoStyle"]:checked')?.value || "chest";
    const selectedItem = document.querySelector(".pm-model-item.selected");
    const model = selectedItem?.dataset.model || "";
    return { baseStyle, torsoStyle, model };
}

function updateAllKieParamsSpans() {
    const { baseStyle, torsoStyle } = getSelectedStyles();
    const text = `Fit: ${baseStyle}. Print placement: ${torsoStyle}`;
    document.querySelectorAll(".pm-ref-kie-params").forEach((el) => { el.textContent = text; });
}

async function regeneratePrompt(referenceId, promptBtn, card) {
    if (!projectId) return;
    const oldText = promptBtn ? promptBtn.textContent : "";
    if (promptBtn) {
        promptBtn.disabled = true;
        promptBtn.textContent = "Генерируем…";
    }
    try {
        const res = await fetch(`/api/projects/${projectId}/references/${referenceId}/regenerate-prompt`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({}),
        });
        const data = await res.json().catch(() => ({}));
        if (!res.ok) throw new Error(data.error || "Regenerate prompt failed");

        card.dataset.hasPrompt = "false";
        const statusEl = card.querySelector(".pm-ref-prompt-status");
        if (statusEl) {
            statusEl.textContent = "Отправка в OpenAI…";
            statusEl.classList.remove("pm-ref-prompt-error");
        }

        startElapsedForCard(card, referenceId, data.created_at, data.prompt_started_at);
        startPollingForPrompts();
    } catch (e) {
        console.error(e);
        const statusEl = card.querySelector(".pm-ref-prompt-status");
        if (statusEl) {
            statusEl.textContent = "Ошибка: " + (e.message || String(e));
            statusEl.classList.add("pm-ref-prompt-error");
        }
    } finally {
        if (promptBtn) {
            promptBtn.disabled = false;
            promptBtn.textContent = oldText || "Промпт";
        }
    }
}

function startResultElapsedTimer(referenceIds, onTick) {
    const start = Date.now();
    const id = setInterval(() => {
        const sec = Math.floor((Date.now() - start) / 1000);
        onTick(sec);
    }, 1000);
    onTick(0);
    return () => clearInterval(id);
}

async function regenerateReference(referenceId, regenBtn) {
    if (!projectId) return;

    const card = refsList?.querySelector(`.pm-card-ref[data-reference-id="${referenceId}"]`);
    if (card) card.dataset.generating = "true";
    stopPolling();

    const btn = regenBtn;
    const oldText = btn ? btn.textContent : "";
    if (btn) {
        btn.disabled = true;
        btn.textContent = "Перегенерируем...";
    }

    const stopTimer = startResultElapsedTimer([referenceId], (sec) => {
        setRefStatus(referenceId, `ожидание (${sec} сек с момента отправки)`);
    });

    try {
        const { baseStyle, torsoStyle, model } = getSelectedStyles();
        const res = await fetch(`/api/projects/${projectId}/references/${referenceId}/regenerate`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ base_style: baseStyle, torso_style: torsoStyle, model }),
        });
        const data = await res.json().catch(() => ({}));
        if (!res.ok) throw new Error(data.error || "Regenerate failed");

        if (data.status === "completed") {
            setRefStatus(referenceId, "готово");
            if (data.preview_url && data.original_url) {
                setRefResult(referenceId, data.preview_url, data.original_url);
            }
        } else if (data.status === "failed") {
            setRefStatus(referenceId, "ошибка", data.error_message || "");
        } else {
            setRefStatus(referenceId, data.status || "неизвестно", data.error_message || "");
        }
    } catch (e) {
        console.error(e);
        setRefStatus(referenceId, "ошибка", getFriendlyFetchError(e));
    } finally {
        stopTimer();
        if (card) delete card.dataset.generating;
        if (btn) {
            btn.disabled = card?.dataset.hasPrompt !== "true";
            btn.textContent = oldText || "Перегенерировать";
        }
        if (initialReferences.some(isPromptPending)) startPollingForPrompts();
    }
}

function delay(ms) {
    return new Promise((r) => setTimeout(r, ms));
}
function randomBetween(min, max) {
    return Math.floor(Math.random() * (max - min + 1)) + min;
}

async function generateAll() {
    if (!projectId) return;
    genBtn.disabled = true;
    stopPolling();

    const cards = refsList.querySelectorAll(".pm-card-ref[data-reference-id]");
    const refIds = Array.from(cards).map((c) => c.dataset.referenceId).filter(Boolean);
    cards.forEach((c) => { c.dataset.generating = "true"; });

    const { baseStyle, torsoStyle, model } = getSelectedStyles();
    const MAX_CONCURRENT = 10;
    const STAGGER_MIN = 1000;
    const STAGGER_MAX = 3000;
    let completed = 0;
    const refTimers = {};

    const startTimerForRef = (refId) => {
        const start = Date.now();
        refTimers[refId] = setInterval(() => {
            const sec = Math.floor((Date.now() - start) / 1000);
            setRefStatus(refId, `ожидание (${sec} сек с момента отправки)`);
        }, 1000);
    };
    const stopTimerForRef = (refId) => {
        if (refTimers[refId]) {
            clearInterval(refTimers[refId]);
            delete refTimers[refId];
        }
    };

    const processRef = async (refId) => {
        await delay(randomBetween(STAGGER_MIN, STAGGER_MAX));
        startTimerForRef(refId);
        try {
            const res = await fetch(`/api/projects/${projectId}/references/${refId}/regenerate`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ base_style: baseStyle, torso_style: torsoStyle, model }),
            });
            const data = await res.json().catch(() => ({}));
            if (!res.ok) throw new Error(data.error || "Ошибка генерации");

            if (data.status === "completed") {
                setRefStatus(refId, "готово");
                if (data.preview_url && data.original_url) {
                    setRefResult(refId, data.preview_url, data.original_url);
                }
            } else if (data.status === "failed") {
                setRefStatus(refId, "ошибка", data.error_message || "Ошибка генерации");
            } else {
                setRefStatus(refId, data.status || "неизвестно", data.error_message || "");
            }
        } catch (e) {
            console.error(e);
            setRefStatus(refId, "ошибка", getFriendlyFetchError(e));
        } finally {
            stopTimerForRef(refId);
            completed++;
            setStatus(genStatus, `Генерация ${completed}/${refIds.length}...`, true);
        }
    };

    try {
        let nextIdx = 0;
        const runWorker = async () => {
            while (nextIdx < refIds.length) {
                const refId = refIds[nextIdx++];
                await processRef(refId);
            }
        };
        const workers = Array(Math.min(MAX_CONCURRENT, refIds.length))
            .fill()
            .map(() => runWorker());
        await Promise.all(workers);

        setStatus(genStatus, `Готово (${completed}/${refIds.length})`, true);
    } catch (e) {
        console.error(e);
        setStatus(genStatus, getFriendlyFetchError(e), true);
    } finally {
        Object.keys(refTimers).forEach(stopTimerForRef);
        cards.forEach((c) => delete c.dataset.generating);
        genBtn.disabled = false;
        if (initialReferences.some(isPromptPending)) startPollingForPrompts();
        setTimeout(() => setStatus(genStatus, "", false), 3000);
    }
}

function setDropzoneActive(active) {
    if (!dropzone) return;
    if (active) dropzone.classList.add("pm-dropzone-active");
    else dropzone.classList.remove("pm-dropzone-active");
}

if (dropzone) {
    dropzone.addEventListener("click", () => refFilesInput?.click());

    dropzone.addEventListener("dragover", (e) => {
        e.preventDefault();
        setDropzoneActive(true);
    });

    dropzone.addEventListener("dragleave", () => {
        setDropzoneActive(false);
    });

    dropzone.addEventListener("drop", async (e) => {
        e.preventDefault();
        setDropzoneActive(false);

        const files = e.dataTransfer?.files;
        if (!files || files.length === 0) return;

        // При дропе грузим сразу (как пользователь ожидает).
        if (selectedFilesInfo) {
            selectedFilesInfo.style.display = "block";
            selectedFilesInfo.textContent = `Выбрано: ${formatFilesCount(files.length)}`;
        }
        await uploadFiles(files);
    });
}

if (refFilesInput) {
    refFilesInput.addEventListener("change", updateSelectedFilesInfo);
    updateSelectedFilesInfo();
}

uploadBtn.addEventListener("click", uploadReferences);
genBtn.addEventListener("click", generateAll);

document.querySelectorAll('input[name="pmBaseStyle"], input[name="pmTorsoStyle"]').forEach((radio) => {
    radio.addEventListener("change", updateAllKieParamsSpans);
});

renderInitial();

// Надежная обработка клика по картинкам (карточки могут рендериться динамически)
if (refsList) {
    refsList.addEventListener("click", (e) => {
        const target = e.target;
        if (!target || !target.closest) return;
        const img = target.closest(".pm-ref-original-img, .pm-ref-result-img");
        if (!img) return;
        const full = img.dataset.fullsrc || "";
        if (!full) return;
        const metaText = img.classList.contains("pm-ref-result-img")
            ? "Результат"
            : "Исходник";
        openImageModal(full, metaText);
    });
}

// Клик по картинке принта — открыть в полноэкранном просмотре
const shirtImg = el("pmProjectShirtImg");
if (shirtImg) {
    const openShirtModal = () => {
        const full = shirtImg.dataset?.fullsrc || "";
        const meta = shirtImg.dataset?.metatext || "Принт";
        if (full) openImageModal(full, meta);
    };
    shirtImg.addEventListener("click", openShirtModal);
    shirtImg.addEventListener("keydown", (e) => {
        if (e.key === "Enter" || e.key === " ") {
            e.preventDefault();
            openShirtModal();
        }
    });
}

