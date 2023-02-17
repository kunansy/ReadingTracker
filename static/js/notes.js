async function openNote(note_id, target_ = "_blank") {
    await window.open('/notes/update-view/?note_id=' + note_id, target=target_);
}

async function addTag(tag) {
    let content = document.getElementById('input-content');

    // WTF: the f*cking shadow DOM
    content.textContent = content.value + ' ' + tag;
    content.value = content.textContent;
}

const recordAudio = async () => {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    const mediaRecorder = new MediaRecorder(stream);
    const audioChunks = [];

    mediaRecorder.addEventListener("dataavailable", event => {
        audioChunks.push(event.data);
    });

    document.getElementById("start").addEventListener("click", () => {
        mediaRecorder.start();
    });
    document.getElementById("stop").addEventListener("click", async () => {
        const audio = await stop();
        let fd = new FormData();
        fd.append("data", audio.audioBlob, "tmp.wav");

        const resp = await fetch(
            '/speech-to-text/transcript',
            {
                method: 'POST',
                body: fd,
                headers: {'Content-Type': 'multipart/form-data'}
            }
        );

        let json = await resp.json();
        let noteContent = document.getElementById('input-content');

        noteContent.textContent = noteContent.value + ' ' + json['transcript'];
        noteContent.value = noteContent.textContent;
    })

    const stop = () =>
        new Promise(resolve => {
            mediaRecorder.addEventListener("stop", () => {
                const audioBlob = new Blob(audioChunks, { type: "audio/mpeg" });
                resolve({ audioBlob });
            });

            mediaRecorder.stop();
        });
};

document.addEventListener("DOMContentLoaded", async () => {
    await recordAudio();
});
