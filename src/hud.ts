import type { CarController } from './car';

const hudEl = document.getElementById('hud')!;

export function updateHud(car: CarController) {
  const pos = car.mesh.position;
  const headingDeg = THREE.MathUtils.radToDeg(car.heading) % 360;

  hudEl.textContent =
    `Speed: ${car.speedKmh.toFixed(0)} km/h\n` +
    `Pos:   ${pos.x.toFixed(1)}, ${pos.z.toFixed(1)}\n` +
    `Heading: ${headingDeg.toFixed(0)}°`;
}

// Import THREE only for MathUtils
import * as THREE from 'three';
