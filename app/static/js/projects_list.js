async function fetchProjects() {
    const res = await fetch("/api/projects", { headers: { "Accept": "application/json" } });
    if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        throw new Error(data.error || "Failed to load projects");
    }
    return res.json();
}

function statusClass(status) {
    switch (status) {
        case "готово":
            return "pm-status-ready";
        case "генерируется":
            return "pm-status-running";
        case "ошибка":
            return "pm-status-error";
        case "новый":
        default:
            return "pm-status-new";
    }
}

function renderProjects(items) {
    const list = document.getElementById("pmProjectsList");
    if (!list) return;

    list.innerHTML = "";
    if (!items || items.length === 0) {
        list.innerHTML = '<div class="pm-muted">Пока нет созданных проектов.</div>';
        return;
    }

    for (const p of items) {
        const row = document.createElement("div");
        row.className = "pm-project-row";
        row.dataset.projectId = p.project_id;
        row.title = p.shirt_filename;

        row.innerHTML = `
            <div class="pm-project-left">
                <div class="pm-project-title">${p.shirt_filename}</div>
                <div class="pm-project-sub">
                    референсов: ${p.references_count ?? 0}
                    <span class="pm-project-status ${statusClass(p.status)}">• ${p.status}</span>
                </div>
            </div>
            <button class="pm-project-delete" type="button" data-project-id="${p.project_id}" aria-label="Удалить проект">×</button>
        `;

        row.addEventListener("click", () => {
            window.location.href = `/projects/${p.project_id}`;
        });

        const delBtn = row.querySelector(".pm-project-delete");
        delBtn.addEventListener("click", async (e) => {
            e.stopPropagation();
            const projectId = delBtn.getAttribute("data-project-id");
            if (!projectId) return;

            const ok = confirm("Удалить проект?");
            if (!ok) return;

            delBtn.disabled = true;
            delBtn.textContent = "…";

            try {
                const res = await fetch(`/api/projects/${projectId}`, { method: "DELETE" });
                const data = await res.json().catch(() => ({}));
                if (!res.ok) throw new Error(data.error || "Delete failed");
                await refreshProjects();
            } catch (err) {
                alert(err.message || String(err));
                delBtn.disabled = false;
                delBtn.textContent = "×";
            }
        });

        list.appendChild(row);
    }
}

async function refreshProjects() {
    const data = await fetchProjects();
    renderProjects(data.items || []);
}

refreshProjects().catch((e) => {
    console.error(e);
    const list = document.getElementById("pmProjectsList");
    if (list) list.innerHTML = `<div class="pm-muted">Ошибка загрузки проектов: ${e.message || String(e)}</div>`;
});

