async function openNotes(material_id) {
    await window.open('/notes?material_id=' + material_id);
}

const addHotkeys = () => {
    let textInputs = document.querySelectorAll('.altch');

    let onClick = (e) => {
        let input = e.target;
        
        // on Alt-Q
        if (e.keyCode === 81 && e.altKey) {
            input.value += '«»';
        }
        // on Alt-T
        else if (e.keyCode === 84 && e.altKey) {
            input.value += '–';
        }
        // on Ctrl-B
        else if (e.keyCode === 66 && e.ctrlKey) {
            input.value += '<span class="font-weight-bold"></span>';
        }
        // on Ctrl-I
        else if (e.keyCode === 73 && e.ctrlKey) {
            input.value += '<span class="font-italic"></span>';
        }
        // on Alt-B
        else if (e.keyCode === 66 && e.altKey) {
            input.value += '<span class="sub"></span>';
        }
        // on Alt-P
        else if (e.keyCode === 80 && e.altKey) {
            input.value += '<span class="sup"></span>';
        }
    }
    for (let textInput of textInputs) {
        textInput.addEventListener('keyup', onClick, true);
    }
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

scope.addEventListener("click", (e) => {
    // ? close the menu if the user clicks outside of it
    if (e.target.offsetParent !== contextMenu) {
      contextMenu.classList.remove("visible");
      contextMenu.innerHTML = '';
    }
});

window.onscroll = () => {
    contextMenu.classList.remove("visible");
    contextMenu.innerHTML = '';
};

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

const addMaterialLog = (material_id) => {
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
    if (await isMaterialReading(material.id)) {
        contextMenu.appendChild(addMaterialLog(material.id));
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

const isNoteDeleted = async (note_id) => {
    let resp = await fetch(`/notes/is-deleted?note_id=${note_id}`, {
        method: 'GET',
        headers: {'Content-type': 'application/json'},
    });

    let json = await resp.json();
    return json['is_deleted'];
}

const addNoteContextMenuItems = async (note) => {
    // ? on duplicate click don't add items again;
    if (contextMenu.children.length > 0) {
        return;
    }

    contextMenu.appendChild(openNoteBtn(note.id));
    contextMenu.appendChild(editNoteBtn(note.id));
    if (await isNoteDeleted(note.id)) {
        contextMenu.appendChild(restoreNoteBtn(note.id));
    } else {
        contextMenu.appendChild(deleteNoteBtn(note.id));
    }
}

addContextMenu('.material', addMaterialContextMenuItems);
addContextMenu('.queue-item', addQueueItemContextMenuItems);
addContextMenu('.note', addNoteContextMenuItems);

document.addEventListener("DOMContentLoaded", async () => {
    addHotkeys();
});
