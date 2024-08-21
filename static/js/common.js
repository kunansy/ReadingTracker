async function openNotes(material_id, page_size = null) {
    let url = `/notes?material_id=${material_id}`;
    if (page_size !== null) {
        url += `&page_size=${page_size}`
    }
    await window.open(url);
}

const surroundSelection = (field, prefix, siffux) => {
    const before = field.value.substring(0, field.selectionStart);
    const sel = field.value.substring(field.selectionStart, field.selectionEnd);
    const after = field.value.substring(field.selectionEnd);

    field.value = `${before}${prefix}${sel}${siffux}${after}`;
};

const isUuid = (value) => {
    const regexExp = /^[0-9a-fA-F]{8}\b-[0-9a-fA-F]{4}\b-[0-9a-fA-F]{4}\b-[0-9a-fA-F]{4}\b-[0-9a-fA-F]{12}$/gi;
    return regexExp.test(value);
}

const addHotKeys = () => {
    document.querySelectorAll('.altch').forEach((elem) => {
        elem.addEventListener("keydown", async (e) => {
            let input = e.target;

            // on Ctrl-Q
            if (e.keyCode === 81 && e.ctrlKey) {
                surroundSelection(input, '«', '»');
            }
            // on Ctrl-T
            else if (e.keyCode === 84 && e.ctrlKey) {
                input.value += '–';
            }
            // on Ctrl-B
            else if (e.keyCode === 66 && e.ctrlKey) {
                surroundSelection(input, "**", "**");
            }
            // on Ctrl-I
            else if (e.keyCode === 73 && e.ctrlKey) {
                surroundSelection(input, "*", "*");
            }
            // on Ctrl-J
            else if (e.keyCode === 74 && e.ctrlKey) {
                surroundSelection(input, "`", "`");
            }
            // on Alt-Down
            else if (e.keyCode === 40 && e.altKey) {
                surroundSelection(input, "<sub>", "</sub>");
            }
            // on Alt-Up
            else if (e.keyCode === 38 && e.altKey) {
                surroundSelection(input, "<sup>", "</sup>");
            }
            // on Ctrl-K
            else if (e.keyCode === 75 && e.ctrlKey) {
                let text = await navigator.clipboard.readText();
                text = text.trim();
                if (isUuid(text)) {
                    input.value += `\n[[${text}]]`;
                }
            }
        }, true);
    });
};

const contextMenu = document.getElementById("context-menu");
const scope = document.querySelector("body");

const normalizePosition = (mouseX, mouseY) => {
    // ? compute what is the mouse position relative to the container element (scope)
    let {
      left: scopeOffsetX,
      top: scopeOffsetY,
    } = scope.getBoundingClientRect();

    scopeOffsetX = scopeOffsetX < 0 ? 0 : scopeOffsetX;
    scopeOffsetY = scopeOffsetY < 0 ? 0 : scopeOffsetY;

    const scopeX = mouseX - scopeOffsetX;
    const scopeY = mouseY - scopeOffsetY;

    // ? check if the element will go out of bounds
    const outOfBoundsOnX = scopeX + contextMenu.clientWidth > scope.clientWidth;
    const outOfBoundsOnY = scopeY + contextMenu.clientHeight > scope.clientHeight;

    let normalizedX = mouseX;
    let normalizedY = mouseY;

    // ? normalize on X
    if (outOfBoundsOnX) {
        normalizedX = scopeOffsetX + scope.clientWidth - contextMenu.clientWidth;
    }
    // ? normalize on Y
    if (outOfBoundsOnY) {
        normalizedY = scopeOffsetY + scope.clientHeight - contextMenu.clientHeight;
    }

    return { normalizedX, normalizedY };
};

const addContextMenu = (selector, addContextMenuItemsFn) => {
    scope.querySelectorAll(selector).forEach((item) => {
        item.addEventListener("contextmenu", (event) => {
            if (!item.contains(event.target)) {
                return;
            }
            addContextMenuItemsFn(item);

            event.preventDefault();

            const { clientX: mouseX, clientY: mouseY } = event;

            const { normalizedX, normalizedY } = normalizePosition(mouseX, mouseY);

            contextMenu.classList.remove("visible");

            contextMenu.style.top = `${normalizedY}px`;
            contextMenu.style.left = `${normalizedX}px`;

            setTimeout(() => {
                contextMenu.classList.add("visible");
            });
        });
    });
}

const hideContentMenu = () => {
    contextMenu.classList.remove("visible");
    contextMenu.innerHTML = '';
}

scope.addEventListener("click", (e) => {
    // ? close the menu if the user clicks outside of it
    if (e.target.offsetParent !== contextMenu) {
        hideContentMenu();
    }
});

window.onscroll = hideContentMenu;

const createContextMenuItem = (name, onclickFn) => {
    const node = document.createElement("div");
    node.className = "item";
    node.onclick = onclickFn;
    node.textContent = name;

    return node;
}

const editMaterialBtn = (material_id) => {
    return createContextMenuItem(
        "Edit",
        () => {window.open('/materials/update-view/?material_id=' + material_id)}
    );
}

