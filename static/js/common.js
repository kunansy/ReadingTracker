async function openNotes(material_id) {
    await window.open('/notes?material_id=' + material_id);
}
