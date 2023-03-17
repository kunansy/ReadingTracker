async function openNote(note_id, target_ = "_blank") {
    await window.open('/notes/note?note_id=' + note_id, target=target_);
}

async function addTag(tag, newLine = false) {
    let content = document.getElementById('input-content');
    let newContent = '';

    if (content.value.length === 0) {
        newContent = tag;
    } else if (newLine) {
        newContent = content.value + '\n' + tag;
    } else {
        newContent = content.value + ' ' + tag;
    }

    // WTF: the f*cking shadow DOM
    content.textContent = newContent;
    content.value = newContent;
}

const recordAudio = async () => {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    const mediaRecorder = new MediaRecorder(stream);
    const loader = document.getElementById("loader");
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

        document.body.classList.add("loader-background");
        loader.classList.add("loader");

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
            let newContent = '';

            if (noteContent.value.length === 0) {
                newContent = json['transcript'];
            } else {
                newContent = noteContent.value + ' ' + json['transcript'];
            }

            noteContent.textContent = newContent;
            noteContent.value = newContent;
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
    if (isStarted) {
        return;
    }

    isStarted = true;
    const recorder = await recordAudio();
    console.log("Listening started");
    recorder.start();
});
