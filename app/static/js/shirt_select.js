function el(id) {
    return document.getElementById(id);
}

const searchInput = el("shirtSearch");
const searchBtn = el("shirtSearchBtn");
const shirtResults = el("shirtResults");
const shirtStatus = el("shirtStatus");

const modal = el("pmShirtModal");
const modalImg = el("pmModalImg");
const modalFilename = el("pmModalFilename");
const modalCreateBtn = el("pmModalCreateBtn");
const modalStatus = el("pmModalStatus");
const modalCloseBtn = el("pmModalCloseBtn");

let selected = null; // { filename, preview_url, original_url }
let debounceTimer = null;

function setStatus(text, show = true) {
    if (!shirtStatus) return;
    shirtStatus.textContent = text;
    shirtStatus.style.display = show ? "block" : "none";
}

function renderItems(items, total) {
    shirtResults.innerHTML = "";
    if (!items || items.length === 0) {
        shirtResults.innerHTML = '<div class="pm-muted">Ничего не найдено.</div>';
        return;
    }

    for (const item of items) {
        const card = document.createElement("div");
        card.className = "pm-card pm-card-shirt";

        card.innerHTML = `
            <div class="pm-card-title" title="${item.filename}">${item.filename}</div>
            <img class="pm-card-img" src="${item.preview_url}" alt="${item.filename}" loading="lazy" referrerpolicy="no-referrer">
            <button class="pm-btn pm-btn-secondary pm-choose pm-card-choose" type="button" data-filename="${item.filename}" data-preview="${item.preview_url}">
                Выбрать
            </button>
        `;

        // Если превью по какой-то причине не загрузилось — не оставляем пустой ящик.
        const imgEl = card.querySelector(".pm-card-img");
        if (imgEl) {
            imgEl.addEventListener("error", () => {
                imgEl.style.background = "rgba(148, 163, 184, 0.10)";
                imgEl.alt = "preview unavailable";
            });
        }

        card.querySelector(".pm-choose").addEventListener("click", () => {
            selected = {
                filename: item.filename,
                preview_url: item.preview_url,
                original_url: item.original_url,
            };

            modalImg.src = selected.original_url || selected.preview_url;
            modalFilename.textContent = selected.filename;
            modalCreateBtn.disabled = false;
            modalStatus.textContent = "";

            modal.style.display = "block";
            modalCreateBtn.textContent = "Создать проект и перейти к генерации";
        });

        shirtResults.appendChild(card);
    }

    const totalCount = typeof total === "number" ? total : items.length;
    const remaining = totalCount - items.length;
    if (remaining > 0) {
        const more = document.createElement("div");
        more.className = "pm-card pm-card-more";
        more.innerHTML = `
            <div class="pm-card-more-box">
                Еще <b>${remaining}</b> принтов<br>
                <span class="pm-muted">уточните поиск</span>
            </div>
        `;
        shirtResults.appendChild(more);
    }
}

async function fetchShirts(query) {
    const url = new URL("/api/shirts", window.location.origin);
    if (query) url.searchParams.set("q", query);
    url.searchParams.set("limit", "6");

    setStatus("Загрузка...");
    const res = await fetch(url, { headers: { "Accept": "application/json" } });
    if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        throw new Error(data.error || "Failed to fetch shirts");
    }
    return res.json();
}

async function searchAndRender() {
    const q = (searchInput.value || "").trim();
    try {
        selected = null;
        if (modal) modal.style.display = "none";
        setStatus("Загрузка...");

        const data = await fetchShirts(q);
        renderItems(data.items || [], data.total);

        setStatus("", false);
    } catch (e) {
        console.error(e);
        setStatus(e.message || String(e));
    }
}

function closeModal() {
    if (!modal) return;
    modal.style.display = "none";
    modalStatus.textContent = "";
    modalCreateBtn.disabled = true;
}

searchBtn.addEventListener("click", searchAndRender);
searchInput.addEventListener("input", () => {
    if (debounceTimer) clearTimeout(debounceTimer);
    debounceTimer = setTimeout(() => searchAndRender(), 350);
});

modalCloseBtn.addEventListener("click", closeModal);
modal.addEventListener("click", (e) => {
    const target = e.target;
    if (target && target.getAttribute && target.getAttribute("data-close") === "1") closeModal();
});

modalCreateBtn.addEventListener("click", async () => {
    if (!selected) return;
    modalCreateBtn.disabled = true;
    modalCreateBtn.textContent = "Создание проекта...";
    modalStatus.textContent = "Ждите, создаём проект...";

    try {
        const res = await fetch("/api/projects", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ shirt_filename: selected.filename }),
        });
        const data = await res.json().catch(() => ({}));
        if (!res.ok) throw new Error(data.error || "Failed to create project");

        window.location.href = `/projects/${data.project_id}`;
    } catch (e) {
        alert(e.message || String(e));
        modalCreateBtn.disabled = false;
        modalCreateBtn.textContent = "Создать проект и перейти к генерации";
        modalStatus.textContent = "";
    }
});

// initial load: show all
searchAndRender();

