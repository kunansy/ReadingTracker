let collection = document.getElementsByClassName("backup-nav");

let subnavbar = collection[0];
subnavbar.href = "";

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

subnavbar.onclick = async () => {
    let details = await backup();
    console.log(details);

    showSuccess(details);
};

console.log(subnavbar);