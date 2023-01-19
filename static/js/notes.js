async function openNote(note_id, target_ = "_blank") {
    await window.open('/notes/update-view/?note_id=' + note_id, target=target_);
}

async function addTag(tag) {
    let content = document.getElementById('input-content');

    // WTF: the f*cking shadow DOM
    content.textContent = content.value + ' ' + tag;
    content.value = content.textContent;
}