const backup = async () => {
    let resp = await fetch("/system/backup", {
        method: 'GET',
        headers: {'Content-type': 'application/json'},
    });

    return await resp.json();
};

const showSuccess = (json) => {
    let success = document.getElementById("backup-success");
    success.removeAttribute("hidden");

    for (let [key, value] of Object.entries(json)) {
        success.textContent = success.textContent.replace(`\{${key}\}`, value);
    }
};

const hideSuccess = () => {
    let success = document.getElementById("backup-success");
    success.setAttribute("hidden", "hidden");
};

document.querySelectorAll(".backup-nav").forEach((btn) => {
    btn.addEventListener("click", async (e) => {
        e.preventDefault();

        let details = await backup();
        showSuccess(details);
        setTimeout(hideSuccess, 5000);
    });
});