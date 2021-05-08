async function chooseNote(note_id, material_id) {
    let noteIdField = document.getElementById('note_id');
    noteIdField.value = note_id;

    let materialIdField = document.getElementById('material_id');
    materialIdField.value = material_id;
}
