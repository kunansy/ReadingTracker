(function () {
    const dialog = document.getElementById("complete-material-dialog");
    const dateInput = document.getElementById("complete-material-date");
    const cancelBtn = document.getElementById("complete-material-cancel");
    const confirmBtn = document.getElementById("complete-material-confirm");

    if (!dialog || !dateInput || !cancelBtn || !confirmBtn) {
        return;
    }

    let activeMaterialId = null;

    const setToday = () => {
        const today = new Date();
        const yyyy = today.getFullYear();
        const mm = String(today.getMonth() + 1).padStart(2, "0");
        const dd = String(today.getDate()).padStart(2, "0");
        dateInput.value = `${yyyy}-${mm}-${dd}`;
    };

    document.querySelectorAll(".complete-material-open").forEach((btn) => {
        btn.addEventListener("click", () => {
            activeMaterialId = btn.getAttribute("data-material-id");
            if (!activeMaterialId) {
                return;
            }
            setToday();
            dialog.showModal();
        });
    });

    cancelBtn.addEventListener("click", () => {
        dialog.close();
    });

    dialog.addEventListener("close", () => {
        activeMaterialId = null;
    });

    confirmBtn.addEventListener("click", async () => {
        const materialId = activeMaterialId;
        const completedAt = dateInput.value;
        if (!materialId || !completedAt) {
            return;
        }

        const url = `/materials/complete/${materialId}?completed_at=${encodeURIComponent(completedAt)}`;
        let response;
        try {
            response = await fetch(url, {
                method: "POST",
                credentials: "same-origin",
            });
        } catch (err) {
            window.alert(`Request failed: ${err}`);
            return;
        }

        if (response.ok) {
            dialog.close();
            const card = document.getElementById(materialId);
            if (card) {
                card.remove();
            }
            return;
        }

        const text = await response.text();
        let detail = response.statusText;
        if (text) {
            try {
                const body = JSON.parse(text);
                if (body && typeof body.detail === "string") {
                    detail = body.detail;
                } else if (body && Array.isArray(body.detail)) {
                    detail = body.detail.map((d) => d.msg || JSON.stringify(d)).join("; ");
                }
            } catch {
                detail = text.slice(0, 500);
            }
        }
        window.alert(`Could not complete material (${response.status}): ${detail}`);
    });
})();
