import type { CarController } from './car';

const hudEl = document.getElementById('hud')!;

export function updateHud(car: CarController) {
  hudEl.textContent = Math.round(car.speedKmh).toString().padStart(3, '0');
}
