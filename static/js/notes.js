async function openNote(note_id) {
    await window.open('/notes/update-view/?note_id=' + note_id);
}

async function addLink(link) {
    let content = document.getElementById('input-content');

    // WTF: the f*cking shadow DOM
    content.textContent = content.value + ' ' + link;
    content.value = content.textContent;
}