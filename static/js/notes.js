async function openNote(note_id) {
    await window.open('/notes/update-view/?note_id=' + note_id);
}
