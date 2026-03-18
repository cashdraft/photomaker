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

function renderReferenceCard(ref) {
    const card = document.createElement("div");
    card.className = "pm-card pm-card-ref";
    card.dataset.referenceId = ref.id;

    card.innerHTML = `
        <div class="pm-ref-meta-top">
            <div class="pm-card-title">reference: ${ref.id}</div>
            <div class="pm-muted pm-ref-status">Статус: ожидание</div>
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
                <div class="pm-ref-result-empty">Результат пока не готов</div>
                <img
                    class="pm-card-img pm-ref-pair-img pm-ref-result-img"
                    src=""
                    alt="Результат"
                    data-fullsrc=""
                    loading="lazy"
                    style="display:none;"
                >
            </div>
        </div>

        <button class="pm-btn pm-btn-secondary pm-ref-regenerate" type="button" data-reference-id="${ref.id}">
            Перегенерировать
        </button>
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

    refsList.appendChild(card);
}

function renderInitial() {
    refsList.innerHTML = "";
    for (const ref of initialReferences) {
        renderReferenceCard(ref);
    }
    updateRefsCount();
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

    setStatus(uploadStatus, "Загрузка...", true);
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
        setStatus(uploadStatus, "Готово", true);
        setTimeout(() => setStatus(uploadStatus, "", false), 1500);
    } catch (e) {
        console.error(e);
        setStatus(uploadStatus, e.message || String(e), true);
    } finally {
        uploadBtn.disabled = false;
    }
}

function setRefStatus(referenceId, status, errorMessage) {
    const card = refsList.querySelector(`[data-reference-id="${referenceId}"]`);
    if (!card) return;
    const statusEl = card.querySelector(".pm-ref-status");
    const errorEl = card.querySelector(".pm-ref-error");

    if (statusEl) statusEl.textContent = `Статус: ${status}`;
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

    if (empty) empty.style.display = "none";
    if (img) {
        img.src = previewUrl;
        img.dataset.fullsrc = originalUrl;
        img.style.display = "block";
    }
}

function getSelectedStyles() {
    const baseStyle = document.querySelector('input[name="pmBaseStyle"]:checked')?.value || "base";
    const torsoStyle = document.querySelector('input[name="pmTorsoStyle"]:checked')?.value || "chest";
    return { baseStyle, torsoStyle };
}

async function regenerateReference(referenceId, regenBtn) {
    if (!projectId) return;

    const btn = regenBtn;
    const oldText = btn ? btn.textContent : "";
    if (btn) {
        btn.disabled = true;
        btn.textContent = "Перегенерируем...";
    }

    try {
        const { baseStyle, torsoStyle } = getSelectedStyles();
        const res = await fetch(`/api/projects/${projectId}/references/${referenceId}/regenerate`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ base_style: baseStyle, torso_style: torsoStyle }),
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
        setRefStatus(referenceId, "ошибка", e.message || String(e));
    } finally {
        if (btn) {
            btn.disabled = false;
            btn.textContent = oldText || "Перегенерировать";
        }
    }
}

async function generateAll() {
    if (!projectId) return;
    genBtn.disabled = true;
    setStatus(genStatus, "Генерация...", true);

    try {
        const { baseStyle, torsoStyle } = getSelectedStyles();

        const res = await fetch(`/api/projects/${projectId}/generate`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ base_style: baseStyle, torso_style: torsoStyle }),
        });
        const data = await res.json().catch(() => ({}));
        if (!res.ok) throw new Error(data.error || "Generate failed");

        const items = data.items || [];
        for (const job of items) {
            if (job.status === "completed") {
                setRefStatus(job.reference_id, "готово");
                setRefResult(job.reference_id, job.preview_url, job.original_url);
            } else if (job.status === "failed") {
                setRefStatus(job.reference_id, "ошибка", job.error_message || "");
            } else {
                setRefStatus(job.reference_id, job.status || "неизвестно", job.error_message || "");
            }
        }

        setStatus(genStatus, "Готово", true);
    } catch (e) {
        console.error(e);
        setStatus(genStatus, e.message || String(e), true);
    } finally {
        genBtn.disabled = false;
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

