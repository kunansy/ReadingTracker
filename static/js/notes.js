async function openNote(note_id, target_ = "_blank") {
    await window.open('/notes/note?note_id=' + note_id, target=target_);
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
    let audioChunks = [];

    mediaRecorder.addEventListener("dataavailable", event => {
        audioChunks.push(event.data);
    });

    document.getElementById("start").addEventListener("click", () => {
        console.log("Listening started");
        audioChunks = [];
        mediaRecorder.start();
    });
    document.getElementById("stop").addEventListener("click", async () => {
        console.log("Listening stopped");
        const audio = await stop();
        console.log("Result audio ", audio.audioBlob.size);
        let fd = new FormData();
        fd.append("data", audio.audioBlob, "tmp.wav");

        fetch(
            '/notes/transcript',
            {
                method: 'POST',
                body: fd,
                headers: {'Content-Type': 'multipart/form-data'}
            }
        ).then(async (resp) => {
            let json = await resp.json();
            let noteContent = document.getElementById('input-content');

            noteContent.textContent = noteContent.value + ' ' + json['transcript'];
            noteContent.value = noteContent.textContent;
        }).catch((error) => {
            console.log(`Server error: ${error}`);
        }).finally(() => {
            audioChunks = [];
        });
    })

    const stop = () =>
        new Promise(resolve => {
            mediaRecorder.addEventListener("stop", () => {
                const audioBlob = new Blob(audioChunks, { type: "audio/mpeg" });
                resolve({ audioBlob });
            });

            mediaRecorder.stop();
        });
    return mediaRecorder;
};

let isStarted = false;

document.getElementById('start').addEventListener("click", async () => {
    if (!isStarted) {
        isStarted = true;
        const recorder = await recordAudio();
        console.log("Listening started");
        recorder.start();
    }
});
