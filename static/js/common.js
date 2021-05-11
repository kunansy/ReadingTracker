async function openNotes(material_id) {
    await window.open('/notes?material_id=' + material_id);
}

document.addEventListener("DOMContentLoaded", () => {
    let textInputs = document.querySelectorAll('.altch');

    let onClick = (e) => {
        let input = e.target;
        
        // on Alt-Q
        if (e.keyCode == 81 && e.altKey) {
            input.value += '«»';
        }
        // on Alt-T
        else if (e.keyCode == 84 && e.altKey) {
            input.value += '–';
        }
        // on Ctrl-B
        else if (e.keyCode == 66 && e.ctrlKey) {
            input.value += '<span class="font-weight-bold"></span>';
        }
        // on Ctrl-I
        else if (e.keyCode == 73 && e.ctrlKey) {
            input.value += '<span class="font-italic"></span>';
        }
    }
    for (textInput of textInputs) {
        textInput.addEventListener('keyup', onClick, true);
    }
})
