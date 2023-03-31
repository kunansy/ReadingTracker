// https://atuin.ru/blog/razletayushhiesya-chasticy-pri-nazhatii-na-knopku/
// modified and improved

function Celebrate(e) {
    // amount of items in animation
    let amount = 250;
    if (e.clientX === 0 && e.clientY === 0) {
        const bbox = e.target.getBoundingClientRect();
        const x = bbox.left + bbox.width / 2;
        const y = bbox.top + bbox.height / 2;
        for (let i = 0; i < 30; i++) {
            createParticle(x, y);
        }
    } else {
        for (let i = 0; i < amount; i++) {
            createParticle(e.clientX, e.clientY);
        }
    }
}
function createParticle(x, y) {
    const celebrate = document.createElement('celebrate');
    document.body.appendChild(celebrate);

    // size of all animation
    let destinationX = (Math.random() - 0.5) * 1000;
    let destinationY = (Math.random() - 0.5) * 800;
    let rotation = Math.random() * 520;
    let delay = Math.random() * 200;

    // hsl(30, 100, 50) – orange
    let color = `hsl(${Math.random() * 50 + 30}, 100%, 50%)`;
    // every fourth random item should be blue
    if (Math.floor(Math.random() * 100) % 4 === 0) {
        color = `hsl(${Math.random() * 50 + 200}, 70%, 50%)`;
    }

    celebrate.style.boxShadow = `0 0 ${Math.floor(Math.random() * 10 + 10)}px ${color}`;
    celebrate.style.background = color;
    celebrate.style.borderRadius = '50%';
    // sizes of the items
    let size = Math.random() * 5 + 4;
    celebrate.style.width = `${size}px`;
    celebrate.style.height = `${size}px`;

    const animation = celebrate.animate([
        {
            transform: `translate(-50%, -50%) translate(${x}px, ${y}px) rotate(0deg)`,
            opacity: 1
        },
        {
            transform: `translate(-50%, -50%) translate(${x + destinationX}px, ${y + destinationY}px) rotate(${rotation}deg)`,
            opacity: 0
        }
    ], {
        duration: Math.random() * 1000 + 5000, // duration of the animation
        easing: 'cubic-bezier(0, .9, .57, 1)',
        delay: delay
    });
    animation.onfinish = removeParticle;
}
function removeParticle (e) {
    e.target.effect.target.remove();
}

document.querySelectorAll(".celebrate-btn").forEach((btn) => {
    let timeoutId = null;

    // celebrate only of mouse stay on bth some time
    btn.addEventListener('mouseover', (e) => {
        timeoutId = setTimeout(() => {Celebrate(e)}, 150);
    });
    // otherwise don't celebrate (if the bth overed accidentally)
    btn.addEventListener('mouseout', () => {
        clearTimeout(timeoutId);
    })
});