const openMaterialNotesBtn = (material_id) => {
    return createContextMenuItem(
        "Open notes",
        () => {window.open('/notes?material_id=' + material_id)}
    );
}

const addMaterialNotesBtn = (material_id) => {
    return createContextMenuItem(
        "Add note",
        () => {window.open('/notes/add-view?material_id=' + material_id)}
    );
}

const openMaterialLogBtn = (material_id) => {
    return createContextMenuItem(
        "Open reading log",
        () => {window.open('/reading_log/?material_id=' + material_id)}
    );
}

const addMaterialLogBtn = (material_id) => {
    return createContextMenuItem(
        "Add reading log",
        () => {window.open('/reading_log/add-view?material_id=' + material_id)}
    );
}

const isMaterialReading = async (material_id) => {
    let resp = await fetch(`/materials/is-reading?material_id=${material_id}`, {
        method: 'GET',
        headers: {'Content-type': 'application/json'},
    });

    let json = await resp.json();
    return json['is_reading'];
}

const addMaterialContextMenuItems = async (material) => {
    // ? on duplicate click don't add items again;
    if (contextMenu.children.length > 0) {
        return;
    }
    contextMenu.appendChild(editMaterialBtn(material.id));
    contextMenu.appendChild(openMaterialNotesBtn(material.id));

    if (material.classList.contains("reading")) {
        contextMenu.appendChild(openMaterialLogBtn(material.id));
        // add notes btn should be in this position
        contextMenu.appendChild(addMaterialNotesBtn(material.id));
        contextMenu.appendChild(addMaterialLogBtn(material.id));
    } else {
        contextMenu.appendChild(addMaterialNotesBtn(material.id));
    }
}

const swapQueueOrder = async (material_id, index) => {
    await fetch(`/materials/queue/swap-order?material_id=${material_id}&index=${index}`, {
        method: 'POST',
        headers: {'Content-type': 'application/json'},
    });

    await window.location.reload();
}

const moveToIndex = (name, material_id, index) => {
    return createContextMenuItem(
        name,
        async () => {await swapQueueOrder(material_id, index)}
    );
}

const getQueueEnd = async () => {
    let resp = await fetch("/materials/queue/end", {
        method: 'GET',
        headers: {'Content-type': 'application/json'},
    });

    let json = await resp.json();
    return json['index']
}

const getQueueStart = async () => {
    let resp = await fetch("/materials/queue/start", {
        method: 'GET',
        headers: {'Content-type': 'application/json'},
    });

    let json = await resp.json();
    return json['index']
}

const addQueueItemContextMenuItems = async (material) => {
    // ? replace 'material' context menu
    contextMenu.innerHTML = '';

    let materialId = material.id;
    let index = +material.getAttribute("index");
    let queueStart = await getQueueStart();
    let queueEnd = await getQueueEnd();

    contextMenu.appendChild(editMaterialBtn(materialId));
    if (index > queueStart) {
        contextMenu.appendChild(moveToIndex("Move top", materialId, queueStart));
        contextMenu.appendChild(moveToIndex("Move upper", materialId, index - 1));
    }
    if (index < queueEnd) {
        contextMenu.appendChild(moveToIndex("Move lower", materialId, index + 1));
        contextMenu.appendChild(moveToIndex("Move bottom", materialId, queueEnd));
    }
}

const openNoteBtn = (note_id) => {
    return createContextMenuItem(
        "Open",
        () => {window.open('/notes/note?note_id=' + note_id)}
    );
}

const editNoteBtn = (note_id) => {
    return createContextMenuItem(
        "Edit",
        () => {window.open('/notes/update-view?note_id=' + note_id)}
    );
}

const deleteNote = async (note_id) => {
    await fetch("/notes/delete", {
        method: 'DELETE',
        headers: {
            'Content-type': 'application/json'
        },
        body: JSON.stringify({'note_id': note_id})
    });

    await window.location.reload();
}

const restoreNote = async (note_id) => {
    await fetch("/notes/restore", {
        method: 'POST',
        headers: {
            'Content-type': 'application/json'
        },
        body: JSON.stringify({'note_id': note_id})
    });

    await window.location.reload();
}

const deleteNoteBtn = (note_id) => {
    return createContextMenuItem(
        "Delete",
        async () => {await deleteNote(note_id)}
    );
}

const restoreNoteBtn = (note_id) => {
    return createContextMenuItem(
        "Restore",
        async () => {await restoreNote(note_id)}
    );
}

const insertToRepeatQueue = (note_id) => {
    return createContextMenuItem(
        "Insert to repeat queue",
        async () => {
            let resp = await fetch(`/notes/repeat-queue/insert?note_id=${note_id}`, {
                method: 'POST',
                headers: {'Content-type': 'application/json'},
            });

            if (!resp.ok) {
                console.log("Error: " + await resp.text());
            }
        }
    );
}

