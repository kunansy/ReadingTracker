document.getElementById("material_id").addEventListener("input", async (e) => {
    let material_id = e.target.value;
    if (!material_id) {
        return;
    }

    let resp = await fetch(`/reading_log/completion-info?material_id=${material_id}`, {
        method: 'GET',
        headers: {'Content-type': 'application/json'},
    });

    let json = await resp.json();

    let reading_info = document.getElementById("reading-info");
    let pages_read = json["pages_read"];
    let material_pages = json["material_pages"];

    reading_info.value = `${pages_read} / ${material_pages}, ${(pages_read / material_pages * 100).toFixed(1)}%`
    reading_info.textContent = reading_info.value;
})