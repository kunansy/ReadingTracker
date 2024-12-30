const backup = async () => {
    let resp = await fetch("/system/backup", {
        method: 'GET',
        headers: {'Content-type': 'application/json'},
    });

    return await resp.json();
};

const successTemplate = "Success! Backup was created successfully.\n" +
    "        ({materials_count} materials, {logs_count} logs, {statuses_count} statuses, {notes_count} notes,\n" +
    "        {cards_count} cards, {repeats_count} repeats, {repeats_history_count} note repeats)";

const showSuccess = (json) => {
    let success = document.getElementById("backup-success");
    let successText = successTemplate;

    success.removeAttribute("hidden");

    for (let [key, value] of Object.entries(json)) {
        successText = successText.replace(`\{${key}\}`, value);
    }
    success.textContent = successText;
};

const showError = () => {
    let err = document.getElementById("backup-failed");
    err.removeAttribute("hidden");
};

const hideSuccess = () => {
    let success = document.getElementById("backup-success");
    success.setAttribute("hidden", "hidden");
};
const hideError = () => {
    let err = document.getElementById("backup-failed");
    err.setAttribute("hidden", "hidden");
};

document.querySelectorAll(".backup-nav").forEach((btn) => {
    btn.addEventListener("click", async (e) => {
        e.preventDefault();

        backup().then((details) => {
            showSuccess(details);
            setTimeout(hideSuccess, 5000);
        }).catch((err) => {
            showError();
            setTimeout(hideError, 5000);
        })
    });
});