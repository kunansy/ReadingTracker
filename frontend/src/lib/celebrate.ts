import type { MouseEvent as ReactMouseEvent } from "react";

/** Particle burst on button hover (legacy celebrate.js behavior). */

function createParticle(x: number, y: number): void {
  const celebrate = document.createElement("celebrate");
  document.body.appendChild(celebrate);

  const destinationX = (Math.random() - 0.5) * 1000;
  const destinationY = (Math.random() - 0.5) * 800;
  const rotation = Math.random() * 520;
  const delay = Math.random() * 200;

  let color = `hsl(${Math.random() * 50 + 30}, 100%, 50%)`;
  if (Math.floor(Math.random() * 100) % 4 === 0) {
    color = `hsl(${Math.random() * 50 + 200}, 70%, 50%)`;
  }

  celebrate.style.boxShadow = `0 0 ${Math.floor(Math.random() * 10 + 10)}px ${color}`;
  celebrate.style.background = color;
  celebrate.style.borderRadius = "50%";
  const size = Math.random() * 5 + 4;
  celebrate.style.width = `${size}px`;
  celebrate.style.height = `${size}px`;

  const animation = celebrate.animate(
    [
      {
        transform: `translate(-50%, -50%) translate(${x}px, ${y}px) rotate(0deg)`,
        opacity: 1,
      },
      {
        transform: `translate(-50%, -50%) translate(${x + destinationX}px, ${y + destinationY}px) rotate(${rotation}deg)`,
        opacity: 0,
      },
    ],
    {
      duration: Math.random() * 1000 + 5000,
      easing: "cubic-bezier(0, .9, .57, 1)",
      delay,
    },
  );
  animation.onfinish = () => {
    celebrate.remove();
  };
}

export function celebrateAtEvent(e: ReactMouseEvent): void {
  const amount = 250;
  if (e.clientX === 0 && e.clientY === 0) {
    const bbox = (e.target as HTMLElement).getBoundingClientRect();
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
