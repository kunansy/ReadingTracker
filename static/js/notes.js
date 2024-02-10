async function openNote(note_id, target_ = "_blank") {
    await window.open('/notes/note?note_id=' + note_id, target=target_);
}

async function addTag(tag, newLine = false) {
    let content = document.getElementById('input-content');
    let newContent = '';

    if (content.value.length === 0) {
        newContent = tag;
    } else if (tag.startsWith("#") && !content.value.contains("#")) {
        newContent = content.value + tag;
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
            loader.classList.remove("loader");
            document.body.classList.remove("loader-background");
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

if (document.getElementById("start")) {
    document.getElementById('start').addEventListener("click", async () => {
        if (isStarted) {
            return;
        }

        isStarted = true;
        const recorder = await recordAudio();
        console.log("Listening started");
        recorder.start();
    });
}

const getTags = async (material_id) => {
    let resp = await fetch(`/notes/tags?material_id=${material_id}`, {
        method: 'GET',
        headers: {'Content-type': 'application/json'},
    });

    return await resp.json();
};

if (document.getElementById("input_material_id")) {
    document.getElementById('input_material_id').addEventListener("input", async (e) => {
        const materialId = e.target.value;
        if (!(materialId && isUuid(materialId))) {
            return;
        }

        const ul = document.getElementById("tags-list");
        ul.innerHTML = "";

        let materialTags = await getTags(materialId);
        materialTags = materialTags['tags'];

        for (let tag of materialTags) {
            const li = document.createElement("li");
            li.setAttribute("value", tag);
            tag = `#${tag}`;
            li.onclick = () => {addTag(tag)};
            li.textContent = tag;

            ul.append(li);
        }
    });
}

const links = document.querySelectorAll("a#link-ref");
if (links) {
    links.forEach((link) => {
        link.addEventListener("mouseover", async (e) => {
            const link_id = e.target.textContent.replace("[[", "").replace("]]", "");

            const cache = localStorage.getItem(`link-ref-${link_id}`);
            // TODO: it works only from cache
            if (cache) {
                link.title = cache;
            } else {
                const note = await getNote(link_id);
                const content = note["content"];

                localStorage.setItem(`link-ref-${link_id}`, content);
                link.title = content;
            }
        })
    })
}

const sleep = async (seconds) => {
    return new Promise(resolve => setTimeout(resolve, seconds));
};

const contentInput = document.getElementById("input-content");
if (contentInput) {
    contentInput.addEventListener("keyup", async (e) => {
        await sleep(2);
        const text = e.target.value;

        const resp = await fetch(
            `https://speller.yandex.net/services/spellservice.json/checkText?text=${text.replaceAll(" ", "+")}`,
            {
                method: "GET",
                headers: {'Content-type': 'application/json'},
            }
        );

        const errata = await resp.json();

        if (errata.length === 0) {
            document.getElementById("input-content-errata").innerHTML = '';
        }
        else {
            const alert = document.getElementById("input-content-errata");
            const image = document.createElement("img");

            image.id = "input-content-errata-img";
            image.src = "/static/errata-alert.png";

            alert.title = "";

            if (!alert.children.namedItem("input-content-errata-img")) {
                alert.appendChild(image);
            }

            let isFirst = true;
            for (let erratum of errata) {
                if (!isFirst) {
                    alert.title += '\n';
                }
                isFirst = false;
                alert.title += `${erratum["word"]} – ${erratum["s"].join(", ")}`
            }
        }
    })
}