async function chooseNote(note_id, material_id) {
    let noteIdField = document.getElementById('note_id');
    noteIdField.value = note_id;

    let materialIdField = document.getElementById('material_id');
    materialIdField.value = material_id;
}

const getMaterialNotes = async (material_id) => {
    let resp = await fetch(`/notes/material-notes?material_id=${material_id.trim()}`, {
        method: 'GET',
        headers: {'Content-type': 'application/json'},
    });

    return await resp.json();
}

const createP = (cls, text) => {
    let p = document.createElement("p");
    p.classList.add(cls);
    p.textContent = text;

    return p;
}

const createMaterialNoteContent = (note) => {
    return createP("note-content", note.content);
}
const createMaterialNotePage = (note) => {
    return createP("note-page", `Page: ${note.page}`);
}
const createMaterialNoteId = (note) => {
    return createP("note-id", `ID: ${note.note_id}`);
}

const createMaterialNoteLi = (note) => {
    const li = document.createElement("li");
    li.className = "note hover";
    li.title = "Click to choose this note";
    li.onclick = () => {chooseNote(note.note_id, note.material_id)};

    li.appendChild(createMaterialNoteContent(note));
    li.appendChild(createMaterialNotePage(note));
    li.appendChild(createMaterialNoteId(note));

    return li;
}

const updateNotesCount = (count) => {
    let field = document.getElementById("srch-label");
    field.textContent = `Search notes | ${count} items`;
}

let searchField = document.getElementById("material_id");
console.log(searchField);
if (searchField) {
    searchField.addEventListener("input", async (e) => {
        const materialId = e.target.value;
        if (!(materialId && isUuid(materialId))) {
            return;
        }

        const ul = document.getElementById("notes-list");
        ul.innerHTML = "";

        let materialNotes = await getMaterialNotes(materialId);
        materialNotes = materialNotes['notes'];

        for (let note of materialNotes) {
            ul.append(createMaterialNoteLi(note));
        }
        updateNotesCount(materialNotes.length);
    });
}
