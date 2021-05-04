async function openNotes(material_id) {
    await window.open('/notes?material_id=' + material_id);
}

document.addEventListener("DOMContentLoaded", () => {
    let textInputs = document.querySelectorAll('.altch');

    let onClick = (e) => {
        let input = e.target;

        if (e.key == 'q' && e.altKey) {
            input.value += '«»';
        }
        else if (e.key == 't' && e.altKey) {
            input.value += '–';
        }
        else if (e.key == 'b' && e.ctrlKey) {
            input.value += '<b></b>';
        }
        else if (e.key == 'i' && e.ctrlKey) {
            input.value += '<i></i>';
        }
    }
    for (textInput of textInputs) {
        textInput.addEventListener('keyup', onClick, true);
    }
})