const getNote = async (note_id) => {
    let resp = await fetch(`/notes/note-json?note_id=${note_id.trim()}`, {
        method: 'GET',
        headers: {'Content-type': 'application/json'},
    });

    return await resp.json();
}

const hasCards = async (note_id) => {
    let resp = await fetch(`/cards/has-cards?note_id=${note_id.trim()}`, {
        method: 'GET',
        headers: {'Content-type': 'application/json'},
    });

    return await resp.json();
}

const openCardsBtn = (note_id) => {
    return createContextMenuItem(
        "Open cards",
        () => {window.open(`/cards/list?note_id=${note_id}`)}
    );
}

const addCardBtn = (note_id, material_id) => {
    return createContextMenuItem(
        "Add card",
        () => {window.open(`/cards/add-view?note_id=${note_id}&material_id=${material_id}`)}
    );
}

const addNoteContextMenuItems = async (note) => {
    // ? on duplicate click don't add items again;
    if (contextMenu.children.length > 0) {
        return;
    }
    let note_json = await getNote(note.id);
    let has_cards = await hasCards(note.id);

    contextMenu.appendChild(openNoteBtn(note.id));
    contextMenu.appendChild(editNoteBtn(note.id));
    if (await note_json['is_deleted']) {
        contextMenu.appendChild(restoreNoteBtn(note.id));
    } else {
        contextMenu.appendChild(deleteNoteBtn(note.id));
    }
    if (has_cards.has_cards) {
        contextMenu.appendChild(openCardsBtn(note.id));
    } else {
        contextMenu.appendChild(addCardBtn(note.id, note_json.material_id));
    }
    contextMenu.appendChild(insertToRepeatQueue(note.id));

    let url = new URL(document.URL);
    // when it's a single note page
    if (url.pathname === "/notes/note") {
        contextMenu.appendChild(openMaterialNotesBtn(note_json['material_id']));
    }
}

const addCopyNoteIdListener = () => {
    document.querySelectorAll('.note-id-row').forEach((elem) => {
        elem.addEventListener("click", async () => {
            const noteId = elem.textContent.split(' ')[3].trim();
            const type = "text/plain";
            const blob = new Blob([noteId], { type });
            const data = [new ClipboardItem({ [type]: blob })];

            await navigator.clipboard.write(data);
        })
    })
}

const addLink = (note_id) => {
    let field = document.getElementById("note-link");
    field.value += `${note_id}`;
}

const addLinkBtn = (note_id) => {
    return createContextMenuItem(
        "Add link",
        () => {
            addLink(note_id);
            hideContentMenu();
        }
    );
}

const addNoteAlertContextMenuItems = (note) => {
    contextMenu.appendChild(openNoteBtn(note.id));
    contextMenu.appendChild(editNoteBtn(note.id));
    contextMenu.appendChild(addLinkBtn(note.id));
}

const editCardBtn = (card_id) => {
    console.log(card_id);

    return createContextMenuItem(
        "Edit card",
        () => {window.open('/cards/edit-view?card_id=' + card_id)}
    );
}

const addCardContextMenuItems = (card) => {
    let cardId = card.id.replaceAll("card-", "");

    contextMenu.appendChild(editCardBtn(cardId));
}

addContextMenu('.material', addMaterialContextMenuItems);
addContextMenu('.queue-item', addQueueItemContextMenuItems);
addContextMenu('.note', addNoteContextMenuItems);
addContextMenu('.add-note-alert', addNoteAlertContextMenuItems);
addContextMenu('.card', addCardContextMenuItems);

addCopyNoteIdListener();

document.addEventListener("DOMContentLoaded", async () => {
    addHotKeys();
});

const parseBtn = document.getElementById("parse-btn");
if (parseBtn) {
    parseBtn.onclick = async () => {
        let link = document.getElementById("parse-url").value;
        if (link.includes("habr")) {
            var resp = await fetch(`/materials/parse/habr?link=${link.toString()}`, {
                method: 'POST',
                headers: {'Content-type': 'application/json'},
            });
        } else if (link.includes("youtu")) {
            var resp = await fetch(`/materials/parse/youtube?link=${link.toString()}`, {
                method: 'POST',
                headers: {'Content-type': 'application/json'},
            });
        }

        let respJson = await resp.json();

        let titleField = document.getElementById("input-title");
        let authorsField = document.getElementById("input-authors");
        let durationField = document.getElementById("input-duration");
        let linkField = document.getElementById("input-link");
        let typeField = document.getElementById("input-type");

        titleField.textContent = respJson["title"];
        titleField.value = respJson["title"];

        authorsField.textContent = respJson["author"];
        authorsField.value = respJson["author"];

        durationField.textContent = respJson["duration"];
        durationField.value = respJson["duration"];

        typeField.textContent = respJson["type"];
        typeField.value = respJson["type"];

        linkField.textContent = respJson["link"];
        linkField.value = respJson["link"];
    };
}


document.querySelectorAll("p.note-content").forEach((e) => {
    e.innerHTML = marked.parse(e.innerHTML.replaceAll("<br>", "\n"));
});
